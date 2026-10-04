from datetime import date, datetime, timedelta

import pytest

import temizlik as t
from gonderici import kuyruga_ekle
from veritabani import baglan
from zaman import db_zamani


class SahteLog:
    def __init__(self):
        self.mesajlar = []

    def info(self, m): self.mesajlar.append(m)


@pytest.fixture
def ortam(tmp_path):
    """Geçici klasörde goruntuler/ yapısı kurar (veritabanı conftest'te geçici)."""
    return tmp_path / "goruntuler", SahteLog()


def goruntu_olustur(kok, gun_once: int, ad: str = "K1_10-00-00.avif"):
    gun = (date.today() - timedelta(days=gun_once)).isoformat()
    dosya = kok / gun / "Y1" / ad
    dosya.parent.mkdir(parents=True, exist_ok=True)
    dosya.write_bytes(b"x")
    return dosya


def kayit_yaz(dosya, durum="bekliyor", gonderim_zamani=None):
    """Görüntü için verilen durumda bir kayıt ekler."""
    kayit_id = kuyruga_ekle(dosya, "H01", "K1", "Y1", datetime.now(), 1, "c", dosya.stem)
    with baglan() as db:
        db.execute("UPDATE kayitlar SET durum = ?, gonderim_zamani = ? WHERE kayit_id = ?",
                   (durum, gonderim_zamani, kayit_id))
    return kayit_id


def gun_once(gun: int) -> str:
    return db_zamani(datetime.now() - timedelta(days=gun))


def kayit_idleri():
    with baglan() as db:
        return {s[0] for s in db.execute("SELECT kayit_id FROM kayitlar")}


# ---------- Görüntü temizliği ----------

def test_eski_sahipsiz_dosya_silinir(ortam):
    kok, log = ortam
    dosya = goruntu_olustur(kok, gun_once=10)
    t.temizle(7, log, klasor=str(kok))
    assert not dosya.exists()
    assert not dosya.parent.parent.exists()      # boşalan tarih klasörü de kalkar


def test_yeni_dosyaya_dokunulmaz(ortam):
    kok, log = ortam
    dosya = goruntu_olustur(kok, gun_once=2)
    t.temizle(7, log, klasor=str(kok))
    assert dosya.exists()


def test_kuyrukta_bekleyen_eski_dosya_korunur(ortam):
    kok, log = ortam
    dosya = goruntu_olustur(kok, gun_once=30)
    kayit_yaz(dosya, "bekliyor")
    t.temizle(7, log, klasor=str(kok))
    assert dosya.exists()


def test_hatali_kayittaki_eski_dosya_korunur(ortam):
    kok, log = ortam
    dosya = goruntu_olustur(kok, gun_once=30)
    kayit_yaz(dosya, "hatali")
    t.temizle(7, log, klasor=str(kok))
    assert dosya.exists()


def test_gonderilmis_kaydin_eski_dosyasi_silinir(ortam):
    kok, log = ortam
    dosya = goruntu_olustur(kok, gun_once=30)
    kayit_yaz(dosya, "gonderildi", gun_once(30))
    t.temizle(7, log, klasor=str(kok))
    assert not dosya.exists()


def test_korunan_ve_sahipsiz_ayni_klasorde(ortam):
    kok, log = ortam
    korunan = goruntu_olustur(kok, gun_once=30, ad="K1_10-00-00.avif")
    sahipsiz = goruntu_olustur(kok, gun_once=30, ad="K1_10-00-05.avif")
    kayit_yaz(korunan, "bekliyor")
    t.temizle(7, log, klasor=str(kok))
    assert korunan.exists()
    assert not sahipsiz.exists()


def test_tarih_adli_olmayan_klasore_dokunulmaz(ortam):
    kok, log = ortam
    yabanci = kok / "notlar" / "onemli.txt"
    yabanci.parent.mkdir(parents=True)
    yabanci.write_text("dokunma")
    t.temizle(7, log, klasor=str(kok))
    assert yabanci.exists()


def test_veritabani_okunamazsa_hicbir_sey_silinmez(ortam, monkeypatch):
    """Hangi görüntülerin beklediği bilinemiyorsa güvenli taraf: silme."""
    kok, log = ortam
    dosya = goruntu_olustur(kok, gun_once=30)

    def bozuk():
        raise RuntimeError("veritabanı okunamadı")
    monkeypatch.setattr(t, "_korunan_dosyalar", bozuk)
    with pytest.raises(RuntimeError):
        t.temizle(7, log, klasor=str(kok))
    assert dosya.exists()


# ---------- Kayıt geçmişi temizliği ----------

def test_eski_gonderilmis_kayit_tablodan_silinir(ortam):
    kok, log = ortam
    eski = kayit_yaz(goruntu_olustur(kok, 0, "a.avif"), "gonderildi", gun_once(100))
    yeni = kayit_yaz(goruntu_olustur(kok, 0, "b.avif"), "gonderildi", gun_once(10))
    assert t.eski_kayitlari_sil(90, log) == 1
    assert kayit_idleri() == {yeni}
    assert eski not in kayit_idleri()


def test_bekleyen_ve_hatali_kayit_ne_kadar_eski_olsa_da_silinmez(ortam):
    kok, log = ortam
    bekleyen = kayit_yaz(goruntu_olustur(kok, 0, "a.avif"), "bekliyor")
    hatali = kayit_yaz(goruntu_olustur(kok, 0, "b.avif"), "hatali", gun_once(500))
    t.eski_kayitlari_sil(1, log)
    assert kayit_idleri() == {bekleyen, hatali}


def test_kayit_saklama_suresi_ayardan_gelir(ortam):
    kok, log = ortam
    kayit_yaz(goruntu_olustur(kok, 0), "gonderildi", gun_once(10))
    assert t.eski_kayitlari_sil(30, log) == 0
    assert t.eski_kayitlari_sil(5, log) == 1


def test_temizlik_dongusu_varsayilan_90_gun(ortam, monkeypatch):
    kok, log = ortam
    monkeypatch.setattr(t, "temizle", lambda *a, **k: None)
    kalacak = kayit_yaz(goruntu_olustur(kok, 0, "a.avif"), "gonderildi", gun_once(80))
    kayit_yaz(goruntu_olustur(kok, 0, "b.avif"), "gonderildi", gun_once(95))

    class TekTur:
        def is_set(self): return getattr(self, "bitti", False)
        def wait(self, sn): self.bitti = True

    t.temizlik_dongusu({}, log, TekTur())            # ayar dosyasında kayit_saklama_gun yok
    assert kayit_idleri() == {kalacak}
