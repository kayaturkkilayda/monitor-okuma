===============================================================
 ELLE DENEME BETIKLERI  (projenin ilk gunlerinden)
===============================================================

Bu klasordeki dosyalar OTOMATIK TEST DEGILDIR. pytest bunlari
calistirmaz (pytest.ini icinde testpaths = tests yazar).
Otomatik testler tests/ klasorundedir:  python -m pytest

Bunlar, kamera ve goruntu bicimi konularini elle denemek icin
yazilmis kisa betiklerdir. Adlari "test_" ile basliyor cunku
projenin ilk gunlerinde yazildilar; adlari gecmisle baglantisi
kopmasin diye degistirilmedi.

DIKKAT: Hepsi GERCEK donanim ya da calisan bir sunucu ister ve
calistirildiklari klasore dosya yazarlar. Gunluk gelistirme
icin gerekli degildirler.

  test_kamera.py   Bilgisayara takili webcam'den tek kare alir
                   ve test.jpg olarak kaydeder. GERCEK WEBCAM
                   ister.

  test_format.py   Webcam'den bir kare alip ayni goruntuyu PNG,
                   JPG (kalite 85/60) ve AVIF (kalite 85/60)
                   olarak kaydeder; dosya boyutlarini
                   karsilastirmak icindir. GERCEK WEBCAM ister.

  test_modul.py    src/kamera.py icindeki Kamera sinifini webcam
                   ile dener: cift cekim yapar, kaydedici ile
                   diske yazar. GERCEK WEBCAM ister.

  test_ip.py       src/kamera.py icindeki IPKamera sinifini uc
                   kamerayla dener. Once araclar/sahte_kamera.py
                   CALISIYOR OLMALIDIR (port 8080).

NASIL CALISTIRILIR
------------------
Proje ana klasorunden (main.py'nin bulundugu yerden):

    python araclar\elle_denemeler\test_kamera.py

Betikler src/ klasorunu kendileri yola ekler, ama cikti
dosyalarini icinde bulundugunuz klasore yazarlar.
