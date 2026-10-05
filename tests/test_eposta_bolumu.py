"""Ayarlar sekmesindeki SMTP bölümü ve kamera formundaki bildirim e-postası alanı."""
from types import SimpleNamespace

import pytest

import arka_plan

import eposta_bolumu as eb
from ayar_sekmesi import AyarSekmesi

SMTP = {"sunucu": "smtp.ornek.com", "port": "587", "guvenlik": "STARTTLS", "kullanici": "bildirim",
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
    ("gonderen", "", "Gönderen"), ("gonderen", "a@x.com, b@y.com", "Gönderen"),
    ("varsayilan_alici", "bt@ornek.com, yanlis", "yanlis"),
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
    sekme.eposta.degerler["gonderen"].set("yanlis")
    yeni, hata = sekme._dogrula()
    assert yeni is None and "Gönderen" in hata


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


# ---------- Kamera formu ----------

def _kamera_dogrula(**alanlar):
    import arayuz
    d = {"kod": "K1", "yatak": "Y1", "adres": "http://x", "kullanici": "", "sifre": "",
         "bildirim_eposta": "", "onay_eposta": "sahip@ornek.com", **alanlar}
    return arayuz.KameraFormu._dogrula(SimpleNamespace(diger={}), d, "ip")


def test_kamera_formunda_bildirim_epostasi_alani():
    import arayuz
    assert "bildirim_eposta" in [ad for ad, _ in arayuz.KameraFormu.ALANLAR]


def test_kamera_bildirim_adresleri_dogrulanir():
    assert _kamera_dogrula(bildirim_eposta="") is None
    assert _kamera_dogrula(bildirim_eposta="a@x.com, b@y.com") is None
    assert "yanlis" in _kamera_dogrula(bildirim_eposta="a@x.com, yanlis")


def test_onaylayacak_eposta_zorunlu_ve_tek_adres():
    assert "zorunlu" in _kamera_dogrula(onay_eposta="")
    assert "zorunlu" in _kamera_dogrula(onay_eposta="yanlis")
    assert "zorunlu" in _kamera_dogrula(onay_eposta="a@x.com, b@y.com")
    assert _kamera_dogrula(onay_eposta="sahip@ornek.com") is None
