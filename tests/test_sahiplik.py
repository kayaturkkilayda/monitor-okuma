"""Kamera sahipliği: kim hangi kamerayı görür, eski kameralar kime gider."""
import json
import logging

import pytest

import gecis
import kullanicilar as ku
import kayitlar_sekmesi as ks
import sahiplik
from veritabani import baglan

AYSE = {"eposta": "ayse@akgun.com.tr", "ad": "Ayşe", "yonetici": False}
MEHMET = {"eposta": "mehmet@akgun.com.tr", "ad": "Mehmet", "yonetici": False}
YONETICI = {"eposta": "bt@akgun.com.tr", "ad": "BT", "yonetici": True}

AYSENIN = {"kod": "K1", "yatak": "Y1", "ekleyen": "ayse@akgun.com.tr"}
MEHMETIN = {"kod": "K2", "yatak": "Y2", "ekleyen": "mehmet@akgun.com.tr"}
SAHIPSIZ = {"kod": "K9", "yatak": "Y9"}                 # eski ayar dosyasından


class SahteLog:
    def __init__(self):
        self.mesajlar = []

    def info(self, m): self.mesajlar.append(m)
    def warning(self, m): self.mesajlar.append(m)
    def error(self, m): self.mesajlar.append(m)
    def exception(self, m): self.mesajlar.append(m)


# ---------- Temel kurallar ----------

def test_sahibi_kucuk_harfe_cevrilir():
    assert sahiplik.sahibi({"ekleyen": "  Ayse@Akgun.Com.TR "}) == "ayse@akgun.com.tr"
    assert sahiplik.sahibi({}) == ""
    assert sahiplik.sahibi({"ekleyen": None}) == ""


def test_sahiplendir_alani_yazar():
    k = sahiplik.sahiplendir({"kod": "K1"}, "Ayse@Akgun.com.tr")
    assert k["ekleyen"] == "ayse@akgun.com.tr"
    assert k["kod"] == "K1"                              # diğer alanlar korunur


def test_kullanici_yalnizca_kendi_kamerasini_gorur():
    assert sahiplik.gorebilir_mi(AYSENIN, AYSE) is True
    assert sahiplik.gorebilir_mi(MEHMETIN, AYSE) is False


def test_yonetici_hepsini_gorur():
    for kamera in (AYSENIN, MEHMETIN, SAHIPSIZ):
        assert sahiplik.gorebilir_mi(kamera, YONETICI) is True


def test_sahipsiz_kamerayi_normal_kullanici_goremez():
    """Eksik bilgi yüzünden veri sızmasın: sahipsiz kamera yöneticiye aittir."""
    assert sahiplik.gorebilir_mi(SAHIPSIZ, AYSE) is False


def test_oturum_yoksa_hicbir_sey_gorunmez():
    assert sahiplik.gorebilir_mi(AYSENIN, None) is False
    assert sahiplik.gorebilir_mi(AYSENIN, {}) is False


def test_gorunen_kameralar_suzulur():
    hepsi = [AYSENIN, MEHMETIN, SAHIPSIZ]
    assert [k["kod"] for k in sahiplik.gorunen_kameralar(hepsi, AYSE)] == ["K1"]
    assert [k["kod"] for k in sahiplik.gorunen_kameralar(hepsi, MEHMET)] == ["K2"]
    assert [k["kod"] for k in sahiplik.gorunen_kameralar(hepsi, YONETICI)] == ["K1", "K2", "K9"]


def test_gorunen_kodlar_yoneticide_sinirsiz():
    hepsi = [AYSENIN, MEHMETIN]
    assert sahiplik.gorunen_kodlar(hepsi, YONETICI) is None      # sınır yok
    assert sahiplik.gorunen_kodlar(hepsi, AYSE) == ["K1"]
    assert sahiplik.gorunen_kodlar([], AYSE) == []


# ---------- Kayıtlar sekmesi filtresi ----------

def test_kosullarda_izinli_kameralar():
    nerede, degerler = ks._kosullar(kodlar=["K1", "K3"])
    assert "kamera_kodu IN (?, ?)" in nerede
    assert degerler == ["K1", "K3"]


def test_kamerasi_olmayan_hicbir_kayit_gormez():
    nerede, degerler = ks._kosullar(kodlar=[])
    assert nerede.strip() == "WHERE 0"
    assert degerler == []


def test_yoneticide_filtre_eklenmez():
    nerede, degerler = ks._kosullar(kodlar=None)
    assert nerede == "" and degerler == []


def _kayit_ekle(kamera_kodu: str, kayit_id: str):
    with baglan() as db:
        db.execute(
            "INSERT INTO kayitlar (kayit_id, cift_id, tesis_kodu, kamera_kodu, yatak_kodu,"
            " cekim_zamani, saat_dilimi, sira, dosya_yolu, durum, sonraki_deneme)"
            " VALUES (?, ?, 'H01', ?, 'Y1', '2026-10-07 10:00:00', '+03:00', 1, 'x.avif',"
            " 'gonderildi', '2026-10-07 10:00:00')",
            (kayit_id, kayit_id, kamera_kodu))


