"""Arayüzün Kullanıcılar sekmesi (yalnızca yöneticiler görür): hesaplar ve yönetici yapma."""
from datetime import datetime
from tkinter import messagebox, ttk

import tema
import kullanicilar as ku
from veritabani import olay
from zaman import db_zamani, ekran_zamani

# Önce kişiyi tanıtan bilgiler (Ad, Rol), sonra kimlik ve durum
SUTUNLAR = [("ad", "Ad", 160), ("rol", "Rol", 90), ("eposta", "E-posta", 220),
            ("durum", "Durum", 120), ("son", "Son giriş", 140)]

ZAMAN_SUTUNLARI = {"son"}          # ekran_zamani() değeri gösterenler


def satir_degerleri(k: dict, simdi: str) -> tuple:
    if not k["dogrulandi"]:
        durum = "Doğrulanmadı"
    elif k["kilit_bitis"] and k["kilit_bitis"] > simdi:
        durum = "Kilitli"
    else:
        durum = "Aktif"
    return (k["ad"], "Yönetici" if k["yonetici"] else "Kullanıcı", k["eposta"], durum,
            ekran_zamani(k["son_giris"]))


class KullanicilarSekmesi(ttk.Frame):
    def __init__(self, ust, oturum: dict, log):
        super().__init__(ust, padding=10)
        self.oturum = oturum
        self.log = log
        self.liste = ttk.Treeview(self, columns=[ad for ad, _, _ in SUTUNLAR], show="headings", height=14)
        for ad, baslik, genislik in SUTUNLAR:
            self.liste.heading(ad, text=baslik)
            self.liste.column(ad, width=tema.sutun_genisligi(
                baslik, genislik, tema.ZAMAN_ORNEGI if ad in ZAMAN_SUTUNLARI else ""))
        self.liste.tag_configure("yonetici", background="#e7f1ff")
        self.liste.pack(fill="both", expand=True)

        alt = ttk.Frame(self)
        alt.pack(fill="x", pady=(10, 0))
        ttk.Button(alt, text="Yönetici yap", command=self._yonetici_yap).pack(side="left")
        ttk.Button(alt, text="Yenile", command=self.yenile).pack(side="left", padx=5)
        self.yenile()

    def yenile(self):
        secili = self.liste.selection()
        simdi = db_zamani(datetime.now())
        self.liste.delete(*self.liste.get_children())
        for k in ku.kullanicilari_listele():
            self.liste.insert("", "end", iid=k["eposta"], values=satir_degerleri(k, simdi),
                              tags=("yonetici",) if k["yonetici"] else ())
        self.liste.selection_set([s for s in secili if self.liste.exists(s)])

    def _yonetici_yap(self):
        secili = self.liste.selection()
        if not secili:
            messagebox.showinfo("Seçim yok", "Önce listeden bir kullanıcı seçin.", parent=self)
            return
        eposta = secili[0]
        if not messagebox.askyesno("Yönetici yap", f"{eposta} yönetici yapılsın mı?\n\n"
                                   "Yöneticiler ayarları ve diğer kullanıcıları değiştirebilir.",
                                   parent=self):
            return
        try:
            ku.yonetici_yap(eposta)
        except ku.KullaniciHatasi as e:
            messagebox.showerror("Yapılamadı", str(e), parent=self)
            return
        olay(self.log, "INFO", "sistem", f"{eposta} yönetici yapıldı — {self.oturum['eposta']}")
        self.yenile()
