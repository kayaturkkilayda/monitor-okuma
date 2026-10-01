"""Test için sahte M4 API sunucusu.

%20 ihtimalle geçici hata döndürür; tekrar deneme mantığını test etmek için.
Aynı kayit_id ikinci kez gelirse kabul eder ama tekrar kaydetmez.
"""
import random
from flask import Flask, jsonify, request

app = Flask(__name__)
API_KEY = "test-anahtar"
HATA_ORANI = 0.2
gorulen = set()


@app.post("/api/goruntu")
def goruntu():
    if request.headers.get("X-API-Key") != API_KEY:
        return jsonify(hata="yetkisiz"), 401
    if random.random() < HATA_ORANI:
        return jsonify(hata="gecici sunucu hatasi"), 503

    kayit_id = request.form.get("kayit_id")
    if kayit_id in gorulen:
        return jsonify(durum="zaten alindi"), 200

    dosya = request.files["goruntu"]
    boyut = len(dosya.read()) / 1024
    gorulen.add(kayit_id)
    f = request.form
    print(f"ALINDI {f['tesis_kodu']}/{f['kamera_kodu']}/{f['yatak_kodu']} "
          f"sıra={f['sira']} zaman={f['zaman']} {boyut:.1f} KB")
    return jsonify(durum="ok"), 201


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=9000)