import json
from datetime import date, timedelta

import pytest

import temizlik as t


class SahteLog:
    def __init__(self):
        self.mesajlar = []

    def info(self, m): self.mesajlar.append(m)


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    """Geçici klasörde goruntuler/, bekleyen/ ve hatali/ yapısı kurar."""
    kuyruk = tmp_path / "bekleyen"
    hatali = tmp_path / "hatali"
    kuyruk.mkdir()
    hatali.mkdir()
    # temizlik modülü bu klasörleri kendi içinde kullanıyor, oradan yönlendiriyoruz
    monkeypatch.setattr(t, "KUYRUK", kuyruk)
    monkeypatch.setattr(t, "HATALI", hatali)
    return tmp_path / "goruntuler", kuyruk, hatali, SahteLog()


def goruntu_olustur(kok, gun_once: int, ad: str = "K1_10-00-00.avif"):
    gun = (date.today() - timedelta(days=gun_once)).isoformat()
    dosya = kok / gun / "Y1" / ad
    dosya.parent.mkdir(parents=True, exist_ok=True)
    dosya.write_bytes(b"x")
    return dosya


def kayit_yaz(klasor, dosya):
    (klasor / "kayit.json").write_text(json.dumps({"dosya": str(dosya)}), encoding="utf-8")


def test_eski_sahipsiz_dosya_silinir(ortam):
    kok, _, _, log = ortam
    dosya = goruntu_olustur(kok, gun_once=10)
    t.temizle(7, log, klasor=str(kok))
    assert not dosya.exists()
    assert not dosya.parent.parent.exists()      # boşalan tarih klasörü de kalkar


def test_yeni_dosyaya_dokunulmaz(ortam):
    kok, _, _, log = ortam
    dosya = goruntu_olustur(kok, gun_once=2)
    t.temizle(7, log, klasor=str(kok))
    assert dosya.exists()


def test_kuyrukta_bekleyen_eski_dosya_korunur(ortam):
    kok, kuyruk, _, log = ortam
    dosya = goruntu_olustur(kok, gun_once=30)
    kayit_yaz(kuyruk, dosya)
    t.temizle(7, log, klasor=str(kok))
    assert dosya.exists()


def test_hatali_klasorundeki_eski_dosya_korunur(ortam):
    kok, _, hatali, log = ortam
    dosya = goruntu_olustur(kok, gun_once=30)
    kayit_yaz(hatali, dosya)
    t.temizle(7, log, klasor=str(kok))
    assert dosya.exists()


def test_korunan_ve_sahipsiz_ayni_klasorde(ortam):
    kok, kuyruk, _, log = ortam
    korunan = goruntu_olustur(kok, gun_once=30, ad="K1_10-00-00.avif")
    sahipsiz = goruntu_olustur(kok, gun_once=30, ad="K1_10-00-05.avif")
    kayit_yaz(kuyruk, korunan)
    t.temizle(7, log, klasor=str(kok))
    assert korunan.exists()
    assert not sahipsiz.exists()


def test_tarih_adli_olmayan_klasore_dokunulmaz(ortam):
    kok, _, _, log = ortam
    yabanci = kok / "notlar" / "onemli.txt"
    yabanci.parent.mkdir(parents=True)
    yabanci.write_text("dokunma")
    t.temizle(7, log, klasor=str(kok))
    assert yabanci.exists()