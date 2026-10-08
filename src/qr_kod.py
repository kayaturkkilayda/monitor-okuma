"""Yatak QR kodları.

Her yatağın kendi adresi vardır. QR yalnızca bu adresi taşır; içinde şifre, jeton ya da
hasta bilgisi YOKTUR. Adres açıldığında kullanıcıdan giriş istenir. Bu yüzden QR
yazdırılıp yatak başına asılabilir.
"""
from pathlib import Path

import segno

VARSAYILAN_PORT = 8099
YOL = "/yatak"


def sunucu_adresi(ip: str, port: int = VARSAYILAN_PORT) -> str:
    return f"http://{ip}:{port}"


def yatak_adresi(ip: str, kamera_kodu: str, port: int = VARSAYILAN_PORT) -> str:
    """QR'ın taşıdığı adres: http://<bilgisayar-ip>:<port>/yatak/K1"""
    return f"{sunucu_adresi(ip, port)}{YOL}/{kamera_kodu}"


def qr_uret(adres: str):
    """segno QR nesnesi. Hata düzeltme seviyesi M: baskıda lekelenirse yine okunur."""
    return segno.make(adres, error="m")


def png_kaydet(adres: str, dosya: Path, kamera: dict | None = None,
               olcek: int = 8) -> Path:
    """QR'ı yazdırılabilir PNG olarak kaydeder.

    kamera verilirse QR'ın altına kamera ve yatak kodu yazılır; yatak başına asılan
    kağıtta hangi yatağa ait olduğu görünsün diye.
    """
    dosya = Path(dosya)
    dosya.parent.mkdir(parents=True, exist_ok=True)
    qr = qr_uret(adres)
    if kamera is None:
        qr.save(dosya, scale=olcek, border=4)
        return dosya

    from io import BytesIO
    from PIL import Image, ImageDraw, ImageFont

    tampon = BytesIO()
    qr.save(tampon, kind="png", scale=olcek, border=4)
    tampon.seek(0)
    with Image.open(tampon) as qr_resmi:
        qr_resmi = qr_resmi.convert("RGB")
        yazi_alani = 70
        sayfa = Image.new("RGB", (qr_resmi.width, qr_resmi.height + yazi_alani), "white")
        sayfa.paste(qr_resmi, (0, 0))
        cizim = ImageDraw.Draw(sayfa)
        try:
            buyuk = ImageFont.truetype("segoeui.ttf", 30)
            kucuk = ImageFont.truetype("segoeui.ttf", 16)
        except OSError:
            buyuk = kucuk = ImageFont.load_default()
        baslik = f"{kamera['kod']} → {kamera['yatak']}"
        cizim.text((qr_resmi.width // 2, qr_resmi.height + 8), baslik,
                   fill="black", font=buyuk, anchor="ma")
        cizim.text((qr_resmi.width // 2, qr_resmi.height + 46), "Monitör fotoğrafı gönder",
                   fill="#555555", font=kucuk, anchor="ma")
        sayfa.save(dosya)
    return dosya


def yerel_ip() -> str:
    """Bilgisayarın yerel ağdaki IP adresi.

    Dışarıya paket gönderilmez; yalnızca hangi arayüzün kullanılacağı sorulur.
    Ağ yoksa 127.0.0.1 döner (o zaman telefon bağlanamaz).
    """
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
