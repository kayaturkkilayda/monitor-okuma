import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

import gecis
from veritabani import SURUM, baglan
from zaman import db_zamani


class SahteLog:
    def __init__(self):
        self.mesajlar = []

    def info(self, m): self.mesajlar.append(m)
    def warning(self, m): self.mesajlar.append(m)
    def error(self, m): self.mesajlar.append(m)
    def exception(self, m): self.mesajlar.append(m)


def kayit(kayit_id):
    with baglan() as db:
        satir = db.execute("SELECT * FROM kayitlar WHERE kayit_id = ?", (kayit_id,)).fetchone()
    return dict(satir) if satir else None


def kayit_sayisi():
    with baglan() as db:
        return db.execute("SELECT COUNT(*) FROM kayitlar").fetchone()[0]


# ====================== Veritabanı sürüm 1 → 2 ======================

ESKI_SEMA = """
CREATE TABLE kayitlar (
    kayit_id TEXT PRIMARY KEY, cift_id TEXT NOT NULL, tesis_kodu TEXT NOT NULL,
    kamera_kodu TEXT NOT NULL, yatak_kodu TEXT NOT NULL, cekim_zamani TEXT NOT NULL,
    sira INTEGER NOT NULL, dosya_yolu TEXT NOT NULL, dosya_boyutu INTEGER,
    durum TEXT NOT NULL DEFAULT 'bekliyor', deneme INTEGER NOT NULL DEFAULT 0,
    sonraki_deneme REAL NOT NULL DEFAULT 0, son_hata TEXT, gonderim_zamani TEXT);
CREATE INDEX ix_kayitlar_durum ON kayitlar (durum, sonraki_deneme);
CREATE TABLE olaylar (id INTEGER PRIMARY KEY AUTOINCREMENT, zaman TEXT NOT NULL,
    seviye TEXT NOT NULL, kaynak TEXT NOT NULL, mesaj TEXT NOT NULL);
"""

SONRAKI = datetime(2026, 10, 2, 16, 0, 0).timestamp()


@pytest.fixture
def eski_db(gecici_veritabani, tmp_path):
    """Sürüm 1 (UUID + ISO zaman) bir veritabanı ve eski adlı görüntüler kurar."""
    klasor = tmp_path / "goruntuler" / "2026-10-02"
    (klasor / "Y1").mkdir(parents=True)
    (klasor / "Y2").mkdir(parents=True)
    g1 = klasor / "Y1" / "K1_15-12-13.avif"
    g2 = klasor / "Y1" / "K1_15-12-18.avif"          # gönderilip silinmiş, diskte yok
    g3 = klasor / "Y2" / "K2_15-12-13.avif"
    g1.write_bytes(b"1")
    g3.write_bytes(b"3")

    gecici_veritabani.parent.mkdir(parents=True)
    db = sqlite3.connect(gecici_veritabani)
    db.executescript(ESKI_SEMA)
    satir = ("INSERT INTO kayitlar (kayit_id, cift_id, tesis_kodu, kamera_kodu, yatak_kodu,"
             " cekim_zamani, sira, dosya_yolu, dosya_boyutu, durum, deneme, sonraki_deneme,"
             " son_hata, gonderim_zamani) VALUES (?, ?, 'H01', ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)")
    db.execute(satir, ("uuid-1", "cift-a", "K1", "Y1", "2026-10-02T15:12:13+03:00", 1, str(g1),
                       "bekliyor", 0, 0, None, None))
    db.execute(satir, ("uuid-2", "cift-a", "K1", "Y1", "2026-10-02T15:12:18+03:00", 2, str(g2),
                       "gonderildi", 1, 0, "HTTP 503", "2026-10-02T15:12:20+03:00"))
    # Başka saat dilimindeki bir kurulumdan (Kazakistan, +05:00)
    db.execute(satir, ("uuid-3", "cift-b", "K2", "Y2", "2026-10-02T15:12:13+05:00", 1, str(g3),
                       "hatali", 3, SONRAKI, "HTTP 401", None))
    db.execute("INSERT INTO olaylar (zaman, seviye, kaynak, mesaj)"
               " VALUES ('2026-10-02T14:47:02+03:00', 'INFO', 'sistem', 'Motor başladı')")
    db.commit()
    db.close()
    return {"g1": g1, "g2": g2, "g3": g3, "klasor": klasor}


