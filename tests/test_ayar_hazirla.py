"""Ayar dosyası ilk açılışta kendiliğinden oluşsun.

Kullanıcıdan config/ayarlar.ornek.json'u elle kopyalaması istenmiyor; hem motor hem
arayüz açılışta ayarlari_hazirla() çağırıyor.
"""
import json
import os
import sys
import subprocess
import textwrap

import pytest

import ayarlar as a


@pytest.fixture
def yollar(tmp_path):
    return tmp_path / "config" / "ayarlar.json", tmp_path / "config" / "ayarlar.ornek.json"


def ornek_yaz(ornek, **ustune):
    ornek.parent.mkdir(parents=True, exist_ok=True)
    d = {**a.VARSAYILAN_AYARLAR, "tesis_kodu": "SABLON", **ustune}
    ornek.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


# ---------- Yoksa oluşturur ----------

def test_dosya_yoksa_olusturulur(yollar):
    yol, ornek = yollar
    ornek_yaz(ornek)
    assert a.ayarlari_hazirla(yol, ornek) is True
    assert yol.exists()
    assert json.loads(yol.read_text(encoding="utf-8"))["tesis_kodu"] == "SABLON"


def test_sablon_yoksa_koddaki_varsayilanlar_kullanilir(yollar):
    yol, ornek = yollar
    assert not ornek.exists()
    assert a.ayarlari_hazirla(yol, ornek) is True
    d = json.loads(yol.read_text(encoding="utf-8"))
    assert d["tesis_kodu"] == a.VARSAYILAN_AYARLAR["tesis_kodu"]
    assert d["kameralar"] == []


def test_sablon_bozuksa_varsayilanlara_dusulur(yollar):
    yol, ornek = yollar
    ornek.parent.mkdir(parents=True, exist_ok=True)
    ornek.write_text("{bu json degil", encoding="utf-8")
    assert a.ayarlari_hazirla(yol, ornek) is True
    assert json.loads(yol.read_text(encoding="utf-8"))["format"] == a.VARSAYILAN_AYARLAR["format"]


def test_config_klasoru_yoksa_olusturulur(tmp_path):
    yol = tmp_path / "hic" / "olmayan" / "ayarlar.json"
    assert a.ayarlari_hazirla(yol, tmp_path / "yok.json") is True
    assert yol.exists()


def test_olusan_dosya_okunabilir(yollar):
    """ayarlari_oku() patlamadan açabilmeli."""
    yol, ornek = yollar
    a.ayarlari_hazirla(yol, ornek)
    d = a.ayarlari_oku(yol)
    assert isinstance(d, dict) and "kameralar" in d


# ---------- Adres ve anahtar boş gelir ----------

def test_adres_ve_anahtar_bos_gelir(yollar):
    yol, ornek = yollar
    ornek_yaz(ornek)
    a.ayarlari_hazirla(yol, ornek)
    d = json.loads(yol.read_text(encoding="utf-8"))
    assert d["api_url"] == "" and d["api_key"] == ""
    assert d["smtp"]["sifre"] == ""


def test_sablona_elle_adres_yazilmissa_bile_bos_gelir(yollar):
    """Şablon değiştirilmiş olsa bile yeni dosyaya adres/anahtar sızmamalı."""
    yol, ornek = yollar
    ornek_yaz(ornek, api_url="https://gercek.hastane/api",
              api_key="GIZLI", smtp={"sunucu": "s", "sifre": "P", "port": 587})
    a.ayarlari_hazirla(yol, ornek)
    metin = yol.read_text(encoding="utf-8")
    assert "gercek.hastane" not in metin
    assert "GIZLI" not in metin
    assert json.loads(metin)["smtp"]["sifre"] == ""


# ---------- Varsa dokunmaz ----------

def test_var_olan_dosyaya_dokunulmaz(yollar):
    yol, ornek = yollar
    ornek_yaz(ornek)
    yol.parent.mkdir(parents=True, exist_ok=True)
    kullanicinin = json.dumps({"tesis_kodu": "BENIM", "api_key": "anahtarim"})
    yol.write_text(kullanicinin, encoding="utf-8")
    once = yol.stat().st_mtime_ns

    assert a.ayarlari_hazirla(yol, ornek) is False
    assert yol.read_text(encoding="utf-8") == kullanicinin    # içerik aynı
    assert yol.stat().st_mtime_ns == once                     # dosyaya hiç yazılmadı


def test_iki_kez_cagirmak_zararsiz(yollar):
    yol, ornek = yollar
    ornek_yaz(ornek)
    assert a.ayarlari_hazirla(yol, ornek) is True
    icerik = yol.read_text(encoding="utf-8")
    assert a.ayarlari_hazirla(yol, ornek) is False
    assert yol.read_text(encoding="utf-8") == icerik


def test_yarim_kalmis_bos_dosya_yeniden_olusturulur(yollar):
    """0 baytlık dosya, kesilmiş bir oluşturmadan artar; ayarı olmayan kurulum demektir."""
    yol, ornek = yollar
    ornek_yaz(ornek)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text("", encoding="utf-8")
    assert a.ayarlari_hazirla(yol, ornek) is True
    assert json.loads(yol.read_text(encoding="utf-8"))["tesis_kodu"] == "SABLON"


# ---------- İki süreç aynı anda ----------

def test_ayni_anda_iki_surec_dosyayi_bozmaz(tmp_path):
    """Motor ve arayüz birlikte açılabilir: yalnızca biri yazar, dosya yarım kalmaz."""
    yol = tmp_path / "config" / "ayarlar.json"
    betik = tmp_path / "ac.py"
    betik.write_text(textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(a.__file__).rsplit("ayarlar.py", 1)[0]!r})
        import ayarlar
        from pathlib import Path
        time.sleep(float(sys.argv[1]))          # ikisi mümkün olduğunca aynı anda girsin
        print("OLUSTURDU" if ayarlar.ayarlari_hazirla(Path({str(yol)!r}),
                                                      Path({str(tmp_path / "yok.json")!r}))
              else "DOKUNMADI")
    """), encoding="utf-8")

    surecler = [subprocess.Popen([sys.executable, str(betik), "0.3"],
                                 stdout=subprocess.PIPE, text=True) for _ in range(2)]
    ciktilar = [p.communicate()[0].strip() for p in surecler]

    assert sorted(ciktilar) == ["DOKUNMADI", "OLUSTURDU"]   # tam olarak biri yazdı
    d = json.loads(yol.read_text(encoding="utf-8"))         # dosya geçerli JSON
    assert d["api_url"] == "" and "kameralar" in d


def test_yaris_sirasinda_var_olan_dosya_ezilmez(tmp_path, monkeypatch):
    """O_EXCL yarışı: biz yazmaya hazırlanırken başkası dosyayı oluşturursa dokunmayız."""
    yol = tmp_path / "config" / "ayarlar.json"
    yol.parent.mkdir(parents=True)
    gercek_open = os.open

    def once_baskasi_olustursun(*args, **kw):
        if not yol.exists():
            yol.write_text('{"tesis_kodu": "DIGER"}', encoding="utf-8")   # yarışı o kazandı
        return gercek_open(*args, **kw)

    monkeypatch.setattr(os, "open", once_baskasi_olustursun)
    assert a.ayarlari_hazirla(yol, tmp_path / "yok.json") is False
    assert json.loads(yol.read_text(encoding="utf-8"))["tesis_kodu"] == "DIGER"
