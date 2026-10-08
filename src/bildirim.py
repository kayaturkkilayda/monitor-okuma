"""E-posta bildirimleri: kamera ARIZA / DÜZELDİ olduğunda SMTP ile mail.

Gönderim motorun kendi iş parçacığında yapılır; kamera döngüsü yalnızca kuyruğa
bırakıp devam eder, mail sunucusunu asla beklemez. Gönderilecek mailler bildirimler
tablosunda durur: gönderilemeyen olaylar tablosuna yazılır ve artan aralıklarla tekrar
denenir; motor yeniden başlarsa bekleyenler kaldığı yerden devam eder.
"""
import queue
import smtplib
import ssl
import threading
import time
from datetime import datetime, timedelta
from email.message import EmailMessage

from onay import gorunen_adres
from veritabani import baglan, olay
from zaman import db_zamani, ekran_zamani

GUVENLIK_SECENEKLERI = ("STARTTLS", "SSL", "Yok")
ZAMAN_ASIMI_SN = 15
TEKRAR_BEKLEME_SN = [60, 300, 900, 1800]
EN_FAZLA_DENEME = 10


# ---------- Adresler ve içerik ----------

def adresleri_ayir(metin: str | None) -> list[str]:
    """'a@x.com, b@y.com' → ['a@x.com', 'b@y.com']"""
    return [a.strip() for a in (metin or "").replace(";", ",").split(",") if a.strip()]


def gecersiz_adresler(metin: str | None) -> list[str]:
    return [a for a in adresleri_ayir(metin)
            if a.count("@") != 1 or "." not in a.split("@")[1] or " " in a]


def gonderen_adres(smtp: dict | None) -> str:
    """Mailler SMTP kullanıcı adından gider; ayrı bir "gönderen" alanı yoktur.

    Eski ayar dosyalarında kullanıcı adı boş ama "gonderen" dolu olabilir; o dosyalar
    bozulmasın diye eski alan yedek olarak okunur.
    """
    smtp = smtp or {}
    return str(smtp.get("kullanici") or smtp.get("gonderen") or "").strip()


def alicilar(kamera: dict, smtp: dict) -> list[str]:
    """Kameranın bildirim adresleri; boşsa varsayılan bildirim adresi.

    Varsayılan adres, ayarları en son kaydeden yöneticinin e-postasıdır.
    """
    return adresleri_ayir(kamera.get("bildirim_eposta")) or adresleri_ayir(smtp.get("varsayilan_alici"))


def sorumlu_adresler(kamera: dict, smtp: dict) -> list[str]:
    """Elle müdahale gereken (kırmızı) hatalar kamerayı onaylayan kullanıcıya gider.

    Onaylayan bir e-posta adresi değilse (eski kayıtlarda Windows kullanıcı adı olabilir)
    varsayılan bildirim adresine düşülür.
    """
    onaylayan = str(kamera.get("onaylayan") or "").strip()
    if onaylayan and not gecersiz_adresler(onaylayan) and "," not in onaylayan:
        return [onaylayan]
    return alicilar(kamera, smtp)


def smtp_hazir_mi(smtp: dict | None) -> bool:
    return bool(smtp and smtp.get("sunucu") and gonderen_adres(smtp))


def kamera_mesaji(tur: str, tesis: str, kamera: dict, ariza_baslangic: str | None,
                  son_basari: str | None) -> tuple[str, str]:
    """(konu, metin). tur: 'ariza' ya da 'duzeldi'."""
    baslik = "kamera arızası" if tur == "ariza" else "kamera düzeldi"
    konu = f"[{tesis}] {kamera['kod']} → {kamera['yatak']} {baslik}"
    satirlar = [
        "Kamera görüntü alamıyor." if tur == "ariza" else "Kamera yeniden görüntü veriyor.",
        "",
        f"Tesis               : {tesis}",
        f"Kamera              : {kamera['kod']}",
        f"Yatak               : {kamera['yatak']}",
        f"Kamera adresi       : {gorunen_adres(kamera.get('adres', ''))}",   # şifre gizli
        f"Arıza başlangıcı    : {ekran_zamani(ariza_baslangic) or '-'}",
        f"Son başarılı görüntü: {ekran_zamani(son_basari) or '-'}",
    ]
    if tur == "ariza":
        satirlar += ["", "NE YAPMALISINIZ", NE_YAPMALI["ariza"]]
    return konu, "\n".join(satirlar)


