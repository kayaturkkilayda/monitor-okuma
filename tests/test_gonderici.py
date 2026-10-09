import re
from datetime import datetime, timedelta

import pytest
import requests

import gonderici as g
from kimlik import cift_tabani, kayit_tabani
from veritabani import baglan
from zaman import DB_BICIMI, db_zamani, saat_dilimi, simdi

OKUNUR = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")     # 2026-10-01 10:00:00


class SahteLog:
    def __init__(self):
        self.mesajlar = []

    def info(self, m): self.mesajlar.append(m)
    def warning(self, m): self.mesajlar.append(m)
    def error(self, m): self.mesajlar.append(m)
    def exception(self, m): self.mesajlar.append(m)


class TekTur:
    """Gönderici döngüsünü tek tur çalıştırıp durduran sahte 'dur' sinyali."""

    def __init__(self):
        self.bitti = False

    def is_set(self): return self.bitti
    def wait(self, sn): self.bitti = True


# M4 gönderimi kameranın sayısal M4 ID'sini ister; ID'si olmayan kameradan gönderim yapılmaz
AYARLAR = {"api_url": "http://test", "api_key": "x", "gonderilince_sil": True,
           "kameralar": [{"kod": "K1", "yatak": "Y1", "m4_id": 7}]}


def kayit(kayit_id):
    with baglan() as db:
        return dict(db.execute("SELECT * FROM kayitlar WHERE kayit_id = ?", (kayit_id,)).fetchone())


def olaylar():
    with baglan() as db:
        return [dict(s) for s in db.execute("SELECT * FROM olaylar ORDER BY id")]


def beklemeyi_atla(kayit_id, sonraki="2000-01-01 00:00:00"):
    with baglan() as db:
        db.execute("UPDATE kayitlar SET sonraki_deneme = ? WHERE kayit_id = ?", (sonraki, kayit_id))


def ornek_goruntu(yol, renk=(30, 60, 90)):
    """Gerçek bir görüntü dosyası yazar.

    Gönderim artık dosyayı açıp JPEG'e çevirdiği için içeriğin geçerli olması şart;
    eskiden rastgele baytlar yeterliydi.
    """
    from PIL import Image
    Image.new("RGB", (16, 12), renk).save(yol)
    return yol


def goruntu_ve_kayit(tmp_path, zaman=datetime(2026, 10, 1, 10, 0, 0), sira=1):
    kayit_id = kayit_tabani("H01", "K1", "Y1", zaman, sira)
    goruntu = ornek_goruntu(tmp_path / f"{kayit_id}.avif")
    cift_id = cift_tabani("H01", "K1", "Y1", zaman)
    return g.kuyruga_ekle(goruntu, "H01", "K1", "Y1", zaman, sira, cift_id, kayit_id), goruntu


@pytest.fixture
def ortam(tmp_path):
    """Geçici klasörde bir görüntü oluşturup kuyruğa ekler."""
    kayit_id, goruntu = goruntu_ve_kayit(tmp_path)
    return kayit_id, goruntu, SahteLog(), tmp_path


def api_cevabi(monkeypatch, kod=None, hata=None):
    """Gerçek gönderim yerine sabit bir cevap döndüren sahte fonksiyon koyar."""
    def sahte_gonder(ayarlar, govde):
        if hata:
            raise hata
        return kod
    monkeypatch.setattr(g, "_gonder", sahte_gonder)


# ---------- Kuyruğa ekleme ----------

def test_kuyruga_ekle_dogru_alanlari_yazar(ortam):
    kayit_id, goruntu, _, _ = ortam
    k = kayit(kayit_id)
    assert k["kayit_id"] == "H01_K1_Y1_2026-10-01_10-00-00_1"
    assert k["cift_id"] == "H01_K1_Y1_2026-10-01_10-00-00"
    assert k["tesis_kodu"] == "H01"
    assert k["kamera_kodu"] == "K1"
    assert k["yatak_kodu"] == "Y1"
    assert k["sira"] == 1
    assert k["deneme"] == 0
    assert k["durum"] == "bekliyor"
    assert k["dosya_yolu"] == str(goruntu)
    assert goruntu.stem == k["kayit_id"]          # dosya adı = kimlik
    assert k["dosya_boyutu"] == goruntu.stat().st_size
    assert k["gonderim_zamani"] is None


