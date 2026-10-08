"""Telefondan fotoğraf gönderme: doğrulama, boru hattı, QR, oturum ve web sunucusu."""
import logging
from datetime import datetime, timedelta
from io import BytesIO

import numpy as np
import pytest
from PIL import Image

import kullanicilar as ku
import qr_kod
import sahiplik
import telefon_oturum
import telefon_sunucusu as ts
import yukleme
from veritabani import baglan

AYARLAR = {"tesis_kodu": "H01", "format": "jpg", "kalite": 85,
           "telefon_yukleme": {"acik": True, "port": 8099}}
AYSE = "ayse@akgun.com.tr"
SIFRE = "GizliSifre1"


class SahteLog:
    def __init__(self):
        self.mesajlar = []

    def info(self, m): self.mesajlar.append(str(m))
    def warning(self, m): self.mesajlar.append(str(m))
    def error(self, m): self.mesajlar.append(str(m))
    def exception(self, m): self.mesajlar.append(str(m))


def resim_baytlari(bicim="JPEG", en=40, boy=30, renk=(20, 120, 200)) -> bytes:
    tampon = BytesIO()
    Image.new("RGB", (en, boy), renk).save(tampon, format=bicim)
    return tampon.getvalue()


def kamera(kod="K1", yatak="Y1", sahip=AYSE) -> dict:
    return {"kod": kod, "yatak": yatak, "tip": "ip", "adres": "http://10.0.0.5/s.jpg",
            "ekleyen": sahip, "onay_zamani": "2026-01-01 00:00:00", "onaylayan": sahip}


def kayitlar() -> list[dict]:
    with baglan() as db:
        return [dict(s) for s in db.execute("SELECT * FROM kayitlar ORDER BY kayit_id")]


# ---------- Boyut ve tür doğrulaması ----------

def test_bos_dosya_reddedilir():
    with pytest.raises(yukleme.YuklemeHatasi, match="boş"):
        yukleme.goruntuyu_coz(b"")


def test_cok_buyuk_dosya_reddedilir():
    kocaman = b"x" * (yukleme.EN_BUYUK_BAYT + 1)
    with pytest.raises(yukleme.YuklemeHatasi, match="çok büyük"):
        yukleme.goruntuyu_coz(kocaman)


@pytest.mark.parametrize("bicim", ["JPEG", "PNG"])
def test_jpeg_ve_png_kabul_edilir(bicim):
    kare = yukleme.goruntuyu_coz(resim_baytlari(bicim))
    assert kare.shape == (30, 40, 3)


def test_resim_olmayan_dosya_reddedilir():
    with pytest.raises(yukleme.YuklemeHatasi, match="okunamadı"):
        yukleme.goruntuyu_coz(b"bu bir resim degil, duz metin" * 10)


def test_izinsiz_bicim_reddedilir():
    """Uzantıya değil, dosyanın gerçek içeriğine bakılır."""
    tampon = BytesIO()
    Image.new("RGB", (10, 10)).save(tampon, format="BMP")
    with pytest.raises(yukleme.YuklemeHatasi, match="JPEG, PNG"):
        yukleme.goruntuyu_coz(tampon.getvalue())


def test_cok_buyuk_fotograf_kuculutulur():
    kare = yukleme.goruntuyu_coz(resim_baytlari(en=6000, boy=4000))
    assert max(kare.shape[:2]) <= yukleme.EN_BUYUK_KENAR


# ---------- Hız sınırı ----------

def test_sinirlayici_pencerede_sinir_koyar():
    s = yukleme.Sinirlayici(pencere_sn=60, en_fazla=2)
    assert s.izin_var_mi("ayse|K1", simdi=0) is True
    assert s.izin_var_mi("ayse|K1", simdi=1) is True
    assert s.izin_var_mi("ayse|K1", simdi=2) is False


