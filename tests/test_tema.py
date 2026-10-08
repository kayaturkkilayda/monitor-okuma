"""Yazı tipi/ölçek ayarı (tema.py) ve pencere büyüyünce düzenin esnemesi."""
import logging
import tkinter as tk
from tkinter import font as tkfont, ttk

import pytest

import tema
from ayar_sekmesi import AyarSekmesi

TEMEL = {"tesis_kodu": "H01", "api_url": "", "api_key": "", "gonderim_araligi_sn": 60,
         "ikinci_cekim_gecikme_sn": 5, "format": "avif", "kalite": 85, "saklama_gun": 7,
         "gonderilince_sil": True, "kameralar": [], "izin_verilen_alan_adi": ["akgun.com.tr"],
         "smtp": {}}
YONETICI = {"eposta": "admin@akgun.com.tr", "ad": "Yönetici", "yonetici": True}
KULLANICI = {"eposta": "ayse@akgun.com.tr", "ad": "Ayşe", "yonetici": False}
LOG = logging.getLogger("test-tema")


@pytest.fixture
def stil(tk_kok):
    return tema.kur(tk_kok)


@pytest.fixture
def gorunur_kok(tk_kok):
    """Genişlik ölçümü yalnızca ekranda görünen pencerede yapılabilir; kısa süre gösterilir."""
    tk_kok.deiconify()
    yield tk_kok
    tk_kok.geometry("")
    tk_kok.withdraw()


def _yazi_adi(deger) -> str:
    """Tk yazı tipini '{Segoe UI} 10' gibi döndürür; karşılaştırma için sadeleştirilir."""
    return str(deger).replace("{", "").replace("}", "")


# ---------- Yazı tipleri ----------

def test_normal_metin_segoe_ui_11(stil, tk_kok):
    yazi = tkfont.nametofont("TkDefaultFont", root=tk_kok)
    assert (yazi.cget("family"), yazi.cget("size")) == (tema.AILE, 11)


def test_basliklar_12_kalin(stil, tk_kok):
    assert tkfont.nametofont("TkHeadingFont", root=tk_kok).cget("size") == 12
    assert tema.BASLIK_YAZI == (tema.AILE, 12, "bold")


def test_kucuk_aciklamalar_10_ve_gri(stil):
    assert tema.KUCUK_YAZI == (tema.AILE, 10)
    assert _yazi_adi(stil.lookup("Kucuk.TLabel", "font")) == f"{tema.AILE} 10"
    assert stil.lookup("Kucuk.TLabel", "foreground") == tema.GRI


def test_sekme_adlari_12_kalin(stil):
    assert _yazi_adi(stil.lookup("TNotebook.Tab", "font")) == f"{tema.AILE} 12 bold"


def test_tablo_satiri_yaziyi_kesmez(stil, tk_kok):
    """Satır yüksekliği yazının satır boşluğundan büyük olmalı; yoksa harflerin altı kesilir."""
    yuksek = int(stil.lookup("Treeview", "rowheight"))
    assert yuksek >= tkfont.Font(root=tk_kok, font=tema.YAZI).metrics("linespace") + 6
    assert yuksek == tema.satir_yuksekligi()


def test_tablo_basligi_kalin(stil):
    assert "bold" in str(stil.lookup("Treeview.Heading", "font"))


def test_dpi_farkindaligi_hata_vermez():
    """Pencere açıkken ya da Windows dışında sessizce geçer; program buna bağlı değil."""
    tema.dpi_farkindaligini_ac()


# ---------- Azami genişlik ----------

def _yan_bosluk(cerceve) -> int:
    return int(str(cerceve.cget("padding")[0]))


def _yan_bosluk_olc(kok, pencere_genisligi: int) -> int:
    cerceve = ttk.Frame(kok)
    try:
        tema.genisligi_sinirla(cerceve, azami=1400, kenar=10)
        cerceve.pack(fill="both", expand=True)
        kok.geometry(f"{pencere_genisligi}x300")
        kok.update()
        return _yan_bosluk(cerceve)
    finally:
        cerceve.destroy()


