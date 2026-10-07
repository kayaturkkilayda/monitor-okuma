"""Altı kutulu kod girişi: rakam filtresi, imleç akışı, yapıştırma ve hata gösterimi."""
import tkinter as tk

import pytest

import kod_girisi as kg
from kullanicilar import KullaniciHatasi


# ---------- Saf fonksiyon ----------

@pytest.mark.parametrize("metin,beklenen", [
    ("123456", "123456"), ("123-456", "123456"), (" 12 34 56 ", "123456"),
    ("1234567890", "123456"), ("abc", ""), ("", ""), ("kod: 987654 ", "987654"),
])
def test_rakamlari_ayikla(metin, beklenen):
    assert kg.rakamlari_ayikla(metin) == beklenen


# ---------- Kutular ----------

@pytest.fixture
def giris(tk_kok):
    pencere = tk.Toplevel(tk_kok)
    pencere.withdraw()
    tamamlananlar = []
    k = kg.KodGirisi(pencere, tamamlandi=tamamlananlar.append)
    k.pack()
    yield k, tamamlananlar
    pencere.destroy()


def test_alti_kutu_olusur(giris):
    k, _ = giris
    assert len(k.kutular) == 6 and len(k.degerler) == 6


def test_yalnizca_rakam_kabul_edilir(giris):
    k, _ = giris
    assert k._tek_rakam("5") is True
    assert k._tek_rakam("") is True
    assert k._tek_rakam("a") is False
    assert k._tek_rakam("55") is False        # kutuya tek hane
    assert k._tek_rakam("-") is False


def test_rakam_yazinca_imlec_ilerler(giris):
    k, _ = giris
    k.degerler[0].set("1")
    k._tus_birakildi(0, None)
    assert k.odakli == 1


def test_bos_kutuda_backspace_oncekine_doner_ve_siler(giris):
    k, _ = giris
    k.yaz("12")
    k.kutular[2].focus_set()
    k._tus_birakildi(2, SahteTus("BackSpace"))
    assert k.odakli == 1
    assert k.degerler[1].get() == ""           # önceki hane silindi


def test_dolu_kutuda_backspace_yerinde_kalir(giris):
    k, _ = giris
    k.yaz("123456")
    k.degerler[3].set("")                      # kullanıcı kendi kutusunu sildi
    k.kutular[3].focus_set()
    k._tus_birakildi(3, SahteTus("BackSpace"))
    assert k.degerler[2].get() == ""           # boşalmıştı, öncekine geçer


def test_ok_tuslariyla_gezinme(giris):
    k, _ = giris
    k.kutular[2].focus_set()
    k._tus_birakildi(2, SahteTus("Left"))
    assert k.odakli == 1
    k._tus_birakildi(1, SahteTus("Right"))
    assert k.odakli == 2


class SahteTus:
    def __init__(self, keysym):
        self.keysym = keysym


# ---------- Yapıştırma ----------

def test_yapistirilan_kod_kutulara_dagilir(giris):
    k, tamamlananlar = giris
    k.yaz("123456")
    assert [d.get() for d in k.degerler] == ["1", "2", "3", "4", "5", "6"]
    assert k.kod() == "123456"
    assert tamamlananlar == ["123456"]          # dolunca kendiliğinden doğrulanır


def test_bicimli_kod_yapistirilabilir(giris):
    k, _ = giris
    k.yaz("12 34-56")
    assert k.kod() == "123456"


def test_eksik_kod_yapistirilirsa_tamamlanmaz(giris):
    k, tamamlananlar = giris
    k.yaz("123")
    assert k.kod() == "123" and not k.dolu_mu()
    assert tamamlananlar == []


# ---------- Tamamlanma ve temizleme ----------

def test_son_hane_girilince_dogrulama_tetiklenir(giris):
    k, tamamlananlar = giris
    for i, hane in enumerate("987654"):
        k.degerler[i].set(hane)
        k._tus_birakildi(i, SahteTus(hane))
    assert tamamlananlar == ["987654"]


def test_hatali_kodda_kutular_kirmizi_ve_bos(giris):
    k, _ = giris
    k.yaz("111111")
    k.temizle(hata=True)
    assert k.kod() == ""
    assert str(k.kutular[0].cget("highlightbackground")) == kg.HATA_KENAR


def test_yazmaya_baslayinca_kirmizi_kalkar(giris):
    k, _ = giris
    k.temizle(hata=True)
    k.degerler[0].set("7")
    k._tus_birakildi(0, SahteTus("7"))
    assert str(k.kutular[0].cget("highlightbackground")) == kg.NORMAL_KENAR


def test_temizle_imleci_basa_alir(giris):
    k, _ = giris
    k.yaz("123456")
    k.temizle()
    assert k.odakli == 0


# ---------- Kod penceresi ----------

def test_pencere_dogru_kodda_kapanir_ve_sonucu_tutar(tk_kok):
    pencere = kg.KodPenceresi(tk_kok, "Onay", "Kodu girin",
                              lambda kod: "ayse@akgun.com.tr" if kod == "123456"
                              else (_ for _ in ()).throw(KullaniciHatasi("Kod hatalı")),
                              KullaniciHatasi)
    pencere.giris.yaz("123456")
    assert pencere.sonuc == "ayse@akgun.com.tr"
    assert not pencere.winfo_exists()


def test_pencere_yanlis_kodda_acik_kalir_ve_uyarir(tk_kok):
    pencere = kg.KodPenceresi(tk_kok, "Onay", "Kodu girin",
                              lambda kod: (_ for _ in ()).throw(KullaniciHatasi("Kod hatalı")),
                              KullaniciHatasi)
    try:
        pencere.giris.yaz("000000")
        assert pencere.sonuc is None
        assert "Kod hatalı" in pencere.mesaj.cget("text")
        assert pencere.giris.kod() == ""                       # kutular temizlendi
        assert str(pencere.giris.kutular[0].cget("highlightbackground")) == kg.HATA_KENAR
    finally:
        pencere.grab_release()
        pencere.destroy()
