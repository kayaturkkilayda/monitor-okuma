===============================================================
 TEST ARACLARI  (sahte kamera + sahte M4)
 SADECE DEMO / TEST AMACLIDIR
===============================================================

Bu klasordeki araclar, gercek bir IP kameraya ve gercek M4
(HBYS) sunucusuna ihtiyac duymadan sistemi uctan uca denemek
icindir. Urunun bir parcasi DEGILDIR, hastanede kurulmaz.


TAMAMEN LOCAL CALISIRLAR
------------------------
Iki arac da yalnizca bu bilgisayarda bir port DINLER. Hicbir
yere baglanti ACMAZLAR: internet, sirket sunucusu, baska bir
bilgisayar ya da dis servis gerekmez.

  sahte_kamera.py   dinler: port 8080
                    adres : http://127.0.0.1:8080/<KAMERA>/shot.jpg
                    ornek : http://127.0.0.1:8080/K1/shot.jpg

  sahte_m4.py       dinler: port 9000
                    adres : http://127.0.0.1:9000/api/goruntu
                    API anahtari: test-anahtar

Not: ikisi de 0.0.0.0 (tum ag arayuzleri) uzerinden dinler, yani
ayni agdaki baska bir bilgisayardan da erisilebilir. Windows ilk
baslatmada "Guvenlik Duvari erisimi" sorabilir; test icin "Ozel
aglar" yeterlidir. Testi bitirince pencereleri kapatin.


GEREKSINIMLER
-------------
Python 3.11 veya uzeri (gelistirme 3.14.2 ile yapildi).
Indirme: https://www.python.org/downloads/
Kurulumda "Add python.exe to PATH" secenegi isaretlenmeli.

Gereken paketler (requirements.txt icinde sabitlenmistir):
  sahte_kamera.py  ->  numpy, opencv-python
  sahte_m4.py      ->  Flask

Kurulum:
  python -m pip install -r requirements.txt

Asagidaki .bat dosyalari bu kurulumu gerekirse kendisi yapar.


NASIL BASLATILIR
----------------
Iki ayri pencerede, sirayla cift tiklayin:

  1_baslat_sahte_kamera.bat
  2_baslat_sahte_m4.bat

Her ikisi de kendi penceresinde acik KALMALIDIR. Kapatirsaniz
motor goruntu alamaz / gonderemez.

Elle baslatmak isterseniz:
  python sahte_kamera.py
  python sahte_m4.py


DOGRU CALISTIGI NASIL ANLASILIR
-------------------------------
Sahte kamera: tarayicida su adresi acin
  http://127.0.0.1:8080/K1/shot.jpg
Uzerinde HR / SpO2 / NIBP degerleri yazan, monitore benzeyen
siyah bir goruntu gormelisiniz. Her yenilemede degerler degisir.

Sahte M4: motor gonderim yapmaya basladiginda bu pencereye
  ALINDI TEST/K1/Y1 sira=1 zaman=... 21.3 KB
satirlari dusmeye baslar.


BILEREK EKLENEN HATA
--------------------
sahte_m4.py gelen isteklerin yaklasik %20'sine HTTP 503
dondurur (HATA_ORANI = 0.2). Bu bir ariza degil, kasitlidir:
motorun "gonderilemedi, tekrar denenecek" mantigini test eder.
Loglarda sunu gormek NORMALDIR ve dogru davranistir:

  WARNING | TEST/K1/Y1 #1 | gonderilemedi (HTTP 503), 1. deneme,
            10 sn sonra tekrar
  INFO    | TEST/K1/Y1 #1 | gonderildi

Hata oranini kapatmak isterseniz sahte_m4.py icindeki
HATA_ORANI = 0.2 satirini 0 yapin.

Ayni goruntu ikinci kez gonderilirse sahte M4 "zaten alindi"
yanitini verir; mukerrer kayit olusmaz.


HAZIR TEST AYARI
----------------
ayarlar.test.json dosyasi, sahte kamera ve sahte M4'e isaret
eden hazir bir ayardir (tesis kodu TEST, K1 kamerasi onayli).
Uygulamayi hizlica calistirmak icin ana klasordeki README.txt
icindeki "HIZLI YOL" adimlarina bakin.

Icinde gercek adres, sifre, API anahtari ya da hasta verisi
YOKTUR; api_key degeri sahte M4'un bekledigi "test-anahtar"dir.
