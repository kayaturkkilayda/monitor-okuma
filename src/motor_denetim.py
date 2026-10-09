"""Motorun arayüzden yönetilmesi: çalışıyor mu, başlat, durdur, açılışta başlat.

Kullanıcı yalnızca arayüzü açar; motoru arayüz kendisi başlatır. İkisi AYRI süreç olarak
kalır: arayüz kapanınca motor çalışmaya devam eder, motor çökse arayüz etkilenmez.

Motor çalışıyor mu? İki bağımsız kanıt kullanılır:

1. Adlandırılmış Windows mutex'i (`MUTEX_ADI`). Süreç ne şekilde biterse bitsin — düzgün
   kapanma, çökme, Görev Yöneticisi'nden sonlandırma — Windows mutex'i kendiliğinden
   serbest bırakır. Yani bayat bilgi kalmaz. Asıl kanıt budur.
2. Kalp atışı dosyası (`KALP_DOSYASI`). Mutex yalnızca aynı oturumda görünür; motor eski
   kurulumlardaki gibi Görev Zamanlayıcı ile SYSTEM hesabında çalışıyorsa arayüz onun
   mutex'ini göremez. Dosya ikisinde de okunabildiği için bu durumu yakalar.

Durdurma: arayüz bir "dur" dosyası bırakır, motor döngüsünde bunu görüp düzgünce kapanır.
Süreci zorla sonlandırmak veritabanını yazma ortasında bölebilirdi; bu yol onu önler.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from zaman import simdi

MUTEX_ADI = "Local\\MonitorOkuma_Motor"      # oturum içi; Global ayrıcalık ister
KALP_DOSYASI = Path("veri/motor.calisiyor")
DUR_DOSYASI = Path("veri/motor.dur")

KALP_ARALIGI_SN = 5          # motor bu sıklıkta kalp atar (ana döngüsüyle aynı)
KALP_ASIMI_SN = 20           # bu kadar süredir atış yoksa motor ölmüş sayılır

_ERROR_ALREADY_EXISTS = 183
_mutex_tutacagi = None       # motor sürecinde mutex'i açık tutar


# ---------- Windows mutex'i ----------

def _mutex_ac(sahiplen: bool):
    """Mutex'i açar/oluşturur. (tutacak, zaten_vardi) döner; Windows dışında (None, False)."""
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None, False
    try:
        olustur = ctypes.windll.kernel32.CreateMutexW
        olustur.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
        olustur.restype = wintypes.HANDLE
        tutacak = olustur(None, bool(sahiplen), MUTEX_ADI)
        vardi = ctypes.windll.kernel32.GetLastError() == _ERROR_ALREADY_EXISTS
        return tutacak, vardi
    except (AttributeError, OSError):
        return None, False


def mutexi_al() -> bool:
    """Motor başlarken çağrılır. Başka motor varsa False döner (ikinci kopya açılmamalı)."""
    global _mutex_tutacagi
    tutacak, vardi = _mutex_ac(sahiplen=True)
    if vardi:
        _mutex_birak(tutacak)
        return False
    _mutex_tutacagi = tutacak
    return True


def _mutex_birak(tutacak):
    if not tutacak:
        return
    try:
        import ctypes
        ctypes.windll.kernel32.CloseHandle(tutacak)
    except (AttributeError, OSError):
        pass


def _mutex_dolu_mu() -> bool:
    """Dışarıdan bakış: mutex başkasında mı? Kendi tutacağımızı etkilemez."""
    tutacak, vardi = _mutex_ac(sahiplen=False)
    _mutex_birak(tutacak)
    return vardi


# ---------- Kalp atışı ----------

def kalp_at():
    """Motor çalıştığını bildirir. Yazılamazsa motor durmaz; mutex zaten asıl kanıttır."""
    try:
        KALP_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
        gecici = KALP_DOSYASI.with_suffix(".tmp")
        gecici.write_text(json.dumps({"pid": os.getpid(), "zaman": simdi()}),
                          encoding="utf-8")
        gecici.replace(KALP_DOSYASI)
    except OSError:
        pass


def kalbi_sil():
    """Motor düzgün kapanırken izini siler."""
    for yol in (KALP_DOSYASI, KALP_DOSYASI.with_suffix(".tmp")):
        try:
            yol.unlink(missing_ok=True)
        except OSError:
            pass


def _kalp_taze_mi() -> bool:
    try:
        d = json.loads(KALP_DOSYASI.read_text(encoding="utf-8"))
        yas = time.time() - KALP_DOSYASI.stat().st_mtime
    except (OSError, ValueError):
        return False
    return isinstance(d, dict) and 0 <= yas < KALP_ASIMI_SN


# ---------- Dışarıya açık ----------

def calisiyor_mu() -> bool:
    """Motor şu anda çalışıyor mu?

    Mutex asıl kanıttır; kalp atışı, motor başka bir Windows oturumunda (ör. eski
    kurulumlardaki SYSTEM görevi) çalışıyorsa devreye girer.
    """
    return _mutex_dolu_mu() or _kalp_taze_mi()


