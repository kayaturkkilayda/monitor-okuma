"""Yönetici ayrımı: Ayarlar sekmesi, Kullanıcılar sekmesi, ana penceredeki oturum."""
import logging

import pytest

import ayar_sekmesi
import kullanicilar as ku
import kullanicilar_sekmesi as kus
from veritabani import baglan

TEMEL = {"tesis_kodu": "H01", "api_url": "", "api_key": "EskiAnahtar", "gonderim_araligi_sn": 60,
         "ikinci_cekim_gecikme_sn": 5, "format": "avif", "kalite": 85, "saklama_gun": 7,
         "gonderilince_sil": True, "kameralar": [],
         "izin_verilen_alan_adi": ["akgun.com.tr"], "smtp": {}}
YONETICI = {"eposta": "admin@akgun.com.tr", "ad": "Yönetici", "yonetici": True}
KULLANICI = {"eposta": "ayse@akgun.com.tr", "ad": "Ayşe", "yonetici": False}
LOG = logging.getLogger("test-yetki")


def olaylar():
    with baglan() as db:
        return [dict(s) for s in db.execute("SELECT kaynak, mesaj FROM olaylar ORDER BY id")]


def kapali_mi(widget) -> bool:
    return "disabled" in widget.state()


def alanlar(sekme):
    import tkinter.ttk as ttk
    sonuc = []

    def gez(w):
        for c in w.winfo_children():
            if isinstance(c, (ttk.Entry, ttk.Button, ttk.Checkbutton)):
                sonuc.append(c)
            gez(c)
    gez(sekme)
    return sonuc


# ---------- Ayarlar sekmesi ----------

def test_yonetici_olmayan_ayarlari_degistiremez(tk_kok, monkeypatch):
    """Sekme normal kullanıcıya hiç gösterilmez; gösterilse bile hiçbir yoldan kaydedemez."""
    yazilan = []
    monkeypatch.setattr(ayar_sekmesi, "ayarlari_yaz", yazilan.append)
    monkeypatch.setattr(ayar_sekmesi.messagebox, "showerror", lambda *a: None)
    sekme = ayar_sekmesi.AyarSekmesi(tk_kok, dict(TEMEL), KULLANICI, LOG)
    try:
        assert alanlar(sekme) and all(kapali_mi(a) for a in alanlar(sekme))
        yeni, hata = sekme._dogrula()                   # fonksiyon seviyesinde yetki kontrolü
        assert yeni is None and hata == ayar_sekmesi.YETKI_YOK
        sekme._kaydet()                                 # düğmeyi atlatsa bile
        assert yazilan == []
    finally:
        sekme.destroy()


def test_yonetici_kaydeder_ve_olaylara_kim_ne_degistirdi_yazilir(tk_kok, monkeypatch):
    yazilan = []
    monkeypatch.setattr(ayar_sekmesi, "ayarlari_yaz", lambda a: yazilan.append(dict(a)))
    monkeypatch.setattr(ayar_sekmesi.messagebox, "showinfo", lambda *a: None)
    sekme = ayar_sekmesi.AyarSekmesi(tk_kok, dict(TEMEL), YONETICI, LOG)
    try:
        assert not any(kapali_mi(a) for a in alanlar(sekme))
        sekme.degerler["api_key"].set("YeniGizliAnahtar")
        sekme.degerler["kalite"].set("70")
        sekme._kaydet()
        assert yazilan[-1]["api_key"] == "YeniGizliAnahtar"
        (o,) = olaylar()
        assert o["mesaj"].startswith("Ayarlar değiştirildi (değişen: api_key, kalite")
        assert o["mesaj"].endswith("— admin@akgun.com.tr")
        assert "YeniGizliAnahtar" not in o["mesaj"] and "EskiAnahtar" not in o["mesaj"]
    finally:
        sekme.destroy()


# ---------- İzin verilen alan adları (dinamik liste) ----------

