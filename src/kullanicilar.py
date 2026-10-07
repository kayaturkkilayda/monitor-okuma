"""Kullanıcı hesapları: kayıt, e-posta doğrulama, giriş, kilitlenme, şifre sıfırlama.

Şifreler ve doğrulama kodları düz hâliyle hiçbir yerde saklanmaz: her biri kendine
özel rastgele tuzla hashlib.scrypt'ten geçirilip saklanır. Kodun kendisi yalnızca
e-postaya yazılır; hiçbir log, olay ya da ekran mesajında yer almaz.
"""
import base64
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

from veritabani import baglan
from zaman import db_zamani

SIFRE_EN_AZ = 8
KOD_GECERLILIK_DK = 10
KOD_EN_FAZLA_DENEME = 5
GIRIS_EN_FAZLA_HATA = 5
KILIT_DK = 5

# scrypt parametreleri: n=2^14, r=8 → hash başına ~16 MB bellek, birkaç on ms
_N, _R, _P, _UZUNLUK = 2 ** 14, 8, 1, 32
_EPOSTA = re.compile(r"^[^@\s]+@([a-z0-9-]+\.)+[a-z]{2,}$")


class KullaniciHatasi(Exception):
    """Kullanıcıya olduğu gibi gösterilebilecek (gizli bilgi içermeyen) hata."""


class HesapKilitlendi(KullaniciHatasi):
    """Bu denemeyle hesap kilitlendi (arayüz bunu olaylar tablosuna yazar)."""


# ---------- Hash ----------

def hashle(gizli: str) -> str:
    """'scrypt$n$r$p$tuz$hash' biçiminde; tuz her çağrıda yeni ve rastgele."""
    tuz = secrets.token_bytes(16)
    ozet = hashlib.scrypt(gizli.encode("utf-8"), salt=tuz, n=_N, r=_R, p=_P, dklen=_UZUNLUK)
    return "$".join(["scrypt", str(_N), str(_R), str(_P),
                     base64.b64encode(tuz).decode(), base64.b64encode(ozet).decode()])


