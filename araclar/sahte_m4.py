"""Test için sahte M4 API sunucusu.

Gerçek M4'ün sözleşmesini taklit eder: başlıkları ve JSON gövdesini doğrular, eksik ya da
yanlış tipte alan görürse 400, yanlış anahtarda 401 döndürür. Motorun gönderdiği gövdenin
biçimi burada da yanlışsa gerçek M4'te de yanlış olur.

%20 ihtimalle 503 döndürür; motorun tekrar deneme mantığını sınamak içindir (HATA_ORANI).
Aynı captureId ikinci kez gelirse kabul eder ama tekrar kaydetmez.

Test anahtarı koda yazılmaz: araclar/ayarlar.test.json dosyasından okunur. Böylece motorun
gönderdiği anahtarla burada beklenen anahtar tek bir yerden gelir.
"""
import base64
import binascii
import json
import random
import re
from pathlib import Path

from flask import Flask, jsonify, request

app = Flask(__name__)

AYAR_DOSYASI = Path(__file__).with_name("ayarlar.test.json")
HATA_ORANI = 0.2
gorulen = set()

# ISO-8601, offset'li: "2026-10-09T07:48:43.650+03:00" (Z ya da offset'siz de kabul)
ZAMAN_DESENI = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{1,9})?(Z|[+-]\d\d:\d\d)?$")

# alan adı -> beklenen Python tipi
# Gerçek backend'in DTO'su: MonitorGoruntuIstekDTO.SabitKamera
ALANLAR = {
    "captureId": str,
    "kameraKodu": str,
    "kameraId": int,                 # Long
    "yatakEslesmeKodu": str,         # @NotBlank
    "goruntuCekilmeZamani": str,
    "okumaGrupId": str,
    "goruntuFormati": str,
    "goruntuBase64": str,            # @NotBlank
}

# @NotBlank olanlar boş olamaz; diğer metinler boş gelebilir
ZORUNLU_DOLU = ("yatakEslesmeKodu", "goruntuBase64")


def beklenen_anahtar() -> str:
    """Test anahtarını ayar dosyasından okur; koda gömülü değildir."""
    try:
        return str(json.loads(AYAR_DOSYASI.read_text(encoding="utf-8")).get("api_key", "")).strip()
    except (OSError, ValueError):
        return ""


def govdeyi_dogrula(govde) -> str | None:
    """Gövde sözleşmeye uyuyor mu? Uymuyorsa sebebi, uyuyorsa None döner."""
    if not isinstance(govde, dict):
        return "gövde JSON nesnesi olmalı"

    eksik = [ad for ad in ALANLAR if ad not in govde]
    if eksik:
        return f"eksik alan: {', '.join(eksik)}"
    fazla = [ad for ad in govde if ad not in ALANLAR]
    if fazla:
        return f"beklenmeyen alan: {', '.join(fazla)}"

    for ad, tip in ALANLAR.items():
        deger = govde[ad]
        # bool, Python'da int sayılır; kameraId için kabul edilmemeli
        if tip is int and (isinstance(deger, bool) or not isinstance(deger, int)):
            return f"{ad} sayı olmalı (tırnaksız)"
        if tip is str and not isinstance(deger, str):
            return f"{ad} metin olmalı"
        if ad in ZORUNLU_DOLU and not deger.strip():
            return f"{ad} boş olamaz (@NotBlank)"

    if not ZAMAN_DESENI.match(govde["goruntuCekilmeZamani"]):
        return ("goruntuCekilmeZamani ISO-8601 olmalı, "
                "ör. 2026-10-09T07:48:43.650+03:00")
    if govde["goruntuFormati"] != "jpeg":
        return "goruntuFormati 'jpeg' olmalı"
    if govde["goruntuBase64"].startswith("data:"):
        return "goruntuBase64 'data:image/...;base64,' öneki İÇERMEMELİ, düz base64 olmalı"
    try:
        ham = base64.b64decode(govde["goruntuBase64"], validate=True)
    except (binascii.Error, ValueError):
        return "goruntuBase64 çözülemedi"
    if ham[:3] != b"\xff\xd8\xff":          # JPEG dosya imzası
        return "goruntuBase64 bir JPEG değil"
    return None


@app.post("/monitor-okuma/kamera")
@app.post("/api/goruntu")                # eski ayarlar bozulmasın diye ikisi de dinlenir
def goruntu():
    if request.headers.get("X-Api-Key") != beklenen_anahtar():
        print("REDDEDILDI 401 | X-Api-Key yanlış ya da eksik")
        return jsonify(hata="yetkisiz"), 401

    # Spring'in @RequestBody ucu JSON olmayan gövdeye 415 döndürür (multipart gönderilirse de)
    tur = (request.headers.get("Content-Type") or "").split(";")[0].strip()
    if tur != "application/json":
        print(f"REDDEDILDI 415 | Content-Type 'application/json' olmalı, gelen: {tur!r}")
        return jsonify(hata=f"Unsupported Media Type: {tur or '(yok)'}"), 415

    govde = request.get_json(silent=True)
    sebep = govdeyi_dogrula(govde)
    if sebep:
        print(f"REDDEDILDI 400 | {sebep}")
        return jsonify(hata=sebep), 400

    if random.random() < HATA_ORANI:
        return jsonify(hata="gecici sunucu hatasi"), 503

    # Gerçek backend gibi: aynı captureId ikinci kez gelirse 200, yenisi 201
    if govde["captureId"] in gorulen:
        print(f"ZATEN VAR 200 | capture={govde['captureId'][:8]}…")
        return jsonify(durum="zaten alindi", captureId=govde["captureId"]), 200
    gorulen.add(govde["captureId"])

    kb = len(base64.b64decode(govde["goruntuBase64"])) / 1024
    print(f"ALINDI {govde['kameraKodu']}/{govde['yatakEslesmeKodu']} "
          f"kameraId={govde['kameraId']} zaman={govde['goruntuCekilmeZamani']} "
          f"{kb:.1f} KB  capture={govde['captureId'][:8]}…")
    return jsonify(durum="ok", captureId=govde["captureId"]), 201


if __name__ == "__main__":
    if not beklenen_anahtar():
        print(f"UYARI: {AYAR_DOSYASI.name} içinde api_key yok; her istek 401 alacak.")
    app.run(host="0.0.0.0", port=9000)