def motor_komutu() -> list[str]:
    """Motoru başlatan komut. EXE'yken motor.exe, kaynak koddan çalışırken main.py."""
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).parent / "motor.exe")]
    # Konsol penceresi açılmasın diye pythonw varsa o tercih edilir
    calistirici = Path(sys.executable)
    penceresiz = calistirici.with_name("pythonw.exe")
    return [str(penceresiz if penceresiz.exists() else calistirici), "main.py"]


def baslat(log=None) -> bool:
    """Motor çalışmıyorsa penceresiz başlatır. Zaten çalışıyorsa hiçbir şey yapmaz.

    True = bu çağrı motoru başlattı. False = zaten çalışıyordu ya da başlatılamadı.
    """
    if calisiyor_mu():
        return False
    DUR_DOSYASI.unlink(missing_ok=True)      # eski durdurma isteği yeni motoru kapatmasın
    komut = motor_komutu()
    if not Path(komut[0]).exists():
        if log:
            log.error(f"Motor başlatılamadı: {komut[0]} bulunamadı")
        return False
    # DETACHED_PROCESS: arayüz kapanınca motor onunla birlikte kapanmaz.
    # CREATE_NO_WINDOW: arka planda çalışır, konsol penceresi açılmaz.
    bayraklar = 0
    if os.name == "nt":
        bayraklar = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    try:
        subprocess.Popen(komut, cwd=str(Path(komut[0]).parent if getattr(sys, "frozen", False)
                                        else Path.cwd()),
                         creationflags=bayraklar, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError as e:
        if log:
            log.error(f"Motor başlatılamadı ({type(e).__name__})")
        return False
    return True


def durdur_iste():
    """Motora düzgün kapanmasını söyler. Süreci zorla sonlandırmaz."""
    try:
        DUR_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
        DUR_DOSYASI.write_text(simdi(), encoding="utf-8")
    except OSError:
        pass


def durdurma_istendi_mi() -> bool:
    """Motor döngüsünde kontrol edilir."""
    return DUR_DOSYASI.exists()


def durdurma_istegini_temizle():
    try:
        DUR_DOSYASI.unlink(missing_ok=True)
    except OSError:
        pass


def durdur(bekle_sn: float = 20.0) -> bool:
    """Durdurma isteği bırakır ve motorun kapanmasını bekler. True = kapandı."""
    durdur_iste()
    son = time.monotonic() + bekle_sn
    while time.monotonic() < son:
        if not calisiyor_mu():
            return True
        time.sleep(0.5)
    return not calisiyor_mu()


# ---------- Windows açılışında başlatma ----------

BASLANGIC_KISAYOLU = "Monitör Görüntü Aktarımı — Motor.lnk"


def baslangic_klasoru() -> Path | None:
    """Kullanıcının Başlangıç klasörü. Buraya yazmak yönetici izni istemez."""
    gezgin = os.environ.get("APPDATA")
    if not gezgin:
        return None
    return Path(gezgin) / "Microsoft/Windows/Start Menu/Programs/Startup"


def _kisayol_yolu() -> Path | None:
    klasor = baslangic_klasoru()
    return klasor / BASLANGIC_KISAYOLU if klasor else None


def acilista_basliyor_mu() -> bool:
    yol = _kisayol_yolu()
    return bool(yol and yol.exists())


def acilista_baslat(acik: bool, log=None) -> bool:
    """Başlangıç klasörüne motor kısayolu koyar ya da kaldırır.

    Yönetici izni gerekmez: kısayol kullanıcının kendi Başlangıç klasörüne yazılır.
    Görev Zamanlayıcı'daki SYSTEM görevinin aksine motor kullanıcı oturumunda çalışır.
    """
    yol = _kisayol_yolu()
    if not yol:
        return False
    try:
        if not acik:
            yol.unlink(missing_ok=True)
            return True
        hedef = motor_komutu()
        yol.parent.mkdir(parents=True, exist_ok=True)
        import win32com.client
        kabuk = win32com.client.Dispatch("WScript.Shell")
        kisayol = kabuk.CreateShortCut(str(yol))
        kisayol.TargetPath = hedef[0]
        kisayol.Arguments = subprocess.list2cmdline(hedef[1:]) if len(hedef) > 1 else ""
        kisayol.WorkingDirectory = str(Path(hedef[0]).parent
                                       if getattr(sys, "frozen", False) else Path.cwd())
        kisayol.WindowStyle = 7                   # simge durumunda; motorun penceresi yok
        kisayol.Description = "Monitör görüntülerini çeken arka plan motoru"
        kisayol.save()
        return True
    except Exception as e:                        # pywin32 yoksa ya da COM hatası
        if log:
            log.error(f"Açılışta başlatma ayarlanamadı ({type(e).__name__})")
        return False
