"""Ayarlar sekmesindeki SMTP bölümü ve kamera formundaki bildirim e-postası alanı."""
from types import SimpleNamespace

import pytest

import arka_plan

import eposta_bolumu as eb
from ayar_sekmesi import AyarSekmesi

SMTP = {"sunucu": "smtp.ornek.com", "port": "587", "guvenlik": "STARTTLS", "kullanici": "bildirim@ornek.com",
        "sifre": "SmtpSifresi123", "gonderen": "monitor@ornek.com", "varsayilan_alici": "bt@ornek.com"}
TEMEL = {"tesis_kodu": "H01", "api_url": "", "api_key": "", "gonderim_araligi_sn": 60,
         "ikinci_cekim_gecikme_sn": 5, "format": "avif", "kalite": 85, "saklama_gun": 7,
         "gonderilince_sil": True, "kameralar": []}


# ---------- Doğrulama ----------

def test_gecerli_ayar():
    smtp, hata = eb.smtp_dogrula(SMTP)
    assert hata is None and smtp["port"] == 587


def test_sunucu_bossa_eposta_kapali_ama_hata_yok():
    smtp, hata = eb.smtp_dogrula({})
    assert hata is None and smtp["sunucu"] == "" and smtp["guvenlik"] == "STARTTLS"


@pytest.mark.parametrize("guvenlik,port", [("STARTTLS", 587), ("SSL", 465), ("Yok", 25)])
def test_bos_port_guvenlige_gore(guvenlik, port):
    assert eb.smtp_dogrula({**SMTP, "guvenlik": guvenlik, "port": ""})[0]["port"] == port


@pytest.mark.parametrize("alan,deger,mesaj", [
    ("port", "abc", "tam sayı"), ("port", "70000", "65535"),
    ("kullanici", "", "kullanıcı adı"),
    ("kullanici", "yanlis", "geçerli e-posta"),
    ("kullanici", "a@x.com, b@y.com", "geçerli e-posta"),
])
def test_hatali_ayar(alan, deger, mesaj):
    smtp, hata = eb.smtp_dogrula({**SMTP, alan: deger})
    assert smtp is None and mesaj in hata


# ---------- Ayarlar sekmesi ----------

@pytest.fixture
def sekme(tk_kok):
    # SMTP ayarları yalnızca yöneticide görünür; sekme hep yönetici oturumuyla açılır
    s = AyarSekmesi(tk_kok, {**TEMEL, "smtp": dict(SMTP)},
                    {"eposta": "admin@akgun.com.tr", "ad": "Yönetici", "yonetici": True})
    yield s
    s.destroy()


def test_sifre_alani_gizli(sekme):
    alanlar = [c for c in sekme.eposta.winfo_children() if c.winfo_class() == "TEntry"]
    sifre = next(a for a in alanlar if str(a.cget("textvariable")) == str(sekme.eposta.degerler["sifre"]))
    assert sifre.cget("show") == "*"


def test_kaydedilen_ayarlarda_smtp_var(sekme):
    yeni, hata = sekme._dogrula()
    assert hata is None
    assert yeni["smtp"]["sunucu"] == "smtp.ornek.com" and yeni["smtp"]["sifre"] == "SmtpSifresi123"


def test_hatali_smtp_kaydi_engeller(sekme):
    sekme.eposta.degerler["kullanici"].set("yanlis")
    yeni, hata = sekme._dogrula()
    assert yeni is None and "kullanıcı adı" in hata


class HemenCalisan:
    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


@pytest.mark.parametrize("sonuc,renk", [((True, "Test maili gönderildi: bt@ornek.com"), eb.YESIL),
                                         ((False, "SMTPAuthenticationError: (535, ...)"), eb.KIRMIZI)])
def test_test_maili_sonucu_gosterilir(sekme, monkeypatch, sonuc, renk):
    giden = []
    monkeypatch.setattr(eb, "test_maili_gonder", lambda smtp: giden.append(smtp) or sonuc)
    monkeypatch.setattr(arka_plan.threading, "Thread", HemenCalisan)
    sekme.eposta._test()
    sekme.update()
    assert giden[0]["sunucu"] == "smtp.ornek.com"            # formdaki değerlerle denendi
    assert sonuc[1] in sekme.eposta.sonuc.cget("text")
    assert str(sekme.eposta.sonuc.cget("foreground")) == renk
    assert str(sekme.eposta.test_dugmesi.cget("state")) == "normal"


