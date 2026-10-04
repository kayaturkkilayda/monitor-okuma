"""Arayüzün Kayıtlar sekmesi: kayitlar tablosundaki gönderim kuyruğu ve geçmişi."""
import sqlite3
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image

from onizleme import onizleme_ac
from veritabani import baglan
from zaman import ekran_tarihini_coz, ekran_zamani

YENILEME_MS = 5000
EN_FAZLA = 500

HEPSI = "Hepsi"
DURUM_SECENEKLERI = {HEPSI: None, "Bekliyor": "bekliyor", "Gönderildi": "gonderildi", "Hatalı": "hatali"}
DURUM_YAZISI = {deger: yazi for yazi, deger in DURUM_SECENEKLERI.items() if deger}

# (sütun adı, başlık, genişlik)
SUTUNLAR = [("cekim", "Çekim zamanı", 140), ("tesis", "Tesis", 60), ("kamera", "Kamera", 70),
            ("yatak", "Yatak", 80), ("sira", "Sıra", 45), ("durum", "Durum", 85),
            ("deneme", "Deneme", 60), ("hata", "Son hata", 150), ("gonderim", "Gönderim zamanı", 140)]


# ---------- Veri (pencereden bağımsız, test edilebilir) ----------

def kayitlari_getir(baslangic: str | None = None, bitis: str | None = None,
                    kamera: str | None = None, durum: str | None = None,
                    limit: int = EN_FAZLA) -> list[dict]:
    """Filtrelere uyan kayıtları en yeni üstte döndürür.

    baslangic / bitis: "YYYY-MM-DD", ikisi de dahil. None olan filtre uygulanmaz.
    """
    kosullar, degerler = [], []
    if baslangic:
        kosullar.append("cekim_zamani >= ?")
        degerler.append(f"{baslangic} 00:00:00")
    if bitis:
        kosullar.append("cekim_zamani <= ?")
        degerler.append(f"{bitis} 23:59:59")
    if kamera:
        kosullar.append("kamera_kodu = ?")
        degerler.append(kamera)
    if durum:
        kosullar.append("durum = ?")
        degerler.append(durum)
    nerede = f" WHERE {' AND '.join(kosullar)}" if kosullar else ""
    with baglan() as db:
        satirlar = db.execute(f"SELECT * FROM kayitlar{nerede}"
                              " ORDER BY cekim_zamani DESC, sira DESC LIMIT ?",
                              (*degerler, limit)).fetchall()
    return [dict(s) for s in satirlar]


def kameralari_getir() -> list[str]:
    with baglan() as db:
        return [s[0] for s in db.execute("SELECT DISTINCT kamera_kodu FROM kayitlar ORDER BY 1")]


def satir_degerleri(k: dict) -> tuple:
    return (ekran_zamani(k["cekim_zamani"]), k["tesis_kodu"], k["kamera_kodu"], k["yatak_kodu"],
            k["sira"], DURUM_YAZISI.get(k["durum"], k["durum"]), k["deneme"],
            k["son_hata"] or "", ekran_zamani(k["gonderim_zamani"]))


def goruntu_bilgisi(k: dict) -> tuple[Path | None, str]:
    """(dosya yolu, None) ya da (None, kullanıcıya gösterilecek açıklama)."""
    yol = Path(k["dosya_yolu"])
    if yol.exists():
        return yol, ""
    if k["durum"] == "gonderildi":
        return None, "Görüntü gönderildikten sonra silindi."
    return None, f"Görüntü dosyası bulunamadı:\n{yol}"


# ---------- Sekme ----------

