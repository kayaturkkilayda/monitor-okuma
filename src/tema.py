"""Bütün arayüzün tek yazı tipi, ölçek ve genişlik ayarı.

Yazı boyutları burada durur; hiçbir pencere kendi başına yazı tipi tanımlamaz. Buradaki
sayılar değişince giriş ekranı, ana pencere ve açılan pencereler (kod girişi, QR, kamera
ekle) birlikte değişir.

Ekran ölçeği (DPI) yüksek bilgisayarlarda Windows, farkındalık açılmazsa pencereyi 96 DPI
çizip büyütür; yazılar bulanık görünür. dpi_farkindaligini_ac() bunu kapatır ve Tk gerçek
çözünürlükte çizer. Tk() oluşturulmadan ÖNCE çağrılmalıdır.
"""
import tkinter as tk
from tkinter import font as tkfont, ttk

AILE = "Segoe UI"
NORMAL = 11               # normal metin: etiketler, giriş kutuları, tablo satırları
BASLIK = 12               # başlıklar ve sekme adları (kalın)
KUCUK = 10                # küçük gri açıklamalar
BUYUK = 18                # giriş ekranı başlığı ve kod kutuları

YAZI = (AILE, NORMAL)
BASLIK_YAZI = (AILE, BASLIK, "bold")
KUCUK_YAZI = (AILE, KUCUK)
BUYUK_YAZI = (AILE, BUYUK)
TEK_ARALIK_YAZI = ("Consolas", KUCUK)

GRI = "#5f6b7a"           # küçük açıklama yazılarının rengi

# Çok geniş ekranda giriş kutuları ve tablolar saçma şekilde uzamasın diye içerik
# en çok bu genişlikte tutulur, artan yer iki yana boşluk olarak dağıtılır.
AZAMI_GENISLIK = 1400

# Ana pencere bundan küçültülemez; küçültülürse alanlar üst üste biner. Yükseklik, en uzun
# sekme olan Ayarlar'ın kesilmeden sığdığı ölçüdür; 1366x768 dizüstüne de sığar.
# Normal (%100) ekran ölçeği içindir; olcekli() bunu ekranın gerçek ölçeğine çevirir.
EN_KUCUK_PENCERE = (1020, 680)

# Ana pencerenin açılış boyutu (yine %100 ölçek için)
ACILIS_PENCERESI = (1180, 760)

# Yazı tipiyle birlikte büyüyen adlandırılmış Tk yazı tipleri (menü, mesaj kutusu dahil)
_NORMAL_YAZILAR = ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkIconFont",
                   "TkCaptionFont", "TkTooltipFont")


def dpi_farkindaligini_ac():
    """Windows'ta yüksek ekran ölçeğinde yazılar bulanık görünmesin.

    Tk() oluşturulmadan önce çağrılır. Başka işletim sisteminde ya da pencere açıldıktan
    sonra çağrılırsa sessizce geçer: görüntü kalitesi için yapılır, program buna bağlı değil.
    """
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)      # sistem DPI farkındalığı
    except Exception:
        pass


def ekran_olcegi(kok=None) -> float:
    """Ekranın büyütme oranı: %100 ekranda 1.0, %150 ekranda 1.5.

    DPI farkındalığı açıkken yazılar bu oranda büyür; pencere boyutları da aynı oranda
    büyümezse içerik sığmaz.
    """
    try:
        return max(1.0, (kok or tk._default_root).winfo_fpixels("1i") / 96.0)
    except (tk.TclError, AttributeError):
        return 1.0


def olcekli(genislik: int, yukseklik: int, kok=None) -> tuple[int, int]:
    """%100 ekran için verilen boyutu, kullanılan ekranın ölçeğine çevirir."""
    olcek = ekran_olcegi(kok)
    return round(genislik * olcek), round(yukseklik * olcek)


def satir_yuksekligi() -> int:
    """Tablo (Treeview) satır yüksekliği: yazı yüksekliği + nefes payı.

    Yazı büyüyünce satır da büyümeli; yoksa harflerin altı kesilir.
    """
    try:
        return tkfont.Font(font=YAZI).metrics("linespace") + 10
    except tk.TclError:
        return 28


ZAMAN_ORNEGI = "00.00.0000 00:00:00"      # zaman sütunlarının sığdırması gereken en uzun değer


def sarma_genisligi(temel: int, kok=None) -> int:
    """Uzun açıklamaların satır sarma genişliği; yazıyla birlikte büyür.

    Sabit kalsaydı büyüyen yazı aynı genişliğe daha az kelime sığdırır, açıklamalar
    gereksiz yere çok satıra bölünürdü.
    """
    return round(temel * ekran_olcegi(kok))


def sutun_genisligi(baslik: str, en_az: int, ornek: str = "") -> int:
    """Tablo sütunu, başlığı ve (verilmişse) örnek değeri sığdıracak kadar geniş olsun.

    Sütun genişlikleri küçük yazıya göre yazılmıştı; yazı büyüyünce hem başlıklar hem de
    zaman gibi uzun değerler kesiliyordu. Bu hesap yazı boyutu değişse de doğru kalır.
    """
    try:
        gerekli = max(tkfont.Font(font=(AILE, NORMAL, "bold")).measure(baslik),
                      tkfont.Font(font=YAZI).measure(ornek) if ornek else 0)
        return max(en_az, gerekli + 24)
    except tk.TclError:
        return en_az