def test_kayitlar_yalnizca_izinli_kameradan_gelir():
    _kayit_ekle("K1", "a")
    _kayit_ekle("K2", "b")
    assert {k["kamera_kodu"] for k in ks.kayitlari_getir()} == {"K1", "K2"}
    assert {k["kamera_kodu"] for k in ks.kayitlari_getir(kodlar=["K1"])} == {"K1"}
    assert ks.kayitlari_getir(kodlar=[]) == []


def test_kamera_listesi_de_suzulur():
    _kayit_ekle("K1", "a")
    _kayit_ekle("K2", "b")
    assert ks.kameralari_getir() == ["K1", "K2"]
    assert ks.kameralari_getir(["K2"]) == ["K2"]


def test_gun_ozetleri_suzulur():
    _kayit_ekle("K1", "a")
    _kayit_ekle("K2", "b")
    assert ks.gun_ozetleri()[0]["toplam"] == 2
    assert ks.gun_ozetleri(kodlar=["K1"])[0]["toplam"] == 1
    assert ks.gun_ozetleri(kodlar=[]) == []


# ---------- Geçiş: eski kameralar yöneticiye ----------

@pytest.fixture
def ayar_dosyasi(tmp_path, monkeypatch):
    """gecis.py'nin okuyup yazdığı ayar dosyasını geçici klasöre alır.

    Gerçek config/ayarlar.json'a dokunulmaz; DPAPI şifrelemesi de devreye girmez.
    """
    yol = tmp_path / "ayarlar.json"

    def oku():
        return json.loads(yol.read_text(encoding="utf-8"))

    def yaz(ayarlar):
        yol.write_text(json.dumps(ayarlar, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(gecis, "ayarlari_oku", oku)
    monkeypatch.setattr(gecis, "ayarlari_yaz", yaz)
    return yol, oku, yaz


def _yonetici_olustur(eposta="bt@akgun.com.tr"):
    ku.ilk_yoneticiyi_olustur(eposta, "BT", "GizliSifre1", "GizliSifre1")


def test_sahipsiz_kameralar_yoneticiye_atanir(ayar_dosyasi):
    yol, oku, yaz = ayar_dosyasi
    yaz({"kameralar": [dict(SAHIPSIZ), dict(AYSENIN)]})
    _yonetici_olustur()
    assert gecis.kamera_sahiplerini_ata(SahteLog()) == 1
    kameralar = {k["kod"]: k["ekleyen"] for k in oku()["kameralar"]}
    assert kameralar["K9"] == "bt@akgun.com.tr"          # sahipsizdi
    assert kameralar["K1"] == "ayse@akgun.com.tr"        # sahibi değişmedi


def test_gecis_ikinci_kez_bir_sey_yapmaz(ayar_dosyasi):
    yol, oku, yaz = ayar_dosyasi
    yaz({"kameralar": [dict(SAHIPSIZ)]})
    _yonetici_olustur()
    assert gecis.kamera_sahiplerini_ata(SahteLog()) == 1
    assert gecis.kamera_sahiplerini_ata(SahteLog()) == 0


def test_yonetici_yokken_gecis_beklemeye_alinir(ayar_dosyasi):
    """Kurulumun ilk anında hesap yoktur; bir sonraki açılışta tekrar denenir."""
    yol, oku, yaz = ayar_dosyasi
    yaz({"kameralar": [dict(SAHIPSIZ)]})
    assert gecis.kamera_sahiplerini_ata(SahteLog()) == 0
    assert "ekleyen" not in oku()["kameralar"][0]


def test_en_eski_yonetici_secilir(ayar_dosyasi):
    yol, oku, yaz = ayar_dosyasi
    yaz({"kameralar": [dict(SAHIPSIZ)]})
    _yonetici_olustur("ilk@akgun.com.tr")
    _, kod = ku.kayit_baslat("ikinci@akgun.com.tr", "İkinci", "GizliSifre1", None, None)
    ku.kayit_dogrula("ikinci@akgun.com.tr", kod)
    ku.yonetici_yap("ikinci@akgun.com.tr")
    gecis.kamera_sahiplerini_ata(SahteLog())
    assert oku()["kameralar"][0]["ekleyen"] == "ilk@akgun.com.tr"


def test_ayar_dosyasi_okunamazsa_cokmez(monkeypatch):
    def patla():
        raise OSError("dosya yok")
    monkeypatch.setattr(gecis, "ayarlari_oku", patla)
    assert gecis.kamera_sahiplerini_ata(SahteLog()) == 0
