"""Loglama ayarları."""
import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def log_kur(klasor: str = "loglar", seviye=logging.INFO) -> logging.Logger:
    """Dosyaya (ve konsol varsa ekrana) yazan logger kurar.

    Her gece yarısı yeni log dosyası açılır, 30 günden eskiler silinir.
    """
    Path(klasor).mkdir(exist_ok=True)

    logger = logging.getLogger("monitor")
    logger.setLevel(seviye)
    if logger.handlers:
        return logger

    bicim = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s",
                              datefmt="%Y-%m-%d %H:%M:%S")

    dosya = TimedRotatingFileHandler(Path(klasor) / "monitor.log",
                                     when="midnight", backupCount=30, encoding="utf-8")
    dosya.setFormatter(bicim)
    logger.addHandler(dosya)

    if sys.stderr:                      # konsolsuz EXE'de ekran yok
        terminal = logging.StreamHandler()
        terminal.setFormatter(bicim)
        logger.addHandler(terminal)

    return logger