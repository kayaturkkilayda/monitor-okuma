import tkinter as tk

import pytest

import eposta_girisi as eg


# ---------- Öneriler ----------

def test_at_isaretinden_sonra_alan_adi_onerileri():
    alanlar = eg.oneri_alanlari("akgun.com.tr")
    assert eg.alan_onerileri("ayse@", alanlar)[:3] == ["ayse@akgun.com.tr", "ayse@gmail.com", "ayse@hotmail.com"]
    assert eg.alan_onerileri("ayse@g", alanlar) == ["ayse@gmail.com"]
    assert eg.alan_onerileri("ayse@HO", alanlar) == ["ayse@hotmail.com"]


def test_oneri_olmayan_durumlar():
    alanlar = eg.oneri_alanlari(None)
    assert eg.alan_onerileri("ayse", alanlar) == []                      # @ yok
    assert eg.alan_onerileri("@gm", alanlar) == []                       # @'den önce bir şey yok
    assert eg.alan_onerileri("ayse@gmail.com", alanlar) == []           # zaten tam
    assert eg.alan_onerileri("a@b@c", alanlar) == []


def test_kayitta_yalnizca_izinli_alanlar_onerilir():
    assert eg.oneri_alanlari("@Akgun.com.tr", yalnizca_izinli=True) == ["akgun.com.tr"]
    assert eg.oneri_alanlari([" @AKGUN.com.tr ", "Hastane1.com.tr"],
                             yalnizca_izinli=True) == ["akgun.com.tr", "hastane1.com.tr"]
    assert eg.oneri_alanlari([], yalnizca_izinli=True)[0] == "gmail.com"   # ayar yoksa yaygınlar


def test_izinli_alanlar_onerilerin_basinda():
    alanlar = eg.oneri_alanlari(["akgun.com.tr", "hastane1.com.tr"])
    assert alanlar[:2] == ["akgun.com.tr", "hastane1.com.tr"]
    assert "gmail.com" in alanlar                       # liste doluyken de yaygınlar önerilir


def test_kurum_alan_adi_en_basta_ve_tekrarsiz():
    alanlar = eg.oneri_alanlari("gmail.com")
    assert alanlar[0] == "gmail.com" and alanlar.count("gmail.com") == 1


# ---------- Satır içi tamamlama (saf fonksiyon) ----------

def test_tamamlama_tek_oneri_dondurur():
    alanlar = eg.oneri_alanlari(None)
    assert eg.tamamlama("ayse@g", alanlar) == "ayse@gmail.com"
    assert eg.tamamlama("ayse@HO", alanlar) == "ayse@hotmail.com"


def test_tamamlama_yoksa_none():
    alanlar = eg.oneri_alanlari(None)
    assert eg.tamamlama("ayse", alanlar) is None                 # @ yok
    assert eg.tamamlama("ayse@gmail.com", alanlar) is None       # zaten tam
    assert eg.tamamlama("ayse@zzz", alanlar) is None             # eşleşen alan adı yok


def test_tamamlamada_kurum_alan_adi_once_gelir():
    alanlar = eg.oneri_alanlari("akgun.com.tr")
    assert eg.tamamlama("ayse@", alanlar) == "ayse@akgun.com.tr"


@pytest.mark.parametrize("metin,gecerli", [
    ("ayse@akgun.com.tr", True), ("Ayse.Yilmaz@gmail.com", True), ("ayse@gmail", False),
    ("ayse", False), ("ayse@@gmail.com", False), ("ay se@gmail.com", False), ("", False)])
def test_eposta_bicimi(metin, gecerli):
    assert eg.eposta_gecerli_mi(metin) is gecerli


# ---------- Giriş kutusu ----------

class SahteOlay:
    """KeyRelease olayı yerine geçer; yalnızca keysym okunuyor."""

    def __init__(self, keysym):
        self.keysym = keysym


@pytest.fixture
def kutu(tk_kok):
    pencere = tk.Toplevel(tk_kok)
    pencere.withdraw()
    deger = tk.StringVar()
    k = eg.EpostaGirisi(pencere, deger, lambda: eg.oneri_alanlari("akgun.com.tr"))
    k.pack()
    yield k, deger
    pencere.destroy()


def yaz(k, deger, metin: str):
    """Kullanıcı kutuya yazmış gibi davranır: metin + imleç sonda + tamamlama."""
    deger.set(metin)
    k.giris.icursor("end")
    k._tus_birakildi(SahteOlay("a"))


def test_yazarken_kalan_alan_adi_kutuda_secili_gorunur(kutu):
    k, deger = kutu
    yaz(k, deger, "ayse@ak")
    assert deger.get() == "ayse@akgun.com.tr"       # tamamlanmış hâli kutuda
    assert k.secili_metin() == "gun.com.tr"         # yalnızca kalan kısım seçili


def test_tamamlama_kabul_edilince_secim_kalkar(kutu):
    k, deger = kutu
    yaz(k, deger, "ayse@g")
    assert k.secili_metin() == "mail.com"
    k.kabul_et()
    assert k.secili_metin() == ""
    assert deger.get() == "ayse@gmail.com"          # metin aynen kalır


def test_enter_once_tamamlamayi_kabul_eder(kutu):
    k, deger = kutu
    yaz(k, deger, "ayse@g")
    assert k._kabul_tusu() == "break"               # ilk Enter formu göndermez
    assert k.secili_metin() == ""
    assert k._kabul_tusu() is None                  # ikinci Enter devam eder


def test_tamamlanacak_sey_yoksa_metin_degismez(kutu):
    k, deger = kutu
    yaz(k, deger, "ayse")
    assert deger.get() == "ayse"
    assert k.secili_metin() == ""


def test_silerken_tamamlama_yapilmaz(kutu):
    k, deger = kutu
    deger.set("ayse@ak")
    k.giris.icursor("end")
    k._tus_birakildi(SahteOlay("BackSpace"))
    assert deger.get() == "ayse@ak"                 # silerken araya girilmez
    assert k.secili_metin() == ""


def test_imlec_sonda_degilse_tamamlanmaz(kutu):
    k, deger = kutu
    deger.set("ayse@ak")
    k.giris.icursor(2)                              # kullanıcı metnin ortasını düzeltiyor
    k.tamamla()
    assert deger.get() == "ayse@ak"


def test_yazmaya_devam_edince_tamamlama_yenilenir(kutu):
    k, deger = kutu
    yaz(k, deger, "ayse@h")
    assert deger.get() == "ayse@hotmail.com"
    yaz(k, deger, "ayse@y")                         # seçili kısmın yerine yeni harf
    assert deger.get() == "ayse@yahoo.com"


def test_gecerlilik_ipucu(kutu):
    k, deger = kutu
    deger.set("ayse")
    assert k.ipucu.cget("text") == ""                                  # henüz @ yok, erken uyarma
    deger.set("ayse@akgun.com.tr")
    assert "✓" in k.ipucu.cget("text")
    deger.set("ayse@akgun.c")
    assert "değil" in k.ipucu.cget("text")
    deger.set("ayse")
    k._ipucu_guncelle(son_karar=True)                                   # alandan çıkınca
    assert "değil" in k.ipucu.cget("text")
