import json
import time
from datetime import datetime

import pytest
import requests

import gonderici as g


class SahteLog:
    def __init__(self):
        self.mesajlar = []

    def info(self, m): self.mesajlar.append(m)
    def warning(self, m): self.mesajlar.append(m)
    def error(self, m): self.mesajlar.append(m)
    def exception(self, m): self.mesajlar.append(m)


AYARLAR = {"api_url": "http://test", "api_key": "x", "gonderilince_sil": True}


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    """Geçici klasörde bir görüntü oluşturup kuyruğa ekler."""
    monkeypatch.setattr(g, "KUYRUK", tmp_path / "bekleyen")
    monkeypatch.setattr(g, "HATALI", tmp_path / "hatali")
    goruntu = tmp_path / "K1.avif"
    goruntu.write_bytes(b"sahte goruntu")
    g.kuyruga_ekle(goruntu, "H01", "K1", "Y1", datetime(2026, 10, 1, 10, 0, 0), 1, "cift-1")
    json_dosya = next((tmp_path / "bekleyen").glob("*.json"))
    return json_dosya, goruntu, SahteLog(), tmp_path


def api_cevabi(monkeypatch, kod=None, hata=None):
    """Gerçek gönderim yerine sabit bir cevap döndüren sahte fonksiyon koyar."""
    def sahte_gonder(kayit, ayarlar):
        if hata:
            raise hata
        return kod
    monkeypatch.setattr(g, "_gonder", sahte_gonder)


def test_kuyruga_ekle_dogru_alanlari_yazar(ortam):
    json_dosya, goruntu, _, _ = ortam
    kayit = json.loads(json_dosya.read_text(encoding="utf-8"))
    assert kayit["tesis_kodu"] == "H01"
    assert kayit["kamera_kodu"] == "K1"
    assert kayit["yatak_kodu"] == "Y1"
    assert kayit["sira"] == 1
    assert kayit["cift_id"] == "cift-1"
    assert kayit["deneme"] == 0
    assert "T10:00:00" in kayit["zaman"]   # saat dilimiyle birlikte


def test_basarili_gonderim_kuyruktan_ve_diskten_siler(ortam, monkeypatch):
    json_dosya, goruntu, log, _ = ortam
    api_cevabi(monkeypatch, kod=201)
    g._kaydi_isle(json_dosya, AYARLAR, log)
    assert not json_dosya.exists()
    assert not goruntu.exists()


def test_gonderilince_sil_kapaliysa_goruntu_kalir(ortam, monkeypatch):
    json_dosya, goruntu, log, _ = ortam
    api_cevabi(monkeypatch, kod=201)
    g._kaydi_isle(json_dosya, {**AYARLAR, "gonderilince_sil": False}, log)
    assert not json_dosya.exists()
    assert goruntu.exists()


def test_gecici_hata_kuyrukta_tutar_ve_bekletir(ortam, monkeypatch):
    json_dosya, goruntu, log, _ = ortam
    api_cevabi(monkeypatch, kod=503)
    g._kaydi_isle(json_dosya, AYARLAR, log)
    kayit = json.loads(json_dosya.read_text(encoding="utf-8"))
    assert kayit["deneme"] == 1
    assert kayit["sonraki_deneme"] > time.time()
    assert goruntu.exists()


def test_baglanti_kopunca_veri_kaybolmaz(ortam, monkeypatch):
    json_dosya, goruntu, log, _ = ortam
    api_cevabi(monkeypatch, hata=requests.ConnectionError())
    g._kaydi_isle(json_dosya, AYARLAR, log)
    assert json_dosya.exists()
    assert goruntu.exists()


def test_bekleme_suresi_her_denemede_artar(ortam, monkeypatch):
    json_dosya, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=503)
    sureler = []
    for _ in range(3):
        kayit = json.loads(json_dosya.read_text(encoding="utf-8"))
        kayit["sonraki_deneme"] = 0          # beklemeyi atla
        json_dosya.write_text(json.dumps(kayit), encoding="utf-8")
        once = time.time()
        g._kaydi_isle(json_dosya, AYARLAR, log)
        kayit = json.loads(json_dosya.read_text(encoding="utf-8"))
        sureler.append(round(kayit["sonraki_deneme"] - once))
    assert sureler == g.BEKLEME_SN[:3]


def test_kalici_hata_hatali_klasorune_tasir(ortam, monkeypatch):
    json_dosya, goruntu, log, tmp_path = ortam
    api_cevabi(monkeypatch, kod=401)
    g._kaydi_isle(json_dosya, AYARLAR, log)
    assert not json_dosya.exists()
    assert (tmp_path / "hatali" / json_dosya.name).exists()
    assert goruntu.exists()                 # görüntü silinmez, elle incelenecek


def test_bekleme_suresi_dolmadan_gondermez(ortam, monkeypatch):
    json_dosya, _, log, _ = ortam
    kayit = json.loads(json_dosya.read_text(encoding="utf-8"))
    kayit["sonraki_deneme"] = time.time() + 3600
    json_dosya.write_text(json.dumps(kayit), encoding="utf-8")
    api_cevabi(monkeypatch, hata=AssertionError("gönderim denenmemeliydi"))
    g._kaydi_isle(json_dosya, AYARLAR, log)
    assert json_dosya.exists()


def test_goruntu_silinmisse_kayit_kuyruktan_cikar(ortam, monkeypatch):
    json_dosya, goruntu, log, _ = ortam
    goruntu.unlink()
    api_cevabi(monkeypatch, kod=201)
    g._kaydi_isle(json_dosya, AYARLAR, log)
    assert not json_dosya.exists()
    assert any("bulunamadı" in m for m in log.mesajlar)