def kur(kok=None) -> ttk.Style:
    """Yazı tiplerini ve ttk stillerini uygular. Tk penceresi açıldıktan sonra çağrılır."""
    stil = ttk.Style(kok)

    for ad in _NORMAL_YAZILAR:
        try:
            tkfont.nametofont(ad, root=kok).configure(family=AILE, size=NORMAL)
        except tk.TclError:                  # bu Tk sürümünde o yazı tipi yoksa atla
            pass
    for ad, boyut in (("TkHeadingFont", BASLIK), ("TkSmallCaptionFont", KUCUK)):
        try:
            tkfont.nametofont(ad, root=kok).configure(family=AILE, size=boyut)
        except tk.TclError:
            pass
    try:
        tkfont.nametofont("TkFixedFont", root=kok).configure(family="Consolas", size=KUCUK)
    except tk.TclError:
        pass

    stil.configure(".", font=YAZI)
    stil.configure("TNotebook.Tab", font=BASLIK_YAZI, padding=(14, 7))
    stil.configure("Treeview", font=YAZI, rowheight=satir_yuksekligi())
    stil.configure("Treeview.Heading", font=(AILE, NORMAL, "bold"))
    stil.configure("TLabelframe.Label", font=BASLIK_YAZI)
    stil.configure("Kucuk.TLabel", font=KUCUK_YAZI, foreground=GRI)
    stil.configure("Baslik.TLabel", font=BASLIK_YAZI)
    return stil


def genisligi_sinirla(cerceve, azami: int | None = None, kenar: int = 10,
                      ust: int = 10, alt: int = 10):
    """Çerçevenin içeriğini en çok `azami` piksel genişlikte tutar ve ortalar.

    azami verilmezse AZAMI_GENISLIK ekran ölçeğine çevrilerek kullanılır; %150 ekranda
    yazılar da 1,5 kat büyüdüğü için sınır aynı oranda büyümeli.

    Widget ağacına dokunmaz; yalnızca çerçevenin kenar boşluğunu pencere genişliğine göre
    ayarlar. Böylece içindeki düzen (pack ya da grid) olduğu gibi kalır.
    """
    if azami is None:
        azami = round(AZAMI_GENISLIK * ekran_olcegi(cerceve))
    cerceve._son_yan = None

    def ayarla(_=None):
        yan = max(kenar, (cerceve.winfo_width() - azami) // 2)
        if yan != cerceve._son_yan:          # değişmedikçe dokunma: sonsuz <Configure> döngüsü olmasın
            cerceve._son_yan = yan
            cerceve.configure(padding=(yan, ust, yan, alt))

    cerceve.bind("<Configure>", ayarla, add="+")
    ayarla()
    return cerceve


class DikeyKaydirma(ttk.Frame):
    """Dikey kaydırılabilir alan; içerik `govde` çerçevesine konur.

    Ayarlar gibi uzun formlar küçük ekranda kesilmesin diye kullanılır. İzin verilen alan
    adı listesi gibi büyüyen bölümler yüzünden gereken yükseklik önceden bilinemez; pencere
    en küçük boyutta bile her alana kaydırarak ulaşılır. Çubuk yalnızca içerik sığmadığında
    görünür, böyle bir durum yoksa ekranda hiçbir fark olmaz.
    """

    def __init__(self, ust, **kw):
        super().__init__(ust, **kw)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        arka = ttk.Style().lookup("TFrame", "background") or None
        self.tuval = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=arka)
        self.tuval.grid(row=0, column=0, sticky="nsew")
        self.cubuk = ttk.Scrollbar(self, orient="vertical", command=self.tuval.yview)
        self.tuval.configure(yscrollcommand=self._cubugu_goster)
        self.govde = ttk.Frame(self.tuval)
        self._pencere = self.tuval.create_window((0, 0), window=self.govde, anchor="nw")
        self.govde.bind("<Configure>", self._icerik_degisti)
        self.tuval.bind("<Configure>", self._alan_degisti)
        self.bind_all("<MouseWheel>", self._tekerlek, add="+")

    def _icerik_degisti(self, _=None):
        self.tuval.configure(scrollregion=self.tuval.bbox("all"))

    def _alan_degisti(self, olay):
        self.tuval.itemconfigure(self._pencere, width=olay.width)   # içerik enine yayılsın

    def _cubugu_goster(self, bas, son):
        """Çubuk yalnızca içerik sığmadığında görünür."""
        if float(bas) <= 0.0 and float(son) >= 1.0:
            self.cubuk.grid_remove()
        else:
            self.cubuk.grid(row=0, column=1, sticky="ns")
        self.cubuk.set(bas, son)

    def _tekerlek(self, olay):
        """Fare imleci bu alanın üstündeyken tekerlek kaydırır."""
        try:
            if not self.cubuk.winfo_ismapped() or self.tuval.winfo_containing(
                    olay.x_root, olay.y_root) is None:
                return
            altinda = str(self.tuval.winfo_containing(olay.x_root, olay.y_root))
            if altinda.startswith(str(self.tuval)):
                self.tuval.yview_scroll(-olay.delta // 120, "units")
        except (tk.TclError, KeyError):
            pass
