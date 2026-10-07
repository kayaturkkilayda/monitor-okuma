"""Kameradan görüntü alma."""
import time

import cv2
import numpy as np
import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

class Kamera:
    """Tek bir kamerayı temsil eder.

    kod    : kamera kodu, örn. "K1"
    yatak  : bağlı olduğu yatak kodu, örn. "Y1"
    kaynak : webcam için sayı (0, 1...), IP kamera için RTSP adresi
    """

    ISINMA_KARE = 30
    ISINMA_SANIYE = 2

    def __init__(self, kod: str, yatak: str, kaynak):
        self.kod = kod
        self.yatak = yatak
        self.kaynak = kaynak

    def _taze_kare(self, cihaz):
        """Tampondaki eski kareleri atlayıp en güncel kareyi döndürür."""
        kare = None
        for _ in range(5):
            basarili, okunan = cihaz.read()
            if basarili:
                kare = okunan
        return kare

    def cift_cekim(self, aralik_sn: float = 5):
        """Kamerayı bir kez açar, aralık_sn arayla iki kare alır.

        (kare1, zaman1, kare2, zaman2) döndürür. Başarısız kareler None olur.
        """
        cihaz = cv2.VideoCapture(self.kaynak)
        if not cihaz.isOpened():
            cihaz.release()
            return None, None, None, None

        try:
            time.sleep(self.ISINMA_SANIYE)
            for _ in range(self.ISINMA_KARE):
                cihaz.read()

            zaman1 = time.time()
            kare1 = self._taze_kare(cihaz)

            time.sleep(aralik_sn)

            zaman2 = time.time()
            kare2 = self._taze_kare(cihaz)
        finally:
            cihaz.release()

        return kare1, zaman1, kare2, zaman2
    


class IPKamera:
    """ONVIF/HTTP snapshot destekleyen IP kamera.

    snapshot_url : kameranın tek kare verdiği adres
    """

    ZAMAN_ASIMI = 5   # saniye; kamera cevap vermezse beklemeyi bırak

    def __init__(self, kod: str, yatak: str, snapshot_url: str,
                 kullanici: str = "", sifre: str = ""):
        self.kod = kod
        self.yatak = yatak
        self.url = snapshot_url
        self.kullanici = kullanici
        self.sifre = sifre
        # Önce Digest denenir. Kamera Basic isterse ilk 401'de ona geçilir.
        self.auth = HTTPDigestAuth(kullanici, sifre) if kullanici else None
        # Son denemenin sonucu; arayüz bağlantı testinde nedeni göstermek için okur
        self.son_hata = None
        self.son_durum_kodu = None

    def _istek(self, auth):
        return requests.get(self.url, auth=auth, timeout=self.ZAMAN_ASIMI)

    def _snapshot(self):
        """Tek kare çeker. Hata olursa None döndürür ve nedeni son_hata'ya yazar."""
        try:
            yanit = self._istek(self.auth)
            if yanit.status_code == 401 and self.kullanici and not isinstance(
                    self.auth, HTTPBasicAuth):
                # Telefon uygulamaları ve bazı IP kameralar Digest yerine Basic ister
                basic = HTTPBasicAuth(self.kullanici, self.sifre)
                yanit = self._istek(basic)
                if yanit.ok:
                    self.auth = basic           # bundan sonrası tek istekte biter
            yanit.raise_for_status()
        except requests.RequestException as e:
            self.son_hata = type(e).__name__
            self.son_durum_kodu = getattr(getattr(e, "response", None), "status_code", None)
            return None
        self.son_hata = self.son_durum_kodu = None
        veri = np.frombuffer(yanit.content, dtype=np.uint8)
        return cv2.imdecode(veri, cv2.IMREAD_COLOR)

    def cift_cekim(self, aralik_sn: float = 5):
        zaman1 = time.time()
        kare1 = self._snapshot()
        time.sleep(aralik_sn)
        zaman2 = time.time()
        kare2 = self._snapshot()
        return kare1, zaman1, kare2, zaman2