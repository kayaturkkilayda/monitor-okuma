from datetime import datetime, timedelta

import pytest

import kullanicilar as ku
from kullanicilar import KullaniciHatasi
from veritabani import baglan

ALAN = "akgun.com.tr"
SIMDI = datetime(2026, 10, 5, 9, 0, 0)


def satir(tablo, eposta):
    with baglan() as db:
        s = db.execute(f"SELECT * FROM {tablo} WHERE eposta = ?", (eposta,)).fetchone()
    return dict(s) if s else None


def kayitli(eposta="ayse@akgun.com.tr", sifre="GizliSifre1"):
    _, kod = ku.kayit_baslat(eposta, "Ayşe", sifre, sifre, ALAN, SIMDI)
    return ku.kayit_dogrula(eposta, kod, SIMDI)


# ---------- Hash ----------

def test_sifre_hash_tuzlu_ve_dogrulanabilir():
    h1, h2 = ku.hashle("GizliSifre1"), ku.hashle("GizliSifre1")
    assert h1 != h2                                         # her seferinde farklı tuz
    assert h1.startswith("scrypt$") and "GizliSifre1" not in h1
    assert ku.hash_dogru_mu("GizliSifre1", h1) and not ku.hash_dogru_mu("Yanlis123", h1)


def test_bozuk_hash_hata_vermez():
    assert not ku.hash_dogru_mu("x", "bozuk")


# ---------- İlk yönetici ----------

def test_ilk_yonetici_kodsuz_ve_yonetici_olarak_acilir():
    assert not ku.kullanici_var_mi()
    k = ku.ilk_yoneticiyi_olustur("Admin@Akgun.com.tr", "Yönetici", "GizliSifre1", "GizliSifre1")
    assert k["eposta"] == "admin@akgun.com.tr" and k["yonetici"] and k["dogrulandi"]
    assert "sifre_hash" not in k
    assert ku.kullanici_var_mi()
    assert ku.giris("admin@akgun.com.tr", "GizliSifre1")["yonetici"]


def test_ikinci_ilk_yonetici_olusturulamaz():
    ku.ilk_yoneticiyi_olustur("admin@akgun.com.tr", "Yönetici", "GizliSifre1")
    with pytest.raises(KullaniciHatasi, match="zaten"):
        ku.ilk_yoneticiyi_olustur("baska@akgun.com.tr", "Başka", "GizliSifre1")


def test_ilk_yonetici_alan_adi_kuralina_takilmaz():
    """Henüz izin verilen alan adı ayarı yokken de oluşturulabilmeli."""
    assert ku.ilk_yoneticiyi_olustur("bt@hastane.local", "BT", "GizliSifre1")["yonetici"]


# ---------- Kayıt ve doğrulama ----------

def test_kayit_kod_uretir_hesap_dogrulanmamis_baslar():
    eposta, kod = ku.kayit_baslat("Ayse@Akgun.com.tr", "Ayşe", "GizliSifre1", "GizliSifre1", ALAN, SIMDI)
    assert eposta == "ayse@akgun.com.tr"
    assert len(kod) == 6 and kod.isdigit()
    k = satir("kullanicilar", eposta)
    assert k["dogrulandi"] == 0 and k["yonetici"] == 0
    assert k["sifre_hash"].startswith("scrypt$") and "GizliSifre1" not in k["sifre_hash"]
    kod_satiri = satir("dogrulama_kodlari", eposta)
    assert kod_satiri["amac"] == "kayit" and kod not in kod_satiri["kod_hash"]   # kod hash'li
    assert kod_satiri["son_kullanma"] == "2026-10-05 09:10:00"                   # 10 dakika


def test_dogru_kodla_hesap_acilir():
    k = kayitli()
    assert k["dogrulandi"] and not k["yonetici"]
    assert satir("dogrulama_kodlari", "ayse@akgun.com.tr") is None               # kod tek kullanımlık
    assert ku.giris("ayse@akgun.com.tr", "GizliSifre1")["ad"] == "Ayşe"


