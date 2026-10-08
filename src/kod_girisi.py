"""Altı kutulu kod girişi.

E-posta doğrulama ve kamera onayı aynı bileşeni kullanır. Her hane kendi kutusundadır.
Kullanıcı rakam yazınca imleç kendiliğinden ilerler. Backspace boş kutuda bir öncekine
döner. Yalnızca rakam kabul edilir. Altı haneli bir kod yapıştırılırsa kutulara dağılır.
Son hane girilince kod kendiliğinden doğrulanır.

Kutular ttk yerine tk.Entry'dir: Windows'un vista teması ttk kenarlık rengini ezer,
hatalı kodda kırmızı çerçeve gösterilemezdi.
"""
import tkinter as tk
from tkinter import ttk
import tema

HANE = 6
RAKAMLAR = "0123456789"

NORMAL_KENAR = "#adb5bd"
ODAK_KENAR = "#0b5ed7"
HATA_KENAR = "#b00020"


def rakamlari_ayikla(metin: str, en_fazla: int = HANE) -> str:
    """'123-456 ' → '123456'. Yapıştırılan metinden yalnızca rakamları alır."""
    return "".join(h for h in str(metin) if h in RAKAMLAR)[:en_fazla]


class KodGirisi(ttk.Frame):
    """hane adet tek karakterlik kutu.

    tamamlandi(kod): bütün haneler dolunca çağrılır. Kodu doğrulamak çağıranın işidir.
    """

    def __init__(self, ust, hane: int = HANE, tamamlandi=None):
        super().__init__(ust)
        self.hane = hane
        self.tamamlandi = tamamlandi
        self.odakli = 0                 # imlecin hangi kutuda olduğu (testler de buna bakar)
        self.degerler, self.kutular = [], []
        dogrula = self.register(self._tek_rakam)

        for i in range(hane):
            deger = tk.StringVar()
            kutu = tk.Entry(self, textvariable=deger, width=2, justify="center",
                            font=tema.BUYUK_YAZI, relief="solid", borderwidth=1,
                            highlightthickness=2, highlightbackground=NORMAL_KENAR,
                            highlightcolor=ODAK_KENAR,
                            validate="key", validatecommand=(dogrula, "%P"))
            kutu.grid(row=0, column=i, padx=3)
            kutu.bind("<KeyRelease>", lambda o, s=i: self._tus_birakildi(s, o))
            kutu.bind("<FocusIn>", lambda o, s=i: self._odaklandi(s))
            kutu.bind("<<Paste>>", self._yapistir)
            self.degerler.append(deger)
            self.kutular.append(kutu)

    # ---------- Dışarıya açık ----------

    def kod(self) -> str:
        """Kutulardaki kod; eksikse kısa döner."""
        return "".join(d.get() for d in self.degerler)

    def dolu_mu(self) -> bool:
        return len(self.kod()) == self.hane

    def temizle(self, hata: bool = False):
        """Kutuları boşaltır. hata=True ise kırmızı çerçeve gösterir."""
        for deger in self.degerler:
            deger.set("")
        self._kenar(HATA_KENAR if hata else NORMAL_KENAR)
        self.odakla()

    def odakla(self):
        self._odakla(0)

    def _odakla(self, sira: int):
        """İmleci bir kutuya taşır ve nerede olduğunu kaydeder."""
        self.odakli = sira
        self.kutular[sira].focus_set()
        self.kutular[sira].select_range(0, "end")

    def yaz(self, metin: str, bildir: bool = True):
        """Kodu kutulara dağıtır (yapıştırma ve testler için).

        bildir=False: kutular doldurulur ama doğrulama tetiklenmez. Dışarıdan gelen
        değer (ör. ekran temizliği) kendiliğinden doğrulamaya girmesin diye.
        """
        rakamlar = rakamlari_ayikla(metin, self.hane)
        for i, deger in enumerate(self.degerler):
            deger.set(rakamlar[i] if i < len(rakamlar) else "")
        self._kenar(NORMAL_KENAR)
        self._odakla(min(len(rakamlar), self.hane - 1))
        if bildir:
            self._belki_tamamlandi()

    # ---------- İç işleyiş ----------

    @staticmethod
    def _tek_rakam(yeni: str) -> bool:
        """Kutuya yalnızca tek bir rakam yazılabilir."""
        return yeni == "" or (len(yeni) == 1 and yeni in RAKAMLAR)

    def _kenar(self, renk: str):
        for kutu in self.kutular:
            kutu.config(highlightbackground=renk,
                        highlightcolor=ODAK_KENAR if renk == NORMAL_KENAR else renk)

    def _odaklandi(self, sira: int):
        self.odakli = sira
        self.kutular[sira].select_range(0, "end")

    def _tus_birakildi(self, sira: int, olay=None):
        tus = getattr(olay, "keysym", "")
        if tus == "BackSpace":
            # Boş kutuda Backspace bir öncekine döner ve onu siler
            if not self.degerler[sira].get() and sira > 0:
                self.degerler[sira - 1].set("")
                self._odakla(sira - 1)
            return
        if tus in ("Left", "Up"):
            if sira > 0:
                self._odakla(sira - 1)
            return
        if tus in ("Right", "Down"):
            if sira + 1 < self.hane:
                self._odakla(sira + 1)
            return
        if self.degerler[sira].get():
            self._kenar(NORMAL_KENAR)                 # yazmaya başlayınca hata rengi kalksın
            if sira + 1 < self.hane:
                self._odakla(sira + 1)
            self._belki_tamamlandi()

    def _yapistir(self, olay=None):
        try:
            panodaki = self.clipboard_get()
        except tk.TclError:
            return "break"
        self.yaz(panodaki)
        return "break"                                # kutu kendi yapıştırmasını yapmasın

    def _belki_tamamlandi(self):
        if self.dolu_mu() and self.tamamlandi:
            self.tamamlandi(self.kod())


class KodPenceresi(tk.Toplevel):
    """Kod girişini tek başına bir pencerede sorar.

    dogrula(kod): kod doğruysa bir şey döndürür, yanlışsa KullaniciHatasi fırlatır.
    Doğru kodda pencere kapanır ve sonuc alanına doğrulamanın dönüşü yazılır.
    """

    def __init__(self, ust, baslik: str, aciklama: str, dogrula, hata_sinifi):
        super().__init__(ust)
        self.title(baslik)
        self.resizable(False, False)
        self.transient(ust)
        self.dogrula = dogrula
        self.hata_sinifi = hata_sinifi
        self.sonuc = None

        govde = ttk.Frame(self, padding=20)
        govde.pack(fill="both", expand=True)
        ttk.Label(govde, text=aciklama, wraplength=360, justify="left").pack(anchor="w")
        self.giris = KodGirisi(govde, tamamlandi=self._dene)
        self.giris.pack(pady=(14, 6))
        self.mesaj = ttk.Label(govde, text="", foreground=HATA_KENAR, wraplength=360,
                               justify="left")
        self.mesaj.pack(anchor="w")
        ttk.Button(govde, text="Kapat", command=self.destroy).pack(pady=(12, 0))

        self.grab_set()
        self.giris.odakla()

    def _dene(self, kod: str):
        try:
            self.sonuc = self.dogrula(kod)
        except self.hata_sinifi as e:
            self.mesaj.config(text=str(e))
            self.giris.temizle(hata=True)
            return
        self.destroy()
