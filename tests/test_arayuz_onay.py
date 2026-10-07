"""Arayüzdeki e-posta kodlu kamera onayı: gerçek Uygulama penceresi, sahte ayar dosyası,
sahte e-posta gönderimi ve sahte kamerayla."""
import logging
import re

import numpy as np
import pytest

import arka_plan
import onay
import sahiplik
from veritabani import baglan

SMTP = {"sunucu": "127.0.0.1", "port": 1025, "guvenlik": "Yok", "gonderen": "monitor@akgun.com.tr"}
AYARLAR = {"tesis_kodu": "H01", "api_url": "", "api_key": "", "gonderim_araligi_sn": 30,
           "ikinci_cekim_gecikme_sn": 5, "format": "avif", "kalite": 85, "saklama_gun": 7,
           "gonderilince_sil": True, "kameralar": []}
KULLANICI = {"eposta": "ayse@akgun.com.tr", "ad": "Ayşe", "yonetici": False}
YONETICI = {"eposta": "bt@akgun.com.tr", "ad": "BT", "yonetici": True}
KAMERA = {"kod": "K1", "yatak": "Y1", "tip": "ip", "adres": "http://10.0.0.5/shot.jpg",
          "kullanici": "", "sifre": "", "aktif": True}


class HemenCalisan:
    """Testte ana döngü yok; arka plan işini hemen çalıştırır."""

    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


class SahteKamera:
    def __init__(self):
        self.cekim = 0

    def cift_cekim(self, aralik_sn=0):
        self.cekim += 1
        return np.zeros((4, 4, 3), dtype=np.uint8), 0, None, 0


class KayitciLog(logging.Handler):
    def __init__(self):
        super().__init__()
        self.mesajlar = []

    def emit(self, kayit):
        self.mesajlar.append(kayit.getMessage())


LOG = logging.getLogger("test-arayuz-onay")
KAYITCI = KayitciLog()
LOG.addHandler(KAYITCI)


@pytest.fixture(scope="module")
def uygulama(tk_kok):
    mp = pytest.MonkeyPatch()
    import arayuz
    from conftest import tk_ac
    mp.setattr(arayuz, "ayarlari_oku", lambda: {**AYARLAR, "kameralar": []})
    mp.setattr(arayuz, "durumlari_oku", lambda: {})
    uyg = tk_ac(lambda: arayuz.Uygulama(dict(KULLANICI), LOG))
    uyg.withdraw()
    yield arayuz, uyg
    uyg.destroy()
    mp.undo()


@pytest.fixture
def ortam(uygulama, monkeypatch):
    arayuz, uyg = uygulama
    o = {"mailler": [], "kaydedilen": [], "sorulan": [], "mesajlar": [], "cevap": True, "kod": None,
         "kamera": SahteKamera(), "form": None, "mail_hatasi": None,
         "kod_soruldu": 0, "kod_hatalari": []}

    def sahte_gonder(smtp, alici, konu, metin):
        if o["mail_hatasi"]:
            raise o["mail_hatasi"]
        o["mailler"].append((alici, konu, metin))

    monkeypatch.setattr(arayuz, "gonder", sahte_gonder)
    monkeypatch.setattr(arayuz, "ayarlari_yaz", lambda a: o["kaydedilen"].append([dict(k) for k in a["kameralar"]]))
    monkeypatch.setattr(arayuz, "kameralari_olustur", lambda a: [o["kamera"]])
    monkeypatch.setattr(arayuz, "onizleme_ac", lambda *a: None)
    monkeypatch.setattr(arka_plan.threading, "Thread", HemenCalisan)
    for tur in ("showinfo", "showerror", "showwarning"):
        monkeypatch.setattr(arayuz.messagebox, tur,
                            lambda baslik, mesaj, tur=tur, **k: o["mesajlar"].append((tur, baslik, mesaj)))
    monkeypatch.setattr(arayuz.messagebox, "askyesno",
                        lambda baslik, mesaj, **k: o["sorulan"].append(mesaj) or o["cevap"])
    class SahteKodPenceresi:
        """KodPenceresi yerine: pencere açmadan o["kod"] ile doğrular."""

        def __init__(self, ust, baslik, aciklama, dogrula, hata_sinifi):
            self.sonuc = None
            o["kod_soruldu"] += 1
            if not o["kod"]:
                return
            try:
                self.sonuc = dogrula(o["kod"])
            except hata_sinifi as e:
                o["kod_hatalari"].append(str(e))      # gerçekte pencerede gösterilir

    monkeypatch.setattr(arayuz, "KodPenceresi", SahteKodPenceresi)

    class SahteForm:
        """KameraFormu yerine: pencere açmadan hazır sonucu döndürür."""
        def __init__(self, ust, diger, kamera=None):
            self.sonuc = o["form"]
    monkeypatch.setattr(arayuz, "KameraFormu", SahteForm)
    monkeypatch.setattr(uyg, "wait_window", lambda w: None)

    uyg.oturum = dict(KULLANICI)
    uyg.ayarlar.update(smtp=dict(SMTP), kameralar=[])
    uyg._listeyi_doldur()
    return uyg, o


