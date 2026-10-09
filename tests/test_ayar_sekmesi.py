import pytest

from ayar_sekmesi import AyarSekmesi

TEMEL = {"tesis_kodu": "H01", "api_url": "", "api_key": "", "gonderim_araligi_sn": 60,
         "ikinci_cekim_gecikme_sn": 5, "format": "avif", "kalite": 85, "saklama_gun": 7,
         "gonderilince_sil": True, "kameralar": []}
# Ayarlar sekmesi yalnızca yöneticide açılır; doğrulama da yönetici oturumu ister
YONETICI = {"eposta": "admin@akgun.com.tr", "ad": "Yönetici", "yonetici": True}


@pytest.fixture
def kok(tk_kok):
    return tk_kok


def test_eski_ayar_dosyasinda_kayit_saklama_varsayilan_90_gorunur(kok):
    sekme = AyarSekmesi(kok, dict(TEMEL), YONETICI)
    assert sekme.degerler["kayit_saklama_gun"].get() == "90"
    yeni, hata = sekme._dogrula()
    assert hata is None
    assert yeni["kayit_saklama_gun"] == 90


@pytest.mark.parametrize("deger", ["0", "3651", "abc"])
def test_kayit_saklama_gecersiz_deger_reddedilir(kok, deger):
    sekme = AyarSekmesi(kok, {**TEMEL, "kayit_saklama_gun": 90}, YONETICI)
    sekme.degerler["kayit_saklama_gun"].set(deger)
    yeni, hata = sekme._dogrula()
    assert yeni is None
    assert "Gönderim kaydı saklama" in hata


# ---------- Bilgisayar açılınca motoru başlat ----------

def test_acilista_baslat_kutusu_mevcut_durumu_gosterir(kok, monkeypatch):
    import motor_denetim
    monkeypatch.setattr(motor_denetim, "acilista_basliyor_mu", lambda: True)
    assert AyarSekmesi(kok, dict(TEMEL), YONETICI).acilista.get() is True
    monkeypatch.setattr(motor_denetim, "acilista_basliyor_mu", lambda: False)
    assert AyarSekmesi(kok, dict(TEMEL), YONETICI).acilista.get() is False


def test_kaydedince_kisayol_olusturulur(kok, monkeypatch):
    import ayar_sekmesi
    import motor_denetim
    monkeypatch.setattr(ayar_sekmesi, "ayarlari_yaz", lambda *a, **k: None)
    monkeypatch.setattr(ayar_sekmesi.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(motor_denetim, "acilista_basliyor_mu", lambda: False)
    istekler = []
    monkeypatch.setattr(motor_denetim, "acilista_baslat",
                        lambda acik, log=None: istekler.append(acik) or True)
    sekme = AyarSekmesi(kok, dict(TEMEL), YONETICI)
    sekme.acilista.set(True)
    sekme._kaydet()
    assert istekler == [True]           # kapalıdan açığa geçti


def test_degismediyse_kisayola_dokunulmaz(kok, monkeypatch):
    """Her kaydetmede kısayolu yeniden yazmak gereksiz."""
    import ayar_sekmesi
    import motor_denetim
    monkeypatch.setattr(ayar_sekmesi, "ayarlari_yaz", lambda *a, **k: None)
    monkeypatch.setattr(ayar_sekmesi.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(motor_denetim, "acilista_basliyor_mu", lambda: True)
    monkeypatch.setattr(motor_denetim, "acilista_baslat",
                        lambda acik, log=None: pytest.fail("dokunulmamalıydı"))
    sekme = AyarSekmesi(kok, dict(TEMEL), YONETICI)
    sekme.acilista.set(True)            # zaten açık
    sekme._kaydet()


def test_kisayol_yazilamazsa_diger_ayarlar_yine_kaydedilir(kok, monkeypatch):
    import ayar_sekmesi
    import motor_denetim
    yazilan = []
    monkeypatch.setattr(ayar_sekmesi, "ayarlari_yaz", lambda a, *r, **k: yazilan.append(a))
    monkeypatch.setattr(ayar_sekmesi.messagebox, "showinfo", lambda *a, **k: None)
    uyarilar = []
    monkeypatch.setattr(ayar_sekmesi.messagebox, "showwarning",
                        lambda *a, **k: uyarilar.append(a))
    monkeypatch.setattr(motor_denetim, "acilista_basliyor_mu", lambda: False)
    monkeypatch.setattr(motor_denetim, "acilista_baslat", lambda acik, log=None: False)
    sekme = AyarSekmesi(kok, dict(TEMEL), YONETICI)
    sekme.acilista.set(True)
    sekme._kaydet()
    assert yazilan                      # ayarlar yine de kaydedildi
    assert uyarilar                     # ama kullanıcı uyarıldı


def test_goruntu_formati_secenekleri(kok):
    """jpg ve jpeg aynı biçimdir; M4 'jpeg' beklediği için ikisi de seçilebilmeli."""
    import ayar_sekmesi
    sekme = AyarSekmesi(kok, dict(TEMEL), YONETICI)
    from tkinter import ttk
    genel = next(c for c in sekme.govde.winfo_children() if isinstance(c, ttk.LabelFrame))
    kutu = next(c for c in genel.winfo_children()
                if c.winfo_class() == "TCombobox"
                and str(c.cget("textvariable")) == str(sekme.degerler["format"]))
    assert list(kutu.cget("values")) == ["avif", "jpg", "jpeg"] == ayar_sekmesi.FORMATLAR


def test_jpeg_secilince_kaydedilir(kok, monkeypatch):
    import ayar_sekmesi
    yazilan = []
    monkeypatch.setattr(ayar_sekmesi, "ayarlari_yaz", lambda a, *r, **k: yazilan.append(dict(a)))
    monkeypatch.setattr(ayar_sekmesi.messagebox, "showinfo", lambda *a, **k: None)
    sekme = AyarSekmesi(kok, dict(TEMEL), YONETICI)
    sekme.degerler["format"].set("jpeg")
    sekme._kaydet()
    assert yazilan and yazilan[0]["format"] == "jpeg"
