"""Kuyruğa yazma ve kuyruktan M4'e gönderme.

Kuyruk, veritabanındaki kayitlar tablosudur. Durumu "bekliyor" olanlar sırada bekler;
gönderilenler "gonderildi", kalıcı hata alanlar "hatali" olarak geçmişte kalır.
"""
import base64
import io as _io
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import requests
from PIL import Image

from veritabani import baglan, olay
from zaman import db_zamani, saat_dilimi, simdi

BEKLEME_SN = [10, 30, 60, 300, 900]

# Tekrar denemenin düzeltemeyeceği hatalar; kayıt "hatali" olarak kuyruktan çıkar.
# 401/403 ayrıca ele alınır (anahtar hatası, e-posta gider).
KALICI_HATA = {400, 401, 403, 404, 413, 422}
YETKI_HATASI = {401, 403}

TUR_BASINA_KAYIT = 100

# M4 gövdesindeki alan adları birebir böyledir; değiştirilmemeli.
M4_FORMATI = "jpeg"                 # ayar avif olsa bile M4'e jpeg gider
JPEG_KALITESI = 90
ZAMAN_BICIMI = "%Y-%m-%dT%H:%M:%S"  # sonuna .mmm eklenir, saat dilimi eki YOKTUR

AYAR_EKSIK = "M4 adresi/anahtarı ayarlanmamış"


