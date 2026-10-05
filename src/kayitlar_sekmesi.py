"""Arayüzün Kayıtlar sekmesi: kayitlar tablosundaki gönderim kuyruğu ve geçmişi.

İki görünüm: "Günlere göre" (gün → kamera → kayıt ağacı) ve düz "Liste".
Ağaçta gün ve kamera özetleri SQL'de gruplanarak sayılır; bir kameranın kayıtları yalnızca
o düğüm açıldığında yüklenir. Yenilemede ağaç baştan kurulmaz, yalnızca değişen düğümler
güncellenir; açık düğümler ve seçim yerinde kalır.
"""
import os
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
GORUNTU_KLASORU = Path("goruntuler")

HEPSI = "Hepsi"
DURUM_SECENEKLERI = {HEPSI: None, "Bekliyor": "bekliyor", "Gönderildi": "gonderildi", "Hatalı": "hatali"}
DURUM_YAZISI = {deger: yazi for yazi, deger in DURUM_SECENEKLERI.items() if deger}
GUNLERE_GORE, LISTE = "Günlere göre", "Liste"

# (sütun adı, başlık, genişlik)
SUTUNLAR = [("cekim", "Çekim zamanı", 140), ("tesis", "Tesis", 60), ("kamera", "Kamera", 70),
            ("yatak", "Yatak", 80), ("sira", "Sıra", 45), ("durum", "Durum", 85),
            ("deneme", "Deneme", 60), ("hata", "Son hata", 150), ("gonderim", "Gönderim zamanı", 140)]

YER_TUTUCU = "…"     # kapalı düğümün altındaki "yükleniyor" satırının öneki


# ---------- Veri (pencereden bağımsız, test edilebilir) ----------

def _kosullar(baslangic=None, bitis=None, kamera=None, durum=None, gun=None, yatak=None):
    """Filtrelerden WHERE cümlesi ve değerleri. Tarihler "YYYY-MM-DD", ikisi de dahil."""
    kosullar, degerler = [], []
    if gun:
        baslangic = bitis = gun
    if baslangic:
        kosullar.append("cekim_zamani >= ?")
        degerler.append(f"{baslangic} 00:00:00")
    if bitis:
        kosullar.append("cekim_zamani <= ?")
        degerler.append(f"{bitis} 23:59:59")
    for sutun, deger in (("kamera_kodu", kamera), ("yatak_kodu", yatak), ("durum", durum)):
        if deger:
            kosullar.append(f"{sutun} = ?")
            degerler.append(deger)
    return (f" WHERE {' AND '.join(kosullar)}" if kosullar else ""), degerler


def kayitlari_getir(baslangic: str | None = None, bitis: str | None = None,
                    kamera: str | None = None, durum: str | None = None,
                    limit: int = EN_FAZLA) -> list[dict]:
    """Düz liste: filtrelere uyan kayıtlar en yeni üstte, en çok limit tane."""
    nerede, degerler = _kosullar(baslangic, bitis, kamera, durum)
    with baglan() as db:
        satirlar = db.execute(f"SELECT * FROM kayitlar{nerede}"
                              " ORDER BY cekim_zamani DESC, sira DESC LIMIT ?",
                              (*degerler, limit)).fetchall()
    return [dict(s) for s in satirlar]


_SAYIMLAR = ("COUNT(*) AS toplam, SUM(durum = 'gonderildi') AS gonderildi,"
             " SUM(durum = 'bekliyor') AS bekliyor, SUM(durum = 'hatali') AS hatali")


def gun_ozetleri(baslangic=None, bitis=None, kamera=None, durum=None) -> list[dict]:
    """Her gün için kayıt sayıları; en yeni gün en üstte. Sayımı SQL yapar."""
    nerede, degerler = _kosullar(baslangic, bitis, kamera, durum)
    with baglan() as db:
        return [dict(s) for s in db.execute(
            f"SELECT substr(cekim_zamani, 1, 10) AS gun, {_SAYIMLAR} FROM kayitlar{nerede}"
            " GROUP BY gun ORDER BY gun DESC", degerler)]


