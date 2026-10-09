"""Motorun arayüzden yönetilmesi: çalışıyor mu, başlat, durdur, açılışta başlat.

Kullanıcı yalnızca arayüzü açar. Buradaki testler motorun gerçekten başlatılmasını
gerektirmez; süreç açan tek test açıkça işaretlidir ve kendi temizliğini yapar.
"""
import json
import logging
import time

import pytest

import motor_denetim as md

LOG = logging.getLogger("test-motor-denetim")

# conftest'teki oturum kapsamlı koruma, kazara gerçek motor açılmasın diye md.baslat ve
# md.durdur'u etkisizleştirir. Bu dosyada asıl sınanan şey o iki işlev olduğu için, gerçek
# halleri içe aktarma anında (fixture'lar çalışmadan önce) yakalanır.
GERCEK_BASLAT = md.baslat
GERCEK_DURDUR = md.durdur


@pytest.fixture
def sahte_motor(tmp_path, monkeypatch):
    """motor_komutu() gerçekten var olan bir dosyayı göstersin.

    Path.exists'i toptan yamalamak durdurma isteği kontrolünü de bozuyordu.
    """
    exe = tmp_path / "motor.exe"
    exe.write_text("", encoding="utf-8")
    monkeypatch.setattr(md, "motor_komutu", lambda: [str(exe)])
    return exe


@pytest.fixture
def kalpsiz(tmp_path, monkeypatch):
    """Kalp atışı ve durdurma dosyaları geçici klasörde; mutex boş."""
    monkeypatch.setattr(md, "KALP_DOSYASI", tmp_path / "veri" / "motor.calisiyor")
    monkeypatch.setattr(md, "DUR_DOSYASI", tmp_path / "veri" / "motor.dur")
    monkeypatch.setattr(md, "_mutex_dolu_mu", lambda: False)
    return tmp_path


# ---------- Çalışıyor mu? ----------

def test_motor_yokken_calismiyor(kalpsiz):
    assert md.calisiyor_mu() is False


def test_taze_kalp_atisi_calisiyor_sayilir(kalpsiz):
    md.kalp_at()
    assert md.calisiyor_mu() is True


def test_bayat_kalp_atisi_calismiyor_sayilir(kalpsiz, monkeypatch):
    """Motor çökerse dosya kalır; eski atış 'çalışıyor' demek değildir."""
    md.kalp_at()
    eski = time.time() - (md.KALP_ASIMI_SN + 5)
    import os
    os.utime(md.KALP_DOSYASI, (eski, eski))
    assert md._kalp_taze_mi() is False
    assert md.calisiyor_mu() is False


def test_mutex_tek_basina_yeterli(tmp_path, monkeypatch):
    """Kalp dosyası hiç yokken bile mutex doluysa motor çalışıyordur.

    Motor başka bir Windows oturumunda (ör. eski SYSTEM görevi) çalışıyorsa kalp
    dosyasını göremeyebiliriz; mutex asıl kanıttır.
    """
    monkeypatch.setattr(md, "KALP_DOSYASI", tmp_path / "yok" / "motor.calisiyor")
    monkeypatch.setattr(md, "_mutex_dolu_mu", lambda: True)
    assert md.calisiyor_mu() is True


def test_kalp_atisi_pid_ve_zaman_yazar(kalpsiz):
    md.kalp_at()
    d = json.loads(md.KALP_DOSYASI.read_text(encoding="utf-8"))
    import os
    assert d["pid"] == os.getpid()
    assert d["zaman"]


def test_kalbi_sil_izi_kaldirir(kalpsiz):
    md.kalp_at()
    assert md.KALP_DOSYASI.exists()
    md.kalbi_sil()
    assert not md.KALP_DOSYASI.exists()


# ---------- İkinci kopya açılmamalı ----------

def test_motor_calisiyorken_baslat_ikinci_kopya_acmaz(kalpsiz, monkeypatch):
    md.kalp_at()                                  # motor çalışıyor gibi
    acilan = []
    monkeypatch.setattr(md.subprocess, "Popen", lambda *a, **k: acilan.append(a))
    assert GERCEK_BASLAT(LOG) is False
    assert acilan == []                           # hiç süreç açılmadı


def test_motor_yokken_baslat_sureci_acar(kalpsiz, sahte_motor, monkeypatch):
    cagrilar = []
    monkeypatch.setattr(md.subprocess, "Popen",
                        lambda *a, **k: cagrilar.append((a, k)) or object())
    assert GERCEK_BASLAT(LOG) is True
    assert len(cagrilar) == 1


