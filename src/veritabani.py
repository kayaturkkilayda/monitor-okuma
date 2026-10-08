"""SQLite veritabanı: gönderim kuyruğu ve geçmişi (kayitlar), olay günlüğü (olaylar).

Motor ve arayüz ayrı programlar olarak aynı dosyaya aynı anda erişebilir:
- WAL modu: okuyan yazanı, yazan okuyanı beklemez.
- busy_timeout: iki yazma çakışırsa ikincisi hemen hata vermez, sırasını bekler.
Her işlem kendi kısa ömürlü bağlantısını açar; iş parçacıkları bağlantı paylaşmaz.
"""
import sqlite3
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

from zaman import simdi

VERITABANI = Path("veri/monitor.db")
KILIT_BEKLEME_SN = 10     # veritabanı meşgulse en çok bu kadar beklenir
KAYIT_SAKLAMA_GUN = 90    # gönderilmiş kayıtlar tabloda kaç gün tutulsun (varsayılan)
SURUM = 2                 # 1: UUID kimlik + ISO zaman, 2: okunur kimlik + okunur yerel zaman

SEMA = """
CREATE TABLE IF NOT EXISTS kayitlar (
    kayit_id        TEXT PRIMARY KEY,
    cift_id         TEXT NOT NULL,
    tesis_kodu      TEXT NOT NULL,
    kamera_kodu     TEXT NOT NULL,
    yatak_kodu      TEXT NOT NULL,
    cekim_zamani    TEXT NOT NULL,
    saat_dilimi     TEXT NOT NULL,
    sira            INTEGER NOT NULL,
    dosya_yolu      TEXT NOT NULL,
    dosya_boyutu    INTEGER,
    durum           TEXT NOT NULL DEFAULT 'bekliyor'
                    CHECK (durum IN ('bekliyor', 'gonderildi', 'hatali')),
    deneme          INTEGER NOT NULL DEFAULT 0,
    sonraki_deneme  TEXT NOT NULL,
    son_hata        TEXT,
    gonderim_zamani TEXT,
    kaynak          TEXT NOT NULL DEFAULT 'kamera'    -- 'kamera' ya da 'telefon'
                    CHECK (kaynak IN ('kamera', 'telefon')),
    yukleyen        TEXT                              -- telefondan yükleyen kullanıcı
);
CREATE INDEX IF NOT EXISTS ix_kayitlar_durum ON kayitlar (durum, sonraki_deneme);
CREATE INDEX IF NOT EXISTS ix_kayitlar_cift ON kayitlar (cift_id);
CREATE INDEX IF NOT EXISTS ix_kayitlar_cekim ON kayitlar (cekim_zamani);

CREATE TABLE IF NOT EXISTS olaylar (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    zaman   TEXT NOT NULL,
    seviye  TEXT NOT NULL CHECK (seviye IN ('INFO', 'WARNING', 'ERROR')),
    kaynak  TEXT NOT NULL,
    mesaj   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_olaylar_zaman ON olaylar (zaman);

CREATE TABLE IF NOT EXISTS bildirimler (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    kamera_kodu      TEXT NOT NULL,
    tur              TEXT NOT NULL CHECK (tur IN ('ariza', 'duzeldi',
                                                  'gonderilemedi', 'm4_hata')),
    ariza_baslangic  TEXT NOT NULL DEFAULT '',   -- olayı tekilleştiren anahtar
    alicilar         TEXT NOT NULL,
    konu             TEXT NOT NULL,
    metin            TEXT NOT NULL,
    durum            TEXT NOT NULL DEFAULT 'bekliyor'
                     CHECK (durum IN ('bekliyor', 'gonderildi', 'vazgecildi')),
    deneme           INTEGER NOT NULL DEFAULT 0,
    sonraki_deneme   TEXT NOT NULL,
    son_hata         TEXT,
    olusturma_zamani TEXT NOT NULL,
    gonderim_zamani  TEXT,
    UNIQUE (kamera_kodu, tur, ariza_baslangic)      -- aynı arıza için tek mail
);
CREATE INDEX IF NOT EXISTS ix_bildirimler_durum ON bildirimler (durum, sonraki_deneme);

CREATE TABLE IF NOT EXISTS kullanicilar (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    eposta           TEXT NOT NULL UNIQUE COLLATE NOCASE,
    ad               TEXT NOT NULL,
    sifre_hash       TEXT NOT NULL,
    dogrulandi       INTEGER NOT NULL DEFAULT 0,
    yonetici         INTEGER NOT NULL DEFAULT 0,
    olusturma_zamani TEXT NOT NULL,
    son_giris        TEXT,
    hatali_deneme    INTEGER NOT NULL DEFAULT 0,
    kilit_bitis      TEXT
);

CREATE TABLE IF NOT EXISTS dogrulama_kodlari (
    eposta        TEXT NOT NULL COLLATE NOCASE,
    kod_hash      TEXT NOT NULL,
    amac          TEXT NOT NULL CHECK (amac IN ('kayit', 'sifirlama')),
    son_kullanma  TEXT NOT NULL,
    deneme        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (eposta, amac)          -- yeni kod istenince eskisinin yerine geçer
);

CREATE TABLE IF NOT EXISTS kamera_onay_kodlari (
    kamera_kodu    TEXT PRIMARY KEY,     -- kamera başına tek geçerli kod, yenisi eskisinin yerine geçer
    adres          TEXT NOT NULL,        -- kod bu adres için, adres değişirse kod geçmez
    eposta         TEXT NOT NULL,        -- onay mailinin gittiği adres (onaylayan bu olur)
    kod_hash       TEXT NOT NULL,
    son_kullanma   TEXT NOT NULL,
    deneme         INTEGER NOT NULL DEFAULT 0,
    gonderen       TEXT NOT NULL,        -- maili gönderten kullanıcı
    gonderim_zamani TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS oturumlar (   -- "Beni hatırla": cihazda saklanan anahtarın yalnızca hash'i
    token_hash       TEXT PRIMARY KEY,
    kullanici_id     INTEGER NOT NULL,
    olusturma_zamani TEXT NOT NULL,
    son_kullanma     TEXT NOT NULL
);
"""

