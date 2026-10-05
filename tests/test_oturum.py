"""Beni hatırla: cihazda kalıcı oturum."""
import logging
import re
import tkinter as tk
from datetime import datetime, timedelta

import pytest

import arka_plan
import giris_ekrani as ge
import kullanicilar as ku
import oturum
from veritabani import baglan

SIMDI = datetime(2026, 10, 5, 9, 0, 0)


@pytest.fixture
def kullanici():
    return ku.ilk_yoneticiyi_olustur("bt@akgun.com.tr", "BT", "GizliSifre1")


def oturum_satirlari():
    with baglan() as db:
        return [dict(s) for s in db.execute("SELECT * FROM oturumlar")]


# ---------- Saklama ----------

def test_cihazda_sifreli_veritabaninda_hash(kullanici):
    oturum.hatirla(kullanici["id"], SIMDI)
    dosya = oturum.OTURUM_DOSYASI.read_text(encoding="ascii")
    assert dosya.startswith("dpapi:")                                  # DPAPI ile şifreli
    anahtar = oturum._dosyadaki_anahtar()
    (satir,) = oturum_satirlari()
    assert satir["token_hash"] != anahtar and anahtar not in satir["token_hash"]
    assert len(satir["token_hash"]) == 64                              # SHA-256
    assert satir["son_kullanma"] == "2026-11-04 09:00:00"              # 30 gün


def test_hatirlanan_kullanici_ve_sure_uzar(kullanici):
    oturum.hatirla(kullanici["id"], SIMDI)
    k = oturum.hatirlanan_kullanici(SIMDI + timedelta(days=20))
    assert k["eposta"] == "bt@akgun.com.tr" and "sifre_hash" not in k
    assert oturum_satirlari()[0]["son_kullanma"] == "2026-11-24 09:00:00"


def test_suresi_dolan_oturum_duser(kullanici):
    oturum.hatirla(kullanici["id"], SIMDI)
    assert oturum.hatirlanan_kullanici(SIMDI + timedelta(days=31)) is None
    assert not oturum.OTURUM_DOSYASI.exists() and oturum_satirlari() == []


def test_dosya_yoksa_ya_da_bozuksa_oturum_yok(kullanici):
    assert oturum.hatirlanan_kullanici() is None
    oturum.OTURUM_DOSYASI.write_text("bozuk", encoding="ascii")
    assert oturum.hatirlanan_kullanici() is None


def test_baska_anahtar_gecmez(kullanici):
    oturum.hatirla(kullanici["id"], SIMDI)
    from sifreleme import sifrele
    oturum.OTURUM_DOSYASI.write_text(sifrele("tahmin-edilen-anahtar"), encoding="ascii")
    assert oturum.hatirlanan_kullanici(SIMDI) is None


def test_unut_cihazdaki_oturumu_kapatir(kullanici):
    oturum.hatirla(kullanici["id"], SIMDI)
    oturum.unut()
    assert not oturum.OTURUM_DOSYASI.exists() and oturum_satirlari() == []
    assert oturum.hatirlanan_kullanici(SIMDI) is None


def test_yeniden_hatirlamada_eski_anahtar_silinir(kullanici):
    oturum.hatirla(kullanici["id"], SIMDI)
    oturum.hatirla(kullanici["id"], SIMDI)
    assert len(oturum_satirlari()) == 1


def test_sifre_sifirlaninca_tum_oturumlar_kapanir(kullanici):
    oturum.hatirla(kullanici["id"], SIMDI)
    _, kod = ku.sifirlama_baslat("bt@akgun.com.tr")
    ku.sifre_sifirla("bt@akgun.com.tr", kod, "YeniSifre99")
    assert oturum_satirlari() == []
    assert oturum.hatirlanan_kullanici() is None


# ---------- Giriş ekranında ----------

class HemenCalisan:
    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