def kamera_ozetleri(gun: str, kamera=None, durum=None, **_) -> list[dict]:
    """Bir günün kamera/yatak bazında kayıt sayıları."""
    nerede, degerler = _kosullar(kamera=kamera, durum=durum, gun=gun)
    with baglan() as db:
        return [dict(s) for s in db.execute(
            f"SELECT kamera_kodu, yatak_kodu, {_SAYIMLAR} FROM kayitlar{nerede}"
            " GROUP BY kamera_kodu, yatak_kodu ORDER BY kamera_kodu, yatak_kodu", degerler)]


def gun_kayitlari(gun: str, kamera: str, yatak: str, durum=None, **_) -> list[dict]:
    """Bir kameranın o günkü kayıtları, en yeni üstte (düğüm açıldığında yüklenir)."""
    nerede, degerler = _kosullar(kamera=kamera, yatak=yatak, durum=durum, gun=gun)
    with baglan() as db:
        return [dict(s) for s in db.execute(
            f"SELECT * FROM kayitlar{nerede} ORDER BY cekim_zamani DESC, sira DESC", degerler)]


def kameralari_getir() -> list[str]:
    with baglan() as db:
        return [s[0] for s in db.execute("SELECT DISTINCT kamera_kodu FROM kayitlar ORDER BY 1")]


def sayi(n: int) -> str:
    """2880 → '2.880'"""
    return f"{n:,}".replace(",", ".")


def _durum_ozeti(o: dict) -> str:
    parcalar = [f"{sayi(o['toplam'])} kayıt"]
    for alan, yazi in (("gonderildi", "gönderildi"), ("bekliyor", "bekliyor"), ("hatali", "hatalı")):
        if o[alan]:
            parcalar.append(f"{sayi(o[alan])} {yazi}")
    return ", ".join(parcalar)


def gun_metni(o: dict) -> str:
    """'02.10.2026 — 2.880 kayıt, 2.875 gönderildi, 5 bekliyor'"""
    return f"{ekran_zamani(o['gun'] + ' 00:00:00')[:10]} — {_durum_ozeti(o)}"


def kamera_metni(o: dict) -> str:
    """'K1 → Y1 — 288 kayıt' (bekleyen/hatalı varsa onlar da)"""
    ek = "".join(f", {sayi(o[a])} {y}" for a, y in (("bekliyor", "bekliyor"), ("hatali", "hatalı")) if o[a])
    return f"{o['kamera_kodu']} → {o['yatak_kodu']} — {sayi(o['toplam'])} kayıt{ek}"


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


def klasor_bilgisi(gun: str, yatak: str | None = None) -> tuple[Path | None, str]:
    """Günün (ya da o günkü yatağın) görüntü klasörü: (yol, '') ya da (None, açıklama)."""
    yol = GORUNTU_KLASORU / gun / yatak if yatak else GORUNTU_KLASORU / gun
    if not yol.is_dir():
        return None, (f"Bu {'yatağın' if yatak else 'günün'} görüntü klasörü yok.\n\n"
                      "Görüntüler gönderildikten sonra silinmiş olabilir.\n\n" + str(yol))
    if not any(p.is_file() for p in yol.rglob("*")):
        return None, ("Klasörde hiç görüntü kalmamış; görüntüler gönderildikten sonra silinmiş.\n\n"
                      + str(yol))
    return yol, ""


# ---------- Ağaç düğüm kimlikleri ----------

def gun_kimligi(gun: str) -> str:
    return f"g|{gun}"


def kamera_kimligi(gun: str, kamera: str, yatak: str) -> str:
    return f"k|{gun}|{kamera}|{yatak}"


def kayit_kimligi(kayit_id: str) -> str:
    return f"r|{kayit_id}"


def kimligi_coz(iid: str) -> tuple[str, list[str]]:
    tur, *parcalar = iid.split("|")
    return tur, parcalar


