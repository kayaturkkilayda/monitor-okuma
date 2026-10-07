"""E-posta bildirimleri. smtplib taklit edilir; gerçek mail gönderilmez."""
import json
import smtplib
import time
from datetime import datetime, timedelta

import pytest

import bildirim as b
import durum as durum_modulu
from ayarlar import ayarlari_oku, ayarlari_yaz
from durum import ARIZA_ESIGI, KameraDurumu
from temizlik import eski_bildirimleri_sil
from veritabani import baglan
from zaman import db_zamani

SMTP = {"sunucu": "smtp.ornek.com", "port": 587, "guvenlik": "STARTTLS", "kullanici": "bildirim@ornek.com",
        "sifre": "SmtpSifresi123", "gonderen": "monitor@ornek.com", "varsayilan_alici": "bt@ornek.com"}
KAMERA = {"kod": "K1", "yatak": "Y1", "tip": "ip", "adres": "http://10.0.0.5/shot.jpg", "aktif": True}
AYARLAR = {"tesis_kodu": "H01", "smtp": SMTP, "kameralar": [KAMERA]}


class SahteSMTP:
    """smtplib.SMTP yerine: bağlantıları ve gönderilen mailleri kaydeder."""
    baglantilar = []
    hata = None              # bir istisna verilirse send_message onu fırlatır
    bekle_sn = 0

    def __init__(self, sunucu, port, timeout=None, context=None):
        self.kayit = {"sunucu": sunucu, "port": port, "ssl": context is not None and type(self).ssl,
                      "starttls": False, "login": None, "mesajlar": []}
        SahteSMTP.baglantilar.append(self.kayit)

    ssl = False

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self, context=None): self.kayit["starttls"] = True
    def login(self, kullanici, sifre): self.kayit["login"] = (kullanici, sifre)

    def send_message(self, mesaj):
        time.sleep(SahteSMTP.bekle_sn)
        if SahteSMTP.hata:
            raise SahteSMTP.hata
        self.kayit["mesajlar"].append(mesaj)


class SahteSMTP_SSL(SahteSMTP):
    ssl = True


@pytest.fixture(autouse=True)
def sahte_smtp(monkeypatch):
    SahteSMTP.baglantilar, SahteSMTP.hata, SahteSMTP.bekle_sn = [], None, 0
    monkeypatch.setattr(b.smtplib, "SMTP", SahteSMTP)
    monkeypatch.setattr(b.smtplib, "SMTP_SSL", SahteSMTP_SSL)
    return SahteSMTP


def gonderilen_mesajlar():
    return [m for k in SahteSMTP.baglantilar for m in k["mesajlar"]]


class SahteLog:
    def __init__(self):
        self.mesajlar = []

    def info(self, m): self.mesajlar.append(m)
    def warning(self, m): self.mesajlar.append(m)
    def error(self, m): self.mesajlar.append(m)
    def exception(self, m): self.mesajlar.append(m)


def olaylar():
    with baglan() as db:
        return [dict(s) for s in db.execute("SELECT seviye, kaynak, mesaj FROM olaylar ORDER BY id")]


# ---------- Adresler ----------

def test_virgulle_birden_fazla_adres():
    assert b.adresleri_ayir(" a@x.com, b@y.com ;c@z.com,, ") == ["a@x.com", "b@y.com", "c@z.com"]


def test_gecersiz_adresler():
    assert b.gecersiz_adresler("a@x.com, yanlis, b@@y.com, c@yok") == ["yanlis", "b@@y.com", "c@yok"]


def test_kamera_adresi_yoksa_varsayilan():
    assert b.alicilar(KAMERA, SMTP) == ["bt@ornek.com"]
    assert b.alicilar({**KAMERA, "bildirim_eposta": "hemsire@ornek.com, doktor@ornek.com"}, SMTP) == \
        ["hemsire@ornek.com", "doktor@ornek.com"]


# ---------- İçerik ----------

def test_ariza_konusu_ve_icerigi():
    konu, metin = b.kamera_mesaji("ariza", "H01", KAMERA, "2026-10-04 10:00:00", "2026-10-04 09:59:00")
    assert konu == "[H01] K1 → Y1 kamera arızası"
    for parca in ("H01", "K1", "Y1", "http://10.0.0.5/shot.jpg", "04.10.2026 10:00:00", "04.10.2026 09:59:00"):
        assert parca in metin


