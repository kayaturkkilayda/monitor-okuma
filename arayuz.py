"""Ayar ve izleme arayüzü. Motordan (main.py) bağımsız çalışır."""
import json
import os
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

import cv2
from PIL import Image

KOK = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
os.chdir(KOK)
sys.path.insert(0, str(KOK / "src"))
from ayarlar import ayarlari_oku, ayarlari_yaz, kameralari_olustur
from arka_plan import arka_planda
from ayar_sekmesi import AyarSekmesi
import kamera_onay
from bildirim import gecersiz_adresler, gonder, smtp_hazir_mi
from kod_girisi import KodPenceresi
from kullanicilar import KullaniciHatasi
from durum import gorunen_durum
from giris_ekrani import GirisEkrani
from kayitlar_sekmesi import KayitlarSekmesi
from kullanicilar_sekmesi import KullanicilarSekmesi
from log import log_kur
import oturum as oturum_deposu
from loglar_sekmesi import LoglarSekmesi
from onay import gorunen_adres, onay_ver, onayi_aktar, onayli_mi
import sahiplik
from onizleme import onizleme_ac
from veritabani import olay
from zaman import ekran_zamani

DURUM_DOSYASI = Path("durum.json")
YENILEME_MS = 5000

DURUM_YAZISI = {"calisiyor": "Çalışıyor", "arizali": "Arızalı", "yanit_yok": "Yanıt yok",
                "onay_bekliyor": "Onay bekliyor", "pasif": "Pasif", "bilinmiyor": "Bilinmiyor"}