def test_sinirlayici_pencere_gecince_serbest():
    s = yukleme.Sinirlayici(pencere_sn=60, en_fazla=1)
    assert s.izin_var_mi("ayse|K1", simdi=0) is True
    assert s.izin_var_mi("ayse|K1", simdi=30) is False
    assert s.izin_var_mi("ayse|K1", simdi=61) is True


def test_sinirlayici_kisileri_ayirir():
    s = yukleme.Sinirlayici(pencere_sn=60, en_fazla=1)
    assert s.izin_var_mi("ayse|K1", simdi=0) is True
    assert s.izin_var_mi("mehmet|K1", simdi=0) is True        # başkasını etkilemez


# ---------- Boru hattı: kamera görüntüsüyle aynı yol ----------

def test_fotograf_kuyruga_kamera_gibi_girer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log = SahteLog()
    kayit_id = yukleme.fotografi_al(resim_baytlari(), AYARLAR, kamera(), AYSE, log,
                                    zaman=datetime(2026, 10, 8, 9, 30, 0))
    (kayit,) = kayitlar()
    assert kayit["kayit_id"] == kayit_id == "H01_K1_Y1_2026-10-08_09-30-00_1"
    assert kayit["durum"] == "bekliyor"            # M4 kuyruğuna normal kayıt gibi girdi
    assert kayit["tesis_kodu"] == "H01" and kayit["kamera_kodu"] == "K1"
    assert kayit["sira"] == 1


def test_kaynak_telefon_ve_yukleyen_kaydedilir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yukleme.fotografi_al(resim_baytlari(), AYARLAR, kamera(), AYSE, SahteLog())
    (kayit,) = kayitlar()
    assert kayit["kaynak"] == "telefon"
    assert kayit["yukleyen"] == AYSE


def test_fotograf_diske_yazilir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yukleme.fotografi_al(resim_baytlari(), AYARLAR, kamera(), AYSE, SahteLog())
    (kayit,) = kayitlar()
    dosya = tmp_path / kayit["dosya_yolu"]
    assert dosya.exists() and dosya.stat().st_size > 0
    assert kayit["dosya_boyutu"] == dosya.stat().st_size


