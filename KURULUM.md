# Kurulum ve İlk Kullanım

Bu belge, programı hiç görmemiş birinin baştan sona izleyebilmesi için yazıldı. Yazılım bilgisi
gerekmez. Her adımda ne göreceğiniz de yazıyor; görmediğiniz bir şey varsa
[Sorun giderme](#10-sorun-giderme) bölümüne bakın.

**Yapacaklarınız:** programı indirip açacak, bir yönetici hesabı oluşturacak, ayarları girecek
ve gerçek kamera olmadan sistemi uçtan uca deneyeceksiniz. Yaklaşık 20 dakika sürer.

---

## İçindekiler

1. [Sistem gereksinimleri](#1-sistem-gereksinimleri)
2. [İndirme](#2-i̇ndirme)
3. [ZIP'i açma](#3-zipi-açma)
4. [İlk çalıştırma ve Windows uyarısı](#4-i̇lk-çalıştırma-ve-windows-uyarısı)
5. [İlk yönetici hesabı](#5-i̇lk-yönetici-hesabı)
6. [Ayarlar](#6-ayarlar)
7. [Sahte kamera ve sahte M4 ile deneme](#7-sahte-kamera-ve-sahte-m4-ile-deneme)
8. [Telefonla fotoğraf gönderme](#8-telefonla-fotoğraf-gönderme)
9. [Otomatik başlatma](#9-otomatik-başlatma)
10. [Sorun giderme](#10-sorun-giderme)

---

## 1. Sistem gereksinimleri

| | |
|---|---|
| İşletim sistemi | Windows 10 veya Windows 11 (64 bit) |
| Disk alanı | En az 2 GB boş yer |
| Ekran | En az 1366 × 768 |
| İnternet | Kurulum için gerekmez |
| Python | **Gerekmez.** Programın içinde hazır gelir. |

Denemeyi `araclar/` klasöründeki sahte kamera ve sahte M4 ile yapacaksanız **Python 3.11 veya
üzeri** gerekir. Yoksa [python.org/downloads](https://www.python.org/downloads/) adresinden
indirin; kurulum ekranında **"Add python.exe to PATH"** kutusunu mutlaka işaretleyin.

---

## 2. İndirme

1. Tarayıcıda projenin **Releases** sayfasını açın.
2. En üstteki sürümün altındaki **Assets** başlığına tıklayın.
3. `MonitorOkuma-v1.0.0.zip` dosyasına tıklayıp indirin (yaklaşık 200 MB).

İndirme bittiğinde dosya genelde `C:\Users\<kullanıcı adınız>\Downloads` klasöründe olur.

---

## 3. ZIP'i açma

ZIP'i doğrudan içinden çalıştırmayın; önce dışarı çıkarmanız gerekir.

1. İndirilen `MonitorOkuma-v1.0.0.zip` dosyasına **sağ tıklayın**.
2. **Tümünü ayıkla...** seçeneğini tıklayın.
3. Açılan pencerede hedef klasörü silip şunu yazın:

   ```
   C:\MonitorOkuma
   ```

4. **Ayıkla** düğmesine basın.

> **Neden `C:\MonitorOkuma`?** Program, ayarlarını ve verisini kendi bulunduğu klasörün altına
> yazar. Masaüstü ya da Downloads yerine sabit bir yerde durması, sonradan taşınırken karışıklık
> çıkmasını önler.

Açma bitince `C:\MonitorOkuma` klasöründe şunları görmelisiniz:

```text
C:\MonitorOkuma\
  motor.exe          ← arka planda çalışan program (penceresi yoktur)
  arayuz.exe         ← ayarları girdiğiniz program
  _motor\            ← motor.exe'nin parçaları
  _arayuz\           ← arayuz.exe'nin parçaları
  araclar\           ← sahte kamera ve sahte M4 (deneme için)
  config\
    ayarlar.ornek.json
  KURULUM.md
  README.md
```

> **Önemli:** `_motor\` ve `_arayuz\` klasörleri programların çalışması için gereklidir.
> Silmeyin, taşımayın, yeniden adlandırmayın.

---

## 4. İlk çalıştırma ve Windows uyarısı

`arayuz.exe` dosyasına **çift tıklayın**.

Windows büyük olasılıkla mavi bir pencere açıp şunu yazacak:

> **Windows kişisel bilgisayarınızı korudu**
> Microsoft Defender SmartScreen tanınmayan bir uygulamanın başlatılmasını engelledi.

**Bu normaldir ve virüs anlamına gelmez.** Uygulama bir kod imzalama sertifikasıyla imzalanmadığı
için Windows onu tanımıyor. Devam etmek için:

1. Pencerede **Ek bilgi** yazısına tıklayın.
2. Alt kısımda beliren **Yine de çalıştır** düğmesine basın.

Bunu yalnızca **bir kez** yapmanız yeterlidir; Windows aynı dosyayı bir daha sormaz.

> ### Smart App Control açıksa
>
> Bazı yeni Windows 11 bilgisayarlarda **Smart App Control** (Akıllı Uygulama Denetimi) özelliği
> açıktır. Bu özellik "Yine de çalıştır" seçeneğini hiç göstermeden şöyle bir hata verebilir:
>
> > Uygulama Denetimi ilkesi bu dosyayı engelledi
>
> **Smart App Control'ü KAPATMAYIN.** Windows'ta bu özellik bir kez kapatılırsa, bilgisayar
> baştan kurulmadan yeniden açılamaz. Bunun yerine:
>
> - Programı farklı bir bilgisayarda deneyin, **ya da**
> - Kurumunuzun BT birimine başvurun: kalıcı çözüm, uygulamanın güvenilir bir **kod imzalama
>   sertifikasıyla imzalanmasıdır**.
>
> Hangi Windows sürümünde olduğunuzu görmek için: **Ayarlar → Gizlilik ve güvenlik → Windows
> Güvenliği → Uygulama ve tarayıcı denetimi → Akıllı Uygulama Denetimi ayarları**.

---

## 5. İlk yönetici hesabı

`arayuz.exe` ilk kez açıldığında **İlk yönetici hesabını oluştur** ekranı gelir.

![Giriş ekranı](docs/ekranlar/0-giris.png)

Doldurun:

| Alan | Ne yazılır |
|---|---|
| E-posta | Kendi çalışma e-postanız. Bildirimler ve onay kodları buraya gelecek. |
| Ad soyad | Adınız. |
| Şifre | En az 8 karakter. |
| Şifre (tekrar) | Aynısını bir daha. |

**Hesabı oluştur** düğmesine basın. Bu ilk hesap otomatik olarak **yönetici** olur ve e-posta
doğrulaması istemez (henüz e-posta ayarı girilmediği için).

> Sonradan eklenecek kullanıcılar e-postalarına gelen 6 haneli kodu girerek kayıt olur. Bunun
> çalışması için önce [Ayarlar'daki e-posta bölümünü](#e-posta-smtp) doldurmanız gerekir.

**Beni hatırla** kutusu işaretliyse bu bilgisayarda bir daha şifre sorulmaz.

---

## 6. Ayarlar

Giriş yaptıktan sonra **Ayarlar** sekmesine geçin. Bu sekme yalnızca yöneticilere görünür.

![Ayarlar sekmesi](docs/ekranlar/4-ayarlar.png)

### Genel ayarlar

| Alan | Anlamı | Önerilen |
|---|---|---|
| **Tesis kodu** | Hastaneyi/birimi ayırt eden kısa kod. Görüntü adlarında ve M4'e giden veride kullanılır. | `TEST` (deneme için) |
| **M4 API adresi** | Görüntülerin gönderileceği adres. Boş bırakılırsa görüntüler kuyrukta birikir, gönderilmez. | `http://127.0.0.1:9000/api/goruntu` |
| **API anahtarı** | M4'ün istediği kimlik anahtarı. Şifreli saklanır. | `test-anahtar` |
| **Çekim aralığı (sn)** | Kaç saniyede bir çekim yapılacağı. | `60` |
| **İkinci çekim gecikmesi (sn)** | Çift çekimde iki kare arası süre. | `5` |
| **Görüntü formatı** | `avif` daha küçük dosya, `jpg` daha yaygın. | `avif` |
| **Kalite (1-100)** | Yüksek = net ama büyük dosya. | `85` |
| **Sahipsiz dosya saklama (gün)** | Kaydı olmayan görüntü dosyaları kaç gün sonra silinsin. | `7` |
| **Gönderim kaydı saklama (gün)** | Gönderilmiş kayıtlar kaç gün geçmişte tutulsun. | `90` |
| **Kayıt için izin verilen alan adları** | Yalnızca bu alan adlarıyla biten e-postalar kayıt olabilir. Boş bırakılırsa herkes kayıt olabilir. | Kurumunuzun alan adı |
| **Gönderilen görüntüleri hemen sil** | İşaretliyse gönderilen dosya hemen silinir, disk şişmez. | İşaretli |

### E-posta (SMTP)

Arıza bildirimleri, kamera onay kodları ve kullanıcı kayıt kodları bu ayarla gönderilir.
Doldurmazsanız program çalışır, yalnızca e-posta gönderemez.

| Alan | Ne yazılır |
|---|---|
| **Sunucu** | Örn. `smtp.gmail.com` veya kurumunuzun posta sunucusu |
| **Port** | Güvenlik seçimine göre kendiliğinden dolar (STARTTLS → 587) |
| **Güvenlik** | Genelde `STARTTLS` |
| **Kullanıcı adı** | Gönderen e-posta adresi. **Mailler bu adresten gider.** |
| **Şifre** | Posta hesabının şifresi. Şifreli saklanır. |

**Test maili gönder** düğmesiyle ayarları hemen deneyebilirsiniz; sonuç düğmenin altında yazar.

> Bildirimler ayrıca sorulmaz: ayarları kaydeden yöneticinin adresine gider.

En alttaki **Kaydet** düğmesine basın. "Ayarlar kaydedildi" mesajını görmelisiniz.

---

## 7. Sahte kamera ve sahte M4 ile deneme

Gerçek kamera ve gerçek M4 olmadan sistemin uçtan uca çalıştığını görmek için `araclar/`
klasöründeki iki yardımcı programı kullanacağız. İkisi de yalnızca **bu bilgisayarda** çalışır,
dışarıya hiçbir bağlantı açmaz.

### 7.1 Sahte kamerayı başlatın

`C:\MonitorOkuma\araclar\` klasörünü açın ve şu dosyaya çift tıklayın:

```
1_baslat_sahte_kamera.bat
```

Siyah bir komut penceresi açılır. **Bu pencereyi kapatmayın.** Doğru çalıştığını kontrol etmek
için tarayıcıda şu adresi açın:

```
http://127.0.0.1:8080/K1/shot.jpg
```

Üzerinde HR / SpO2 / NIBP değerleri yazan, monitöre benzeyen siyah bir görüntü görmelisiniz.
Sayfayı her yenilediğinizde değerler değişir.

### 7.2 Sahte M4'ü başlatın

Aynı klasörde ikinci dosyaya çift tıklayın:

```
2_baslat_sahte_m4.bat
```

İkinci bir siyah pencere açılır. **Bunu da kapatmayın.**

> İlk başlatmada Windows **Güvenlik Duvarı erişimi** sorabilir. Deneme için **"Özel ağlar"**
> seçeneği yeterlidir.

### 7.3 Hazır test ayarını yükleyin

`araclar\ayarlar.test.json` dosyası, sahte kamera ve sahte M4'e işaret eden hazır bir ayardır.

1. `araclar\ayarlar.test.json` dosyasını **kopyalayın**.
2. `C:\MonitorOkuma\config\` klasörüne **yapıştırın**.
3. Yapıştırdığınız dosyanın adını `ayarlar.json` olarak **değiştirin**.

> **Dikkat:** `config\ayarlar.json` zaten varsa üzerine yazılır. Kendi ayarlarınızı girdiyseniz
> önce bir yedeğini alın.

### 7.4 Motoru çalıştırın

`C:\MonitorOkuma\motor.exe` dosyasına çift tıklayın. **Penceresi açılmaz** — bu normaldir,
motor arka planda çalışır.

### 7.5 Çalıştığını nasıl anlarsınız

**Sahte M4 penceresinde** şuna benzer satırlar düşmeye başlar:

```
ALINDI TEST/K1/Y1 sira=1 zaman=... 21.3 KB
```

**`arayuz.exe` içinde:**

- **Kameralar** sekmesinde `K1` satırı yeşile döner, "Çalışıyor" yazar.
- **Kayıtlar** sekmesinde günlere göre gönderim kayıtları birikir.
- **Loglar** sekmesinde olaylar akar.

![Kayıtlar sekmesi](docs/ekranlar/2-kayitlar.png)

### 7.6 "Gönderilemedi" uyarıları normaldir

Loglarda şöyle sarı satırlar göreceksiniz:

```
Y1 #1 | gönderilemedi (HTTP 503), 1. deneme, 10 sn sonra tekrar
Y1 #1 | gönderildi
```

Bu bir **arıza değildir**. Sahte M4, gelen isteklerin yaklaşık %20'sine bilerek hata döndürür
(`araclar/sahte_m4.py` içindeki `HATA_ORANI = 0.2`). Amaç, motorun tekrar deneme mantığının
çalıştığını göstermektir. Kapatmak isterseniz o satırı `0` yapın.

### 7.7 Denemeyi bitirme

1. Görev Yöneticisi'ni açın (Ctrl + Shift + Esc), **motor.exe**'yi bulup **Görevi sonlandır** deyin.
2. İki siyah komut penceresini kapatın.
3. Deneme sırasında oluşan `veri\`, `loglar\`, `goruntuler\` klasörleri ve `durum.json` dosyası
   silinebilir.

---

## 8. Telefonla fotoğraf gönderme

Kamera takılamayan bir yatak için, telefonla fotoğraf çekip sisteme yükleyebilirsiniz. Bu özellik
**varsayılan olarak kapalıdır**, çünkü açıldığında bilgisayar yerel ağa bir port açar.

**Açmak için:**

1. **Ayarlar** sekmesinde **"Telefondan fotoğraf yüklemeyi aç"** kutusunu işaretleyin.
2. Port alanını `8099` olarak bırakın.
3. **Kaydet**'e basın ve `motor.exe`'yi yeniden başlatın.

**Kullanmak için:**

1. **Kameralar** sekmesinde bir yatak seçin, **QR göster** düğmesine basın.
2. Açılan pencereden QR kodu **PNG olarak kaydet**ip yazdırın, yatak başına asın.
3. Telefonun kamerasıyla QR'ı okutun; açılan sayfadan fotoğraf çekip gönderin.

QR kod yalnızca o yatağın adresini taşır; şifre ya da hasta bilgisi içermez. Adresi açan kişiden
ayrıca giriş istenir.

> **Güvenlik notu:** Bu bağlantı şifresiz HTTP'dir. Yalnızca güvendiğiniz bir hastane ağında ve
> ihtiyaç duyulan süre boyunca açık tutun. Misafir ağı ya da internete açık bir ağda kullanmayın.

---

## 9. Otomatik başlatma

Motorun bilgisayar her açıldığında kendiliğinden başlaması için Windows Görev Zamanlayıcı
kullanılır.

1. Başlat menüsüne `PowerShell` yazın.
2. **Windows PowerShell**'e sağ tıklayıp **Yönetici olarak çalıştır** deyin.
3. Aşağıdaki dört satırı kopyalayıp yapıştırın ve Enter'a basın:

```powershell
$eylem = New-ScheduledTaskAction -Execute "C:\MonitorOkuma\motor.exe" -WorkingDirectory "C:\MonitorOkuma"
$tetik = New-ScheduledTaskTrigger -AtStartup
$ayar  = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
Register-ScheduledTask -TaskName "MonitorGoruntuMotor" -Action $eylem -Trigger $tetik -Settings $ayar -User "SYSTEM" -RunLevel Highest -Force
```

Son satırdan sonra görev adını içeren bir çıktı görürseniz kurulum tamamdır. Motor bundan sonra
bilgisayar açılışında, kimse oturum açmasa bile başlar; kapanırsa her dakika yeniden denenir.

**Kaldırmak için** (yine yönetici PowerShell'de):

```powershell
Unregister-ScheduledTask -TaskName "MonitorGoruntuMotor" -Confirm:$false
```

---

## 10. Sorun giderme

### "Uygulama Denetimi ilkesi bu dosyayı engelledi"
Smart App Control açık. [Bölüm 4'teki uyarıya](#4-i̇lk-çalıştırma-ve-windows-uyarısı) bakın.
**Smart App Control'ü kapatmayın.**

### `arayuz.exe` açılmıyor, hiçbir şey olmuyor
`_arayuz\` klasörünün `arayuz.exe` ile aynı yerde durduğundan emin olun. ZIP'i açarken yalnızca
EXE dosyaları kopyalandıysa program açılmaz.

### `motor.exe` çalışıyor ama hiç görüntü gelmiyor
- **Kameralar** sekmesinde kamera "Onay bekliyor" durumunda olabilir. Onaysız kamera çekim
  yapmaz. Kamerayı seçip **Onay kodunu gir** düğmesini kullanın (kod e-postanıza gelir).
- Kamera "Pasif" olabilir: kamerayı düzenleyip **Aktif** kutusunu işaretleyin.
- Sahte kamera penceresi kapanmış olabilir.

### Görüntüler birikiyor ama M4'e gitmiyor
**Ayarlar → M4 API adresi** boş olabilir. Boşken motor çekim yapar ama göndermez; görüntüler
kuyrukta bekler. Adresi girip kaydedin, motor 5 saniye içinde kendiliğinden fark eder.

### "Ayarlar kaydedilemedi" / motor açılmıyor, şifreler çözülemiyor
`config\ayarlar.json` dosyasını **başka bir bilgisayardan kopyaladıysanız** bu olur. Şifreler
Windows DPAPI ile o bilgisayara bağlı olarak şifrelenir. Çözüm: `config\ayarlar.ornek.json`
dosyasını `ayarlar.json` adıyla kopyalayın ve API anahtarı ile şifreleri bu bilgisayarda yeniden
girin.

### Kayıt olurken "bu alan adı kabul edilmiyor" diyor
**Ayarlar → Kayıt için izin verilen alan adları** listesinde o e-postanın alan adı yok. Yönetici
olarak listeye ekleyin ya da listeyi boşaltın.

### E-posta gitmiyor, kod gelmiyor
**Ayarlar → E-posta (SMTP)** bölümündeki **Test maili gönder** düğmesine basın; hata mesajı
düğmenin altında yazar. Gmail kullanıyorsanız normal hesap şifresi değil, **uygulama şifresi**
gerekir.

### Hesabım kilitlendi
Art arda çok hatalı şifre girildiğinde hesap geçici olarak kilitlenir. Birkaç dakika bekleyin ya
da **Şifremi unuttum** ile sıfırlayın.

### Veritabanına bakmak istiyorum
`veri\monitor.db` dosyasını bir SQLite programıyla açabilirsiniz, ama **salt okunur** modda açın.
Düzenleme modunda açık bırakılan program veritabanını kilitler ve motor yeni kayıt ekleyemez.

### Her şeyi sıfırlamak istiyorum
`motor.exe`'yi kapatın, sonra şu klasör ve dosyaları silin: `veri\`, `loglar\`, `goruntuler\`,
`durum.json`, `config\ayarlar.json`. Program bir sonraki açılışta sıfırdan başlar (kullanıcı
hesapları da silinir).

---

**Daha fazlası:** [README.md](README.md) (genel bakış) ·
[PROJE_TANITIM.md](PROJE_TANITIM.md) (teknik ayrıntılar) ·
[araclar/README.txt](araclar/README.txt) (test araçları)
