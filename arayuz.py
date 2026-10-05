"""Ayar ve izleme arayüzü. Motordan (main.py) bağımsız çalışır."""
import json
import os
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

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
from kullanicilar import KullaniciHatasi
from durum import gorunen_durum
from giris_ekrani import GirisEkrani
from kayitlar_sekmesi import KayitlarSekmesi
from kullanicilar_sekmesi import KullanicilarSekmesi
from log import log_kur
import oturum as oturum_deposu
from loglar_sekmesi import LoglarSekmesi
from onay import gorunen_adres, onay_ver, onayi_aktar, onayli_mi
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


class KameraFormu(tk.Toplevel):
    """Kamera ekleme ve düzenleme penceresi.

    diger_kameralar: düzenlenen kamera hariç {kod: yatak} sözlüğü (çakışma kontrolü için)
    """

    ALANLAR = [("kod", "Kamera kodu"), ("yatak", "Yatak kodu"), ("adres", "Adres"),
               ("kullanici", "Kullanıcı adı"), ("sifre", "Şifre"),
               ("bildirim_eposta", "Bildirim e-postası\n(virgülle; boşsa varsayılan)"),
               ("onay_eposta", "Onaylayacak kişinin\ne-postası (zorunlu)")]

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

        ttk.Label(govde, text="Tip").grid(row=0, column=0, sticky="w", pady=4)
        self.tip = tk.StringVar(value=k.get("tip", "ip"))
        ttk.Combobox(govde, textvariable=self.tip, values=["ip", "webcam"],
                     state="readonly", width=37).grid(row=0, column=1, pady=4)

        self.degerler = {}
        for i, (ad, etiket) in enumerate(self.ALANLAR, start=1):
            ttk.Label(govde, text=etiket).grid(row=i, column=0, sticky="w", pady=4, padx=(0, 10))
            deger = tk.StringVar(value=str(k.get(ad, "")))
            ttk.Entry(govde, textvariable=deger, width=40,
                      show="*" if ad == "sifre" else "").grid(row=i, column=1, pady=4)
            self.degerler[ad] = deger

        self.aktif = tk.BooleanVar(value=k.get("aktif", True))
        ttk.Checkbutton(govde, text="Aktif", variable=self.aktif).grid(
            row=len(self.ALANLAR) + 1, column=1, sticky="w", pady=4)

        dugmeler = ttk.Frame(govde)
        dugmeler.grid(row=len(self.ALANLAR) + 2, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(dugmeler, text="Kaydet", command=self._kaydet).pack(side="left", padx=5)
        ttk.Button(dugmeler, text="İptal", command=self.destroy).pack(side="left", padx=5)

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
        yanlis = gecersiz_adresler(d["bildirim_eposta"])
        if yanlis:
            return f"Geçersiz e-posta adresi: {', '.join(yanlis)}"
        if not d["onay_eposta"] or "," in d["onay_eposta"] or gecersiz_adresler(d["onay_eposta"]):
            return "Onaylayacak kişinin e-postası zorunlu ve tek bir geçerli adres olmalı."
        return None

    def _kaydet(self):
        d = {ad: v.get().strip() for ad, v in self.degerler.items()}
        tip = self.tip.get()
        hata = self._dogrula(d, tip)
        if hata:
            messagebox.showerror("Hatalı giriş", hata, parent=self)
            return
        self.sonuc = {
            "kod": d["kod"], "yatak": d["yatak"], "tip": tip,
            "adres": int(d["adres"]) if tip == "webcam" else d["adres"],
            "kullanici": d["kullanici"], "sifre": d["sifre"],
            "bildirim_eposta": d["bildirim_eposta"],
            "onay_eposta": d["onay_eposta"].lower(),
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

        self.kayitlar_sekmesi = KayitlarSekmesi(sekmeler)
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

    def _listeyi_doldur(self):
        durumlar = durumlari_oku()
        tesis = self.ayarlar["tesis_kodu"]
        aralik = self.ayarlar["gonderim_araligi_sn"]
        simdi = datetime.now()
        secili = self.liste.selection()

        self.liste.delete(*self.liste.get_children())
        for k in self.ayarlar["kameralar"]:
            d = durumlar.get(f"{tesis}/{k['kod']}/{k['yatak']}", {})
            durum = gorunen_durum(d, k.get("aktif", True), aralik, simdi, onayli=onayli_mi(k))
            yazi = DURUM_YAZISI.get(durum, durum)
            if durum == "onay_bekliyor" and kamera_onay.bekleyen_kod(k):
                yazi = "Onay bekliyor (mail gönderildi)"
            son = ekran_zamani(d.get("son_basari"))
            self.liste.insert("", "end", iid=k["kod"], tags=(durum,), values=(
                k["kod"], k["yatak"], k["tip"], gorunen_adres(k["adres"]), yazi, son))

        self.liste.selection_set([s for s in secili if self.liste.exists(s)])

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
        ttk.Button(cerceve, text="Onay kodunu gir", command=self._onay_kodu_gir).pack(side="left", padx=5)
        ttk.Button(cerceve, text="Onay mailini tekrar gönder",
                   command=self._onay_mailini_tekrar_gonder).pack(side="left", padx=5)

    def _diger_kameralar(self, haric: str | None = None) -> dict:
        return {k["kod"]: k["yatak"] for k in self.ayarlar["kameralar"] if k["kod"] != haric}

    def _secili_kamera(self) -> int | None:
        secili = self.liste.selection()
        if not secili:
            messagebox.showinfo("Seçim yok", "Önce listeden bir kamera seçin.")
            return None
        return next(i for i, k in enumerate(self.ayarlar["kameralar"]) if k["kod"] == secili[0])

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
        """Onaylayacak kişiye kodlu mail gönderir. SMTP yoksa yalnızca yönetici e-postasız onay verebilir."""
        smtp = self.ayarlar.get("smtp")
        if not smtp_hazir_mi(smtp):
            self._epostasiz_onay(k)
            return
        if not k.get("onay_eposta"):
            messagebox.showwarning("Onay e-postası yok", f"{k['kod']} için onaylayacak kişinin e-postası "
                                   "girilmemiş. Önce kamerayı düzenleyip e-postayı girin.")
            return
        kod = kamera_onay.kod_olustur(k, k["onay_eposta"], self.oturum["eposta"])
        konu, metin = kamera_onay.onay_maili(self.ayarlar.get("tesis_kodu", ""), k, self.oturum["eposta"], kod)
        del kod                                       # kod artık yalnızca mail metninde

        def gonderim():
            try:
                gonder(smtp, [k["onay_eposta"]], konu, metin)
                return None
            except Exception as e:
                return type(e).__name__

        arka_planda(self, gonderim, lambda hata: self._onay_maili_sonucu(k, hata))

    def _onay_maili_sonucu(self, k: dict, hata: str | None):
        if hata:
            kamera_onay.kodu_sil(k["kod"])            # gitmeyen kod geçerli kalmasın
            olay(self.log, "WARNING", k["kod"],
                 f"{k['kod']} onay maili gönderilemedi ({hata}) — {self.oturum['eposta']}")
            messagebox.showerror("Onay maili gönderilemedi",
                                 f"{k['kod']} için onay maili gönderilemedi ({hata}).\n\n"
                                 "E-posta ayarlarını kontrol edip 'Onay mailini tekrar gönder' ile deneyin.")
        else:
            olay(self.log, "INFO", k["kod"],
                 f"{k['kod']} onay maili gönderildi: {k['onay_eposta']} — {self.oturum['eposta']}")
            messagebox.showinfo("Onay maili gönderildi",
                                f"{k['kod']} için onay kodu {k['onay_eposta']} adresine gönderildi.\n\n"
                                "Kod gelince 'Onay kodunu gir' ile girin. Onaylanana kadar kameradan "
                                "görüntü alınmaz.")
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

    def _onay_kodu_gir(self):
        sira = self._secili_kamera()
        if sira is None:
            return
        k = self.ayarlar["kameralar"][sira]
        if self._zaten_onayli(k):
            return
        if not kamera_onay.bekleyen_kod(k):
            messagebox.showinfo("Kod yok", f"{k['kod']} için gönderilmiş geçerli bir onay kodu yok.\n\n"
                                           "'Onay mailini tekrar gönder' ile yeni kod gönderin.")
            return
        kod = simpledialog.askstring("Onay kodu", f"{k['kod']} → {k['yatak']} için e-postayla gelen "
                                                  "6 haneli onay kodunu girin:", parent=self)
        if not kod:
            return
        try:
            onaylayan = kamera_onay.kodu_dogrula(k, kod)
        except KullaniciHatasi as e:
            messagebox.showerror("Onaylanamadı", str(e), parent=self)
            self._listeyi_doldur()
            return
        self.ayarlar["kameralar"][sira] = onay_ver(k, onaylayan)
        ayarlari_yaz(self.ayarlar)
        olay(self.log, "INFO", k["kod"], f"{k['kod']} kullanımı onaylandı (onaylayan: {onaylayan}, "
                                         f"kodu giren: {self.oturum['eposta']})")
        self._listeyi_doldur()
        messagebox.showinfo("Onaylandı", f"{k['kod']} kamerası {onaylayan} onayıyla kullanıma açıldı.\n\n"
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
            k = form.sonuc                            # onaysız eklenir; onay e-posta koduyla gelir
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
                return kare, None
            except Exception as e:
                return None, str(e)

        arka_planda(self, cekim, lambda sonuc: self._test_sonucu(k, *(sonuc or (None, None))))

    def _test_sonucu(self, k: dict, kare, hata: str | None):
        self.test_dugmesi.config(state="normal", text="Bağlantıyı test et")
        if kare is None:
            messagebox.showerror(
                "Bağlantı başarısız",
                f"{k['kod']} kamerasından görüntü alınamadı.\n\n"
                f"{hata or 'Adres, kullanıcı adı ve şifreyi kontrol edin.'}")
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