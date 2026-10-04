from datetime import datetime

import numpy as np
import pytest

import zamanlayici
from veritabani import baglan

AYARLAR = {"tesis_kodu": "H01", "format": "jpg", "kalite": 80}
Z1 = datetime(2026, 10, 2, 15, 12, 13).timestamp()
Z2 = datetime(2026, 10, 2, 15, 12, 18).timestamp()


class SahteKamera:
    kod, yatak = "K1", "Y1"


class SahteLog:
    def __init__(self):
        self.mesajlar = []

    def info(self, m): self.mesajlar.append(m)
    def debug(self, m): self.mesajlar.append(m)


def kare():
    return np.zeros((8, 8, 3), dtype=np.uint8)


def kayitlar():
    with baglan() as db:
        return [dict(s) for s in db.execute("SELECT * FROM kayitlar ORDER BY sira")]


@pytest.fixture(autouse=True)
def calisma_klasoru(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)          # goruntuler/ geçici klasöre yazılsın


def test_cift_kimlik_ve_dosya_adlari(tmp_path):
    eklenen = zamanlayici.cifti_kaydet(SahteKamera(), AYARLAR, SahteLog(), kare(), Z1, kare(), Z2)
    assert eklenen == 2
    k1, k2 = kayitlar()
    assert k1["kayit_id"] == "H01_K1_Y1_2026-10-02_15-12-13_1"
    assert k2["kayit_id"] == "H01_K1_Y1_2026-10-02_15-12-18_2"
    # İki karenin çifti aynı, ilk karenin zamanıyla
    assert k1["cift_id"] == k2["cift_id"] == "H01_K1_Y1_2026-10-02_15-12-13"
    # Dosya adı = kimlik, klasör yapısı goruntuler/<tarih>/<yatak>/
    for k in (k1, k2):
        yol = tmp_path / k["dosya_yolu"]
        assert yol.exists()
        assert yol.name == f"{k['kayit_id']}.jpg"
        assert yol.parent == tmp_path / "goruntuler" / "2026-10-02" / "Y1"


def test_ilk_kare_alinamazsa_cift_yine_ilk_karenin_zamaniyla():
    zamanlayici.cifti_kaydet(SahteKamera(), AYARLAR, SahteLog(), None, Z1, kare(), Z2)
    (k2,) = kayitlar()
    assert k2["kayit_id"] == "H01_K1_Y1_2026-10-02_15-12-18_2"
    assert k2["cift_id"] == "H01_K1_Y1_2026-10-02_15-12-13"


def test_hic_kare_yoksa_kayit_olusmaz():
    assert zamanlayici.cifti_kaydet(SahteKamera(), AYARLAR, SahteLog(), None, None, None, None) == 0
    assert kayitlar() == []


def test_ayni_saniyede_yeniden_cekim_ustune_yazmaz(tmp_path):
    """Örn. motor aynı saniyede yeniden başladı: ikinci çift _2 ekiyle ayrı kaydedilir."""
    zamanlayici.cifti_kaydet(SahteKamera(), AYARLAR, SahteLog(), kare(), Z1, None, Z2)
    zamanlayici.cifti_kaydet(SahteKamera(), AYARLAR, SahteLog(), kare(), Z1, None, Z2)
    ilk, ikinci = sorted(kayitlar(), key=lambda k: k["kayit_id"])
    assert ilk["kayit_id"] == "H01_K1_Y1_2026-10-02_15-12-13_1"
    assert ikinci["kayit_id"] == "H01_K1_Y1_2026-10-02_15-12-13_1_2"
    assert ikinci["cift_id"] == "H01_K1_Y1_2026-10-02_15-12-13_2"
    assert (tmp_path / ilk["dosya_yolu"]).exists() and (tmp_path / ikinci["dosya_yolu"]).exists()
