"""Giriş penceresi akışları: gerçek ekran, sahte e-posta gönderimi."""
import logging
import re
import tkinter as tk

import pytest

import arka_plan

import giris_ekrani as ge
import kullanicilar as ku
from veritabani import baglan

SMTP = {"sunucu": "127.0.0.1", "port": 1025, "guvenlik": "Yok", "gonderen": "monitor@akgun.com.tr"}
AYARLAR = {"smtp": SMTP, "izin_verilen_alan_adi": "akgun.com.tr"}


class HemenCalisan:
    """Testte ana döngü yok; arka plan işini hemen çalıştırır."""

    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


class KayitciLog(logging.Handler):
    def __init__(self):
        super().__init__()
        self.mesajlar = []

    def emit(self, kayit):
        self.mesajlar.append(kayit.getMessage())


@pytest.fixture
def ortam(tk_kok, monkeypatch):
    mailler, girenler = [], []
    ayarlar = {"deger": dict(AYARLAR)}
    monkeypatch.setattr(ge, "gonder", lambda smtp, alici, konu, metin: mailler.append((alici, konu, metin)))
    monkeypatch.setattr(arka_plan.threading, "Thread", HemenCalisan)
    log = logging.getLogger("test-giris")
    kayitci = KayitciLog()
    log.addHandler(kayitci)
    pencere = tk.Toplevel(tk_kok)
    pencere.withdraw()

    def kur():
        ekran = ge.GirisEkrani(pencere, lambda: ayarlar["deger"], girenler.append, log)
        ekran.pack()
        return ekran

    yield kur, mailler, girenler, ayarlar, kayitci
    log.removeHandler(kayitci)
    pencere.destroy()


def doldur(ekran, ekran_adi, **degerler):
    for alan, deger in degerler.items():
        ekran.alanlar[ekran_adi][alan].set(deger)


def mesaj(ekran, ad):
    return ekran.mesajlar[ad].cget("text")


def koddan(mail):
    return re.search(r"\b(\d{6})\b", mail[2]).group(1)


def tum_yazilar(widget):
    """Penceredeki bütün etiket ve alanların yazısı (kodun ekranda görünmediğini denetlemek için)."""
    yazilar = []
    for c in widget.winfo_children():
        try:
            yazilar.append(str(c.cget("text")))
        except tk.TclError:
            pass
        yazilar += tum_yazilar(c)
    return yazilar


def olaylar():
    with baglan() as db:
        return [dict(s) for s in db.execute("SELECT seviye, mesaj FROM olaylar ORDER BY id")]


def yonetici_var():
    ku.ilk_yoneticiyi_olustur("admin@akgun.com.tr", "Yönetici", "GizliSifre1")


# ---------- İlk yönetici ----------

def test_hic_kullanici_yoksa_ilk_yonetici_ekrani(ortam):
    kur, mailler, girenler, *_ = ortam
    ekran = kur()
    assert ekran.aktif == "ilk"
    doldur(ekran, "ilk", eposta="admin@akgun.com.tr", ad="Yönetici", sifre="GizliSifre1", tekrar="GizliSifre1")
    ekran._ilk_yonetici()
    assert girenler[0]["eposta"] == "admin@akgun.com.tr" and girenler[0]["yonetici"]
    assert mailler == []                                         # kodsuz
    assert "İlk yönetici hesabı oluşturuldu: admin@akgun.com.tr" in [o["mesaj"] for o in olaylar()]


def test_ilk_yonetici_kisa_sifre(ortam):
    kur, _, girenler, *_ = ortam
    ekran = kur()
    doldur(ekran, "ilk", eposta="admin@akgun.com.tr", ad="Y", sifre="kisa", tekrar="kisa")
    ekran._ilk_yonetici()
    assert girenler == [] and "en az 8" in mesaj(ekran, "ilk")


# ---------- Giriş ----------

