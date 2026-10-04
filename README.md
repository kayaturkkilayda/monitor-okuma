# Monitör Görüntü Okuma ve Aktarım Uygulaması

Bu doküman, uygulamanın mevcut geliştirme durumunu ve kullanımını açıklar.

## 1. Projenin amacı

Bu proje, hasta monitörlerinden kamera aracılığıyla alınan görüntülerin Windows üzerinde alınması, yerelde işlenip kuyruklanması ve M4 API'ye gönderilebilmesi için geliştirilmiştir. Sistem iki ana programdan oluşur:

- `motor.exe`
  - Arka planda çalışır.
  - Kameralardan görüntü alır.
  - Görüntüleri işler ve kaydeder.
  - Kuyruk mekanizmasını yönetir.
  - M4 API'ye gönderim yapar.
  - Hata durumlarında tekrar dener.
- `arayuz.exe`
  - Kamera ayarlarını yönetir.
  - Kamera-yatak eşleştirmesini yapar.
  - M4/API ayarlarının girilmesini sağlar.
  - Kamera bağlantısını test eder.
  - Kameraların durumunu gösterir.

## 2. Şu ana kadar yapılanlar

- Python tabanlı uygulama geliştirildi.
- Kamera bağlantısı için yapı hazırlandı.
- Kamera-yatak eşleştirme yapısı hazırlandı.
- Çift çekim mantığı hazırlandı.
- Görüntülerin yerel olarak kaydedilmesi ve kuyruklanması hazırlandı.
- M4 API gönderim altyapısı hazırlandı.
- Geçici ağ/API hatalarında tekrar deneme mekanizması hazırlandı.
- Gönderim kuyruğu, gönderim geçmişi ve olaylar SQLite veritabanında tutuluyor; kalıcı hatalı kayıtlar `hatali` durumuyla işaretleniyor.
- Ayarlar arayüz üzerinden yönetiliyor.
- Kamera ve M4 bilgileri kod içine gömülmeden ayar dosyası üzerinden yönetiliyor.
- Şifrelerin düz metin olarak tutulmaması için Windows DPAPI kullanılıyor.
- Sahte kamera ve sahte M4 ile test ortamı oluşturuldu.
- Otomatik testler yazıldı.
- PyInstaller ile `motor.exe` ve `arayuz.exe` oluşturma işlemi yapıldı.
- Proje Git ile commitlendi ve GitHub repository'sine gönderildi.

## 3. EXE oluşturma sırasında karşılaşılan hata

PyInstaller ile EXE oluşturma sırasında sorun kaynak kod tarafında değil, paketlenmiş EXE çalıştırılırken NumPy'nin native bileşenlerinden birinin Windows tarafından engellenmesidir.

Alınan hata özeti:

`ImportError: DLL load failed while importing _multiarray_umath`

Windows Code Integrity günlüğünde görülen kayıt:

`attempted to load ... numpy\_core\_multiarray_umath.cp314-win_amd64.pyd that did not meet the Enterprise signing level requirements.`

Windows tarafında Smart App Control / uygulama kontrolü, imzasız veya güvenilmeyen bir bileşeni engellemiştir. Önemli ayrım şudur:

- Python ortamındaki NumPy çalışmaktadır.
- OpenCV ve NumPy Python ortamında import edilebilmektedir.
- Sorun, PyInstaller ile paketlenen EXE içindeki NumPy native `.pyd` bileşeninin Windows güvenlik politikası tarafından engellenmesidir.
- EXE üretimi tamamlanmış olsa da bazı makinelerde EXE çalıştırılırken Windows güvenlik politikası engeli oluşabilir.
- Bu durum kaynak kodunun çalışmadığı anlamına gelmez.

Windows güvenlik mekanizmalarının devre dışı bırakılması önerilmez. Kurumsal ortamda kod imzalama ve allowlist gibi BT tarafından uygulanabilecek yöntemler değerlendirilmelidir.

### Çözüm

Paketleme `--onefile` yerine `--onedir` ile yapılınca sorun aşıldı. `--onefile` ile üretilen EXE, bileşenlerini her açılışta geçici bir klasöre çıkarır; güvenlik yazılımları bu davranışı engeller. `--onedir` ile bileşenler kurulum klasöründe sabit olarak durur.

İki programın bileşenleri aynı kurulum klasöründe çakışmasın diye `--contents-directory _motor` ve `--contents-directory _arayuz` seçenekleri kullanılır.

Hastane ortamında imzasız EXE'ler yine engellenebileceği için kod imzalama sertifikası açık konu olarak kalmaktadır.