def kuyruga_ekle(dosya: Path, tesis: str, kamera: str, yatak: str,
                 zaman: datetime, sira: int, cift_id: str, kayit_id: str,
                 kaynak: str = "kamera", yukleyen: str | None = None) -> str:
    """Kaydı "bekliyor" durumuyla ekler, kayit_id döndürür.

    Zaman yerel saatle okunur biçimde, saat dilimi ayrı sütunda saklanır.
    Kayıt çekildiği andan itibaren gönderilebilir (sonraki_deneme = çekim zamanı).
    """
    cekim = db_zamani(zaman)
    with baglan() as db:
        db.execute(
            "INSERT INTO kayitlar (kayit_id, cift_id, tesis_kodu, kamera_kodu, yatak_kodu,"
            " cekim_zamani, saat_dilimi, sira, dosya_yolu, dosya_boyutu, durum, sonraki_deneme,"
            " kaynak, yukleyen, capture_id, cekim_ms)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'bekliyor', ?, ?, ?, ?, ?)",
            (kayit_id, cift_id, tesis, kamera, yatak, cekim, saat_dilimi(zaman), sira,
             str(dosya), Path(dosya).stat().st_size, cekim, kaynak, yukleyen,
             str(uuid.uuid4()), zaman.microsecond // 1000))
    return kayit_id


def kamera_m4_id(ayarlar: dict, kamera_kodu: str):
    """Kameranın M4 kimliği (sayı) ya da girilmemişse None.

    Ayarlarda kullanıcının girdiği değerdir; koda gömülü bir eşleme yoktur.
    """
    for k in ayarlar.get("kameralar", []):
        if str(k.get("kod", "")).strip() == kamera_kodu:
            deger = str(k.get("m4_id", "")).strip()
            if not deger:
                return None
            try:
                return int(deger)
            except ValueError:
                return None
    return None


def _hata_anahtari(neden: str, zaman: datetime) -> str:
    """Aynı sebep, aynı kamera, aynı gün için tek mail gider.

    M4 uzun süre kapalı kalırsa her görüntü için ayrı mail gitmesini engeller;
    sorun ertesi gün de sürüyorsa yeniden hatırlatılır.
    """
    return f"{neden} {zaman:%Y-%m-%d}"


def _guncelle(kayit_id: str, **alanlar):
    atamalar = ", ".join(f"{ad} = ?" for ad in alanlar)
    with baglan() as db:
        db.execute(f"UPDATE kayitlar SET {atamalar} WHERE kayit_id = ?",
                   (*alanlar.values(), kayit_id))


def m4_zamani(cekim_zamani: str, ms: int) -> str:
    """Veritabanındaki yerel saat + milisaniye → M4'ün beklediği biçim.

    "2026-10-09 07:48:43" + 650 → "2026-10-09T07:48:43.650"
    Yerel saattir; M4 bu alanda saat dilimi eki beklemez.
    """
    return f"{cekim_zamani.replace(' ', 'T')}.{int(ms) % 1000:03d}"


def jpeg_base64(dosya: Path) -> str:
    """Görüntüyü JPEG'e çevirip öneksiz base64 döndürür.

    Ayar avif olsa bile M4'e jpeg gider. Dosya zaten JPEG ise yeniden sıkıştırılmaz;
    gereksiz kalite kaybı olmaz.
    """
    ham = dosya.read_bytes()
    with Image.open(_io.BytesIO(ham)) as goruntu:
        if goruntu.format == "JPEG":
            return base64.b64encode(ham).decode("ascii")
        tampon = _io.BytesIO()
        goruntu.convert("RGB").save(tampon, format="JPEG", quality=JPEG_KALITESI)
    return base64.b64encode(tampon.getvalue()).decode("ascii")


def m4_govdesi(kayit, kamera_id: int, dosya: Path) -> dict:
    """M4'e gönderilecek JSON gövdesi. Alan adları birebir böyledir."""
    return {
        "captureId": kayit["capture_id"],
        "kameraKodu": kayit["kamera_kodu"],
        "kameraId": int(kamera_id),
        "yatakEslesmeKodu": kayit["yatak_kodu"],
        "goruntuCekilmeZamani": m4_zamani(kayit["cekim_zamani"], kayit["cekim_ms"]),
        "goruntuFormati": M4_FORMATI,
        "goruntuBase64": jpeg_base64(dosya),
    }


def _gonder(ayarlar: dict, govde: dict) -> int:
    """Kullanıcının girdiği adrese AYNEN POST eder; koda yol ya da anahtar yazılmaz."""
    yanit = requests.post(
        ayarlar["api_url"],
        headers={"X-Api-Key": ayarlar["api_key"],
                 "Content-Type": "application/json"},
        json=govde,
        timeout=30,
    )
    return yanit.status_code


def _tekrar_dene(kayit_id: str, deneme: int, neden: str | None = None) -> tuple[int, int]:
    """Kaydı artan bir bekleme sonrasına erteler. (yeni deneme sayısı, bekleme sn) döner."""
    yeni = deneme + 1
    bekle = BEKLEME_SN[min(yeni - 1, len(BEKLEME_SN) - 1)]
    _guncelle(kayit_id, deneme=yeni,
              sonraki_deneme=db_zamani(datetime.now() + timedelta(seconds=bekle)),
              **({"son_hata": neden} if neden else {}))
    return yeni, bekle


def _kaydi_isle(kayit_id: str, ayarlar: dict, log, bildirici=None):
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
        if bildirici:
            bildirici.hata_olayi("gonderilemedi", kaynak,
                                 _hata_anahtari("dosya yok", datetime.now()),
                                 "Görüntü dosyası bulunamadı, kayıt kuyruktan çıkarıldı.")
        return

    # Adres ya da anahtar girilmemişse hiç denenmez; kayıt kuyrukta bekler
    if not str(ayarlar.get("api_url", "")).strip() or not str(ayarlar.get("api_key", "")).strip():
        olay(log, "WARNING", kaynak, f"{etiket} | {AYAR_EKSIK}")
        _tekrar_dene(kayit_id, kayit["deneme"])
        return

    kamera_id = kamera_m4_id(ayarlar, kayit["kamera_kodu"])
    if kamera_id is None:
        olay(log, "WARNING", kaynak,
             f"{etiket} | M4 kamera ID girilmemiş; Ayarlar'dan kameraya ID verin")
        _tekrar_dene(kayit_id, kayit["deneme"])
        return

    # Görüntüyü okuyup JPEG'e çevirmek ağa çıkmadan önce yapılır: buradaki bir hata
    # gönderim hatası değildir, dosya bozuk demektir. HTTP çağrısıyla karıştırılmamalı.
    try:
        govde = m4_govdesi(kayit, kamera_id, Path(kayit["dosya_yolu"]))
    except (OSError, ValueError):
        _guncelle(kayit_id, durum="hatali", son_hata="görüntü hazırlanamadı")
        olay(log, "ERROR", kaynak, f"{etiket} | görüntü JPEG'e çevrilemedi, kuyruktan çıkarıldı",
             ayrinti=True)
        return

    # Gönderim sırasında veritabanı kilitli tutulmaz; sonuç ayrı ve tek bir güncellemeyle yazılır
    try:
        kod = _gonder(ayarlar, govde)
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
    elif kod in YETKI_HATASI:
        # Anahtar yanlışsa tekrar denemek düzeltmez; yöneticinin Ayarlar'dan düzeltmesi gerekir
        _guncelle(kayit_id, durum="hatali", deneme=kayit["deneme"] + 1, son_hata=neden)
        olay(log, "ERROR", kaynak, f"{etiket} | API anahtarı hatalı ({neden})")
        if bildirici:
            bildirici.hata_olayi("m4_hata", kaynak,
                                 _hata_anahtari("api anahtari", datetime.now()),
                                 "M4 API anahtarı kabul edilmedi. Ayarlar sekmesinden "
                                 "doğru anahtarı girin.")
    elif kod in KALICI_HATA:
        # 400: gövde M4'ün beklediği biçimde değil. Tekrar denemek aynı sonucu verir.
        _guncelle(kayit_id, durum="hatali", deneme=kayit["deneme"] + 1, son_hata=neden)
        olay(log, "ERROR", kaynak, f"{etiket} | kalıcı hata ({neden}), hatalı olarak işaretlendi")
        if bildirici and kod != 400:
            bildirici.hata_olayi("m4_hata", kaynak, _hata_anahtari(neden, datetime.now()),
                                 f"{etiket} gönderilemedi: {neden}")
    else:
        # 5xx, zaman aşımı, ağ hatası: geçici sayılır, artan aralıklarla tekrar denenir
        deneme, bekle = _tekrar_dene(kayit_id, kayit["deneme"], neden)
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


def gonderici_dongusu(ayarlar: dict, log, dur, bildirici=None):
    """bildirici: kırmızı hatalarda sorumlu kullanıcıya mail atan nesne (yoksa yalnızca log)."""
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
                _kaydi_isle(kayit_id, ayarlar, log, bildirici)
            except Exception:
                # Tek bir kayıttaki beklenmedik hata göndericiyi durdurmasın
                olay(log, "ERROR", "sistem", f"{kayit_id} | işlenirken beklenmeyen hata",
                     ayrinti=True)
        dur.wait(2)