def test_duzeldi_konusu():
    konu, _ = b.kamera_mesaji("duzeldi", "H01", KAMERA, "2026-10-04 10:00:00", "2026-10-04 10:05:00")
    assert konu == "[H01] K1 → Y1 kamera düzeldi"


def test_mailde_kamera_adresindeki_sifre_gizlenir():
    _, metin = b.kamera_mesaji("ariza", "H01", {**KAMERA, "adres": "http://admin:Gizli1@10.0.0.5/s.jpg"},
                               None, None)
    assert "Gizli1" not in metin and "admin" not in metin


# ---------- Gönderim ----------

def test_starttls_ile_gonderim():
    b.gonder(SMTP, ["bt@ornek.com"], "konu", "metin")
    (baglanti,) = SahteSMTP.baglantilar
    assert (baglanti["sunucu"], baglanti["port"], baglanti["starttls"]) == ("smtp.ornek.com", 587, True)
    assert baglanti["login"] == ("bildirim@ornek.com", "SmtpSifresi123")
    mesaj = baglanti["mesajlar"][0]
    # Gönderen artık SMTP kullanıcı adıdır; eski "gonderen" alanı dolu olsa bile o kullanılır
    assert (mesaj["From"], mesaj["To"], mesaj["Subject"]) == ("bildirim@ornek.com", "bt@ornek.com", "konu")


def test_ssl_ile_gonderim_varsayilan_port_465():
    b.gonder({**SMTP, "guvenlik": "SSL", "port": ""}, ["bt@ornek.com"], "k", "m")
    (baglanti,) = SahteSMTP.baglantilar
    assert baglanti["ssl"] and baglanti["port"] == 465 and not baglanti["starttls"]


def test_guvenliksiz_ve_kullanicisiz():
    b.gonder({**SMTP, "guvenlik": "Yok", "kullanici": "", "port": 25}, ["bt@ornek.com"], "k", "m")
    (baglanti,) = SahteSMTP.baglantilar
    assert not baglanti["starttls"] and baglanti["login"] is None


def test_test_maili_basarili():
    basarili, aciklama = b.test_maili_gonder(SMTP)
    assert basarili and "bt@ornek.com" in aciklama
    assert len(gonderilen_mesajlar()) == 1


def test_test_maili_eksik_ayar():
    assert b.test_maili_gonder({**SMTP, "sunucu": ""}) == (False, "SMTP sunucusu ve kullanıcı adı girilmeli.")
    assert b.test_maili_gonder({**SMTP, "varsayilan_alici": ""})[0] is False


def test_test_maili_hata_nedeni_sifre_gizli():
    SahteSMTP.hata = smtplib.SMTPAuthenticationError(535, b"Bad credentials for SmtpSifresi123")
    basarili, aciklama = b.test_maili_gonder(SMTP)
    assert not basarili
    assert "SMTPAuthenticationError" in aciklama and "535" in aciklama
    assert "SmtpSifresi123" not in aciklama


# ---------- Bildirici (motorun kuyruğu) ----------

@pytest.fixture
def bildirici():
    return b.Bildirici(AYARLAR, SahteLog(), baslat=False)


def test_ariza_maili_ilgili_adrese_gider(bildirici):
    bildirici.kamera_olayi("ariza", "K1", "2026-10-04 10:00:00", "2026-10-04 09:59:00")
    bildirici.isle()
    (mesaj,) = gonderilen_mesajlar()
    assert mesaj["Subject"] == "[H01] K1 → Y1 kamera arızası" and mesaj["To"] == "bt@ornek.com"


def test_ayni_ariza_icin_tek_mail(bildirici):
    for _ in range(3):
        bildirici.kamera_olayi("ariza", "K1", "2026-10-04 10:00:00", None)
        bildirici.isle()
    bildirici.kamera_olayi("duzeldi", "K1", "2026-10-04 10:00:00", "2026-10-04 10:05:00")
    bildirici.isle()
    assert [m["Subject"] for m in gonderilen_mesajlar()] == [
        "[H01] K1 → Y1 kamera arızası", "[H01] K1 → Y1 kamera düzeldi"]


def test_yeni_ariza_yeni_mail(bildirici):
    bildirici.kamera_olayi("ariza", "K1", "2026-10-04 10:00:00", None)
    bildirici.kamera_olayi("ariza", "K1", "2026-10-04 12:00:00", None)    # ertesi arıza
    bildirici.isle()
    assert len(gonderilen_mesajlar()) == 2


