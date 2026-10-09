"""Sahte M4, gerçek M4'ün sözleşmesini doğru taklit ediyor mu?

Bu araç testin kendisi değil, testin ölçeğidir: motorun gönderdiği gövdeyi burada
reddediyorsak gerçek M4'te de reddedilir. Bu yüzden doğrulaması test ediliyor.
"""
import base64
import importlib.util
import io
import sys
from pathlib import Path

import pytest
from PIL import Image

KOK = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def m4():
    """araclar/ klasörü paket değil; dosyayı doğrudan yükleriz."""
    yol = KOK / "araclar" / "sahte_m4.py"
    tanim = importlib.util.spec_from_file_location("sahte_m4", yol)
    modul = importlib.util.module_from_spec(tanim)
    sys.modules["sahte_m4"] = modul
    tanim.loader.exec_module(modul)
    return modul


def jpeg_b64() -> str:
    tampon = io.BytesIO()
    Image.new("RGB", (8, 6), (10, 20, 30)).save(tampon, format="JPEG")
    return base64.b64encode(tampon.getvalue()).decode("ascii")


@pytest.fixture
def gecerli():
    return {
        "captureId": "4f1c0c5e-0b3a-4a1e-9a7a-0d2b6c9f1111",
        "kameraKodu": "K1",
        "kameraId": 1,
        "yatakEslesmeKodu": "Y1",
        "goruntuCekilmeZamani": "2026-10-09T07:48:43.650+03:00",
        "okumaGrupId": "H01_K1_Y1_2026-10-09_07-48-43",
        "goruntuFormati": "jpeg",
        "goruntuBase64": jpeg_b64(),
    }


def test_gecerli_govde_kabul_edilir(m4, gecerli):
    assert m4.govdeyi_dogrula(gecerli) is None


@pytest.mark.parametrize("alan", ["captureId", "kameraKodu", "kameraId", "yatakEslesmeKodu",
                                  "goruntuCekilmeZamani", "okumaGrupId", "goruntuFormati",
                                  "goruntuBase64"])
def test_eksik_alan_reddedilir(m4, gecerli, alan):
    gecerli.pop(alan)
    sebep = m4.govdeyi_dogrula(gecerli)
    assert sebep and alan in sebep


def test_fazladan_alan_reddedilir(m4, gecerli):
    gecerli["fazlalik"] = 1
    assert "beklenmeyen alan" in m4.govdeyi_dogrula(gecerli)


def test_kamera_id_metin_olursa_reddedilir(m4, gecerli):
    gecerli["kameraId"] = "1"
    assert "sayı olmalı" in m4.govdeyi_dogrula(gecerli)


def test_kamera_id_bool_olursa_reddedilir(m4, gecerli):
    """Python'da bool, int sayılır; kameraId için kabul edilmemeli."""
    gecerli["kameraId"] = True
    assert "sayı olmalı" in m4.govdeyi_dogrula(gecerli)


@pytest.mark.parametrize("alan", ["yatakEslesmeKodu", "goruntuBase64"])
def test_notblank_alanlar_bos_olamaz(m4, gecerli, alan):
    gecerli[alan] = "  "
    assert "boş olamaz" in m4.govdeyi_dogrula(gecerli)


@pytest.mark.parametrize("zaman", [
    "2026-10-09 07:48:43.650",             # T yok
    "09.10.2026 07:48:43",                 # ISO değil
    "dun",                                 # tamamen yanlış
])
def test_yanlis_zaman_bicimi_reddedilir(m4, gecerli, zaman):
    gecerli["goruntuCekilmeZamani"] = zaman
    assert "goruntuCekilmeZamani" in m4.govdeyi_dogrula(gecerli)


def test_format_jpeg_degilse_reddedilir(m4, gecerli):
    gecerli["goruntuFormati"] = "avif"
    assert "jpeg" in m4.govdeyi_dogrula(gecerli)


def test_base64_oneki_reddedilir(m4, gecerli):
    gecerli["goruntuBase64"] = "data:image/jpeg;base64," + gecerli["goruntuBase64"]
    assert "önek" in m4.govdeyi_dogrula(gecerli).lower()


def test_bozuk_base64_reddedilir(m4, gecerli):
    gecerli["goruntuBase64"] = "bu base64 degil!!"
    assert "çözülemedi" in m4.govdeyi_dogrula(gecerli)


