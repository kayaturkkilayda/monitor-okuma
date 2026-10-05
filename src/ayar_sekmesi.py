"""Arayüzün Ayarlar sekmesi."""
import copy
import re
import tkinter as tk
from tkinter import messagebox, ttk

from ayarlar import ayarlari_yaz, degisen_alanlar
from eposta_bolumu import EpostaBolumu
from kullanicilar import alan_adi_normallestir
from veritabani import KAYIT_SAKLAMA_GUN, olay

_ALAN_ADI = re.compile(r"^([a-z0-9-]+\.)+[a-z]{2,}$")
YETKI_YOK = "Ayarları yalnızca yöneticiler değiştirebilir."

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
    ("kayit_saklama_gun", "Gönderim kaydı saklama (gün)", "metin"),
    ("izin_verilen_alan_adi", "Kayıt için izin verilen alan adı", "metin"),
]

# Eski ayar dosyalarında olmayan alanlar için ekranda gösterilecek değer
VARSAYILANLAR = {"kayit_saklama_gun": KAYIT_SAKLAMA_GUN}

# (ayar adı, en az, en çok)
SAYI_SINIRLARI = [
    ("gonderim_araligi_sn", 10, 3600),
    ("ikinci_cekim_gecikme_sn", 1, 60),
    ("kalite", 1, 100),
    ("saklama_gun", 1, 365),
    ("kayit_saklama_gun", 1, 3650),
]


def salt_okunur_yap(widget):
    """Bir çerçevedeki bütün giriş alanlarını, seçim kutularını ve düğmeleri kapatır."""
    for cocuk in widget.winfo_children():
        if isinstance(cocuk, (ttk.Entry, ttk.Button, ttk.Checkbutton)):   # Combobox da bir Entry
            cocuk.state(["disabled"])
        salt_okunur_yap(cocuk)


class AyarSekmesi(ttk.Frame):
    def __init__(self, ust, ayarlar: dict, oturum: dict | None = None, log=None):
        """oturum: giriş yapan kullanıcı. Yönetici değilse ayarlar görülür ama değiştirilemez."""
        super().__init__(ust, padding=15)
        self.ayarlar = ayarlar
        self.oturum = oturum or {}
        self.yonetici = bool(self.oturum.get("yonetici"))
        self.log = log
        self.etiketler = {ad: etiket for ad, etiket, _ in SATIRLAR}
        self.degerler = {}

        for i, (ad, etiket, tur) in enumerate(SATIRLAR):
            ttk.Label(self, text=etiket).grid(row=i, column=0, sticky="w", pady=5, padx=(0, 15))
            deger = tk.StringVar(value=str(ayarlar.get(ad, VARSAYILANLAR.get(ad, ""))))
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

        self.eposta = EpostaBolumu(self, ayarlar.get("smtp"))
        self.eposta.grid(row=0, column=2, rowspan=len(SATIRLAR) + 2, sticky="nw", padx=(25, 0))

        if not self.yonetici:
            salt_okunur_yap(self)
            ttk.Label(self, text=YETKI_YOK, foreground="#b00020").grid(
                row=len(SATIRLAR) + 2, column=1, sticky="w", pady=(10, 0))

    def _dogrula(self):
        """(yeni ayarlar, None) ya da (None, hata mesajı) döndürür."""
        d = {ad: v.get().strip() for ad, v in self.degerler.items()}

        if not d["tesis_kodu"]:
            return None, "Tesis kodu boş olamaz."
        if d["api_url"] and not d["api_url"].startswith(("http://", "https://")):
            return None, "API adresi http:// veya https:// ile başlamalı (ya da boş bırakılmalı)."
        d["izin_verilen_alan_adi"] = alan_adi_normallestir(d["izin_verilen_alan_adi"])
        if d["izin_verilen_alan_adi"] and not _ALAN_ADI.match(d["izin_verilen_alan_adi"]):
            return None, "İzin verilen alan adı örneğin akgun.com.tr biçiminde olmalı (@ olmadan)."

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

        smtp, hata = self.eposta.dogrula()
        if hata:
            return None, hata

        return {**d, **sayilar, "gonderilince_sil": self.sil.get(), "smtp": smtp}, None

    def _kaydet(self):
        if not self.yonetici:                 # düğme kapalı olsa da ikinci bir kontrol
            messagebox.showerror("Yetki yok", YETKI_YOK)
            return
        yeni, hata = self._dogrula()
        if hata:
            messagebox.showerror("Hatalı giriş", hata)
            return
        eski = copy.deepcopy(self.ayarlar)
        self.ayarlar.update(yeni)
        ayarlari_yaz(self.ayarlar)
        # Yalnızca değişen ayarların adları yazılır; değerleri (şifreler dahil) yazılmaz
        degisen = ", ".join(degisen_alanlar(eski, self.ayarlar)) or "değişiklik yok"
        if self.log:
            olay(self.log, "INFO", "sistem",
                 f"Ayarlar değiştirildi (değişen: {degisen}) — {self.oturum.get('eposta', '?')}")
        messagebox.showinfo("Kaydedildi", "Ayarlar kaydedildi.\n\n"
                            "Motor çalışıyorsa birkaç saniye içinde geçerli olur.")