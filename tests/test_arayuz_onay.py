"""Arayüzdeki onay akışı: gerçek Uygulama penceresi, sahte ayar dosyası ve sahte kamerayla."""
import numpy as np
import pytest

import onay

AYARLAR = {"tesis_kodu": "H01", "api_url": "", "api_key": "", "gonderim_araligi_sn": 30,
           "ikinci_cekim_gecikme_sn": 5, "format": "avif", "kalite": 85, "saklama_gun": 7,
           "gonderilince_sil": True, "kameralar": []}
KAMERA = {"kod": "K1", "yatak": "Y1", "tip": "ip", "adres": "http://10.0.0.5/shot.jpg",
          "kullanici": "", "sifre": "", "aktif": True}


class HemenCalisan:
    """Testte ana döngü olmadığı için arka plan işini aynı iş parçacığında hemen çalıştırır."""

    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


class SahteKamera:
    def __init__(self):
        self.cekim = 0

    def cift_cekim(self, aralik_sn=0):
        self.cekim += 1
        return np.zeros((4, 4, 3), dtype=np.uint8), 0, None, 0


@pytest.fixture(scope="module")
def uygulama(tk_kok):
    mp = pytest.MonkeyPatch()
    import arayuz
    mp.setattr(arayuz, "ayarlari_oku", lambda: {**AYARLAR, "kameralar": []})
    mp.setattr(arayuz, "durumlari_oku", lambda: {})
    uyg = arayuz.Uygulama()
    uyg.withdraw()
    yield arayuz, uyg
    uyg.destroy()
    mp.undo()


@pytest.fixture
def ortam(uygulama, monkeypatch):
    arayuz, uyg = uygulama
    kaydedilen, sorulan, bilgi = [], [], []
    kamera = SahteKamera()
    monkeypatch.setattr(arayuz, "ayarlari_yaz", lambda a: kaydedilen.append(
        [dict(k) for k in a["kameralar"]]))
    monkeypatch.setattr(arayuz, "kameralari_olustur", lambda a: [kamera])
    monkeypatch.setattr(arayuz, "onizleme_ac", lambda *a: None)
    monkeypatch.setattr(arayuz.threading, "Thread", HemenCalisan)
    monkeypatch.setattr(arayuz.messagebox, "showinfo", lambda *a, **k: bilgi.append(a))
    monkeypatch.setattr(arayuz.messagebox, "showerror", lambda *a, **k: bilgi.append(a))
    uyg.ayarlar["kameralar"] = [dict(KAMERA)]
    uyg._listeyi_doldur()
    uyg.liste.selection_set("K1")

    def cevap(evet):
        monkeypatch.setattr(arayuz.messagebox, "askyesno",
                            lambda baslik, mesaj, **k: sorulan.append(mesaj) or evet)

    return uyg, kamera, kaydedilen, sorulan, cevap, bilgi


def _test_bitsin(uyg):
    """Bağlantı testinin sonucu pencereye after() ile döner; onu işlet."""
    uyg.update()
    assert str(uyg.test_dugmesi.cget("state")) == "normal"


def test_onaysiz_kamera_listede_onay_bekliyor_turuncu(ortam):
    uyg, *_ = ortam
    assert uyg.liste.item("K1", "values")[4] == "Onay bekliyor"
    assert uyg.liste.item("K1", "tags") == ("onay_bekliyor",)
    assert str(uyg.liste.tag_configure("onay_bekliyor", "background")) == "#ffd8a8"


def test_reddedilirse_goruntu_alinmaz(ortam):
    uyg, kamera, kaydedilen, sorulan, cevap, _ = ortam
    cevap(False)
    uyg._baglanti_test()
    _test_bitsin(uyg)
    assert sorulan == [onay.onay_sorusu(KAMERA)]          # görüntüden önce soruldu
    assert kamera.cekim == 0                              # görüntü alınmadı
    assert kaydedilen == []
    assert not onay.onayli_mi(uyg.ayarlar["kameralar"][0])


def test_onaylanirsa_kaydedilir_ve_test_yapilir(ortam):
    uyg, kamera, kaydedilen, sorulan, cevap, _ = ortam
    cevap(True)
    uyg._baglanti_test()
    _test_bitsin(uyg)
    assert len(sorulan) == 1
    assert onay.onayli_mi(kaydedilen[-1][0])              # onay ayar dosyasına yazıldı
    assert kamera.cekim == 1
    assert uyg.liste.item("K1", "values")[4] != "Onay bekliyor"


def test_onayli_kamerada_tekrar_sorulmaz(ortam):
    uyg, kamera, _, sorulan, cevap, _ = ortam
    uyg.ayarlar["kameralar"] = [onay.onay_ver(KAMERA, "ilayda")]
    cevap(False)
    uyg._baglanti_test()
    _test_bitsin(uyg)
    assert sorulan == [] and kamera.cekim == 1


def test_onayla_dugmesi(ortam):
    uyg, kamera, kaydedilen, sorulan, cevap, _ = ortam
    cevap(True)
    uyg._onayla()
    assert len(sorulan) == 1
    assert onay.onayli_mi(uyg.ayarlar["kameralar"][0]) and onay.onayli_mi(kaydedilen[-1][0])
    assert uyg.liste.item("K1", "values")[4] != "Onay bekliyor"
    assert kamera.cekim == 0                              # onaylamak görüntü almaz


def test_onayla_dugmesi_reddedilince_degisiklik_yok(ortam):
    uyg, _, kaydedilen, _, cevap, _ = ortam
    cevap(False)
    uyg._onayla()
    assert kaydedilen == [] and not onay.onayli_mi(uyg.ayarlar["kameralar"][0])


def test_onayli_kamerada_onayla_kimin_onayladigini_gosterir(ortam):
    uyg, _, _, sorulan, cevap, bilgi = ortam
    uyg.ayarlar["kameralar"] = [{**KAMERA, "onay_zamani": "2026-10-04 10:00:00", "onaylayan": "ilayda"}]
    cevap(True)
    uyg._onayla()
    assert sorulan == []
    assert "04.10.2026 10:00:00" in bilgi[-1][1] and "ilayda" in bilgi[-1][1]
