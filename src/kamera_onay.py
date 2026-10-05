"""Kamera kullanım onayının e-posta koduyla alınması.

Kamera eklenince (ya da adresi/tipi değişince) onaylayacak kişiye 6 haneli bir kod gider.
Kod, kullanıcı doğrulama kodlarıyla aynı yöntemle (tuzlu scrypt) hash'lenip saklanır;
düz hâli yalnızca e-postada bulunur. Kod gönderildiği andaki kamera adresine bağlıdır.
"""
import secrets
from datetime import datetime, timedelta

from kullanicilar import KullaniciHatasi, hash_dogru_mu, hashle
from onay import gorunen_adres, onayli_mi
from veritabani import baglan
from zaman import db_zamani, ekran_zamani

GECERLILIK_SAAT = 48
EN_FAZLA_DENEME = 5


def kod_olustur(kamera: dict, eposta: str, gonderen: str, simdi: datetime | None = None) -> str:
    """Yeni kod üretip saklar ve döndürür (yalnızca e-postaya yazılmak üzere).

    Kameranın önceki kodu varsa geçersiz olur.
    """
    simdi = simdi or datetime.now()
    kod = f"{secrets.randbelow(10 ** 6):06d}"
    with baglan() as db:
        db.execute("INSERT OR REPLACE INTO kamera_onay_kodlari (kamera_kodu, adres, eposta, kod_hash,"
                   " son_kullanma, deneme, gonderen, gonderim_zamani) VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                   (kamera["kod"], str(kamera["adres"]), eposta, hashle(kod),
                    db_zamani(simdi + timedelta(hours=GECERLILIK_SAAT)), gonderen, db_zamani(simdi)))
    return kod


def kodu_sil(kamera_kodu: str):
    with baglan() as db:
        db.execute("DELETE FROM kamera_onay_kodlari WHERE kamera_kodu = ?", (kamera_kodu,))


def bekleyen_kod(kamera: dict, simdi: datetime | None = None) -> dict | None:
    """Kamera için hâlâ kullanılabilir bir kod (gönderilmiş mail) varsa bilgisini döndürür."""
    with baglan() as db:
        satir = db.execute("SELECT eposta, son_kullanma, gonderim_zamani, adres FROM kamera_onay_kodlari"
                           " WHERE kamera_kodu = ?", (kamera["kod"],)).fetchone()
    if satir is None or satir["adres"] != str(kamera["adres"]) \
            or satir["son_kullanma"] < db_zamani(simdi or datetime.now()):
        return None
    return dict(satir)


def kodu_dogrula(kamera: dict, kod: str, simdi: datetime | None = None) -> str:
    """Kod doğruysa onay mailinin gittiği adresi döndürür ve kodu siler.

    Değilse deneme sayısını kaydedip KullaniciHatasi fırlatır.
    """
    simdi = simdi or datetime.now()
    hata, eposta = None, None
    with baglan() as db:
        satir = db.execute("SELECT * FROM kamera_onay_kodlari WHERE kamera_kodu = ?",
                           (kamera["kod"],)).fetchone()
        if satir is None:
            hata = "Bu kamera için geçerli bir onay kodu yok; onay mailini tekrar gönderin."
        elif satir["adres"] != str(kamera["adres"]):
            db.execute("DELETE FROM kamera_onay_kodlari WHERE kamera_kodu = ?", (kamera["kod"],))
            hata = "Kod gönderildikten sonra kamera adresi değişti; onay mailini tekrar gönderin."
        elif satir["son_kullanma"] < db_zamani(simdi):
            db.execute("DELETE FROM kamera_onay_kodlari WHERE kamera_kodu = ?", (kamera["kod"],))
            hata = f"Onay kodunun süresi doldu ({GECERLILIK_SAAT} saat); onay mailini tekrar gönderin."
        elif not hash_dogru_mu((kod or "").strip(), satir["kod_hash"]):
            deneme = satir["deneme"] + 1
            if deneme >= EN_FAZLA_DENEME:
                db.execute("DELETE FROM kamera_onay_kodlari WHERE kamera_kodu = ?", (kamera["kod"],))
                hata = "Çok fazla hatalı deneme; onay mailini tekrar gönderin."
            else:
                db.execute("UPDATE kamera_onay_kodlari SET deneme = ? WHERE kamera_kodu = ?",
                           (deneme, kamera["kod"]))
                hata = f"Kod hatalı. Kalan deneme: {EN_FAZLA_DENEME - deneme}"
        else:
            eposta = satir["eposta"]
            db.execute("DELETE FROM kamera_onay_kodlari WHERE kamera_kodu = ?", (kamera["kod"],))
    if hata:
        raise KullaniciHatasi(hata)
    return eposta


def onay_maili(tesis: str, kamera: dict, ekleyen: str, kod: str,
               simdi: datetime | None = None) -> tuple[str, str]:
    """(konu, metin). Kamera adresindeki kullanıcı adı/şifre gizlenir."""
    konu = f"[{tesis}] {kamera['kod']} → {kamera['yatak']} kamera kullanım onayı"
    metin = "\n".join([
        "Aşağıdaki kameradan görüntü alınıp M4'e gönderilmesi için onayınız isteniyor.",
        "",
        f"Kamera       : {kamera['kod']}",
        f"Yatak        : {kamera['yatak']}",
        f"Kamera adresi: {gorunen_adres(kamera['adres'])}",
        f"Ekleyen      : {ekleyen}",
        f"Tarih        : {ekran_zamani(db_zamani(simdi or datetime.now()))}",
        "",
        f"Onay kodu    : {kod}   ({GECERLILIK_SAAT} saat geçerli)",
        "",
        "Onaylıyorsanız bu kodu kurulumu yapan kişiye iletin ya da arayüzde girin. "
        "Onaylamıyorsanız hiçbir şey yapmanız gerekmez; kamera kullanılmayacak.",
    ])
    return konu, metin


def onay_maili_gerekli_mi(eski: dict | None, yeni: dict) -> bool:
    """Yeni ya da düzenlenen kamera için onay maili gönderilmeli mi?

    Onaylı kamera onaylı kaldıysa hayır. Onay düştüyse (adres/tip değişti) ya da bekleyen
    kameranın kodu, adresi, tipi veya onaylayacak e-postası değiştiyse evet.
    """
    if onayli_mi(yeni):
        return False
    if eski is None or onayli_mi(eski):
        return True
    return any(eski.get(a) != yeni.get(a) for a in ("kod", "adres", "tip", "onay_eposta"))
