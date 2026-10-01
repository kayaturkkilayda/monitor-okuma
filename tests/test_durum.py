import durum as durum_modulu
from durum import ARIZA_ESIGI, KameraDurumu


class SahteLog:
    """Gerçek log yerine mesajları bir listede toplar, testte kontrol edebilelim."""

    def __init__(self):
        self.mesajlar = []

    def info(self, mesaj):
        self.mesajlar.append(mesaj)

    def error(self, mesaj):
        self.mesajlar.append(mesaj)


def _kur(tmp_path, monkeypatch):
    # durum.json gerçek proje klasörüne değil, geçici bir klasöre yazılsın
    monkeypatch.setattr(durum_modulu, "DURUM_DOSYASI", tmp_path / "durum.json")
    log = SahteLog()
    return KameraDurumu(log), log


def test_esik_dolmadan_ariza_yok(tmp_path, monkeypatch):
    d, log = _kur(tmp_path, monkeypatch)
    for _ in range(ARIZA_ESIGI - 1):
        d.bildir("H01/K1/Y1", basarili=False)
    assert log.mesajlar == []


def test_esikte_tek_ariza(tmp_path, monkeypatch):
    d, log = _kur(tmp_path, monkeypatch)
    for _ in range(ARIZA_ESIGI + 10):
        d.bildir("H01/K1/Y1", basarili=False)
    arizalar = [m for m in log.mesajlar if "ARIZA" in m]
    assert len(arizalar) == 1


def test_ariza_sonrasi_duzelme(tmp_path, monkeypatch):
    d, log = _kur(tmp_path, monkeypatch)
    for _ in range(ARIZA_ESIGI):
        d.bildir("H01/K1/Y1", basarili=False)
    d.bildir("H01/K1/Y1", basarili=True)
    assert any("DÜZELDİ" in m for m in log.mesajlar)


def test_saglam_kamera_duzeldi_demez(tmp_path, monkeypatch):
    d, log = _kur(tmp_path, monkeypatch)
    d.bildir("H01/K1/Y1", basarili=True)
    d.bildir("H01/K1/Y1", basarili=True)
    assert log.mesajlar == []


def test_kameralar_birbirini_etkilemez(tmp_path, monkeypatch):
    d, log = _kur(tmp_path, monkeypatch)
    for _ in range(ARIZA_ESIGI):
        d.bildir("H01/K1/Y1", basarili=False)
        d.bildir("H01/K2/Y2", basarili=True)
    assert len(log.mesajlar) == 1
    assert "K1" in log.mesajlar[0]