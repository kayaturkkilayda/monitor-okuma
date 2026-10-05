"""Kayıtlar sekmesinin "Günlere göre" ağaç görünümü."""
import time

import pytest

import kayitlar_sekmesi as ks
from veritabani import baglan


def kayit(kayit_id, cekim, kamera="K1", yatak="Y1", durum="gonderildi", dosya="yok.avif"):
    return (kayit_id, "c", "H01", kamera, yatak, cekim, "+03:00", 1, dosya, durum, cekim)


def ekle(*kayitlar):
    with baglan() as db:
        db.executemany(
            "INSERT INTO kayitlar (kayit_id, cift_id, tesis_kodu, kamera_kodu, yatak_kodu, cekim_zamani,"
            " saat_dilimi, sira, dosya_yolu, durum, sonraki_deneme) VALUES (?,?,?,?,?,?,?,?,?,?,?)", kayitlar)


@pytest.fixture
def ornekler():
    ekle(kayit("a1", "2026-10-01 09:00:00"),
         kayit("a2", "2026-10-01 10:00:00", "K2", "Y2", "hatali"),
         kayit("b1", "2026-10-02 08:00:00"),
         kayit("b2", "2026-10-02 08:00:20"),
         kayit("b3", "2026-10-02 08:00:40", durum="bekliyor"),
         kayit("b4", "2026-10-02 23:59:59", "K2", "Y2"))


# ---------- SQL özetleri ----------

def test_gun_ozetleri_en_yeni_ustte_ve_sayimlar(ornekler):
    o = ks.gun_ozetleri()
    assert [x["gun"] for x in o] == ["2026-10-02", "2026-10-01"]
    assert {k: o[0][k] for k in ("toplam", "gonderildi", "bekliyor", "hatali")} == \
        {"toplam": 4, "gonderildi": 3, "bekliyor": 1, "hatali": 0}
    assert o[1]["hatali"] == 1


def test_gun_ozetlerinde_filtreler(ornekler):
    assert [x["gun"] for x in ks.gun_ozetleri(durum="hatali")] == ["2026-10-01"]
    assert [x["toplam"] for x in ks.gun_ozetleri(kamera="K2")] == [1, 1]
    assert [x["gun"] for x in ks.gun_ozetleri(baslangic="2026-10-02")] == ["2026-10-02"]
    assert [x["gun"] for x in ks.gun_ozetleri(bitis="2026-10-01")] == ["2026-10-01"]


def test_kamera_ozetleri_ve_gun_kayitlari(ornekler):
    o = ks.kamera_ozetleri("2026-10-02")
    assert [(x["kamera_kodu"], x["yatak_kodu"], x["toplam"]) for x in o] == [("K1", "Y1", 3), ("K2", "Y2", 1)]
    assert [k["kayit_id"] for k in ks.gun_kayitlari("2026-10-02", "K1", "Y1")] == ["b3", "b2", "b1"]
    assert [k["kayit_id"] for k in ks.gun_kayitlari("2026-10-02", "K1", "Y1", durum="bekliyor")] == ["b3"]


# ---------- Metinler ----------

def test_gun_ve_kamera_metinleri():
    gun = {"gun": "2026-10-02", "toplam": 2880, "gonderildi": 2875, "bekliyor": 5, "hatali": 0}
    assert ks.gun_metni(gun) == "02.10.2026 — 2.880 kayıt, 2.875 gönderildi, 5 bekliyor"
    kamera = {"kamera_kodu": "K1", "yatak_kodu": "Y1", "toplam": 288, "gonderildi": 288,
              "bekliyor": 0, "hatali": 0}
    assert ks.kamera_metni(kamera) == "K1 → Y1 — 288 kayıt"
    assert ks.kamera_metni({**kamera, "hatali": 2}) == "K1 → Y1 — 288 kayıt, 2 hatalı"


# ---------- Klasör ----------

def test_klasor_bilgisi(tmp_path, monkeypatch):
    monkeypatch.setattr(ks, "GORUNTU_KLASORU", tmp_path / "goruntuler")
    yol, aciklama = ks.klasor_bilgisi("2026-10-02")
    assert yol is None and "günün görüntü klasörü yok" in aciklama
    yatak = tmp_path / "goruntuler" / "2026-10-02" / "Y1"
    yatak.mkdir(parents=True)
    yol, aciklama = ks.klasor_bilgisi("2026-10-02", "Y1")
    assert yol is None and "hiç görüntü kalmamış" in aciklama            # klasör var ama boş
    (yatak / "x.avif").write_bytes(b"x")
    assert ks.klasor_bilgisi("2026-10-02", "Y1") == (yatak, "")
    assert ks.klasor_bilgisi("2026-10-02")[0] == tmp_path / "goruntuler" / "2026-10-02"


