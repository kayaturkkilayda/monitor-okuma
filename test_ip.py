import sys
import time
from datetime import datetime
sys.path.insert(0, "src")

from kamera import IPKamera
from kaydedici import kaydet
from log import log_kur

log = log_kur()

kameralar = [
    IPKamera("K1", "Y1", "http://localhost:8080/K1/shot.jpg"),
    IPKamera("K2", "Y2", "http://localhost:8080/K2/shot.jpg"),
    IPKamera("K3", "Y3", "http://localhost:8080/K3/shot.jpg"),
]

baslangic = time.time()

for k in kameralar:
    kare1, z1, kare2, z2 = k.cift_cekim(aralik_sn=5)
    for sira, (kare, z) in enumerate([(kare1, z1), (kare2, z2)], start=1):
        if kare is None:
            log.error(f"{k.kod} -> {k.yatak} | {sira}. kare alınamadı")
            continue
        yol, boyut = kaydet(kare, k.kod, k.yatak, datetime.fromtimestamp(z))
        log.info(f"{k.kod} -> {k.yatak} | {sira}. kare: {yol.name} ({boyut / 1024:.1f} KB)")

log.info(f"Tüm tur: {time.time() - baslangic:.1f} sn")