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

def _olaylar():
    from veritabani import baglan
    with baglan() as db:
        return [dict(s) for s in db.execute("SELECT seviye, kaynak, mesaj FROM olaylar ORDER BY id")]


def test_ariza_ve_duzelme_olaylara_yazilir(tmp_path, monkeypatch):
    d, log = _kur(tmp_path, monkeypatch)
    for _ in range(ARIZA_ESIGI):
        d.bildir("H01/K1/Y1", basarili=False, kaynak="K1")
    d.bildir("H01/K1/Y1", basarili=True, kaynak="K1")
    olaylar = _olaylar()
    assert [(o["seviye"], o["kaynak"]) for o in olaylar] == [("ERROR", "K1"), ("INFO", "K1")]
    assert "ARIZA" in olaylar[0]["mesaj"] and "DÜZELDİ" in olaylar[1]["mesaj"]
    assert [o["mesaj"] for o in olaylar] == log.mesajlar     # log dosyasına da aynısı


def test_normal_turlar_olaylara_yazilmaz(tmp_path, monkeypatch):
    d, _ = _kur(tmp_path, monkeypatch)
    d.bildir("H01/K1/Y1", basarili=True, kaynak="K1")
    d.bildir("H01/K1/Y1", basarili=False, kaynak="K1")
    assert _olaylar() == []


# ---------- Arayüzde görünen durum ----------

from datetime import datetime, timedelta

from durum import gorunen_durum

SIMDI = datetime(2026, 10, 4, 12, 0, 0)


def _once(saniye):
    return (SIMDI - timedelta(seconds=saniye)).strftime("%Y-%m-%d %H:%M:%S")


def test_taze_goruntu_calisiyor():
    assert gorunen_durum({"durum": "calisiyor", "son_basari": _once(60)}, True, 30, SIMDI) == "calisiyor"


def test_aralik_3_katindan_eski_goruntu_yanit_yok():
    """Motor kapanınca durum.json'da 'çalışıyor' kalır; yeşil görünmemeli."""
    assert gorunen_durum({"durum": "calisiyor", "son_basari": _once(91)}, True, 30, SIMDI) == "yanit_yok"


def test_tam_sinirda_hala_calisiyor():
    assert gorunen_durum({"durum": "calisiyor", "son_basari": _once(90)}, True, 30, SIMDI) == "calisiyor"


def test_eski_iso_bicimli_son_basari_da_okunur():
    iso = (SIMDI - timedelta(seconds=500)).astimezone().isoformat(timespec="seconds")
    assert gorunen_durum({"durum": "calisiyor", "son_basari": iso}, True, 30, SIMDI) == "yanit_yok"


def test_arizali_ve_bilinmiyor_aynen_kalir():
    assert gorunen_durum({"durum": "arizali", "son_basari": _once(9999)}, True, 30, SIMDI) == "arizali"
    assert gorunen_durum({}, True, 30, SIMDI) == "bilinmiyor"


def test_pasif_kamera_pasif():
    assert gorunen_durum({"durum": "calisiyor", "son_basari": _once(1)}, False, 30, SIMDI) == "pasif"


def test_onaysiz_kamera_onay_bekliyor_her_durumdan_once():
    taze = {"durum": "calisiyor", "son_basari": _once(1)}
    assert gorunen_durum(taze, True, 30, SIMDI, onayli=False) == "onay_bekliyor"
    assert gorunen_durum({}, False, 30, SIMDI, onayli=False) == "onay_bekliyor"
    assert gorunen_durum(taze, True, 30, SIMDI, onayli=True) == "calisiyor"
