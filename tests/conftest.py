import pytest

import veritabani


@pytest.fixture(autouse=True)
def gecici_veritabani(tmp_path, monkeypatch):
    """Her test kendi boş veritabanını kullansın; gerçek veri/monitor.db'ye asla dokunulmasın."""
    yol = tmp_path / "veri" / "monitor.db"
    monkeypatch.setattr(veritabani, "VERITABANI", yol)
    return yol


@pytest.fixture(scope="session")
def tk_kok():
    """Tüm arayüz testlerinin paylaştığı tek Tk penceresi (Windows'ta tekrar tekrar açıp
    kapatmak kararsız). Ekran yoksa arayüz testleri atlanır."""
    import tkinter as tk
    try:
        kok = tk.Tk()
    except tk.TclError:
        pytest.skip("Ekran yok, Tk açılamıyor")
    kok.withdraw()
    yield kok
    kok.destroy()
