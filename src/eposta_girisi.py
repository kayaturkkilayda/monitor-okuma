"""E-posta giriş alanı: yazarken biçim denetimi ve satır içi alan adı tamamlama.

Kullanıcı "ayse@g" yazınca kalan "mail.com" kutunun İÇİNDE seçili olarak belirir.
Enter ya da Tab tamamlamayı kabul eder. Yazmaya devam etmek seçili kısmın yerine geçer,
çünkü seçili metin bir sonraki tuşla değişir. Silerken tamamlama yapılmaz; yoksa alan
hiç boşaltılamaz.

Bir adresin gerçekten var olduğu çevrimdışı anlaşılamaz; burada yalnızca biçimi denetlenir.
Adresin gerçek olduğu, kayıtta o adrese giden doğrulama koduyla kanıtlanır.
"""
import tkinter as tk
from tkinter import ttk

from kullanicilar import KullaniciHatasi, alan_adi_listesi, eposta_kontrol

YAYGIN_ALANLAR = ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "icloud.com", "yandex.com"]
EN_FAZLA_ONERI = 6
YESIL, KIRMIZI = "#1e7e34", "#b00020"

# Bu tuşlar metni uzatmaz; bunlardan sonra tamamlama yapılmaz
TAMAMLAMAYAN_TUSLAR = {
    "BackSpace", "Delete", "Left", "Right", "Up", "Down", "Home", "End",
    "Return", "KP_Enter", "Tab", "ISO_Left_Tab", "Escape",
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
}


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


def tamamlama(metin: str, alanlar: list[str]) -> str | None:
    """Satır içi tamamlama için tek öneri: 'ayse@g' → 'ayse@gmail.com'.

    Tamamlanacak bir şey yoksa None. İlk sıradaki öneri seçilir; kurumun alan adları
    oneri_alanlari() tarafından başa konduğu için önce onlar tamamlanır.
    """
    oneriler = alan_onerileri(metin, alanlar, en_fazla=1)
    return oneriler[0] if oneriler else None


class EpostaGirisi(ttk.Frame):
    """Giriş kutusu + altında geçerlilik ipucu. Tamamlama kutunun içinde gösterilir.

    alanlar_getir(): o an önerilecek alan adlarını döndürür (ayar değişmiş olabilir).
    """

    def __init__(self, ust, degisken: tk.StringVar, alanlar_getir, genislik: int = 34):
        super().__init__(ust)
        self.degisken = degisken
        self.alanlar_getir = alanlar_getir
        self._kendi_yaziyor = False          # kendi yazdığımız değer ipucunu şaşırtmasın

        self.giris = ttk.Entry(self, textvariable=degisken, width=genislik)
        self.giris.grid(row=0, column=0, sticky="we")
        self.columnconfigure(0, weight=1)
        self.ipucu = ttk.Label(self, text="", style="Kucuk.TLabel")
        self.ipucu.grid(row=1, column=0, sticky="w")

        degisken.trace_add("write", lambda *a: self._ipucu_guncelle(son_karar=False))
        self.giris.bind("<KeyRelease>", self._tus_birakildi)
        self.giris.bind("<Return>", self._kabul_tusu)
        self.giris.bind("<Tab>", self._kabul_tusu)
        self.giris.bind("<FocusOut>", lambda e: self.after(100, self._odak_gitti))

    # --- satır içi tamamlama ---

    def _tus_birakildi(self, olay=None):
        """Yalnızca metni uzatan tuşlardan sonra tamamlar."""
        if olay is not None and olay.keysym in TAMAMLAMAYAN_TUSLAR:
            return
        self.tamamla()

    def tamamla(self):
        """Kalan alan adını kutuya yazıp seçili bırakır. Bir şey yoksa dokunmaz."""
        metin = self.degisken.get()
        if self.giris.index("insert") != len(metin):
            return                            # imleç sonda değil: araya yazılıyor, karışmayalım
        tam = tamamlama(metin, self.alanlar_getir())
        if not tam:
            return
        self._kendi_yaziyor = True
        try:
            self.degisken.set(tam)
            self.giris.icursor(len(metin))
            self.giris.selection_range(len(metin), "end")
        finally:
            self._kendi_yaziyor = False

    def secili_metin(self) -> str:
        """Kutuda seçili (tamamlanmış) kısım; yoksa boş metin."""
        if not self.giris.selection_present():
            return ""
        return self.degisken.get()[self.giris.index("sel.first"):self.giris.index("sel.last")]

    def kabul_et(self):
        """Tamamlamayı kabul eder: seçim kalkar, imleç sona gider."""
        if self.giris.selection_present():
            self.giris.selection_clear()
        self.giris.icursor("end")

    def _kabul_tusu(self, olay=None):
        """Enter/Tab: önce tamamlamayı kabul et.

        Tamamlama varken Enter formu göndermez, yalnızca tamamlamayı onaylar; ikinci
        Enter formu gönderir. Tamamlama yoksa tuş olduğu gibi devam eder.
        """
        if self.giris.selection_present():
            self.kabul_et()
            self._ipucu_guncelle(son_karar=True)
            return "break"
        return None

    def _odak_gitti(self):
        self.kabul_et()
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
