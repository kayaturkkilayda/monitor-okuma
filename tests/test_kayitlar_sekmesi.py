import sqlite3

import pytest

import kayitlar_sekmesi as ks
from veritabani import baglan


def kayit_ekle(kayit_id, cekim, kamera="K1", durum="bekliyor", dosya_yolu="yok.avif",
               gonderim=None, son_hata=None, sira=1):
    with baglan() as db:
        db.execute(
            "INSERT INTO kayitlar (kayit_id, cift_id, tesis_kodu, kamera_kodu, yatak_kodu,"
            " cekim_zamani, saat_dilimi, sira, dosya_yolu, durum, sonraki_deneme, son_hata,"
            " gonderim_zamani) VALUES (?, 'c', 'H01', ?, 'Y1', ?, '+03:00', ?, ?, ?, ?, ?, ?)",
            (kayit_id, kamera, cekim, sira, dosya_yolu, durum, cekim, son_hata, gonderim))


@pytest.fixture
def ornekler():
    kayit_ekle("a", "2026-10-01 09:00:00", "K1", "gonderildi", gonderim="2026-10-01 09:00:05")
    kayit_ekle("b", "2026-10-02 10:00:00", "K2", "bekliyor")
    kayit_ekle("c", "2026-10-02 23:59:59", "K1", "hatali", son_hata="HTTP 401")
    kayit_ekle("d", "2026-10-03 00:00:00", "K2", "gonderildi", gonderim="2026-10-03 00:00:04")


def kimlikler(kayitlar):
    return [k["kayit_id"] for k in kayitlar]


# ---------- Sorgu ----------

def test_en_yeni_ustte(ornekler):
    assert kimlikler(ks.kayitlari_getir()) == ["d", "c", "b", "a"]


def test_tarih_araligi_iki_ucu_da_dahil(ornekler):
    assert kimlikler(ks.kayitlari_getir(baslangic="2026-10-02", bitis="2026-10-02")) == ["c", "b"]
    assert kimlikler(ks.kayitlari_getir(baslangic="2026-10-02")) == ["d", "c", "b"]
    assert kimlikler(ks.kayitlari_getir(bitis="2026-10-01")) == ["a"]


def test_kamera_ve_durum_filtresi(ornekler):
    assert kimlikler(ks.kayitlari_getir(kamera="K1")) == ["c", "a"]
    assert kimlikler(ks.kayitlari_getir(durum="gonderildi")) == ["d", "a"]
    assert kimlikler(ks.kayitlari_getir(kamera="K2", durum="bekliyor")) == ["b"]


def test_en_fazla_500_kayit_ve_en_yeniler():
    for i in range(510):
        kayit_ekle(f"k{i:03d}", f"2026-10-02 10:{i // 60:02d}:{i % 60:02d}")
    kayitlar = ks.kayitlari_getir()
    assert len(kayitlar) == ks.EN_FAZLA == 500
    assert kayitlar[0]["kayit_id"] == "k509" and kayitlar[-1]["kayit_id"] == "k010"


def test_kamera_listesi(ornekler):
    assert ks.kameralari_getir() == ["K1", "K2"]


def test_satir_tarihleri_ekran_biciminde(ornekler):
    k = ks.kayitlari_getir(kamera="K1", durum="gonderildi")[0]
    assert ks.satir_degerleri(k) == ("01.10.2026 09:00:00", "H01", "K1", "Y1", 1,
                                     "Gönderildi", 0, "", "01.10.2026 09:00:05")


# ---------- Görüntü önizleme kararı ----------

def test_goruntu_diskteyse_yolu_doner(tmp_path):
    dosya = tmp_path / "x.avif"
    dosya.write_bytes(b"x")
    assert ks.goruntu_bilgisi({"dosya_yolu": str(dosya), "durum": "gonderildi"}) == (dosya, "")


def test_gonderilmis_ve_silinmis_goruntu():
    yol, aciklama = ks.goruntu_bilgisi({"dosya_yolu": "yok.avif", "durum": "gonderildi"})
    assert yol is None
    assert aciklama == "Görüntü gönderildikten sonra silindi."


def test_bekleyen_ama_dosyasi_olmayan_goruntu():
    yol, aciklama = ks.goruntu_bilgisi({"dosya_yolu": "yok.avif", "durum": "bekliyor"})
    assert yol is None and "bulunamadı" in aciklama


# ---------- Sekme ----------

@pytest.fixture
def sekme(tk_kok, ornekler):
    s = ks.KayitlarSekmesi(tk_kok)
    yield s
    s.destroy()


def test_renkler_durumdan_gelir(sekme):
    assert sekme.liste.item("b", "tags") == ("bekliyor",)
    assert sekme.liste.item("c", "tags") == ("hatali",)
    assert str(sekme.liste.tag_configure("bekliyor", "background")) == "#fff3cd"     # sarı
    assert str(sekme.liste.tag_configure("hatali", "background")) == "#f8d7da"       # kırmızı


def test_yenilemede_secim_ve_filtreler_korunur(sekme):
    sekme.kamera.set("K1")
    sekme.yenile()
    sekme.liste.selection_set("c")
    kayit_ekle("e", "2026-10-04 08:00:00", "K1")       # motor bu arada yeni kayıt ekledi
    kayit_ekle("f", "2026-10-04 08:00:00", "K2")
    sekme.yenile()
    assert sekme.liste.selection() == ("c",)
    assert sekme.kamera.get() == "K1"
    assert list(sekme.liste.get_children()) == ["e", "c", "a"]


def test_kamera_kutusu_tablodaki_kameralarla_dolar(sekme):
    assert list(sekme.kamera_kutusu["values"]) == ["Hepsi", "K1", "K2"]


def test_tarih_filtresi_ekran_biciminden(sekme):
    sekme.baslangic.set("02.10.2026")
    sekme.bitis.set("02.10.2026")
    sekme.yenile()
    assert list(sekme.liste.get_children()) == ["c", "b"]


def test_gecersiz_tarih_uyari_verir_filtre_uygulanmaz(sekme):
    sekme.baslangic.set("2026-10-02")
    sekme.yenile()
    assert "GG.AA.YYYY" in sekme.bilgi.cget("text")
    assert len(sekme.liste.get_children()) == 4


def test_veritabani_okunamazsa_eski_liste_kalir(sekme, monkeypatch):
    def kilitli(**_):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(ks, "kayitlari_getir", kilitli)
    sekme.yenile()
    assert len(sekme.liste.get_children()) == 4
    assert "okunamadı" in sekme.bilgi.cget("text")


def test_cift_tikta_silinmis_goruntu_mesaji(sekme, monkeypatch):
    gosterilen = []
    monkeypatch.setattr(ks.messagebox, "showinfo", lambda baslik, mesaj: gosterilen.append(mesaj))
    sekme.liste.selection_set("a")
    sekme._goruntuyu_ac()
    assert gosterilen == ["Görüntü gönderildikten sonra silindi."]


def test_cift_tikta_diskteki_goruntu_onizlemede_acilir(sekme, monkeypatch, tmp_path):
    from PIL import Image
    dosya = tmp_path / "g.jpg"
    Image.new("RGB", (20, 10), "red").save(dosya)
    kayit_ekle("g", "2026-10-05 08:00:00", dosya_yolu=str(dosya))
    sekme.yenile()
    acilan = []
    monkeypatch.setattr(ks, "onizleme_ac", lambda ust, goruntu, baslik: acilan.append((goruntu.size, baslik)))
    sekme.liste.selection_set("g")
    sekme._goruntuyu_ac()
    assert acilan == [((20, 10), "g")]