def hash_dogru_mu(gizli: str, kayitli: str) -> bool:
    try:
        _, n, r, p, tuz, ozet = kayitli.split("$")
        hesaplanan = hashlib.scrypt(gizli.encode("utf-8"), salt=base64.b64decode(tuz),
                                    n=int(n), r=int(r), p=int(p), dklen=len(base64.b64decode(ozet)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(hesaplanan, base64.b64decode(ozet))    # zamanlamadan sızıntı olmasın


# Var olmayan e-postayla girişte de aynı süre harcansın (hangi e-postaların kayıtlı olduğu anlaşılmasın)
_SAHTE_HASH = hashle(secrets.token_hex(8))


# ---------- Kurallar ----------

def eposta_normallestir(eposta: str) -> str:
    return (eposta or "").strip().lower()


def eposta_kontrol(eposta: str) -> str:
    eposta = eposta_normallestir(eposta)
    if not _EPOSTA.match(eposta):
        raise KullaniciHatasi("Geçerli bir e-posta adresi girin.")
    return eposta


def sifre_kontrol(sifre: str, tekrar: str | None = None):
    if len(sifre or "") < SIFRE_EN_AZ:
        raise KullaniciHatasi(f"Şifre en az {SIFRE_EN_AZ} karakter olmalı.")
    if tekrar is not None and sifre != tekrar:
        raise KullaniciHatasi("Şifreler birbirini tutmuyor.")


def alan_adi_normallestir(alan: str | None) -> str:
    return (alan or "").strip().lower().lstrip("@")


def alan_adi_listesi(izinli_alanlar) -> list[str]:
    """İzin verilen alan adlarını normalleştirilmiş bir listeye çevirir.

    Tek bir metin de kabul edilir: eski ayar dosyalarındaki
    "izin_verilen_alan_adi": "akgun.com.tr" biçimi böyle çalışmaya devam eder.
    Boşlar atılır, sıra korunarak tekrarlar temizlenir.
    """
    if izinli_alanlar is None:
        ham = []
    elif isinstance(izinli_alanlar, str):
        ham = [izinli_alanlar]
    else:
        ham = list(izinli_alanlar)
    liste = []
    for alan in ham:
        alan = alan_adi_normallestir(alan)
        if alan and alan not in liste:
            liste.append(alan)
    return liste


def alan_adi_izinli_mi(eposta: str, izinli_alanlar) -> bool:
    """Liste boşsa her geçerli e-posta alan adı kabul edilir; doluysa yalnızca listedekiler."""
    izinli = alan_adi_listesi(izinli_alanlar)
    if not izinli:
        return True
    return eposta_normallestir(eposta).split("@")[-1] in izinli


def _ad_kontrol(ad: str) -> str:
    ad = (ad or "").strip()
    if not ad:
        raise KullaniciHatasi("Ad boş olamaz.")
    return ad


def _kullanici(satir) -> dict | None:
    """Dışarıya şifre hash'i olmadan verilir."""
    if satir is None:
        return None
    k = dict(satir)
    k.pop("sifre_hash", None)
    k["dogrulandi"], k["yonetici"] = bool(k["dogrulandi"]), bool(k["yonetici"])
    return k


# ---------- İlk yönetici ----------

def kullanici_var_mi() -> bool:
    with baglan() as db:
        return db.execute("SELECT 1 FROM kullanicilar LIMIT 1").fetchone() is not None


def ilk_yoneticiyi_olustur(eposta: str, ad: str, sifre: str, tekrar: str | None = None,
                           simdi: datetime | None = None) -> dict:
    """Hiç kullanıcı yokken, e-posta kodu olmadan doğrulanmış yönetici hesabı açar."""
    eposta, ad = eposta_kontrol(eposta), _ad_kontrol(ad)
    sifre_kontrol(sifre, tekrar)
    sifre_hash = hashle(sifre)
    with baglan() as db:
        db.execute("BEGIN IMMEDIATE")        # iki arayüz aynı anda açılırsa yalnızca biri yönetici olur
        if db.execute("SELECT 1 FROM kullanicilar LIMIT 1").fetchone():
            raise KullaniciHatasi("İlk yönetici zaten oluşturulmuş; giriş yapın.")
        db.execute("INSERT INTO kullanicilar (eposta, ad, sifre_hash, dogrulandi, yonetici,"
                   " olusturma_zamani) VALUES (?, ?, ?, 1, 1, ?)",
                   (eposta, ad, sifre_hash, db_zamani(simdi or datetime.now())))
        return _kullanici(db.execute("SELECT * FROM kullanicilar WHERE eposta = ?", (eposta,)).fetchone())


# ---------- Doğrulama kodları ----------

def _yeni_kod(db, eposta: str, amac: str, simdi: datetime) -> str:
    kod = f"{secrets.randbelow(10 ** 6):06d}"
    db.execute("INSERT OR REPLACE INTO dogrulama_kodlari (eposta, kod_hash, amac, son_kullanma, deneme)"
               " VALUES (?, ?, ?, ?, 0)",
               (eposta, hashle(kod), amac, db_zamani(simdi + timedelta(minutes=KOD_GECERLILIK_DK))))
    return kod


def _kodu_dogrula(eposta: str, amac: str, kod: str, simdi: datetime):
    """Doğruysa kodu siler. Değilse deneme sayısını kaydedip KullaniciHatasi fırlatır."""
    hata = None
    with baglan() as db:
        satir = db.execute("SELECT * FROM dogrulama_kodlari WHERE eposta = ? AND amac = ?",
                           (eposta, amac)).fetchone()
        if satir is None:
            hata = "Geçerli bir kod yok; yeni kod isteyin."
        elif satir["son_kullanma"] < db_zamani(simdi):
            db.execute("DELETE FROM dogrulama_kodlari WHERE eposta = ? AND amac = ?", (eposta, amac))
            hata = "Kodun süresi doldu; yeni kod isteyin."
        elif not hash_dogru_mu((kod or "").strip(), satir["kod_hash"]):
            deneme = satir["deneme"] + 1
            if deneme >= KOD_EN_FAZLA_DENEME:
                db.execute("DELETE FROM dogrulama_kodlari WHERE eposta = ? AND amac = ?", (eposta, amac))
                hata = "Çok fazla hatalı deneme; yeni kod isteyin."
            else:
                db.execute("UPDATE dogrulama_kodlari SET deneme = ? WHERE eposta = ? AND amac = ?",
                           (deneme, eposta, amac))
                hata = f"Kod hatalı. Kalan deneme: {KOD_EN_FAZLA_DENEME - deneme}"
        else:
            db.execute("DELETE FROM dogrulama_kodlari WHERE eposta = ? AND amac = ?", (eposta, amac))
    # Hata, deneme sayısı kaydedildikten (işlem bittikten) sonra fırlatılır
    if hata:
        raise KullaniciHatasi(hata)


def kod_maili(amac: str, kod: str) -> tuple[str, str]:
    """(konu, metin). Kod yalnızca bu e-postanın içinde geçer."""
    if amac == "kayit":
        konu, ne = "Monitör Görüntü Aktarımı: kayıt doğrulama kodu", "Hesabınızı açmak"
    else:
        konu, ne = "Monitör Görüntü Aktarımı: şifre sıfırlama kodu", "Şifrenizi sıfırlamak"
    metin = (f"{ne} için doğrulama kodunuz: {kod}\n\n"
             f"Kod {KOD_GECERLILIK_DK} dakika geçerlidir. Bu isteği siz yapmadıysanız "
             "bu e-postayı dikkate almayın.")
    return konu, metin


# ---------- Kayıt ----------

def kayit_baslat(eposta: str, ad: str, sifre: str, tekrar: str | None, izinli_alanlar=None,
                 simdi: datetime | None = None) -> tuple[str, str]:
    """Doğrulanmamış hesap açar ve kod üretir: (normalleştirilmiş e-posta, kod).

    Kodu e-postayla göndermek çağıranın işidir; kod başka hiçbir yere yazılmamalı.
    """
    simdi = simdi or datetime.now()
    eposta, ad = eposta_kontrol(eposta), _ad_kontrol(ad)
    if not alan_adi_izinli_mi(eposta, izinli_alanlar):
        izinli = ", ".join("@" + a for a in alan_adi_listesi(izinli_alanlar))
        raise KullaniciHatasi(f"Yalnızca {izinli} adresleri kayıt olabilir.")
    sifre_kontrol(sifre, tekrar)
    sifre_hash = hashle(sifre)
    with baglan() as db:
        var = db.execute("SELECT dogrulandi FROM kullanicilar WHERE eposta = ?", (eposta,)).fetchone()
        if var and var["dogrulandi"]:
            raise KullaniciHatasi("Bu e-posta ile açılmış bir hesap var; giriş yapın.")
        if var:      # yarım kalmış kayıt: bilgiler yenilenir, yeni kod gönderilir
            db.execute("UPDATE kullanicilar SET ad = ?, sifre_hash = ? WHERE eposta = ?",
                       (ad, sifre_hash, eposta))
        else:
            db.execute("INSERT INTO kullanicilar (eposta, ad, sifre_hash, olusturma_zamani)"
                       " VALUES (?, ?, ?, ?)", (eposta, ad, sifre_hash, db_zamani(simdi)))
        return eposta, _yeni_kod(db, eposta, "kayit", simdi)


def kayit_dogrula(eposta: str, kod: str, simdi: datetime | None = None) -> dict:
    eposta = eposta_normallestir(eposta)
    _kodu_dogrula(eposta, "kayit", kod, simdi or datetime.now())
    with baglan() as db:
        db.execute("UPDATE kullanicilar SET dogrulandi = 1 WHERE eposta = ?", (eposta,))
        return _kullanici(db.execute("SELECT * FROM kullanicilar WHERE eposta = ?", (eposta,)).fetchone())


# ---------- Giriş ----------

def giris(eposta: str, sifre: str, simdi: datetime | None = None) -> dict:
    simdi = simdi or datetime.now()
    eposta = eposta_normallestir(eposta)
    with baglan() as db:
        satir = db.execute("SELECT * FROM kullanicilar WHERE eposta = ?", (eposta,)).fetchone()
    if satir is None:
        hash_dogru_mu(sifre or "", _SAHTE_HASH)
        raise KullaniciHatasi("E-posta ya da şifre hatalı.")

    if satir["kilit_bitis"] and satir["kilit_bitis"] > db_zamani(simdi):
        kalan = datetime.strptime(satir["kilit_bitis"], "%Y-%m-%d %H:%M:%S") - simdi
        dakika = max(1, -(-int(kalan.total_seconds()) // 60))
        raise KullaniciHatasi(f"Çok fazla hatalı deneme nedeniyle hesap kilitli. "
                              f"{dakika} dakika sonra tekrar deneyin.")

    if not hash_dogru_mu(sifre or "", satir["sifre_hash"]):
        hatali = satir["hatali_deneme"] + 1
        with baglan() as db:
            if hatali >= GIRIS_EN_FAZLA_HATA:
                db.execute("UPDATE kullanicilar SET hatali_deneme = 0, kilit_bitis = ? WHERE id = ?",
                           (db_zamani(simdi + timedelta(minutes=KILIT_DK)), satir["id"]))
            else:
                db.execute("UPDATE kullanicilar SET hatali_deneme = ? WHERE id = ?", (hatali, satir["id"]))
        if hatali >= GIRIS_EN_FAZLA_HATA:
            raise HesapKilitlendi(f"{GIRIS_EN_FAZLA_HATA} hatalı deneme: hesap {KILIT_DK} dakika kilitlendi.")
        raise KullaniciHatasi("E-posta ya da şifre hatalı.")

    if not satir["dogrulandi"]:
        raise KullaniciHatasi("E-posta adresi henüz doğrulanmadı; kayıt olurken gönderilen kodu girin.")

    with baglan() as db:
        db.execute("UPDATE kullanicilar SET hatali_deneme = 0, kilit_bitis = NULL, son_giris = ?"
                   " WHERE id = ?", (db_zamani(simdi), satir["id"]))
        return _kullanici(db.execute("SELECT * FROM kullanicilar WHERE id = ?", (satir["id"],)).fetchone())


def girisi_kaydet(eposta: str, simdi: datetime | None = None) -> dict:
    """Şifre sorulmadan oturum açıldığında son giriş zamanını yazar.

    Kayıt doğrulamasında kullanılır: kullanıcı e-postasına gelen kodu girdi, kimliği
    kanıtlandı. Aynı şifreyi ikinci kez sormak gereksizdir.
    """
    simdi = simdi or datetime.now()
    eposta = eposta_normallestir(eposta)
    with baglan() as db:
        db.execute("UPDATE kullanicilar SET hatali_deneme = 0, kilit_bitis = NULL, son_giris = ?"
                   " WHERE eposta = ?", (db_zamani(simdi), eposta))
        k = _kullanici(db.execute("SELECT * FROM kullanicilar WHERE eposta = ?", (eposta,)).fetchone())
    if k is None:
        raise KullaniciHatasi("Hesap bulunamadı.")
    return k


# ---------- Şifre sıfırlama ----------

def sifirlama_baslat(eposta: str, simdi: datetime | None = None) -> tuple[str, str | None]:
    """(e-posta, kod). Böyle doğrulanmış bir hesap yoksa kod None'dır; arayüz yine de aynı
    mesajı gösterir ki hangi adreslerin kayıtlı olduğu anlaşılmasın."""
    eposta = eposta_kontrol(eposta)
    with baglan() as db:
        satir = db.execute("SELECT dogrulandi FROM kullanicilar WHERE eposta = ?", (eposta,)).fetchone()
        if satir is None or not satir["dogrulandi"]:
            return eposta, None
        return eposta, _yeni_kod(db, eposta, "sifirlama", simdi or datetime.now())


def sifre_sifirla(eposta: str, kod: str, yeni_sifre: str, tekrar: str | None = None,
                  simdi: datetime | None = None):
    eposta = eposta_normallestir(eposta)
    sifre_kontrol(yeni_sifre, tekrar)
    _kodu_dogrula(eposta, "sifirlama", kod, simdi or datetime.now())
    with baglan() as db:
        db.execute("UPDATE kullanicilar SET sifre_hash = ?, hatali_deneme = 0, kilit_bitis = NULL"
                   " WHERE eposta = ?", (hashle(yeni_sifre), eposta))
        # Şifre değişince "Beni hatırla" ile açık kalan bütün cihazlardaki oturumlar kapanır
        db.execute("DELETE FROM oturumlar WHERE kullanici_id = (SELECT id FROM kullanicilar"
                   " WHERE eposta = ?)", (eposta,))


# ---------- Yönetim ----------

def kullanicilari_listele() -> list[dict]:
    with baglan() as db:
        return [_kullanici(s) for s in db.execute("SELECT * FROM kullanicilar ORDER BY eposta")]


def yonetici_yap(eposta: str):
    with baglan() as db:
        degisen = db.execute("UPDATE kullanicilar SET yonetici = 1 WHERE eposta = ? AND dogrulandi = 1",
                             (eposta_normallestir(eposta),)).rowcount
    if not degisen:
        raise KullaniciHatasi("Doğrulanmış böyle bir kullanıcı yok.")
