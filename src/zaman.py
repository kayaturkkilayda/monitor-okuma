"""Zaman biçimleri.

- Veritabanı : yerel saat, okunur  → 2026-10-02 15:12:13   (saat dilimi ayrı sütunda: +03:00)
- M4         : saat dilimli ISO    → 2026-10-02T15:12:13+03:00
- Ekran      : 02.10.2026 15:12:13
"""
from datetime import datetime, timedelta

DB_BICIMI = "%Y-%m-%d %H:%M:%S"
EKRAN_BICIMI = "%d.%m.%Y %H:%M:%S"


def db_zamani(zaman: datetime) -> str:
    """Bu bilgisayarın yerel saatiyle; saat dilimsiz zaman zaten yerel sayılır."""
    return zaman.astimezone().strftime(DB_BICIMI)


def simdi() -> str:
    return db_zamani(datetime.now())


def fark_metni(fark: timedelta) -> str:
    """UTC farkını +03:00 / -05:30 biçimine çevirir."""
    dakika = int(fark.total_seconds() // 60)
    isaret = "+" if dakika >= 0 else "-"
    return f"{isaret}{abs(dakika) // 60:02d}:{abs(dakika) % 60:02d}"


def saat_dilimi(zaman: datetime) -> str:
    """Zamanın bu bilgisayardaki saat dilimi, örn. +03:00."""
    return fark_metni(zaman.astimezone().utcoffset())


def iso_zaman(db_metni: str, dilim: str) -> str:
    """Veritabanındaki yerel saat + saat dilimi → M4'e giden ISO biçimi."""
    return db_metni.replace(" ", "T") + dilim


def ekran_zamani(metin: str | None) -> str:
    """Veritabanı ya da ISO biçimindeki zamanı ekranda GG.AA.YYYY SS:DD:ss olarak gösterir.

    Saat dilimli bir zaman çevrilmeden, kaydedildiği yerel saatle gösterilir.
    """
    if not metin:
        return ""
    try:
        return datetime.fromisoformat(metin).strftime(EKRAN_BICIMI)
    except ValueError:
        return metin