def test_ayni_anda_iki_fotograf_birbirini_ezmez(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    an = datetime(2026, 10, 8, 9, 30, 0)
    for _ in range(2):
        yukleme.fotografi_al(resim_baytlari(), AYARLAR, kamera(), AYSE, SahteLog(), zaman=an)
    kimlikler = [k["kayit_id"] for k in kayitlar()]
    assert len(set(kimlikler)) == 2                 # ikincisine _2 eklendi


def test_log_mesajinda_sifre_yok(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log = SahteLog()
    yukleme.fotografi_al(resim_baytlari(), AYARLAR, kamera(), AYSE, log)
    birlesik = " ".join(log.mesajlar)
    assert "telefondan fotoğraf alındı" in birlesik
    assert SIFRE not in birlesik


# ---------- QR ----------

def test_yatak_adresi_bicimi():
    assert qr_kod.yatak_adresi("192.168.1.10", "K1", 8099) == "http://192.168.1.10:8099/yatak/K1"


def test_qr_adresi_tasir():
    qr = qr_kod.qr_uret("http://192.168.1.10:8099/yatak/K1")
    assert qr is not None and qr.error == "M"


def test_qr_png_olarak_kaydedilir(tmp_path):
    yol = qr_kod.png_kaydet("http://192.168.1.10:8099/yatak/K1", tmp_path / "qr.png", kamera())
    assert yol.exists()
    with Image.open(yol) as resim:
        assert resim.format == "PNG" and resim.height > resim.width   # altında yazı var


def test_qr_yazisiz_da_kaydedilir(tmp_path):
    yol = qr_kod.png_kaydet("http://x/y", tmp_path / "sade.png")
    with Image.open(yol) as resim:
        assert resim.format == "PNG" and resim.height == resim.width


# ---------- Telefon oturumu ----------

def _ayse_olustur(yonetici=False) -> dict:
    ku.ilk_yoneticiyi_olustur("bt@akgun.com.tr", "BT", SIFRE, SIFRE)
    _, kod = ku.kayit_baslat(AYSE, "Ayşe", SIFRE, SIFRE, None)
    ku.kayit_dogrula(AYSE, kod)
    if yonetici:
        ku.yonetici_yap(AYSE)
    return ku.giris(AYSE, SIFRE)


def test_oturum_acilir_ve_cozulur():
    k = _ayse_olustur()
    anahtar = telefon_oturum.oturum_ac(k["id"])
    assert telefon_oturum.kullanici(anahtar)["eposta"] == AYSE


def test_yanlis_anahtar_cozulmez():
    _ayse_olustur()
    assert telefon_oturum.kullanici("uydurma-anahtar") is None
    assert telefon_oturum.kullanici(None) is None


def test_suresi_gecen_oturum_gecersiz():
    k = _ayse_olustur()
    anahtar = telefon_oturum.oturum_ac(k["id"])
    sonra = datetime.now() + timedelta(hours=telefon_oturum.GECERLILIK_SAAT + 1)
    assert telefon_oturum.kullanici(anahtar, simdi=sonra) is None


def test_oturum_kapatilir():
    k = _ayse_olustur()
    anahtar = telefon_oturum.oturum_ac(k["id"])
    telefon_oturum.oturum_kapat(anahtar)
    assert telefon_oturum.kullanici(anahtar) is None


def test_anahtarin_kendisi_veritabaninda_durmaz():
    k = _ayse_olustur()
    anahtar = telefon_oturum.oturum_ac(k["id"])
    with baglan() as db:
        saklanan = [s["token_hash"] for s in db.execute("SELECT token_hash FROM oturumlar")]
    assert anahtar not in saklanan                  # yalnızca hash'i saklanır


# ---------- Web sunucusu ----------

@pytest.fixture
def istemci(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log = SahteLog()
    kameralar = [kamera("K1", "Y1", AYSE), kamera("K2", "Y2", "baska@akgun.com.tr")]
    ayarlar = {**AYARLAR, "kameralar": kameralar}
    uygulama = ts.uygulama_olustur(lambda: ayarlar, log)
    uygulama.config["TESTING"] = True
    return uygulama.test_client(), log


def giris_yap(istemci, eposta=AYSE, sifre=SIFRE, kod="K1"):
    return istemci.post(f"/yatak/{kod}/giris", data={"eposta": eposta, "sifre": sifre})


def test_girissiz_giris_sayfasi_gelir(istemci):
    c, _ = istemci
    _ayse_olustur()
    yanit = c.get("/yatak/K1")
    metin = yanit.get_data(as_text=True)
    assert yanit.status_code == 200
    assert "Giriş yap" in metin and "Y1" in metin


def test_bilinmeyen_yatak_404(istemci):
    c, _ = istemci
    assert c.get("/yatak/YOK").status_code == 404


def test_yanlis_sifreyle_giris_olmaz(istemci):
    c, _ = istemci
    _ayse_olustur()
    yanit = giris_yap(c, sifre="Yanlis1234")
    assert yanit.status_code == 401
    assert "hatalı" in yanit.get_data(as_text=True).lower()


def test_dogru_sifreyle_giris_ve_cerez(istemci):
    c, _ = istemci
    _ayse_olustur()
    yanit = giris_yap(c)
    assert yanit.status_code == 302
    cerez = yanit.headers.get("Set-Cookie", "")
    assert telefon_oturum.CEREZ_ADI in cerez and "HttpOnly" in cerez


def test_giristen_sonra_yukleme_sayfasi(istemci):
    c, _ = istemci
    _ayse_olustur()
    giris_yap(c)
    metin = c.get("/yatak/K1").get_data(as_text=True)
    assert "Fotoğraf çek" in metin
    assert 'capture="environment"' in metin and 'accept="image/*"' in metin


def test_baskasinin_yataginda_yetki_yok(istemci):
    c, _ = istemci
    _ayse_olustur()
    yanit = giris_yap(c, kod="K2")                  # K2 başkasının
    assert yanit.status_code == 403


def test_yonetici_her_yataga_yukleyebilir(istemci):
    c, _ = istemci
    _ayse_olustur(yonetici=True)
    assert giris_yap(c, kod="K2").status_code == 302


def test_fotograf_gonderilir_ve_kuyruga_girer(istemci):
    c, _ = istemci
    _ayse_olustur()
    giris_yap(c)
    yanit = c.post("/yatak/K1/yukle",
                   data={"fotograf": (BytesIO(resim_baytlari()), "foto.jpg")},
                   content_type="multipart/form-data")
    assert yanit.status_code == 200
    assert "Gönderildi" in yanit.get_data(as_text=True)
    (kayit,) = kayitlar()
    assert kayit["kaynak"] == "telefon" and kayit["yukleyen"] == AYSE


def test_resim_olmayan_dosya_reddedilir_sunucuda(istemci):
    c, _ = istemci
    _ayse_olustur()
    giris_yap(c)
    yanit = c.post("/yatak/K1/yukle",
                   data={"fotograf": (BytesIO(b"duz metin"), "kotu.jpg")},
                   content_type="multipart/form-data")
    assert yanit.status_code == 400
    assert "okunamadı" in yanit.get_data(as_text=True)
    assert kayitlar() == []


def test_girissiz_yukleme_yapilamaz(istemci):
    c, _ = istemci
    _ayse_olustur()
    yanit = c.post("/yatak/K1/yukle",
                   data={"fotograf": (BytesIO(resim_baytlari()), "foto.jpg")},
                   content_type="multipart/form-data")
    assert "Giriş yap" in yanit.get_data(as_text=True)
    assert kayitlar() == []


def test_cok_sik_gonderim_engellenir(istemci):
    c, _ = istemci
    _ayse_olustur()
    giris_yap(c)
    sonuclar = []
    for _ in range(yukleme.PENCEREDE_EN_FAZLA + 1):
        sonuclar.append(c.post("/yatak/K1/yukle",
                               data={"fotograf": (BytesIO(resim_baytlari()), "f.jpg")},
                               content_type="multipart/form-data").status_code)
    assert sonuclar[-1] == 429
    assert "Çok sık" in c.post("/yatak/K1/yukle",
                               data={"fotograf": (BytesIO(resim_baytlari()), "f.jpg")},
                               content_type="multipart/form-data").get_data(as_text=True)


def test_cok_buyuk_istek_reddedilir(istemci):
    c, _ = istemci
    _ayse_olustur()
    giris_yap(c)
    kocaman = b"x" * (yukleme.EN_BUYUK_BAYT + 1000)
    yanit = c.post("/yatak/K1/yukle",
                   data={"fotograf": (BytesIO(kocaman), "buyuk.jpg")},
                   content_type="multipart/form-data")
    assert yanit.status_code == 413


def test_sifre_loglanmaz(istemci):
    c, log = istemci
    _ayse_olustur()
    giris_yap(c)
    assert all(SIFRE not in m for m in log.mesajlar)


# ---------- Ayar ----------

def test_varsayilan_kapali():
    assert ts.sunucu_ayari({}) == {"acik": False, "port": ts.VARSAYILAN_PORT}
    assert ts.sunucu_ayari({"telefon_yukleme": {}})["acik"] is False


def test_ayar_okunur():
    assert ts.sunucu_ayari({"telefon_yukleme": {"acik": True, "port": 9100}}) == \
        {"acik": True, "port": 9100}


def test_kapaliyken_sunucu_baslatilmaz():
    import threading
    assert ts.sunucuyu_baslat(lambda: {"telefon_yukleme": {"acik": False}},
                              SahteLog(), threading.Event()) is None