> **Not (2 Ekim 2026):** Geliştirme bilgisayarında Smart App Control açıkken her yeniden paketleme EXE'nin parmak izini değiştirir ve Windows yeni dosyayı tanımadığı için engelleyebilir. Aynı anda paketlenen `arayuz.exe` çalışırken `motor.exe` "Uygulama Denetimi ilkesi bu dosyayı engelledi" hatasıyla engellendi; karar dosya bazında verildiği için önceden bilinemez. Kalıcı çözüm EXE'leri güvenilir bir kod imzalama sertifikasıyla imzalamaktır. Smart App Control kapatılmamalıdır; Windows'ta bir kez kapatılınca sistem sıfırlanmadan yeniden açılamaz. İmza gelene kadar geliştirme sırasında motor `python main.py` ile çalıştırılır.

## 4. Kurulum klasörü

Beklenen kurulum yapısı aşağıdaki gibidir:

```text
C:\MonitorOkuma
  motor.exe
  arayuz.exe
  _motor/
  _arayuz/
  config/
    ayarlar.json
```

`_motor/` ve `_arayuz/` klasörleri programların çalışması için gereken bileşenleri içerir; silinmemeli veya taşınmamalıdır.

Motor çalıştığında aşağıdaki çalışma klasörleri ve dosyalar oluşabilir:

```text
goruntuler/
veri/
  monitor.db
loglar/
durum.json
```

- `goruntuler/`: Çekilen görüntü dosyaları.
- `veri/monitor.db`: SQLite veritabanı. `kayitlar` tablosu gönderim kuyruğunu ve geçmişini (durum: `bekliyor` / `gonderildi` / `hatali`), `olaylar` tablosu arıza, düzelme, gönderim uyarı/hataları ve motorun başlama/durma/ayar değişikliği olaylarını tutar. Motor ve arayüz aynı anda erişebilsin diye WAL modunda çalışır; motor çalışırken yanında `monitor.db-wal` ve `monitor.db-shm` dosyaları görülmesi normaldir, silinmemelidir.
- `loglar/`: Günlük log dosyaları (olaylar ayrıca burada da yazılır).
- `durum.json`: Motorun kamera durumlarını yazdığı dosya; arayüz kamera durumlarını buradan okur.

Her görüntünün okunabilir bir kimliği vardır ve dosya adı bu kimliktir:

- `kayit_id`: `<tesis>_<kamera>_<yatak>_<tarih>_<saat>_<sıra>`, örn. `H01_K1_Y1_2026-10-02_15-12-13_1`
- `cift_id`: aynı çekimdeki iki kareyi bağlar, ilk karenin zamanıyla ve sırasız: `H01_K1_Y1_2026-10-02_15-12-13`
- Aynı kimlik zaten varsa (örn. motor aynı saniyede yeniden başlarsa) sonuna `_2`, `_3` eklenir.

Veritabanında zamanlar yerel saatle `2026-10-02 15:12:13` biçiminde, saat dilimi ayrı `saat_dilimi` sütununda (`+03:00`) tutulur. M4'e giden `zaman` alanı saat dilimli ISO biçimindedir (`2026-10-02T15:12:13+03:00`). Arayüz tarihleri `02.10.2026 15:12:13` biçiminde gösterir. Eski sürümün UUID'li kayıtları ve görüntü adları motor ilk açıldığında bu biçime çevrilir.

Gönderilen kayıtlar `kayit_saklama_gun` ayarı kadar (varsayılan 90 gün) geçmişte tutulur, sonra temizlik tarafından silinir. Önceki sürümün `bekleyen/` ve `hatali/` klasörlerindeki JSON kayıtları, motor ilk açıldığında veritabanına aktarılır ve klasörler kaldırılır.

> **Dikkat:** Veritabanı motor çalışırken bir SQLite programıyla incelenecekse **salt okunur** açılmalıdır. Düzenleme modunda açık bırakılan bir program veritabanını kilitler ve motor yeni kayıt ekleyemez.

> **Önemli:** Şifreler Windows DPAPI ile o bilgisayara bağlı olarak şifrelenir. `ayarlar.json` başka bir bilgisayara kopyalanırsa şifreler çözülemez ve motor açılmaz. Yeni bilgisayarda `config/ayarlar.ornek.json` kopyalanıp adı `ayarlar.json` yapılmalı; API anahtarı ve kamera şifreleri o bilgisayardaki arayüzden girilmelidir.

## 5. EXE oluşturma

EXE'ler proje klasöründe, sanal ortam etkinken PyInstaller ile oluşturulur. Paketlemeden önce çalışan `motor.exe` ve `arayuz.exe` kapatılmalıdır; aksi halde dosyalar kilitli olduğu için üzerine yazılamaz.