# Kırmızı (elle müdahale gereken) hatalar için ne yapılacağı
NE_YAPMALI = {
    "ariza": ("Kameranın elektriğini ve ağ bağlantısını kontrol edin. Kamera görüntü\n"
              "vermeye başlayana kadar bu yataktan M4'e görüntü gitmeyecek. Bu sürede\n"
              "değerleri M4'e elle girin VEYA yatak başındaki QR'ı telefonunuzla okutup\n"
              "monitörün fotoğrafını gönderin."),
    "gonderilemedi": ("Görüntü çekildi ama M4'e gönderilemedi ve tekrar denemeler bitti.\n"
                      "Bu görüntü kendiliğinden gitmeyecek. Değeri M4'e elle girin VEYA\n"
                      "yatak başındaki QR'ı okutup telefonla yeni bir fotoğraf gönderin.\n"
                      "Sorun sürüyorsa BT ile M4 bağlantısını kontrol edin."),
    "m4_hata": ("M4 isteği kalıcı olarak reddetti. Bu genellikle yanlış API adresi ya da\n"
                "API anahtarı demektir. Arayüzdeki Ayarlar sekmesinden M4 bilgilerini\n"
                "kontrol edin. Düzelene kadar değerleri M4'e elle girin.\n"
                "(Telefonla gönderilen fotoğraflar da aynı kuyruğa girer; M4 düzelene\n"
                "kadar onlar da bekler.)"),
}

HATA_BASLIGI = {"gonderilemedi": "görüntü gönderilemedi", "m4_hata": "M4 kalıcı hata"}
# "ariza" da kırmızıdır ama kendi kamera mesajıyla gider; bunlar hata mesajı kullanır
HATA_TURLERI = ("gonderilemedi", "m4_hata")


def hata_mesaji(tur: str, tesis: str, kamera: dict, ayrinti: str) -> tuple[str, str]:
    """(konu, metin). Elle müdahale gereken hatalar için sorumlu kullanıcıya giden mail."""
    konu = f"[{tesis}] {kamera['kod']} → {kamera['yatak']} {HATA_BASLIGI.get(tur, tur)}"
    satirlar = [
        "Bu kamerada elle müdahale gereken bir hata oluştu.",
        "",
        f"Tesis         : {tesis}",
        f"Kamera        : {kamera['kod']}",
        f"Yatak         : {kamera['yatak']}",
        f"Kamera adresi : {gorunen_adres(kamera.get('adres', ''))}",   # şifre gizli
        f"Hata          : {ayrinti}",
        "",
        "NE YAPMALISINIZ",
        NE_YAPMALI.get(tur, "Arayüzdeki Loglar sekmesinden ayrıntıya bakın."),
    ]
    return konu, "\n".join(satirlar)


# ---------- Gönderim ----------

def gonder(smtp: dict, alici: list[str], konu: str, metin: str):
    """Tek bir maili gönderir; hata olursa istisna fırlatır."""
    mesaj = EmailMessage()
    mesaj["From"] = gonderen_adres(smtp)
    mesaj["To"] = ", ".join(alici)
    mesaj["Subject"] = konu
    mesaj.set_content(metin)

    sunucu, port = smtp["sunucu"], int(smtp.get("port") or 0)
    guvenlik = smtp.get("guvenlik", "STARTTLS")
    if guvenlik == "SSL":
        baglanti = smtplib.SMTP_SSL(sunucu, port or 465, timeout=ZAMAN_ASIMI_SN,
                                    context=ssl.create_default_context())
    else:
        baglanti = smtplib.SMTP(sunucu, port or 587, timeout=ZAMAN_ASIMI_SN)
    with baglanti:
        if guvenlik == "STARTTLS":
            baglanti.starttls(context=ssl.create_default_context())
        # Kullanıcı adı aynı zamanda gönderen adrestir; kimlik doğrulaması yalnızca
        # şifre girilmişse denenir. Şifresiz (açık röle) sunucular da çalışsın.
        if smtp.get("kullanici") and smtp.get("sifre"):
            baglanti.login(smtp["kullanici"], smtp["sifre"])
        baglanti.send_message(mesaj)