def test_gonderilemezse_olaylara_yazilir_ve_tekrar_denenir(bildirici):
    SahteSMTP.hata = ConnectionRefusedError()
    simdi = datetime.now()
    bildirici.kamera_olayi("ariza", "K1", "2026-10-04 10:00:00", None)
    bildirici.isle(simdi)
    (o,) = olaylar()
    # Kendi kendine tekrar denenecek: uyarı (sarı). Vazgeçilince ERROR (kırmızı) olur.
    assert (o["seviye"], o["kaynak"]) == ("WARNING", "K1")
    assert "ConnectionRefusedError" in o["mesaj"] and "60 sn sonra tekrar" in o["mesaj"]

    bildirici.isle(simdi + timedelta(seconds=30))     # bekleme dolmadan tekrar denenmez
    assert len(SahteSMTP.baglantilar) == 1

    SahteSMTP.hata = None                              # sunucu düzeldi
    bildirici.isle(simdi + timedelta(seconds=61))
    assert len(gonderilen_mesajlar()) == 1
    bildirici.isle(simdi + timedelta(days=1))         # gönderilen bir daha gitmez
    assert len(gonderilen_mesajlar()) == 1


def test_cok_kez_gonderilemezse_vazgecilir(bildirici):
    SahteSMTP.hata = smtplib.SMTPServerDisconnected()
    bildirici.kamera_olayi("ariza", "K1", "2026-10-04 10:00:00", None)
    simdi = datetime.now()
    for i in range(b.EN_FAZLA_DENEME + 3):
        bildirici.isle(simdi + timedelta(hours=i))
    assert len(SahteSMTP.baglantilar) == b.EN_FAZLA_DENEME
    assert "vazgeçildi" in olaylar()[-1]["mesaj"]


def test_smtp_ayarlanmamissa_mail_yok(bildirici):
    bildirici.ayarlari_guncelle({**AYARLAR, "smtp": {}})
    bildirici.kamera_olayi("ariza", "K1", "2026-10-04 10:00:00", None)
    bildirici.isle()
    assert SahteSMTP.baglantilar == [] and olaylar() == []


def test_kamera_olayi_maili_beklemez(bildirici):
    """Mail sunucusu ne kadar yavaş olursa olsun kamera döngüsü hemen devam eder."""
    SahteSMTP.bekle_sn = 2
    once = time.perf_counter()
    bildirici.kamera_olayi("ariza", "K1", "2026-10-04 10:00:00", None)
    assert time.perf_counter() - once < 0.1
    assert SahteSMTP.baglantilar == []


def test_bildirici_kendi_is_parcaciginda_gonderir():
    bildirici = b.Bildirici(AYARLAR, SahteLog())             # gerçek iş parçacığıyla
    try:
        bildirici.kamera_olayi("ariza", "K1", "2026-10-04 10:00:00", None)
        for _ in range(50):
            if gonderilen_mesajlar():
                break
            time.sleep(0.1)
        assert len(gonderilen_mesajlar()) == 1
    finally:
        bildirici.durdur()
    assert not bildirici._is_parcacigi.is_alive()          # başka testlerin veritabanına karışmasın


# ---------- Kamera durumuyla birlikte ----------

class KayitciBildirici:
    def __init__(self):
        self.olaylar = []

    def kamera_olayi(self, *a):
        self.olaylar.append(a)


@pytest.fixture
def durum_ortami(tmp_path, monkeypatch):
    monkeypatch.setattr(durum_modulu, "DURUM_DOSYASI", tmp_path / "durum.json")
    return KayitciBildirici()


def test_ariza_ve_duzelmede_bildirim(durum_ortami):
    d = KameraDurumu(SahteLog(), durum_ortami)
    d.bildir("H01/K1/Y1", True, kaynak="K1")
    for _ in range(ARIZA_ESIGI + 5):
        d.bildir("H01/K1/Y1", False, kaynak="K1")
    d.bildir("H01/K1/Y1", True, kaynak="K1")
    turler = [o[0] for o in durum_ortami.olaylar]
    assert turler == ["ariza", "duzeldi"]
    ariza, duzeldi = durum_ortami.olaylar
    assert ariza[1] == "K1" and ariza[3] is not None           # son başarılı görüntü zamanı
    assert duzeldi[2] == ariza[2]                               # aynı arıza başlangıcı


