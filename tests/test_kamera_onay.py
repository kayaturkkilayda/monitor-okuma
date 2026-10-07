from datetime import datetime, timedelta

import pytest

import kamera_onay as ko
from kullanicilar import KullaniciHatasi
from onay import onay_ver
from veritabani import baglan

KAMERA = {"kod": "K1", "yatak": "Y1", "tip": "ip", "adres": "http://admin:Gizli1@10.0.0.5/shot.jpg",
          "onay_eposta": "sahip@ornek.com"}
SIMDI = datetime(2026, 10, 5, 9, 0, 0)


def satir(kamera_kodu="K1"):
    with baglan() as db:
        s = db.execute("SELECT * FROM kamera_onay_kodlari WHERE kamera_kodu = ?", (kamera_kodu,)).fetchone()
    return dict(s) if s else None


def yanlis(kod):
    return "000000" if kod != "000000" else "111111"


# ---------- Üretim ve saklama ----------

def test_kod_alti_haneli_ve_hashli_saklanir():
    kod = ko.kod_olustur(KAMERA, "sahip@ornek.com", "ayse@akgun.com.tr", SIMDI)
    assert len(kod) == 6 and kod.isdigit()
    s = satir()
    assert s["kod_hash"].startswith("scrypt$") and kod not in s["kod_hash"]
    assert (s["eposta"], s["gonderen"], s["adres"]) == ("sahip@ornek.com", "ayse@akgun.com.tr", KAMERA["adres"])
    assert s["son_kullanma"] == "2026-10-07 09:00:00"                  # 48 saat
    assert s["gonderim_zamani"] == "2026-10-05 09:00:00" and s["deneme"] == 0


def test_kodlar_rastgele():
    kodlar = {ko.kod_olustur({**KAMERA, "kod": f"K{i}"}, "a@b.co", "x@y.co", SIMDI) for i in range(30)}
    assert len(kodlar) > 25


# ---------- Doğrulama ----------

def test_dogru_kod_onaylayani_dondurur_ve_silinir():
    kod = ko.kod_olustur(KAMERA, "sahip@ornek.com", "ayse@akgun.com.tr", SIMDI)
    assert ko.kodu_dogrula(KAMERA, kod, SIMDI) == "sahip@ornek.com"
    assert satir() is None
    with pytest.raises(KullaniciHatasi, match="geçerli bir onay kodu yok"):
        ko.kodu_dogrula(KAMERA, kod, SIMDI)                              # tek kullanımlık


def test_yanlis_kod_kalan_deneme():
    kod = ko.kod_olustur(KAMERA, "sahip@ornek.com", "ayse@akgun.com.tr", SIMDI)
    with pytest.raises(KullaniciHatasi, match="Kalan deneme: 4"):
        ko.kodu_dogrula(KAMERA, yanlis(kod), SIMDI)
    assert satir()["deneme"] == 1
    assert ko.kodu_dogrula(KAMERA, kod, SIMDI) == "sahip@ornek.com"


def test_bes_yanlis_denemede_kod_gecersiz():
    kod = ko.kod_olustur(KAMERA, "sahip@ornek.com", "ayse@akgun.com.tr", SIMDI)
    for _ in range(ko.EN_FAZLA_DENEME - 1):
        with pytest.raises(KullaniciHatasi, match="Kod hatalı"):
            ko.kodu_dogrula(KAMERA, yanlis(kod), SIMDI)
    with pytest.raises(KullaniciHatasi, match="Çok fazla"):
        ko.kodu_dogrula(KAMERA, yanlis(kod), SIMDI)
    with pytest.raises(KullaniciHatasi):
        ko.kodu_dogrula(KAMERA, kod, SIMDI)


def test_suresi_dolmus_kod():
    kod = ko.kod_olustur(KAMERA, "sahip@ornek.com", "ayse@akgun.com.tr", SIMDI)
    assert ko.kodu_dogrula(KAMERA, kod, SIMDI + timedelta(hours=48)) == "sahip@ornek.com"   # sınırda geçerli
    kod = ko.kod_olustur(KAMERA, "sahip@ornek.com", "ayse@akgun.com.tr", SIMDI)
    with pytest.raises(KullaniciHatasi, match="süresi doldu"):
        ko.kodu_dogrula(KAMERA, kod, SIMDI + timedelta(hours=48, seconds=1))
    assert satir() is None


