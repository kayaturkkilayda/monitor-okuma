"""Ayar dosyasını okuma, yazma ve kameraları oluşturma."""
import copy
import json
from pathlib import Path

from kamera import IPKamera, Kamera
from sifreleme import coz, sifrele

AYAR_DOSYASI = Path("config/ayarlar.json")


def _gizli_alanlara_uygula(ayarlar: dict, islem) -> dict:
    """API anahtarına ve kamera şifrelerine işlemi uygular.

    Orijinal sözlüğe dokunmaz, kopya döndürür.
    """
    sonuc = copy.deepcopy(ayarlar)
    if "api_key" in sonuc:
        sonuc["api_key"] = islem(sonuc["api_key"])
    for k in sonuc.get("kameralar", []):
        if "sifre" in k:
            k["sifre"] = islem(k["sifre"])
    return sonuc


def ayarlari_oku(yol: Path = AYAR_DOSYASI) -> dict:
    with open(yol, encoding="utf-8") as f:
        return _gizli_alanlara_uygula(json.load(f), coz)


def ayarlari_yaz(ayarlar: dict, yol: Path = AYAR_DOSYASI):
    """Gizli alanları şifreleyip atomik olarak yazar."""
    yol = Path(yol)
    diskteki = _gizli_alanlara_uygula(ayarlar, sifrele)
    gecici = yol.with_suffix(".tmp")
    gecici.write_text(json.dumps(diskteki, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    gecici.replace(yol)


def degisen_alanlar(eski: dict, yeni: dict) -> list[str]:
    """Değeri değişen ayarların yalnızca adlarını döndürür.

    Değerler döndürülmez; böylece şifre ve API anahtarı loglara karışmaz.
    """
    return sorted(ad for ad in eski.keys() | yeni.keys() if eski.get(ad) != yeni.get(ad))


def kameralari_olustur(ayarlar: dict) -> list:
    """Aktif kameraları tipine göre oluşturur.

    Eşleşmeler ileride merkezden okunacaksa sadece bu fonksiyon değişir.
    """
    kameralar = []
    for k in ayarlar["kameralar"]:
        if not k.get("aktif", True):
            continue
        if k["tip"] == "ip":
            kameralar.append(IPKamera(k["kod"], k["yatak"], k["adres"],
                                      k.get("kullanici", ""), k.get("sifre", "")))
        elif k["tip"] == "webcam":
            kameralar.append(Kamera(k["kod"], k["yatak"], k["adres"]))
        else:
            raise ValueError(f"Bilinmeyen kamera tipi: {k['tip']} ({k['kod']})")
    return kameralar