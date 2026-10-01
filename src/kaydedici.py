"""Kareyi diske kaydetme."""
from datetime import datetime
from pathlib import Path

import cv2
from PIL import Image
import pillow_avif  # noqa: F401  AVIF desteğini Pillow'a ekler


def kaydet(kare, kamera_kod: str, yatak_kod: str, zaman: datetime,
           klasor: str = "goruntuler", format: str = "avif",
           kalite: int = 85) -> tuple[Path, int]:
    """Kareyi kaydeder. (dosya yolu, boyut byte) döndürür."""
    hedef = Path(klasor) / zaman.strftime("%Y-%m-%d") / yatak_kod
    hedef.mkdir(parents=True, exist_ok=True)

    dosya = hedef / f"{kamera_kod}_{zaman.strftime('%H-%M-%S')}.{format}"

    # OpenCV BGR tutar, Pillow RGB bekler
    goruntu = Image.fromarray(cv2.cvtColor(kare, cv2.COLOR_BGR2RGB))
    goruntu.save(dosya, quality=kalite)

    return dosya, dosya.stat().st_size