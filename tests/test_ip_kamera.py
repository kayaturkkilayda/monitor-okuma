"""IP kamera: şifresiz adres, Basic/Digest kimlik doğrulama ve hata nedeni.

Telefonu IP kameraya çeviren uygulamalar (Android "IP Webcam" gibi)
http://<telefon-ip>:8080/shot.jpg adresinde düz bir JPEG verir. Şifre açılırsa
Digest değil Basic ister; bu yüzden ikisi de desteklenir.
"""
import cv2
import numpy as np
import pytest
import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from kamera import IPKamera

TELEFON = "http://192.168.1.25:8080/shot.jpg"


def jpeg_baytlari() -> bytes:
    kare = np.zeros((8, 8, 3), dtype=np.uint8)
    tamam, veri = cv2.imencode(".jpg", kare)
    assert tamam
    return veri.tobytes()


class SahteYanit:
    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def raise_for_status(self):
        if not self.ok:
            hata = requests.HTTPError(f"HTTP {self.status_code}")
            hata.response = self
            raise hata


@pytest.fixture
def istekler(monkeypatch):
    """requests.get çağrılarını kaydeder; yanıtları test belirler."""
    kayit = {"cagrilar": [], "yanitlar": []}

    def sahte_get(url, auth=None, timeout=None):
        kayit["cagrilar"].append({"url": url, "auth": auth, "timeout": timeout})
        sonraki = kayit["yanitlar"].pop(0)
        if isinstance(sonraki, Exception):
            raise sonraki
        return sonraki

    monkeypatch.setattr(requests, "get", sahte_get)
    return kayit


# ---------- Şifresiz telefon kamerası ----------

def test_sifresiz_adres_calisir(istekler):
    """IP Webcam varsayılan olarak şifre istemez; mevcut kod bu hâliyle çalışır."""
    istekler["yanitlar"] = [SahteYanit(200, jpeg_baytlari())]
    kamera = IPKamera("K1", "Y1", TELEFON)
    kare = kamera._snapshot()
    assert kare is not None and kare.shape == (8, 8, 3)
    assert istekler["cagrilar"][0]["url"] == TELEFON
    assert istekler["cagrilar"][0]["auth"] is None       # kimlik gönderilmez
    assert len(istekler["cagrilar"]) == 1


def test_zaman_asimi_gonderilir(istekler):
    istekler["yanitlar"] = [SahteYanit(200, jpeg_baytlari())]
    IPKamera("K1", "Y1", TELEFON)._snapshot()
    assert istekler["cagrilar"][0]["timeout"] == IPKamera.ZAMAN_ASIMI


def test_telefon_kapaliysa_none_doner(istekler):
    """Telefon uykuda, Wi-Fi'den düşmüş ya da adres yanlışsa çekim sessizce başarısız olur."""
    istekler["yanitlar"] = [requests.ConnectionError("baglanti yok")]
    k = IPKamera("K1", "Y1", TELEFON)
    assert k._snapshot() is None
    assert k.son_hata == "ConnectionError"


# ---------- Şifreli kamera ----------

def test_once_digest_denenir(istekler):
    istekler["yanitlar"] = [SahteYanit(200, jpeg_baytlari())]
    kamera = IPKamera("K1", "Y1", TELEFON, "admin", "1234")
    kamera._snapshot()
    assert isinstance(istekler["cagrilar"][0]["auth"], HTTPDigestAuth)


def test_digest_reddedilirse_basic_denenir(istekler):
    """Telefon uygulamaları Basic ister; ilk 401'den sonra ona geçilir."""
    istekler["yanitlar"] = [SahteYanit(401), SahteYanit(200, jpeg_baytlari())]
    kamera = IPKamera("K1", "Y1", TELEFON, "admin", "1234")
    kare = kamera._snapshot()
    assert kare is not None
    assert isinstance(istekler["cagrilar"][0]["auth"], HTTPDigestAuth)
    assert isinstance(istekler["cagrilar"][1]["auth"], HTTPBasicAuth)


def test_basic_calisinca_sonraki_cekim_tek_istek(istekler):
    istekler["yanitlar"] = [SahteYanit(401), SahteYanit(200, jpeg_baytlari()),
                            SahteYanit(200, jpeg_baytlari())]
    kamera = IPKamera("K1", "Y1", TELEFON, "admin", "1234")
    kamera._snapshot()
    kamera._snapshot()
    assert len(istekler["cagrilar"]) == 3               # 2 + 1, tekrar denenmez
    assert isinstance(istekler["cagrilar"][2]["auth"], HTTPBasicAuth)


def test_sifre_yanlissa_401_bildirilir(istekler):
    istekler["yanitlar"] = [SahteYanit(401), SahteYanit(401)]
    kamera = IPKamera("K1", "Y1", TELEFON, "admin", "yanlis")
    assert kamera._snapshot() is None
    assert kamera.son_durum_kodu == 401                 # arayüz bunu mesaja çevirir


def test_kullanici_adi_yoksa_basic_denenmez(istekler):
    istekler["yanitlar"] = [SahteYanit(401)]
    kamera = IPKamera("K1", "Y1", TELEFON)
    assert kamera._snapshot() is None
    assert len(istekler["cagrilar"]) == 1
