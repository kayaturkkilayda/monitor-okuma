from datetime import datetime

import kimlik as k
from gonderici import kuyruga_ekle

ZAMAN = datetime(2026, 10, 2, 15, 12, 13)


def test_kayit_kimligi_bicimi():
    assert k.kayit_tabani("H01", "K1", "Y1", ZAMAN, 1) == "H01_K1_Y1_2026-10-02_15-12-13_1"


def test_cift_kimligi_sirasiz():
    assert k.cift_tabani("H01", "K1", "Y1", ZAMAN) == "H01_K1_Y1_2026-10-02_15-12-13"


def test_dosya_adina_uymayan_karakterler_temizlenir():
    kimlik = k.kayit_tabani("H01", "K1", "Yoğun Bakım/3", ZAMAN, 2)
    assert kimlik == "H01_K1_Yoğun-Bakım-3_2026-10-02_15-12-13_2"


def test_benzersiz_bos_ise_aynen_doner():
    assert k.benzersiz("A", lambda x: False) == "A"


def test_benzersiz_doluysa_2_3_ekler():
    dolu = {"A", "A_2"}
    assert k.benzersiz("A", dolu.__contains__) == "A_3"


def _ekle(tmp_path, kayit_id, cift_id="c"):
    dosya = tmp_path / f"{kayit_id}.avif"
    dosya.write_bytes(b"x")
    kuyruga_ekle(dosya, "H01", "K1", "Y1", ZAMAN, 1, cift_id, kayit_id)


def test_tabloda_olan_kimlik_tekrar_verilmez(tmp_path):
    yol = lambda ad: tmp_path / f"{ad}.avif"
    ilk = k.yeni_kayit_kimligi("H01", "K1", "Y1", ZAMAN, 1, yol)
    _ekle(tmp_path, ilk)
    ikinci = k.yeni_kayit_kimligi("H01", "K1", "Y1", ZAMAN, 1, yol)
    assert ilk == "H01_K1_Y1_2026-10-02_15-12-13_1"
    assert ikinci == "H01_K1_Y1_2026-10-02_15-12-13_1_2"


def test_diskte_dosyasi_olan_kimlik_tekrar_verilmez(tmp_path):
    """Kaydı silinmiş ama görüntüsü duran bir dosyanın üzerine yazılmasın."""
    (tmp_path / "H01_K1_Y1_2026-10-02_15-12-13_1.avif").write_bytes(b"eski")
    kimlik = k.yeni_kayit_kimligi("H01", "K1", "Y1", ZAMAN, 1, lambda ad: tmp_path / f"{ad}.avif")
    assert kimlik == "H01_K1_Y1_2026-10-02_15-12-13_1_2"


def test_cift_kimligi_tekil(tmp_path):
    _ekle(tmp_path, "x", cift_id="H01_K1_Y1_2026-10-02_15-12-13")
    assert k.yeni_cift_kimligi("H01", "K1", "Y1", ZAMAN) == "H01_K1_Y1_2026-10-02_15-12-13_2"


def test_farkli_kamera_ayni_saniye_cakismaz():
    assert k.kayit_tabani("H01", "K1", "Y1", ZAMAN, 1) != k.kayit_tabani("H01", "K2", "Y2", ZAMAN, 1)