# ---------- Sekme ----------

class KayitlarSekmesi(ttk.Frame):
    def __init__(self, ust):
        super().__init__(ust, padding=10)
        self.kayitlar = {}          # kayit_id → satır; çift tıklamada kullanılır
        self.ozet_imzasi = {}       # açık kamera düğümü → son yüklenen özet (değişmediyse yeniden yüklenmez)
        self.gorunen = {}           # ağaç düğümü → ekranda yazan (metin, değerler, etiketler)
        self.gorunum = tk.StringVar(value=GUNLERE_GORE)
        self._filtreleri_kur()
        self.icerik = ttk.Frame(self)
        self.icerik.pack(fill="both", expand=True)
        self._agaci_kur()
        self._listeyi_kur()
        self._gorunumu_degistir()
        self._periyodik_yenile()

    # ---------- Kurulum ----------

    def _filtreleri_kur(self):
        ust = ttk.Frame(self)
        ust.pack(fill="x", pady=(0, 6))
        for secenek in (GUNLERE_GORE, LISTE):
            ttk.Radiobutton(ust, text=secenek, value=secenek, variable=self.gorunum,
                            command=self._gorunumu_degistir).pack(side="left", padx=(0, 10))
        self.klasor_dugmesi = ttk.Button(ust, text="Klasörü aç", command=self._klasoru_ac,
                                         state="disabled")
        self.klasor_dugmesi.pack(side="left", padx=(10, 0))

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

    def _kaydirmali(self, agac: ttk.Treeview) -> ttk.Frame:
        cerceve = agac.master
        kaydirma = ttk.Scrollbar(cerceve, orient="vertical", command=agac.yview)
        agac.configure(yscrollcommand=kaydirma.set)
        agac.pack(side="left", fill="both", expand=True)
        kaydirma.pack(side="right", fill="y")
        agac.tag_configure("bekliyor", background="#fff3cd")
        agac.tag_configure("hatali", background="#f8d7da")
        return cerceve

    def _agaci_kur(self):
        cerceve = ttk.Frame(self.icerik)
        self.agac = ttk.Treeview(cerceve, columns=[ad for ad, _, _ in SUTUNLAR],
                                 show="tree headings", height=15)
        self.agac.heading("#0", text="Gün / kamera")
        self.agac.column("#0", width=330, stretch=False)
        for ad, baslik, genislik in SUTUNLAR:
            self.agac.heading(ad, text=baslik)
            self.agac.column(ad, width=genislik)
        self.agac.tag_configure("gun", font=("Segoe UI", 9, "bold"))
        self.agac_cercevesi = self._kaydirmali(self.agac)
        self.agac.bind("<<TreeviewOpen>>", lambda e: self._dugum_acildi(self.agac.focus()))
        self.agac.bind("<<TreeviewClose>>", lambda e: self.ozet_imzasi.pop(self.agac.focus(), None))
        self.agac.bind("<<TreeviewSelect>>", lambda e: self._klasor_dugmesini_guncelle())
        self.agac.bind("<Double-1>", lambda e: self._goruntuyu_ac(self.agac))

    def _listeyi_kur(self):
        cerceve = ttk.Frame(self.icerik)
        self.liste = ttk.Treeview(cerceve, columns=[ad for ad, _, _ in SUTUNLAR],
                                  show="headings", height=15)
        for ad, baslik, genislik in SUTUNLAR:
            self.liste.heading(ad, text=baslik)
            self.liste.column(ad, width=genislik)
        self.liste_cercevesi = self._kaydirmali(self.liste)
        self.liste.bind("<Double-1>", lambda e: self._goruntuyu_ac(self.liste))

    def _gorunumu_degistir(self):
        agac_mi = self.gorunum.get() == GUNLERE_GORE
        (self.liste_cercevesi if agac_mi else self.agac_cercevesi).pack_forget()
        (self.agac_cercevesi if agac_mi else self.liste_cercevesi).pack(fill="both", expand=True)
        self._klasor_dugmesini_guncelle()
        self.yenile()

    # ---------- Filtreler ----------

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

    # ---------- Yenileme ----------

    def yenile(self):
        filtreler, uyari = self._filtreler()
        try:
            self.kamera_kutusu["values"] = [HEPSI, *kameralari_getir()]
            if self.gorunum.get() == GUNLERE_GORE:
                metin = self._agaci_yenile(filtreler)
            else:
                metin = self._listeyi_yenile(filtreler)
        except sqlite3.Error as e:
            # Veritabanı o an okunamıyorsa eski görünüm ekranda kalır
            self.bilgi.config(text=f"Veritabanı okunamadı ({type(e).__name__})", foreground="#b00020")
            return
        self.bilgi.config(text=uyari or metin, foreground="#b00020" if uyari else "")

    def _listeyi_yenile(self, filtreler: dict) -> str:
        kayitlar = kayitlari_getir(**filtreler)
        secili, odak, konum = self.liste.selection(), self.liste.focus(), self.liste.yview()[0]
        self.liste.delete(*self.liste.get_children())
        self.kayitlar = {k["kayit_id"]: k for k in kayitlar}
        for k in kayitlar:
            self.liste.insert("", "end", iid=k["kayit_id"], values=satir_degerleri(k), tags=(k["durum"],))
        self.liste.selection_set([s for s in secili if self.liste.exists(s)])
        if odak and self.liste.exists(odak):
            self.liste.focus(odak)
        self.liste.yview_moveto(konum)
        return f"{len(kayitlar)} kayıt" + (f" (en yeni {EN_FAZLA})" if len(kayitlar) == EN_FAZLA else "")

    def _esitle(self, ust: str, istenen: list[tuple]):
        """ust düğümünün çocuklarını istenen [(iid, metin, değerler, etiketler, alt_var_mi)] ile eşitler.

        Var olan düğümler silinip yeniden eklenmez (açık/seçili kalırlar); yalnızca yazıları
        güncellenir, eksikler eklenir, artık olmayanlar silinir, sıra düzeltilir.
        """
        istenen_kimlikler = {i[0] for i in istenen}
        kalanlar = []
        for cocuk in self.agac.get_children(ust):
            if cocuk in istenen_kimlikler:
                kalanlar.append(cocuk)
            else:
                self.ozet_imzasi.pop(cocuk, None)
                self.gorunen.pop(cocuk, None)
                self.agac.delete(cocuk)
        # Var olanların sırası bozulduysa (normalde bozulmaz) hepsi yeniden dizilir
        var_olanlar = set(kalanlar)
        sira_bozuk = kalanlar != [i[0] for i in istenen if i[0] in var_olanlar]
        for sira, (iid, metin, degerler, etiketler, alt_var) in enumerate(istenen):
            gorunum = (metin, degerler, etiketler)
            if iid in var_olanlar:
                if self.gorunen.get(iid) != gorunum:          # yalnızca değişen satıra dokunulur
                    self.agac.item(iid, text=metin, values=degerler, tags=etiketler)
                if sira_bozuk:
                    self.agac.move(iid, ust, sira)
            else:
                self.agac.insert(ust, sira, iid=iid, text=metin, values=degerler, tags=etiketler)
                if alt_var:      # açılabilsin diye yer tutucu; asıl içerik açılınca yüklenir
                    self.agac.insert(iid, "end", iid=f"{YER_TUTUCU}{iid}", text="yükleniyor…")
            self.gorunen[iid] = gorunum

    def _agaci_yenile(self, filtreler: dict) -> str:
        self._filtre = filtreler
        gunler = gun_ozetleri(**filtreler)
        self._esitle("", [(gun_kimligi(o["gun"]), gun_metni(o), (), ("gun",), True) for o in gunler])
        for o in gunler:
            iid = gun_kimligi(o["gun"])
            if self.agac.item(iid, "open"):
                self._gunu_doldur(o["gun"])
        toplam = sum(o["toplam"] for o in gunler)
        return f"{len(gunler)} gün, {sayi(toplam)} kayıt"

    def _dugum_acildi(self, iid: str):
        tur, parcalar = kimligi_coz(iid)
        if tur == "g":
            self._gunu_doldur(parcalar[0])
        elif tur == "k":
            self._kamerayi_doldur(*parcalar, zorla=True)

    def _gunu_doldur(self, gun: str):
        kameralar = kamera_ozetleri(gun, **self._filtre)
        self._esitle(gun_kimligi(gun), [
            (kamera_kimligi(gun, o["kamera_kodu"], o["yatak_kodu"]), kamera_metni(o), (), (), True)
            for o in kameralar])
        for o in kameralar:
            iid = kamera_kimligi(gun, o["kamera_kodu"], o["yatak_kodu"])
            if self.agac.item(iid, "open"):
                self._kamerayi_doldur(gun, o["kamera_kodu"], o["yatak_kodu"], ozet=o)

    def _kamerayi_doldur(self, gun: str, kamera: str, yatak: str, ozet: dict | None = None,
                         zorla: bool = False):
        """Kameranın o günkü kayıtlarını yükler; sayıları değişmediyse yeniden yüklemez."""
        iid = kamera_kimligi(gun, kamera, yatak)
        imza = tuple(ozet.values()) if ozet else None
        if not zorla and imza is not None and self.ozet_imzasi.get(iid) == imza:
            return
        # Gün ve kamera düğümün kendisinden gelir; filtrelerden yalnızca durum kalır
        kayitlar = gun_kayitlari(gun, kamera, yatak, durum=self._filtre["durum"])
        self.kayitlar.update({k["kayit_id"]: k for k in kayitlar})
        self._esitle(iid, [(kayit_kimligi(k["kayit_id"]), "", satir_degerleri(k), (k["durum"],), False)
                           for k in kayitlar])
        if imza is None:
            o = next((x for x in kamera_ozetleri(gun, **self._filtre)
                      if (x["kamera_kodu"], x["yatak_kodu"]) == (kamera, yatak)), None)
            imza = tuple(o.values()) if o else None
        self.ozet_imzasi[iid] = imza

    def _periyodik_yenile(self):
        self.yenile()
        self._zamanlayici = self.after(YENILEME_MS, self._periyodik_yenile)

    def destroy(self):
        self.after_cancel(self._zamanlayici)
        super().destroy()

    # ---------- Düğmeler ----------

    def _secili_klasor(self) -> tuple[str, str | None] | None:
        """Seçili gün ya da kamera düğümünün (gün, yatak); başka bir şey seçiliyse None."""
        if self.gorunum.get() != GUNLERE_GORE or not self.agac.selection():
            return None
        tur, parcalar = kimligi_coz(self.agac.selection()[0])
        if tur == "g":
            return parcalar[0], None
        if tur == "k":
            return parcalar[0], parcalar[2]
        return None

    def _klasor_dugmesini_guncelle(self):
        self.klasor_dugmesi.config(state="normal" if self._secili_klasor() else "disabled")

    def _klasoru_ac(self):
        secim = self._secili_klasor()
        if secim is None:
            return
        yol, aciklama = klasor_bilgisi(*secim)
        if yol is None:
            messagebox.showinfo("Klasör yok", aciklama, parent=self)
            return
        os.startfile(yol.resolve())          # Windows Dosya Gezgini'nde açar

    def _goruntuyu_ac(self, agac: ttk.Treeview | None = None):
        if agac is None:
            agac = self.agac if self.gorunum.get() == GUNLERE_GORE else self.liste
        secili = agac.selection()
        if not secili:
            return
        kayit_id = secili[0][2:] if secili[0].startswith("r|") else secili[0]
        if kayit_id not in self.kayitlar:
            return                           # gün/kamera düğümünde çift tıklama: aç/kapa yeterli
        k = self.kayitlar[kayit_id]
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