@pytest.mark.parametrize("girilenler,beklenen,hata", [
    ([" @Akgun.Com.TR "], ["akgun.com.tr"], None),                      # trim + küçük harf + @
    ([], [], None),                                                      # boş liste: whitelist yok
    (["", "   "], [], None),                                             # boş satırlar atılır
    (["akgun.com.tr", "HASTANE1.com.tr"], ["akgun.com.tr", "hastane1.com.tr"], None),
    (["akgun.com.tr", "akgun.com.tr"], ["akgun.com.tr"], None),          # tekrar temizlenir
    (["akgun"], None, "akgun.com.tr"),                                   # geçersiz: TLD yok
    (["ayse@akgun.com.tr"], None, "geçerli bir alan adı değil"),         # geçersiz: yerel kısım var
    (["akgun.com.tr", "bozuk alan"], None, "bozuk alan"),                # biri bozuksa reddedilir
])
def test_izin_verilen_alan_adlari_dogrulamasi(tk_kok, girilenler, beklenen, hata):
    sekme = ayar_sekmesi.AyarSekmesi(tk_kok, dict(TEMEL), YONETICI, LOG)
    try:
        for kayit in list(sekme.alan_adlari.satirlar):                    # ayardan gelenleri boşalt
            sekme.alan_adlari.sil(kayit)
        for girilen in girilenler:
            sekme.alan_adlari.ekle(girilen)
        yeni, mesaj = sekme._dogrula()
        if hata:
            assert yeni is None and hata in mesaj
        else:
            assert yeni["izin_verilen_alan_adi"] == beklenen
    finally:
        sekme.destroy()


def test_alan_adi_satirlari_eklenip_silinebilir(tk_kok):
    sekme = ayar_sekmesi.AyarSekmesi(tk_kok, dict(TEMEL), YONETICI, LOG)
    try:
        liste = sekme.alan_adlari
        assert liste.degerler() == ["akgun.com.tr"]                       # ayardan geldi
        liste.ekle("hastane1.com.tr")
        assert liste.degerler() == ["akgun.com.tr", "hastane1.com.tr"]
        liste.sil(liste.satirlar[0])
        assert liste.degerler() == ["hastane1.com.tr"]
        liste.sil(liste.satirlar[0])
        assert liste.degerler() == [] and liste.BOS_UYARI in liste.bilgi.cget("text")
    finally:
        sekme.destroy()


def test_eski_tek_string_ayar_listede_gorunur(tk_kok):
    """Eski config: "izin_verilen_alan_adi": "akgun.com.tr" → tek satırlık liste."""
    sekme = ayar_sekmesi.AyarSekmesi(
        tk_kok, {**TEMEL, "izin_verilen_alan_adi": "akgun.com.tr"}, YONETICI, LOG)
    try:
        assert sekme.alan_adlari.degerler() == ["akgun.com.tr"]
        yeni, hata = sekme._dogrula()
        assert hata is None and yeni["izin_verilen_alan_adi"] == ["akgun.com.tr"]
    finally:
        sekme.destroy()


# ---------- Kullanıcılar sekmesi ----------

def test_kullanicilar_listesi_ve_yonetici_yapma(tk_kok, monkeypatch):
    ku.ilk_yoneticiyi_olustur("admin@akgun.com.tr", "Yönetici", "GizliSifre1")
    _, kod = ku.kayit_baslat("ayse@akgun.com.tr", "Ayşe", "GizliSifre1", None, "akgun.com.tr")
    ku.kayit_dogrula("ayse@akgun.com.tr", kod)
    monkeypatch.setattr(kus.messagebox, "askyesno", lambda *a, **k: True)
    sekme = kus.KullanicilarSekmesi(tk_kok, YONETICI, LOG)
    try:
        assert sekme.liste.item("ayse@akgun.com.tr", "values")[2] == "Kullanıcı"
        sekme.liste.selection_set("ayse@akgun.com.tr")
        sekme._yonetici_yap()
        assert sekme.liste.item("ayse@akgun.com.tr", "values")[2] == "Yönetici"
        assert olaylar()[-1]["mesaj"] == "ayse@akgun.com.tr yönetici yapıldı — admin@akgun.com.tr"
        assert ku.giris("ayse@akgun.com.tr", "GizliSifre1")["yonetici"]
    finally:
        sekme.destroy()


