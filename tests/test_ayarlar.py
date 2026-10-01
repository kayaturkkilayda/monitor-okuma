import json

import pytest

from ayarlar import ayarlari_oku, ayarlari_yaz, kameralari_olustur
from kamera import IPKamera, Kamera


def ayar(kameralar):
    return {"tesis_kodu": "H01", "kameralar": kameralar}


def test_ip_ve_webcam_dogru_sinifla_olusur():
    kameralar = kameralari_olustur(ayar([
        {"kod": "K1", "yatak": "Y1", "tip": "ip", "adres": "http://x/shot.jpg"},
        {"kod": "W1", "yatak": "Y2", "tip": "webcam", "adres": 0},
    ]))
    assert isinstance(kameralar[0], IPKamera)
    assert isinstance(kameralar[1], Kamera)


def test_pasif_kamera_atlanir():
    kameralar = kameralari_olustur(ayar([
        {"kod": "K1", "yatak": "Y1", "tip": "ip", "adres": "http://x", "aktif": True},
        {"kod": "K2", "yatak": "Y2", "tip": "ip", "adres": "http://y", "aktif": False},
    ]))
    assert [k.kod for k in kameralar] == ["K1"]


def test_aktif_alani_yoksa_aktif_sayilir():
    kameralar = kameralari_olustur(ayar([
        {"kod": "K1", "yatak": "Y1", "tip": "ip", "adres": "http://x"},
    ]))
    assert len(kameralar) == 1


def test_kamera_yatak_eslesmesi_korunur():
    kameralar = kameralari_olustur(ayar([
        {"kod": "K7", "yatak": "302-A", "tip": "ip", "adres": "http://x"},
    ]))
    assert kameralar[0].kod == "K7"
    assert kameralar[0].yatak == "302-A"


def test_bilinmeyen_tip_hata_verir():
    with pytest.raises(ValueError, match="Bilinmeyen kamera tipi"):
        kameralari_olustur(ayar([
            {"kod": "K1", "yatak": "Y1", "tip": "rtsp", "adres": "rtsp://x"},
        ]))


def test_dosyadan_okuma_turkce_karakter(tmp_path):
    dosya = tmp_path / "ayarlar.json"
    dosya.write_text(json.dumps(ayar([
        {"kod": "K1", "yatak": "Yoğun Bakım-1", "tip": "ip", "adres": "http://x"},
    ]), ensure_ascii=False), encoding="utf-8")
    okunan = ayarlari_oku(dosya)
    assert okunan["kameralar"][0]["yatak"] == "Yoğun Bakım-1"


def test_yaz_oku_ayni_sonucu_verir(tmp_path):
    dosya = tmp_path / "ayarlar.json"
    orijinal = ayar([
        {"kod": "K1", "yatak": "Yoğun Bakım-1", "tip": "ip", "adres": "http://x",
         "kullanici": "admin", "sifre": "123", "aktif": True},
    ])
    ayarlari_yaz(orijinal, dosya)
    assert ayarlari_oku(dosya) == orijinal
    assert not dosya.with_suffix(".tmp").exists()   # geçici dosya kalmamalı    

def test_diskte_sifreler_duz_metin_degil(tmp_path):
    dosya = tmp_path / "ayarlar.json"
    ayarlar = ayar([{"kod": "K1", "yatak": "Y1", "tip": "ip", "adres": "http://x",
                     "kullanici": "admin", "sifre": "KameraSifresi"}])
    ayarlar["api_key"] = "ApiAnahtari"
    ayarlari_yaz(ayarlar, dosya)

    icerik = dosya.read_text(encoding="utf-8")
    assert "KameraSifresi" not in icerik
    assert "ApiAnahtari" not in icerik
    assert "admin" in icerik           # gizli olmayan alanlar okunabilir kalır


def test_yazmak_bellekteki_ayarlari_degistirmez(tmp_path):
    ayarlar = ayar([{"kod": "K1", "yatak": "Y1", "tip": "ip", "adres": "http://x",
                     "sifre": "gizli"}])
    ayarlari_yaz(ayarlar, tmp_path / "ayarlar.json")
    assert ayarlar["kameralar"][0]["sifre"] == "gizli"


def test_eski_duz_metin_dosya_okunabilir(tmp_path):
    dosya = tmp_path / "ayarlar.json"
    dosya.write_text(json.dumps(ayar([{"kod": "K1", "yatak": "Y1", "tip": "ip",
                                        "adres": "http://x", "sifre": "eski"}])),
                     encoding="utf-8")
    assert ayarlari_oku(dosya)["kameralar"][0]["sifre"] == "eski"    