def hata_aciklamasi(hata: Exception, smtp: dict) -> str:
    """Kullanıcıya gösterilecek hata nedeni; şifre (sunucu cevabında geçse bile) gizlenir."""
    metin = f"{type(hata).__name__}: {hata}"
    if smtp.get("sifre"):
        metin = metin.replace(smtp["sifre"], "***")
    return metin


def test_maili_gonder(smtp: dict) -> tuple[bool, str]:
    """Varsayılan bildirim adresine deneme maili gönderir: (başarılı mı, açıklama)."""
    alici = adresleri_ayir(smtp.get("varsayilan_alici"))
    if not smtp_hazir_mi(smtp):
        return False, "SMTP sunucusu ve kullanıcı adı girilmeli."
    if not alici:
        return False, "Bildirim adresi yok; ayarları kaydeden yöneticinin e-postası kullanılır."
    try:
        gonder(smtp, alici, "Monitör görüntü aktarımı: test maili",
               "Bu bir deneme mailidir. E-posta ayarları çalışıyor.")
    except Exception as e:
        return False, hata_aciklamasi(e, smtp)
    return True, f"Test maili gönderildi: {', '.join(alici)}"


# ---------- Motorun bildirim kuyruğu ----------

class Bildirici:
    """Kamera olaylarını maile çevirip bildirimler tablosuna yazar, ayrı iş parçacığında gönderir."""

    def __init__(self, ayarlar: dict, log, baslat: bool = True):
        self.ayarlar = ayarlar
        self.log = log
        self._gelen = queue.Queue()     # kamera döngüsünden gelen, henüz tabloya yazılmamış olaylar
        self._dur = threading.Event()
        self._is_parcacigi = None
        if baslat:
            self._is_parcacigi = threading.Thread(target=self._calis, name="bildirim", daemon=True)
            self._is_parcacigi.start()

    def durdur(self, bekle_sn: float = 5):
        self._dur.set()
        if self._is_parcacigi:
            self._is_parcacigi.join(bekle_sn)

    def ayarlari_guncelle(self, ayarlar: dict):
        self.ayarlar = ayarlar

    def kamera_olayi(self, tur: str, kamera_kodu: str, ariza_baslangic: str | None,
                     son_basari: str | None):
        """Kamera döngüsünden çağrılır; veritabanını bile beklemeden hemen döner."""
        self._gelen.put({"tur": tur, "kamera_kodu": kamera_kodu,
                         "anahtar": ariza_baslangic, "son_basari": son_basari})

    def hata_olayi(self, tur: str, kamera_kodu: str, anahtar: str, ayrinti: str):
        """Elle müdahale gereken (kırmızı) hata; sorumlu kullanıcıya mail gider.

        anahtar: aynı hatanın tekrar tekrar maillenmesini önleyen tekillik anahtarı.
        Göndericiden çağrılır; gönderim döngüsünü bekletmez.
        """
        self._gelen.put({"tur": tur, "kamera_kodu": kamera_kodu,
                         "anahtar": anahtar, "ayrinti": ayrinti})

    # --- iş parçacığı ---

    def _calis(self):
        while not self._dur.is_set():
            try:
                self.isle()
            except Exception:
                self.log.exception("Bildirim işlenirken beklenmeyen hata")
            self._dur.wait(1)

    def isle(self, simdi: datetime | None = None):
        """Yeni olayları tabloya yazar, zamanı gelen mailleri gönderir."""
        simdi = simdi or datetime.now()
        while True:
            try:
                olay_ = self._gelen.get_nowait()
            except queue.Empty:
                break
            try:
                self._hazirla(olay_, simdi)
            except Exception:
                self._gelen.put(olay_)   # veritabanı o an yazılamadıysa olay kaybolmasın
                raise
        with baglan() as db:
            zamani_gelenler = db.execute(
                "SELECT * FROM bildirimler WHERE durum = 'bekliyor' AND sonraki_deneme <= ?"
                " ORDER BY id", (db_zamani(simdi),)).fetchall()
        for b in zamani_gelenler:
            self._gonder(dict(b), simdi)

    def _hazirla(self, olay_: dict, simdi: datetime):
        tur, kamera_kodu = olay_["tur"], olay_["kamera_kodu"]
        smtp = self.ayarlar.get("smtp") or {}
        kamera = next((k for k in self.ayarlar.get("kameralar", []) if k["kod"] == kamera_kodu), None)
        if kamera is None or not smtp_hazir_mi(smtp):
            return                       # e-posta ayarlanmamışsa bildirim yalnızca loglarda kalır
        tesis = self.ayarlar.get("tesis_kodu", "")
        if tur in HATA_TURLERI:
            konu, metin = hata_mesaji(tur, tesis, kamera, olay_["ayrinti"])
        else:
            konu, metin = kamera_mesaji(tur, tesis, kamera, olay_["anahtar"], olay_["son_basari"])
        alici = sorumlu_adresler(kamera, smtp)
        if not alici:
            return
        # Aynı kamera + tür + anahtar zaten varsa (motor yeniden başlamış olsa bile) tekillik
        # kuralı yüzünden ikinci satır eklenmez: aynı olay için tek mail
        with baglan() as db:
            db.execute(
                "INSERT OR IGNORE INTO bildirimler (kamera_kodu, tur, ariza_baslangic, alicilar,"
                " konu, metin, sonraki_deneme, olusturma_zamani) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (kamera_kodu, tur, olay_["anahtar"] or "", ", ".join(alici), konu, metin,
                 db_zamani(simdi), db_zamani(simdi)))

    def _guncelle(self, bildirim_id: int, **alanlar):
        atamalar = ", ".join(f"{ad} = ?" for ad in alanlar)
        with baglan() as db:
            db.execute(f"UPDATE bildirimler SET {atamalar} WHERE id = ?", (*alanlar.values(), bildirim_id))

    def _gonder(self, b: dict, simdi: datetime):
        smtp = self.ayarlar.get("smtp") or {}
        alici = adresleri_ayir(b["alicilar"])
        try:
            gonder(smtp, alici, b["konu"], b["metin"])
        except Exception as e:
            deneme = b["deneme"] + 1
            neden = type(e).__name__
            if deneme >= EN_FAZLA_DENEME:
                self._guncelle(b["id"], durum="vazgecildi", deneme=deneme, son_hata=neden)
                olay(self.log, "ERROR", b["kamera_kodu"],
                     f"E-posta gönderilemedi ({neden}), {deneme} denemeden sonra vazgeçildi: {b['konu']}")
                return
            bekle = TEKRAR_BEKLEME_SN[min(deneme - 1, len(TEKRAR_BEKLEME_SN) - 1)]
            self._guncelle(b["id"], deneme=deneme, son_hata=neden,
                           sonraki_deneme=db_zamani(simdi + timedelta(seconds=bekle)))
            # Kendi kendine tekrar denenecek: uyarı (sarı), elle müdahale gerektiren hata değil
            olay(self.log, "WARNING", b["kamera_kodu"],
                 f"E-posta gönderilemedi ({neden}), {deneme}. deneme, {bekle} sn sonra tekrar: {b['konu']}")
            return
        self._guncelle(b["id"], durum="gonderildi", gonderim_zamani=db_zamani(simdi))
        self.log.info(f"E-posta gönderildi: {b['konu']} → {b['alicilar']}")