def test_test_maili_hatali_formda_gonderilmez(sekme, monkeypatch):
    monkeypatch.setattr(eb, "test_maili_gonder", lambda smtp: pytest.fail("gönderilmemeliydi"))
    sekme.eposta.degerler["port"].set("abc")
    sekme.eposta._test()
    assert "tam sayı" in sekme.eposta.sonuc.cget("text")


# ---------- Gönderen ve bildirim adresi ----------

def test_formda_gonderen_ve_varsayilan_alici_alani_yok():
    """İkisi de kullanıcıya sorulmaz: biri kullanıcı adından, biri oturumdan gelir."""
    alan_adlari = [ad for ad, _, _ in eb.ALANLAR]
    assert "gonderen" not in alan_adlari
    assert "varsayilan_alici" not in alan_adlari
    assert alan_adlari == ["sunucu", "port", "guvenlik", "kullanici", "sifre"]


def test_varsayilan_alici_kaydeden_yoneticinin_epostasi(sekme):
    yeni, hata = sekme._dogrula()
    assert hata is None
    assert yeni["smtp"]["varsayilan_alici"] == "admin@akgun.com.tr"


def test_eski_ayar_dosyasindaki_alanlar_korunur():
    """Geriye uyumluluk: eski "gonderen" değeri silinmez."""
    smtp, hata = eb.smtp_dogrula(SMTP, "admin@akgun.com.tr")
    assert hata is None
    assert smtp["gonderen"] == "monitor@ornek.com"


def test_oturum_yoksa_eski_varsayilan_alici_kalir():
    smtp, hata = eb.smtp_dogrula(SMTP, "")
    assert hata is None and smtp["varsayilan_alici"] == "bt@ornek.com"


def test_sunucu_bossa_kullanici_adi_zorunlu_degil():
    smtp, hata = eb.smtp_dogrula({"sunucu": "", "kullanici": ""}, "admin@akgun.com.tr")
    assert hata is None and smtp["kullanici"] == ""


# ---------- Kamera formu ----------

def _kamera_dogrula(**alanlar):
    import arayuz
    d = {"kod": "K1", "yatak": "Y1", "adres": "http://x", "kullanici": "", "sifre": "", **alanlar}
    return arayuz.KameraFormu._dogrula(SimpleNamespace(diger={}), d, "ip")


def test_kamera_formunda_eposta_alani_yok():
    """Bildirim ve onay adresleri artık sorulmaz; Ayarlar'dan ve oturumdan gelir."""
    import arayuz
    alan_adlari = [ad for ad, _ in arayuz.KameraFormu.ALANLAR]
    assert "bildirim_eposta" not in alan_adlari
    assert "onay_eposta" not in alan_adlari
    assert alan_adlari == ["kod", "yatak", "adres", "kullanici", "sifre"]


def test_kamera_alanlari_iki_gruba_ayrilmis():
    import arayuz
    assert arayuz.KameraFormu.BILGI_ALANLARI == ("kod", "yatak", "adres")
    assert arayuz.KameraFormu.GIRIS_ALANLARI == ("kullanici", "sifre")


def test_her_alanin_aciklamasi_var():
    import arayuz
    form = arayuz.KameraFormu
    for ad in ("kod", "yatak", "kullanici", "sifre"):
        assert form.ACIKLAMA[ad].strip(), ad
    assert "K1" in form.ACIKLAMA["kod"]
    assert "Y1" in form.ACIKLAMA["yatak"]
    assert "Sizin hesabınız değildir" in form.ACIKLAMA["kullanici"]
    assert "Şifreli saklanır" in form.ACIKLAMA["sifre"]


def test_adres_aciklamasi_tipe_gore_degisir():
    import arayuz
    assert "shot.jpg" in arayuz.KameraFormu.ADRES_ACIKLAMA["ip"]
    assert "0" in arayuz.KameraFormu.ADRES_ACIKLAMA["webcam"]


def test_kamera_dogrulamasi_epostasiz_calisir():
    assert _kamera_dogrula() is None
    assert "boş olamaz" in _kamera_dogrula(kod="")
    assert "http://" in _kamera_dogrula(adres="10.0.0.5")
