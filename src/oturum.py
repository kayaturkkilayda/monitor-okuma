"""Beni hatırla: bu cihazda (Windows kullanıcı profilinde) kalıcı oturum.

Cihazda rastgele bir oturum anahtarı DPAPI ile şifrelenmiş olarak saklanır; veritabanında
yalnızca anahtarın SHA-256 hash'i durur. Veritabanını ele geçiren biri anahtarı elde edemez,
cihazdaki dosyayı kopyalayan biri de başka bilgisayarda çözemez (DPAPI o bilgisayara bağlı).
Her açılışta süre uzar; 30 gün hiç açılmazsa oturum düşer. "Çıkış" ve şifre sıfırlama oturumu kapatır.
"""
import hashlib
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from kullanicilar import _kullanici
from sifreleme import coz, sifrele
from veritabani import baglan
from zaman import db_zamani

OTURUM_DOSYASI = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "MonitorOkuma" / "oturum.dat"
GECERLILIK_GUN = 30


def _hash(anahtar: str) -> str:
    # Anahtar 256 bit rastgele olduğu için yavaş (scrypt) hash'e gerek yok
    return hashlib.sha256(anahtar.encode("ascii")).hexdigest()


def _dosyadaki_anahtar() -> str | None:
    try:
        return coz(OTURUM_DOSYASI.read_text(encoding="ascii").strip()) or None
    except Exception:
        return None


def _dosyayi_sil():
    try:
        OTURUM_DOSYASI.unlink(missing_ok=True)
    except OSError:
        pass


def hatirla(kullanici_id: int, simdi: datetime | None = None):
    """Bu cihaz için yeni oturum açar; varsa eskisini kapatır."""
    unut()
    simdi = simdi or datetime.now()
    anahtar = secrets.token_urlsafe(32)
    with baglan() as db:
        db.execute("INSERT INTO oturumlar (token_hash, kullanici_id, olusturma_zamani, son_kullanma)"
                   " VALUES (?, ?, ?, ?)", (_hash(anahtar), kullanici_id, db_zamani(simdi),
                                            db_zamani(simdi + timedelta(days=GECERLILIK_GUN))))
    OTURUM_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
    OTURUM_DOSYASI.write_text(sifrele(anahtar), encoding="ascii")


def hatirlanan_kullanici(simdi: datetime | None = None) -> dict | None:
    """Cihazda geçerli bir oturum varsa kullanıcıyı döndürür (süreyi uzatarak), yoksa None."""
    anahtar = _dosyadaki_anahtar()
    if not anahtar:
        return None
    simdi = simdi or datetime.now()
    with baglan() as db:
        satir = db.execute(
            "SELECT k.* FROM oturumlar o JOIN kullanicilar k ON k.id = o.kullanici_id"
            " WHERE o.token_hash = ? AND o.son_kullanma >= ? AND k.dogrulandi = 1",
            (_hash(anahtar), db_zamani(simdi))).fetchone()
        if satir is None:
            db.execute("DELETE FROM oturumlar WHERE token_hash = ?", (_hash(anahtar),))
        else:
            db.execute("UPDATE oturumlar SET son_kullanma = ? WHERE token_hash = ?",
                       (db_zamani(simdi + timedelta(days=GECERLILIK_GUN)), _hash(anahtar)))
            db.execute("UPDATE kullanicilar SET son_giris = ? WHERE id = ?", (db_zamani(simdi), satir["id"]))
    if satir is None:
        _dosyayi_sil()
        return None
    return _kullanici(satir)


def unut():
    """Bu cihazdaki oturumu kapatır ("Çıkış" ya da "Beni hatırla" işaretsiz giriş)."""
    anahtar = _dosyadaki_anahtar()
    if anahtar:
        try:
            with baglan() as db:
                db.execute("DELETE FROM oturumlar WHERE token_hash = ?", (_hash(anahtar),))
        except Exception:
            pass
    _dosyayi_sil()
