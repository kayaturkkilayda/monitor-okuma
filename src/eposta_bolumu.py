"""Ayarlar sekmesindeki "E-posta (SMTP)" bölümü.

Gönderen adres ayrı bir alan değildir: mailler her zaman SMTP kullanıcı adından gider.
Varsayılan bildirim adresi de sorulmaz; ayarları kaydeden yöneticinin e-postası kullanılır.
Böylece yönetici aynı adresi iki kez yazmaz ve yanlış gönderen adresi girilemez.
"""
import tkinter as tk
from tkinter import ttk

import tema
from arka_plan import arka_planda
from bildirim import GUVENLIK_SECENEKLERI, gecersiz_adresler, test_maili_gonder

VARSAYILAN_PORT = {"STARTTLS": 587, "SSL": 465, "Yok": 25}

# (ayar adı, ekranda görünen ad, alan türü)
ALANLAR = [
    ("sunucu", "Sunucu", "metin"),
    ("port", "Port", "metin"),
    ("guvenlik", "Güvenlik", "secim"),
    ("kullanici", "Kullanıcı adı", "metin"),
    ("sifre", "Şifre", "gizli"),
]

# Formda sorulmayan ama ayar dosyasında tutulan alanlar
TASINAN_ALANLAR = ("varsayilan_alici", "gonderen")

YESIL, KIRMIZI = "#1e7e34", "#b00020"
KULLANICI_IPUCU = "Mailler bu adresten gönderilir."


def smtp_dogrula(d: dict, varsayilan_alici: str = "") -> tuple[dict | None, str | None]:
    """Formdaki değerleri denetler: (smtp ayarı, None) ya da (None, hata mesajı).

    Sunucu boşsa e-posta kapalı sayılır; diğer alanlar yine saklanır.
    varsayilan_alici: ayarları kaydeden yöneticinin e-postası; bildirimler buraya gider.
    """
    eski = d
    d = {ad: str(d.get(ad, "")).strip() for ad, _, _ in ALANLAR}
    if d["guvenlik"] not in GUVENLIK_SECENEKLERI:
        d["guvenlik"] = "STARTTLS"
    if not d["port"]:
        d["port"] = str(VARSAYILAN_PORT[d["guvenlik"]])
    try:
        d["port"] = int(d["port"])
    except ValueError:
        return None, "SMTP portu bir tam sayı olmalı."
    if not 1 <= d["port"] <= 65535:
        return None, "SMTP portu 1 ile 65535 arasında olmalı."

    # Eski ayar dosyasındaki alanlar silinmesin (geriye uyumluluk)
    for ad in TASINAN_ALANLAR:
        if eski.get(ad):
            d[ad] = str(eski[ad]).strip()

    alici = (varsayilan_alici or d.get("varsayilan_alici") or "").strip()
    if alici:
        d["varsayilan_alici"] = alici

    if not d["sunucu"]:
        return d, None
    if not d["kullanici"]:
        return None, "SMTP kullanıcı adı girilmeli; mailler bu adresten gönderilir."
    if gecersiz_adresler(d["kullanici"]) or "," in d["kullanici"]:
        return None, ("SMTP kullanıcı adı tek bir geçerli e-posta adresi olmalı; "
                      "gönderen adres olarak kullanılır.")
    return d, None


class EpostaBolumu(ttk.LabelFrame):
    """varsayilan_alici: ayarları kaydeden yöneticinin e-postası (bildirimler oraya gider)."""

    def __init__(self, ust, smtp: dict | None, varsayilan_alici: str = ""):
        super().__init__(ust, text="E-posta (SMTP)", padding=10)
        smtp = smtp or {}
        self.varsayilan_alici = varsayilan_alici
        self.tasinan = {ad: smtp.get(ad, "") for ad in TASINAN_ALANLAR}
        self.degerler = {}
        self.columnconfigure(1, weight=1)        # giriş kutuları pencereyle birlikte büyür
        satir = 0
        for ad, etiket, tur in ALANLAR:
            ttk.Label(self, text=etiket).grid(row=satir, column=0, sticky="w", pady=3, padx=(0, 10))
            varsayilan = {"guvenlik": "STARTTLS", "port": VARSAYILAN_PORT["STARTTLS"]}.get(ad, "")
            deger = tk.StringVar(value=str(smtp.get(ad, varsayilan)))
            if tur == "secim":
                alan = ttk.Combobox(self, textvariable=deger, values=list(GUVENLIK_SECENEKLERI),
                                    state="readonly", width=20)
            else:
                alan = ttk.Entry(self, textvariable=deger, width=20, show="*" if tur == "gizli" else "")
            alan.grid(row=satir, column=1, sticky="ew", pady=3)
            self.degerler[ad] = deger
            satir += 1
            if ad == "kullanici":
                # İpucu kutunun altında: yan yana koyunca kutuya genişlik kalmıyordu
                ttk.Label(self, text=KULLANICI_IPUCU, style="Kucuk.TLabel").grid(
                    row=satir, column=1, sticky="w", pady=(0, 4))
                satir += 1

        alici_yazisi = (f"Bildirimler {varsayilan_alici} adresine gider."
                        if varsayilan_alici else "Bildirim adresi: ayarları kaydeden yönetici.")
        ttk.Label(self, text=alici_yazisi, style="Kucuk.TLabel",
                  wraplength=tema.sarma_genisligi(330), justify="left").grid(row=satir, column=0, columnspan=2,
                                                       sticky="w", pady=(8, 0))

        self.test_dugmesi = ttk.Button(self, text="Test maili gönder", command=self._test)
        self.test_dugmesi.grid(row=satir + 1, column=1, sticky="w", pady=(10, 0))
        self.sonuc = ttk.Label(self, text="", wraplength=tema.sarma_genisligi(330),
                               justify="left")
        self.sonuc.grid(row=satir + 2, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def dogrula(self):
        degerler = {ad: v.get() for ad, v in self.degerler.items()}
        return smtp_dogrula({**self.tasinan, **degerler}, self.varsayilan_alici)

    def _test(self):
        """Formdaki (henüz kaydedilmemiş olabilir) ayarlarla varsayılan adrese deneme maili."""
        smtp, hata = self.dogrula()
        if hata:
            self.sonuc_goster(False, hata)
            return
        self.test_dugmesi.config(state="disabled", text="Gönderiliyor...")
        self.sonuc.config(text="")

        arka_planda(self, lambda: test_maili_gonder(smtp),
                    lambda sonuc: self.sonuc_goster(*(sonuc or (False, "Beklenmeyen hata"))))

    def sonuc_goster(self, basarili: bool, aciklama: str):
        self.test_dugmesi.config(state="normal", text="Test maili gönder")
        self.sonuc.config(text=("✓ " if basarili else "✗ ") + aciklama,
                          foreground=YESIL if basarili else KIRMIZI)