def test_kullanici_varsa_giris_ekrani_ve_giris(ortam):
    kur, _, girenler, *_ = ortam
    yonetici_var()
    ekran = kur()
    assert ekran.aktif == "giris"
    doldur(ekran, "giris", eposta="admin@akgun.com.tr", sifre="Yanlis1234")
    ekran._giris()
    assert girenler == [] and mesaj(ekran, "giris") == "E-posta ya da şifre hatalı."
    assert ekran.deger("giris", "sifre") == ""                   # yanlış şifre ekranda kalmaz
    doldur(ekran, "giris", sifre="GizliSifre1")
    ekran._giris()
    assert girenler[0]["eposta"] == "admin@akgun.com.tr"


def test_kilitlenme_olaylara_yazilir(ortam):
    kur, *_ = ortam
    yonetici_var()
    ekran = kur()
    for _ in range(ku.GIRIS_EN_FAZLA_HATA):
        doldur(ekran, "giris", eposta="admin@akgun.com.tr", sifre="Yanlis1234")
        ekran._giris()
    assert "kilitlendi" in mesaj(ekran, "giris")
    assert olaylar()[-1] == {"seviye": "WARNING",
                             "mesaj": "Hesap kilitlendi (5 hatalı giriş denemesi): admin@akgun.com.tr"}


# ---------- SMTP yoksa ----------

@pytest.mark.parametrize("ekran_adi", ["kayit", "unuttum"])
def test_smtp_yoksa_mesaj_ve_dugme_kapali(ortam, ekran_adi):
    kur, mailler, _, ayarlar, _ = ortam
    yonetici_var()
    ayarlar["deger"] = {"izin_verilen_alan_adi": "akgun.com.tr"}
    ekran = kur()
    ekran.goster(ekran_adi)
    assert mesaj(ekran, ekran_adi) == "E-posta ayarları yapılmamış, yöneticinize başvurun."
    assert "disabled" in ekran.dugmeler[ekran_adi][0].state()
    # Düğme kapalı olsa da işlem çağrılırsa çökmez, kod gönderilmez
    doldur(ekran, ekran_adi, eposta="ayse@akgun.com.tr")
    if ekran_adi == "kayit":
        doldur(ekran, "kayit", ad="Ayşe", sifre="GizliSifre1", tekrar="GizliSifre1")
        ekran._kayit()
        ekran.update()
    else:
        ekran._sifirlama_baslat()
        ekran.update()
    assert mailler == [] and "E-posta ayarları yapılmamış" in mesaj(ekran, ekran_adi)


# ---------- Kayıt ----------

def test_kayit_akisi_kod_yalnizca_e_postada(ortam):
    kur, mailler, girenler, _, kayitci = ortam
    yonetici_var()
    ekran = kur()
    ekran.goster("kayit")
    doldur(ekran, "kayit", eposta="Ayse@Akgun.com.tr", ad="Ayşe", sifre="GizliSifre1", tekrar="GizliSifre1")
    ekran._kayit()
    ekran.update()
    (mail,) = mailler
    assert mail[0] == ["ayse@akgun.com.tr"] and "kayıt doğrulama kodu" in mail[1]
    kod = koddan(mail)
    assert ekran.aktif == "kayit_kod"
    # Kod hiçbir ekran yazısında, olayda ya da logda yok
    assert all(kod not in y for y in tum_yazilar(ekran))
    assert all(kod not in o["mesaj"] for o in olaylar())
    assert all(kod not in m and "GizliSifre1" not in m for m in kayitci.mesajlar)

    doldur(ekran, "kayit_kod", kod=kod)
    ekran._kayit_dogrula()
    assert ekran.aktif == "giris" and "Hesabınız açıldı" in mesaj(ekran, "giris")
    doldur(ekran, "giris", sifre="GizliSifre1")
    ekran._giris()
    assert girenler[0]["eposta"] == "ayse@akgun.com.tr" and not girenler[0]["yonetici"]