def test_dogrulanmamis_hesap_giris_yapamaz():
    ku.kayit_baslat("ayse@akgun.com.tr", "Ayşe", "GizliSifre1", "GizliSifre1", ALAN, SIMDI)
    with pytest.raises(KullaniciHatasi, match="doğrulanmadı"):
        ku.giris("ayse@akgun.com.tr", "GizliSifre1")


def test_yanlis_kod_ve_kalan_deneme():
    eposta, kod = ku.kayit_baslat("ayse@akgun.com.tr", "Ayşe", "GizliSifre1", "GizliSifre1", ALAN, SIMDI)
    yanlis = "000000" if kod != "000000" else "111111"
    with pytest.raises(KullaniciHatasi, match="Kalan deneme: 4"):
        ku.kayit_dogrula(eposta, yanlis, SIMDI)
    assert satir("dogrulama_kodlari", eposta)["deneme"] == 1
    assert ku.kayit_dogrula(eposta, kod, SIMDI)["dogrulandi"]                   # doğru kod hâlâ geçerli


def test_bes_yanlis_kodda_kod_gecersiz_olur():
    eposta, kod = ku.kayit_baslat("ayse@akgun.com.tr", "Ayşe", "GizliSifre1", "GizliSifre1", ALAN, SIMDI)
    yanlis = "000000" if kod != "000000" else "111111"
    for _ in range(ku.KOD_EN_FAZLA_DENEME - 1):
        with pytest.raises(KullaniciHatasi, match="Kod hatalı"):
            ku.kayit_dogrula(eposta, yanlis, SIMDI)
    with pytest.raises(KullaniciHatasi, match="Çok fazla"):
        ku.kayit_dogrula(eposta, yanlis, SIMDI)
    with pytest.raises(KullaniciHatasi, match="yeni kod"):
        ku.kayit_dogrula(eposta, kod, SIMDI)                                     # doğru kod da artık geçmez


def test_suresi_dolmus_kod():
    eposta, kod = ku.kayit_baslat("ayse@akgun.com.tr", "Ayşe", "GizliSifre1", "GizliSifre1", ALAN, SIMDI)
    with pytest.raises(KullaniciHatasi, match="süresi doldu"):
        ku.kayit_dogrula(eposta, kod, SIMDI + timedelta(minutes=10, seconds=1))
    assert satir("kullanicilar", eposta)["dogrulandi"] == 0


def test_tam_on_dakikada_hala_gecerli():
    eposta, kod = ku.kayit_baslat("ayse@akgun.com.tr", "Ayşe", "GizliSifre1", "GizliSifre1", ALAN, SIMDI)
    assert ku.kayit_dogrula(eposta, kod, SIMDI + timedelta(minutes=10))["dogrulandi"]


def test_yeni_kod_eskisini_gecersiz_kilar():
    eposta, eski = ku.kayit_baslat("ayse@akgun.com.tr", "Ayşe", "GizliSifre1", "GizliSifre1", ALAN, SIMDI)
    _, yeni = ku.kayit_baslat("ayse@akgun.com.tr", "Ayşe", "GizliSifre1", "GizliSifre1", ALAN, SIMDI)
    if eski != yeni:
        with pytest.raises(KullaniciHatasi):
            ku.kayit_dogrula(eposta, eski, SIMDI)
    assert ku.kayit_dogrula(eposta, yeni, SIMDI)["dogrulandi"]


def test_dogrulanmis_hesapla_tekrar_kayit_olunamaz():
    kayitli()
    with pytest.raises(KullaniciHatasi, match="giriş yapın"):
        ku.kayit_baslat("ayse@akgun.com.tr", "Ayşe", "GizliSifre1", "GizliSifre1", ALAN, SIMDI)


# ---------- Alan adı ----------

