import pytest

import veritabani


@pytest.fixture(autouse=True)
def gecici_veritabani(tmp_path, monkeypatch):
    """Her test kendi boş veritabanını kullansın; gerçek veri/monitor.db'ye asla dokunulmasın."""
    yol = tmp_path / "veri" / "monitor.db"
    monkeypatch.setattr(veritabani, "VERITABANI", yol)
    return yol