def durumlari_oku() -> dict:
    try:
        return json.loads(DURUM_DOSYASI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# Kameranın kullanıcı adı/şifre istediğini gösteren HTTP kodları
KIMLIK_KODLARI = {401: "Kamera kullanıcı adı veya şifre istiyor.",
                  403: "Kamera bu kullanıcı adı ve şifreye izin vermiyor."}
TEST_VARSAYILAN = "Adres, kullanıcı adı ve şifreyi kontrol edin."
KIMLIK_ONERISI = "Kamerayı düzenleyip 'Kamera girişi' bölümünü doldurun."


def baglanti_hata_mesaji(kamera_kodu: str, hata: str | None, durum_kodu: int | None) -> str:
    """Bağlantı testi başarısız olunca gösterilecek metin.

    Kamera kimlik istiyorsa (401/403) teknik hata yerine ne yapılacağı yazılır.
    """
    if durum_kodu in KIMLIK_KODLARI:
        neden = KIMLIK_KODLARI[durum_kodu] + " " + KIMLIK_ONERISI
    else:
        neden = hata or TEST_VARSAYILAN
    return f"{kamera_kodu} kamerasından görüntü alınamadı." + "\n\n" + neden


class IpuculuGiris(ttk.Entry):
    """Boşken soluk bir ipucu gösteren giriş kutusu.

    İpucu metni ayar dosyasına yazılmaz: kutu boş bırakılırsa deger() boş metin döndürür.
    Şifre alanında ipucu yıldızlanmasın diye gösterilirken maskeleme kapatılır.
    """

    IPUCU_RENGI = "#9aa4b1"

    def __init__(self, ust, degisken: tk.StringVar, ipucu: str, gizli: bool = False, **k):
        super().__init__(ust, textvariable=degisken, **k)
        self.degisken = degisken
        self.ipucu = ipucu
        self.gizli = gizli
        self._ipucu_acik = False
        self._normal_renk = self.cget("foreground")
        self.bind("<FocusIn>", self._odak_geldi)
        self.bind("<FocusOut>", self._odak_gitti)
        self._ipucu_goster()

    def deger(self) -> str:
        """Kullanıcının gerçekten yazdığı metin; ipucu görünüyorsa boş."""
        return "" if self._ipucu_acik else self.degisken.get()

    def _ipucu_goster(self):
        if self.degisken.get():
            return
        self._ipucu_acik = True
        self.degisken.set(self.ipucu)
        self.config(foreground=self.IPUCU_RENGI, show="")

    def _odak_geldi(self, olay=None):
        if self._ipucu_acik:
            self._ipucu_acik = False
            self.degisken.set("")
            self.config(foreground=self._normal_renk, show="*" if self.gizli else "")

    def _odak_gitti(self, olay=None):
        self._ipucu_goster()


class KameraFormu(tk.Toplevel):
    """Kamera ekleme ve düzenleme penceresi.

    diger_kameralar: düzenlenen kamera hariç {kod: yatak} sözlüğü (çakışma kontrolü için)

    Bildirim e-postası ve onaylayacak kişinin e-postası burada sorulmaz:
    bildirimler Ayarlar'daki varsayılan adrese, onay kodu ise giriş yapan kullanıcıya gider.
    """

    ALANLAR = [("kod", "Kamera kodu"), ("yatak", "Yatak kodu"), ("adres", "Adres"),
               ("kullanici", "Kullanıcı adı"), ("sifre", "Şifre")]

    BILGI_ALANLARI = ("kod", "yatak", "adres")
    GIRIS_ALANLARI = ("kullanici", "sifre")
    IPUCU = "İsteğe bağlı"

    ACIKLAMA = {
        "kod": "Bu kameraya verdiğiniz kısa ad. Örnek: K1",
        "yatak": "Kameranın baktığı yatak. Örnek: Y1",
        "kullanici": ("Kameranın kendi giriş adı. Sizin hesabınız değildir. "
                      "Kamera şifre istemiyorsa boş bırakın."),
        "sifre": "Kameranın kendi şifresi. Şifreli saklanır.",
    }
    # Adres alanının anlamı kamera tipine göre değişir
    ADRES_ACIKLAMA = {
        "ip": "Kameranın anlık görüntü adresi. Örnek: http://192.168.1.20/shot.jpg",
        "webcam": "Bilgisayara takılı kameranın numarası. Genelde 0.",
    }
    ACIKLAMA_RENGI = "#5f6b7a"

    def __init__(self, ust, diger_kameralar: dict, kamera: dict | None = None):
        super().__init__(ust)
        self.title("Kamera düzenle" if kamera else "Kamera ekle")
        self.resizable(False, False)
        self.transient(ust)
        self.grab_set()

        self.sonuc = None
        self.diger = diger_kameralar
        k = kamera or {"tip": "ip", "aktif": True}

        govde = ttk.Frame(self, padding=15)
        govde.pack(fill="both", expand=True)

        self.degerler, self.girisler = {}, {}

        bilgi = ttk.LabelFrame(govde, text="Kamera bilgileri", padding=10)
        bilgi.pack(fill="x")
        ttk.Label(bilgi, text="Tip").grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.tip = tk.StringVar(value=k.get("tip", "ip"))
        ttk.Combobox(bilgi, textvariable=self.tip, values=["ip", "webcam"],
                     state="readonly", width=38).grid(row=1, column=0, sticky="we")
        self._alanlari_ekle(bilgi, self.BILGI_ALANLARI, k, baslangic=2)

        giris = ttk.LabelFrame(govde, text="Kamera girişi (isteğe bağlı)", padding=10)
        giris.pack(fill="x", pady=(12, 0))
        self._alanlari_ekle(giris, self.GIRIS_ALANLARI, k, baslangic=0)

        self.aktif = tk.BooleanVar(value=k.get("aktif", True))
        ttk.Checkbutton(govde, text="Aktif", variable=self.aktif).pack(anchor="w", pady=(12, 0))

        dugmeler = ttk.Frame(govde)
        dugmeler.pack(pady=(12, 0))
        ttk.Button(dugmeler, text="Kaydet", command=self._kaydet).pack(side="left", padx=5)
        ttk.Button(dugmeler, text="İptal", command=self.destroy).pack(side="left", padx=5)

        self.tip.trace_add("write", lambda *a: self._adres_aciklamasini_guncelle())
        self._adres_aciklamasini_guncelle()

    def _alanlari_ekle(self, ust, adlar, k: dict, baslangic: int):
        """Her alan için: etiket, kutu ve altında küçük gri açıklama."""
        satir = baslangic
        for ad in adlar:
            etiket = next(e for a, e in self.ALANLAR if a == ad)
            ttk.Label(ust, text=etiket).grid(row=satir, column=0, sticky="w", pady=(10, 2))
            satir += 1
            deger = tk.StringVar(value=str(k.get(ad, "")))
            if ad in self.GIRIS_ALANLARI:
                kutu = IpuculuGiris(ust, deger, self.IPUCU, gizli=(ad == "sifre"), width=40)
            else:
                kutu = ttk.Entry(ust, textvariable=deger, width=40)
            kutu.grid(row=satir, column=0, sticky="we")
            satir += 1
            aciklama = ttk.Label(ust, text=self.ACIKLAMA.get(ad, ""), foreground=self.ACIKLAMA_RENGI,
                                 font=("Segoe UI", 8), wraplength=300, justify="left")
            aciklama.grid(row=satir, column=0, sticky="w", pady=(2, 0))
            satir += 1
            if ad == "adres":
                self.adres_aciklamasi = aciklama
            self.degerler[ad], self.girisler[ad] = deger, kutu

    def _adres_aciklamasini_guncelle(self):
        self.adres_aciklamasi.config(text=self.ADRES_ACIKLAMA.get(self.tip.get(), ""))

    def _degerleri_al(self) -> dict:
        """Formdaki değerler; ipucu görünen kutular boş sayılır."""
        return {ad: (kutu.deger() if isinstance(kutu, IpuculuGiris) else self.degerler[ad].get()).strip()
                for ad, kutu in self.girisler.items()}

    def _dogrula(self, d: dict, tip: str) -> str | None:
        if not d["kod"]:
            return "Kamera kodu boş olamaz."
        if not d["yatak"]:
            return "Yatak kodu boş olamaz."
        if d["kod"] in self.diger:
            return f"{d['kod']} kodlu bir kamera zaten var."
        for kod, yatak in self.diger.items():
            if yatak == d["yatak"]:
                return f"{d['yatak']} yatağına zaten {kod} kamerası bağlı."
        if tip == "ip" and not d["adres"].startswith(("http://", "https://")):
            return "IP kamera adresi http:// veya https:// ile başlamalı."
        if tip == "webcam" and not d["adres"].isdigit():
            return "Webcam için adres bir sayı olmalı (genelde 0)."
        return None

    def _kaydet(self):
        d = self._degerleri_al()
        tip = self.tip.get()
        hata = self._dogrula(d, tip)
        if hata:
            messagebox.showerror("Hatalı giriş", hata, parent=self)
            return
        self.sonuc = {
            "kod": d["kod"], "yatak": d["yatak"], "tip": tip,
            "adres": int(d["adres"]) if tip == "webcam" else d["adres"],
            "kullanici": d["kullanici"], "sifre": d["sifre"],
            "aktif": self.aktif.get(),
        }
        self.destroy()

class Uygulama(tk.Tk):
    def __init__(self, oturum: dict, log):
        """oturum: giriş yapan kullanıcı (eposta, ad, yonetici)."""
        super().__init__()
        self.title("Monitör Görüntü Aktarımı")
        self.geometry("1100x600")
        self.oturum = oturum
        self.log = log
        self.cikis_yapildi = False
        self.ayarlar = ayarlari_oku()

        ust = ttk.Frame(self, padding=(10, 8, 10, 0))
        ust.pack(fill="x")
        ttk.Button(ust, text="Çıkış", command=self._cikis).pack(side="right")
        rol = " · Yönetici" if oturum.get("yonetici") else ""
        ttk.Label(ust, text=f"{oturum['ad']} ({oturum['eposta']}){rol}").pack(side="right", padx=10)

        sekmeler = ttk.Notebook(self)
        sekmeler.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        self.kamera_sekmesi = ttk.Frame(sekmeler, padding=10)
        sekmeler.add(self.kamera_sekmesi, text="Kameralar")
        self._kamera_listesi_kur()
        self._dugmeleri_kur()

        self.kayitlar_sekmesi = KayitlarSekmesi(
            sekmeler, sahiplik.gorunen_kodlar(self.ayarlar["kameralar"], oturum))
        sekmeler.add(self.kayitlar_sekmesi, text="Kayıtlar")

        self.loglar_sekmesi = LoglarSekmesi(sekmeler)
        sekmeler.add(self.loglar_sekmesi, text="Loglar")

        # Ayarlar ve Kullanıcılar yalnızca yöneticide: SMTP, M4/API anahtarı ve izin verilen
        # alan adları normal kullanıcıya hiç gösterilmez. Sekme gizlemek tek başına yeterli
        # değil; AyarSekmesi kaydetmeyi ayrıca yönetici olmayana kapatır.
        if oturum.get("yonetici"):
            self.ayar_sekmesi = AyarSekmesi(sekmeler, self.ayarlar, oturum, log)
            sekmeler.add(self.ayar_sekmesi, text="Ayarlar")

            self.kullanicilar_sekmesi = KullanicilarSekmesi(sekmeler, oturum, log)
            sekmeler.add(self.kullanicilar_sekmesi, text="Kullanıcılar")

        self._periyodik_yenile()

    # ---------- Liste ----------

    def _kamera_listesi_kur(self):
        kolonlar = {"kod": ("Kamera", 70), "yatak": ("Yatak", 100),
                    "tip": ("Tip", 70), "adres": ("Adres", 300),
                    "durum": ("Durum", 210), "son": ("Son görüntü", 140)}
        self.liste = ttk.Treeview(self.kamera_sekmesi, columns=list(kolonlar),
                                  show="headings", height=15)
        for ad, (baslik, genislik) in kolonlar.items():
            self.liste.heading(ad, text=baslik)
            self.liste.column(ad, width=genislik)

        self.liste.tag_configure("calisiyor", background="#d4edda")
        self.liste.tag_configure("arizali", background="#f8d7da")
        self.liste.tag_configure("yanit_yok", background="#fff3cd")
        self.liste.tag_configure("onay_bekliyor", background="#ffd8a8")    # turuncu
        self.liste.tag_configure("pasif", foreground="#999999")
        self.liste.pack(fill="both", expand=True)
        self.liste.bind("<Double-1>", lambda e: self._duzenle())
        self.liste.bind("<<TreeviewSelect>>", self._onay_dugmelerini_guncelle)

    def _listeyi_doldur(self):
        durumlar = durumlari_oku()
        tesis = self.ayarlar["tesis_kodu"]
        aralik = self.ayarlar["gonderim_araligi_sn"]
        simdi = datetime.now()
        secili = self.liste.selection()

        self.liste.delete(*self.liste.get_children())
        for k in sahiplik.gorunen_kameralar(self.ayarlar["kameralar"], self.oturum):
            d = durumlar.get(f"{tesis}/{k['kod']}/{k['yatak']}", {})
            durum = gorunen_durum(d, k.get("aktif", True), aralik, simdi, onayli=onayli_mi(k))
            yazi = DURUM_YAZISI.get(durum, durum)
            if durum == "onay_bekliyor" and kamera_onay.bekleyen_kod(k):
                yazi = "Onay bekliyor (mail gönderildi)"
            son = ekran_zamani(d.get("son_basari"))
            self.liste.insert("", "end", iid=k["kod"], tags=(durum,), values=(
                k["kod"], k["yatak"], k["tip"], gorunen_adres(k["adres"]), yazi, son))

        self.liste.selection_set([s for s in secili if self.liste.exists(s)])
        self._onay_dugmelerini_guncelle()

    def _periyodik_yenile(self):
        self._listeyi_doldur()
        self._zamanlayici = self.after(YENILEME_MS, self._periyodik_yenile)

    def destroy(self):
        # Çıkışta pencere kapanırken bekleyen yenileme iptal edilir; yoksa kapanmış pencereyi yenilemeye çalışır
        self.after_cancel(self._zamanlayici)
        super().destroy()

    # ---------- Düğmeler ----------

    def _dugmeleri_kur(self):
        cerceve = ttk.Frame(self.kamera_sekmesi)
        cerceve.pack(fill="x", pady=(10, 0))
        ttk.Button(cerceve, text="Ekle", command=self._ekle).pack(side="left", padx=(0, 5))
        ttk.Button(cerceve, text="Düzenle", command=self._duzenle).pack(side="left", padx=5)
        ttk.Button(cerceve, text="Sil", command=self._sil).pack(side="left", padx=5)
        self.test_dugmesi = ttk.Button(cerceve, text="Bağlantıyı test et",
                                       command=self._baglanti_test)
        self.test_dugmesi.pack(side="left", padx=5)
        # Bu iki düğme yalnızca seçili kamera onay bekliyorken görünür
        self.onay_dugmeleri = [
            ttk.Button(cerceve, text="Onay kodunu gir", command=self._onay_kodu_gir),
            ttk.Button(cerceve, text="Onay mailini tekrar gönder",
                       command=self._onay_mailini_tekrar_gonder),
        ]
        self._onay_dugmelerini_guncelle()

    def secili_kamera_kaydi(self) -> dict | None:
        """Seçili kamera; seçim yoksa None. Uyarı göstermez."""
        secili = self.liste.selection()
        if not secili:
            return None
        return next((k for k in self.ayarlar["kameralar"] if k["kod"] == secili[0]), None)

    def _onay_dugmelerini_guncelle(self, olay=None):
        """Onaylı kamerada ve seçim yokken onay düğmeleri gizlenir."""
        k = self.secili_kamera_kaydi()
        goster = k is not None and not onayli_mi(k)
        for dugme in self.onay_dugmeleri:
            if goster:
                dugme.pack(side="left", padx=5)
            else:
                dugme.pack_forget()

    def _diger_kameralar(self, haric: str | None = None) -> dict:
        return {k["kod"]: k["yatak"] for k in self.ayarlar["kameralar"] if k["kod"] != haric}

    def _secili_kamera(self) -> int | None:
        """Seçili kameranın sırası. Düzenle, sil, test ve onay hep buradan geçer.

        Yetki kontrolü burada yapılır: listede gizlemek tek başına yeterli değildir.
        """
        secili = self.liste.selection()
        if not secili:
            messagebox.showinfo("Seçim yok", "Önce listeden bir kamera seçin.")
            return None
        sira = next((i for i, k in enumerate(self.ayarlar["kameralar"])
                     if k["kod"] == secili[0]), None)
        if sira is None:
            return None
        if not sahiplik.gorebilir_mi(self.ayarlar["kameralar"][sira], self.oturum):
            messagebox.showwarning("Yetki yok", "Bu kamerayı yalnızca ekleyen kullanıcı ya da "
                                                "bir yönetici görebilir ve değiştirebilir.")
            return None
        return sira

    # ---------- Onay ----------

    def _sira(self, kamera_kodu: str) -> int:
        return next(i for i, k in enumerate(self.ayarlar["kameralar"]) if k["kod"] == kamera_kodu)

    def _zaten_onayli(self, k: dict) -> bool:
        if onayli_mi(k):
            messagebox.showinfo("Zaten onaylı", f"{k['kod']} kamerası {ekran_zamani(k['onay_zamani'])} "
                                                f"tarihinde {k['onaylayan']} tarafından onaylandı.")
            return True
        return False

    def _onay_baslat(self, k: dict):
        """Giriş yapan kullanıcıya kodlu mail gönderir.

        Onayı kamerayı ekleyen kişi verir; ayrıca bir adres sorulmaz. SMTP yoksa
        yalnızca yönetici e-postasız onay verebilir.
        """
        smtp = self.ayarlar.get("smtp")
        if not smtp_hazir_mi(smtp):
            self._epostasiz_onay(k)
            return
        onay_eposta = self.oturum["eposta"]
        kod = kamera_onay.kod_olustur(k, onay_eposta, self.oturum["eposta"])
        konu, metin = kamera_onay.onay_maili(self.ayarlar.get("tesis_kodu", ""), k, self.oturum["eposta"], kod)
        del kod                                       # kod artık yalnızca mail metninde

        def gonderim():
            try:
                gonder(smtp, [onay_eposta], konu, metin)
                return None
            except Exception as e:
                return type(e).__name__

        arka_planda(self, gonderim, lambda hata: self._onay_maili_sonucu(k, hata, onay_eposta))

    def _onay_maili_sonucu(self, k: dict, hata: str | None, onay_eposta: str):
        if hata:
            kamera_onay.kodu_sil(k["kod"])            # gitmeyen kod geçerli kalmasın
            olay(self.log, "WARNING", k["kod"],
                 f"{k['kod']} onay maili gönderilemedi ({hata}) — {self.oturum['eposta']}")
            messagebox.showerror("Onay maili gönderilemedi",
                                 f"{k['kod']} için onay maili gönderilemedi ({hata}).\n\n"
                                 "E-posta ayarlarını kontrol edip 'Onay mailini tekrar gönder' ile deneyin.")
        else:
            olay(self.log, "INFO", k["kod"],
                 f"{k['kod']} onay maili gönderildi: {onay_eposta}")
            messagebox.showinfo("Onay maili gönderildi",
                                f"{k['kod']} için onay kodu {onay_eposta} adresine gönderildi.\n\n"
                                "Kod gelince aşağıdaki kutulara girin. Onaylanana kadar kameradan "
                                "görüntü alınmaz.")
            self._listeyi_doldur()
            # Kullanıcı düğme aramasın: kod penceresi kendiliğinden açılır
            self._onay_kodu_gir(k)
            return
        self._listeyi_doldur()

    def _epostasiz_onay(self, k: dict):
        if not self.oturum.get("yonetici"):
            messagebox.showwarning("E-posta ayarlanmamış",
                                   "E-posta ayarları yapılmadığı için onay maili gönderilemiyor.\n\n"
                                   f"{k['kod']} kamerası, bir yönetici onaylayana kadar kullanılmayacak.")
            return
        if not messagebox.askyesno(
                "E-postasız onay",
                "E-posta ayarları yapılmadığı için onay maili gönderilemiyor.\n\n"
                f"{k['kod']} → {k['yatak']} ({gorunen_adres(k['adres'])}) kamerası için yönetici olarak "
                "E-POSTASIZ ONAY vermek istiyor musunuz?\n\n"
                "Bu onay olaylara ayrıca işaretlenerek yazılır.", icon="warning", parent=self):
            return
        onayli = onay_ver(k, self.oturum["eposta"])
        self.ayarlar["kameralar"][self._sira(k["kod"])] = onayli
        ayarlari_yaz(self.ayarlar)
        olay(self.log, "WARNING", k["kod"],
             f"[E-POSTASIZ ONAY] {k['kod']} kullanımı e-posta kodu olmadan onaylandı — {self.oturum['eposta']}")
        self._listeyi_doldur()

    def _onay_kodu_gir(self, kamera: dict | None = None):
        """Altı kutulu kod penceresini açar.

        kamera verilirse (mail gönderildikten hemen sonra) listeden seçim beklenmez.
        """
        if kamera is None:
            sira = self._secili_kamera()
            if sira is None:
                return
            kamera = self.ayarlar["kameralar"][sira]
        if self._zaten_onayli(kamera):
            return
        if not kamera_onay.bekleyen_kod(kamera):
            messagebox.showinfo("Kod yok", f"{kamera['kod']} için gönderilmiş geçerli bir onay "
                                           "kodu yok." + chr(10) + chr(10) +
                                           "'Onay mailini tekrar gönder' ile yeni kod gönderin.")
            return

        pencere = KodPenceresi(
            self, "Onay kodu",
            f"{kamera['kod']} → {kamera['yatak']} için e-postanıza gelen 6 haneli onay kodunu girin.",
            lambda kod: kamera_onay.kodu_dogrula(kamera, kod), KullaniciHatasi)
        self.wait_window(pencere)
        if pencere.sonuc is None:
            self._listeyi_doldur()                 # deneme hakkı azalmış olabilir
            return
        self._onayi_isle(kamera, pencere.sonuc)

    def _onayi_isle(self, kamera: dict, onaylayan: str):
        sira = self._sira(kamera["kod"])
        self.ayarlar["kameralar"][sira] = onay_ver(kamera, onaylayan)
        ayarlari_yaz(self.ayarlar)
        olay(self.log, "INFO", kamera["kod"],
             f"{kamera['kod']} kullanımı onaylandı (onaylayan: {onaylayan}, "
             f"kodu giren: {self.oturum['eposta']})")
        self._listeyi_doldur()
        messagebox.showinfo("Onaylandı",
                            f"{kamera['kod']} kamerası {onaylayan} onayıyla kullanıma açıldı." +
                            chr(10) + chr(10) +
                            "Motor çalışıyorsa birkaç saniye içinde çekime başlar.")

    def _onay_mailini_tekrar_gonder(self):
        sira = self._secili_kamera()
        if sira is None:
            return
        k = self.ayarlar["kameralar"][sira]
        if self._zaten_onayli(k):
            return
        self._onay_baslat(k)                          # yeni kod üretilir, eskisi geçersiz olur

    # ---------- Ekle / düzenle / sil ----------

    def _ekle(self):
        form = KameraFormu(self, self._diger_kameralar())
        self.wait_window(form)
        if form.sonuc:
            # Onaysız eklenir; onay e-posta koduyla gelir. Ekleyen kullanıcı sahibidir.
            k = sahiplik.sahiplendir(form.sonuc, self.oturum["eposta"])
            self.ayarlar["kameralar"].append(k)
            self._kaydet_ve_bildir(f"{k['kod']} eklendi", k["kod"], bilgi=False)
            self._onay_baslat(k)

    def _duzenle(self):
        sira = self._secili_kamera()
        if sira is None:
            return
        eski = self.ayarlar["kameralar"][sira]
        form = KameraFormu(self, self._diger_kameralar(haric=eski["kod"]), eski)
        self.wait_window(form)
        if form.sonuc:
            k = onayi_aktar(eski, form.sonuc)         # adres ya da tip değiştiyse onay düşer
            k = sahiplik.sahiplendir(k, sahiplik.sahibi(eski) or self.oturum["eposta"])
            if k["kod"] != eski["kod"]:
                kamera_onay.kodu_sil(eski["kod"])
            self.ayarlar["kameralar"][sira] = k
            mail = kamera_onay.onay_maili_gerekli_mi(eski, k)
            self._kaydet_ve_bildir(f"{k['kod']} güncellendi", k["kod"], bilgi=not mail)
            if mail:
                # Başka bir cihaz olabilir: onay yeniden, e-posta koduyla istenir
                self._onay_baslat(k)

    def _sil(self):
        sira = self._secili_kamera()
        if sira is None:
            return
        k = self.ayarlar["kameralar"][sira]
        if not messagebox.askyesno("Kamerayı sil",
                                   f"{k['kod']} → {k['yatak']} silinsin mi?"):
            return
        del self.ayarlar["kameralar"][sira]
        kamera_onay.kodu_sil(k["kod"])
        self._kaydet_ve_bildir(f"{k['kod']} silindi", k["kod"])

    def _kaydet_ve_bildir(self, mesaj: str, kamera_kodu: str, bilgi: bool = True):
        ayarlari_yaz(self.ayarlar)
        olay(self.log, "INFO", kamera_kodu, f"{mesaj} — {self.oturum['eposta']}")
        self._listeyi_doldur()
        if bilgi:
            messagebox.showinfo("Kaydedildi",
                                f"{mesaj}.\n\nMotor çalışıyorsa birkaç saniye içinde geçerli olur.")
    # ---------- Bağlantı testi ----------

    def _baglanti_test(self):
        sira = self._secili_kamera()
        if sira is None:
            return
        k = self.ayarlar["kameralar"][sira]
        if not onayli_mi(k):
            # Onaysız kameradan test görüntüsü bile alınmaz
            messagebox.showwarning("Onay gerekli", f"{k['kod']} kamerası henüz onaylanmadı.\n\n"
                                   "Önce onay kodu girilmeli ('Onay kodunu gir').", parent=self)
            return
        # Pasif kamerayı da test edebilmek için geçici olarak aktif sayıyoruz
        kamera = kameralari_olustur({"kameralar": [{**k, "aktif": True}]})[0]
        self.test_dugmesi.config(state="disabled", text="Test ediliyor...")

        def cekim():
            try:
                kare, *_ = kamera.cift_cekim(aralik_sn=0)
                return kare, None, getattr(kamera, "son_durum_kodu", None)
            except Exception as e:
                return None, str(e), None

        arka_planda(self, cekim,
                    lambda sonuc: self._test_sonucu(k, *(sonuc or (None, None, None))))

    def _test_sonucu(self, k: dict, kare, hata: str | None, durum_kodu: int | None = None):
        self.test_dugmesi.config(state="normal", text="Bağlantıyı test et")
        if kare is None:
            messagebox.showerror("Bağlantı başarısız",
                                 baglanti_hata_mesaji(k["kod"], hata, durum_kodu), parent=self)
            return

        goruntu = Image.fromarray(cv2.cvtColor(kare, cv2.COLOR_BGR2RGB))
        onizleme_ac(self, goruntu, f"{k['kod']} → {k['yatak']}")


    # ---------- Oturum ----------

    def _cikis(self):
        oturum_deposu.unut()                  # "Beni hatırla" ile açık kalan oturum da kapanır
        olay(self.log, "INFO", "sistem", f"Kullanıcı çıkış yaptı: {self.oturum['eposta']}")
        self.cikis_yapildi = True
        self.destroy()


def ayarlari_guvenli_oku() -> dict:
    try:
        return ayarlari_oku()
    except Exception:
        return {}


def giris_penceresi(log) -> dict | None:
    """Giriş penceresini açar; giriş yapan kullanıcıyı ya da (pencere kapatılırsa) None döndürür."""
    pencere = tk.Tk()
    pencere.title("Monitör Görüntü Aktarımı — Giriş")
    pencere.resizable(False, False)
    sonuc = {}

    def girildi(kullanici):
        sonuc["kullanici"] = kullanici
        pencere.destroy()

    GirisEkrani(pencere, ayarlari_guvenli_oku, girildi, log).pack(fill="both", expand=True)
    pencere.mainloop()
    return sonuc.get("kullanici")


def calistir():
    log = log_kur(ad="arayuz", dosya_adi="arayuz.log")
    try:                             # "Beni hatırla": bu cihazda açık kalan oturum varsa doğrudan aç
        oturum = oturum_deposu.hatirlanan_kullanici()
    except Exception:
        oturum = None
    if oturum:
        olay(log, "INFO", "sistem", f"Kullanıcı giriş yaptı (hatırlanan oturum): {oturum['eposta']}")
    while True:                      # "Çıkış" yapılınca tekrar giriş penceresi açılır
        oturum = oturum or giris_penceresi(log)
        if oturum is None:
            return
        uygulama = Uygulama(oturum, log)
        uygulama.mainloop()
        if not uygulama.cikis_yapildi:
            return
        oturum = None


if __name__ == "__main__":
    calistir()