def test_veritabaninda_zamanlar_okunur_yerel_saat(ortam):
    kayit_id, _, _, _ = ortam
    k = kayit(kayit_id)
    assert k["cekim_zamani"] == "2026-10-01 10:00:00"     # T harfi ve +03:00 yok
    assert k["saat_dilimi"] == saat_dilimi(datetime(2026, 10, 1, 10, 0, 0))
    assert re.fullmatch(r"[+-]\d\d:\d\d", k["saat_dilimi"])
    assert k["sonraki_deneme"] == k["cekim_zamani"]       # çekildiği andan itibaren gönderilebilir


# ---------- Tek kaydın işlenmesi ----------

def test_basarili_gonderim_gecmiste_kalir_ve_goruntuyu_siler(ortam, monkeypatch):
    kayit_id, goruntu, log, _ = ortam
    api_cevabi(monkeypatch, kod=201)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    k = kayit(kayit_id)                     # kayıt silinmez, geçmiş olarak kalır
    assert k["durum"] == "gonderildi"
    assert OKUNUR.match(k["gonderim_zamani"])
    assert not goruntu.exists()


def test_gonderilince_sil_kapaliysa_goruntu_kalir(ortam, monkeypatch):
    kayit_id, goruntu, log, _ = ortam
    api_cevabi(monkeypatch, kod=201)
    g._kaydi_isle(kayit_id, {**AYARLAR, "gonderilince_sil": False}, log)
    assert kayit(kayit_id)["durum"] == "gonderildi"
    assert goruntu.exists()


def test_gecici_hata_kuyrukta_tutar_ve_bekletir(ortam, monkeypatch):
    kayit_id, goruntu, log, _ = ortam
    api_cevabi(monkeypatch, kod=503)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    k = kayit(kayit_id)
    assert k["durum"] == "bekliyor"
    assert k["deneme"] == 1
    assert k["sonraki_deneme"] > simdi()
    assert OKUNUR.match(k["sonraki_deneme"])
    assert k["son_hata"] == "HTTP 503"
    assert goruntu.exists()


def test_baglanti_kopunca_veri_kaybolmaz(ortam, monkeypatch):
    kayit_id, goruntu, log, _ = ortam
    api_cevabi(monkeypatch, hata=requests.ConnectionError())
    g._kaydi_isle(kayit_id, AYARLAR, log)
    k = kayit(kayit_id)
    assert k["durum"] == "bekliyor"
    assert k["son_hata"] == "ConnectionError"
    assert goruntu.exists()


def test_bekleme_suresi_her_denemede_artar(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=503)
    for beklenen in g.BEKLEME_SN[:3]:
        beklemeyi_atla(kayit_id)
        once = datetime.now()
        g._kaydi_isle(kayit_id, AYARLAR, log)
        sonraki = datetime.strptime(kayit(kayit_id)["sonraki_deneme"], DB_BICIMI)
        # Saniye hassasiyetinde saklandığı için en fazla 1 sn sapma olabilir
        assert abs((sonraki - once).total_seconds() - beklenen) <= 1


def test_kalici_hata_hatali_olarak_isaretler(ortam, monkeypatch):
    kayit_id, goruntu, log, _ = ortam
    api_cevabi(monkeypatch, kod=401)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    k = kayit(kayit_id)
    assert k["durum"] == "hatali"
    assert k["son_hata"] == "HTTP 401"
    assert goruntu.exists()                 # görüntü silinmez, elle incelenecek