# ---------- Ağaç ----------

@pytest.fixture
def sekme(tk_kok, ornekler):
    s = ks.KayitlarSekmesi(tk_kok)
    yield s
    s.destroy()


def ac(sekme, iid):
    sekme.agac.item(iid, open=True)
    sekme._dugum_acildi(iid)


G2, G1 = ks.gun_kimligi("2026-10-02"), ks.gun_kimligi("2026-10-01")
K1 = ks.kamera_kimligi("2026-10-02", "K1", "Y1")


def test_varsayilan_agac_en_yeni_gun_ustte(sekme):
    assert sekme.gorunum.get() == ks.GUNLERE_GORE
    assert sekme.agac.get_children() == (G2, G1)
    assert sekme.agac.item(G2, "text") == "02.10.2026 — 4 kayıt, 3 gönderildi, 1 bekliyor"
    assert sekme.bilgi.cget("text") == "2 gün, 6 kayıt"


def test_gun_acilmadan_kayit_yuklenmez(sekme, monkeypatch):
    (cocuk,) = sekme.agac.get_children(G2)
    assert cocuk.startswith(ks.YER_TUTUCU)                               # yalnızca yer tutucu
    yuklenen = []
    monkeypatch.setattr(ks, "gun_kayitlari", lambda *a, **k: yuklenen.append(a) or [])
    sekme.yenile()
    assert yuklenen == []


def test_acinca_kameralar_sonra_kayitlar(sekme):
    ac(sekme, G2)
    assert sekme.agac.get_children(G2) == (K1, ks.kamera_kimligi("2026-10-02", "K2", "Y2"))
    assert sekme.agac.item(K1, "text") == "K1 → Y1 — 3 kayıt, 1 bekliyor"
    ac(sekme, K1)
    kayitlar = sekme.agac.get_children(K1)
    assert kayitlar == tuple(ks.kayit_kimligi(i) for i in ("b3", "b2", "b1"))
    assert sekme.agac.item(kayitlar[0], "tags") == ("bekliyor",)
    assert sekme.agac.item(kayitlar[0], "values")[0] == "02.10.2026 08:00:40"


def test_yenilemede_acik_dugumler_ve_secim_korunur(sekme):
    ac(sekme, G2)
    ac(sekme, K1)
    secili = ks.kayit_kimligi("b2")
    sekme.agac.selection_set(secili)
    ekle(kayit("b5", "2026-10-02 08:01:00"))                            # motor yeni kayıt ekledi
    sekme.yenile()
    assert sekme.agac.item(G2, "open") and sekme.agac.item(K1, "open")
    assert sekme.agac.selection() == (secili,)
    assert sekme.agac.get_children(K1)[0] == ks.kayit_kimligi("b5")
    assert sekme.agac.item(G2, "text").startswith("02.10.2026 — 5 kayıt")


def test_degismeyen_kamera_yeniden_yuklenmez(sekme, monkeypatch):
    ac(sekme, G2)
    ac(sekme, K1)
    yuklenen = []
    gercek = ks.gun_kayitlari
    monkeypatch.setattr(ks, "gun_kayitlari", lambda *a, **k: yuklenen.append(a) or gercek(*a, **k))
    sekme.yenile()
    assert yuklenen == []                                                # sayılar aynı → dokunulmadı
    with baglan() as db:
        db.execute("UPDATE kayitlar SET durum = 'gonderildi' WHERE kayit_id = 'b3'")
    sekme.yenile()
    assert len(yuklenen) == 1                                            # durum değişti → yenilendi
    assert sekme.agac.item(ks.kayit_kimligi("b3"), "tags") == ("gonderildi",)


def test_yeni_gun_en_uste_eklenir(sekme):
    ekle(kayit("c1", "2026-10-03 00:00:01"))
    sekme.yenile()
    assert sekme.agac.get_children()[0] == ks.gun_kimligi("2026-10-03")


def test_filtreler_agacta_calisir(sekme):
    ac(sekme, G2)
    sekme.durum.set("Bekliyor")
    sekme.yenile()
    assert sekme.agac.get_children() == (G2,)
    assert sekme.agac.get_children(G2) == (K1,)                         # açık gün filtreye göre güncellendi
    sekme.durum.set(ks.HEPSI)
    sekme.kamera.set("K2")
    sekme.yenile()
    assert sekme.agac.get_children() == (G2, G1)
    assert [sekme.agac.item(i, "text").split(" — ")[1] for i in sekme.agac.get_children()] == \
        ["1 kayıt, 1 gönderildi", "1 kayıt, 1 hatalı"]