class KayitlarSekmesi(ttk.Frame):
    def __init__(self, ust):
        super().__init__(ust, padding=10)
        self.kayitlar = {}          # kayit_id → satır; çift tıklamada kullanılır
        self._filtreleri_kur()
        self._listeyi_kur()
        self._periyodik_yenile()

    def _filtreleri_kur(self):
        cerceve = ttk.Frame(self)
        cerceve.pack(fill="x", pady=(0, 8))

        self.baslangic = tk.StringVar()
        self.bitis = tk.StringVar()
        self.kamera = tk.StringVar(value=HEPSI)
        self.durum = tk.StringVar(value=HEPSI)

        ttk.Label(cerceve, text="Tarih").pack(side="left")
        for deger in (self.baslangic, self.bitis):
            alan = ttk.Entry(cerceve, textvariable=deger, width=11)
            alan.pack(side="left", padx=(5, 0))
            alan.bind("<Return>", lambda e: self.yenile())
            alan.bind("<FocusOut>", lambda e: self.yenile())
        ttk.Label(cerceve, text="(GG.AA.YYYY)", foreground="#777777").pack(side="left", padx=(5, 15))

        ttk.Label(cerceve, text="Kamera").pack(side="left")
        self.kamera_kutusu = ttk.Combobox(cerceve, textvariable=self.kamera, values=[HEPSI],
                                          state="readonly", width=10)
        self.kamera_kutusu.pack(side="left", padx=(5, 15))

        ttk.Label(cerceve, text="Durum").pack(side="left")
        durum_kutusu = ttk.Combobox(cerceve, textvariable=self.durum, state="readonly",
                                    values=list(DURUM_SECENEKLERI), width=11)
        durum_kutusu.pack(side="left", padx=(5, 15))

        for kutu in (self.kamera_kutusu, durum_kutusu):
            kutu.bind("<<ComboboxSelected>>", lambda e: self.yenile())

        self.bilgi = ttk.Label(cerceve, text="")
        self.bilgi.pack(side="right")

    def _listeyi_kur(self):
        cerceve = ttk.Frame(self)
        cerceve.pack(fill="both", expand=True)
        self.liste = ttk.Treeview(cerceve, columns=[ad for ad, _, _ in SUTUNLAR],
                                  show="headings", height=15)
        for ad, baslik, genislik in SUTUNLAR:
            self.liste.heading(ad, text=baslik)
            self.liste.column(ad, width=genislik)
        self.liste.tag_configure("bekliyor", background="#fff3cd")
        self.liste.tag_configure("hatali", background="#f8d7da")

        kaydirma = ttk.Scrollbar(cerceve, orient="vertical", command=self.liste.yview)
        self.liste.configure(yscrollcommand=kaydirma.set)
        self.liste.pack(side="left", fill="both", expand=True)
        kaydirma.pack(side="right", fill="y")
        self.liste.bind("<Double-1>", lambda e: self._goruntuyu_ac())

    def _filtreler(self) -> tuple[dict, str]:
        """(sorgu filtreleri, uyarı). Geçersiz tarih filtresi uygulanmaz, uyarı verilir."""
        uyari = ""
        tarihler = []
        for metin in (self.baslangic.get(), self.bitis.get()):
            tarih = ekran_tarihini_coz(metin) if metin.strip() else None
            if metin.strip() and tarih is None:
                uyari = "Tarih GG.AA.YYYY biçiminde olmalı"
            tarihler.append(tarih)
        kamera = self.kamera.get()
        return {"baslangic": tarihler[0], "bitis": tarihler[1],
                "kamera": None if kamera == HEPSI else kamera,
                "durum": DURUM_SECENEKLERI.get(self.durum.get())}, uyari

    def yenile(self):
        filtreler, uyari = self._filtreler()
        try:
            kayitlar = kayitlari_getir(**filtreler)
            self.kamera_kutusu["values"] = [HEPSI, *kameralari_getir()]
        except sqlite3.Error as e:
            # Veritabanı o an okunamıyorsa eski liste ekranda kalır
            self.bilgi.config(text=f"Veritabanı okunamadı ({type(e).__name__})", foreground="#b00020")
            return

        secili = self.liste.selection()
        odak = self.liste.focus()
        konum = self.liste.yview()[0]

        self.liste.delete(*self.liste.get_children())
        self.kayitlar = {k["kayit_id"]: k for k in kayitlar}
        for k in kayitlar:
            self.liste.insert("", "end", iid=k["kayit_id"], values=satir_degerleri(k),
                              tags=(k["durum"],))

        self.liste.selection_set([s for s in secili if self.liste.exists(s)])
        if odak and self.liste.exists(odak):
            self.liste.focus(odak)
        self.liste.yview_moveto(konum)

        metin = f"{len(kayitlar)} kayıt" + (f" (en yeni {EN_FAZLA})" if len(kayitlar) == EN_FAZLA else "")
        self.bilgi.config(text=uyari or metin, foreground="#b00020" if uyari else "")

    def _periyodik_yenile(self):
        self.yenile()
        self._zamanlayici = self.after(YENILEME_MS, self._periyodik_yenile)

    def destroy(self):
        self.after_cancel(self._zamanlayici)
        super().destroy()

    def _goruntuyu_ac(self):
        secili = self.liste.selection()
        if not secili or secili[0] not in self.kayitlar:
            return
        k = self.kayitlar[secili[0]]
        yol, aciklama = goruntu_bilgisi(k)
        if yol is None:
            messagebox.showinfo("Görüntü yok", aciklama)
            return
        try:
            with Image.open(yol) as goruntu:
                goruntu.load()
                onizleme_ac(self, goruntu, k["kayit_id"])
        except OSError as e:
            messagebox.showerror("Görüntü açılamadı", f"{yol}\n\n{type(e).__name__}")