def test_hatali_kayit_tekrar_gonderilmez(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=401)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    api_cevabi(monkeypatch, hata=AssertionError("hatalı kayıt gönderilmemeliydi"))
    g._kaydi_isle(kayit_id, AYARLAR, log)
    assert g._siradakiler() == []


def test_bekleme_suresi_dolmadan_gondermez(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    beklemeyi_atla(kayit_id, sonraki=db_zamani(datetime.now() + timedelta(hours=1)))
    api_cevabi(monkeypatch, hata=AssertionError("gönderim denenmemeliydi"))
    g._kaydi_isle(kayit_id, AYARLAR, log)
    assert kayit(kayit_id)["durum"] == "bekliyor"
    assert g._siradakiler() == []


def test_goruntu_silinmisse_kayit_kuyruktan_cikar(ortam, monkeypatch):
    kayit_id, goruntu, log, _ = ortam
    goruntu.unlink()
    api_cevabi(monkeypatch, kod=201)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    assert kayit(kayit_id)["durum"] == "hatali"
    assert g._siradakiler() == []
    assert any("bulunamadı" in m for m in log.mesajlar)


def test_gecici_hata_olaylara_uyari_olarak_yazilir(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=503)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    olay = olaylar()[-1]
    assert (olay["seviye"], olay["kaynak"]) == ("WARNING", "K1")
    assert "HTTP 503" in olay["mesaj"]
    assert olay["mesaj"] in log.mesajlar     # log dosyasına da aynı mesaj gider


def test_kalici_hata_olaylara_hata_olarak_yazilir(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=401)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    olay = olaylar()[-1]
    assert (olay["seviye"], olay["kaynak"]) == ("ERROR", "K1")


def test_basarili_gonderim_olaylara_yazilmaz(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=201)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    assert olaylar() == []


# ---------- Gönderici döngüsü ----------

def test_siradakiler_cekim_sirasina_gore_ve_sadece_zamani_gelenler(tmp_path):
    gec, _ = goruntu_ve_kayit(tmp_path, datetime(2026, 10, 1, 10, 0, 10))
    erken, _ = goruntu_ve_kayit(tmp_path, datetime(2026, 10, 1, 10, 0, 0))
    bekleyecek, _ = goruntu_ve_kayit(tmp_path, datetime(2026, 10, 1, 10, 0, 5))
    beklemeyi_atla(bekleyecek, sonraki=db_zamani(datetime.now() + timedelta(hours=1)))
    gonderilmis, _ = goruntu_ve_kayit(tmp_path, datetime(2026, 10, 1, 9, 0, 0))
    with baglan() as db:
        db.execute("UPDATE kayitlar SET durum = 'gonderildi' WHERE kayit_id = ?", (gonderilmis,))
    assert g._siradakiler() == [erken, gec]


def test_tek_bozuk_kayit_gondericiyi_durdurmaz(tmp_path, monkeypatch):
    bozuk, _ = goruntu_ve_kayit(tmp_path, datetime(2026, 10, 1, 10, 0, 0))
    saglam, _ = goruntu_ve_kayit(tmp_path, datetime(2026, 10, 1, 10, 0, 5))
    bozuk_capture = kayit(bozuk)["capture_id"]

    def sahte_gonder(ayarlar, govde):
        if govde["captureId"] == bozuk_capture:
            raise ValueError("beklenmeyen")
        return 201
    monkeypatch.setattr(g, "_gonder", sahte_gonder)

    log = SahteLog()
    g.gonderici_dongusu(AYARLAR, log, TekTur())
    assert kayit(saglam)["durum"] == "gonderildi"
    assert kayit(bozuk)["durum"] == "bekliyor"
    assert any("beklenmeyen hata" in m for m in log.mesajlar)
    assert olaylar()[-1]["seviye"] == "ERROR"


def test_veritabani_okunamazsa_gonderici_durmaz(monkeypatch):
    def bozuk():
        raise RuntimeError("veritabanı yok")
    monkeypatch.setattr(g, "_siradakiler", bozuk)
    log = SahteLog()
    g.gonderici_dongusu(AYARLAR, log, TekTur())      # hata fırlatmadan dönmeli
    assert any("kuyruğu okunamadı" in m for m in log.mesajlar)


def test_once_hata_sonra_basari_gecmiste_iz_birakir(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=503)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    beklemeyi_atla(kayit_id)
    api_cevabi(monkeypatch, kod=201)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    k = kayit(kayit_id)
    assert (k["durum"], k["deneme"], k["son_hata"]) == ("gonderildi", 1, "HTTP 503")


# ---------- Kırmızı hatada sorumluya bildirim ----------

class KayitciBildirici:
    """hata_olayi çağrılarını kaydeder; mail göndermez."""

    def __init__(self):
        self.olaylar = []

    def hata_olayi(self, tur, kamera_kodu, anahtar, ayrinti):
        self.olaylar.append((tur, kamera_kodu, anahtar, ayrinti))


def test_kalici_hata_sorumluya_bildirilir(ortam, monkeypatch):
    """401 gibi kalıcı hatalar elle müdahale ister: mail kuyruğuna düşer."""
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=401)
    bildirici = KayitciBildirici()
    g._kaydi_isle(kayit_id, AYARLAR, log, bildirici)
    assert kayit(kayit_id)["durum"] == "hatali"
    (tur, kamera, anahtar, ayrinti) = bildirici.olaylar[0]
    assert tur == "m4_hata" and kamera == "K1"
    assert "api anahtari" in anahtar
    assert "anahtar" in ayrinti.lower() and "Ayarlar" in ayrinti


