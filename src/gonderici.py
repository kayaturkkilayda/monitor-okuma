"""Kuyruğa yazma ve kuyruktan M4'e gönderme."""
import json
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

import requests

KUYRUK = Path("bekleyen")
HATALI = Path("hatali")
BEKLEME_SN = [10, 30, 60, 300, 900]
KALICI_HATA = {400, 401, 403, 404, 413, 422}
MIME = {"avif": "image/avif", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}


def _atomik_yaz(hedef: Path, veri: dict):
    """Önce geçici dosyaya yaz, sonra adını değiştir.

    Gönderici yarım yazılmış bir dosyayı asla okumaz.
    """
    gecici = hedef.with_suffix(".tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    gecici.replace(hedef)


def kuyruga_ekle(dosya: Path, tesis: str, kamera: str, yatak: str,
                 zaman: datetime, sira: int, cift_id: str):
    KUYRUK.mkdir(exist_ok=True)
    kayit = {
        "kayit_id": str(uuid.uuid4()),
        "cift_id": cift_id,
        "tesis_kodu": tesis,
        "kamera_kodu": kamera,
        "yatak_kodu": yatak,
        "zaman": zaman.astimezone().isoformat(timespec="seconds"),
        "sira": sira,
        "dosya": str(dosya),
        "deneme": 0,
        "sonraki_deneme": 0,
    }
    _atomik_yaz(KUYRUK / f"{kayit['kayit_id']}.json", kayit)


def _gonder(kayit: dict, ayarlar: dict) -> int:
    alanlar = ("kayit_id", "cift_id", "tesis_kodu", "kamera_kodu",
               "yatak_kodu", "zaman", "sira")
    dosya = Path(kayit["dosya"])
    mime = MIME.get(dosya.suffix.lstrip(".").lower(), "application/octet-stream")
    with open(dosya, "rb") as f:
        yanit = requests.post(
            ayarlar["api_url"],
            headers={"X-API-Key": ayarlar["api_key"]},
            data={k: kayit[k] for k in alanlar},
            files={"goruntu": (dosya.name, f, mime)},
            timeout=15,
        )
    return yanit.status_code


def _kaydi_isle(json_dosya: Path, ayarlar: dict, log):
    """Kuyruktaki tek bir kaydı işler: gönderir, tekrar dener veya hatalıya taşır."""
    kayit = json.loads(json_dosya.read_text(encoding="utf-8"))
    if time.time() < kayit["sonraki_deneme"]:
        return

    etiket = f"{kayit['tesis_kodu']}/{kayit['kamera_kodu']}/{kayit['yatak_kodu']} #{kayit['sira']}"

    if not Path(kayit["dosya"]).exists():
        log.error(f"{etiket} | görüntü dosyası bulunamadı, kuyruktan çıkarıldı")
        json_dosya.unlink()
        return

    try:
        kod = _gonder(kayit, ayarlar)
        neden = f"HTTP {kod}"
    except requests.RequestException as e:
        kod, neden = None, type(e).__name__

    if kod is not None and 200 <= kod < 300:
        json_dosya.unlink()
        if ayarlar.get("gonderilince_sil", True):
            Path(kayit["dosya"]).unlink(missing_ok=True)
        log.info(f"{etiket} | gönderildi")
    elif kod in KALICI_HATA:
        HATALI.mkdir(exist_ok=True)
        shutil.move(json_dosya, HATALI / json_dosya.name)
        log.error(f"{etiket} | kalıcı hata ({neden}), hatali/ klasörüne taşındı")
    else:
        kayit["deneme"] += 1
        bekle = BEKLEME_SN[min(kayit["deneme"] - 1, len(BEKLEME_SN) - 1)]
        kayit["sonraki_deneme"] = time.time() + bekle
        _atomik_yaz(json_dosya, kayit)
        log.warning(f"{etiket} | gönderilemedi ({neden}), "
                    f"{kayit['deneme']}. deneme, {bekle} sn sonra tekrar")


def gonderici_dongusu(ayarlar: dict, log, dur):
    KUYRUK.mkdir(exist_ok=True)
    while not dur.is_set():
        for json_dosya in sorted(KUYRUK.glob("*.json")):
            if dur.is_set():
                break
            try:
                _kaydi_isle(json_dosya, ayarlar, log)
            except Exception:
                # Tek bir kayıttaki beklenmedik hata göndericiyi durdurmasın
                log.exception(f"{json_dosya.name} | işlenirken beklenmeyen hata")
        dur.wait(2)