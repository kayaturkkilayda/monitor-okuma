"""Kamera sahipliği: kim hangi kamerayı görür.

Kamerayı ekleyen kullanıcı onun sahibidir. Sahibi kamerayı görür, düzenler, siler ve
kayıtlarını okur. Yönetici bütün kameraları görür.

Eski ayar dosyalarında sahip alanı yoktur. O kameralar yöneticiye aittir; normal kullanıcı
onları göremez. Böylece eksik bilgi yüzünden veri sızmaz. gecis.py açılışta sahipsiz
kameralara ilk yöneticiyi yazar.
"""
SAHIP_ALANI = "ekleyen"


def _kucuk(metin) -> str:
    return str(metin or "").strip().lower()


def sahibi(kamera: dict) -> str:
    """Kamerayı ekleyen kullanıcının e-postası; yoksa boş metin."""
    return _kucuk(kamera.get(SAHIP_ALANI))


def sahiplendir(kamera: dict, eposta: str) -> dict:
    """Yeni kameraya sahibini yazar."""
    return {**kamera, SAHIP_ALANI: _kucuk(eposta)}


def yonetici_mi(oturum: dict | None) -> bool:
    return bool((oturum or {}).get("yonetici"))


def gorebilir_mi(kamera: dict, oturum: dict | None) -> bool:
    """Yönetici hepsini görür. Diğerleri yalnızca kendi eklediğini görür."""
    if yonetici_mi(oturum):
        return True
    sahip = sahibi(kamera)
    return bool(sahip) and sahip == _kucuk((oturum or {}).get("eposta"))


def gorunen_kameralar(kameralar: list[dict], oturum: dict | None) -> list[dict]:
    return [k for k in kameralar if gorebilir_mi(k, oturum)]


def gorunen_kodlar(kameralar: list[dict], oturum: dict | None) -> list[str] | None:
    """Kayıtlar sekmesinin filtresi. None = sınır yok (yönetici)."""
    if yonetici_mi(oturum):
        return None
    return [k["kod"] for k in gorunen_kameralar(kameralar, oturum)]
