"""Telefondan gelen fotoğrafı sisteme alma.

Gelen fotoğraf kamera görüntüsüyle AYNI yoldan gider: diske kaydedilir, ayarlardaki
biçim ve kaliteyle sıkıştırılır, M4 kuyruğuna eklenir. Tek farkı kaynağının "telefon"
olarak işaretlenmesi ve yükleyen kullanıcının kaydedilmesidir.

Gelen veri dışarıdandır, bu yüzden hiçbir şey varsayılmaz: boyutu sınırlıdır, türü
Pillow ile gerçekten açılarak doğrulanır (uzantıya ya da içerik türüne güvenilmez)
ve aynı kişi çok sık yükleyemez.
"""
import threading
import time
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from gonderici import kuyruga_ekle
from kaydedici import goruntu_yolu, kaydet
from kimlik import yeni_cift_kimligi, yeni_kayit_kimligi

# iPhone fotoğrafları (HEIC) için. Eklentinin native DLL'i yüklenemezse motor DURMAMALI:
# bu modül main.py'de loglama kurulmadan önce içe aktarılır, orada çıkan bir hata motoru
# hiçbir iz bırakmadan kapatır. HEIC isteğe bağlı bir ek: telefondan yükleme zaten
# varsayılan kapalı ve kapalı değilken de JPEG/PNG çalışmaya devam eder.
# Gerçek örnek: Windows Smart App Control _pillow_heif.pyd dosyasını engelledi ve
# motor.exe sessizce açılmaz oldu (9 Ekim 2026).
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_DESTEGI = True
except Exception:                       # ImportError, OSError, eklentinin kendi hataları
    HEIC_DESTEGI = False

KAYNAK = "telefon"
EN_BUYUK_BAYT = 15 * 1024 * 1024        # 15 MB
# HEIF yalnızca eklenti yüklendiyse kabul edilir; yoksa Pillow onu zaten açamaz
IZINLI_BICIMLER = ({"JPEG", "PNG", "MPO"}           # MPO: bazı telefonların çoklu JPEG'i
                   | ({"HEIF"} if HEIC_DESTEGI else set()))
EN_BUYUK_KENAR = 4096                   # çok büyük fotoğraf küçültülür

# Hız sınırı: aynı kişi + yatak için bu pencerede en fazla bu kadar yükleme
PENCERE_SN = 60
PENCEREDE_EN_FAZLA = 5


class YuklemeHatasi(Exception):
    """Kullanıcıya gösterilebilecek, ayrıntı sızdırmayan hata."""


def boyut_kontrol(veri: bytes):
    if not veri:
        raise YuklemeHatasi("Fotoğraf boş geldi.")
    if len(veri) > EN_BUYUK_BAYT:
        mb = EN_BUYUK_BAYT // (1024 * 1024)
        raise YuklemeHatasi(f"Fotoğraf çok büyük. En fazla {mb} MB olabilir.")


def goruntuyu_coz(veri: bytes) -> np.ndarray:
    """Baytları doğrulayıp OpenCV'nin kullandığı BGR diziye çevirir.

    Dosyayı gerçekten açar; sahte uzantı ya da bozuk dosya burada elenir.
    """
    boyut_kontrol(veri)
    from io import BytesIO
    try:
        with Image.open(BytesIO(veri)) as goruntu:
            bicim = goruntu.format
            if bicim not in IZINLI_BICIMLER:
                if bicim == "HEIF":      # eklenti yüklenemedi; neden olduğu söylenir
                    raise YuklemeHatasi("Bu bilgisayarda HEIC desteği açılamadı. "
                                        "Telefonunuzun kamera ayarından 'En Uyumlu' (JPEG) "
                                        "biçimini seçip yeniden deneyin.")
                raise YuklemeHatasi("Yalnızca JPEG, PNG ve HEIC fotoğraf gönderilebilir.")
            goruntu.load()                       # bozuk dosya burada hata verir
            duz = goruntu.convert("RGB")
            duz.thumbnail((EN_BUYUK_KENAR, EN_BUYUK_KENAR))
            dizi = np.array(duz)
    except YuklemeHatasi:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise YuklemeHatasi("Dosya okunamadı. Lütfen yeniden fotoğraf çekin.")
    return cv2.cvtColor(dizi, cv2.COLOR_RGB2BGR)


class Sinirlayici:
    """Aynı kişi + yatak için çok sık yüklemeyi engeller. Bellekte tutulur."""

    def __init__(self, pencere_sn: int = PENCERE_SN, en_fazla: int = PENCEREDE_EN_FAZLA):
        self.pencere_sn = pencere_sn
        self.en_fazla = en_fazla
        self._kayitlar = {}
        self._kilit = threading.Lock()

    def izin_var_mi(self, anahtar: str, simdi: float | None = None) -> bool:
        simdi = time.monotonic() if simdi is None else simdi
        with self._kilit:
            gecmis = [t for t in self._kayitlar.get(anahtar, []) if simdi - t < self.pencere_sn]
            if len(gecmis) >= self.en_fazla:
                self._kayitlar[anahtar] = gecmis
                return False
            gecmis.append(simdi)
            self._kayitlar[anahtar] = gecmis
            return True


def fotografi_al(veri: bytes, ayarlar: dict, kamera: dict, yukleyen: str, log,
                 zaman: datetime | None = None) -> str:
    """Fotoğrafı kaydeder ve kuyruğa ekler; kayit_id döndürür.

    Kamera döngüsündeki cifti_kaydet ile aynı adımları izler. Telefon tek kare
    gönderdiği için çift çekim yoktur; sıra her zaman 1'dir.
    """
    kare = goruntuyu_coz(veri)
    zaman = zaman or datetime.now()
    tesis = ayarlar["tesis_kodu"]
    kod, yatak = kamera["kod"], kamera["yatak"]

    cift_id = yeni_cift_kimligi(tesis, kod, yatak, zaman)

    def yol(ad):
        return goruntu_yolu(ad, yatak, zaman, format=ayarlar["format"])

    kayit_id = yeni_kayit_kimligi(tesis, kod, yatak, zaman, 1, yol)
    boyut = kaydet(kare, yol(kayit_id), kalite=ayarlar["kalite"])
    kuyruga_ekle(yol(kayit_id), tesis, kod, yatak, zaman, 1, cift_id, kayit_id,
                 kaynak=KAYNAK, yukleyen=yukleyen)
    log.info(f"{tesis}/{kod}/{yatak} | telefondan fotoğraf alındı "
             f"({boyut / 1024:.1f} KB) — {yukleyen}")
    return kayit_id
