"""Loglama ayarları."""
import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def log_kur(klasor: str = "loglar", seviye=logging.INFO, ad: str = "monitor",
            dosya_adi: str = "monitor.log") -> logging.Logger:
    """Dosyaya (ve konsol varsa ekrana) yazan logger kurar.

    Her gece yarısı yeni log dosyası açılır, 30 günden eskiler silinir.
    Motor ve arayüz ayrı dosyaya yazar: iki program aynı dosyayı döndürmeye çalışmasın.
    """
    Path(klasor).mkdir(exist_ok=True)

    logger = logging.getLogger(ad)
    logger.setLevel(seviye)
    if logger.handlers:
        return logger

    bicim = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s",
                              datefmt="%Y-%m-%d %H:%M:%S")

    dosya = TimedRotatingFileHandler(Path(klasor) / dosya_adi,
                                     when="midnight", backupCount=30, encoding="utf-8")
    dosya.setFormatter(bicim)
    logger.addHandler(dosya)

    if sys.stderr:                      # konsolsuz EXE'de ekran yok
        terminal = logging.StreamHandler()
        terminal.setFormatter(bicim)
        logger.addHandler(terminal)

    return logger