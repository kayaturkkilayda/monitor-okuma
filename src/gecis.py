"""Eski biçimlerden yeni biçime tek seferlik geçişler (motor açılışında çalışır).

1. Veritabanı sürüm 1 → 2: UUID kimlikler okunur kimliğe, ISO ve sayısal zamanlar
   okunur yerel saate çevrilir; diskteki görüntüler yeni kimlikle yeniden adlandırılır.
2. Eski JSON kuyruğu (bekleyen/, hatali/) → kayitlar tablosu, aynı dönüşümle.

İkisi de yarıda kesilirse bir sonraki açılışta kaldığı yerden güvenle tekrar çalışır.
"""
import json
from datetime import datetime
from pathlib import Path

from kimlik import benzersiz, cift_tabani, kayit_tabani
from veritabani import SURUM, baglan, olay, tablolari_olustur
from zaman import db_zamani, fark_metni, saat_dilimi

# Eski sürümün JSON kuyruk klasörleri
KUYRUK = Path("bekleyen")
HATALI = Path("hatali")


def _iso_coz(metin: str) -> tuple[datetime, str]:
    """'2026-10-01T15:22:10+03:00' → (2026-10-01 15:22:10 yerel saat, '+03:00')

    Saat, kaydedildiği yerel saatle aynen korunur; başka dilime çevrilmez.
    """
    zaman = datetime.fromisoformat(metin)
    dilim = fark_metni(zaman.utcoffset()) if zaman.tzinfo else saat_dilimi(zaman)
    return zaman.replace(tzinfo=None), dilim


def _sonraki_deneme(eski, cekim: str) -> str:
    """Eski sayısal zaman damgası → okunur zaman. 0 'hemen' demekti; çekim zamanı aynı işi görür."""
    if not eski or float(eski) <= 0:
        return cekim
    return db_zamani(datetime.fromtimestamp(float(eski)))


def _yeniden_adlandir(eski: Path, kayit_id: str, tasinanlar: list) -> Path:
    """Görüntüyü aynı klasörde kayit_id adıyla yeniden adlandırır, yeni yolu döndürür.

    Dosya yoksa (gönderilip silinmiş ya da yarım kalan önceki geçişte zaten taşınmışsa)
    yalnızca yeni yolu döndürür.
    """
    yeni = eski.with_name(kayit_id + eski.suffix)
    if yeni != eski and eski.exists():
        eski.rename(yeni)            # hedef varsa hata verir; hiçbir dosyanın üzerine yazılmaz
        tasinanlar.append((eski, yeni))
    return yeni


def _geri_al(tasinanlar: list):
    for eski, yeni in reversed(tasinanlar):
        try:
            yeni.rename(eski)
        except OSError:
            pass


def _cift_zamanlari(kayitlar: list[dict]) -> dict:
    """Her eski cift_id için çiftin ilk karesinin çekim zamanı (ISO metin)."""
    ilk = {}
    for k in sorted(kayitlar, key=lambda k: (k["cift_id"], k["sira"])):
        ilk.setdefault(k["cift_id"], k["cekim"])
    return ilk


# ---------- 1. Veritabanı sürüm 1 → 2 ----------

def _surum(db) -> int:
    return db.execute("PRAGMA user_version").fetchone()[0]


def _kayitlari_cevir(db, tasinanlar: list) -> int:
    db.execute("ALTER TABLE kayitlar RENAME TO kayitlar_eski")
    db.execute("DROP INDEX IF EXISTS ix_kayitlar_durum")
    db.execute("DROP INDEX IF EXISTS ix_kayitlar_cift")
    db.execute("DROP INDEX IF EXISTS ix_kayitlar_cekim")
    tablolari_olustur(db)

    satirlar = [dict(s) | {"cekim": s["cekim_zamani"]} for s in db.execute(
        "SELECT * FROM kayitlar_eski ORDER BY cekim_zamani, sira, rowid")]
    cift_zamani = _cift_zamanlari(satirlar)
    yeni_cift, kullanilan_cift, kullanilan_kayit = {}, set(), set()

    for s in satirlar:
        zaman, dilim = _iso_coz(s["cekim_zamani"])
        kodlar = (s["tesis_kodu"], s["kamera_kodu"], s["yatak_kodu"])

        if s["cift_id"] not in yeni_cift:
            cift_id = benzersiz(cift_tabani(*kodlar, _iso_coz(cift_zamani[s["cift_id"]])[0]),
                                kullanilan_cift.__contains__)
            kullanilan_cift.add(cift_id)
            yeni_cift[s["cift_id"]] = cift_id

        kayit_id = benzersiz(kayit_tabani(*kodlar, zaman, s["sira"]), kullanilan_kayit.__contains__)
        kullanilan_kayit.add(kayit_id)
        yol = _yeniden_adlandir(Path(s["dosya_yolu"]), kayit_id, tasinanlar)

        cekim = db_zamani(zaman)
        db.execute(
            "INSERT INTO kayitlar (kayit_id, cift_id, tesis_kodu, kamera_kodu, yatak_kodu,"
            " cekim_zamani, saat_dilimi, sira, dosya_yolu, dosya_boyutu, durum, deneme,"
            " sonraki_deneme, son_hata, gonderim_zamani)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (kayit_id, yeni_cift[s["cift_id"]], *kodlar, cekim, dilim, s["sira"], str(yol),
             s["dosya_boyutu"], s["durum"], s["deneme"],
             _sonraki_deneme(s["sonraki_deneme"], cekim), s["son_hata"],
             db_zamani(_iso_coz(s["gonderim_zamani"])[0]) if s["gonderim_zamani"] else None))

    db.execute("DROP TABLE kayitlar_eski")
    return len(satirlar)