def test_motor_yeniden_baslayinca_suren_ariza_tekrar_bildirilmez(durum_ortami):
    ilk = KameraDurumu(SahteLog(), durum_ortami)
    for _ in range(ARIZA_ESIGI):
        ilk.bildir("H01/K1/Y1", False, kaynak="K1")
    # Motor yeniden başladı: durum durum.json'dan okunur
    yeni = KameraDurumu(SahteLog(), durum_ortami)
    for _ in range(ARIZA_ESIGI + 2):
        yeni.bildir("H01/K1/Y1", False, kaynak="K1")
    yeni.bildir("H01/K1/Y1", True, kaynak="K1")
    assert [o[0] for o in durum_ortami.olaylar] == ["ariza", "duzeldi"]


def test_bozuk_durum_dosyasi_motoru_durdurmaz(durum_ortami):
    durum_modulu.DURUM_DOSYASI.write_text("{yarım", encoding="utf-8")
    d = KameraDurumu(SahteLog(), durum_ortami)
    d.bildir("H01/K1/Y1", True, kaynak="K1")
    assert json.loads(durum_modulu.DURUM_DOSYASI.read_text(encoding="utf-8"))["H01/K1/Y1"]["durum"] == "calisiyor"


# ---------- Ayar dosyası ----------

def test_smtp_sifresi_diskte_sifreli(tmp_path):
    dosya = tmp_path / "ayarlar.json"
    ayarlari_yaz(AYARLAR, dosya)
    icerik = dosya.read_text(encoding="utf-8")
    assert "SmtpSifresi123" not in icerik
    assert json.loads(icerik)["smtp"]["sifre"].startswith("dpapi:")
    assert ayarlari_oku(dosya)["smtp"]["sifre"] == "SmtpSifresi123"
    assert AYARLAR["smtp"]["sifre"] == "SmtpSifresi123"         # bellekteki değişmez


def test_smtp_sifresi_loglara_yazilmaz(bildirici):
    SahteSMTP.hata = smtplib.SMTPAuthenticationError(535, b"SmtpSifresi123 rejected")
    bildirici.kamera_olayi("ariza", "K1", "2026-10-04 10:00:00", None)
    bildirici.isle()
    assert all("SmtpSifresi123" not in o["mesaj"] for o in olaylar())
    assert all("SmtpSifresi123" not in m for m in bildirici.log.mesajlar)


# ---------- Bildirimler tablosu ----------

def bildirimler():
    with baglan() as db:
        return [dict(r) for r in db.execute("SELECT * FROM bildirimler ORDER BY id")]


def test_bildirim_tabloya_yazilir_ve_gonderildi_isaretlenir(bildirici):
    bildirici.kamera_olayi("ariza", "K1", "2026-10-04 10:00:00", "2026-10-04 09:59:00")
    bildirici.isle()
    (satir,) = bildirimler()
    assert (satir["kamera_kodu"], satir["tur"], satir["durum"]) == ("K1", "ariza", "gonderildi")
    assert satir["alicilar"] == "bt@ornek.com" and satir["konu"] == "[H01] K1 → Y1 kamera arızası"
    assert satir["gonderim_zamani"] is not None


def test_gonderilemeyen_tabloda_bekler(bildirici):
    SahteSMTP.hata = ConnectionRefusedError()
    simdi = datetime(2026, 10, 4, 10, 0, 0)
    bildirici.kamera_olayi("ariza", "K1", "2026-10-04 10:00:00", None)
    bildirici.isle(simdi)
    (satir,) = bildirimler()
    assert (satir["durum"], satir["deneme"], satir["son_hata"]) == ("bekliyor", 1, "ConnectionRefusedError")
    assert satir["sonraki_deneme"] == "2026-10-04 10:01:00"            # 60 sn sonra


def test_motor_yeniden_baslayinca_bekleyen_kaldigi_yerden_denenir():
    SahteSMTP.hata = ConnectionRefusedError()
    simdi = datetime.now()
    ilk = b.Bildirici(AYARLAR, SahteLog(), baslat=False)
    ilk.kamera_olayi("ariza", "K1", "2026-10-04 10:00:00", None)
    ilk.isle(simdi)
    ilk.isle(simdi + timedelta(seconds=61))                 # 2. deneme de başarısız → 300 sn
    assert bildirimler()[0]["deneme"] == 2

    # Motor kapandı ve yeniden açıldı: bellekte hiçbir şey yok, yalnızca tablo
    SahteSMTP.hata = None
    yeni = b.Bildirici(AYARLAR, SahteLog(), baslat=False)
    yeni.isle(simdi + timedelta(seconds=100))               # bekleme süresi korunur
    assert gonderilen_mesajlar() == []
    yeni.isle(simdi + timedelta(seconds=61 + 301))
    assert [m["Subject"] for m in gonderilen_mesajlar()] == ["[H01] K1 → Y1 kamera arızası"]
    assert bildirimler()[0]["durum"] == "gonderildi"


