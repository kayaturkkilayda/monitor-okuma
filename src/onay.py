"""Kamera kullanım onayı: onaylanmamış kameradan görüntü alınmaz.

Kamera ayarında onay_zamani ve onaylayan alanları tutulur. Bu alanları olmayan
(eski ayar dosyasındaki) kameralar onaysız sayılır. Adres değişirse onay düşer,
çünkü artık başka bir cihaza bağlanılıyor olabilir.
"""
import getpass
from urllib.parse import urlsplit, urlunsplit

from veritabani import olay
from zaman import simdi

ONAY_ALANLARI = ("onay_zamani", "onaylayan")


def onayli_mi(kamera: dict) -> bool:
    return bool(kamera.get("onay_zamani")) and bool(kamera.get("onaylayan"))


def windows_kullanicisi() -> str:
    """Giriş sistemi gelene kadar onaylayan olarak Windows kullanıcı adı kullanılır."""
    try:
        return getpass.getuser()
    except Exception:
        return "bilinmiyor"


def onay_ver(kamera: dict, onaylayan: str | None = None) -> dict:
    return {**kamera, "onay_zamani": simdi(), "onaylayan": onaylayan or windows_kullanicisi()}


def onay_kaldir(kamera: dict) -> dict:
    return {ad: deger for ad, deger in kamera.items() if ad not in ONAY_ALANLARI}


def onayi_aktar(eski: dict, yeni: dict) -> dict:
    """Düzenlenen kameraya eski onayı taşır; adres ya da tip değiştiyse onay düşer."""
    yeni = onay_kaldir(yeni)
    if eski.get("adres") == yeni.get("adres") and eski.get("tip") == yeni.get("tip") \
            and onayli_mi(eski):
        yeni.update({ad: eski[ad] for ad in ONAY_ALANLARI})
    return yeni


def gorunen_adres(adres) -> str:
    """Adresin içine yazılmış kullanıcı adı/şifre varsa (http://kullanici:sifre@ip/...) gizler."""
    adres = str(adres)
    parca = urlsplit(adres)
    if parca.username is None and parca.password is None:
        return adres
    ana = parca.hostname or ""
    if parca.port:
        ana += f":{parca.port}"
    return urlunsplit((parca.scheme, ana, parca.path, parca.query, parca.fragment))


def onay_sorusu(kamera: dict) -> str:
    return (f"{kamera['kod']} → {kamera['yatak']} ({gorunen_adres(kamera['adres'])}) kamerasından "
            "görüntü alınacak ve M4'e gönderilecek. "
            "Bu kameranın kullanımını onaylıyor musunuz?")


def onayli_kameralar(kameralar: list[dict], log, bildirilenler: set) -> list[dict]:
    """Motor için: yalnızca onaylı kameraları döndürür.

    Onaysız aktif kamera her tur değil, bir kez loglanır ve olaylara yazılır.
    bildirilenler motor çalıştığı sürece korunur; (kod, adres) değişirse yeniden bildirilir.
    """
    onaylilar = []
    for k in kameralar:
        if onayli_mi(k):
            onaylilar.append(k)
            continue
        anahtar = (k["kod"], str(k.get("adres")))
        if k.get("aktif", True) and anahtar not in bildirilenler:
            bildirilenler.add(anahtar)
            olay(log, "WARNING", k["kod"],
                 f"{k['kod']} → {k['yatak']} | kullanım onayı yok, çekim yapılmıyor "
                 "(arayüzden onaylanmalı)")
    return onaylilar
