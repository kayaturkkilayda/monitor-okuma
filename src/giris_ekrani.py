"""Giriş penceresi: ilk yönetici, giriş, kayıt, e-posta kodu ve şifre sıfırlama ekranları.

Doğrulama kodları buradan doğrudan gönderilir (kullanıcı ekranda bekliyor); motorun
bildirim kuyruğu kullanılmaz. Kodlar ve şifreler hiçbir log, olay ya da mesajda yer almaz.
"""
import tkinter as tk
from tkinter import ttk

import kullanicilar as ku
import oturum
import tema
from arka_plan import arka_planda
from eposta_girisi import EpostaGirisi, oneri_alanlari
from kod_girisi import KodGirisi
from bildirim import gonder, smtp_hazir_mi
from veritabani import olay

YESIL, KIRMIZI = "#1e7e34", "#b00020"
SMTP_YOK = "E-posta ayarları yapılmamış, yöneticinize başvurun."

GRI, BAGLANTI = "#5f6b7a", "#0b5ed7"
ALAN_GENISLIGI = 34               # karakter; etiketler alanların üstünde olduğu için tek sütun


def stilleri_kur():
    """Giriş ekranının kendi ttk stilleri. Tema değişse de bir kez tanımlanması yeter."""
    stil = tema.kur()
    stil.configure("Giris.TButton", font=tema.YAZI, padding=(0, 8))
    stil.configure("GirisBaslik.TLabel", font=(tema.AILE, tema.BUYUK))
    stil.configure("GirisAciklama.TLabel", foreground=GRI, font=tema.KUCUK_YAZI)
    stil.configure("GirisEtiket.TLabel", foreground=GRI, font=tema.KUCUK_YAZI)
    stil.configure("GirisBaglanti.TLabel", foreground=BAGLANTI,
                   font=(tema.AILE, tema.KUCUK, "underline"))