def durum_yazisi(uyg, kod="K1"):
    return uyg.liste.item(kod, "values")[4]


def olaylar():
    with baglan() as db:
        return [dict(s) for s in db.execute("SELECT seviye, kaynak, mesaj FROM olaylar ORDER BY id")]


def mailden_kod(mail):
    return re.search(r"Onay kodu\s*:\s*(\d{6})", mail[2]).group(1)


def ekle(uyg, o, kamera=KAMERA):
    o["form"] = dict(kamera)
    uyg._ekle()
    uyg.update()
    uyg.liste.selection_set(kamera["kod"])


# ---------- Ekleme ve mail ----------

def test_eklenince_onay_maili_gider_ve_onay_bekler(ortam):
    uyg, o = ortam
    ekle(uyg, o)
    (alici, konu, metin), = o["mailler"]
    # Onay kodu, kamerayı ekleyen (giriş yapmış) kullanıcıya gider
    assert alici == [KULLANICI["eposta"]] and konu == "[H01] K1 → Y1 kamera kullanım onayı"
    assert "ayse@akgun.com.tr" in metin                                  # ekleyen kullanıcı
    assert not onay.onayli_mi(uyg.ayarlar["kameralar"][0])
    assert durum_yazisi(uyg) == "Onay bekliyor (mail gönderildi)"
    assert "onay maili gönderildi: ayse@akgun.com.tr" in olaylar()[-1]["mesaj"]


def test_dogru_kodla_onaylanir_onaylayan_mail_adresi(ortam):
    uyg, o = ortam
    ekle(uyg, o)
    o["kod"] = mailden_kod(o["mailler"][0])
    uyg._onay_kodu_gir()
    k = uyg.ayarlar["kameralar"][0]
    assert onay.onayli_mi(k) and k["onaylayan"] == KULLANICI["eposta"]
    assert o["kaydedilen"][-1][0]["onaylayan"] == KULLANICI["eposta"]
    assert olaylar()[-1]["mesaj"] == ("K1 kullanımı onaylandı (onaylayan: ayse@akgun.com.tr, "
                                      "kodu giren: ayse@akgun.com.tr)")
    assert durum_yazisi(uyg) != "Onay bekliyor (mail gönderildi)"


def test_yanlis_kodla_onaylanmaz(ortam):
    uyg, o = ortam
    ekle(uyg, o)
    kod = mailden_kod(o["mailler"][0])
    o["kod"] = "000000" if kod != "000000" else "111111"
    uyg._onay_kodu_gir()
    assert not onay.onayli_mi(uyg.ayarlar["kameralar"][0])
    # Hata artık kod penceresinin içinde gösterilir, ayrı bir uyarı kutusunda değil
    assert "Kalan deneme: 4" in o["kod_hatalari"][-1]


def test_tekrar_gonderimde_eski_kod_gecersiz(ortam):
    uyg, o = ortam
    ekle(uyg, o)
    uyg._onay_mailini_tekrar_gonder()
    eski, yeni = mailden_kod(o["mailler"][0]), mailden_kod(o["mailler"][1])
    if eski != yeni:
        o["kod"] = eski
        uyg._onay_kodu_gir()
        assert not onay.onayli_mi(uyg.ayarlar["kameralar"][0])
    o["kod"] = yeni
    uyg._onay_kodu_gir()
    assert onay.onayli_mi(uyg.ayarlar["kameralar"][0])


def test_mail_gonderilemezse_kod_silinir(ortam):
    uyg, o = ortam
    o["mail_hatasi"] = ConnectionRefusedError()
    ekle(uyg, o)
    assert durum_yazisi(uyg) == "Onay bekliyor"
    assert o["mesajlar"][-1][0] == "showerror" and "ConnectionRefusedError" in o["mesajlar"][-1][2]
    assert olaylar()[-1]["seviye"] == "WARNING"
    uyg._onay_kodu_gir()                                                # geçerli kod yok
    assert "geçerli bir onay kodu yok" in o["mesajlar"][-1][2]


def test_adres_degisince_onay_duser_ve_yeni_mail_gider(ortam):
    uyg, o = ortam
    # Kamerayı listede görebilmek için sahibi oturumdaki kullanıcı olmalı
    uyg.ayarlar["kameralar"] = [sahiplik.sahiplendir(
        onay.onay_ver(dict(KAMERA), "sahip@ornek.com"), KULLANICI["eposta"])]
    uyg._listeyi_doldur()
    uyg.liste.selection_set("K1")
    o["form"] = {**KAMERA, "adres": "http://10.0.0.99/shot.jpg"}
    uyg._duzenle()
    uyg.update()
    assert not onay.onayli_mi(uyg.ayarlar["kameralar"][0])
    assert len(o["mailler"]) == 1 and "10.0.0.99" in o["mailler"][0][2]