def veritabanini_guncelle(log) -> int:
    """Sürüm 1 veritabanını sürüm 2'ye çevirir; çevrilen kayıt sayısını döndürür.

    Her şey tek bir işlemde yapılır: bir hata olursa veritabanı eski hâline döner ve
    o ana kadar yeniden adlandırılan görüntüler de eski adlarına geri alınır.
    """
    with baglan() as db:
        if _surum(db) >= SURUM:
            return 0

    tasinanlar = []
    try:
        with baglan() as db:
            db.execute("BEGIN IMMEDIATE")
            if _surum(db) >= SURUM:          # başka bir program bu arada çevirdiyse
                return 0
            sutunlar = {s["name"] for s in db.execute("PRAGMA table_info(kayitlar)")}
            sayi = 0 if "saat_dilimi" in sutunlar else _kayitlari_cevir(db, tasinanlar)
            db.execute("UPDATE olaylar SET zaman = replace(substr(zaman, 1, 19), 'T', ' ')"
                       " WHERE zaman LIKE '____-__-__T%'")
            db.execute(f"PRAGMA user_version = {SURUM}")
    except Exception:
        _geri_al(tasinanlar)
        raise

    olay(log, "INFO", "sistem", f"Veritabanı yeni biçime çevrildi: {sayi} kayıt, "
                                f"{len(tasinanlar)} görüntü yeniden adlandırıldı")
    return sayi


# ---------- 2. Eski JSON kuyruğu ----------

def _json_kayitlari_oku(log) -> list[dict]:
    kayitlar = []
    for klasor, durum in ((KUYRUK, "bekliyor"), (HATALI, "hatali")):
        if not klasor.is_dir():
            continue
        for json_dosya in sorted(klasor.glob("*.json")):
            try:
                k = json.loads(json_dosya.read_text(encoding="utf-8"))
                _iso_coz(k["zaman"])                  # zaman okunamıyorsa şimdiden ayıkla
                kayitlar.append(k | {"durum": durum, "json": json_dosya, "cekim": k["zaman"]})
            except Exception:
                olay(log, "ERROR", "sistem", f"{json_dosya} | eski kayıt aktarılamadı",
                     ayrinti=True)
    return kayitlar


def _baska_kayitta(kayit_id: str, yol: Path) -> bool:
    """Bu kimlik tabloda başka bir görüntüye mi ait? (Aynı görüntüyse yarım kalmış önceki aktarımdır.)"""
    with baglan() as db:
        satir = db.execute("SELECT dosya_yolu FROM kayitlar WHERE kayit_id = ?",
                           (kayit_id,)).fetchone()
    return satir is not None and satir["dosya_yolu"] != str(yol)


def eski_kuyrugu_aktar(log) -> int:
    """Eski sürümün bekleyen/ ve hatali/ klasörlerindeki JSON kayıtları tabloya aktarır.

    Sıra: görüntü yeniden adlandırılır → kayıt eklenir → JSON silinir. Arada kesilirse
    JSON yerinde kaldığı için sonraki açılışta aynı kimlikle tamamlanır, kayıt çoğalmaz.
    Okunamayan JSON yerinde bırakılır, diğerlerinin aktarılmasını engellemez.
    """
    kayitlar = sorted(_json_kayitlari_oku(log), key=lambda k: (k["zaman"], k["sira"]))
    cift_zamani = _cift_zamanlari(kayitlar)
    yeni_cift, kullanilan_cift, kullanilan_kayit = {}, set(), set()
    aktarilan = 0

    for k in kayitlar:
        try:
            zaman, dilim = _iso_coz(k["zaman"])
            kodlar = (k["tesis_kodu"], k["kamera_kodu"], k["yatak_kodu"])
            eski_yol = Path(k["dosya"])

            if k["cift_id"] not in yeni_cift:
                cift_id = benzersiz(cift_tabani(*kodlar, _iso_coz(cift_zamani[k["cift_id"]])[0]),
                                    kullanilan_cift.__contains__)
                kullanilan_cift.add(cift_id)
                yeni_cift[k["cift_id"]] = cift_id

            kayit_id = benzersiz(
                kayit_tabani(*kodlar, zaman, k["sira"]),
                lambda a: a in kullanilan_kayit or _baska_kayitta(a, eski_yol.with_name(a + eski_yol.suffix)))
            kullanilan_kayit.add(kayit_id)

            yol = _yeniden_adlandir(eski_yol, kayit_id, [])
            cekim = db_zamani(zaman)
            with baglan() as db:
                db.execute(
                    "INSERT OR IGNORE INTO kayitlar (kayit_id, cift_id, tesis_kodu, kamera_kodu,"
                    " yatak_kodu, cekim_zamani, saat_dilimi, sira, dosya_yolu, dosya_boyutu,"
                    " durum, deneme, sonraki_deneme, son_hata)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (kayit_id, yeni_cift[k["cift_id"]], *kodlar, cekim, dilim, k["sira"],
                     str(yol), yol.stat().st_size if yol.exists() else None, k["durum"],
                     k.get("deneme", 0), _sonraki_deneme(k.get("sonraki_deneme"), cekim),
                     "eski hatali/ klasöründen aktarıldı" if k["durum"] == "hatali" else None))
            k["json"].unlink()
            aktarilan += 1
        except Exception:
            olay(log, "ERROR", "sistem", f"{k['json']} | eski kayıt aktarılamadı", ayrinti=True)

    for klasor in (KUYRUK, HATALI):
        try:
            klasor.rmdir()           # yalnızca boşaldıysa kalkar
        except OSError:
            pass

    if aktarilan:
        olay(log, "INFO", "sistem", f"Eski kuyruktan {aktarilan} kayıt veritabanına aktarıldı")
    return aktarilan