_hazir = set()            # bu programda tabloları hazırlanmış veritabanı dosyaları
_hazir_kilit = threading.Lock()


def tablolari_olustur(db: sqlite3.Connection):
    """Eksik tablo ve indeksleri, açık olan işlemin içinde oluşturur."""
    for komut in SEMA.split(";"):
        if komut.strip():
            db.execute(komut)


def _kayit_sutunlarini_guncelle(db: sqlite3.Connection) -> bool:
    """Eski veritabanlarına kaynak ve yukleyen sütunlarını ekler.

    SQLite ALTER TABLE ADD COLUMN destekler; tabloyu yeniden kurmaya gerek yoktur.
    Var olan kayıtlar 'kamera' kaynağıyla kalır.
    """
    sutunlar = {s["name"] for s in db.execute("PRAGMA table_info(kayitlar)")}
    eklendi = False
    if "kaynak" not in sutunlar:
        db.execute("ALTER TABLE kayitlar ADD COLUMN kaynak TEXT NOT NULL DEFAULT 'kamera'")
        eklendi = True
    if "yukleyen" not in sutunlar:
        db.execute("ALTER TABLE kayitlar ADD COLUMN yukleyen TEXT")
        eklendi = True
    return eklendi


def _bildirim_turlerini_guncelle(db: sqlite3.Connection) -> bool:
    """Eski veritabanlarında bildirimler.tur yalnızca 'ariza' ve 'duzeldi' kabul ediyordu.

    SQLite'ta CHECK kuralı değiştirilemez; tablo yeniden kurulur, satırlar taşınır.
    Zaten yeni biçimdeyse hiçbir şey yapılmaz.
    """
    satir = db.execute("SELECT sql FROM sqlite_master WHERE type = 'table'"
                       " AND name = 'bildirimler'").fetchone()
    if satir is None or "gonderilemedi" in satir[0]:
        return False
    db.execute("ALTER TABLE bildirimler RENAME TO bildirimler_eski")
    # İndeks adı tablodan bağımsızdır; eskisi silinmezse yenisi oluşturulamaz
    db.execute("DROP INDEX IF EXISTS ix_bildirimler_durum")
    tablolari_olustur(db)
    db.execute("INSERT INTO bildirimler SELECT * FROM bildirimler_eski")
    db.execute("DROP TABLE bildirimler_eski")
    return True


def _hazirla(db: sqlite3.Connection, anahtar: str):
    """İlk bağlantıda WAL modunu açar ve eksik tabloları oluşturur.

    Yepyeni veritabanı doğrudan son sürümle başlar. Eski sürüm bir veritabanının
    dönüştürülmesi gecis.py'nin işidir; burada yalnızca eksik parçalar eklenir.
    """
    with _hazir_kilit:
        if anahtar in _hazir:
            return
        mod = db.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        db.execute("BEGIN IMMEDIATE")
        try:
            yeni = db.execute("SELECT 1 FROM sqlite_master WHERE name = 'kayitlar'").fetchone() is None
            tablolari_olustur(db)
            _bildirim_turlerini_guncelle(db)
            _kayit_sutunlarini_guncelle(db)
            if yeni:
                db.execute(f"PRAGMA user_version = {SURUM}")
            db.commit()
        except Exception:
            db.rollback()
            raise
        # Diğer program o an kilit tuttuğu için WAL'a geçilemediyse sonraki bağlantıda tekrar denenir
        if mod.lower() == "wal":
            _hazir.add(anahtar)


@contextmanager
def baglan(yol: Path | None = None):
    """Kısa ömürlü bağlantı açar.

    Blok hatasız biterse değişiklikler kaydedilir, hata olursa hepsi geri alınır.
    """
    yol = Path(yol or VERITABANI)
    yol.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(yol)
    try:
        db.execute(f"PRAGMA busy_timeout = {KILIT_BEKLEME_SN * 1000}")
        db.row_factory = sqlite3.Row
        _hazirla(db, str(yol.resolve()))
        with db:
            yield db
    finally:
        db.close()


def olay_ekle(seviye: str, kaynak: str, mesaj: str):
    with baglan() as db:
        db.execute("INSERT INTO olaylar (zaman, seviye, kaynak, mesaj) VALUES (?, ?, ?, ?)",
                   (simdi(), seviye, kaynak, mesaj))


_LOG_FONKSIYONU = {"INFO": "info", "WARNING": "warning", "ERROR": "error"}


def olay(log, seviye: str, kaynak: str, mesaj: str, ayrinti: bool = False):
    """Mesajı log dosyasına yazar, olaylar tablosuna da ekler.

    ayrinti=True yalnızca except bloğu içinden kullanılır: log dosyasına hatanın tam dökümü,
    tabloya yalnızca hatanın türü yazılır.
    Tabloya yazılamazsa çağıranı durdurmaz; log dosyasına not düşer.
    """
    if ayrinti:
        log.exception(mesaj)
        tur = sys.exc_info()[0]
        if tur is not None:
            mesaj = f"{mesaj} ({tur.__name__})"
    else:
        getattr(log, _LOG_FONKSIYONU[seviye])(mesaj)

    try:
        olay_ekle(seviye, kaynak, mesaj)
    except Exception as e:
        log.error(f"Olay veritabanına yazılamadı ({type(e).__name__})")
