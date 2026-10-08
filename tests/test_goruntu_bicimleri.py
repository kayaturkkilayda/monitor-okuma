"""Kaydedilen görüntü geri okunabilmeli.

Bu dosya bir hatanın tekrarını önlemek için var: pillow-avif-plugin kurulu ve import
edilmiş olduğunda Pillow 12'nin kendi AVIF okuyucusunu eziyordu. Sonuç şuydu: motor
AVIF dosyasını yazıyordu ama arayüz Kayıtlar sekmesinde aynı dosyayı açamıyordu.
Pillow 12 AVIF'i kendi destekler; eklenti KULLANILMAMALIDIR.
"""
import sys

import numpy as np
import pytest
from PIL import Image, features

import kaydedici
import onizleme


# ---------- Eski eklenti devrede olmamalı ----------

def test_pillow_avif_eklentisi_import_edilmiyor():
    """Modüller yüklendiği hâlde eklenti devreye girmemeli."""
    assert "pillow_avif" not in sys.modules


def test_pillow_kendi_avif_destegine_sahip():
    assert features.check("avif") is True


# ---------- Yaz / oku turu ----------

def kare(en=48, boy=32):
    """OpenCV'nin kullandığı BGR dizi."""
    dizi = np.zeros((boy, en, 3), dtype=np.uint8)
    dizi[:, :, 0] = 200          # mavi kanal
    return dizi


@pytest.mark.parametrize("bicim", ["avif", "jpg", "png"])
def test_kaydedilen_goruntu_geri_okunabilir(tmp_path, bicim):
    """Motor neyi yazıyorsa arayüz onu açabilmeli."""
    dosya = tmp_path / f"deneme.{bicim}"
    boyut = kaydedici.kaydet(kare(), dosya, kalite=85)
    assert boyut > 0 and dosya.stat().st_size == boyut
    with Image.open(dosya) as okunan:
        okunan.load()                       # bozuksa burada hata verir
        assert okunan.size == (48, 32)


def test_avif_dosyasi_onizlemede_acilabilir(tmp_path, tk_kok):
    """Kayıtlar sekmesindeki önizlemenin yaptığı iş."""
    dosya = tmp_path / "kayit.avif"
    kaydedici.kaydet(kare(), dosya)
    with Image.open(dosya) as goruntu:
        pencere = onizleme.onizleme_ac(tk_kok, goruntu, "K1 → Y1")
    try:
        assert pencere.winfo_exists()
        assert "48x32" in pencere.title()
    finally:
        pencere.destroy()


def test_telefon_fotografi_avif_olarak_okunabilir(tmp_path, monkeypatch):
    """Telefondan gelen JPEG, ayarlardaki AVIF biçimine çevrilip geri okunabilmeli."""
    import yukleme
    from io import BytesIO
    monkeypatch.chdir(tmp_path)

    tampon = BytesIO()
    Image.new("RGB", (120, 90), (30, 140, 210)).save(tampon, format="JPEG")

    class SahteLog:
        def info(self, m): pass

    ayarlar = {"tesis_kodu": "H01", "format": "avif", "kalite": 85}
    kamera = {"kod": "K1", "yatak": "Y1"}
    yukleme.fotografi_al(tampon.getvalue(), ayarlar, kamera, "ayse@akgun.com.tr", SahteLog())

    avifler = list(tmp_path.rglob("*.avif"))
    assert len(avifler) == 1
    with Image.open(avifler[0]) as okunan:
        okunan.load()
        assert okunan.size == (120, 90)
