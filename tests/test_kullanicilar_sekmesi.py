"""Kullanıcılar sekmesi: sütun sırası ve satır değerleri."""
import kullanicilar as ku
import kullanicilar_sekmesi as ks
from kullanicilar_sekmesi import KullanicilarSekmesi

BEKLENEN_SIRA = ["ad", "rol", "eposta", "durum", "son"]
BEKLENEN_BASLIKLAR = ["Ad", "Rol", "E-posta", "Durum", "Son giriş"]

KULLANICI = {"eposta": "ayse@akgun.com.tr", "ad": "Ayşe Yılmaz", "yonetici": False,
             "dogrulandi": 1, "kilit_bitis": None, "son_giris": None}


def test_sutun_sirasi():
    assert [ad for ad, _, _ in ks.SUTUNLAR] == BEKLENEN_SIRA
    assert [baslik for _, baslik, _ in ks.SUTUNLAR] == BEKLENEN_BASLIKLAR


def test_satir_degerleri_sutun_sirasiyla_ayni():
    degerler = ks.satir_degerleri(KULLANICI, "2026-10-07 12:00:00")
    assert degerler[0] == "Ayşe Yılmaz"            # Ad
    assert degerler[1] == "Kullanıcı"              # Rol
    assert degerler[2] == "ayse@akgun.com.tr"      # E-posta
    assert degerler[3] == "Aktif"                  # Durum
    assert len(degerler) == len(ks.SUTUNLAR)


def test_yonetici_rolu_yazilir():
    assert ks.satir_degerleri({**KULLANICI, "yonetici": True}, "2026-10-07 12:00:00")[1] == "Yönetici"


def test_dogrulanmamis_ve_kilitli_durumlari():
    simdi = "2026-10-07 12:00:00"
    assert ks.satir_degerleri({**KULLANICI, "dogrulandi": 0}, simdi)[3] == "Doğrulanmadı"
    assert ks.satir_degerleri({**KULLANICI, "kilit_bitis": "2026-10-07 13:00:00"}, simdi)[3] == "Kilitli"


def test_listede_basliklar_dogru_sirada(tk_kok):
    """Gerçek Treeview'da da sıra aynı olmalı."""
    ku.ilk_yoneticiyi_olustur("admin@akgun.com.tr", "Yönetici", "GizliSifre1", "GizliSifre1")
    sekme = KullanicilarSekmesi(tk_kok, {"eposta": "admin@akgun.com.tr", "yonetici": True}, None)
    try:
        assert list(sekme.liste.cget("columns")) == BEKLENEN_SIRA
        assert [sekme.liste.heading(ad)["text"] for ad in BEKLENEN_SIRA] == BEKLENEN_BASLIKLAR
        (satir,) = sekme.liste.get_children()
        degerler = sekme.liste.item(satir)["values"]
        assert degerler[0] == "Yönetici"                 # Ad sütunu (hesabın adı)
        assert degerler[2] == "admin@akgun.com.tr"       # E-posta sütunu
    finally:
        sekme.destroy()