@pytest.fixture
def ekran(tk_kok, kullanici, monkeypatch):
    mailler, girenler = [], []
    monkeypatch.setattr(ge, "gonder", lambda smtp, alici, konu, metin: mailler.append(metin))
    monkeypatch.setattr(arka_plan.threading, "Thread", HemenCalisan)
    pencere = tk.Toplevel(tk_kok)
    pencere.withdraw()
    smtp = {"sunucu": "127.0.0.1", "gonderen": "m@akgun.com.tr"}
    e = ge.GirisEkrani(pencere, lambda: {"smtp": smtp, "izin_verilen_alan_adi": "akgun.com.tr"},
                       girenler.append, logging.getLogger("test-oturum"))
    e.pack()
    yield e, girenler, mailler
    pencere.destroy()


def _giris(e, sifre="GizliSifre1"):
    e.alanlar["giris"]["eposta"].set("bt@akgun.com.tr")
    e.alanlar["giris"]["sifre"].set(sifre)
    e._giris()


def test_beni_hatirla_varsayilan_isaretli_ve_oturum_acik_kalir(ekran):
    e, girenler, _ = ekran
    assert e.hatirla.get() is True
    _giris(e)
    assert girenler and oturum.hatirlanan_kullanici()["eposta"] == "bt@akgun.com.tr"


def test_beni_hatirla_isaretsizse_oturum_kalmaz(ekran):
    e, girenler, _ = ekran
    oturum.hatirla(ku.giris("bt@akgun.com.tr", "GizliSifre1")["id"])   # önceden hatırlanmış olsa bile
    e.hatirla.set(False)
    _giris(e)
    assert girenler and oturum.hatirlanan_kullanici() is None


def test_yanlis_sifrede_oturum_acilmaz(ekran):
    e, girenler, _ = ekran
    _giris(e, "YanlisSifre")
    assert girenler == [] and oturum.hatirlanan_kullanici() is None


def test_sifreyi_goster(ekran):
    e, *_ = ekran
    e.goster("kayit")
    assert e.girisler["kayit"]["sifre"].cget("show") == "*"
    e.goster_kutusu["kayit"].set(True)
    e._sifreyi_goster("kayit")
    assert e.girisler["kayit"]["sifre"].cget("show") == "" == e.girisler["kayit"]["tekrar"].cget("show")
    e.goster("giris")
    e.goster("kayit")                                                  # ekrana dönünce yine gizli
    assert e.girisler["kayit"]["sifre"].cget("show") == "*" and not e.goster_kutusu["kayit"].get()


def test_sifremi_unuttum_epostayi_tasir_ve_mail_gider(ekran):
    e, _, mailler = ekran
    e.alanlar["giris"]["eposta"].set("bt@akgun.com.tr")
    e._unuttum_ac()
    assert e.aktif == "unuttum" and e.deger("unuttum", "eposta") == "bt@akgun.com.tr"
    e._sifirlama_baslat()
    e.update()
    assert len(mailler) == 1 and re.search(r"\b\d{6}\b", mailler[0])
    assert e.aktif == "sifirla"


# ---------- Ana pencere ----------

def test_cikis_hatirlanan_oturumu_kapatir(kullanici, monkeypatch):
    import arayuz
    from conftest import tk_ac
    monkeypatch.setattr(arayuz, "ayarlari_oku", lambda: {"tesis_kodu": "H01", "kameralar": [],
                                                         "gonderim_araligi_sn": 30})
    monkeypatch.setattr(arayuz, "durumlari_oku", lambda: {})
    oturum.hatirla(kullanici["id"])
    uyg = tk_ac(lambda: arayuz.Uygulama(kullanici, logging.getLogger("test-oturum")))
    uyg.withdraw()
    uyg._cikis()
    assert oturum.hatirlanan_kullanici() is None


def test_acilista_hatirlanan_oturumla_giris_penceresi_acilmaz(kullanici, monkeypatch):
    import arayuz
    oturum.hatirla(kullanici["id"])
    acilan = []

    class SahteUygulama:
        def __init__(self, o, log):
            acilan.append(o["eposta"])
            self.cikis_yapildi = False

        def mainloop(self):
            pass

    monkeypatch.setattr(arayuz, "Uygulama", SahteUygulama)
    monkeypatch.setattr(arayuz, "giris_penceresi", lambda log: pytest.fail("giriş penceresi açılmamalıydı"))
    monkeypatch.setattr(arayuz, "log_kur", lambda **k: logging.getLogger("test-oturum"))
    arayuz.calistir()
    assert acilan == ["bt@akgun.com.tr"]
