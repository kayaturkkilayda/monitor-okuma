"""Arayüzün Ayarlar sekmesi."""
import copy
import re
import tkinter as tk
from tkinter import messagebox, ttk

from ayarlar import ayarlari_yaz, degisen_alanlar
from eposta_bolumu import EpostaBolumu
from telefon_sunucusu import VARSAYILAN_PORT as VARSAYILAN_TELEFON_PORT, sunucu_ayari
from kullanicilar import alan_adi_listesi
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


class AlanAdiListesi(ttk.Frame):
    """Kayıt için izin verilen alan adlarının dinamik listesi.

    Her satırda bir giriş alanı ve o satırı silen bir "−" düğmesi vardır; altta
    "+ Alan adı ekle" yeni satır açar. Liste boş bırakılırsa bütün geçerli
    e-posta alan adları kabul edilir (bkz. kullanicilar.alan_adi_izinli_mi).
    """

    BOS_UYARI = "Liste boşsa bütün geçerli e-posta adresleri kayıt olabilir."

    def __init__(self, ust, alanlar=None):
        super().__init__(ust)
        self.satirlar = []                      # [(çerçeve, StringVar)]
        self.satir_cercevesi = ttk.Frame(self)
        self.satir_cercevesi.grid(row=0, column=0, sticky="w")
        self.ekle_dugmesi = ttk.Button(self, text="+ Alan adı ekle", command=self.ekle)
        self.ekle_dugmesi.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.bilgi = ttk.Label(self, text="", foreground="#555555", font=("Segoe UI", 8))
        self.bilgi.grid(row=2, column=0, sticky="w")
        for alan in alan_adi_listesi(alanlar):
            self.ekle(alan)
        self._bilgi_guncelle()

    def ekle(self, alan: str = ""):
        satir = ttk.Frame(self.satir_cercevesi)
        satir.pack(anchor="w", pady=1)
        deger = tk.StringVar(value=alan)
        giris = ttk.Entry(satir, textvariable=deger, width=40)
        giris.pack(side="left")
        kayit = (satir, deger)
        ttk.Button(satir, text="−", width=3,
                   command=lambda k=kayit: self.sil(k)).pack(side="left", padx=(4, 0))
        self.satirlar.append(kayit)
        self._bilgi_guncelle()
        return giris

    def sil(self, kayit):
        if kayit in self.satirlar:
            self.satirlar.remove(kayit)
            kayit[0].destroy()
            self._bilgi_guncelle()

    def _bilgi_guncelle(self):
        self.bilgi.config(text="" if self.degerler() else self.BOS_UYARI)

    def degerler(self) -> list[str]:
        """Girilen alan adları: kırpılmış, küçük harfe çevrilmiş, @'siz ve tekrarsız."""
        return alan_adi_listesi(d.get() for _, d in self.satirlar)

    def dogrula(self) -> tuple[list[str] | None, str | None]:
        """(alan adları, None) ya da (None, hata mesajı). Boş satırlar sessizce atılır."""
        alanlar = self.degerler()
        for alan in alanlar:
            if not _ALAN_ADI.match(alan):
                return None, (f"'{alan}' geçerli bir alan adı değil; örneğin akgun.com.tr "
                              "biçiminde olmalı (@ olmadan).")
        return alanlar, None


class AyarSekmesi(ttk.Frame):
    def __init__(self, ust, ayarlar: dict, oturum: dict | None = None, log=None):
        """oturum: giriş yapan kullanıcı.

        Sekme yalnızca yöneticiye gösterilir (bkz. arayuz.Uygulama). Yine de yönetici
        olmayan bir oturumla açılırsa alanlar kapatılır ve kaydetme reddedilir.
        """
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

        ttk.Label(self, text="Kayıt için izin verilen\nalan adları").grid(
            row=len(SATIRLAR), column=0, sticky="nw", pady=5, padx=(0, 15))
        self.alan_adlari = AlanAdiListesi(self, ayarlar.get("izin_verilen_alan_adi"))
        self.alan_adlari.grid(row=len(SATIRLAR), column=1, sticky="w", pady=5)

        self.sil = tk.BooleanVar(value=ayarlar.get("gonderilince_sil", True))
        ttk.Checkbutton(self, text="Gönderilen görüntüleri hemen sil",
                        variable=self.sil).grid(row=len(SATIRLAR) + 1, column=1, sticky="w", pady=5)

        # Telefondan fotoğraf yükleme: varsayılan kapalı, çünkü bilgisayarı ağa açar
        telefon = sunucu_ayari(ayarlar)
        self.telefon_acik = tk.BooleanVar(value=telefon["acik"])
        self.telefon_port = tk.StringVar(value=str(telefon["port"]))
        kutu = ttk.Frame(self)
        kutu.grid(row=len(SATIRLAR) + 2, column=1, sticky="w", pady=5)
        ttk.Checkbutton(kutu, text="Telefondan fotoğraf yüklemeyi aç",
                        variable=self.telefon_acik).pack(side="left")
        ttk.Label(kutu, text="Port").pack(side="left", padx=(12, 4))
        ttk.Entry(kutu, textvariable=self.telefon_port, width=7).pack(side="left")

        ttk.Button(self, text="Kaydet", command=self._kaydet).grid(
            row=len(SATIRLAR) + 3, column=1, sticky="w", pady=(15, 0))

        # Bildirimler, ayarları kaydeden yöneticinin adresine gider; ayrıca sorulmaz
        self.eposta = EpostaBolumu(self, ayarlar.get("smtp"), self.oturum.get("eposta", ""))
        self.eposta.grid(row=0, column=2, rowspan=len(SATIRLAR) + 4, sticky="nw", padx=(25, 0))

        if not self.yonetici:
            salt_okunur_yap(self)
            ttk.Label(self, text=YETKI_YOK, foreground="#b00020").grid(
                row=len(SATIRLAR) + 4, column=1, sticky="w", pady=(10, 0))

    def _dogrula(self):
        """(yeni ayarlar, None) ya da (None, hata mesajı) döndürür."""
        if not self.yonetici:            # arayüzden bağımsız, fonksiyon seviyesinde yetki kontrolü
            return None, YETKI_YOK
        d = {ad: v.get().strip() for ad, v in self.degerler.items()}

        if not d["tesis_kodu"]:
            return None, "Tesis kodu boş olamaz."
        if d["api_url"] and not d["api_url"].startswith(("http://", "https://")):
            return None, "API adresi http:// veya https:// ile başlamalı (ya da boş bırakılmalı)."
        alanlar, hata = self.alan_adlari.dogrula()
        if hata:
            return None, hata
        d["izin_verilen_alan_adi"] = alanlar

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

        try:
            port = int(self.telefon_port.get().strip() or VARSAYILAN_TELEFON_PORT)
        except ValueError:
            return None, "Telefon yükleme portu bir tam sayı olmalı."
        if not 1024 <= port <= 65535:
            return None, "Telefon yükleme portu 1024 ile 65535 arasında olmalı."

        return {**d, **sayilar, "gonderilince_sil": self.sil.get(), "smtp": smtp,
                "telefon_yukleme": {"acik": self.telefon_acik.get(), "port": port}}, None

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