def test_eski_veritabani_yeni_bicime_cevrilir(eski_db):
    log = SahteLog()
    assert gecis.veritabanini_guncelle(log) == 3

    k1 = kayit("H01_K1_Y1_2026-10-02_15-12-13_1")
    k2 = kayit("H01_K1_Y1_2026-10-02_15-12-18_2")
    k3 = kayit("H01_K2_Y2_2026-10-02_15-12-13_1")
    assert kayit("uuid-1") is None
    # Çift, ilk karenin zamanıyla
    assert k1["cift_id"] == k2["cift_id"] == "H01_K1_Y1_2026-10-02_15-12-13"
    assert k3["cift_id"] == "H01_K2_Y2_2026-10-02_15-12-13"
    # Zamanlar okunur yerel saat, dilim ayrı sütunda ve kaydedildiği gibi
    assert (k1["cekim_zamani"], k1["saat_dilimi"]) == ("2026-10-02 15:12:13", "+03:00")
    assert (k3["cekim_zamani"], k3["saat_dilimi"]) == ("2026-10-02 15:12:13", "+05:00")
    assert k1["sonraki_deneme"] == "2026-10-02 15:12:13"          # eskiden 0 = hemen
    assert k3["sonraki_deneme"] == db_zamani(datetime.fromtimestamp(SONRAKI))
    assert k2["gonderim_zamani"] == "2026-10-02 15:12:20"
    # Diğer alanlar aynen korunur
    assert (k2["durum"], k2["deneme"], k2["son_hata"]) == ("gonderildi", 1, "HTTP 503")
    assert (k3["durum"], k3["deneme"], k3["son_hata"]) == ("hatali", 3, "HTTP 401")
    # Olaylar tablosu da çevrilir
    with baglan() as db:
        assert db.execute("SELECT zaman FROM olaylar").fetchone()[0] == "2026-10-02 14:47:02"
        assert db.execute("PRAGMA user_version").fetchone()[0] == SURUM
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name = 'kayitlar_eski'").fetchone() is None
    assert any("2 görüntü yeniden adlandırıldı" in m for m in log.mesajlar)


def test_diskteki_goruntuler_yeni_adla_yeniden_adlandirilir(eski_db):
    gecis.veritabanini_guncelle(SahteLog())
    k1 = kayit("H01_K1_Y1_2026-10-02_15-12-13_1")
    k3 = kayit("H01_K2_Y2_2026-10-02_15-12-13_1")
    assert not eski_db["g1"].exists() and not eski_db["g3"].exists()
    assert Path(k1["dosya_yolu"]) == eski_db["klasor"] / "Y1" / "H01_K1_Y1_2026-10-02_15-12-13_1.avif"
    assert Path(k1["dosya_yolu"]).read_bytes() == b"1"
    assert Path(k3["dosya_yolu"]).read_bytes() == b"3"
    # Gönderilip silinmiş görüntünün kaydı da tutarlı ada geçer
    k2 = kayit("H01_K1_Y1_2026-10-02_15-12-18_2")
    assert Path(k2["dosya_yolu"]).name == "H01_K1_Y1_2026-10-02_15-12-18_2.avif"


def test_ikinci_calistirmada_hicbir_sey_yapmaz(eski_db):
    gecis.veritabanini_guncelle(SahteLog())
    log = SahteLog()
    assert gecis.veritabanini_guncelle(log) == 0
    assert kayit_sayisi() == 3
    assert log.mesajlar == []


def test_hata_olursa_veritabani_ve_dosyalar_eski_haline_doner(eski_db):
    # Üçüncü kaydın yeni adında beklenmedik bir dosya var: yeniden adlandırma başarısız olur
    engel = eski_db["klasor"] / "Y2" / "H01_K2_Y2_2026-10-02_15-12-13_1.avif"
    engel.write_bytes(b"engel")

    with pytest.raises(OSError):
        gecis.veritabanini_guncelle(SahteLog())

    assert eski_db["g1"].exists()                     # önceden adlandırılan geri alındı
    assert not (eski_db["klasor"] / "Y1" / "H01_K1_Y1_2026-10-02_15-12-13_1.avif").exists()
    assert engel.read_bytes() == b"engel"             # hiçbir dosyanın üzerine yazılmadı
    with baglan() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] < SURUM
        assert db.execute("SELECT COUNT(*) FROM kayitlar WHERE kayit_id LIKE 'uuid-%'").fetchone()[0] == 3


def test_yarida_kalmis_gecis_tamamlanir(eski_db):
    """Önceki denemede dosya yeniden adlandırılmış ama veritabanı kaydedilememiş (elektrik kesintisi)."""
    yeni = eski_db["g1"].with_name("H01_K1_Y1_2026-10-02_15-12-13_1.avif")
    eski_db["g1"].rename(yeni)
    gecis.veritabanini_guncelle(SahteLog())
    assert kayit("H01_K1_Y1_2026-10-02_15-12-13_1")["dosya_yolu"] == str(yeni)
    assert yeni.exists()


def test_eski_kayitlarda_ayni_kimlik_cikarsa_ek_alir(eski_db, gecici_veritabani):
    db = sqlite3.connect(gecici_veritabani)
    db.execute("INSERT INTO kayitlar (kayit_id, cift_id, tesis_kodu, kamera_kodu, yatak_kodu,"
               " cekim_zamani, sira, dosya_yolu) VALUES ('uuid-4', 'cift-c', 'H01', 'K1', 'Y1',"
               " '2026-10-02T15:12:13+03:00', 1, ?)", (str(eski_db["klasor"] / "Y1" / "yok.avif"),))
    db.commit()
    db.close()
    gecis.veritabanini_guncelle(SahteLog())
    assert kayit("H01_K1_Y1_2026-10-02_15-12-13_1") is not None
    assert kayit("H01_K1_Y1_2026-10-02_15-12-13_1_2") is not None
    with baglan() as db:
        ciftler = {s[0] for s in db.execute("SELECT DISTINCT cift_id FROM kayitlar WHERE kamera_kodu = 'K1'")}
    assert ciftler == {"H01_K1_Y1_2026-10-02_15-12-13", "H01_K1_Y1_2026-10-02_15-12-13_2"}