def test_izin_verilmeyen_alan_adi_kayit_olamaz():
    with pytest.raises(KullaniciHatasi, match="@akgun.com.tr"):
        ku.kayit_baslat("ayse@gmail.com", "Ayşe", "GizliSifre1", "GizliSifre1", ALAN, SIMDI)
    with pytest.raises(KullaniciHatasi):
        ku.kayit_baslat("ayse@sahte-akgun.com.tr", "Ayşe", "GizliSifre1", "GizliSifre1", ALAN, SIMDI)
    with pytest.raises(KullaniciHatasi):
        ku.kayit_baslat("ayse@akgun.com.tr.kotu.com", "Ayşe", "GizliSifre1", "GizliSifre1", ALAN, SIMDI)
    assert satir("kullanicilar", "ayse@gmail.com") is None


@pytest.mark.parametrize("bos", [None, "", [], ["", "  "], "   "])
def test_alan_adi_listesi_bossa_her_gecerli_eposta_kayit_olabilir(bos):
    """Liste boşsa whitelist uygulanmaz: geçerli her adres kayıt olabilir."""
    assert ku.alan_adi_izinli_mi("test@gmail.com", bos)
    eposta, kod = ku.kayit_baslat("test@gmail.com", "Test", "GizliSifre1", "GizliSifre1", bos, SIMDI)
    assert ku.kayit_dogrula(eposta, kod, SIMDI)["eposta"] == "test@gmail.com"


def test_alan_adi_listesi_bos_olsa_bile_gecersiz_eposta_reddedilir():
    with pytest.raises(KullaniciHatasi, match="Geçerli bir e-posta"):
        ku.kayit_baslat("ayse@gmail", "Ayşe", "GizliSifre1", "GizliSifre1", [], SIMDI)


def test_tek_domain_listesi():
    assert ku.alan_adi_izinli_mi("ayse@akgun.com.tr", ["akgun.com.tr"])
    assert not ku.alan_adi_izinli_mi("ayse@gmail.com", ["akgun.com.tr"])


def test_birden_fazla_domain_listedekiler_kabul_digerleri_reddedilir():
    liste = ["akgun.com.tr", "hastane1.com.tr"]
    assert ku.alan_adi_izinli_mi("ayse@akgun.com.tr", liste)
    assert ku.alan_adi_izinli_mi("veli@hastane1.com.tr", liste)
    assert not ku.alan_adi_izinli_mi("ayse@gmail.com", liste)
    assert not ku.alan_adi_izinli_mi("ayse@sahte-hastane1.com.tr", liste)

    eposta, kod = ku.kayit_baslat("veli@hastane1.com.tr", "Veli", "GizliSifre1", "GizliSifre1",
                                  liste, SIMDI)
    assert ku.kayit_dogrula(eposta, kod, SIMDI)["eposta"] == "veli@hastane1.com.tr"
    with pytest.raises(KullaniciHatasi, match="@akgun.com.tr, @hastane1.com.tr"):
        ku.kayit_baslat("ayse@gmail.com", "Ayşe", "GizliSifre1", "GizliSifre1", liste, SIMDI)


def test_alan_adi_buyuk_kucuk_harf_ve_at_isareti():
    assert ku.alan_adi_izinli_mi("Ayse@AKGUN.com.tr", "@Akgun.Com.Tr")
    assert ku.alan_adi_izinli_mi("Ayse@AKGUN.com.tr", [" @AKGUN.COM.TR "])


def test_alan_adi_listesi_normallestirir():
    """trim + lowercase + baştaki @ kaldırılır; boşlar atılır, tekrarlar temizlenir."""
    assert ku.alan_adi_listesi([" @AKGUN.COM.TR ", "Hastane1.Com.TR", "", "  ",
                                "akgun.com.tr"]) == ["akgun.com.tr", "hastane1.com.tr"]
    assert ku.alan_adi_listesi(None) == []
    assert ku.alan_adi_listesi("") == []


