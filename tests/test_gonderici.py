import re
from datetime import datetime, timedelta

import pytest
import requests

import gonderici as g
from kimlik import cift_tabani, kayit_tabani
from veritabani import baglan
from zaman import DB_BICIMI, db_zamani, saat_dilimi, simdi

OKUNUR = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")     # 2026-10-01 10:00:00


class SahteLog:
    def __init__(self):
        self.mesajlar = []

    def info(self, m): self.mesajlar.append(m)
    def warning(self, m): self.mesajlar.append(m)
    def error(self, m): self.mesajlar.append(m)
    def exception(self, m): self.mesajlar.append(m)


class TekTur:
    """Gönderici döngüsünü tek tur çalıştırıp durduran sahte 'dur' sinyali."""

    def __init__(self):
        self.bitti = False

    def is_set(self): return self.bitti
    def wait(self, sn): self.bitti = True


AYARLAR = {"api_url": "http://test", "api_key": "x", "gonderilince_sil": True}


def kayit(kayit_id):
    with baglan() as db:
        return dict(db.execute("SELECT * FROM kayitlar WHERE kayit_id = ?", (kayit_id,)).fetchone())


def olaylar():
    with baglan() as db:
        return [dict(s) for s in db.execute("SELECT * FROM olaylar ORDER BY id")]


def beklemeyi_atla(kayit_id, sonraki="2000-01-01 00:00:00"):
    with baglan() as db:
        db.execute("UPDATE kayitlar SET sonraki_deneme = ? WHERE kayit_id = ?", (sonraki, kayit_id))


def goruntu_ve_kayit(tmp_path, zaman=datetime(2026, 10, 1, 10, 0, 0), sira=1):
    kayit_id = kayit_tabani("H01", "K1", "Y1", zaman, sira)
    goruntu = tmp_path / f"{kayit_id}.avif"
    goruntu.write_bytes(b"sahte goruntu")
    cift_id = cift_tabani("H01", "K1", "Y1", zaman)
    return g.kuyruga_ekle(goruntu, "H01", "K1", "Y1", zaman, sira, cift_id, kayit_id), goruntu


@pytest.fixture
def ortam(tmp_path):
    """Geçici klasörde bir görüntü oluşturup kuyruğa ekler."""
    kayit_id, goruntu = goruntu_ve_kayit(tmp_path)
    return kayit_id, goruntu, SahteLog(), tmp_path


def api_cevabi(monkeypatch, kod=None, hata=None):
    """Gerçek gönderim yerine sabit bir cevap döndüren sahte fonksiyon koyar."""
    def sahte_gonder(kayit, ayarlar):
        if hata:
            raise hata
        return kod
    monkeypatch.setattr(g, "_gonder", sahte_gonder)


# ---------- Kuyruğa ekleme ----------

def test_kuyruga_ekle_dogru_alanlari_yazar(ortam):
    kayit_id, goruntu, _, _ = ortam
    k = kayit(kayit_id)
    assert k["kayit_id"] == "H01_K1_Y1_2026-10-01_10-00-00_1"
    assert k["cift_id"] == "H01_K1_Y1_2026-10-01_10-00-00"
    assert k["tesis_kodu"] == "H01"
    assert k["kamera_kodu"] == "K1"
    assert k["yatak_kodu"] == "Y1"
    assert k["sira"] == 1
    assert k["deneme"] == 0
    assert k["durum"] == "bekliyor"
    assert k["dosya_yolu"] == str(goruntu)
    assert goruntu.stem == k["kayit_id"]          # dosya adı = kimlik
    assert k["dosya_boyutu"] == len(b"sahte goruntu")
    assert k["gonderim_zamani"] is None


def test_veritabaninda_zamanlar_okunur_yerel_saat(ortam):
    kayit_id, _, _, _ = ortam
    k = kayit(kayit_id)
    assert k["cekim_zamani"] == "2026-10-01 10:00:00"     # T harfi ve +03:00 yok
    assert k["saat_dilimi"] == saat_dilimi(datetime(2026, 10, 1, 10, 0, 0))
    assert re.fullmatch(r"[+-]\d\d:\d\d", k["saat_dilimi"])
    assert k["sonraki_deneme"] == k["cekim_zamani"]       # çekildiği andan itibaren gönderilebilir


# ---------- Tek kaydın işlenmesi ----------

def test_basarili_gonderim_gecmiste_kalir_ve_goruntuyu_siler(ortam, monkeypatch):
    kayit_id, goruntu, log, _ = ortam
    api_cevabi(monkeypatch, kod=201)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    k = kayit(kayit_id)                     # kayıt silinmez, geçmiş olarak kalır
    assert k["durum"] == "gonderildi"
    assert OKUNUR.match(k["gonderim_zamani"])
    assert not goruntu.exists()