def test_yeniden_baslatmada_ayni_ariza_icin_ikinci_mail_yok():
    ilk = b.Bildirici(AYARLAR, SahteLog(), baslat=False)
    ilk.kamera_olayi("ariza", "K1", "2026-10-04 10:00:00", None)
    ilk.isle()
    yeni = b.Bildirici(AYARLAR, SahteLog(), baslat=False)
    yeni.kamera_olayi("ariza", "K1", "2026-10-04 10:00:00", None)
    yeni.isle()
    assert len(gonderilen_mesajlar()) == 1 and len(bildirimler()) == 1


def test_vazgecilen_tabloda_isaretlenir(bildirici):
    SahteSMTP.hata = smtplib.SMTPServerDisconnected()
    bildirici.kamera_olayi("ariza", "K1", "2026-10-04 10:00:00", None)
    simdi = datetime.now()
    for i in range(b.EN_FAZLA_DENEME):
        bildirici.isle(simdi + timedelta(hours=i))
    (satir,) = bildirimler()
    assert (satir["durum"], satir["deneme"]) == ("vazgecildi", b.EN_FAZLA_DENEME)


def test_veritabani_yazilamazsa_olay_kaybolmaz(bildirici, monkeypatch):
    def kilitli(*a):
        raise RuntimeError("database is locked")
    bildirici.kamera_olayi("ariza", "K1", "2026-10-04 10:00:00", None)
    with monkeypatch.context() as m:
        m.setattr(bildirici, "_hazirla", kilitli)
        with pytest.raises(RuntimeError):
            bildirici.isle()
    bildirici.isle()                                         # veritabanı düzelince
    assert len(gonderilen_mesajlar()) == 1


def test_eski_bildirimler_temizlenir_bekleyenler_kalir(bildirici):
    SahteSMTP.hata = ConnectionRefusedError()
    bildirici.kamera_olayi("ariza", "K1", "2026-01-01 10:00:00", None)
    bildirici.isle()                                         # bekliyor
    SahteSMTP.hata = None
    bildirici.kamera_olayi("ariza", "K1", "2026-02-01 10:00:00", None)
    bildirici.kamera_olayi("duzeldi", "K1", "2026-02-01 10:00:00", None)
    bildirici.isle()                                         # bunlar gönderildi
    eski = db_zamani(datetime.now() - timedelta(days=100))
    with baglan() as db:
        db.execute("UPDATE bildirimler SET olusturma_zamani = ?", (eski,))
        db.execute("UPDATE bildirimler SET olusturma_zamani = ? WHERE tur = 'duzeldi'",
                   (db_zamani(datetime.now()),))
    assert eski_bildirimleri_sil(90, SahteLog()) == 1
    assert sorted(r["durum"] for r in bildirimler()) == ["bekliyor", "gonderildi"]


# ---------- Gönderen adres ----------

def test_gonderen_adres_smtp_kullanici_adidir():
    assert b.gonderen_adres(SMTP) == "bildirim@ornek.com"


def test_eski_ayarda_kullanici_yoksa_gonderen_alani_okunur():
    """Geriye uyumluluk: eski ayar dosyasında yalnızca "gonderen" vardır."""
    eski = {"sunucu": "smtp.ornek.com", "gonderen": "monitor@ornek.com"}
    assert b.gonderen_adres(eski) == "monitor@ornek.com"
    assert b.smtp_hazir_mi(eski) is True


def test_gonderen_adres_yoksa_smtp_hazir_degil():
    assert b.gonderen_adres({}) == ""
    assert b.smtp_hazir_mi({"sunucu": "smtp.ornek.com"}) is False


# ---------- Kırmızı hatalar: sorumlu kullanıcıya mail ----------

ONAYLI_KAMERA = {**KAMERA, "onaylayan": "hemsire@ornek.com",
                 "onay_zamani": "2026-10-01 09:00:00"}
ONAYLI_AYARLAR = {"tesis_kodu": "H01", "smtp": SMTP, "kameralar": [ONAYLI_KAMERA]}


def test_sorumlu_kamerayi_onaylayan_kullanicidir():
    assert b.sorumlu_adresler(ONAYLI_KAMERA, SMTP) == ["hemsire@ornek.com"]


