import pytest

import oturum
import veritabani


@pytest.fixture(autouse=True)
def gecici_veritabani(tmp_path, monkeypatch):
    """Her test kendi boş veritabanını kullansın; gerçek veri/monitor.db'ye asla dokunulmasın."""
    yol = tmp_path / "veri" / "monitor.db"
    monkeypatch.setattr(veritabani, "VERITABANI", yol)
    # "Beni hatırla" dosyası da geçici klasöre: gerçek profildeki oturuma dokunulmasın
    monkeypatch.setattr(oturum, "OTURUM_DOSYASI", tmp_path / "oturum.dat")
    return yol


def tk_ac(olustur, deneme: int = 3):
    """Windows'ta yeni Tk açılırken Tcl dosyaları ara sıra okunamıyor ("couldn't read file ...
    No error"; büyük olasılıkla antivirüs taraması). Testler bu yüzden kararsız olmasın."""
    import time
    import tkinter as tk
    for i in range(deneme):
        try:
            return olustur()
        except tk.TclError:
            if i == deneme - 1:
                raise
            time.sleep(0.3)


@pytest.fixture(scope="session")
def tk_kok():
    """Tüm arayüz testlerinin paylaştığı tek Tk penceresi (Windows'ta tekrar tekrar açıp
    kapatmak kararsız). Ekran yoksa arayüz testleri atlanır."""
    import tkinter as tk
    try:
        kok = tk_ac(tk.Tk)
    except tk.TclError:
        pytest.skip("Ekran yok, Tk açılamıyor")
    kok.withdraw()
    yield kok
    kok.destroy()


@pytest.fixture(scope="session", autouse=True)
def motor_surecleri_kapali():
    """Testler ASLA gerçek motor süreci başlatmasın.

    Uygulama penceresi açılınca motoru kendisi başlatır. Test içinde bu, arka planda
    gerçek motor süreçleri bırakır: repoya veri/log yazarlar ve test bitince de
    çalışmaya devam ederler. Bir kez başımıza geldi; pytest 4 motor açtı.

    Oturum kapsamı şart: test_arayuz_onay.py gibi dosyalarda pencereyi kuran fixture
    module kapsamlı ve fonksiyon kapsamlı bir korumadan ÖNCE çalışıyor.
    """
    import motor_denetim
    with pytest.MonkeyPatch.context() as yama:
        yama.setattr(motor_denetim, "baslat", lambda log=None: False)
        yama.setattr(motor_denetim, "durdur", lambda bekle_sn=20.0: True)
        yield


@pytest.fixture(autouse=True)
def motor_dosyalari_gecici(monkeypatch, tmp_path):
    """Kalp atışı, durdurma isteği ve Başlangıç kısayolu geçici klasöre gitsin.

    Gerçek repo ve kullanıcının Başlangıç klasörü testlerden etkilenmemeli.
    """
    import motor_denetim
    monkeypatch.setattr(motor_denetim, "KALP_DOSYASI", tmp_path / "veri" / "motor.calisiyor")
    monkeypatch.setattr(motor_denetim, "DUR_DOSYASI", tmp_path / "veri" / "motor.dur")
    monkeypatch.setattr(motor_denetim, "baslangic_klasoru", lambda: tmp_path / "Baslangic")