def test_liste_gorunumune_gecis(sekme):
    sekme.gorunum.set(ks.LISTE)
    sekme._gorunumu_degistir()
    assert sekme.liste.get_children()[0] == "b4" and sekme.bilgi.cget("text") == "6 kayıt"
    assert not sekme.agac_cercevesi.winfo_manager() and sekme.liste_cercevesi.winfo_manager()


def test_klasoru_ac_dugmesi(sekme, monkeypatch, tmp_path):
    monkeypatch.setattr(ks, "GORUNTU_KLASORU", tmp_path / "goruntuler")
    acilan, mesajlar = [], []
    monkeypatch.setattr(ks.os, "startfile", acilan.append, raising=False)
    monkeypatch.setattr(ks.messagebox, "showinfo", lambda b, m, **k: mesajlar.append(m))
    assert str(sekme.klasor_dugmesi.cget("state")) == "disabled"        # seçim yok

    sekme.agac.selection_set(G2)
    sekme.update()
    assert str(sekme.klasor_dugmesi.cget("state")) == "normal"
    sekme._klasoru_ac()
    assert acilan == [] and "görüntü klasörü yok" in mesajlar[-1]       # gönderilip silinmiş

    (tmp_path / "goruntuler" / "2026-10-02" / "Y1").mkdir(parents=True)
    (tmp_path / "goruntuler" / "2026-10-02" / "Y1" / "b3.avif").write_bytes(b"x")
    ac(sekme, G2)
    sekme.agac.selection_set(K1)
    sekme.update()
    sekme._klasoru_ac()
    assert acilan == [(tmp_path / "goruntuler" / "2026-10-02" / "Y1").resolve()]

    ac(sekme, K1)
    sekme.agac.selection_set(ks.kayit_kimligi("b3"))
    sekme.update()
    assert str(sekme.klasor_dugmesi.cget("state")) == "disabled"        # kayıt seçiliyken kapalı


def test_agacta_kayda_cift_tiklama_onizleme(sekme, monkeypatch, tmp_path):
    from PIL import Image
    dosya = tmp_path / "g.jpg"
    Image.new("RGB", (20, 10), "red").save(dosya)
    ekle(kayit("g1", "2026-10-02 09:00:00", dosya=str(dosya)))
    sekme.yenile()
    ac(sekme, G2)
    ac(sekme, K1)
    acilan = []
    monkeypatch.setattr(ks, "onizleme_ac", lambda ust, g, baslik: acilan.append((g.size, baslik)))
    sekme.agac.selection_set(ks.kayit_kimligi("g1"))
    sekme._goruntuyu_ac(sekme.agac)
    assert acilan == [((20, 10), "g1")]
    sekme.agac.selection_set(G2)                                         # gün düğümünde önizleme yok
    sekme._goruntuyu_ac(sekme.agac)
    assert len(acilan) == 1


def test_binlerce_kayitta_hizli(tk_kok):
    """30 gün × 4 kamera × 250 kayıt = 30.000 kayıt: özetler SQL'de, kayıtlar yalnızca açılınca."""
    ekle(*(kayit(f"x{g}-{k}-{i}", f"2026-09-{g:02d} {i // 60 % 24:02d}:{i % 60:02d}:00", f"K{k}", f"Y{k}")
           for g in range(1, 31) for k in range(1, 5) for i in range(250)))
    once = time.perf_counter()
    s = ks.KayitlarSekmesi(tk_kok)
    try:
        acilis = time.perf_counter() - once
        assert len(s.agac.get_children()) == 30
        assert all(len(s.agac.get_children(g)) == 1 for g in s.agac.get_children())   # yalnızca yer tutucular
        once = time.perf_counter()
        s.yenile()
        yenileme = time.perf_counter() - once
        assert acilis < 2 and yenileme < 2, (acilis, yenileme)
    finally:
        s.destroy()


def test_esitle_sira_bozulursa_duzeltir_degismeyene_dokunmaz(sekme, monkeypatch):
    satirlar = [(f"t{i}", f"satır {i}", (), (), False) for i in range(3)]
    sekme._esitle("", satirlar)
    guncellenen = []
    gercek = sekme.agac.item
    monkeypatch.setattr(sekme.agac, "item", lambda iid, *a, **k: (k and guncellenen.append(iid)) or gercek(iid, *a, **k))
    sekme._esitle("", satirlar)
    assert guncellenen == []                                             # hiçbir şey değişmedi
    sekme._esitle("", list(reversed(satirlar)))
    assert sekme.agac.get_children() == ("t2", "t1", "t0")