def test_adres_ayni_kalirsa_onay_korunur_mail_gitmez(ortam):
    uyg, o = ortam
    # Kamerayı listede görebilmek için sahibi oturumdaki kullanıcı olmalı
    uyg.ayarlar["kameralar"] = [sahiplik.sahiplendir(
        onay.onay_ver(dict(KAMERA), "sahip@ornek.com"), KULLANICI["eposta"])]
    uyg._listeyi_doldur()
    uyg.liste.selection_set("K1")
    o["form"] = {**KAMERA, "yatak": "Y9"}
    uyg._duzenle()
    assert onay.onayli_mi(uyg.ayarlar["kameralar"][0]) and o["mailler"] == []


# ---------- SMTP yokken ----------

def test_smtp_yokken_yonetici_epostasiz_onay_verebilir(ortam):
    uyg, o = ortam
    uyg.oturum = dict(YONETICI)
    uyg.ayarlar["smtp"] = {}
    ekle(uyg, o)
    assert o["mailler"] == [] and "E-POSTASIZ ONAY" in o["sorulan"][-1]
    k = uyg.ayarlar["kameralar"][0]
    assert onay.onayli_mi(k) and k["onaylayan"] == "bt@akgun.com.tr"
    son = olaylar()[-1]
    assert son["seviye"] == "WARNING" and son["mesaj"].startswith("[E-POSTASIZ ONAY] K1")


def test_smtp_yokken_yonetici_vazgecerse_onay_yok(ortam):
    uyg, o = ortam
    uyg.oturum = dict(YONETICI)
    uyg.ayarlar["smtp"] = {}
    o["cevap"] = False
    ekle(uyg, o)
    assert not onay.onayli_mi(uyg.ayarlar["kameralar"][0])


def test_smtp_yokken_kullanici_onay_veremez(ortam):
    uyg, o = ortam
    uyg.ayarlar["smtp"] = {}
    ekle(uyg, o)
    uyg._onay_mailini_tekrar_gonder()
    assert o["sorulan"] == []                                          # e-postasız onay sorulmaz bile
    assert not onay.onayli_mi(uyg.ayarlar["kameralar"][0])
    assert o["mesajlar"][-1][0] == "showwarning" and "yönetici" in o["mesajlar"][-1][2]


# ---------- Bağlantı testi ----------

def test_onaysiz_kamerada_baglanti_testi_yapilmaz(ortam):
    uyg, o = ortam
    ekle(uyg, o)
    uyg._baglanti_test()
    assert o["kamera"].cekim == 0
    assert "Önce onay kodu girilmeli" in o["mesajlar"][-1][2]


def test_onayli_kamerada_baglanti_testi_yapilir(ortam):
    uyg, o = ortam
    # Kamerayı listede görebilmek için sahibi oturumdaki kullanıcı olmalı
    uyg.ayarlar["kameralar"] = [sahiplik.sahiplendir(
        onay.onay_ver(dict(KAMERA), "sahip@ornek.com"), KULLANICI["eposta"])]
    uyg._listeyi_doldur()
    uyg.liste.selection_set("K1")
    uyg._baglanti_test()
    uyg.update()
    assert o["kamera"].cekim == 1


# ---------- Kod hiçbir yerde görünmez ----------

def test_onay_kodu_log_olay_ve_mesajlarda_yok(ortam):
    uyg, o = ortam
    KAYITCI.mesajlar.clear()
    ekle(uyg, o)
    uyg._onay_mailini_tekrar_gonder()
    kodlar = [mailden_kod(m) for m in o["mailler"]]
    o["kod"] = kodlar[-1]
    uyg._onay_kodu_gir()
    yazilar = [m[2] for m in o["mesajlar"]] + o["sorulan"] + KAYITCI.mesajlar + \
              [x["mesaj"] for x in olaylar()]
    assert all(kod not in y for kod in kodlar for y in yazilar)
    with baglan() as db:
        assert all(kod not in str(tuple(s)) for kod in kodlar
                   for s in db.execute("SELECT * FROM kamera_onay_kodlari"))


# ---------- Kod penceresi kendiliğinden açılır ----------

def test_mail_gidince_kod_penceresi_kendiliginden_acilir(ortam):
    """Kullanıcı 'Onay kodunu gir' düğmesini aramak zorunda kalmaz."""
    uyg, o = ortam
    uyg.update()                 # önceki testlerden kalan işler bitsin
    o["kod_soruldu"] = 0
    ekle(uyg, o)
    assert o["kod_soruldu"] == 1


