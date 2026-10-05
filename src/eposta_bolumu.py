"""Ayarlar sekmesindeki "E-posta (SMTP)" bölümü."""
import tkinter as tk
from tkinter import ttk

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
    ("gonderen", "Gönderen adres", "metin"),
    ("varsayilan_alici", "Varsayılan bildirim adresi", "metin"),
]

YESIL, KIRMIZI = "#1e7e34", "#b00020"


def smtp_dogrula(d: dict) -> tuple[dict | None, str | None]:
    """Formdaki değerleri denetler: (smtp ayarı, None) ya da (None, hata mesajı).

    Sunucu boşsa e-posta kapalı sayılır; diğer alanlar yine saklanır.
    """
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
    if not d["sunucu"]:
        return d, None
    if not d["gonderen"] or gecersiz_adresler(d["gonderen"]) or "," in d["gonderen"]:
        return None, "Gönderen adres geçerli tek bir e-posta adresi olmalı."
    yanlis = gecersiz_adresler(d["varsayilan_alici"])
    if yanlis:
        return None, f"Geçersiz bildirim adresi: {', '.join(yanlis)}"
    return d, None


class EpostaBolumu(ttk.LabelFrame):
    def __init__(self, ust, smtp: dict | None):
        super().__init__(ust, text="E-posta (SMTP)", padding=10)
        smtp = smtp or {}
        self.degerler = {}
        for i, (ad, etiket, tur) in enumerate(ALANLAR):
            ttk.Label(self, text=etiket).grid(row=i, column=0, sticky="w", pady=4, padx=(0, 10))
            varsayilan = {"guvenlik": "STARTTLS", "port": VARSAYILAN_PORT["STARTTLS"]}.get(ad, "")
            deger = tk.StringVar(value=str(smtp.get(ad, varsayilan)))
            if tur == "secim":
                alan = ttk.Combobox(self, textvariable=deger, values=list(GUVENLIK_SECENEKLERI),
                                    state="readonly", width=32)
            else:
                alan = ttk.Entry(self, textvariable=deger, width=35, show="*" if tur == "gizli" else "")
            alan.grid(row=i, column=1, sticky="w", pady=4)
            self.degerler[ad] = deger

        self.test_dugmesi = ttk.Button(self, text="Test maili gönder", command=self._test)
        self.test_dugmesi.grid(row=len(ALANLAR), column=1, sticky="w", pady=(10, 0))
        self.sonuc = ttk.Label(self, text="", wraplength=330, justify="left")
        self.sonuc.grid(row=len(ALANLAR) + 1, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def dogrula(self):
        return smtp_dogrula({ad: v.get() for ad, v in self.degerler.items()})

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
