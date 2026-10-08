"""Arayüzün Loglar sekmesi: olaylar tablosu (arıza, uyarı, hata ve motor olayları).

Kim hangi satırı görür (süzme veri okunurken yapılır, log dosyası/veritabanı aynı kalır):
- Yönetici bütün satırları görür.
- Normal kullanıcı yalnızca sahibi olduğu kameraların satırlarını görür (sahiplik kuralı
  src/sahiplik.py'de; buradaki kodlar oradan gelir).
- "sistem" satırlarından ise yalnızca kendisiyle ilgili olanları (kendi girişi gibi, yani
  mesajında kendi e-postası geçenleri) görür. Motor başladı, sunucu açıldı gibi genel
  satırlar ve başka kullanıcıların giriş satırları yalnızca yöneticide görünür.
"""
import sqlite3
import tkinter as tk
from tkinter import ttk

import tema
from veritabani import baglan
from zaman import ekran_zamani

SISTEM_KAYNAGI = "sistem"   # kameraya değil, programın kendisine ait satırlar

YENILEME_MS = 3000
EN_FAZLA = 1000           # ekranda en çok bu kadar satır tutulur

SEVIYE_SECENEKLERI = {"Hepsi": ("INFO", "WARNING", "ERROR"),
                      "Uyarı ve hata": ("WARNING", "ERROR"),
                      "Sadece hata": ("ERROR",)}
SEVIYE_YAZISI = {"INFO": "Bilgi", "WARNING": "Uyarı", "ERROR": "Hata"}

ZAMAN_SUTUNLARI = {"zaman"}        # ekran_zamani() değeri gösterenler; sütun ona göre genişler

SUTUNLAR = [("zaman", "Zaman", 140), ("seviye", "Seviye", 60),
            ("kaynak", "Kaynak", 70), ("mesaj", "Mesaj", 600)]

# Satır renkleri:
#   yeşil  = iş yolunda gitti ya da bilgi
#   sarı   = sorun var ama sistem kendi kendine tekrar deniyor, elin değmesin
#   kırmızı = elle müdahale gerekiyor (kamera arızası, gönderilemeyen kayıt, kalıcı M4 hatası)
SEVIYE_RENGI = {"INFO": "#e7f6ec", "WARNING": "#fff3cd", "ERROR": "#f8d7da"}
SEVIYE_YAZI_RENGI = {"INFO": "#15603a", "WARNING": "#7a5800", "ERROR": "#8a1020"}


# ---------- Veri (pencereden bağımsız, test edilebilir) ----------

def _like_deseni(eposta: str) -> str:
    r"""LIKE deseni; e-postadaki \ % _ karakterleri joker sayılmasın."""
    kacis = eposta.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{kacis}%"


def sahiplik_kosulu(kamera_kodlari: list[str] | None, eposta: str = "") -> tuple[str, tuple]:
    """Normal kullanıcıya gösterilecek satırların SQL koşulu ve değerleri.

    kamera_kodlari None ise (yönetici) koşul yoktur: bütün satırlar görünür.
    Görülecek kamerası da e-postası da olmayan kullanıcıya hiçbir satır gösterilmez.
    """
    if kamera_kodlari is None:
        return "", ()
    parcalar, degerler = [], []
    if kamera_kodlari:
        parcalar.append(f"kaynak IN ({', '.join('?' * len(kamera_kodlari))})")
        degerler.extend(kamera_kodlari)
    if eposta.strip():
        parcalar.append(r"(kaynak = ? AND lower(mesaj) LIKE ? ESCAPE '\')")
        degerler.extend((SISTEM_KAYNAGI, _like_deseni(eposta.strip().lower())))
    if not parcalar:
        return " AND 0", ()
    return " AND (" + " OR ".join(parcalar) + ")", tuple(degerler)


def olaylari_getir(seviyeler: tuple, son_id: int = 0, limit: int = EN_FAZLA,
                   kamera_kodlari: list[str] | None = None, eposta: str = "") -> list[dict]:
    """Eskiden yeniye sıralı, oturum sahibinin görebildiği olaylar.

    son_id = 0 : son `limit` olay (ilk yükleme)
    son_id > 0 : yalnızca bu id'den sonra gelen yeni olaylar
    kamera_kodlari = None : sınır yok (yönetici); liste ise yalnızca o kameralar
    """
    yer = ", ".join("?" * len(seviyeler))
    kosul, sahiplik_degerleri = sahiplik_kosulu(kamera_kodlari, eposta)
    nerede = f"WHERE seviye IN ({yer}){kosul}"
    with baglan() as db:
        if son_id:
            satirlar = db.execute(f"SELECT * FROM olaylar {nerede} AND id > ?"
                                  " ORDER BY id LIMIT ?",
                                  (*seviyeler, *sahiplik_degerleri, son_id, limit)).fetchall()
        else:
            satirlar = db.execute(f"SELECT * FROM olaylar {nerede}"
                                  " ORDER BY id DESC LIMIT ?",
                                  (*seviyeler, *sahiplik_degerleri, limit)).fetchall()[::-1]
    return [dict(s) for s in satirlar]


