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


def test_kayitta_yalnizca_izinli_alan_onerilir():
    assert eg.oneri_alanlari("@Akgun.com.tr", yalnizca_izinli=True) == ["akgun.com.tr"]
    assert eg.oneri_alanlari("", yalnizca_izinli=True)[0] == "gmail.com"   # ayar yoksa yaygınlar


def test_kurum_alan_adi_en_basta_ve_tekrarsiz():
    alanlar = eg.oneri_alanlari("gmail.com")
    assert alanlar[0] == "gmail.com" and alanlar.count("gmail.com") == 1


@pytest.mark.parametrize("metin,gecerli", [
    ("ayse@akgun.com.tr", True), ("Ayse.Yilmaz@gmail.com", True), ("ayse@gmail", False),
    ("ayse", False), ("ayse@@gmail.com", False), ("ay se@gmail.com", False), ("", False)])
def test_eposta_bicimi(metin, gecerli):
    assert eg.eposta_gecerli_mi(metin) is gecerli


# ---------- Giriş kutusu ----------

@pytest.fixture
def kutu(tk_kok):
    pencere = tk.Toplevel(tk_kok)
    pencere.withdraw()
    deger = tk.StringVar()
    k = eg.EpostaGirisi(pencere, deger, lambda: eg.oneri_alanlari("akgun.com.tr"))
    k.pack()
    yield k, deger
    pencere.destroy()


def test_yazarken_oneri_listesi_acilir_ve_secilir(kutu):
    k, deger = kutu
    deger.set("ayse@ak")
    assert k.gorunur_oneriler() == ["ayse@akgun.com.tr"]
    k.sec(0)
    assert deger.get() == "ayse@akgun.com.tr"
    assert k.gorunur_oneriler() == []                                   # seçince kapanır


def test_asagi_ok_ile_listeye_gecilir(kutu):
    k, deger = kutu
    deger.set("ayse@")
    k._listeye_gec()
    assert k.oneriler.curselection() == (0,)


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