Motor:

```powershell
pyinstaller --onedir --noconsole --name motor --contents-directory _motor --paths src --hidden-import pillow_avif --hidden-import win32crypt main.py
```

Arayüz:

```powershell
pyinstaller --onedir --noconsole --name arayuz --contents-directory _arayuz --paths src --hidden-import pillow_avif --hidden-import win32crypt arayuz.py
```

Seçeneklerin anlamı:

- `--onedir`: Bileşenleri tek EXE içine gömmek yerine klasör olarak çıkarır (bkz. Bölüm 3).
- `--noconsole`: Konsol penceresi açılmaz.
- `--name`: Oluşacak EXE'nin adı.
- `--contents-directory`: Bileşenlerin konulacağı klasörün adı; iki programın bileşenlerinin çakışmasını önler.
- `--paths src`: `src` klasöründeki modüllerin bulunmasını sağlar.
- `--hidden-import pillow_avif`, `--hidden-import win32crypt`: PyInstaller'ın kendiliğinden bulamadığı AVIF desteği ve DPAPI modüllerini pakete ekler.

Çıktılar `dist\motor` ve `dist\arayuz` klasörlerinde oluşur. Bunlar kurulum klasörüne kopyalanır:

```powershell
xcopy /E /I /Y dist\motor C:\MonitorOkuma
xcopy /E /I /Y dist\arayuz C:\MonitorOkuma
```

- `/E`: Alt klasörlerle birlikte kopyalar.
- `/I`: Hedef yoksa klasör olarak oluşturur.
- `/Y`: Var olan dosyaların üzerine sormadan yazar.

Kopyalama `config/` klasörüne dokunmaz; mevcut ayarlar korunur.

## 6. M4 bilgileri nereye girilecek?

M4 bilgileri doğrudan Python koduna yazılmaz. Kullanıcı `arayuz.exe` programını açar ve `Ayarlar` sekmesinden gerekli bilgileri girer.

Bu bölümde en az aşağıdaki yapılandırmalar bulunur:

- Tesis kodu
- M4 API adresi
- API anahtarı
- Çekim aralığı
- İkinci çekim gecikmesi
- Görüntü formatı
- Görüntü kalitesi
- Gönderilen görüntülerin silinme ayarı
- Sahipsiz dosya saklama süresi
- Gönderim kaydı saklama süresi

M4 API'nin gerçek endpoint ve kimlik doğrulama bilgileri geldiğinde bunlar arayüzden girilmelidir. Mevcut gönderim formatı farklıysa yalnızca `src/gonderici.py` içindeki `_gonder` fonksiyonunun uyarlanması gerekebilir.

## 7. Kamera bilgileri nereye girilecek?

Kamera bilgileri de kod içine yazılmaz. `arayuz.exe` içindeki `Kameralar` sekmesinden kamera eklenir.

Kamera eklerken şu bilgiler girilebilir:

- Kamera kodu
- Yatak kodu
- Kamera tipi
- Kamera adresi / IP
- Kullanıcı adı
- Şifre
- Aktif/pasif durumu

Kamera bağlantısı `Bağlantıyı test et` butonu ile kontrol edilir. Test başarılı olduğunda kameradan alınan görüntü görüntülenerek kontrol edilebilir. Gerçek IP kamera kullanılırken snapshot adresi kamera modeline göre belirlenmelidir.

## 8. Uygulama nasıl çalıştırılır?

### Geliştirme ortamında

Proje klasörü: `C:\Projeler\monitor-okuma`

PowerShell'de önce sanal ortam etkinleştirilir:

```powershell
cd C:\Projeler\monitor-okuma
.venv\Scripts\activate
```

Arka plan motoru için ayrı bir PowerShell penceresinde aşağıdaki komut çalıştırılır:

```powershell
python main.py
```

Arayüz için başka bir PowerShell penceresinde:

```powershell
python arayuz.py
```

İlk çalıştırmada ayarlar arayüzden girilir; ardından motor kamera tanımlarını ve M4 ayarlarını `config/ayarlar.json` üzerinden kullanır.

Test ortamında sahte kamera ve sahte M4 aşağıdaki komutlarla ayrı terminallerde başlatılabilir:

```powershell
python araclar\sahte_kamera.py
```

```powershell
python araclar\sahte_m4.py
```

Ardından motor için `python main.py`, arayüz için ise `python arayuz.py` çalıştırılır.


### Kurulu uygulamada

