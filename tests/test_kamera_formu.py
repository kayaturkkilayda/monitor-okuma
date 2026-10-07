"""Kamera ekle/düzenle penceresi: alan açıklamaları, isteğe bağlı giriş ve 401 mesajı."""
import tkinter as tk

import pytest

import arayuz


# ---------- Bağlantı testi mesajı ----------

def test_401_kullanici_sifre_istiyor_der():
    mesaj = arayuz.baglanti_hata_mesaji("K1", "HTTPError", 401)
    assert "kullanıcı adı veya şifre istiyor" in mesaj
    assert "Kamera girişi" in mesaj                  # ne yapacağı da yazıyor
    assert "K1" in mesaj


def test_403_de_kimlik_mesaji_verir():
    assert "izin vermiyor" in arayuz.baglanti_hata_mesaji("K1", "HTTPError", 403)


def test_baska_hatada_teknik_neden_gosterilir():
    mesaj = arayuz.baglanti_hata_mesaji("K1", "ConnectTimeout", None)
    assert "ConnectTimeout" in mesaj
    assert "kullanıcı adı veya şifre istiyor" not in mesaj


def test_neden_bilinmiyorsa_genel_oneri():
    assert arayuz.TEST_VARSAYILAN in arayuz.baglanti_hata_mesaji("K1", None, None)


# ---------- İsteğe bağlı alan ipucu ----------

@pytest.fixture
def ipuclu(tk_kok):
    pencere = tk.Toplevel(tk_kok)
    pencere.withdraw()
    yield pencere
    pencere.destroy()


def test_bos_alanda_ipucu_gorunur(ipuclu):
    deger = tk.StringVar()
    kutu = arayuz.IpuculuGiris(ipuclu, deger, "İsteğe bağlı")
    assert deger.get() == "İsteğe bağlı"
    assert kutu.deger() == ""                        # ayarlara boş yazılır


def test_odak_gelince_ipucu_temizlenir(ipuclu):
    deger = tk.StringVar()
    kutu = arayuz.IpuculuGiris(ipuclu, deger, "İsteğe bağlı")
    kutu._odak_geldi()
    assert deger.get() == ""
    deger.set("admin")
    assert kutu.deger() == "admin"


def test_bos_birakilinca_ipucu_geri_gelir(ipuclu):
    deger = tk.StringVar()
    kutu = arayuz.IpuculuGiris(ipuclu, deger, "İsteğe bağlı")
    kutu._odak_geldi()
    kutu._odak_gitti()
    assert deger.get() == "İsteğe bağlı" and kutu.deger() == ""


def test_dolu_alanda_ipucu_cikmaz(ipuclu):
    deger = tk.StringVar(value="admin")
    kutu = arayuz.IpuculuGiris(ipuclu, deger, "İsteğe bağlı")
    assert deger.get() == "admin" and kutu.deger() == "admin"


def test_sifre_ipucusu_yildizlanmaz_ama_sifre_gizlenir(ipuclu):
    deger = tk.StringVar()
    kutu = arayuz.IpuculuGiris(ipuclu, deger, "İsteğe bağlı", gizli=True)
    assert kutu.cget("show") == ""                   # ipucu okunabilir olmalı
    kutu._odak_geldi()
    assert kutu.cget("show") == "*"                  # yazılan şifre gizli


# ---------- Formun kendisi ----------

@pytest.fixture
def form(tk_kok):
    f = arayuz.KameraFormu(tk_kok, {})
    f.withdraw()
    yield f
    try:
        f.grab_release()
    except tk.TclError:
        pass
    f.destroy()


def test_formda_iki_grup_var(form):
    from tkinter import ttk

    govde = form.winfo_children()[0]
    gruplar = [c.cget("text") for c in govde.winfo_children() if isinstance(c, ttk.LabelFrame)]
    assert gruplar == ["Kamera bilgileri", "Kamera girişi (isteğe bağlı)"]


def test_kullanici_ve_sifre_ipuclu(form):
    for ad in ("kullanici", "sifre"):
        assert isinstance(form.girisler[ad], arayuz.IpuculuGiris), ad
        assert form.girisler[ad].ipucu == "İsteğe bağlı"


def test_adres_aciklamasi_tip_degisince_guncellenir(form):
    assert "shot.jpg" in form.adres_aciklamasi.cget("text")
    form.tip.set("webcam")
    form.update()
    assert "numarası" in form.adres_aciklamasi.cget("text")


def test_bos_birakilan_giris_ayarlara_bos_yazilir(form):
    form.degerler["kod"].set("K1")
    form.degerler["yatak"].set("Y1")
    form.degerler["adres"].set("http://10.0.0.5/shot.jpg")
    d = form._degerleri_al()
    assert d["kullanici"] == "" and d["sifre"] == ""      # ipucu metni sızmaz