def test_tekrar_denenen_hata_bildirilmez(ortam, monkeypatch):
    """503 kendi kendine tekrar denenir (sarı); kimseye mail gitmez."""
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=503)
    bildirici = KayitciBildirici()
    g._kaydi_isle(kayit_id, AYARLAR, log, bildirici)
    assert kayit(kayit_id)["durum"] == "bekliyor"
    assert bildirici.olaylar == []


def test_goruntu_dosyasi_yoksa_bildirilir(ortam, monkeypatch):
    kayit_id, goruntu, log, _ = ortam
    goruntu.unlink()
    bildirici = KayitciBildirici()
    g._kaydi_isle(kayit_id, AYARLAR, log, bildirici)
    assert kayit(kayit_id)["durum"] == "hatali"
    assert bildirici.olaylar[0][0] == "gonderilemedi"


def test_bildirici_verilmezse_gonderim_calisir(ortam, monkeypatch):
    """Bildirici isteğe bağlıdır; yoksa hata yalnızca loglara yazılır."""
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=401)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    assert kayit(kayit_id)["durum"] == "hatali"


def test_ayni_sebep_ayni_gun_tek_anahtar():
    """Aynı gün aynı sebep tek anahtar üretir: M4 kapalıyken mail yağmuru olmaz."""
    sabah = datetime(2026, 10, 7, 8, 0, 0)
    aksam = datetime(2026, 10, 7, 20, 0, 0)
    ertesi = datetime(2026, 10, 8, 8, 0, 0)
    assert g._hata_anahtari("HTTP 401", sabah) == g._hata_anahtari("HTTP 401", aksam)
    assert g._hata_anahtari("HTTP 401", sabah) != g._hata_anahtari("HTTP 401", ertesi)
    assert g._hata_anahtari("HTTP 401", sabah) != g._hata_anahtari("HTTP 404", sabah)


# ---------- M4 gövdesi ----------
#
# Alan adları, tipleri ve zaman biçimi M4'ün beklediği gibi BİREBİR olmalı.
# Koda hiçbir adres ya da anahtar yazılmaz; ikisi de kullanıcının Ayarlar'da girdiği
# değerlerden gelir.

import base64
import json as _json