def test_onaylayan_eposta_degilse_varsayilan_adrese_dusulur():
    """Eski kayıtlarda onaylayan Windows kullanıcı adı olabilir."""
    assert b.sorumlu_adresler({**KAMERA, "onaylayan": "ILAYDA"}, SMTP) == ["bt@ornek.com"]
    assert b.sorumlu_adresler(KAMERA, SMTP) == ["bt@ornek.com"]


def test_hata_maili_ne_oldugunu_ve_ne_yapilacagini_yazar():
    konu, metin = b.hata_mesaji("m4_hata", "H01", ONAYLI_KAMERA, "HTTP 401")
    assert konu == "[H01] K1 → Y1 M4 kalıcı hata"
    assert "K1" in metin and "Y1" in metin and "HTTP 401" in metin
    assert "NE YAPMALISINIZ" in metin
    assert "elle" in metin                      # değeri elle girmesi söyleniyor


def test_gonderilemedi_maili_elle_girmeyi_soyler():
    _, metin = b.hata_mesaji("gonderilemedi", "H01", ONAYLI_KAMERA, "dosya yok")
    assert "elle" in metin and "NE YAPMALISINIZ" in metin


def test_ariza_maili_de_ne_yapilacagini_yazar():
    _, metin = b.kamera_mesaji("ariza", "H01", ONAYLI_KAMERA, "2026-10-04 10:00:00", None)
    assert "NE YAPMALISINIZ" in metin and "elle" in metin


def test_hata_mailinde_kamera_sifresi_gizlenir():
    gizli = {**ONAYLI_KAMERA, "adres": "http://admin:Gizli123@10.0.0.5/shot.jpg"}
    _, metin = b.hata_mesaji("m4_hata", "H01", gizli, "HTTP 401")
    assert "Gizli123" not in metin and "10.0.0.5" in metin


def test_hata_olayi_sorumluya_mail_gonderir():
    bildirici = b.Bildirici(ONAYLI_AYARLAR, SahteLog(), baslat=False)
    bildirici.hata_olayi("m4_hata", "K1", "HTTP 401 2026-10-07", "K1 gönderilemedi: HTTP 401")
    bildirici.isle()
    (mesaj,) = gonderilen_mesajlar()
    assert mesaj["To"] == "hemsire@ornek.com"
    assert mesaj["Subject"] == "[H01] K1 → Y1 M4 kalıcı hata"


def test_ayni_hata_icin_tek_mail():
    bildirici = b.Bildirici(ONAYLI_AYARLAR, SahteLog(), baslat=False)
    for _ in range(5):
        bildirici.hata_olayi("m4_hata", "K1", "HTTP 401 2026-10-07", "ayrıntı")
    bildirici.isle()
    assert len(gonderilen_mesajlar()) == 1


def test_farkli_sebep_yeni_mail():
    bildirici = b.Bildirici(ONAYLI_AYARLAR, SahteLog(), baslat=False)
    bildirici.hata_olayi("m4_hata", "K1", "HTTP 401 2026-10-07", "ayrıntı")
    bildirici.hata_olayi("m4_hata", "K1", "HTTP 500 2026-10-07", "ayrıntı")
    bildirici.isle()
    assert len(gonderilen_mesajlar()) == 2


def test_hata_olayi_kuyruga_yazilir():
    """Mail gidemese bile kayıt bildirimler tablosunda durur."""
    bildirici = b.Bildirici(ONAYLI_AYARLAR, SahteLog(), baslat=False)
    SahteSMTP.hata = ConnectionRefusedError()
    bildirici.hata_olayi("gonderilemedi", "K1", "dosya yok 2026-10-07", "ayrıntı")
    bildirici.isle()
    (satir,) = bildirimler()
    assert satir["tur"] == "gonderilemedi" and satir["durum"] == "bekliyor"


def test_sifre_yoksa_giris_denenmez():
    """Gönderen adres kullanıcı adıdır; şifresiz sunucuda AUTH denenmemeli."""
    b.gonder({**SMTP, "sifre": ""}, ["bt@ornek.com"], "k", "m")
    (baglanti,) = SahteSMTP.baglantilar
    assert baglanti["login"] is None
    assert baglanti["mesajlar"][0]["From"] == "bildirim@ornek.com"   # gönderen yine doğru


def test_sifre_varsa_giris_denenir():
    b.gonder(SMTP, ["bt@ornek.com"], "k", "m")
    (baglanti,) = SahteSMTP.baglantilar
    assert baglanti["login"] == ("bildirim@ornek.com", "SmtpSifresi123")
