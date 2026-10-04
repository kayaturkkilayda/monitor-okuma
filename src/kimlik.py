"""Okunabilir kayıt kimlikleri.

kayit_id : H01_K1_Y1_2026-10-02_15-12-13_1   (tesis_kamera_yatak_tarih_saat_sıra)
cift_id  : H01_K1_Y1_2026-10-02_15-12-13     (sırasız, çiftin ilk karesinin zamanıyla)
Görüntü dosyasının adı da kayit_id'dir. Aynı kimlik zaten varsa sonuna _2, _3 ... eklenir.
"""
import re
from datetime import datetime

from veritabani import baglan

# Windows dosya adında kullanılamayan karakterler ve boşluk kimlikte "-" olur
_UYGUNSUZ = re.compile(r'[<>:"/\\|?*\s]+')


def _temiz(kod) -> str:
    return _UYGUNSUZ.sub("-", str(kod).strip())


def cift_tabani(tesis: str, kamera: str, yatak: str, zaman: datetime) -> str:
    return "_".join((_temiz(tesis), _temiz(kamera), _temiz(yatak),
                     zaman.astimezone().strftime("%Y-%m-%d_%H-%M-%S")))


def kayit_tabani(tesis: str, kamera: str, yatak: str, zaman: datetime, sira: int) -> str:
    return f"{cift_tabani(tesis, kamera, yatak, zaman)}_{sira}"


def benzersiz(aday: str, dolu) -> str:
    """dolu(kimlik) True döndürdükçe sonuna _2, _3 ... ekler."""
    if not dolu(aday):
        return aday
    n = 2
    while dolu(f"{aday}_{n}"):
        n += 1
    return f"{aday}_{n}"


def _tabloda_var(sutun: str, deger: str) -> bool:
    with baglan() as db:
        return db.execute(f"SELECT 1 FROM kayitlar WHERE {sutun} = ? LIMIT 1",
                          (deger,)).fetchone() is not None


def yeni_cift_kimligi(tesis: str, kamera: str, yatak: str, zaman: datetime) -> str:
    return benzersiz(cift_tabani(tesis, kamera, yatak, zaman),
                     lambda k: _tabloda_var("cift_id", k))


def yeni_kayit_kimligi(tesis: str, kamera: str, yatak: str, zaman: datetime, sira: int,
                       dosya_yolu) -> str:
    """dosya_yolu(kimlik) → o kimlikle kaydedilecek görüntünün yolu.

    Kimlik ne tabloda ne de diskte kullanılmış olmalı; böylece eski bir görüntünün üzerine yazılmaz.
    """
    return benzersiz(kayit_tabani(tesis, kamera, yatak, zaman, sira),
                     lambda k: _tabloda_var("kayit_id", k) or dosya_yolu(k).exists())