from PIL import Image


def _govde(ortam, **ayar_ustu):
    kayit_id, goruntu, _, _ = ortam
    return g.m4_govdesi(kayit(kayit_id), 7, goruntu)


def test_govde_tam_olarak_beklenen_alanlari_icerir(ortam):
    govde = _govde(ortam)
    assert set(govde) == {"captureId", "kameraKodu", "kameraId", "yatakEslesmeKodu",
                          "goruntuCekilmeZamani", "goruntuFormati", "goruntuBase64"}


def test_govde_alan_tipleri(ortam):
    govde = _govde(ortam)
    assert isinstance(govde["captureId"], str)
    assert isinstance(govde["kameraKodu"], str)
    assert isinstance(govde["kameraId"], int) and not isinstance(govde["kameraId"], bool)
    assert isinstance(govde["yatakEslesmeKodu"], str)
    assert isinstance(govde["goruntuCekilmeZamani"], str)
    assert isinstance(govde["goruntuBase64"], str)
    assert govde["goruntuFormati"] == "jpeg"          # ayar avif olsa bile


def test_kamera_ve_yatak_kodlari_bizdeki_degerlerden_gelir(ortam):
    govde = _govde(ortam)
    assert govde["kameraKodu"] == "K1"
    assert govde["yatakEslesmeKodu"] == "Y1"
    assert govde["kameraId"] == 7


def test_zaman_bicimi_milisaniyeli_ve_dilimsiz(ortam):
    """2026-10-01T10:00:00.000 — 3 hane ms, sonda Z ya da +03:00 YOK."""
    zaman = _govde(ortam)["goruntuCekilmeZamani"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}", zaman), zaman
    assert not zaman.endswith("Z") and "+" not in zaman
    assert zaman.startswith("2026-10-01T10:00:00")


def test_zaman_milisaniyeyi_korur():
    assert g.m4_zamani("2026-10-09 07:48:43", 650) == "2026-10-09T07:48:43.650"
    assert g.m4_zamani("2026-10-09 07:48:43", 5) == "2026-10-09T07:48:43.005"
    assert g.m4_zamani("2026-10-09 07:48:43", 0) == "2026-10-09T07:48:43.000"


def test_cekim_milisaniyesi_veritabaninda_saklanir(tmp_path):
    zaman = datetime(2026, 10, 1, 10, 0, 0, 123000)
    kid = kayit_tabani("H01", "K1", "Y1", zaman, 1)
    ornek_goruntu(tmp_path / f"{kid}.avif")
    g.kuyruga_ekle(tmp_path / f"{kid}.avif", "H01", "K1", "Y1", zaman, 1,
                   cift_tabani("H01", "K1", "Y1", zaman), kid)
    assert kayit(kid)["cekim_ms"] == 123


def test_base64_onek_icermez_ve_cozulebilir(ortam):
    b64 = _govde(ortam)["goruntuBase64"]
    assert not b64.startswith("data:")
    ham = base64.b64decode(b64, validate=True)
    with Image.open(_io_bytes(ham)) as goruntu:
        assert goruntu.format == "JPEG"             # avif kaydedilse de jpeg gider


def _io_bytes(ham):
    import io as _i
    return _i.BytesIO(ham)


def test_avif_kayit_jpege_cevrilir(tmp_path):
    yol = ornek_goruntu(tmp_path / "x.avif")
    with Image.open(yol) as g_:
        assert g_.format == "AVIF"
    ham = base64.b64decode(g.jpeg_base64(yol), validate=True)
    with Image.open(_io_bytes(ham)) as g_:
        assert g_.format == "JPEG"


def test_jpeg_kayit_yeniden_sikistirilmaz(tmp_path):
    """Zaten JPEG olan dosya olduğu gibi gider; gereksiz kalite kaybı olmaz."""
    yol = ornek_goruntu(tmp_path / "x.jpg")
    assert base64.b64decode(g.jpeg_base64(yol)) == yol.read_bytes()


