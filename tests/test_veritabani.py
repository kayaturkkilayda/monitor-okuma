import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import veritabani as v


class SahteLog:
    def __init__(self):
        self.mesajlar = []

    def info(self, m): self.mesajlar.append(("INFO", m))
    def warning(self, m): self.mesajlar.append(("WARNING", m))
    def error(self, m): self.mesajlar.append(("ERROR", m))
    def exception(self, m): self.mesajlar.append(("EXCEPTION", m))


def olaylar():
    with v.baglan() as db:
        return [dict(s) for s in db.execute("SELECT * FROM olaylar ORDER BY id")]


# ---------- Bağlantı ve şema ----------

def test_ilk_acilista_klasor_ve_tablolar_olusur(gecici_veritabani):
    assert not gecici_veritabani.parent.exists()
    with v.baglan() as db:
        tablolar = {s[0] for s in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert gecici_veritabani.exists()
    assert {"kayitlar", "olaylar"} <= tablolar


def test_kayitlar_tablosunun_sutunlari():
    with v.baglan() as db:
        sutunlar = [s["name"] for s in db.execute("PRAGMA table_info(kayitlar)")]
    assert sutunlar == ["kayit_id", "cift_id", "tesis_kodu", "kamera_kodu", "yatak_kodu",
                        "cekim_zamani", "saat_dilimi", "sira", "dosya_yolu", "dosya_boyutu",
                        "durum", "deneme", "sonraki_deneme", "son_hata", "gonderim_zamani"]


def test_yeni_veritabani_son_surumle_baslar():
    with v.baglan() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == v.SURUM


def test_wal_modu_ve_busy_timeout_acik():
    with v.baglan() as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] == v.KILIT_BEKLEME_SN * 1000


def test_tablolar_tekrar_acilista_korunur(gecici_veritabani):
    v.olay_ekle("INFO", "sistem", "ilk")
    v._hazir.clear()                     # programın yeniden açılması gibi
    v.olay_ekle("INFO", "sistem", "ikinci")
    assert [o["mesaj"] for o in olaylar()] == ["ilk", "ikinci"]


def test_hata_olursa_yarim_islem_geri_alinir():
    with pytest.raises(RuntimeError):
        with v.baglan() as db:
            db.execute("INSERT INTO olaylar (zaman, seviye, kaynak, mesaj)"
                       " VALUES ('z', 'INFO', 'sistem', 'yarım')")
            raise RuntimeError("işlemin ortasında hata")
    assert olaylar() == []


def test_gecersiz_durum_kabul_edilmez():
    with pytest.raises(sqlite3.IntegrityError):
        with v.baglan() as db:
            db.execute("INSERT INTO kayitlar (kayit_id, cift_id, tesis_kodu, kamera_kodu,"
                       " yatak_kodu, cekim_zamani, sira, dosya_yolu, durum)"
                       " VALUES ('1', 'c', 'H01', 'K1', 'Y1', 'z', 1, 'd', 'kayboldu')")


# ---------- Olaylar ----------

def test_olay_hem_loga_hem_tabloya_yazar():
    log = SahteLog()
    v.olay(log, "WARNING", "K1", "H01/K1/Y1 | uyarı")
    assert log.mesajlar == [("WARNING", "H01/K1/Y1 | uyarı")]
    o = olaylar()[0]
    assert (o["seviye"], o["kaynak"], o["mesaj"]) == ("WARNING", "K1", "H01/K1/Y1 | uyarı")
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", o["zaman"])   # okunur yerel saat


def test_ayrintili_olay_tabloya_hata_turunu_yazar():
    log = SahteLog()
    try:
        raise ValueError("ayrıntı")
    except ValueError:
        v.olay(log, "ERROR", "sistem", "bir şey bozuldu", ayrinti=True)
    assert log.mesajlar == [("EXCEPTION", "bir şey bozuldu")]
    assert olaylar()[0]["mesaj"] == "bir şey bozuldu (ValueError)"


def test_olay_tabloya_yazilamazsa_cagirani_durdurmaz(monkeypatch):
    def kilitli(*a):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(v, "olay_ekle", kilitli)
    log = SahteLog()
    v.olay(log, "ERROR", "K1", "ARIZA")          # hata fırlatmamalı
    assert log.mesajlar[0] == ("ERROR", "ARIZA")
    assert "yazılamadı" in log.mesajlar[1][1]


# ---------- Motor ve arayüz aynı anda ----------

# Ayrı bir programda (motor gibi) çalışır: gerçek kuyruga_ekle ile kayıt ekler, sonra gönderir gibi günceller
MOTOR = r"""
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, sys.argv[2])
import veritabani, gonderici
veritabani.VERITABANI = Path(sys.argv[1])
goruntu = Path(sys.argv[3])
for i in range(int(sys.argv[4])):
    kid = gonderici.kuyruga_ekle(goruntu, "H01", "K1", "Y1", datetime.now(), 1, f"c{i}", f"k{i}")
    if i % 2:
        gonderici._guncelle(kid, durum="gonderildi", gonderim_zamani=veritabani.simdi())
"""


