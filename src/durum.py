"""Kamera sağlık takibi: arıza ve düzelme anlarını yakalar."""
import json
import threading
from pathlib import Path

from veritabani import olay
from zaman import simdi as simdiki_zaman

DURUM_DOSYASI = Path("durum.json")
ARIZA_ESIGI = 3   # üst üste kaç başarısız turdan sonra arıza sayılsın


class KameraDurumu:
    def __init__(self, log):
        self.log = log
        self._kilit = threading.Lock()
        self._durum = {}

    def bildir(self, etiket: str, basarili: bool, kaynak: str | None = None):
        """Her turun sonunda çağrılır. Durum değiştiyse loglar ve olaylara yazar.

        kaynak: olaylar tablosundaki kaynak (kamera kodu); verilmezse etiket kullanılır.
        """
        bildirim = None
        with self._kilit:
            d = self._durum.setdefault(etiket, {
                "durum": "bilinmiyor", "ardisik_hata": 0,
                "son_basari": None, "ariza_baslangic": None,
            })
            simdi = simdiki_zaman()

            if basarili:
                if d["durum"] == "arizali":
                    bildirim = ("INFO", f"{etiket} | DÜZELDİ (arıza başlangıcı: {d['ariza_baslangic']})")
                d.update(durum="calisiyor", ardisik_hata=0,
                         son_basari=simdi, ariza_baslangic=None)
            else:
                d["ardisik_hata"] += 1
                if d["ardisik_hata"] == ARIZA_ESIGI:
                    d.update(durum="arizali", ariza_baslangic=simdi)
                    bildirim = ("ERROR", f"{etiket} | ARIZA: {ARIZA_ESIGI} tur üst üste görüntü alınamadı")

            self._kaydet()

        # Veritabanı meşgulse diğer kameralar kilit yüzünden beklemesin diye kilidin dışında
        if bildirim:
            olay(self.log, bildirim[0], kaynak or etiket, bildirim[1])

    def _kaydet(self):
        gecici = DURUM_DOSYASI.with_suffix(".tmp")
        gecici.write_text(json.dumps(self._durum, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        gecici.replace(DURUM_DOSYASI)