def test_dar_pencerede_icerik_tam_genisligi_kullanir(gorunur_kok):
    assert _yan_bosluk_olc(gorunur_kok, 900) == 10       # sadece normal kenar payı


def test_genis_pencerede_icerik_ortalanir(gorunur_kok):
    assert _yan_bosluk_olc(gorunur_kok, 2000) == 300     # (2000 - 1400) / 2


def test_genislik_sinirinin_varsayilani_1400():
    assert tema.AZAMI_GENISLIK == 1400


# ---------- Ayarlar sekmesi düzeni ----------

@pytest.fixture
def ayarlar(tk_kok):
    sekme = AyarSekmesi(tk_kok, dict(TEMEL), YONETICI)
    yield sekme
    sekme.destroy()


def _cerceveler(sekme) -> dict:
    """Ayarlar sekmesindeki bölümler; form kaydırılabilir alanın (govde) içindedir."""
    return {c.cget("text"): c for c in sekme.govde.winfo_children()
            if isinstance(c, ttk.LabelFrame)}


def test_genel_ayarlar_kendi_cercevesinde(ayarlar):
    """Sol taraf da çerçeve içinde olsun ki iki bölüm dengeli görünsün."""
    assert "Genel ayarlar" in _cerceveler(ayarlar)


def test_iki_bolum_yan_yana_ve_esit(ayarlar):
    genel = _cerceveler(ayarlar)["Genel ayarlar"]
    assert genel.grid_info()["column"] == 0
    assert ayarlar.eposta.grid_info()["column"] == 1
    assert genel.grid_info()["row"] == ayarlar.eposta.grid_info()["row"] == 0
    for sutun in (0, 1):
        ayar = ayarlar.govde.grid_columnconfigure(sutun)
        assert ayar["weight"] == 1                      # ikisi de genişlikle büyür
        assert ayar["uniform"]                          # ve aynı genişlikte kalır
    assert (ayarlar.govde.grid_columnconfigure(0)["uniform"]
            == ayarlar.govde.grid_columnconfigure(1)["uniform"])


def test_iki_bolum_de_yuksekligi_doldurur(ayarlar):
    genel = _cerceveler(ayarlar)["Genel ayarlar"]
    assert genel.grid_info()["sticky"] == "nesw"
    assert ayarlar.eposta.grid_info()["sticky"] == "nesw"
    assert ayarlar.govde.grid_rowconfigure(0)["weight"] == 1


def _kaydet_dugmesi(sekme):
    return next(d for c in sekme.winfo_children() if type(c) is ttk.Frame
                for d in c.winfo_children()
                if isinstance(d, ttk.Button) and d.cget("text") == "Kaydet")


def test_kaydet_dugmesi_kaydirmanin_disinda_altta_kalir(ayarlar):
    alt = _kaydet_dugmesi(ayarlar).master
    assert alt.master is ayarlar                        # kaydırılan gövdenin içinde değil
    assert alt.grid_info()["row"] == 1                  # iki bölümün altında


def test_giris_kutulari_genislikle_buyur(ayarlar):
    genel = _cerceveler(ayarlar)["Genel ayarlar"]
    kutular = [c for c in genel.winfo_children()
               if c.winfo_class() in ("TEntry", "TCombobox")]
    assert kutular
    for kutu in kutular:
        assert kutu.grid_info()["sticky"] == "ew", kutu.cget("textvariable")
    assert genel.grid_columnconfigure(1)["weight"] == 1


def test_smtp_kutulari_da_genislikle_buyur(ayarlar):
    kutular = [c for c in ayarlar.eposta.winfo_children()
               if c.winfo_class() in ("TEntry", "TCombobox")]
    assert len(kutular) == 5
    for kutu in kutular:
        assert kutu.grid_info()["sticky"] == "ew"
    assert ayarlar.eposta.grid_columnconfigure(1)["weight"] == 1


