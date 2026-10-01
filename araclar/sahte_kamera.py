"""Test için sahte IP kamera sunucusu.

Her kamera için /<KOD>/shot.jpg adresinde monitör benzeri bir görüntü üretir.
Örnek: http://localhost:8080/K1/shot.jpg
BOZUK listesindeki kameralar hata döndürür (arızalı kamerayı taklit eder).
"""
import random
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

PORT = 8080
BOZUK = set()


def monitor_goruntusu(kod: str) -> bytes:
    img = np.zeros((480, 640, 3), dtype=np.uint8)

    def yaz(metin, y, renk, boy=2.0):
        cv2.putText(img, metin, (30, y), cv2.FONT_HERSHEY_SIMPLEX, boy, renk, 3)

    yaz(f"{kod}  {datetime.now():%H:%M:%S}", 50, (200, 200, 200), 1.0)
    yaz(f"HR   {random.randint(60, 110)}", 150, (0, 255, 0))
    yaz(f"SpO2 {random.randint(90, 100)}", 250, (255, 255, 0))
    yaz(f"NIBP {random.randint(100, 140)}/{random.randint(60, 90)}", 350, (0, 0, 255))

    _, jpeg = cv2.imencode(".jpg", img)
    return jpeg.tobytes()


class Istek(BaseHTTPRequestHandler):
    def do_GET(self):
        parcalar = self.path.strip("/").split("/")
        if len(parcalar) != 2 or parcalar[1] != "shot.jpg":
            self.send_error(404)
            return

        kod = parcalar[0]
        if kod in BOZUK:
            self.send_error(503, "Kamera arizali")
            return

        veri = monitor_goruntusu(kod)
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(veri)))
        self.end_headers()
        self.wfile.write(veri)

    def log_message(self, *args):
        pass  # her isteği terminale yazmasın


if __name__ == "__main__":
    print(f"Sahte kamera sunucusu çalışıyor: http://localhost:{PORT}/K1/shot.jpg")
    print("Durdurmak için Ctrl+C")
    ThreadingHTTPServer(("", PORT), Istek).serve_forever()