def test_motor_ve_arayuz_ayni_anda_erisebilir(gecici_veritabani, tmp_path):
    adet = 400
    goruntu = tmp_path / "K1.avif"
    goruntu.write_bytes(b"x")
    src = Path(__file__).resolve().parents[1] / "src"

    # Veritabanı henüz yok: iki program onu aynı anda ilk kez açmaya çalışır
    motor = subprocess.Popen(
        [sys.executable, "-c", MOTOR, str(gecici_veritabani), str(src), str(goruntu), str(adet)],
        stderr=subprocess.PIPE, text=True)

    # Bu süreç arayüz gibi davranır: sürekli okur, araya kendi yazmalarını da katar
    ara_sayilar, yazilan_olay = set(), 0
    while motor.poll() is None:
        with v.baglan() as db:
            ara_sayilar.add(db.execute("SELECT COUNT(*) FROM kayitlar").fetchone()[0])
            db.execute("SELECT * FROM kayitlar WHERE durum = 'bekliyor'"
                       " ORDER BY cekim_zamani LIMIT 50").fetchall()
        v.olay_ekle("INFO", "sistem", "arayüz yazdı")
        yazilan_olay += 1

    _, hata = motor.communicate()
    assert motor.returncode == 0, hata
    assert any(0 < n < adet for n in ara_sayilar), "iki program gerçekten aynı anda çalışmadı"
    with v.baglan() as db:
        assert db.execute("SELECT COUNT(*) FROM kayitlar").fetchone()[0] == adet
        assert db.execute("SELECT COUNT(*) FROM kayitlar WHERE durum = 'gonderildi'"
                          ).fetchone()[0] == adet // 2
    assert len(olaylar()) == yazilan_olay


def test_sema_yorumlarinda_noktali_virgul_yok():
    """Şema ';' ile bölünüp komut komut çalıştırılıyor; yorumdaki ';' komutu ortadan keser."""
    import re
    assert [y for y in re.findall(r"--[^\n]*", v.SEMA) if ";" in y] == []


# ---------- bildirimler tablosunun yeni türlere açılması ----------

ESKI_BILDIRIMLER = """
CREATE TABLE bildirimler (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    kamera_kodu      TEXT NOT NULL,
    tur              TEXT NOT NULL CHECK (tur IN ('ariza', 'duzeldi')),
    ariza_baslangic  TEXT NOT NULL DEFAULT '',
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
    UNIQUE (kamera_kodu, tur, ariza_baslangic)
);
CREATE INDEX ix_bildirimler_durum ON bildirimler (durum, sonraki_deneme);
"""

ESKI_SATIR = ("K1", "ariza", "2026-10-04 10:00:00", "bt@ornek.com", "konu", "metin",
              "2026-10-04 10:00:00", "2026-10-04 10:00:00")
EKLE = ("INSERT INTO bildirimler (kamera_kodu, tur, ariza_baslangic, alicilar, konu, metin,"
        " sonraki_deneme, olusturma_zamani) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")


def _eski_veritabani_kur(yol: Path):
    """Eski sürümdeki bildirimler tablosuyla bir veritabanı oluşturur."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(yol)
    try:
        db.executescript(ESKI_BILDIRIMLER)
        db.execute(EKLE, ESKI_SATIR)
        db.commit()
    finally:
        db.close()


def test_eski_bildirimler_tablosu_yeni_turlere_acilir(gecici_veritabani):
    _eski_veritabani_kur(gecici_veritabani)
    with v.baglan() as db:
        db.execute(EKLE, ("K1", "m4_hata", "HTTP 401", "a@b.co", "k", "m",
                          "2026-10-07 10:00:00", "2026-10-07 10:00:00"))
    with v.baglan() as db:
        turler = [s["tur"] for s in db.execute("SELECT tur FROM bildirimler ORDER BY id")]
    assert turler == ["ariza", "m4_hata"]          # eski satır korundu, yenisi kabul edildi


def test_gecis_sonrasi_indeks_yerinde(gecici_veritabani):
    _eski_veritabani_kur(gecici_veritabani)
    with v.baglan() as db:
        indeksler = [s["name"] for s in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'bildirimler'")]
    assert "ix_bildirimler_durum" in indeksler


def test_gecis_tekrar_calistirilinca_bir_sey_yapmaz(gecici_veritabani):
    """Her açılışta çalışır; zaten yeni biçimdeyse dokunmaz."""
    _eski_veritabani_kur(gecici_veritabani)
    with v.baglan() as db:
        assert v._bildirim_turlerini_guncelle(db) is False   # ilk bağlantıda çevrildi
