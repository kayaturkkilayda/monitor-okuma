"""Her kamera için ayrı iş parçacığında periyodik çekim."""
import threading
import time
from datetime import datetime

from gonderici import kuyruga_ekle
from kaydedici import goruntu_yolu, kaydet
from kimlik import yeni_cift_kimligi, yeni_kayit_kimligi


def cifti_kaydet(kamera, ayarlar: dict, log, kare1, z1, kare2, z2) -> int:
    """Çekilen kareleri kimlikleriyle kaydedip kuyruğa ekler; eklenen kare sayısını döndürür.

    Kimlik görüntü kaydedilmeden önce belirlenir, çünkü dosyanın adı kimliğin kendisidir.
    """
    tesis = ayarlar["tesis_kodu"]
    etiket = f"{tesis}/{kamera.kod}/{kamera.yatak}"
    kareler = [(1, kare1, z1), (2, kare2, z2)]
    if all(kare is None for _, kare, _ in kareler):
        return 0

    # Çiftin kimliği ilk karenin zamanıyla (ilk kare alınamadıysa bile çekim anı bellidir)
    cift_zamani = datetime.fromtimestamp(z1 if z1 is not None else z2)
    cift_id = yeni_cift_kimligi(tesis, kamera.kod, kamera.yatak, cift_zamani)

    eklenen = 0
    for sira, kare, z in kareler:
        if kare is None:
            log.debug(f"{etiket} | {sira}. kare alınamadı")
            continue
        zaman = datetime.fromtimestamp(z)

        def yol(ad, zaman=zaman):
            return goruntu_yolu(ad, kamera.yatak, zaman, format=ayarlar["format"])

        kayit_id = yeni_kayit_kimligi(tesis, kamera.kod, kamera.yatak, zaman, sira, yol)
        boyut = kaydet(kare, yol(kayit_id), kalite=ayarlar["kalite"])
        kuyruga_ekle(yol(kayit_id), tesis, kamera.kod, kamera.yatak,
                     zaman, sira, cift_id, kayit_id)
        eklenen += 1
        log.info(f"{etiket} | {sira}. kare kuyruğa eklendi ({boyut / 1024:.1f} KB)")
    return eklenen


def kamera_dongusu(kamera, ayarlar: dict, log, durum, dur: threading.Event):
    aralik = ayarlar["gonderim_araligi_sn"]
    gecikme = ayarlar["ikinci_cekim_gecikme_sn"]
    etiket = f"{ayarlar['tesis_kodu']}/{kamera.kod}/{kamera.yatak}"

    while not dur.is_set():
        baslangic = time.time()
        basarili_kare = 0
        try:
            kareler = kamera.cift_cekim(aralik_sn=gecikme)
            basarili_kare = cifti_kaydet(kamera, ayarlar, log, *kareler)
        except Exception:
            log.exception(f"{etiket} | beklenmeyen hata")

        durum.bildir(etiket, basarili=basarili_kare > 0, kaynak=kamera.kod)

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