def test_tekrar_gonderimde_eski_kod_gecersiz():
    eski = ko.kod_olustur(KAMERA, "sahip@ornek.com", "ayse@akgun.com.tr", SIMDI)
    yeni = ko.kod_olustur(KAMERA, "sahip@ornek.com", "ayse@akgun.com.tr", SIMDI)
    if eski != yeni:
        with pytest.raises(KullaniciHatasi, match="Kod hatalı"):
            ko.kodu_dogrula(KAMERA, eski, SIMDI)
    assert ko.kodu_dogrula(KAMERA, yeni, SIMDI) == "sahip@ornek.com"


def test_adres_degisince_eski_kod_gecmez():
    kod = ko.kod_olustur(KAMERA, "sahip@ornek.com", "ayse@akgun.com.tr", SIMDI)
    baska = {**KAMERA, "adres": "http://10.0.0.99/shot.jpg"}
    assert ko.bekleyen_kod(baska, SIMDI) is None
    with pytest.raises(KullaniciHatasi, match="adresi değişti"):
        ko.kodu_dogrula(baska, kod, SIMDI)


def test_bekleyen_kod_bilgisi():
    assert ko.bekleyen_kod(KAMERA, SIMDI) is None
    ko.kod_olustur(KAMERA, "sahip@ornek.com", "ayse@akgun.com.tr", SIMDI)
    assert ko.bekleyen_kod(KAMERA, SIMDI)["eposta"] == "sahip@ornek.com"
    assert ko.bekleyen_kod(KAMERA, SIMDI + timedelta(hours=49)) is None
    ko.kodu_sil("K1")
    assert ko.bekleyen_kod(KAMERA, SIMDI) is None


# ---------- Mail ----------

def test_onay_maili_icerigi():
    konu, metin = ko.onay_maili("H01", KAMERA, "ayse@akgun.com.tr", "123456", SIMDI)
    assert konu == "[H01] K1 → Y1 kamera kullanım onayı"
    for parca in ("K1", "Y1", "http://10.0.0.5/shot.jpg", "ayse@akgun.com.tr", "05.10.2026 09:00:00",
                  "123456", "kurulumu yapan kişiye iletin ya da arayüzde girin",
                  "Onaylamıyorsanız hiçbir şey yapmanız gerekmez; kamera kullanılmayacak."):
        assert parca in metin
    assert "Gizli1" not in metin and "admin:" not in metin               # adresteki şifre gizli


# ---------- Ne zaman mail gider ----------

def test_yeni_kamera_icin_mail_gerekli():
    assert ko.onay_maili_gerekli_mi(None, KAMERA)


def test_onayli_kamera_onayli_kaldiysa_mail_yok():
    onayli = onay_ver(KAMERA, "sahip@ornek.com")
    assert not ko.onay_maili_gerekli_mi(onayli, {**onayli, "yatak": "Y9"})


def test_onay_dustuyse_mail_gerekli():
    from onay import onayi_aktar
    onayli = onay_ver(KAMERA, "sahip@ornek.com")
    yeni = onayi_aktar(onayli, {**KAMERA, "adres": "http://10.0.0.99/shot.jpg"})
    assert ko.onay_maili_gerekli_mi(onayli, yeni)


@pytest.mark.parametrize("alan,deger,gerekli", [
    ("yatak", "Y9", False), ("kullanici", "baska", False),
    ("adres", "http://10.0.0.99/s.jpg", True), ("kod", "K9", True),
    ("tip", "webcam", True),
])
def test_bekleyen_kamerada_hangi_degisiklik_mail_gerektirir(alan, deger, gerekli):
    assert ko.onay_maili_gerekli_mi(KAMERA, {**KAMERA, alan: deger}) is gerekli
