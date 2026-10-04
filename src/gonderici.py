"""Kuyruğa yazma ve kuyruktan M4'e gönderme.

Kuyruk, veritabanındaki kayitlar tablosudur. Durumu "bekliyor" olanlar sırada bekler;
gönderilenler "gonderildi", kalıcı hata alanlar "hatali" olarak geçmişte kalır.
"""
from datetime import datetime, timedelta
from pathlib import Path

import requests

from veritabani import baglan, olay
from zaman import db_zamani, iso_zaman, saat_dilimi, simdi

BEKLEME_SN = [10, 30, 60, 300, 900]
KALICI_HATA = {400, 401, 403, 404, 413, 422}
MIME = {"avif": "image/avif", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}
TUR_BASINA_KAYIT = 100

# M4'e olduğu gibi giden sütunlar ("zaman" ayrıca saat dilimli olarak eklenir)
API_ALANLARI = ("kayit_id", "cift_id", "tesis_kodu", "kamera_kodu", "yatak_kodu", "sira")


def kuyruga_ekle(dosya: Path, tesis: str, kamera: str, yatak: str,
                 zaman: datetime, sira: int, cift_id: str, kayit_id: str) -> str:
    """Kaydı "bekliyor" durumuyla ekler, kayit_id döndürür.

    Zaman yerel saatle okunur biçimde, saat dilimi ayrı sütunda saklanır.
    Kayıt çekildiği andan itibaren gönderilebilir (sonraki_deneme = çekim zamanı).
    """
    cekim = db_zamani(zaman)
    with baglan() as db:
        db.execute(
            "INSERT INTO kayitlar (kayit_id, cift_id, tesis_kodu, kamera_kodu, yatak_kodu,"
            " cekim_zamani, saat_dilimi, sira, dosya_yolu, dosya_boyutu, durum, sonraki_deneme)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'bekliyor', ?)",
            (kayit_id, cift_id, tesis, kamera, yatak, cekim, saat_dilimi(zaman), sira,
             str(dosya), Path(dosya).stat().st_size, cekim))
    return kayit_id


def _guncelle(kayit_id: str, **alanlar):
    atamalar = ", ".join(f"{ad} = ?" for ad in alanlar)
    with baglan() as db:
        db.execute(f"UPDATE kayitlar SET {atamalar} WHERE kayit_id = ?",
                   (*alanlar.values(), kayit_id))


def _gonder(kayit, ayarlar: dict) -> int:
    dosya = Path(kayit["dosya_yolu"])
    mime = MIME.get(dosya.suffix.lstrip(".").lower(), "application/octet-stream")
    with open(dosya, "rb") as f:
        yanit = requests.post(
            ayarlar["api_url"],
            headers={"X-API-Key": ayarlar["api_key"]},
            data={**{alan: kayit[alan] for alan in API_ALANLARI},
                  "zaman": iso_zaman(kayit["cekim_zamani"], kayit["saat_dilimi"])},
            files={"goruntu": (dosya.name, f, mime)},
            timeout=15,
        )
    return yanit.status_code


def _kaydi_isle(kayit_id: str, ayarlar: dict, log):
    """Kuyruktaki tek bir kaydı işler: gönderir, tekrar denemeye bırakır veya hatalı işaretler."""
    with baglan() as db:
        kayit = db.execute("SELECT * FROM kayitlar WHERE kayit_id = ?", (kayit_id,)).fetchone()
    if kayit is None or kayit["durum"] != "bekliyor" or simdi() < kayit["sonraki_deneme"]:
        return

    etiket = f"{kayit['tesis_kodu']}/{kayit['kamera_kodu']}/{kayit['yatak_kodu']} #{kayit['sira']}"
    kaynak = kayit["kamera_kodu"]

    if not Path(kayit["dosya_yolu"]).exists():
        _guncelle(kayit_id, durum="hatali", son_hata="görüntü dosyası bulunamadı")
        olay(log, "ERROR", kaynak, f"{etiket} | görüntü dosyası bulunamadı, kuyruktan çıkarıldı")
        return

    # Gönderim sırasında veritabanı kilitli tutulmaz; sonuç ayrı ve tek bir güncellemeyle yazılır
    try:
        kod = _gonder(kayit, ayarlar)
        neden = f"HTTP {kod}"
    except requests.RequestException as e:
        kod, neden = None, type(e).__name__

    if kod is not None and 200 <= kod < 300:
        # Önce kayıt işaretlenir, sonra görüntü silinir. Arada kesilirse görüntü sahipsiz kalır,
        # temizlik onu sonra siler; tersi olsaydı kuyrukta dosyası olmayan kayıt kalırdı.
        _guncelle(kayit_id, durum="gonderildi", gonderim_zamani=simdi())
        if ayarlar.get("gonderilince_sil", True):
            Path(kayit["dosya_yolu"]).unlink(missing_ok=True)
        log.info(f"{etiket} | gönderildi")
    elif kod in KALICI_HATA:
        _guncelle(kayit_id, durum="hatali", deneme=kayit["deneme"] + 1, son_hata=neden)
        olay(log, "ERROR", kaynak, f"{etiket} | kalıcı hata ({neden}), hatalı olarak işaretlendi")
    else:
        deneme = kayit["deneme"] + 1
        bekle = BEKLEME_SN[min(deneme - 1, len(BEKLEME_SN) - 1)]
        sonraki = db_zamani(datetime.now() + timedelta(seconds=bekle))
        _guncelle(kayit_id, deneme=deneme, sonraki_deneme=sonraki, son_hata=neden)
        olay(log, "WARNING", kaynak, f"{etiket} | gönderilemedi ({neden}), "
                                     f"{deneme}. deneme, {bekle} sn sonra tekrar")


def _siradakiler() -> list[str]:
    """Bekleme süresi dolmuş "bekliyor" kayıtları çekim sırasına göre döndürür."""
    with baglan() as db:
        satirlar = db.execute(
            "SELECT kayit_id FROM kayitlar WHERE durum = 'bekliyor' AND sonraki_deneme <= ?"
            " ORDER BY cekim_zamani, sira LIMIT ?",
            (simdi(), TUR_BASINA_KAYIT)).fetchall()
    return [s["kayit_id"] for s in satirlar]


def gonderici_dongusu(ayarlar: dict, log, dur):
    while not dur.is_set():
        try:
            siradakiler = _siradakiler()
        except Exception:
            olay(log, "ERROR", "sistem", "Gönderim kuyruğu okunamadı", ayrinti=True)
            siradakiler = []

        for kayit_id in siradakiler:
            if dur.is_set():
                break
            try:
                _kaydi_isle(kayit_id, ayarlar, log)
            except Exception:
                # Tek bir kayıttaki beklenmedik hata göndericiyi durdurmasın
                olay(log, "ERROR", "sistem", f"{kayit_id} | işlenirken beklenmeyen hata",
                     ayrinti=True)
        dur.wait(2)

