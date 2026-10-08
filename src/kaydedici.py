"""Kareyi diske kaydetme."""
from datetime import datetime
from pathlib import Path

import cv2
from PIL import Image      # AVIF desteği Pillow 12 ile birlikte gelir


def goruntu_yolu(ad: str, yatak_kod: str, zaman: datetime,
                 klasor: str = "goruntuler", format: str = "avif") -> Path:
    """goruntuler/<tarih>/<yatak>/<ad>.<format>  (ad = kayit_id)"""
    return Path(klasor) / zaman.strftime("%Y-%m-%d") / yatak_kod / f"{ad}.{format}"


def kaydet(kare, dosya: Path, kalite: int = 85) -> int:
    """Kareyi verilen yola kaydeder, boyutu (byte) döndürür."""
    dosya.parent.mkdir(parents=True, exist_ok=True)

    # OpenCV BGR tutar, Pillow RGB bekler
    goruntu = Image.fromarray(cv2.cvtColor(kare, cv2.COLOR_BGR2RGB))
    goruntu.save(dosya, quality=kalite)

    return dosya.stat().st_size
