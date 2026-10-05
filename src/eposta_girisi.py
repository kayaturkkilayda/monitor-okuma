"""E-posta giriş alanı: yazarken biçim denetimi ve @'den sonrası için alan adı önerileri.

Bir adresin gerçekten var olduğu çevrimdışı anlaşılamaz; burada yalnızca biçimi denetlenir.
Adresin gerçek olduğu, kayıtta o adrese giden doğrulama koduyla kanıtlanır.
"""
import tkinter as tk
from tkinter import ttk

from kullanicilar import KullaniciHatasi, alan_adi_listesi, eposta_kontrol

YAYGIN_ALANLAR = ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "icloud.com", "yandex.com"]
EN_FAZLA_ONERI = 6
YESIL, KIRMIZI = "#1e7e34", "#b00020"


def eposta_gecerli_mi(metin: str) -> bool:
    try:
        eposta_kontrol(metin)
        return True
    except KullaniciHatasi:
        return False


def oneri_alanlari(izinli_alanlar, yalnizca_izinli: bool = False) -> list[str]:
    """Önerilecek alan adları: kurumun izin verdiği alan adları en başta.

    Kayıt ekranında yalnızca izin verilen alan adları önerilir; diğerleri zaten reddedilir.
    İzin listesi boşsa (her alan adı kabul ediliyorsa) yaygın alan adları önerilir.
    """
    izinli = alan_adi_listesi(izinli_alanlar)
    if yalnizca_izinli and izinli:
        return izinli
    return izinli + [a for a in YAYGIN_ALANLAR if a not in izinli]


def alan_onerileri(metin: str, alanlar: list[str], en_fazla: int = EN_FAZLA_ONERI) -> list[str]:
    """'ayse@g' → ['ayse@gmail.com']. @ yoksa ya da alan adı zaten tamsa öneri yok."""
    if metin.count("@") != 1:
        return []
    yerel, yazilan = metin.split("@")
    yerel, yazilan = yerel.strip(), yazilan.strip().lower()
    if not yerel:
        return []
    return [f"{yerel}@{a}" for a in alanlar if a.startswith(yazilan) and a != yazilan][:en_fazla]


class EpostaGirisi(ttk.Frame):
    """Giriş kutusu + altında açılan öneri listesi + geçerlilik ipucu.

    alanlar_getir(): o an önerilecek alan adlarını döndürür (ayar değişmiş olabilir).
    """

    def __init__(self, ust, degisken: tk.StringVar, alanlar_getir, genislik: int = 34):
        super().__init__(ust)
        self.degisken = degisken
        self.alanlar_getir = alanlar_getir
        self.giris = ttk.Entry(self, textvariable=degisken, width=genislik)
        self.giris.grid(row=0, column=0, sticky="w")
        self.oneriler = tk.Listbox(self, height=4, width=genislik + 4, activestyle="dotbox",
                                   exportselection=False)
        self.ipucu = ttk.Label(self, text="", font=("Segoe UI", 8))
        self.ipucu.grid(row=2, column=0, sticky="w")

        degisken.trace_add("write", lambda *a: self.guncelle())
        self.giris.bind("<Down>", self._listeye_gec)
        self.giris.bind("<FocusOut>", lambda e: self.after(150, self._odak_gitti))
        self.oneriler.bind("<Return>", lambda e: self.sec())
        self.oneriler.bind("<Double-Button-1>", lambda e: self.sec())
        self.oneriler.bind("<ButtonRelease-1>", lambda e: self.sec())
        self.oneriler.bind("<Escape>", lambda e: self.gizle())

    # --- öneriler ---

    def guncelle(self):
        metin = self.degisken.get()
        liste = alan_onerileri(metin, self.alanlar_getir())
        self.oneriler.delete(0, "end")
        for oneri in liste:
            self.oneriler.insert("end", oneri)
        if liste:
            self.oneriler.config(height=min(len(liste), EN_FAZLA_ONERI))
            self.oneriler.grid(row=1, column=0, sticky="w")
        else:
            self.gizle()
        self._ipucu_guncelle(son_karar=False)

    def gizle(self):
        self.oneriler.grid_remove()

    def gorunur_oneriler(self) -> list[str]:
        return list(self.oneriler.get(0, "end")) if self.oneriler.grid_info() else []

    def sec(self, sira: int | None = None):
        if sira is None:
            secili = self.oneriler.curselection()
            sira = secili[0] if secili else 0
        if self.oneriler.size():
            self.degisken.set(self.oneriler.get(sira))
        self.gizle()
        self.giris.focus_set()
        self.giris.icursor("end")

    def _listeye_gec(self, olay=None):
        if self.oneriler.size():
            self.oneriler.focus_set()
            self.oneriler.selection_clear(0, "end")
            self.oneriler.selection_set(0)
            self.oneriler.activate(0)
        return "break"

    def _odak_gitti(self):
        if self.focus_get() is not self.oneriler:
            self.gizle()
            self._ipucu_guncelle(son_karar=True)

    # --- geçerlilik ipucu ---

    def _ipucu_guncelle(self, son_karar: bool):
        """Yazarken @'den sonra bir şey yazılınca, alandan çıkınca her zaman denetler."""
        metin = self.degisken.get().strip()
        if not metin or ("@" not in metin and not son_karar):
            self.ipucu.config(text="")
        elif eposta_gecerli_mi(metin):
            self.ipucu.config(text="✓ Geçerli bir e-posta adresi", foreground=YESIL)
        elif son_karar or "." in metin.split("@")[-1]:
            self.ipucu.config(text="Geçerli bir e-posta adresi değil (örn. ad@akgun.com.tr)",
                              foreground=KIRMIZI)
        else:
            self.ipucu.config(text="")
