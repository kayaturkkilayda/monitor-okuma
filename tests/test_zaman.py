import re
from datetime import datetime, timedelta, timezone

import zaman as z


def test_db_zamani_okunur_bicimde():
    assert z.db_zamani(datetime(2026, 10, 2, 15, 12, 13)) == "2026-10-02 15:12:13"


def test_simdi_okunur_bicimde():
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", z.simdi())


def test_saat_dilimi_bicimi():
    assert re.fullmatch(r"[+-]\d\d:\d\d", z.saat_dilimi(datetime(2026, 10, 2, 15, 0, 0)))


def test_fark_metni_pozitif_negatif_ve_yarim_saat():
    assert z.fark_metni(timedelta(hours=3)) == "+03:00"
    assert z.fark_metni(timedelta(hours=5)) == "+05:00"
    assert z.fark_metni(timedelta(0)) == "+00:00"
    assert z.fark_metni(timedelta(hours=-5, minutes=-30)) == "-05:30"


def test_iso_zaman_m4_icin_saat_dilimli():
    iso = z.iso_zaman("2026-10-02 15:12:13", "+05:00")
    assert iso == "2026-10-02T15:12:13+05:00"
    assert datetime.fromisoformat(iso).utcoffset() == timedelta(hours=5)


def test_saat_dilimli_zaman_yerel_saate_cevrilerek_saklanir():
    """Başka dilimdeki bir an, bilgisayarın yerel saatiyle saklanır; dilim de buna uyar."""
    an = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
    yerel = datetime.fromisoformat(z.iso_zaman(z.db_zamani(an), z.saat_dilimi(an)))
    assert yerel == an                       # aynı an, farklı gösterim


def test_ekran_zamani_veritabani_biciminden():
    assert z.ekran_zamani("2026-10-02 15:12:13") == "02.10.2026 15:12:13"


def test_ekran_zamani_eski_iso_biciminden_cevirmeden():
    """durum.json'daki eski kayıtlar: kaydedildiği yerel saat aynen gösterilir."""
    assert z.ekran_zamani("2026-10-02T15:12:13+05:00") == "02.10.2026 15:12:13"


def test_ekran_zamani_bos_ve_bozuk_deger():
    assert z.ekran_zamani(None) == ""
    assert z.ekran_zamani("") == ""
    assert z.ekran_zamani("bilinmiyor") == "bilinmiyor"