def satir_degerleri(o: dict) -> tuple:
    return (ekran_zamani(o["zaman"]), SEVIYE_YAZISI.get(o["seviye"], o["seviye"]),
            o["kaynak"], o["mesaj"])


# ---------- Sekme ----------

class LoglarSekmesi(ttk.Frame):
    """kodlari_al: görülebilecek kamera kodlarını döndüren işlev. None = hepsi (yönetici).

    Kamera listesi pencere açıkken değişebildiği (kamera eklenip silinebildiği) için kodlar
    her yenilemede yeniden sorulur.
    """

    def __init__(self, ust, kodlari_al=None, eposta: str = ""):
        super().__init__(ust, padding=10)
        self.kodlari_al = kodlari_al
        self.eposta = eposta
        self.son_id = 0
        self._kur()
        self._periyodik_yenile()

    def _kur(self):
        ust = ttk.Frame(self)
        ust.pack(fill="x", pady=(0, 8))
        ttk.Label(ust, text="Seviye").pack(side="left")
        self.seviye = tk.StringVar(value="Hepsi")
        kutu = ttk.Combobox(ust, textvariable=self.seviye, values=list(SEVIYE_SECENEKLERI),
                            state="readonly", width=14)
        kutu.pack(side="left", padx=(5, 15))
        kutu.bind("<<ComboboxSelected>>", lambda e: self.bastan_yukle())

        self.otomatik_kaydir = tk.BooleanVar(value=True)
        ttk.Checkbutton(ust, text="Otomatik kaydır", variable=self.otomatik_kaydir).pack(side="left")
        self.bilgi = ttk.Label(ust, text="")
        self.bilgi.pack(side="right")

        cerceve = ttk.Frame(self)
        cerceve.pack(fill="both", expand=True)
        self.liste = ttk.Treeview(cerceve, columns=[ad for ad, _, _ in SUTUNLAR],
                                  show="headings", height=15)
        for ad, baslik, genislik in SUTUNLAR:
            self.liste.heading(ad, text=baslik)
            self.liste.column(ad, width=tema.sutun_genisligi(
                baslik, genislik, tema.ZAMAN_ORNEGI if ad in ZAMAN_SUTUNLARI else ""),
                stretch=(ad == "mesaj"))
        for seviye, arka in SEVIYE_RENGI.items():
            self.liste.tag_configure(seviye, background=arka,
                                     foreground=SEVIYE_YAZI_RENGI[seviye])

        kaydirma = ttk.Scrollbar(cerceve, orient="vertical", command=self.liste.yview)
        self.liste.configure(yscrollcommand=kaydirma.set)
        self.liste.pack(side="left", fill="both", expand=True)
        kaydirma.pack(side="right", fill="y")

    def _sona_kaydir(self):
        satirlar = self.liste.get_children()
        if satirlar and self.otomatik_kaydir.get():
            self.liste.see(satirlar[-1])

    def bastan_yukle(self):
        """Filtre değişince liste baştan kurulur."""
        self.liste.delete(*self.liste.get_children())
        self.son_id = 0
        self.yenile()

    def yenile(self):
        """Yalnızca yeni olayları alta ekler; var olan satırlara (ve seçime) dokunmaz."""
        try:
            kodlar = self.kodlari_al() if self.kodlari_al else None
            yeniler = olaylari_getir(SEVIYE_SECENEKLERI[self.seviye.get()], self.son_id,
                                     kamera_kodlari=kodlar, eposta=self.eposta)
        except sqlite3.Error as e:
            self.bilgi.config(text=f"Veritabanı okunamadı ({type(e).__name__})", foreground="#b00020")
            return
        self.bilgi.config(text="", foreground="")

        for o in yeniler:
            self.liste.insert("", "end", iid=str(o["id"]), values=satir_degerleri(o),
                              tags=(o["seviye"],))
            self.son_id = o["id"]

        # Ekranda en çok EN_FAZLA satır kalsın; en eskiler silinir
        fazla = len(self.liste.get_children()) - EN_FAZLA
        if fazla > 0:
            self.liste.delete(*self.liste.get_children()[:fazla])

        if yeniler:
            self._sona_kaydir()

    def _periyodik_yenile(self):
        self.yenile()
        self._zamanlayici = self.after(YENILEME_MS, self._periyodik_yenile)

    def destroy(self):
        self.after_cancel(self._zamanlayici)
        super().destroy()
