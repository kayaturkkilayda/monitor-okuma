"""Eski görüntülerin temizlenmesi."""
import json
import shutil
from datetime import date, timedelta
from pathlib import Path

from gonderici import HATALI, KUYRUK


def _korunan_dosyalar() -> set[Path]:
    """Henüz merkeze ulaşmamış kayıtların görüntü dosyaları."""
    korunan = set()
    for klasor in (KUYRUK, HATALI):
        if not klasor.exists():
            continue
        for json_dosya in klasor.glob("*.json"):
            try:
                kayit = json.loads(json_dosya.read_text(encoding="utf-8"))
                korunan.add(Path(kayit["dosya"]).resolve())
            except (ValueError, KeyError, OSError):
                continue
    return korunan


def temizle(saklama_gun: int, log, klasor: str = "goruntuler"):
    """saklama_gun'den eski tarih klasörlerindeki görüntüleri siler.

    Kuyrukta veya hatalı klasöründe kaydı olan görüntülere dokunmaz.
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


def temizlik_dongusu(ayarlar: dict, log, dur):
    """Açılışta ve sonra her saat temizlik yapar."""
    while not dur.is_set():
        try:
            temizle(ayarlar.get("saklama_gun", 7), log)
        except Exception:
            log.exception("Temizlik sırasında hata")
        dur.wait(3600)