def test_eski_tek_string_config_calisir():
    """Eski ayar dosyası ("izin_verilen_alan_adi": "akgun.com.tr") tek elemanlı liste gibi çalışır."""
    assert ku.alan_adi_listesi("akgun.com.tr") == ["akgun.com.tr"]
    assert ku.alan_adi_izinli_mi("ayse@akgun.com.tr", "akgun.com.tr")
    assert not ku.alan_adi_izinli_mi("ayse@gmail.com", "akgun.com.tr")
    eposta, kod = ku.kayit_baslat("ayse@akgun.com.tr", "Ayşe", "GizliSifre1", "GizliSifre1",
                                  "akgun.com.tr", SIMDI)
    assert ku.kayit_dogrula(eposta, kod, SIMDI)["dogrulandi"]


# ---------- Şifre kuralı ----------

def test_kisa_sifre_ve_uyusmayan_tekrar():
    with pytest.raises(KullaniciHatasi, match="en az 8"):
        ku.kayit_baslat("ayse@akgun.com.tr", "Ayşe", "1234567", "1234567", ALAN, SIMDI)
    with pytest.raises(KullaniciHatasi, match="tutmuyor"):
        ku.kayit_baslat("ayse@akgun.com.tr", "Ayşe", "GizliSifre1", "GizliSifre2", ALAN, SIMDI)


# ---------- Giriş ve kilitlenme ----------

def test_yanlis_sifre_ve_olmayan_kullanici_ayni_mesaj():
    kayitli()
    with pytest.raises(KullaniciHatasi) as h1:
        ku.giris("ayse@akgun.com.tr", "YanlisSifre")
    with pytest.raises(KullaniciHatasi) as h2:
        ku.giris("yok@akgun.com.tr", "YanlisSifre")
    assert str(h1.value) == str(h2.value) == "E-posta ya da şifre hatalı."


def test_giriste_son_giris_yazilir_buyuk_kucuk_harf_onemsiz():
    kayitli()
    k = ku.giris(" AYSE@akgun.com.tr ", "GizliSifre1", SIMDI)
    assert k["son_giris"] == "2026-10-05 09:00:00"


def test_bes_hatali_denemede_bes_dakika_kilit():
    kayitli()
    for _ in range(ku.GIRIS_EN_FAZLA_HATA - 1):
        with pytest.raises(KullaniciHatasi, match="hatalı"):
            ku.giris("ayse@akgun.com.tr", "YanlisSifre", SIMDI)
    with pytest.raises(KullaniciHatasi, match="kilitlendi"):
        ku.giris("ayse@akgun.com.tr", "YanlisSifre", SIMDI)
    # Kilitliyken doğru şifre de geçmez
    with pytest.raises(KullaniciHatasi, match="5 dakika sonra"):
        ku.giris("ayse@akgun.com.tr", "GizliSifre1", SIMDI)
    with pytest.raises(KullaniciHatasi, match="1 dakika sonra"):
        ku.giris("ayse@akgun.com.tr", "GizliSifre1", SIMDI + timedelta(minutes=4, seconds=30))
    # Süre dolunca doğru şifreyle girilir, sayaç sıfırlanır
    ku.giris("ayse@akgun.com.tr", "GizliSifre1", SIMDI + timedelta(minutes=5, seconds=1))
    k = satir("kullanicilar", "ayse@akgun.com.tr")
    assert k["hatali_deneme"] == 0 and k["kilit_bitis"] is None


def test_basarili_giris_hatali_sayaci_sifirlar():
    kayitli()
    for _ in range(ku.GIRIS_EN_FAZLA_HATA - 1):
        with pytest.raises(KullaniciHatasi):
            ku.giris("ayse@akgun.com.tr", "YanlisSifre", SIMDI)
    ku.giris("ayse@akgun.com.tr", "GizliSifre1", SIMDI)
    with pytest.raises(KullaniciHatasi, match="hatalı\\."):               # kilitlenmez, sayaç baştan
        ku.giris("ayse@akgun.com.tr", "YanlisSifre", SIMDI)