def test_capture_id_uuid_ve_tekrar_denemede_degismez(ortam, monkeypatch):
    import uuid as _uuid
    kayit_id, _, log, _ = ortam
    ilk = kayit(kayit_id)["capture_id"]
    _uuid.UUID(ilk)                                  # geçerli UUID mi?

    api_cevabi(monkeypatch, kod=503)                 # geçici hata, tekrar denenecek
    g._kaydi_isle(kayit_id, AYARLAR, log)
    assert kayit(kayit_id)["durum"] == "bekliyor"
    assert kayit(kayit_id)["capture_id"] == ilk      # tekrar denemede AYNI


def test_her_kare_kendi_capture_id_sini_alir(tmp_path):
    bir, _ = goruntu_ve_kayit(tmp_path, datetime(2026, 10, 1, 10, 0, 0), sira=1)
    iki, _ = goruntu_ve_kayit(tmp_path, datetime(2026, 10, 1, 10, 0, 0), sira=2)
    assert kayit(bir)["capture_id"] != kayit(iki)["capture_id"]


# ---------- İstek: adres, başlık, yöntem ----------

def test_girilen_adrese_aynen_gonderilir(ortam, monkeypatch):
    """Koda yol eklenmez, adres değiştirilmez."""
    yakalanan = {}

    class Yanit:
        status_code = 200

    monkeypatch.setattr(g.requests, "post",
                        lambda url, **k: yakalanan.update(url=url, **k) or Yanit())
    adres = "https://ornek.test/herhangi/bir/yol?x=1"
    g._gonder({**AYARLAR, "api_url": adres, "api_key": "ANAHTAR"}, {"a": 1})
    assert yakalanan["url"] == adres                 # aynen, ek yol yok


def test_basliklar_birebir(ortam, monkeypatch):
    yakalanan = {}

    class Yanit:
        status_code = 200

    monkeypatch.setattr(g.requests, "post",
                        lambda url, **k: yakalanan.update(k) or Yanit())
    g._gonder({**AYARLAR, "api_key": "GIZLI-ANAHTAR"}, {"a": 1})
    assert yakalanan["headers"]["X-Api-Key"] == "GIZLI-ANAHTAR"
    assert yakalanan["headers"]["Content-Type"] == "application/json"
    assert yakalanan["json"] == {"a": 1}             # gövde JSON olarak gider


def test_govde_json_olarak_serilesebilir(ortam):
    _json.dumps(_govde(ortam))                       # patlamamalı


# ---------- Adres/anahtar yoksa gönderim yok ----------

@pytest.mark.parametrize("eksik", ["api_url", "api_key"])
def test_adres_ya_da_anahtar_bossa_gonderim_yapilmaz(ortam, monkeypatch, eksik):
    kayit_id, _, log, _ = ortam
    monkeypatch.setattr(g.requests, "post",
                        lambda *a, **k: pytest.fail("gönderim yapılmamalıydı"))
    g._kaydi_isle(kayit_id, {**AYARLAR, eksik: ""}, log)
    assert kayit(kayit_id)["durum"] == "bekliyor"        # kuyrukta kalır, kaybolmaz
    son = olaylar()[-1]
    assert son["seviye"] == "WARNING"
    assert "M4 adresi/anahtarı ayarlanmamış" in son["mesaj"]


