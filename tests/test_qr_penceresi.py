"""Yatak QR penceresi: doğru adresi gösterir, kapalıyken uyarır, PNG kaydeder."""
from pathlib import Path
from tkinter import ttk

import pytest
from PIL import Image

import qr_penceresi
from qr_penceresi import QrPenceresi

KAMERA = {"kod": "K1", "yatak": "Y1", "tip": "ip", "adres": "http://10.0.0.5/s.jpg"}


def yazilar(pencere) -> str:
    """Penceredeki bütün etiket metinleri tek metin hâlinde."""
    toplanan = []

    def gez(widget):
        for c in widget.winfo_children():
            if isinstance(c, ttk.Label):
                toplanan.append(str(c.cget("text")))
            gez(c)

    gez(pencere)
    return " | ".join(toplanan)


@pytest.fixture
def pencere(tk_kok):
    acilanlar = []

    def ac(acik=True, port=8099, ip="192.168.1.50"):
        p = QrPenceresi(tk_kok, KAMERA, port, acik, ip=ip)
        p.withdraw()
        acilanlar.append(p)
        return p

    yield ac
    for p in acilanlar:
        p.destroy()


def test_adres_yatak_koduna_gore_uretilir(pencere):
    p = pencere(port=8099, ip="192.168.1.50")
    assert p.adres == "http://192.168.1.50:8099/yatak/K1"
    assert p.adres in yazilar(p)                      # kullanıcı adresi de görebilsin


def test_kamera_ve_yatak_basligi_gorunur(pencere):
    p = pencere()
    metin = yazilar(p)
    assert "K1 → Y1" in metin
    assert "fotoğrafı gönderin" in metin


def test_kapaliyken_uyari_gosterilir(pencere):
    p = pencere(acik=False)
    assert "KAPALI" in yazilar(p)


def test_acikken_uyari_yok(pencere):
    assert "KAPALI" not in yazilar(pencere(acik=True))


def test_qr_resmi_olusur(pencere):
    p = pencere()
    assert p.resim.width() > 50 and p.resim.height() > 50


def test_png_kaydedilir(pencere, tmp_path, monkeypatch):
    p = pencere()
    hedef = tmp_path / "qr.png"
    monkeypatch.setattr(qr_penceresi.filedialog, "asksaveasfilename", lambda **k: str(hedef))
    monkeypatch.setattr(qr_penceresi.messagebox, "showinfo", lambda *a, **k: None)
    p._kaydet()
    assert hedef.exists()
    with Image.open(hedef) as resim:
        assert resim.format == "PNG"


def test_kaydetmekten_vazgecilirse_dosya_yazilmaz(pencere, tmp_path, monkeypatch):
    p = pencere()
    monkeypatch.setattr(qr_penceresi.filedialog, "asksaveasfilename", lambda **k: "")
    monkeypatch.setattr(qr_penceresi.messagebox, "showinfo",
                        lambda *a, **k: pytest.fail("kaydedilmemeliydi"))
    p._kaydet()
    assert list(Path(tmp_path).glob("*.png")) == []