# ====================== Eski JSON kuyruğu ======================

@pytest.fixture
def json_ortam(tmp_path, monkeypatch):
    monkeypatch.setattr(gecis, "KUYRUK", tmp_path / "bekleyen")
    monkeypatch.setattr(gecis, "HATALI", tmp_path / "hatali")
    return tmp_path


def eski_json(klasor, goruntu, kayit_id, zaman="2026-10-01T15:22:10+03:00", sira=1, **ek):
    klasor.mkdir(exist_ok=True)
    veri = {"kayit_id": kayit_id, "cift_id": "c", "tesis_kodu": "H01", "kamera_kodu": "K3",
            "yatak_kodu": "Y3", "zaman": zaman, "sira": sira,
            "dosya": str(goruntu), "deneme": 0, "sonraki_deneme": 0, **ek}
    dosya = klasor / f"{kayit_id}.json"
    dosya.write_text(json.dumps(veri), encoding="utf-8")
    return dosya


def test_eski_json_kayitlar_tabloya_aktarilir(json_ortam):
    tmp_path = json_ortam
    g1 = tmp_path / "K3_15-22-10.avif"
    g2 = tmp_path / "K3_15-22-15.avif"
    g1.write_bytes(b"12345")
    g2.write_bytes(b"x")
    b = eski_json(tmp_path / "bekleyen", g1, "uuid-b", deneme=2, sonraki_deneme=SONRAKI)
    h = eski_json(tmp_path / "hatali", g2, "uuid-h", zaman="2026-10-01T15:22:15+03:00", sira=2)

    assert gecis.eski_kuyrugu_aktar(SahteLog()) == 2

    k = kayit("H01_K3_Y3_2026-10-01_15-22-10_1")
    assert (k["durum"], k["deneme"]) == ("bekliyor", 2)
    assert k["sonraki_deneme"] == db_zamani(datetime.fromtimestamp(SONRAKI))
    assert (k["cekim_zamani"], k["saat_dilimi"]) == ("2026-10-01 15:22:10", "+03:00")
    assert Path(k["dosya_yolu"]) == tmp_path / "H01_K3_Y3_2026-10-01_15-22-10_1.avif"
    assert Path(k["dosya_yolu"]).exists() and not g1.exists()
    assert k["dosya_boyutu"] == 5
    k2 = kayit("H01_K3_Y3_2026-10-01_15-22-15_2")
    assert k2["durum"] == "hatali"
    assert k["cift_id"] == k2["cift_id"] == "H01_K3_Y3_2026-10-01_15-22-10"
    assert not b.exists() and not h.exists()
    assert not (tmp_path / "bekleyen").exists()     # boşalan eski klasörler kalkar
    assert not (tmp_path / "hatali").exists()


def test_gecis_tekrar_calisirsa_kayit_cogalmaz(json_ortam):
    """Görüntü taşınıp kayıt eklenmiş ama JSON silinemeden kesilmiş gibi: aynı JSON tekrar gelir."""
    tmp_path = json_ortam
    goruntu = tmp_path / "K3.avif"
    goruntu.write_bytes(b"x")
    eski_json(tmp_path / "bekleyen", goruntu, "ayni-id")
    gecis.eski_kuyrugu_aktar(SahteLog())
    json_dosya = eski_json(tmp_path / "bekleyen", goruntu, "ayni-id")
    gecis.eski_kuyrugu_aktar(SahteLog())
    assert kayit_sayisi() == 1
    assert kayit("H01_K3_Y3_2026-10-01_15-22-10_1") is not None
    assert not json_dosya.exists()


def test_gecis_bozuk_jsonu_birakir_digerlerini_aktarir(json_ortam):
    tmp_path = json_ortam
    goruntu = tmp_path / "K3.avif"
    goruntu.write_bytes(b"x")
    bozuk = tmp_path / "bekleyen" / "0-bozuk.json"
    eski_json(tmp_path / "bekleyen", goruntu, "saglam")
    bozuk.write_text("{yarım", encoding="utf-8")

    log = SahteLog()
    assert gecis.eski_kuyrugu_aktar(log) == 1
    assert kayit("H01_K3_Y3_2026-10-01_15-22-10_1")["durum"] == "bekliyor"
    assert bozuk.exists()                           # silinmez, elle incelenebilir
    assert any("aktarılamadı" in m for m in log.mesajlar)


def test_eski_klasor_yoksa_gecis_sessizce_gecer(json_ortam):
    log = SahteLog()
    assert gecis.eski_kuyrugu_aktar(log) == 0
    assert log.mesajlar == []
