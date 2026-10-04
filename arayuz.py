"""Ayar ve izleme arayüzü. Motordan (main.py) bağımsız çalışır."""
import json
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import cv2
from PIL import Image, ImageTk

KOK = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
os.chdir(KOK)
sys.path.insert(0, str(KOK / "src"))
from ayarlar import ayarlari_oku, ayarlari_yaz, kameralari_olustur
from ayar_sekmesi import AyarSekmesi
from zaman import ekran_zamani

DURUM_DOSYASI = Path("durum.json")
YENILEME_MS = 5000

DURUM_YAZISI = {"calisiyor": "Çalışıyor", "arizali": "Arızalı",
                "pasif": "Pasif", "bilinmiyor": "Bilinmiyor"}


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
               ("kullanici", "Kullanıcı adı"), ("sifre", "Şifre")]

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
            "aktif": self.aktif.get(),
        }
        self.destroy()


class Uygulama(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Monitör Görüntü Aktarımı")
        self.geometry("950x500")
        self.ayarlar = ayarlari_oku()

        sekmeler = ttk.Notebook(self)
        sekmeler.pack(fill="both", expand=True, padx=10, pady=10)

        self.kamera_sekmesi = ttk.Frame(sekmeler, padding=10)
        sekmeler.add(self.kamera_sekmesi, text="Kameralar")
        self._kamera_listesi_kur()
        self._dugmeleri_kur()

        self.ayar_sekmesi = AyarSekmesi(sekmeler, self.ayarlar)
        sekmeler.add(self.ayar_sekmesi, text="Ayarlar")

        self._periyodik_yenile()

    # ---------- Liste ----------

    def _kamera_listesi_kur(self):
        kolonlar = {"kod": ("Kamera", 70), "yatak": ("Yatak", 100),
                    "tip": ("Tip", 70), "adres": ("Adres", 330),
                    "durum": ("Durum", 100), "son": ("Son görüntü", 140)}
        self.liste = ttk.Treeview(self.kamera_sekmesi, columns=list(kolonlar),
                                  show="headings", height=15)
        for ad, (baslik, genislik) in kolonlar.items():
            self.liste.heading(ad, text=baslik)
            self.liste.column(ad, width=genislik)

        self.liste.tag_configure("calisiyor", background="#d4edda")
        self.liste.tag_configure("arizali", background="#f8d7da")
        self.liste.tag_configure("pasif", foreground="#999999")
        self.liste.pack(fill="both", expand=True)
        self.liste.bind("<Double-1>", lambda e: self._duzenle())

    def _listeyi_doldur(self):
        durumlar = durumlari_oku()
        tesis = self.ayarlar["tesis_kodu"]
        secili = self.liste.selection()

        self.liste.delete(*self.liste.get_children())
        for k in self.ayarlar["kameralar"]:
            d = durumlar.get(f"{tesis}/{k['kod']}/{k['yatak']}", {})
            durum = d.get("durum", "bilinmiyor") if k.get("aktif", True) else "pasif"
            son = ekran_zamani(d.get("son_basari"))
            self.liste.insert("", "end", iid=k["kod"], tags=(durum,), values=(
                k["kod"], k["yatak"], k["tip"], k["adres"],
                DURUM_YAZISI.get(durum, durum), son))

        self.liste.selection_set([s for s in secili if self.liste.exists(s)])

    def _periyodik_yenile(self):
        self._listeyi_doldur()
        self.after(YENILEME_MS, self._periyodik_yenile)

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

    def _diger_kameralar(self, haric: str | None = None) -> dict:
        return {k["kod"]: k["yatak"] for k in self.ayarlar["kameralar"] if k["kod"] != haric}

    def _secili_kamera(self) -> int | None:
        secili = self.liste.selection()
        if not secili:
            messagebox.showinfo("Seçim yok", "Önce listeden bir kamera seçin.")
            return None
        return next(i for i, k in enumerate(self.ayarlar["kameralar"]) if k["kod"] == secili[0])

    def _ekle(self):
        form = KameraFormu(self, self._diger_kameralar())
        self.wait_window(form)
        if form.sonuc:
            self.ayarlar["kameralar"].append(form.sonuc)
            self._kaydet_ve_bildir(f"{form.sonuc['kod']} eklendi")

    def _duzenle(self):
        sira = self._secili_kamera()
        if sira is None:
            return
        eski = self.ayarlar["kameralar"][sira]
        form = KameraFormu(self, self._diger_kameralar(haric=eski["kod"]), eski)
        self.wait_window(form)
        if form.sonuc:
            self.ayarlar["kameralar"][sira] = form.sonuc
            self._kaydet_ve_bildir(f"{form.sonuc['kod']} güncellendi")

    def _sil(self):
        sira = self._secili_kamera()
        if sira is None:
            return
        k = self.ayarlar["kameralar"][sira]
        if not messagebox.askyesno("Kamerayı sil",
                                   f"{k['kod']} → {k['yatak']} silinsin mi?"):
            return
        del self.ayarlar["kameralar"][sira]
        self._kaydet_ve_bildir(f"{k['kod']} silindi")

    def _kaydet_ve_bildir(self, mesaj: str):
        ayarlari_yaz(self.ayarlar)
        self._listeyi_doldur()
        messagebox.showinfo("Kaydedildi",
                            f"{mesaj}.\n\nMotor çalışıyorsa birkaç saniye içinde geçerli olur.")
    # ---------- Bağlantı testi ----------

    def _baglanti_test(self):
        sira = self._secili_kamera()
        if sira is None:
            return
        k = self.ayarlar["kameralar"][sira]
        # Pasif kamerayı da test edebilmek için geçici olarak aktif sayıyoruz
        kamera = kameralari_olustur({"kameralar": [{**k, "aktif": True}]})[0]
        self.test_dugmesi.config(state="disabled", text="Test ediliyor...")

        def arka_planda():
            try:
                kare, *_ = kamera.cift_cekim(aralik_sn=0)
                hata = None
            except Exception as e:
                kare, hata = None, str(e)
            # Pencereyi sadece ana iş parçacığı güncelleyebilir; sonucu ona devrediyoruz
            self.after(0, lambda: self._test_sonucu(k, kare, hata))

        threading.Thread(target=arka_planda, daemon=True).start()

    def _test_sonucu(self, k: dict, kare, hata: str | None):
        self.test_dugmesi.config(state="normal", text="Bağlantıyı test et")
        if kare is None:
            messagebox.showerror(
                "Bağlantı başarısız",
                f"{k['kod']} kamerasından görüntü alınamadı.\n\n"
                f"{hata or 'Adres, kullanıcı adı ve şifreyi kontrol edin.'}")
            return

        pencere = tk.Toplevel(self)
        pencere.title(f"{k['kod']} → {k['yatak']}  |  {kare.shape[1]}x{kare.shape[0]}")
        goruntu = Image.fromarray(cv2.cvtColor(kare, cv2.COLOR_BGR2RGB))
        goruntu.thumbnail((800, 600))
        foto = ImageTk.PhotoImage(goruntu)
        etiket = ttk.Label(pencere, image=foto)
        etiket.image = foto      # referansı tut; yoksa Python resmi siler ve pencere boş kalır
        etiket.pack(padx=10, pady=10)


if __name__ == "__main__":
    Uygulama().mainloop()