def test_pencere_genisleyince_kutular_gercekten_genisler(gorunur_kok):
    """Sayısal kontrol: pencere genişleyince giriş kutusu da belirgin genişler."""
    sekme = AyarSekmesi(gorunur_kok, dict(TEMEL), YONETICI)
    try:
        sekme.pack(fill="both", expand=True)
        genel = _cerceveler(sekme)["Genel ayarlar"]
        kutu = next(c for c in genel.winfo_children() if c.winfo_class() == "TEntry")
        gorunur_kok.geometry("800x600")
        gorunur_kok.update()
        dar = kutu.winfo_width()
        gorunur_kok.geometry("1600x600")
        gorunur_kok.update()
        assert kutu.winfo_width() > dar + 100
    finally:
        sekme.destroy()


# ---------- Ana pencere ----------

@pytest.fixture
def uygulama(monkeypatch):
    import arayuz
    monkeypatch.setattr(arayuz, "ayarlari_oku", lambda: dict(TEMEL))
    monkeypatch.setattr(arayuz, "durumlari_oku", lambda: {})
    from conftest import tk_ac
    uyg = tk_ac(lambda: arayuz.Uygulama(YONETICI, LOG))
    uyg.withdraw()
    yield uyg
    if not uyg.cikis_yapildi:
        uyg.destroy()


def test_pencerenin_en_kucuk_boyutu_var(uygulama):
    assert tuple(uygulama.minsize()) == tema.olcekli(*tema.EN_KUCUK_PENCERE, kok=uygulama)


def test_en_kucuk_boyut_ekran_olcegiyle_buyur():
    """%150 ekranda yazılar 1,5 kat büyür; pencere de 1,5 kat büyümezse içerik sığmaz."""
    assert tema.olcekli(1000, 600) == (round(1000 * tema.ekran_olcegi()),
                                       round(600 * tema.ekran_olcegi()))
    assert tema.ekran_olcegi() >= 1.0


def test_butun_sekmelerde_genislik_siniri_var(uygulama):
    defter = next(c for c in uygulama.winfo_children() if c.winfo_class() == "TNotebook")
    sekmeler = [uygulama.nametowidget(ad) for ad in defter.tabs()]
    assert [defter.tab(s, "text") for s in defter.tabs()] == [
        "Kameralar", "Kayıtlar", "Loglar", "Ayarlar", "Kullanıcılar"]
    for sekme in sekmeler:
        assert hasattr(sekme, "_son_yan"), defter.tab(sekme, "text")


def test_sekmeler_pencereyle_birlikte_buyur(uygulama):
    defter = next(c for c in uygulama.winfo_children() if c.winfo_class() == "TNotebook")
    assert defter.pack_info()["expand"] in (1, "1", True)
    assert defter.pack_info()["fill"] == "both"


# ---------- Kaydırma (uzun form küçük ekranda kesilmesin) ----------

def test_ayarlar_formu_kaydirilabilir(ayarlar):
    kaydirma = ayarlar.govde.master.master
    assert isinstance(kaydirma, tema.DikeyKaydirma)
    assert kaydirma.grid_info()["sticky"] == "nesw"


def test_kaydirma_cubugu_sigan_icerikte_gizli(tk_kok):
    alan = tema.DikeyKaydirma(tk_kok)
    try:
        ttk.Label(alan.govde, text="kısa").pack()
        alan.pack(fill="both", expand=True)
        tk_kok.update()
        assert not alan.cubuk.winfo_ismapped()
    finally:
        alan.destroy()


def test_kaydirma_cubugu_sigmayan_icerikte_gorunur(gorunur_kok):
    alan = tema.DikeyKaydirma(gorunur_kok)
    try:
        for i in range(60):
            ttk.Label(alan.govde, text=f"satır {i}").pack()
        alan.pack(fill="both", expand=True)
        gorunur_kok.geometry("500x300")
        gorunur_kok.update()
        assert alan.cubuk.winfo_ismapped()
    finally:
        alan.destroy()


