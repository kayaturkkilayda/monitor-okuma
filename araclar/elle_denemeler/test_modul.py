import sys
from datetime import datetime
sys.path.insert(0, "src")

from kamera import Kamera
from kaydedici import kaydet
from log import log_kur

log = log_kur()
k = Kamera(kod="K1", yatak="Y1", kaynak=0)

log.info(f"{k.kod} -> {k.yatak} | çift çekim başlıyor")
kare1, z1, kare2, z2 = k.cift_cekim(aralik_sn=5)

for sira, (kare, z) in enumerate([(kare1, z1), (kare2, z2)], start=1):
    if kare is None:
        log.error(f"{k.kod} -> {k.yatak} | {sira}. kare alınamadı")
        continue
    yol, boyut = kaydet(kare, k.kod, k.yatak, datetime.fromtimestamp(z))
    log.info(f"{k.kod} -> {k.yatak} | {sira}. kare: {yol.name} ({boyut / 1024:.1f} KB)")

if z1 and z2:
    log.info(f"İki kare arası: {z2 - z1:.2f} sn")