def test_gonderilince_sil_kapaliysa_goruntu_kalir(ortam, monkeypatch):
    kayit_id, goruntu, log, _ = ortam
    api_cevabi(monkeypatch, kod=201)
    g._kaydi_isle(kayit_id, {**AYARLAR, "gonderilince_sil": False}, log)
    assert kayit(kayit_id)["durum"] == "gonderildi"
    assert goruntu.exists()


def test_gecici_hata_kuyrukta_tutar_ve_bekletir(ortam, monkeypatch):
    kayit_id, goruntu, log, _ = ortam
    api_cevabi(monkeypatch, kod=503)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    k = kayit(kayit_id)
    assert k["durum"] == "bekliyor"
    assert k["deneme"] == 1
    assert k["sonraki_deneme"] > simdi()
    assert OKUNUR.match(k["sonraki_deneme"])
    assert k["son_hata"] == "HTTP 503"
    assert goruntu.exists()


def test_baglanti_kopunca_veri_kaybolmaz(ortam, monkeypatch):
    kayit_id, goruntu, log, _ = ortam
    api_cevabi(monkeypatch, hata=requests.ConnectionError())
    g._kaydi_isle(kayit_id, AYARLAR, log)
    k = kayit(kayit_id)
    assert k["durum"] == "bekliyor"
    assert k["son_hata"] == "ConnectionError"
    assert goruntu.exists()


def test_bekleme_suresi_her_denemede_artar(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=503)
    for beklenen in g.BEKLEME_SN[:3]:
        beklemeyi_atla(kayit_id)
        once = datetime.now()
        g._kaydi_isle(kayit_id, AYARLAR, log)
        sonraki = datetime.strptime(kayit(kayit_id)["sonraki_deneme"], DB_BICIMI)
        # Saniye hassasiyetinde saklandığı için en fazla 1 sn sapma olabilir
        assert abs((sonraki - once).total_seconds() - beklenen) <= 1


def test_kalici_hata_hatali_olarak_isaretler(ortam, monkeypatch):
    kayit_id, goruntu, log, _ = ortam
    api_cevabi(monkeypatch, kod=401)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    k = kayit(kayit_id)
    assert k["durum"] == "hatali"
    assert k["son_hata"] == "HTTP 401"
    assert goruntu.exists()                 # görüntü silinmez, elle incelenecek


def test_hatali_kayit_tekrar_gonderilmez(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=401)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    api_cevabi(monkeypatch, hata=AssertionError("hatalı kayıt gönderilmemeliydi"))
    g._kaydi_isle(kayit_id, AYARLAR, log)
    assert g._siradakiler() == []


