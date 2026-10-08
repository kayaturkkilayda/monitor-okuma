"""Telefondaki oturum.

Masaüstündeki "Beni hatırla" ile aynı yöntem kullanılır (bkz. oturum.py): telefona
rastgele bir anahtar çerez olarak verilir, veritabanında yalnızca anahtarın SHA-256
hash'i durur. Veritabanını okuyan biri anahtarı elde edemez.

Bu yöntem imzalı çerezden daha güvenlidir: sunucuda bir imza anahtarı saklamak
gerekmez ve oturum veritabanından tek satır silinerek kapatılabilir.
"""
import hashlib
import secrets
from datetime import datetime, timedelta

from kullanicilar import _kullanici
from veritabani import baglan
from zaman import db_zamani

CEREZ_ADI = "monitor_telefon"
GECERLILIK_SAAT = 12        # vardiya boyu yeter; ertesi gün yeniden giriş istenir


def _hash(anahtar: str) -> str:
    # Anahtar 256 bit rastgele; yavaş (scrypt) hash'e gerek yok
    return hashlib.sha256(anahtar.encode("ascii")).hexdigest()


def oturum_ac(kullanici_id: int, simdi: datetime | None = None) -> str:
    """Yeni oturum açar ve telefona verilecek anahtarı döndürür."""
    simdi = simdi or datetime.now()
    anahtar = secrets.token_urlsafe(32)
    with baglan() as db:
        db.execute("INSERT INTO oturumlar (token_hash, kullanici_id, olusturma_zamani,"
                   " son_kullanma) VALUES (?, ?, ?, ?)",
                   (_hash(anahtar), kullanici_id, db_zamani(simdi),
                    db_zamani(simdi + timedelta(hours=GECERLILIK_SAAT))))
    return anahtar


def kullanici(anahtar: str | None, simdi: datetime | None = None) -> dict | None:
    """Anahtar geçerliyse kullanıcıyı döndürür, değilse None. Süreyi uzatmaz."""
    if not anahtar:
        return None
    simdi = simdi or datetime.now()
    with baglan() as db:
        satir = db.execute(
            "SELECT k.* FROM oturumlar o JOIN kullanicilar k ON k.id = o.kullanici_id"
            " WHERE o.token_hash = ? AND o.son_kullanma >= ? AND k.dogrulandi = 1",
            (_hash(anahtar), db_zamani(simdi))).fetchone()
    return _kullanici(satir) if satir else None


def oturum_kapat(anahtar: str | None):
    if not anahtar:
        return
    with baglan() as db:
        db.execute("DELETE FROM oturumlar WHERE token_hash = ?", (_hash(anahtar),))


def suresi_gecenleri_sil(simdi: datetime | None = None) -> int:
    """Süresi dolmuş oturumları temizler; silinen satır sayısını döndürür."""
    simdi = simdi or datetime.now()
    with baglan() as db:
        return db.execute("DELETE FROM oturumlar WHERE son_kullanma < ?",
                          (db_zamani(simdi),)).rowcount