def test_kullanici_durumlari():
    simdi = "2026-10-05 10:00:00"
    temel = {"eposta": "a@b.co", "ad": "A", "yonetici": False, "son_giris": None, "kilit_bitis": None}
    assert kus.satir_degerleri({**temel, "dogrulandi": False}, simdi)[3] == "Doğrulanmadı"
    assert kus.satir_degerleri({**temel, "dogrulandi": True, "kilit_bitis": "2026-10-05 10:03:00"}, simdi)[3] == "Kilitli"
    assert kus.satir_degerleri({**temel, "dogrulandi": True, "kilit_bitis": "2026-10-05 09:00:00"}, simdi)[3] == "Aktif"


# ---------- Ana pencere ----------

@pytest.fixture
def uygulama(monkeypatch):
    import arayuz
    monkeypatch.setattr(arayuz, "ayarlari_oku", lambda: dict(TEMEL))
    monkeypatch.setattr(arayuz, "durumlari_oku", lambda: {})
    olusturulan = []

    def kur(oturum):
        from conftest import tk_ac
        uyg = tk_ac(lambda: arayuz.Uygulama(oturum, LOG))
        uyg.withdraw()
        olusturulan.append(uyg)
        return uyg

    yield kur
    for uyg in olusturulan:
        if not uyg.cikis_yapildi:
            uyg.destroy()


def _sekme_adlari(uyg):
    defter = next(c for c in uyg.winfo_children() if c.winfo_class() == "TNotebook")
    return [defter.tab(s, "text") for s in defter.tabs()]


def _ust_yazi(uyg):
    ust = uyg.winfo_children()[0]
    return [c.cget("text") for c in ust.winfo_children()]


def test_ana_pencerede_kullanici_adi_ve_cikis(uygulama):
    uyg = uygulama(KULLANICI)
    assert _ust_yazi(uyg) == ["Çıkış", "Ayşe (ayse@akgun.com.tr)"]
    # Yalnızca yönetici görür: SMTP, M4/API anahtarı ve izin verilen alan adları Ayarlar'da
    assert _sekme_adlari(uyg) == ["Kameralar", "Kayıtlar", "Loglar"]
    assert not hasattr(uyg, "ayar_sekmesi") and not hasattr(uyg, "kullanicilar_sekmesi")


def test_yonetici_ayarlar_ve_kullanicilar_sekmelerini_gorur(uygulama):
    uyg = uygulama(YONETICI)
    assert _ust_yazi(uyg)[1] == "Yönetici (admin@akgun.com.tr) · Yönetici"
    assert _sekme_adlari(uyg) == ["Kameralar", "Kayıtlar", "Loglar", "Ayarlar", "Kullanıcılar"]


def test_cikis_olaylara_yazilir(uygulama):
    uyg = uygulama(KULLANICI)
    uyg._cikis()
    assert uyg.cikis_yapildi
    assert olaylar()[-1]["mesaj"] == "Kullanıcı çıkış yaptı: ayse@akgun.com.tr"


def test_cikista_bekleyen_yenileme_iptal_edilir(uygulama):
    uyg = uygulama(KULLANICI)
    bekleyen = uyg._zamanlayici
    assert bekleyen in uyg.tk.call("after", "info")
    iptal_edilen = []
    asil_iptal = uyg.after_cancel
    uyg.after_cancel = lambda kimlik: (iptal_edilen.append(kimlik), asil_iptal(kimlik))
    uyg._cikis()
    assert iptal_edilen == [bekleyen]