def test_bekleme_suresi_dolmadan_gondermez(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    beklemeyi_atla(kayit_id, sonraki=db_zamani(datetime.now() + timedelta(hours=1)))
    api_cevabi(monkeypatch, hata=AssertionError("gönderim denenmemeliydi"))
    g._kaydi_isle(kayit_id, AYARLAR, log)
    assert kayit(kayit_id)["durum"] == "bekliyor"
    assert g._siradakiler() == []


def test_goruntu_silinmisse_kayit_kuyruktan_cikar(ortam, monkeypatch):
    kayit_id, goruntu, log, _ = ortam
    goruntu.unlink()
    api_cevabi(monkeypatch, kod=201)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    assert kayit(kayit_id)["durum"] == "hatali"
    assert g._siradakiler() == []
    assert any("bulunamadı" in m for m in log.mesajlar)


def test_api_ye_giden_alan_adlari_degismedi(ortam, monkeypatch):
    """Tablo sütunlarının adı değişse de M4'e eskisiyle aynı alanlar gitmeli."""
    kayit_id, _, _, _ = ortam
    giden = {}

    class Yanit:
        status_code = 201

    def sahte_post(url, headers, data, files, timeout):
        giden.update(data)
        return Yanit()

    monkeypatch.setattr(g.requests, "post", sahte_post)
    with baglan() as db:
        k = db.execute("SELECT * FROM kayitlar WHERE kayit_id = ?", (kayit_id,)).fetchone()
    assert g._gonder(k, AYARLAR) == 201
    assert set(giden) == {"kayit_id", "cift_id", "tesis_kodu", "kamera_kodu",
                          "yatak_kodu", "zaman", "sira"}
    assert giden["kayit_id"] == "H01_K1_Y1_2026-10-01_10-00-00_1"


class Yanit:
    status_code = 201


def test_m4_ye_giden_zaman_saat_dilimli_iso(ortam, monkeypatch):
    """Veritabanında okunur saklansa da M4'e saat dilimli ISO gitmeli."""
    kayit_id, _, _, _ = ortam
    giden = {}
    monkeypatch.setattr(g.requests, "post",
                        lambda url, headers, data, files, timeout: giden.update(data) or Yanit())
    g._gonder(kayit(kayit_id), AYARLAR)
    dilim = saat_dilimi(datetime(2026, 10, 1, 10, 0, 0))
    assert giden["zaman"] == f"2026-10-01T10:00:00{dilim}"
    assert datetime.fromisoformat(giden["zaman"]).tzinfo is not None


def test_farkli_saat_dilimli_kayit_kendi_dilimiyle_gider(ortam, monkeypatch):
    """Örn. Kazakistan'daki bir kurulum: tablodaki dilim neyse M4'e o gider."""
    kayit_id, _, _, _ = ortam
    with baglan() as db:
        db.execute("UPDATE kayitlar SET saat_dilimi = '+05:00' WHERE kayit_id = ?", (kayit_id,))
    giden = {}
    monkeypatch.setattr(g.requests, "post",
                        lambda url, headers, data, files, timeout: giden.update(data) or Yanit())
    g._gonder(kayit(kayit_id), AYARLAR)
    assert giden["zaman"] == "2026-10-01T10:00:00+05:00"


# ---------- Olaylar tablosu ----------

def test_gecici_hata_olaylara_uyari_olarak_yazilir(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=503)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    olay = olaylar()[-1]
    assert (olay["seviye"], olay["kaynak"]) == ("WARNING", "K1")
    assert "HTTP 503" in olay["mesaj"]
    assert olay["mesaj"] in log.mesajlar     # log dosyasına da aynı mesaj gider


def test_kalici_hata_olaylara_hata_olarak_yazilir(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=401)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    olay = olaylar()[-1]
    assert (olay["seviye"], olay["kaynak"]) == ("ERROR", "K1")


def test_basarili_gonderim_olaylara_yazilmaz(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=201)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    assert olaylar() == []


# ---------- Gönderici döngüsü ----------

def test_siradakiler_cekim_sirasina_gore_ve_sadece_zamani_gelenler(tmp_path):
    gec, _ = goruntu_ve_kayit(tmp_path, datetime(2026, 10, 1, 10, 0, 10))
    erken, _ = goruntu_ve_kayit(tmp_path, datetime(2026, 10, 1, 10, 0, 0))
    bekleyecek, _ = goruntu_ve_kayit(tmp_path, datetime(2026, 10, 1, 10, 0, 5))
    beklemeyi_atla(bekleyecek, sonraki=db_zamani(datetime.now() + timedelta(hours=1)))
    gonderilmis, _ = goruntu_ve_kayit(tmp_path, datetime(2026, 10, 1, 9, 0, 0))
    with baglan() as db:
        db.execute("UPDATE kayitlar SET durum = 'gonderildi' WHERE kayit_id = ?", (gonderilmis,))
    assert g._siradakiler() == [erken, gec]


def test_tek_bozuk_kayit_gondericiyi_durdurmaz(tmp_path, monkeypatch):
    bozuk, _ = goruntu_ve_kayit(tmp_path, datetime(2026, 10, 1, 10, 0, 0))
    saglam, _ = goruntu_ve_kayit(tmp_path, datetime(2026, 10, 1, 10, 0, 5))

    def sahte_gonder(kayit, ayarlar):
        if kayit["kayit_id"] == bozuk:
            raise ValueError("beklenmeyen")
        return 201
    monkeypatch.setattr(g, "_gonder", sahte_gonder)

    log = SahteLog()
    g.gonderici_dongusu(AYARLAR, log, TekTur())
    assert kayit(saglam)["durum"] == "gonderildi"
    assert kayit(bozuk)["durum"] == "bekliyor"
    assert any("beklenmeyen hata" in m for m in log.mesajlar)
    assert olaylar()[-1]["seviye"] == "ERROR"


def test_veritabani_okunamazsa_gonderici_durmaz(monkeypatch):
    def bozuk():
        raise RuntimeError("veritabanı yok")
    monkeypatch.setattr(g, "_siradakiler", bozuk)
    log = SahteLog()
    g.gonderici_dongusu(AYARLAR, log, TekTur())      # hata fırlatmadan dönmeli
    assert any("kuyruğu okunamadı" in m for m in log.mesajlar)


def test_once_hata_sonra_basari_gecmiste_iz_birakir(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=503)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    beklemeyi_atla(kayit_id)
    api_cevabi(monkeypatch, kod=201)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    k = kayit(kayit_id)
    assert (k["durum"], k["deneme"], k["son_hata"]) == ("gonderildi", 1, "HTTP 503")
