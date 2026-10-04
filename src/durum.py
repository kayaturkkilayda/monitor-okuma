"""Kamera sağlık takibi: arıza ve düzelme anlarını yakalar."""
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

from veritabani import olay
from zaman import simdi as simdiki_zaman, zamani_coz

DURUM_DOSYASI = Path("durum.json")
ARIZA_ESIGI = 3   # üst üste kaç başarısız turdan sonra arıza sayılsın
YANIT_YOK_KATI = 3  # son görüntü çekim aralığının kaç katından eskiyse "yanıt yok"


def gorunen_durum(d: dict, aktif: bool, aralik_sn: float, simdi: datetime,
                  onayli: bool = True) -> str:
    """Arayüzde gösterilecek durum.

    Onaysız kamera her durumdan önce "onay_bekliyor" görünür; motor ondan çekim yapmaz.

    durum.json'u motor yazar; motor kapalıysa son yazılan "çalışıyor" orada öylece kalır.
    Son görüntü çok eskiyse "çalışıyor" yerine "yanit_yok" gösterilir. Arızalı kamera
    zaten görüntü veremediği için arızalı olarak kalır.
    """
    if not onayli:
        return "onay_bekliyor"
    if not aktif:
        return "pasif"
    durum = d.get("durum", "bilinmiyor")
    son = zamani_coz(d.get("son_basari"))
    if durum == "calisiyor" and (son is None or simdi - son > timedelta(seconds=aralik_sn * YANIT_YOK_KATI)):
        return "yanit_yok"
    return durum


class KameraDurumu:
    def __init__(self, log, bildirici=None):
        """bildirici: ARIZA / DÜZELDİ anlarında e-posta gönderen nesne (yoksa yalnızca loglanır)."""
        self.log = log
        self.bildirici = bildirici
        self._kilit = threading.Lock()
        # Motor yeniden başlayınca süren bir arıza "yeni arıza" sayılıp tekrar bildirilmesin
        self._durum = self._oku()

    @staticmethod
    def _oku() -> dict:
        try:
            durum = json.loads(DURUM_DOSYASI.read_text(encoding="utf-8"))
            return durum if isinstance(durum, dict) else {}
        except (OSError, ValueError):
            return {}

    def bildir(self, etiket: str, basarili: bool, kaynak: str | None = None):
        """Her turun sonunda çağrılır. Durum değiştiyse loglar ve olaylara yazar.

        kaynak: olaylar tablosundaki kaynak (kamera kodu); verilmezse etiket kullanılır.
        """
        bildirim = eposta = None
        with self._kilit:
            d = self._durum.setdefault(etiket, {
                "durum": "bilinmiyor", "ardisik_hata": 0,
                "son_basari": None, "ariza_baslangic": None,
            })
            simdi = simdiki_zaman()

            if basarili:
                if d["durum"] == "arizali":
                    bildirim = ("INFO", f"{etiket} | DÜZELDİ (arıza başlangıcı: {d['ariza_baslangic']})")
                    eposta = ("duzeldi", d["ariza_baslangic"], simdi)
                d.update(durum="calisiyor", ardisik_hata=0,
                         son_basari=simdi, ariza_baslangic=None)
            else:
                d["ardisik_hata"] += 1
                if d["ardisik_hata"] == ARIZA_ESIGI:
                    d.update(durum="arizali", ariza_baslangic=simdi)
                    bildirim = ("ERROR", f"{etiket} | ARIZA: {ARIZA_ESIGI} tur üst üste görüntü alınamadı")
                    eposta = ("ariza", simdi, d["son_basari"])

            self._kaydet()

        # Veritabanı meşgulse diğer kameralar kilit yüzünden beklemesin diye kilidin dışında
        if bildirim:
            olay(self.log, bildirim[0], kaynak or etiket, bildirim[1])
        if eposta and self.bildirici and kaynak:
            # Yalnızca kuyruğa bırakılır; mail gönderimi kamera döngüsünü bekletmez
            self.bildirici.kamera_olayi(eposta[0], kaynak, eposta[1], eposta[2])

    def _kaydet(self):
        gecici = DURUM_DOSYASI.with_suffix(".tmp")
        gecici.write_text(json.dumps(self._durum, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        gecici.replace(DURUM_DOSYASI)
