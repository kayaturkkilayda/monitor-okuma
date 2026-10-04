import os
import sys
import threading
import time
from pathlib import Path

# EXE'yken EXE'nin klasörü, normal çalışırken bu dosyanın klasörü
KOK = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
os.chdir(KOK)
sys.path.insert(0, str(KOK / "src"))

from ayarlar import AYAR_DOSYASI, ayarlari_oku, degisen_alanlar, kameralari_olustur
from durum import KameraDurumu
from gecis import eski_kuyrugu_aktar, veritabanini_guncelle
from gonderici import gonderici_dongusu
from log import log_kur
from onay import onayli_kameralar
from temizlik import temizlik_dongusu
from veritabani import olay
from zamanlayici import baslat

KONTROL_SN = 5
ONAYSIZ_BILDIRILEN = set()   # onaysız kameralar motor açık kaldıkça yalnızca bir kez bildirilir

log = log_kur()
durum = KameraDurumu(log)


def calistir(ayarlar: dict):
    """Kameraları, göndericiyi ve temizliği başlatır. Onaysız kameradan çekim yapılmaz."""
    onaylilar = onayli_kameralar(ayarlar["kameralar"], log, ONAYSIZ_BILDIRILEN)
    kameralar = kameralari_olustur({**ayarlar, "kameralar": onaylilar})
    olay(log, "INFO", "sistem", f"{ayarlar['tesis_kodu']} | {len(kameralar)} kamera başlatılıyor")
    dur, is_parcaciklari = baslat(kameralar, ayarlar, log, durum)

    if ayarlar["api_url"]:
        g = threading.Thread(target=gonderici_dongusu, args=(ayarlar, log, dur),
                             name="gonderici", daemon=True)
        g.start()
        is_parcaciklari.append(g)
    else:
        olay(log, "WARNING", "sistem", "api_url boş; görüntüler kuyrukta birikecek")

    t = threading.Thread(target=temizlik_dongusu, args=(ayarlar, log, dur),
                         name="temizlik", daemon=True)
    t.start()
    is_parcaciklari.append(t)
    return dur, is_parcaciklari


def durdur(dur, is_parcaciklari):
    dur.set()
    for th in is_parcaciklari:
        th.join(timeout=15)


def degisim_zamani() -> float | None:
    try:
        return AYAR_DOSYASI.stat().st_mtime
    except OSError:
        return None


olay(log, "INFO", "sistem", "Motor başladı")
try:
    veritabanini_guncelle(log)
except Exception:
    # Yarım dönüşümle çalışmaktansa dur; Görev Zamanlayıcı yeniden başlatınca tekrar denenir
    olay(log, "ERROR", "sistem", "Veritabanı yeni biçime çevrilemedi, motor durduruluyor",
         ayrinti=True)
    raise
eski_kuyrugu_aktar(log)
ayarlar = ayarlari_oku()
son_degisim = degisim_zamani()
dur, is_parcaciklari = calistir(ayarlar)

try:
    while True:
        time.sleep(KONTROL_SN)
        simdiki = degisim_zamani()
        if simdiki is None or simdiki == son_degisim:
            continue
        son_degisim = simdiki

        # Önce yeni ayarları dene; bozuksa çalışan sistemi durdurma
        try:
            yeni = ayarlari_oku()
            kameralari_olustur(yeni)
        except Exception:
            olay(log, "ERROR", "sistem", "Yeni ayarlar okunamadı, eski ayarlarla devam ediliyor",
                 ayrinti=True)
            continue

        degisen = ", ".join(degisen_alanlar(ayarlar, yeni)) or "yok"
        olay(log, "INFO", "sistem", f"Ayarlar değişti (değişen: {degisen}), yeniden başlatılıyor...")
        durdur(dur, is_parcaciklari)
        ayarlar = yeni
        dur, is_parcaciklari = calistir(ayarlar)

except KeyboardInterrupt:
    olay(log, "INFO", "sistem", "Motor durduruluyor...")
    durdur(dur, is_parcaciklari)
    olay(log, "INFO", "sistem", "Motor durduruldu")