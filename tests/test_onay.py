import json
import re

import onay
from ayarlar import ayarlari_oku, ayarlari_yaz
from veritabani import baglan

KAMERA = {"kod": "K1", "yatak": "Y1", "tip": "ip", "adres": "http://10.0.0.5/shot.jpg",
          "kullanici": "", "sifre": "", "aktif": True}


class SahteLog:
    def __init__(self):
        self.mesajlar = []

    def warning(self, m): self.mesajlar.append(m)


def olaylar():
    with baglan() as db:
        return [dict(s) for s in db.execute("SELECT seviye, kaynak, mesaj FROM olaylar")]


# ---------- Onay alanları ----------

def test_eski_ayar_dosyasindaki_kamera_onaysiz():
    assert not onay.onayli_mi(KAMERA)                     # onay alanı hiç yok


def test_yarim_onay_gecersiz():
    assert not onay.onayli_mi({**KAMERA, "onay_zamani": "2026-10-04 10:00:00"})
    assert not onay.onayli_mi({**KAMERA, "onay_zamani": "", "onaylayan": "ilayda"})


def test_onay_ver_zaman_ve_windows_kullanicisi(monkeypatch):
    monkeypatch.setattr(onay.getpass, "getuser", lambda: "hemsire1")
    k = onay.onay_ver(KAMERA)
    assert onay.onayli_mi(k)
    assert k["onaylayan"] == "hemsire1"
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", k["onay_zamani"])
    assert "onay_zamani" not in KAMERA                    # orijinal değişmez


def test_onaylar_ayar_dosyasinda_saklanir(tmp_path):
    dosya = tmp_path / "ayarlar.json"
    ayarlari_yaz({"tesis_kodu": "H01", "kameralar": [onay.onay_ver(KAMERA, "ilayda")]}, dosya)
    k = ayarlari_oku(dosya)["kameralar"][0]
    assert onay.onayli_mi(k) and k["onaylayan"] == "ilayda"
    assert json.loads(dosya.read_text(encoding="utf-8"))["kameralar"][0]["onaylayan"] == "ilayda"


# ---------- Düzenlemede onayın taşınması ----------

def test_adres_ayni_kalirsa_onay_korunur():
    eski = onay.onay_ver(KAMERA, "ilayda")
    yeni = onay.onayi_aktar(eski, {**KAMERA, "yatak": "Y9", "aktif": False})
    assert onay.onayli_mi(yeni) and yeni["onay_zamani"] == eski["onay_zamani"]


def test_adres_degisirse_onay_sifirlanir():
    eski = onay.onay_ver(KAMERA, "ilayda")
    yeni = onay.onayi_aktar(eski, {**KAMERA, "adres": "http://10.0.0.99/shot.jpg"})
    assert not onay.onayli_mi(yeni)
    assert "onay_zamani" not in yeni and "onaylayan" not in yeni


def test_tip_degisirse_onay_sifirlanir():
    eski = onay.onay_ver({**KAMERA, "tip": "webcam", "adres": 0}, "ilayda")
    assert not onay.onayli_mi(onay.onayi_aktar(eski, {**KAMERA, "tip": "ip", "adres": 0}))


def test_onaysiz_kamera_duzenlenince_onaysiz_kalir():
    assert not onay.onayli_mi(onay.onayi_aktar(KAMERA, dict(KAMERA)))


# ---------- Soru ----------

def test_onay_sorusu_metni():
    assert onay.onay_sorusu(KAMERA) == (
        "K1 → Y1 (http://10.0.0.5/shot.jpg) kamerasından görüntü alınacak ve M4'e gönderilecek. "
        "Bu kameranın kullanımını onaylıyor musunuz?")


def test_soruda_adresteki_sifre_gizlenir():
    k = {**KAMERA, "adres": "http://admin:Gizli123@10.0.0.5:8080/shot.jpg"}
    soru = onay.onay_sorusu(k)
    assert "Gizli123" not in soru and "admin" not in soru
    assert "http://10.0.0.5:8080/shot.jpg" in soru


def test_onay_iste_evet_ve_hayir():
    sorulan = []

    def evet(baslik, mesaj):
        sorulan.append(mesaj)
        return True

    assert onay.onayli_mi(onay.onay_iste(KAMERA, evet))
    assert sorulan == [onay.onay_sorusu(KAMERA)]
    assert onay.onay_iste(KAMERA, lambda b, m: False) is None


# ---------- Motor ----------

def test_motor_yalnizca_onayli_kameralari_alir():
    onayli = onay.onay_ver(KAMERA, "ilayda")
    onaysiz = {**KAMERA, "kod": "K2", "yatak": "Y2"}
    assert onay.onayli_kameralar([onayli, onaysiz], SahteLog(), set()) == [onayli]


def test_onaysiz_kamera_bir_kez_loglanir_ve_olaylara_yazilir():
    log, bildirilen = SahteLog(), set()
    for _ in range(3):                                    # ayar değişikliğiyle yeniden başlatmalar
        onay.onayli_kameralar([KAMERA], log, bildirilen)
    assert len(log.mesajlar) == 1 and "onay" in log.mesajlar[0]
    assert [(o["seviye"], o["kaynak"]) for o in olaylar()] == [("WARNING", "K1")]


def test_adresi_degisen_onaysiz_kamera_yeniden_bildirilir():
    log, bildirilen = SahteLog(), set()
    onay.onayli_kameralar([KAMERA], log, bildirilen)
    onay.onayli_kameralar([{**KAMERA, "adres": "http://10.0.0.99/shot.jpg"}], log, bildirilen)
    assert len(log.mesajlar) == 2


def test_pasif_onaysiz_kamera_icin_uyari_yok():
    log = SahteLog()
    assert onay.onayli_kameralar([{**KAMERA, "aktif": False}], log, set()) == []
    assert log.mesajlar == []
