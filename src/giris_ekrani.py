"""Giriş penceresi: ilk yönetici, giriş, kayıt, e-posta kodu ve şifre sıfırlama ekranları.

Doğrulama kodları buradan doğrudan gönderilir (kullanıcı ekranda bekliyor); motorun
bildirim kuyruğu kullanılmaz. Kodlar ve şifreler hiçbir log, olay ya da mesajda yer almaz.
"""
import tkinter as tk
from tkinter import ttk

import kullanicilar as ku
import oturum
from arka_plan import arka_planda
from eposta_girisi import EpostaGirisi, oneri_alanlari
from bildirim import gonder, smtp_hazir_mi
from veritabani import olay

YESIL, KIRMIZI = "#1e7e34", "#b00020"
SMTP_YOK = "E-posta ayarları yapılmamış, yöneticinize başvurun."


class GirisEkrani(ttk.Frame):
    """girildi(kullanici) başarılı girişte çağrılır.

    ayarlari_getir() her işlemde güncel ayarları döndürür (SMTP ve izin verilen alan adı
    giriş penceresi açıkken yönetici tarafından değiştirilmiş olabilir).
    """

    def __init__(self, ust, ayarlari_getir, girildi, log):
        super().__init__(ust, padding=25)
        self.ayarlari_getir = ayarlari_getir
        self.girildi = girildi
        self.log = log
        self.eposta = ""                     # kod ekranlarında hangi hesap için çalışıldığı
        self.ekranlar, self.alanlar, self.mesajlar, self.dugmeler = {}, {}, {}, {}
        self.girisler, self.goster_kutusu = {}, {}
        self.hatirla = tk.BooleanVar(value=True)

        self._ekran("ilk", "İlk yönetici hesabını oluştur",
                    "Henüz hiç kullanıcı yok. Bu hesap yönetici olacak.",
                    [("eposta", "E-posta"), ("ad", "Ad soyad"), ("sifre", "Şifre"), ("tekrar", "Şifre (tekrar)")],
                    ("Hesabı oluştur", self._ilk_yonetici), [])
        self._ekran("giris", "Giriş", "", [("eposta", "E-posta"), ("sifre", "Şifre")],
                    ("Giriş yap", self._giris),
                    [("Kayıt ol", lambda: self.goster("kayit")),
                     ("Şifremi unuttum", self._unuttum_ac)])
        self._ekran("kayit", "Kayıt ol", "E-posta adresinize 6 haneli bir doğrulama kodu gönderilecek.",
                    [("eposta", "E-posta"), ("ad", "Ad soyad"), ("sifre", "Şifre"), ("tekrar", "Şifre (tekrar)")],
                    ("Kod gönder", self._kayit), [("Girişe dön", lambda: self.goster("giris"))])
        self._ekran("kayit_kod", "E-posta doğrulama", "E-postanıza gelen 6 haneli kodu girin (10 dakika geçerli).",
                    [("kod", "Kod")], ("Doğrula", self._kayit_dogrula),
                    [("Girişe dön", lambda: self.goster("giris"))])
        self._ekran("unuttum", "Şifremi unuttum", "Hesabınızın e-posta adresine kod gönderilecek.",
                    [("eposta", "E-posta")], ("Kod gönder", self._sifirlama_baslat),
                    [("Girişe dön", lambda: self.goster("giris"))])
        self._ekran("sifirla", "Yeni şifre", "E-postanıza gelen kodu ve yeni şifrenizi girin.",
                    [("kod", "Kod"), ("sifre", "Yeni şifre"), ("tekrar", "Yeni şifre (tekrar)")],
                    ("Şifreyi değiştir", self._sifre_sifirla), [("Girişe dön", lambda: self.goster("giris"))])

        try:
            self.goster("giris" if ku.kullanici_var_mi() else "ilk")
        except Exception as e:
            self.goster("giris")
            self.mesaj("giris", f"Veritabanı açılamadı ({type(e).__name__}).", hata=True)

    # ---------- Ekran kurulumu ----------

    def _ekran(self, ad, baslik, aciklama, alanlar, ana_dugme, diger_dugmeler):
        cerceve = ttk.Frame(self)
        ttk.Label(cerceve, text=baslik, font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        ttk.Label(cerceve, text=aciklama, foreground="#555555", wraplength=380).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))
        degerler, girisler = {}, {}
        for i, (alan, etiket) in enumerate(alanlar, start=2):
            ttk.Label(cerceve, text=etiket).grid(row=i, column=0, sticky="nw", pady=4, padx=(0, 12))
            deger = tk.StringVar()
            if alan == "eposta":
                # Yazarken biçim denetimi ve @'den sonrası için alan adı önerileri
                kutu = EpostaGirisi(cerceve, deger, lambda e=ad: self._oneri_alanlari(e))
                kutu.grid(row=i, column=1, sticky="w", pady=4)
                giris = kutu.giris
            else:
                giris = ttk.Entry(cerceve, textvariable=deger, width=34,
                                  show="*" if alan in ("sifre", "tekrar") else "")
                giris.grid(row=i, column=1, sticky="w", pady=4)
            giris.bind("<Return>", lambda e, f=ana_dugme[1]: f())
            degerler[alan], girisler[alan] = deger, giris
        satir = len(alanlar) + 2
        if "sifre" in degerler:
            secenekler = ttk.Frame(cerceve)
            secenekler.grid(row=satir, column=1, sticky="w")
            goster = tk.BooleanVar(value=False)
            ttk.Checkbutton(secenekler, text="Şifreyi göster", variable=goster,
                            command=lambda e=ad: self._sifreyi_goster(e)).pack(side="left")
            self.goster_kutusu[ad] = goster
            if ad == "giris":
                ttk.Checkbutton(secenekler, text="Beni hatırla", variable=self.hatirla).pack(
                    side="left", padx=(12, 0))
            satir += 1
        dugme = ttk.Button(cerceve, text=ana_dugme[0], command=ana_dugme[1])
        dugme.grid(row=satir, column=1, sticky="w", pady=(10, 0))
        alt = ttk.Frame(cerceve)
        alt.grid(row=satir + 1, column=1, sticky="w", pady=(6, 0))
        for metin, komut in diger_dugmeler:
            ttk.Button(alt, text=metin, command=komut).pack(side="left", padx=(0, 6))
        mesaj = ttk.Label(cerceve, text="", wraplength=380, justify="left")
        mesaj.grid(row=satir + 2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.ekranlar[ad], self.alanlar[ad], self.mesajlar[ad], self.dugmeler[ad] = \
            cerceve, degerler, mesaj, (dugme, ana_dugme[0])
        self.girisler[ad] = girisler

    def _oneri_alanlari(self, ekran: str) -> list[str]:
        izinli = (self.ayarlari_getir() or {}).get("izin_verilen_alan_adi")
        # Kayıtta yalnızca izin verilen alan adı önerilir; diğerleri zaten kabul edilmez
        return oneri_alanlari(izinli, yalnizca_izinli=(ekran == "kayit"))

    def _sifreyi_goster(self, ekran: str):
        goster = self.goster_kutusu[ekran].get()
        for alan in ("sifre", "tekrar"):
            if alan in self.girisler[ekran]:
                self.girisler[ekran][alan].config(show="" if goster else "*")

    def _unuttum_ac(self):
        """Girişte yazılmış e-posta, şifremi unuttum ekranına taşınır."""
        eposta = self.deger("giris", "eposta")
        self.goster("unuttum")
        if eposta:
            self.alanlar["unuttum"]["eposta"].set(eposta)

    def goster(self, ad: str):
        for cerceve in self.ekranlar.values():
            cerceve.pack_forget()
        self.ekranlar[ad].pack(fill="both", expand=True)
        self.aktif = ad
        self.mesaj(ad, "")
        for alan in ("sifre", "tekrar", "kod"):          # önceki girişten şifre/kod ekranda kalmasın
            if alan in self.alanlar[ad]:
                self.alanlar[ad][alan].set("")
        if ad in self.goster_kutusu:                     # ekrana her gelişte şifreler yine gizli
            self.goster_kutusu[ad].set(False)
            self._sifreyi_goster(ad)
        if ad in ("kayit", "unuttum"):
            hazir = smtp_hazir_mi((self.ayarlari_getir() or {}).get("smtp"))
            self._dugme_durumu(ad, hazir)
            if not hazir:
                self.mesaj(ad, SMTP_YOK, hata=True)

    def deger(self, ekran: str, alan: str) -> str:
        return self.alanlar[ekran][alan].get()

    def mesaj(self, ekran: str, metin: str, hata: bool = False):
        self.mesajlar[ekran].config(text=metin, foreground=KIRMIZI if hata else YESIL)

    def _dugme_durumu(self, ekran: str, acik: bool, metin: str | None = None):
        dugme, asil = self.dugmeler[ekran]
        dugme.config(state="normal" if acik else "disabled", text=metin or asil)

    def _olay(self, seviye: str, mesaj: str):
        olay(self.log, seviye, "sistem", mesaj)

    # ---------- Kod e-postası ----------

    def _kod_gonder(self, ekran: str, eposta: str, amac: str, kod: str | None, basarida):
        """Kodu arka planda e-postayla gönderir; pencere donmaz. Kod başka hiçbir yere yazılmaz."""
        smtp = (self.ayarlari_getir() or {}).get("smtp")
        if not smtp_hazir_mi(smtp):
            self.mesaj(ekran, SMTP_YOK, hata=True)
            return
        if kod is None:              # kayıtlı olmayan adres: bilerek aynı sonuç gösterilir
            basarida()
            return
        self._dugme_durumu(ekran, False, "Gönderiliyor...")
        konu, metin = ku.kod_maili(amac, kod)

        def gonderim():
            try:
                gonder(smtp, [eposta], konu, metin)
                return None
            except Exception as e:
                return type(e).__name__

        arka_planda(self, gonderim, lambda hata: self._kod_sonucu(ekran, hata, basarida))

    def _kod_sonucu(self, ekran: str, hata: str | None, basarida):
        self._dugme_durumu(ekran, True)
        if hata:
            self.mesaj(ekran, f"Kod e-postası gönderilemedi ({hata}). Tekrar deneyin ya da "
                              "yöneticinize başvurun.", hata=True)
            return
        basarida()

    # ---------- Akışlar ----------

    def _ilk_yonetici(self):
        try:
            k = ku.ilk_yoneticiyi_olustur(self.deger("ilk", "eposta"), self.deger("ilk", "ad"),
                                         self.deger("ilk", "sifre"), self.deger("ilk", "tekrar"))
        except ku.KullaniciHatasi as e:
            self.mesaj("ilk", str(e), hata=True)
            return
        self._olay("INFO", f"İlk yönetici hesabı oluşturuldu: {k['eposta']}")
        self._olay("INFO", f"Kullanıcı giriş yaptı: {k['eposta']}")
        self.girildi(k)

    def _giris(self):
        eposta = self.deger("giris", "eposta")
        try:
            k = ku.giris(eposta, self.deger("giris", "sifre"))
        except ku.HesapKilitlendi as e:
            self._olay("WARNING", f"Hesap kilitlendi ({ku.GIRIS_EN_FAZLA_HATA} hatalı giriş denemesi): "
                                  f"{ku.eposta_normallestir(eposta)}")
            self.alanlar["giris"]["sifre"].set("")
            self.mesaj("giris", str(e), hata=True)
            return
        except ku.KullaniciHatasi as e:
            self.alanlar["giris"]["sifre"].set("")
            self.mesaj("giris", str(e), hata=True)
            return
        if self.hatirla.get():
            oturum.hatirla(k["id"])          # bu cihazda açık kalsın
        else:
            oturum.unut()
        self._olay("INFO", f"Kullanıcı giriş yaptı: {k['eposta']}"
                           + (" (bu cihazda hatırlanacak)" if self.hatirla.get() else ""))
        self.girildi(k)

    def _kayit(self):
        ayarlar = self.ayarlari_getir() or {}
        try:
            eposta, kod = ku.kayit_baslat(self.deger("kayit", "eposta"), self.deger("kayit", "ad"),
                                         self.deger("kayit", "sifre"), self.deger("kayit", "tekrar"),
                                         ayarlar.get("izin_verilen_alan_adi"))
        except ku.KullaniciHatasi as e:
            self.mesaj("kayit", str(e), hata=True)
            return
        self.eposta = eposta

        def gonderildi():
            self.goster("kayit_kod")
            self.mesaj("kayit_kod", f"Kod {eposta} adresine gönderildi.")

        self._kod_gonder("kayit", eposta, "kayit", kod, gonderildi)

    def _kayit_dogrula(self):
        try:
            k = ku.kayit_dogrula(self.eposta, self.deger("kayit_kod", "kod"))
        except ku.KullaniciHatasi as e:
            self.alanlar["kayit_kod"]["kod"].set("")
            self.mesaj("kayit_kod", str(e), hata=True)
            return
        self._olay("INFO", f"Yeni kullanıcı kaydı tamamlandı: {k['eposta']}")
        self.goster("giris")
        self.alanlar["giris"]["eposta"].set(k["eposta"])
        self.mesaj("giris", "Hesabınız açıldı. Giriş yapabilirsiniz.")

    def _sifirlama_baslat(self):
        try:
            eposta, kod = ku.sifirlama_baslat(self.deger("unuttum", "eposta"))
        except ku.KullaniciHatasi as e:
            self.mesaj("unuttum", str(e), hata=True)
            return
        self.eposta = eposta

        def gonderildi():
            self.goster("sifirla")
            self.mesaj("sifirla", f"Bu adresle kayıtlı bir hesap varsa kod {eposta} adresine gönderildi.")

        self._kod_gonder("unuttum", eposta, "sifirlama", kod, gonderildi)

    def _sifre_sifirla(self):
        try:
            ku.sifre_sifirla(self.eposta, self.deger("sifirla", "kod"),
                             self.deger("sifirla", "sifre"), self.deger("sifirla", "tekrar"))
        except ku.KullaniciHatasi as e:
            for alan in ("kod", "sifre", "tekrar"):
                self.alanlar["sifirla"][alan].set("")
            self.mesaj("sifirla", str(e), hata=True)
            return
        self._olay("INFO", f"Şifre sıfırlandı: {self.eposta}")
        self.goster("giris")
        self.alanlar["giris"]["eposta"].set(self.eposta)
        self.mesaj("giris", "Şifreniz değiştirildi. Yeni şifrenizle giriş yapın.")
