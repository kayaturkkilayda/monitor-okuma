from sifreleme import ONEK, coz, sifrele


def test_sifrele_coz_ayni_degeri_verir():
    assert coz(sifrele("gizli123")) == "gizli123"


def test_sifreli_deger_duz_metni_icermez():
    sifreli = sifrele("gizli123")
    assert sifreli.startswith(ONEK)
    assert "gizli123" not in sifreli


def test_turkce_karakter():
    assert coz(sifrele("şifreÇĞÜ")) == "şifreÇĞÜ"


def test_bos_deger_bos_kalir():
    assert sifrele("") == ""
    assert coz("") == ""


def test_zaten_sifreli_tekrar_sifrelenmez():
    bir_kez = sifrele("gizli")
    assert sifrele(bir_kez) == bir_kez


def test_duz_metin_coz_ile_bozulmaz():
    assert coz("eski_duz_sifre") == "eski_duz_sifre"