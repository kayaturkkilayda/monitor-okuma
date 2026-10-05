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
