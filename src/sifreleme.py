"""Windows DPAPI ile şifreleme.

Şifrelenen veri yalnızca aynı bilgisayarda çözülebilir. Makine kapsamı kullanıldığı için
arayüz ve servis farklı kullanıcı hesaplarında çalışsa bile ikisi de çözebilir.
"""
import base64

import win32crypt

ONEK = "dpapi:"
MAKINE_KAPSAMI = 0x4   # CRYPTPROTECT_LOCAL_MACHINE


def sifrele(duz: str) -> str:
    """Boş veya zaten şifreli değerlere dokunmaz."""
    if not duz or duz.startswith(ONEK):
        return duz
    blob = win32crypt.CryptProtectData(duz.encode("utf-8"), "monitor-okuma",
                                       None, None, None, MAKINE_KAPSAMI)
    return ONEK + base64.b64encode(blob).decode("ascii")


def coz(deger: str) -> str:
    """Şifreli değilse olduğu gibi döndürür (eski düz metin ayarlar için)."""
    if not deger or not deger.startswith(ONEK):
        return deger
    blob = base64.b64decode(deger[len(ONEK):])
    _, veri = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
    return veri.decode("utf-8")