from tkinter import ttk

import pytest

import loglar_sekmesi as ls
from veritabani import baglan

HEPSI = ls.SEVIYE_SECENEKLERI["Hepsi"]


def olay_ekle(seviye, mesaj, zaman="2026-10-02 15:00:00", kaynak="sistem"):
    with baglan() as db:
        return db.execute("INSERT INTO olaylar (zaman, seviye, kaynak, mesaj) VALUES (?, ?, ?, ?)",
                          (zaman, seviye, kaynak, mesaj)).lastrowid


@pytest.fixture
def ornekler():
    olay_ekle("INFO", "Motor başladı")
    olay_ekle("WARNING", "gönderilemedi", kaynak="K1")
    olay_ekle("ERROR", "ARIZA", kaynak="K2")
    olay_ekle("INFO", "Ayarlar değişti")


def mesajlar(olaylar):
    return [o["mesaj"] for o in olaylar]


# ---------- Sorgu ----------

def test_eskiden_yeniye_sirali(ornekler):
    assert mesajlar(ls.olaylari_getir(HEPSI)) == ["Motor başladı", "gönderilemedi", "ARIZA",
                                                  "Ayarlar değişti"]


def test_seviye_filtresi(ornekler):
    assert mesajlar(ls.olaylari_getir(ls.SEVIYE_SECENEKLERI["Uyarı ve hata"])) == ["gönderilemedi", "ARIZA"]
    assert mesajlar(ls.olaylari_getir(ls.SEVIYE_SECENEKLERI["Sadece hata"])) == ["ARIZA"]


def test_yalnizca_yeni_olaylar(ornekler):
    son = ls.olaylari_getir(HEPSI)[1]["id"]
    assert mesajlar(ls.olaylari_getir(HEPSI, son_id=son)) == ["ARIZA", "Ayarlar değişti"]


def test_ilk_yuklemede_son_olaylar():
    for i in range(15):
        olay_ekle("INFO", f"m{i}")
    assert mesajlar(ls.olaylari_getir(HEPSI, limit=10)) == [f"m{i}" for i in range(5, 15)]


def test_satir_zamani_ekran_biciminde():
    olay_ekle("WARNING", "x", zaman="2026-10-02 15:12:13", kaynak="K1")
    assert ls.satir_degerleri(ls.olaylari_getir(HEPSI)[0]) == ("02.10.2026 15:12:13", "Uyarı", "K1", "x")


# ---------- Sekme ----------

@pytest.fixture
def sekme(tk_kok, ornekler):
    s = ls.LoglarSekmesi(tk_kok)
    yield s
    s.destroy()


@pytest.fixture
def gorunur(tk_kok, sekme):
    """Kaydırma yalnızca ekranda görünen listede ölçülebilir: pencereyi kısa süre göster."""
    sekme.pack(fill="both", expand=True)
    tk_kok.deiconify()
    tk_kok.update()
    yield sekme
    tk_kok.withdraw()


def test_renkler_seviyeden_gelir(sekme):
    satirlar = sekme.liste.get_children()
    assert sekme.liste.item(satirlar[0], "tags") == ("INFO",)
    assert sekme.liste.item(satirlar[1], "tags") == ("WARNING",)
    assert sekme.liste.item(satirlar[2], "tags") == ("ERROR",)
    assert str(sekme.liste.tag_configure("INFO", "background")) == "#e7f6ec"       # yeşil
    assert str(sekme.liste.tag_configure("WARNING", "background")) == "#fff3cd"    # sarı
    assert str(sekme.liste.tag_configure("ERROR", "background")) == "#f8d7da"      # kırmızı


def test_her_seviyenin_kendi_rengi_var(sekme):
    """Yeşil = yolunda, sarı = kendi kendine tekrar deneniyor, kırmızı = elle müdahale."""
    assert set(ls.SEVIYE_RENGI) == {"INFO", "WARNING", "ERROR"}
    assert len(set(ls.SEVIYE_RENGI.values())) == 3           # üç ayrı renk
    for seviye in ls.SEVIYE_RENGI:
        assert str(sekme.liste.tag_configure(seviye, "background")) == ls.SEVIYE_RENGI[seviye]
        assert str(sekme.liste.tag_configure(seviye, "foreground")) == ls.SEVIYE_YAZI_RENGI[seviye]


def test_yeni_olaylar_alta_eklenir_secim_korunur(sekme):
    ilk = sekme.liste.get_children()[0]
    sekme.liste.selection_set(ilk)
    olay_ekle("ERROR", "yeni hata")
    sekme.yenile()
    assert sekme.liste.item(sekme.liste.get_children()[-1], "values")[3] == "yeni hata"
    assert len(sekme.liste.get_children()) == 5
    assert sekme.liste.selection() == (ilk,)


def test_filtre_degisince_liste_bastan_kurulur(sekme):
    sekme.seviye.set("Sadece hata")
    sekme.bastan_yukle()
    assert [sekme.liste.item(s, "values")[3] for s in sekme.liste.get_children()] == ["ARIZA"]


def _yeni_olaylar(sekme, adet):
    for i in range(adet):
        olay_ekle("INFO", f"satır {i}")
    sekme.yenile()
    sekme.update()


def test_otomatik_kaydir_isaretliyse_son_satir_gorunur(gorunur):
    _yeni_olaylar(gorunur, 60)
    assert gorunur.liste.yview()[1] == 1.0


def test_otomatik_kaydir_kapaliysa_yer_degismez(gorunur):
    gorunur.otomatik_kaydir.set(False)
    gorunur.liste.yview_moveto(0)
    _yeni_olaylar(gorunur, 60)
    assert gorunur.liste.yview()[0] == 0.0


def test_baska_sekmedeyken_gelenler_sekme_acilinca_gorunur(tk_kok, ornekler):
    """Kullanıcı Kameralar sekmesindeyken gelen olaylar, Loglar'a geçince en altta görünür."""
    defter = ttk.Notebook(tk_kok)
    defter.pack(fill="both", expand=True)
    defter.add(ttk.Frame(defter), text="Kameralar")
    sekme = ls.LoglarSekmesi(defter)
    defter.add(sekme, text="Loglar")
    tk_kok.deiconify()
    try:
        tk_kok.update()
        _yeni_olaylar(sekme, 80)
        defter.select(sekme)
        tk_kok.update()
        assert sekme.liste.yview()[1] == 1.0
    finally:
        tk_kok.withdraw()
        defter.destroy()


def test_ekranda_en_fazla_satir_tutulur(sekme, monkeypatch):
    monkeypatch.setattr(ls, "EN_FAZLA", 10)
    _yeni_olaylar(sekme, 20)
    satirlar = sekme.liste.get_children()
    assert len(satirlar) == 10
    assert sekme.liste.item(satirlar[-1], "values")[3] == "satır 19"
