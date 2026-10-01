"""Arayüzün Ayarlar sekmesi."""
import tkinter as tk
from tkinter import messagebox, ttk

from ayarlar import ayarlari_yaz

# (ayar adı, ekranda görünen ad, alan türü)
SATIRLAR = [
    ("tesis_kodu", "Tesis kodu", "metin"),
    ("api_url", "M4 API adresi", "metin"),
    ("api_key", "API anahtarı", "gizli"),
    ("gonderim_araligi_sn", "Çekim aralığı (sn)", "metin"),
    ("ikinci_cekim_gecikme_sn", "İkinci çekim gecikmesi (sn)", "metin"),
    ("format", "Görüntü formatı", "secim"),
    ("kalite", "Kalite (1-100)", "metin"),
    ("saklama_gun", "Sahipsiz dosya saklama (gün)", "metin"),
]

# (ayar adı, en az, en çok)
SAYI_SINIRLARI = [
    ("gonderim_araligi_sn", 10, 3600),
    ("ikinci_cekim_gecikme_sn", 1, 60),
    ("kalite", 1, 100),
    ("saklama_gun", 1, 365),
]


class AyarSekmesi(ttk.Frame):
    def __init__(self, ust, ayarlar: dict):
        super().__init__(ust, padding=15)
        self.ayarlar = ayarlar
        self.etiketler = {ad: etiket for ad, etiket, _ in SATIRLAR}
        self.degerler = {}

        for i, (ad, etiket, tur) in enumerate(SATIRLAR):
            ttk.Label(self, text=etiket).grid(row=i, column=0, sticky="w", pady=5, padx=(0, 15))
            deger = tk.StringVar(value=str(ayarlar.get(ad, "")))
            if tur == "secim":
                alan = ttk.Combobox(self, textvariable=deger, values=["avif", "jpg"],
                                    state="readonly", width=47)
            else:
                alan = ttk.Entry(self, textvariable=deger, width=50,
                                 show="*" if tur == "gizli" else "")
            alan.grid(row=i, column=1, sticky="w", pady=5)
            self.degerler[ad] = deger

        self.sil = tk.BooleanVar(value=ayarlar.get("gonderilince_sil", True))
        ttk.Checkbutton(self, text="Gönderilen görüntüleri hemen sil",
                        variable=self.sil).grid(row=len(SATIRLAR), column=1, sticky="w", pady=5)

        ttk.Button(self, text="Kaydet", command=self._kaydet).grid(
            row=len(SATIRLAR) + 1, column=1, sticky="w", pady=(15, 0))

    def _dogrula(self):
        """(yeni ayarlar, None) ya da (None, hata mesajı) döndürür."""
        d = {ad: v.get().strip() for ad, v in self.degerler.items()}

        if not d["tesis_kodu"]:
            return None, "Tesis kodu boş olamaz."
        if d["api_url"] and not d["api_url"].startswith(("http://", "https://")):
            return None, "API adresi http:// veya https:// ile başlamalı (ya da boş bırakılmalı)."

        sayilar = {}
        for ad, en_az, en_cok in SAYI_SINIRLARI:
            try:
                sayi = int(d[ad])
            except ValueError:
                return None, f"'{self.etiketler[ad]}' bir tam sayı olmalı."
            if not en_az <= sayi <= en_cok:
                return None, f"'{self.etiketler[ad]}' {en_az} ile {en_cok} arasında olmalı."
            sayilar[ad] = sayi

        if sayilar["gonderim_araligi_sn"] < sayilar["ikinci_cekim_gecikme_sn"] + 5:
            return None, "Çekim aralığı, ikinci çekim gecikmesinden en az 5 sn uzun olmalı."

        return {**d, **sayilar, "gonderilince_sil": self.sil.get()}, None

    def _kaydet(self):
        yeni, hata = self._dogrula()
        if hata:
            messagebox.showerror("Hatalı giriş", hata)
            return
        self.ayarlar.update(yeni)
        ayarlari_yaz(self.ayarlar)
        messagebox.showinfo("Kaydedildi", "Ayarlar kaydedildi.\n\n"
                            "Motor çalışıyorsa birkaç saniye içinde geçerli olur.")