def test_kayitta_yanlis_kod(ortam):
    kur, mailler, *_ = ortam
    yonetici_var()
    ekran = kur()
    ekran.goster("kayit")
    doldur(ekran, "kayit", eposta="ayse@akgun.com.tr", ad="Ayşe", sifre="GizliSifre1", tekrar="GizliSifre1")
    ekran._kayit()
    ekran.update()
    kod = koddan(mailler[0])
    doldur(ekran, "kayit_kod", kod="000000" if kod != "000000" else "111111")
    ekran._kayit_dogrula()
    assert ekran.aktif == "kayit_kod" and "Kalan deneme: 4" in mesaj(ekran, "kayit_kod")


def test_izin_verilmeyen_alan_adi_kod_gonderilmez(ortam):
    kur, mailler, *_ = ortam
    yonetici_var()
    ekran = kur()
    ekran.goster("kayit")
    doldur(ekran, "kayit", eposta="ayse@gmail.com", ad="Ayşe", sifre="GizliSifre1", tekrar="GizliSifre1")
    ekran._kayit()
    ekran.update()
    assert mailler == [] and "@akgun.com.tr" in mesaj(ekran, "kayit")


def test_kod_maili_gonderilemezse_hata_ve_ekranda_kalir(ortam, monkeypatch):
    kur, *_ = ortam
    yonetici_var()

    def bozuk(*a):
        raise ConnectionRefusedError()
    monkeypatch.setattr(ge, "gonder", bozuk)
    ekran = kur()
    ekran.goster("kayit")
    doldur(ekran, "kayit", eposta="ayse@akgun.com.tr", ad="Ayşe", sifre="GizliSifre1", tekrar="GizliSifre1")
    ekran._kayit()
    ekran.update()
    assert ekran.aktif == "kayit"
    assert "gönderilemedi (ConnectionRefusedError)" in mesaj(ekran, "kayit")
    assert str(ekran.dugmeler["kayit"][0].cget("state")) == "normal"


# ---------- Şifremi unuttum ----------

def test_sifre_sifirlama_akisi(ortam):
    kur, mailler, girenler, *_ = ortam
    yonetici_var()
    ekran = kur()
    ekran.goster("unuttum")
    doldur(ekran, "unuttum", eposta="admin@akgun.com.tr")
    ekran._sifirlama_baslat()
    ekran.update()
    kod = koddan(mailler[0])
    assert "şifre sıfırlama kodu" in mailler[0][1] and ekran.aktif == "sifirla"
    assert all(kod not in y for y in tum_yazilar(ekran))
    doldur(ekran, "sifirla", kod=kod, sifre="YeniSifre99", tekrar="YeniSifre99")
    ekran._sifre_sifirla()
    assert ekran.aktif == "giris" and "değiştirildi" in mesaj(ekran, "giris")
    doldur(ekran, "giris", sifre="YeniSifre99")
    ekran._giris()
    assert girenler[0]["eposta"] == "admin@akgun.com.tr"
    assert "Şifre sıfırlandı: admin@akgun.com.tr" in [o["mesaj"] for o in olaylar()]


def test_kayitli_olmayan_adreste_ayni_mesaj_ama_mail_yok(ortam):
    kur, mailler, *_ = ortam
    yonetici_var()
    ekran = kur()
    ekran.goster("unuttum")
    doldur(ekran, "unuttum", eposta="yok@akgun.com.tr")
    ekran._sifirlama_baslat()
    ekran.update()
    assert mailler == []
    assert ekran.aktif == "sifirla" and "kayıtlı bir hesap varsa" in mesaj(ekran, "sifirla")


def test_ekran_degisince_sifre_ve_kod_alanlari_temizlenir(ortam):
    kur, *_ = ortam
    yonetici_var()
    ekran = kur()
    doldur(ekran, "giris", eposta="admin@akgun.com.tr", sifre="GizliSifre1")
    ekran.goster("kayit")
    ekran.goster("giris")
    assert ekran.deger("giris", "sifre") == "" and ekran.deger("giris", "eposta") == "admin@akgun.com.tr"


def test_sifre_alanlari_gizli(ortam):
    kur, *_ = ortam
    ekran = kur()
    for ad, girisler in ekran.girisler.items():
        for alan, giris in girisler.items():
            assert (giris.cget("show") == "*") == (alan in ("sifre", "tekrar")), (ad, alan)