1. `arayuz.exe` açılır.
2. `Ayarlar` sekmesinden M4 bilgileri girilir.
3. `Kameralar` sekmesinden kamera-yatak eşleştirmeleri eklenir ve bağlantılar test edilir.
4. Ayarlar kaydedildikten sonra `motor.exe` çalıştırılır.
5. Motor görüntüleri alır, yerelde kuyruklar ve yapılandırılmış M4 API'ye gönderir.

Motor çalışırken arayüzde yapılan değişiklikleri 5 saniye içinde kendisi algılar; motoru yeniden başlatmaya gerek yoktur. Ayar dosyası hatalıysa motor eski ayarlarla çalışmaya devam eder.

Kurulum klasörü `C:\MonitorOkuma` olduğunda çalıştırılabilir dosyalar şunlardır:

```yaml
C:\MonitorOkuma\motor.exe
```

```yaml
C:\MonitorOkuma\arayuz.exe
```

`motor.exe` arka planda çalışır; pencere göstermemesi normaldir. `arayuz.exe` ise kullanıcı tarafından gerektiğinde açılır.

## 9. Otomatik başlatma

Windows Görev Zamanlayıcı kullanılarak `motor.exe`, bilgisayar açıldığında otomatik başlatılabilir. Görev adı `MonitorGoruntuMotor` olarak tanımlanabilir. Motor, kullanıcı oturum açmasını beklemeden çalışacak biçimde yapılandırılabilir.

Görev, yönetici olarak açılmış bir PowerShell penceresinde aşağıdaki komutlarla oluşturulur:

```powershell
$eylem = New-ScheduledTaskAction -Execute "C:\MonitorOkuma\motor.exe" -WorkingDirectory "C:\MonitorOkuma"
$tetik = New-ScheduledTaskTrigger -AtStartup
$ayar  = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
Register-ScheduledTask -TaskName "MonitorGoruntuMotor" -Action $eylem -Trigger $tetik -Settings $ayar -User "SYSTEM" -RunLevel Highest -Force
```

- `-WorkingDirectory`: Motorun `config/`, `loglar/` ve diğer klasörleri kurulum klasöründe bulması için gereklidir.
- `-AtStartup`: Görev bilgisayar açıldığında, oturum açılmasını beklemeden başlar.
- `-ExecutionTimeLimit ([TimeSpan]::Zero)`: Görev için süre sınırı yoktur; motor sürekli çalışır.
- `-RestartCount 999 -RestartInterval 1 dakika`: Motor kapanırsa her dakika yeniden başlatılmaya çalışılır.
- `-StartWhenAvailable`: Başlangıç zamanı kaçırıldıysa görev ilk fırsatta başlatılır.
- `-User "SYSTEM"`: Görev SYSTEM hesabıyla çalışır.
- `-Force`: Aynı adlı görev varsa üzerine yazılır.

## 10. Test ortamı

Gerçek kamera ve gerçek M4 olmadan sistemi test etmek için `araclar/sahte_kamera.py` ve `araclar/sahte_m4.py` kullanılır.

- Sahte kamera: `http://127.0.0.1:8080/<KOD>/shot.jpg`
- Sahte M4: `http://127.0.0.1:9000/api/goruntu`

Bu dosyalar yalnızca geliştirme ve test amacıyla kullanılır; gerçek kurulum paketinin parçası değildir.

## 11. Gerçek ortama geçiş

1. Gerçek M4 API adresi ve API anahtarı alınır.
2. `arayuz.exe` içindeki `Ayarlar` bölümünden M4 bilgileri girilir.
3. Gerçek IP kameraların IP, kullanıcı adı ve şifre bilgileri alınır.
4. `arayuz.exe` içindeki `Kameralar` bölümünden kameralar eklenir.
5. Kamera-yatak eşleşmeleri yapılır.
6. `Bağlantıyı test et` ile görüntü kontrol edilir.
7. Çekim aralığı gerçek kullanım değerine ayarlanır.
8. `motor.exe` arka planda çalışacak şekilde kurulur.
9. Windows Görev Zamanlayıcı ile otomatik başlatma yapılandırılır.

## 12. Mevcut proje durumu

- Kaynak kod hazır.
- Python ortamında uygulama çalışıyor.
- Sahte kamera ve sahte M4 ile test altyapısı mevcut.
- Otomatik testler mevcut.
- Git repository oluşturuldu.
- İlk commit oluşturuldu.
- GitHub repository oluşturuldu.
- Remote tanımlandı ve mevcut commit GitHub'a gönderildi.
- `--onedir` paketleme ile EXE'ler çalışıyor; hastane bilgisayarları için kod imzalama açık konu olarak kalıyor.
- Gerçek kamera ve gerçek M4 bilgileri girildiğinde mevcut arayüz üzerinden yapılandırma yapılabilir.