def test_jpeg_olmayan_goruntu_reddedilir(m4, gecerli):
    tampon = io.BytesIO()
    Image.new("RGB", (8, 6)).save(tampon, format="PNG")
    gecerli["goruntuBase64"] = base64.b64encode(tampon.getvalue()).decode("ascii")
    assert "JPEG değil" in m4.govdeyi_dogrula(gecerli)


# ---------- Anahtar koda gömülü olmamalı ----------

def test_test_anahtari_koda_yazilmamis(m4):
    kaynak = (KOK / "araclar" / "sahte_m4.py").read_text(encoding="utf-8")
    assert "test-anahtar" not in kaynak          # yalnızca ayarlar.test.json'da
    assert m4.beklenen_anahtar()                 # ama ayar dosyasından okunabiliyor


def test_anahtar_ayar_dosyasindan_okunur(m4):
    import json
    ayar = json.loads((KOK / "araclar" / "ayarlar.test.json").read_text(encoding="utf-8"))
    assert m4.beklenen_anahtar() == ayar["api_key"]


# ---------- HTTP uçtan uca (Flask test istemcisi) ----------

@pytest.fixture
def istemci(m4, monkeypatch):
    monkeypatch.setattr(m4, "HATA_ORANI", 0)     # rastgele 503 testi bozmasın
    m4.gorulen.clear()
    m4.app.config.update(TESTING=True)
    return m4.app.test_client()


def _basliklar(m4):
    return {"X-Api-Key": m4.beklenen_anahtar(), "Content-Type": "application/json"}


def test_dogru_istek_kabul_edilir(m4, istemci, gecerli):
    assert istemci.post("/api/goruntu", json=gecerli, headers=_basliklar(m4)).status_code == 201


def test_yanlis_anahtar_401(m4, istemci, gecerli):
    basliklar = {**_basliklar(m4), "X-Api-Key": "yanlis"}
    assert istemci.post("/api/goruntu", json=gecerli, headers=basliklar).status_code == 401


def test_anahtarsiz_istek_401(m4, istemci, gecerli):
    assert istemci.post("/api/goruntu", json=gecerli,
                        headers={"Content-Type": "application/json"}).status_code == 401


def test_eksik_alan_400(m4, istemci, gecerli):
    gecerli.pop("kameraId")
    assert istemci.post("/api/goruntu", json=gecerli, headers=_basliklar(m4)).status_code == 400


def test_yanlis_tip_400(m4, istemci, gecerli):
    gecerli["kameraId"] = "1"
    assert istemci.post("/api/goruntu", json=gecerli, headers=_basliklar(m4)).status_code == 400


def test_ayni_capture_id_ikinci_kez_200(m4, istemci, gecerli):
    assert istemci.post("/api/goruntu", json=gecerli, headers=_basliklar(m4)).status_code == 201
    assert istemci.post("/api/goruntu", json=gecerli, headers=_basliklar(m4)).status_code == 200


# ---------- Backend gibi davranıyor mu? ----------

def test_json_olmayan_govde_415(m4, istemci, gecerli):
    """Spring'in @RequestBody ucu multipart gövdeye 415 döndürür; 415'in sebebi buydu."""
    y = istemci.post("/monitor-okuma/kamera",
                     data={"captureId": "x"},                  # multipart/form-data
                     headers={"X-Api-Key": m4.beklenen_anahtar()})
    assert y.status_code == 415
    assert "Unsupported Media Type" in y.get_json()["hata"]


def test_backend_yolu_dinleniyor(m4, istemci, gecerli):
    assert istemci.post("/monitor-okuma/kamera", json=gecerli,
                        headers=_basliklar(m4)).status_code == 201


def test_yeni_capture_201_tekrar_200(m4, istemci, gecerli):
    assert istemci.post("/monitor-okuma/kamera", json=gecerli,
                        headers=_basliklar(m4)).status_code == 201
    y = istemci.post("/monitor-okuma/kamera", json=gecerli, headers=_basliklar(m4))
    assert y.status_code == 200
    assert y.get_json()["captureId"] == gecerli["captureId"]


def test_offsetli_zaman_kabul_edilir(m4, gecerli):
    gecerli["goruntuCekilmeZamani"] = "2026-10-09T07:48:43.650+03:00"
    assert m4.govdeyi_dogrula(gecerli) is None


def test_notblank_bos_gelirse_400(m4, istemci, gecerli):
    gecerli["yatakEslesmeKodu"] = ""
    y = istemci.post("/monitor-okuma/kamera", json=gecerli, headers=_basliklar(m4))
    assert y.status_code == 400
    assert "yatakEslesmeKodu" in y.get_json()["hata"]