def test_en_kucuk_boyutta_ayarlarin_tamami_okunabilir(gorunur_kok):
    """Pencere en küçükken bile her alana kaydırarak ulaşılır: içerik kesilip kaybolmaz."""
    sekme = AyarSekmesi(gorunur_kok, dict(TEMEL), YONETICI)
    try:
        sekme.pack(fill="both", expand=True)
        gorunur_kok.geometry("%dx%d" % tema.olcekli(*tema.EN_KUCUK_PENCERE, kok=gorunur_kok))
        gorunur_kok.update()
        kaydirma = sekme.govde.master.master
        kaydirma.tuval.yview_moveto(1.0)                         # sonuna kadar kaydır
        gorunur_kok.update()
        assert kaydirma.tuval.yview()[1] == 1.0                  # en alt satıra ulaşılabiliyor

        # Formun en altındaki alan (telefon portu) gerçekten görünür hale geliyor
        port_kutusu = next(c for c in _cerceveler(sekme)["Genel ayarlar"].winfo_children()
                           if type(c) is ttk.Frame).winfo_children()[-1]
        alt_kenar = port_kutusu.winfo_rooty() + port_kutusu.winfo_height()
        assert alt_kenar <= kaydirma.tuval.winfo_rooty() + kaydirma.tuval.winfo_height()
    finally:
        sekme.destroy()


# ---------- Tablo sütunları ----------

def test_sutun_basligi_sigacak_kadar_genis(stil):
    """Sütun genişlikleri küçük yazıya göre yazılmıştı; başlık kesilmemeli."""
    assert tema.sutun_genisligi("Gönderim zamanı", 140) > 140      # uzun başlık yer açar
    assert tema.sutun_genisligi("Ad", 160) == 160                  # kısa başlık daralmaz


def test_tablolarin_sutunlari_basligi_kesmiyor(uygulama, stil):
    import tkinter.font as tkf
    kalin = tkf.Font(root=uygulama, font=(tema.AILE, tema.NORMAL, "bold"))
    defter = next(c for c in uygulama.winfo_children() if c.winfo_class() == "TNotebook")
    tablolar = []

    def gez(w):
        for c in w.winfo_children():
            if isinstance(c, ttk.Treeview):
                tablolar.append(c)
            gez(c)

    for ad in defter.tabs():
        gez(uygulama.nametowidget(ad))
    assert len(tablolar) >= 4                                      # 4 sekmede tablo var
    for tablo in tablolar:
        for sutun in tablo.cget("columns"):
            baslik = tablo.heading(sutun, "text")
            assert int(tablo.column(sutun, "width")) >= kalin.measure(baslik), (tablo, baslik)


def test_zaman_sutunu_tam_zamani_sigdirir(stil):
    """Başlık kısa ama değer uzun: '08.10.2026 10:00:00' kesilmemeli."""
    import tkinter.font as tkf
    dar = tema.sutun_genisligi("Zaman", 140)
    genis = tema.sutun_genisligi("Zaman", 140, tema.ZAMAN_ORNEGI)
    assert genis > dar
    assert genis >= tkf.Font(font=tema.YAZI).measure(tema.ZAMAN_ORNEGI)


def test_tablolardaki_zamanlar_kesilmiyor(uygulama, stil):
    import tkinter.font as tkf
    normal = tkf.Font(root=uygulama, font=tema.YAZI)
    defter = next(c for c in uygulama.winfo_children() if c.winfo_class() == "TNotebook")
    tablolar = []

    def gez(w):
        for c in w.winfo_children():
            if isinstance(c, ttk.Treeview):
                tablolar.append(c)
            gez(c)

    for ad in defter.tabs():
        gez(uygulama.nametowidget(ad))
    zamanli = 0
    for tablo in tablolar:
        for sutun in tablo.cget("columns"):
            if "zaman" in tablo.heading(sutun, "text").lower() or sutun == "son":
                zamanli += 1
                assert int(tablo.column(sutun, "width")) >= normal.measure(tema.ZAMAN_ORNEGI)
    assert zamanli >= 4


def test_sarma_genisligi_yaziyla_birlikte_buyur(stil):
    """Yazı büyüyünce açıklamalar gereksiz yere çok satıra bölünmesin."""
    assert tema.sarma_genisligi(300) == round(300 * tema.ekran_olcegi())
    assert tema.sarma_genisligi(300) >= 300