# ---------- Şifre sıfırlama ----------

def test_sifre_sifirlama():
    kayitli()
    eposta, kod = ku.sifirlama_baslat("ayse@akgun.com.tr", SIMDI)
    assert len(kod) == 6 and satir("dogrulama_kodlari", eposta)["amac"] == "sifirlama"
    ku.sifre_sifirla(eposta, kod, "YeniSifre99", "YeniSifre99", SIMDI)
    assert ku.giris(eposta, "YeniSifre99")["eposta"] == eposta
    with pytest.raises(KullaniciHatasi):
        ku.giris(eposta, "GizliSifre1")


def test_sifirlama_kilidi_acar():
    kayitli()
    for _ in range(ku.GIRIS_EN_FAZLA_HATA):
        with pytest.raises(KullaniciHatasi):
            ku.giris("ayse@akgun.com.tr", "YanlisSifre", SIMDI)
    _, kod = ku.sifirlama_baslat("ayse@akgun.com.tr", SIMDI)
    ku.sifre_sifirla("ayse@akgun.com.tr", kod, "YeniSifre99", None, SIMDI)
    assert ku.giris("ayse@akgun.com.tr", "YeniSifre99", SIMDI)


def test_sifirlamada_yanlis_ve_suresi_dolmus_kod():
    kayitli()
    eposta, kod = ku.sifirlama_baslat("ayse@akgun.com.tr", SIMDI)
    yanlis = "000000" if kod != "000000" else "111111"
    with pytest.raises(KullaniciHatasi, match="Kod hatalı"):
        ku.sifre_sifirla(eposta, yanlis, "YeniSifre99", None, SIMDI)
    with pytest.raises(KullaniciHatasi, match="süresi doldu"):
        ku.sifre_sifirla(eposta, kod, "YeniSifre99", None, SIMDI + timedelta(minutes=11))
    assert ku.giris(eposta, "GizliSifre1")                          # şifre değişmedi


def test_sifirlamada_kisa_sifre_kodu_harcamaz():
    kayitli()
    eposta, kod = ku.sifirlama_baslat("ayse@akgun.com.tr", SIMDI)
    with pytest.raises(KullaniciHatasi, match="en az 8"):
        ku.sifre_sifirla(eposta, kod, "kisa", None, SIMDI)
    ku.sifre_sifirla(eposta, kod, "YeniSifre99", None, SIMDI)       # kod hâlâ kullanılabilir


def test_kayitli_olmayan_adrese_kod_uretilmez():
    assert ku.sifirlama_baslat("yok@akgun.com.tr", SIMDI) == ("yok@akgun.com.tr", None)
    assert satir("dogrulama_kodlari", "yok@akgun.com.tr") is None


def test_kayit_ve_sifirlama_kodlari_karismaz():
    eposta, kayit_kodu = ku.kayit_baslat("ayse@akgun.com.tr", "Ayşe", "GizliSifre1", "GizliSifre1", ALAN, SIMDI)
    with pytest.raises(KullaniciHatasi, match="Geçerli bir kod yok"):
        ku.sifre_sifirla(eposta, kayit_kodu, "YeniSifre99", None, SIMDI)


# ---------- Yönetici ----------

def test_yonetici_yapma_ve_listeleme():
    kayitli()
    ku.yonetici_yap("ayse@akgun.com.tr")
    (k,) = ku.kullanicilari_listele()
    assert k["yonetici"] and "sifre_hash" not in k


def test_dogrulanmamis_kullanici_yonetici_yapilamaz():
    ku.kayit_baslat("ayse@akgun.com.tr", "Ayşe", "GizliSifre1", "GizliSifre1", ALAN, SIMDI)
    with pytest.raises(KullaniciHatasi):
        ku.yonetici_yap("ayse@akgun.com.tr")
