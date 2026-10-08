import cv2
import time
from PIL import Image
# AVIF desteği Pillow 12 ile hazır gelir; pillow-avif-plugin KULLANILMAZ
from pathlib import Path

kamera = cv2.VideoCapture(0)
time.sleep(2)
for _ in range(30):
    basarili, kare = kamera.read()
kamera.release()

if not basarili:
    print("Kare alınamadı")
    exit()

# OpenCV BGR sırasında tutar, Pillow RGB bekler
goruntu = Image.fromarray(cv2.cvtColor(kare, cv2.COLOR_BGR2RGB))

goruntu.save("ornek.png")
goruntu.save("ornek_q85.jpg", quality=85)
goruntu.save("ornek_q60.jpg", quality=60)
goruntu.save("ornek_q85.avif", quality=85)
goruntu.save("ornek_q60.avif", quality=60)

print(f"Çözünürlük: {goruntu.width}x{goruntu.height}\n")
for dosya in ["ornek.png", "ornek_q85.jpg", "ornek_q60.jpg",
              "ornek_q85.avif", "ornek_q60.avif"]:
    kb = Path(dosya).stat().st_size / 1024
    print(f"{dosya:20s} {kb:8.1f} KB")