def test_mail_gidemezse_kod_penceresi_acilmaz(ortam):
    uyg, o = ortam
    uyg.update()
    o["kod_soruldu"] = 0
    o["mail_hatasi"] = OSError("baglanti yok")
    ekle(uyg, o)
    assert o["kod_soruldu"] == 0


def test_kod_penceresi_dogru_kodda_onaylar(ortam):
    """Pencere açılır açılmaz doğru kod girilirse kamera onaylanır."""
    uyg, o = ortam
    o["form"] = dict(KAMERA)
    # Kod maili gönderilirken doğru kodu bilmek için önce mail gider, sonra pencere açılır
    uyg._ekle()
    uyg.update()
    assert not onay.onayli_mi(uyg.ayarlar["kameralar"][0])
    o["kod"] = mailden_kod(o["mailler"][0])
    uyg.liste.selection_set(KAMERA["kod"])
    uyg._onay_kodu_gir()
    assert onay.onayli_mi(uyg.ayarlar["kameralar"][0])


# ---------- Onay düğmelerinin görünürlüğü ----------

def gorunen_onay_dugmeleri(uyg) -> list[str]:
    return [d.cget("text") for d in uyg.onay_dugmeleri if d.winfo_manager()]


def test_secim_yokken_onay_dugmeleri_gizli(ortam):
    uyg, o = ortam
    uyg.liste.selection_remove(*uyg.liste.selection())
    uyg._onay_dugmelerini_guncelle()
    assert gorunen_onay_dugmeleri(uyg) == []


def test_onay_bekleyen_kamerada_dugmeler_gorunur(ortam):
    uyg, o = ortam
    ekle(uyg, o)                                   # onaysız eklenir
    uyg._onay_dugmelerini_guncelle()
    assert gorunen_onay_dugmeleri(uyg) == ["Onay kodunu gir", "Onay mailini tekrar gönder"]


def test_onayli_kamerada_dugmeler_gizlenir(ortam):
    uyg, o = ortam
    ekle(uyg, o)
    o["kod"] = mailden_kod(o["mailler"][0])
    uyg._onay_kodu_gir()
    assert onay.onayli_mi(uyg.ayarlar["kameralar"][0])
    uyg.liste.selection_set(KAMERA["kod"])
    uyg._onay_dugmelerini_guncelle()
    assert gorunen_onay_dugmeleri(uyg) == []


# ---------- Kamera görünürlüğü ve yetki ----------

def test_baskasinin_kamerasi_listede_gorunmez(ortam):
    uyg, o = ortam
    uyg.ayarlar["kameralar"] = [sahiplik.sahiplendir(dict(KAMERA), "baska@akgun.com.tr")]
    uyg._listeyi_doldur()
    assert uyg.liste.get_children() == ()


def test_kendi_kamerasi_listede_gorunur(ortam):
    uyg, o = ortam
    uyg.ayarlar["kameralar"] = [sahiplik.sahiplendir(dict(KAMERA), KULLANICI["eposta"])]
    uyg._listeyi_doldur()
    assert uyg.liste.get_children() == (KAMERA["kod"],)


def test_baskasinin_kamerasinda_islem_reddedilir(ortam):
    """Liste eski kalmış olsa bile düzenle/sil yetki kontrolünden geçer."""
    uyg, o = ortam
    uyg.ayarlar["kameralar"] = [sahiplik.sahiplendir(dict(KAMERA), "baska@akgun.com.tr")]
    uyg._listeyi_doldur()
    uyg.liste.insert("", "end", iid=KAMERA["kod"], values=())      # bayat satır
    uyg.liste.selection_set(KAMERA["kod"])
    assert uyg._secili_kamera() is None
    assert o["mesajlar"][-1][0] == "showwarning" and "Yetki yok" in o["mesajlar"][-1][1]


def test_yonetici_baskasinin_kamerasini_gorur(ortam):
    uyg, o = ortam
    uyg.oturum = dict(YONETICI)
    try:
        uyg.ayarlar["kameralar"] = [sahiplik.sahiplendir(dict(KAMERA), "baska@akgun.com.tr")]
        uyg._listeyi_doldur()
        assert uyg.liste.get_children() == (KAMERA["kod"],)
        uyg.liste.selection_set(KAMERA["kod"])
        assert uyg._secili_kamera() == 0
    finally:
        uyg.oturum = dict(KULLANICI)


def test_eklenen_kameranin_sahibi_ekleyen_kullanicidir(ortam):
    uyg, o = ortam
    ekle(uyg, o)
    assert sahiplik.sahibi(uyg.ayarlar["kameralar"][0]) == KULLANICI["eposta"]