class GirisEkrani(ttk.Frame):
    """girildi(kullanici) başarılı girişte çağrılır.

    ayarlari_getir() her işlemde güncel ayarları döndürür (SMTP ve izin verilen alan adları
    giriş penceresi açıkken yönetici tarafından değiştirilmiş olabilir).
    """

    def __init__(self, ust, ayarlari_getir, girildi, log):
        super().__init__(ust, padding=(40, 32))
        stilleri_kur()
        self.ayarlari_getir = ayarlari_getir
        self.girildi = girildi
        self.log = log
        self.eposta = ""                     # kod ekranlarında hangi hesap için çalışıldığı
        self.ekranlar, self.alanlar, self.mesajlar, self.dugmeler = {}, {}, {}, {}
        self.girisler, self.goster_kutusu = {}, {}
        self.kod_kutulari = {}               # ekran adı → KodGirisi
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
        """Tek sütunlu düzen: etiket alanın üstünde, ana düğme tam genişlikte.

        Yaygın giriş ekranlarındaki gibi tek bir ana eylem öne çıkar. İkincil eylemler
        (Kayıt ol, Şifremi unuttum) düğme değil bağlantı görünümündedir; böylece göz
        önce "Giriş yap" düğmesine gider.
        """
        cerceve = ttk.Frame(self)
        cerceve.columnconfigure(0, weight=1)
        satir = 0

        ttk.Label(cerceve, text=baslik, style="GirisBaslik.TLabel").grid(
            row=satir, column=0, sticky="w")
        satir += 1
        if aciklama:
            ttk.Label(cerceve, text=aciklama, style="GirisAciklama.TLabel",
                      wraplength=tema.sarma_genisligi(320), justify="left").grid(row=satir, column=0, sticky="w",
                                                           pady=(6, 0))
            satir += 1

        degerler, girisler = {}, {}
        for alan, etiket in alanlar:
            ttk.Label(cerceve, text=etiket, style="GirisEtiket.TLabel").grid(
                row=satir, column=0, sticky="w", pady=(14, 3))
            satir += 1
            deger = tk.StringVar()
            if alan == "eposta":
                # Yazarken biçim denetimi ve @'den sonrası için satır içi alan adı tamamlama
                kutu = EpostaGirisi(cerceve, deger, lambda e=ad: self._oneri_alanlari(e),
                                    genislik=ALAN_GENISLIGI)
                kutu.grid(row=satir, column=0, sticky="we")
                giris = kutu.giris
            elif alan == "kod":
                # Altı ayrı kutu; son hane girilince kendiliğinden doğrular
                kutu = KodGirisi(cerceve, tamamlandi=self._kod_tamamlandi(ad, deger, ana_dugme[1]))
                kutu.grid(row=satir, column=0, sticky="w")
                giris = kutu.kutular[0]
                self.kod_kutulari[ad] = kutu
                # Dışarıdan deger.set(...) yapılınca (ekran temizliği, testler) kutulara dağıt
                deger.trace_add("write", self._kodu_kutulara_yaz(deger, kutu))
            else:
                giris = ttk.Entry(cerceve, textvariable=deger, width=ALAN_GENISLIGI,
                                  show="*" if alan in ("sifre", "tekrar") else "")
                giris.grid(row=satir, column=0, sticky="we")
            satir += 1
            giris.bind("<Return>", lambda e, f=ana_dugme[1]: f())
            degerler[alan], girisler[alan] = deger, giris

        if "sifre" in degerler:
            secenekler = ttk.Frame(cerceve)
            secenekler.grid(row=satir, column=0, sticky="w", pady=(14, 0))
            satir += 1
            goster = tk.BooleanVar(value=False)
            ttk.Checkbutton(secenekler, text="Şifreyi göster", variable=goster,
                            command=lambda e=ad: self._sifreyi_goster(e)).pack(side="left")
            self.goster_kutusu[ad] = goster
            if ad == "giris":
                ttk.Checkbutton(secenekler, text="Beni hatırla", variable=self.hatirla).pack(
                    side="left", padx=(14, 0))

        dugme = ttk.Button(cerceve, text=ana_dugme[0], command=ana_dugme[1], style="Giris.TButton")
        dugme.grid(row=satir, column=0, sticky="we", pady=(20, 0))
        satir += 1

        if diger_dugmeler:
            alt = ttk.Frame(cerceve)
            alt.grid(row=satir, column=0, pady=(16, 0))      # ortalı: grid sticky verilmedi
            satir += 1
            for i, (metin, komut) in enumerate(diger_dugmeler):
                if i:
                    ttk.Label(alt, text="•", foreground=GRI).pack(side="left", padx=9)
                self._baglanti(alt, metin, komut)

        mesaj = ttk.Label(cerceve, text="", wraplength=tema.sarma_genisligi(320),
                          justify="left")
        mesaj.grid(row=satir, column=0, sticky="w", pady=(16, 0))
        self.ekranlar[ad], self.alanlar[ad], self.mesajlar[ad], self.dugmeler[ad] = \
            cerceve, degerler, mesaj, (dugme, ana_dugme[0])
        self.girisler[ad] = girisler

    @staticmethod
    def _kodu_kutulara_yaz(deger, kutu):
        """StringVar dışarıdan değişince kutuları eşitler; doğrulamayı tetiklemez."""
        def guncelle(*_):
            if kutu.kod() != deger.get():
                kutu.yaz(deger.get(), bildir=False)
        return guncelle

    def _kod_tamamlandi(self, ekran: str, deger, eylem):
        """Altıncı hane girilince kodu alana yazar ve doğrulamayı başlatır."""
        def tamamlandi(kod: str):
            deger.set(kod)
            eylem()
        return tamamlandi

    @staticmethod
    def _baglanti(ust, metin: str, komut):
        """Düğme yerine bağlantı görünümlü etiket; ikincil eylem öne çıkmasın."""
        etiket = ttk.Label(ust, text=metin, style="GirisBaglanti.TLabel", cursor="hand2")
        etiket.pack(side="left")
        etiket.bind("<Button-1>", lambda e: komut())
        return etiket

    def _oneri_alanlari(self, ekran: str) -> list[str]:
        izinli = (self.ayarlari_getir() or {}).get("izin_verilen_alan_adi")
        # Kayıtta yalnızca izin verilen alan adları önerilir; diğerleri zaten kabul edilmez
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

    def _kodu_temizle(self, ekran: str):
        """Yanlış kodda kutuları boşaltır ve kırmızı çerçeve gösterir."""
        self.alanlar[ekran]["kod"].set("")
        if ekran in self.kod_kutulari:
            self.kod_kutulari[ekran].temizle(hata=True)

    def _oturum_ac(self, k: dict, neden: str):
        """Kullanıcıyı içeri alır. "Beni hatırla" seçiliyse cihazda oturum açık kalır."""
        if self.hatirla.get():
            oturum.hatirla(k["id"])
        else:
            oturum.unut()
        self._olay("INFO", f"Kullanıcı giriş yaptı ({neden}): {k['eposta']}"
                           + (" (bu cihazda hatırlanacak)" if self.hatirla.get() else ""))
        self.girildi(k)

    def _kayit_dogrula(self):
        try:
            k = ku.kayit_dogrula(self.eposta, self.deger("kayit_kod", "kod"))
        except ku.KullaniciHatasi as e:
            self._kodu_temizle("kayit_kod")
            self.mesaj("kayit_kod", str(e), hata=True)
            return
        self._olay("INFO", f"Yeni kullanıcı kaydı tamamlandı: {k['eposta']}")
        # E-posta kodu kimliği kanıtladı. Aynı kişiye şifresini ikinci kez sormayız.
        self._oturum_ac(ku.girisi_kaydet(k["eposta"]), "kayıt doğrulandı")

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
            self._kodu_temizle("sifirla")
            for alan in ("sifre", "tekrar"):
                self.alanlar["sifirla"][alan].set("")
            self.mesaj("sifirla", str(e), hata=True)
            return
        self._olay("INFO", f"Şifre sıfırlandı: {self.eposta}")
        self.goster("giris")
        self.alanlar["giris"]["eposta"].set(self.eposta)
        self.mesaj("giris", "Şifreniz değiştirildi. Yeni şifrenizle giriş yapın.")