def test_baslatilan_surec_arayuzden_bagimsiz_ve_penceresiz(kalpsiz, sahte_motor, monkeypatch):
    """Arayüz kapanınca motor onunla birlikte kapanmamalı, penceresi de olmamalı."""
    import subprocess as sp
    yakalanan = {}
    monkeypatch.setattr(md.subprocess, "Popen",
                        lambda *a, **k: yakalanan.update(k) or object())
    GERCEK_BASLAT(LOG)
    bayraklar = yakalanan["creationflags"]
    assert bayraklar & sp.DETACHED_PROCESS        # arayüzle birlikte kapanmaz
    assert bayraklar & sp.CREATE_NO_WINDOW        # konsol penceresi açılmaz


def test_motor_bulunamazsa_baslat_sessizce_basarisiz_olur(kalpsiz, tmp_path, monkeypatch):
    monkeypatch.setattr(md, "motor_komutu", lambda: [str(tmp_path / "olmayan.exe")])
    monkeypatch.setattr(md.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("süreç açılmamalıydı"))
    assert GERCEK_BASLAT(LOG) is False


def test_baslatirken_eski_durdurma_istegi_silinir(kalpsiz, sahte_motor, monkeypatch):
    """Önceki oturumdan kalan 'dur' dosyası yeni motoru hemen kapatmamalı."""
    md.durdur_iste()
    assert md.durdurma_istendi_mi() is True
    monkeypatch.setattr(md.subprocess, "Popen", lambda *a, **k: object())
    GERCEK_BASLAT(LOG)
    assert md.durdurma_istendi_mi() is False


# ---------- Durdurma ----------

def test_durdurma_istegi_dosya_birakir(kalpsiz):
    assert md.durdurma_istendi_mi() is False
    md.durdur_iste()
    assert md.durdurma_istendi_mi() is True
    md.durdurma_istegini_temizle()
    assert md.durdurma_istendi_mi() is False


def test_durdur_motor_kapanınca_basarili_doner(kalpsiz, monkeypatch):
    durumlar = iter([True, True, False])
    monkeypatch.setattr(md, "calisiyor_mu", lambda: next(durumlar, False))
    assert GERCEK_DURDUR(bekle_sn=5) is True


def test_durdur_kapanmazsa_basarisiz_doner(kalpsiz, monkeypatch):
    monkeypatch.setattr(md, "calisiyor_mu", lambda: True)
    assert GERCEK_DURDUR(bekle_sn=0.2) is False


# ---------- Açılışta başlatma ----------

def test_acilista_baslatma_varsayilan_kapali(tmp_path, monkeypatch):
    monkeypatch.setattr(md, "baslangic_klasoru", lambda: tmp_path / "Baslangic")
    assert md.acilista_basliyor_mu() is False


def test_acilista_baslatma_kisayol_olusturur(tmp_path, monkeypatch):
    """Başlangıç klasörüne yazmak yönetici izni istemez."""
    klasor = tmp_path / "Baslangic"
    monkeypatch.setattr(md, "baslangic_klasoru", lambda: klasor)
    if not md.acilista_baslat(True, LOG):
        pytest.skip("pywin32/COM yok, kısayol oluşturulamıyor")
    assert md.acilista_basliyor_mu() is True
    assert (klasor / md.BASLANGIC_KISAYOLU).exists()

    assert md.acilista_baslat(False, LOG) is True
    assert md.acilista_basliyor_mu() is False


def test_baslangic_klasoru_yoksa_sessizce_gecer(monkeypatch):
    monkeypatch.setattr(md, "baslangic_klasoru", lambda: None)
    assert md.acilista_basliyor_mu() is False
    assert md.acilista_baslat(True, LOG) is False


# ---------- Motoru başlatan komut ----------

def test_kaynak_koddan_calisirken_main_py_calistirilir(monkeypatch):
    monkeypatch.delattr(md.sys, "frozen", raising=False)
    komut = md.motor_komutu()
    assert komut[-1] == "main.py"
    assert komut[0].endswith(".exe")               # python ya da pythonw


def test_exe_olarak_calisirken_motor_exe_calistirilir(monkeypatch, tmp_path):
    monkeypatch.setattr(md.sys, "frozen", True, raising=False)
    monkeypatch.setattr(md.sys, "executable", str(tmp_path / "arayuz.exe"))
    komut = md.motor_komutu()
    assert komut == [str(tmp_path / "motor.exe")]  # motor.exe arayuz.exe'nin yanındadır
