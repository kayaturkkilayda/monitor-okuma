"""Ayar dosyasını okuma, yazma, ilk kez oluşturma ve kameraları oluşturma."""
import copy
import json
import os
from pathlib import Path

from kamera import IPKamera, Kamera
from sifreleme import coz, sifrele

AYAR_DOSYASI = Path("config/ayarlar.json")
ORNEK_DOSYASI = Path("config/ayarlar.ornek.json")

# Şablon dosyası da yoksa kullanılacak varsayılanlar. Adres ve anahtar BOŞ gelir;
# kullanıcı bunları arayüzdeki Ayarlar sekmesinden girer.
VARSAYILAN_AYARLAR = {
    "tesis_kodu": "ORNEK",
    "api_url": "",
    "api_key": "",
    "gonderim_araligi_sn": 60,
    "ikinci_cekim_gecikme_sn": 5,
    "format": "avif",
    "kalite": 85,
    "saklama_gun": 7,
    "kayit_saklama_gun": 90,
    "gonderilince_sil": True,
    "telefon_yukleme": {"acik": False, "port": 8099},
    "izin_verilen_alan_adi": [],
    "smtp": {"sunucu": "", "port": 587, "guvenlik": "STARTTLS",
             "kullanici": "", "sifre": "", "varsayilan_alici": ""},
    "kameralar": [],
}

# Yeni dosyada her zaman boş olması gereken alanlar. Şablon elle değiştirilmiş olsa
# bile buraya bir adres ya da anahtar sızmasın diye zorlanır.
BOS_BASLATILANLAR = ("api_url", "api_key")


def _gizli_alanlara_uygula(ayarlar: dict, islem) -> dict:
    """API anahtarına, SMTP şifresine ve kamera şifrelerine işlemi uygular.

    Orijinal sözlüğe dokunmaz, kopya döndürür.
    """
    sonuc = copy.deepcopy(ayarlar)
    if "api_key" in sonuc:
        sonuc["api_key"] = islem(sonuc["api_key"])
    if "sifre" in sonuc.get("smtp", {}):
        sonuc["smtp"]["sifre"] = islem(sonuc["smtp"]["sifre"])
    for k in sonuc.get("kameralar", []):
        if "sifre" in k:
            k["sifre"] = islem(k["sifre"])
    return sonuc


def _baslangic_ayarlari(ornek: Path) -> dict:
    """Yeni ayar dosyasının içeriği: şablon varsa ondan, yoksa koddaki varsayılanlardan."""
    try:
        d = json.loads(Path(ornek).read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            raise ValueError("şablon bir nesne değil")
    except (OSError, ValueError):
        d = copy.deepcopy(VARSAYILAN_AYARLAR)
    for ad in BOS_BASLATILANLAR:
        d[ad] = ""
    if isinstance(d.get("smtp"), dict):
        d["smtp"]["sifre"] = ""
    return d


def ayarlari_hazirla(yol: Path = AYAR_DOSYASI, ornek: Path = ORNEK_DOSYASI) -> bool:
    """Ayar dosyası yoksa oluşturur. Varsa DOKUNMAZ. True = bu çağrı oluşturdu.

    Kullanıcının şablonu elle kopyalaması gerekmesin diye hem motor hem arayüz açılışta
    bunu çağırır. İkisi aynı anda açılabilir: dosya O_EXCL ile oluşturulur, yani
    "yoksa oluştur" adımı tek ve bölünmez bir işlemdir; yarışı kim kazanırsa dosyayı o
    yazar, diğeri False alır ve var olan dosyaya dokunmaz.

    Oluşturma yarıda kesilirse geriye 0 baytlık bir dosya kalabilir; bu, hiç ayarı olmayan
    bir kurulum demektir ve bir sonraki açılışta yeniden oluşturulur. Dolu bir dosyaya
    hiçbir koşulda dokunulmaz.
    """
    yol = Path(yol)
    try:
        if yol.stat().st_size > 0:
            return False                      # kullanıcının ayarları duruyor
        yol.unlink()                          # yarım kalmış oluşturmadan artan boş dosya
    except OSError:
        pass                                  # dosya yok ya da okunamadı; oluşturmayı dene

    icerik = json.dumps(_baslangic_ayarlari(ornek), ensure_ascii=False, indent=2) + "\n"
    yol.parent.mkdir(parents=True, exist_ok=True)
    try:
        # O_EXCL: dosya zaten varsa hata verir. İki süreç aynı anda denerse yalnızca biri açar.
        tutamac = os.open(yol, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False                          # yarışı başka süreç kazandı
    with os.fdopen(tutamac, "w", encoding="utf-8") as f:
        f.write(icerik)
        f.flush()
        os.fsync(f.fileno())                  # elektrik kesilirse yarım dosya kalmasın
    return True


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