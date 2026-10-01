import cv2
import time

kamera = cv2.VideoCapture(0)

if not kamera.isOpened():
    print("Kamera açılamadı")
    exit()

# Kameranın pozlamayı ayarlaması için bekle
time.sleep(2)

# Isınma kareleri
for _ in range(30):
    basarili, kare = kamera.read()

kamera.release()

if basarili:
    cv2.imwrite("test.jpg", kare)
    print(f"Kare alındı. Boyut: {kare.shape}")
    print(f"Ortalama parlaklık: {kare.mean():.1f}  (0 = tamamen siyah)")
else:
    print("Kare alınamadı")