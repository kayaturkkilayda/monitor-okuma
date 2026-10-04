import tkinter as tk

import pytest

from ayar_sekmesi import AyarSekmesi

TEMEL = {"tesis_kodu": "H01", "api_url": "", "api_key": "", "gonderim_araligi_sn": 60,
         "ikinci_cekim_gecikme_sn": 5, "format": "avif", "kalite": 85, "saklama_gun": 7,
         "gonderilince_sil": True, "kameralar": []}


@pytest.fixture(scope="module")
def kok():
    try:
        pencere = tk.Tk()
    except tk.TclError:
        pytest.skip("Ekran yok, Tk açılamıyor")
    pencere.withdraw()
    yield pencere
    pencere.destroy()


def test_eski_ayar_dosyasinda_kayit_saklama_varsayilan_90_gorunur(kok):
    sekme = AyarSekmesi(kok, dict(TEMEL))
    assert sekme.degerler["kayit_saklama_gun"].get() == "90"
    yeni, hata = sekme._dogrula()
    assert hata is None
    assert yeni["kayit_saklama_gun"] == 90


@pytest.mark.parametrize("deger", ["0", "3651", "abc"])
def test_kayit_saklama_gecersiz_deger_reddedilir(kok, deger):
    sekme = AyarSekmesi(kok, {**TEMEL, "kayit_saklama_gun": 90})
    sekme.degerler["kayit_saklama_gun"].set(deger)
    yeni, hata = sekme._dogrula()
    assert yeni is None
    assert "Gönderim kaydı saklama" in hata
