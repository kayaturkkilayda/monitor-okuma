"""Eski görüntülerin ve eski gönderim kayıtlarının temizlenmesi."""
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from veritabani import KAYIT_SAKLAMA_GUN, baglan
from zaman import db_zamani


def _korunan_dosyalar() -> set[Path]:
    """Henüz merkeze ulaşmamış ("bekliyor" ya da "hatali") kayıtların görüntü dosyaları."""
    with baglan() as db:
        satirlar = db.execute("SELECT dosya_yolu FROM kayitlar"
                              " WHERE durum IN ('bekliyor', 'hatali')").fetchall()
    return {Path(s["dosya_yolu"]).resolve() for s in satirlar}


def temizle(saklama_gun: int, log, klasor: str = "goruntuler"):
    """saklama_gun'den eski tarih klasörlerindeki görüntüleri siler.

    Bekleyen veya hatalı kaydı olan görüntülere dokunmaz. Veritabanı okunamazsa
    hangi dosyaların korunacağı bilinemeyeceği için hiçbir şey silmez.
    """
    kok = Path(klasor)
    if not kok.exists():
        return

    sinir = date.today() - timedelta(days=saklama_gun)
    korunan = _korunan_dosyalar()
    silinen = atlanan = 0

    for gun_klasoru in kok.iterdir():
        try:
            gun = date.fromisoformat(gun_klasoru.name)
        except ValueError:
            continue                     # tarih adlı olmayan klasörlere dokunma
        if gun >= sinir:
            continue

        for dosya in gun_klasoru.rglob("*.*"):
            if dosya.resolve() in korunan:
                atlanan += 1
            else:
                dosya.unlink(missing_ok=True)
                silinen += 1

        # Klasör tamamen boşaldıysa kaldır
        if not any(gun_klasoru.rglob("*.*")):
            shutil.rmtree(gun_klasoru, ignore_errors=True)

    if silinen or atlanan:
        log.info(f"Temizlik: {silinen} görüntü silindi, "
                 f"{atlanan} görüntü gönderilmeyi beklediği için tutuldu")


def eski_kayitlari_sil(kayit_saklama_gun: int, log) -> int:
    """Gönderileli kayit_saklama_gun'den fazla olmuş kayıtları tablodan siler."""
    # Zamanlar aynı okunur biçimde (YYYY-MM-DD SS:DD:ss) olduğu için metin karşılaştırması yeterli
    sinir = db_zamani(datetime.now() - timedelta(days=int(kayit_saklama_gun)))
    with baglan() as db:
        silinen = db.execute("DELETE FROM kayitlar WHERE durum = 'gonderildi'"
                             " AND gonderim_zamani < ?", (sinir,)).rowcount
    if silinen:
        log.info(f"Temizlik: {silinen} eski gönderim kaydı veritabanından silindi")
    return silinen


def eski_bildirimleri_sil(saklama_gun: int, log) -> int:
    """Gönderilmiş ya da vazgeçilmiş, saklama_gun'den eski bildirim maillerini siler.

    Bekleyen bildirimlere dokunmaz.
    """
    sinir = db_zamani(datetime.now() - timedelta(days=int(saklama_gun)))
    with baglan() as db:
        silinen = db.execute("DELETE FROM bildirimler WHERE durum != 'bekliyor'"
                             " AND olusturma_zamani < ?", (sinir,)).rowcount
    if silinen:
        log.info(f"Temizlik: {silinen} eski bildirim kaydı veritabanından silindi")
    return silinen


def temizlik_dongusu(ayarlar: dict, log, dur):
    """Açılışta ve sonra her saat temizlik yapar."""
    while not dur.is_set():
        try:
            temizle(ayarlar.get("saklama_gun", 7), log)
        except Exception:
            log.exception("Temizlik sırasında hata")
        saklama = ayarlar.get("kayit_saklama_gun", KAYIT_SAKLAMA_GUN)
        try:
            eski_kayitlari_sil(saklama, log)
        except Exception:
            log.exception("Eski kayıtlar silinirken hata")
        try:
            eski_bildirimleri_sil(saklama, log)
        except Exception:
            log.exception("Eski bildirimler silinirken hata")
        dur.wait(3600)
