"""Her kamera için ayrı iş parçacığında periyodik çekim."""
import threading
import time
import uuid
from datetime import datetime

from gonderici import kuyruga_ekle
from kaydedici import kaydet


def kamera_dongusu(kamera, ayarlar: dict, log, durum, dur: threading.Event):
    aralik = ayarlar["gonderim_araligi_sn"]
    gecikme = ayarlar["ikinci_cekim_gecikme_sn"]
    etiket = f"{ayarlar['tesis_kodu']}/{kamera.kod}/{kamera.yatak}"

    while not dur.is_set():
        baslangic = time.time()
        basarili_kare = 0
        try:
            kare1, z1, kare2, z2 = kamera.cift_cekim(aralik_sn=gecikme)
            cift_id = str(uuid.uuid4())
            for sira, (kare, z) in enumerate([(kare1, z1), (kare2, z2)], start=1):
                if kare is None:
                    log.debug(f"{etiket} | {sira}. kare alınamadı")
                    continue
                zaman = datetime.fromtimestamp(z)
                yol, boyut = kaydet(kare, kamera.kod, kamera.yatak, zaman,
                                    format=ayarlar["format"], kalite=ayarlar["kalite"])
                kuyruga_ekle(yol, ayarlar["tesis_kodu"], kamera.kod, kamera.yatak,
                             zaman, sira, cift_id)
                basarili_kare += 1
                log.info(f"{etiket} | {sira}. kare kuyruğa eklendi ({boyut / 1024:.1f} KB)")
        except Exception:
            log.exception(f"{etiket} | beklenmeyen hata")

        durum.bildir(etiket, basarili=basarili_kare > 0)

        gecen = time.time() - baslangic
        dur.wait(max(0, aralik - gecen))


def baslat(kameralar: list, ayarlar: dict, log, durum):
    dur = threading.Event()
    is_parcaciklari = []
    for k in kameralar:
        t = threading.Thread(target=kamera_dongusu, args=(k, ayarlar, log, durum, dur),
                             name=k.kod, daemon=True)
        t.start()
        is_parcaciklari.append(t)
    return dur, is_parcaciklari