def test_sadece_bosluk_girilmisse_de_gonderim_yapilmaz(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    monkeypatch.setattr(g.requests, "post",
                        lambda *a, **k: pytest.fail("gönderim yapılmamalıydı"))
    g._kaydi_isle(kayit_id, {**AYARLAR, "api_key": "   "}, log)
    assert olaylar()[-1]["seviye"] == "WARNING"


def test_kamera_m4_id_girilmemisse_gonderim_yapilmaz(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    monkeypatch.setattr(g.requests, "post",
                        lambda *a, **k: pytest.fail("gönderim yapılmamalıydı"))
    ayarlar = {**AYARLAR, "kameralar": [{"kod": "K1", "yatak": "Y1", "m4_id": ""}]}
    g._kaydi_isle(kayit_id, ayarlar, log)
    assert kayit(kayit_id)["durum"] == "bekliyor"
    son = olaylar()[-1]
    assert son["seviye"] == "WARNING" and "M4 kamera ID" in son["mesaj"]


def test_kamera_m4_id_okunmasi():
    ayarlar = {"kameralar": [{"kod": "K1", "m4_id": "42"}, {"kod": "K2", "m4_id": 7},
                             {"kod": "K3"}, {"kod": "K4", "m4_id": "abc"}]}
    assert g.kamera_m4_id(ayarlar, "K1") == 42        # metin de sayıya çevrilir
    assert g.kamera_m4_id(ayarlar, "K2") == 7
    assert g.kamera_m4_id(ayarlar, "K3") is None      # alan yok
    assert g.kamera_m4_id(ayarlar, "K4") is None      # sayı değil
    assert g.kamera_m4_id(ayarlar, "YOK") is None     # kamera silinmiş


# ---------- Hata kuralları ----------

@pytest.mark.parametrize("kod", [401, 403])
def test_yetki_hatasi_kirmizi_log_ve_eposta(ortam, monkeypatch, kod):
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=kod)
    bildirici = KayitciBildirici()
    g._kaydi_isle(kayit_id, AYARLAR, log, bildirici)
    assert kayit(kayit_id)["durum"] == "hatali"       # tekrar denenmez
    son = olaylar()[-1]
    assert son["seviye"] == "ERROR" and "API anahtarı hatalı" in son["mesaj"]
    assert bildirici.olaylar                          # e-posta kuyruğa düştü


def test_400_tekrar_denenmez_kirmizi_log_eposta_yok(ortam, monkeypatch):
    """400 gövde biçimi hatasıdır; tekrar denemek aynı sonucu verir, mail de gereksiz."""
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=400)
    bildirici = KayitciBildirici()
    g._kaydi_isle(kayit_id, AYARLAR, log, bildirici)
    assert kayit(kayit_id)["durum"] == "hatali"
    assert olaylar()[-1]["seviye"] == "ERROR"
    assert bildirici.olaylar == []


@pytest.mark.parametrize("kod", [500, 502, 503])
def test_sunucu_hatasi_tekrar_denenir(ortam, monkeypatch, kod):
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=kod)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    assert kayit(kayit_id)["durum"] == "bekliyor"
    assert olaylar()[-1]["seviye"] == "WARNING"


def test_zaman_asimi_tekrar_denenir(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, hata=requests.Timeout("zaman asimi"))
    g._kaydi_isle(kayit_id, AYARLAR, log)
    assert kayit(kayit_id)["durum"] == "bekliyor"
    assert olaylar()[-1]["seviye"] == "WARNING"


def test_2xx_basarili_sayilir(ortam, monkeypatch):
    kayit_id, _, log, _ = ortam
    api_cevabi(monkeypatch, kod=204)
    g._kaydi_isle(kayit_id, AYARLAR, log)
    assert kayit(kayit_id)["durum"] == "gonderildi"


def test_bozuk_goruntu_kuyruktan_cikar(ortam, monkeypatch):
    """Dosya açılamıyorsa gönderim hatası değil, dosya hatasıdır."""
    kayit_id, goruntu, log, _ = ortam
    goruntu.write_bytes(b"bu bir goruntu degil")
    monkeypatch.setattr(g.requests, "post",
                        lambda *a, **k: pytest.fail("ağa çıkılmamalıydı"))
    g._kaydi_isle(kayit_id, AYARLAR, log)
    assert kayit(kayit_id)["durum"] == "hatali"
    assert "JPEG'e çevrilemedi" in olaylar()[-1]["mesaj"]
