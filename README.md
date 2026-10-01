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
- Kalıcı hatalar için ayrı hata klasörü kullanılıyor.
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

## 4. Kurulum klasörü

Beklenen kurulum yapısı aşağıdaki gibidir:

```text
C:\MonitorOkuma
  motor.exe
  arayuz.exe
  config/
    ayarlar.json
```

Motor çalıştığında aşağıdaki çalışma klasörleri oluşabilir:

```text
goruntuler/
bekleyen/
hatali/
loglar/
```

## 5. M4 bilgileri nereye girilecek?

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

M4 API'nin gerçek endpoint ve kimlik doğrulama bilgileri geldiğinde bunlar arayüzden girilmelidir. Mevcut gönderim formatı farklıysa yalnızca `src/gonderici.py` içindeki `_gonder` fonksiyonunun uyarlanması gerekebilir.

## 6. Kamera bilgileri nereye girilecek?

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

## 7. Uygulama nasıl çalıştırılır?

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

Kurulum klasörü `C:\MonitorOkuma` olduğunda çalıştırılabilir dosyalar şunlardır:

```yaml
C:\MonitorOkuma\motor.exe
```

```yaml
C:\MonitorOkuma\arayuz.exe
```

`motor.exe` arka planda çalışır; pencere göstermemesi normaldir. `arayuz.exe` ise kullanıcı tarafından gerektiğinde açılır.

## 8. Otomatik başlatma

Windows Görev Zamanlayıcı kullanılarak `motor.exe`, bilgisayar açıldığında otomatik başlatılabilir. Görev adı `MonitorGoruntuMotor` olarak tanımlanabilir. Motor, kullanıcı oturum açmasını beklemeden çalışacak biçimde yapılandırılabilir.

## 9. Test ortamı

Gerçek kamera ve gerçek M4 olmadan sistemi test etmek için `araclar/sahte_kamera.py` ve `araclar/sahte_m4.py` kullanılır.

- Sahte kamera: `http://127.0.0.1:8080/<KOD>/shot.jpg`
- Sahte M4: `http://127.0.0.1:9000/api/goruntu`

Bu dosyalar yalnızca geliştirme ve test amacıyla kullanılır; gerçek kurulum paketinin parçası değildir.

## 10. Gerçek ortama geçiş

1. Gerçek M4 API adresi ve API anahtarı alınır.
2. `arayuz.exe` içindeki `Ayarlar` bölümünden M4 bilgileri girilir.
3. Gerçek IP kameraların IP, kullanıcı adı ve şifre bilgileri alınır.
4. `arayuz.exe` içindeki `Kameralar` bölümünden kameralar eklenir.
5. Kamera-yatak eşleşmeleri yapılır.
6. `Bağlantıyı test et` ile görüntü kontrol edilir.
7. Çekim aralığı gerçek kullanım değerine ayarlanır.
8. `motor.exe` arka planda çalışacak şekilde kurulur.
9. Windows Görev Zamanlayıcı ile otomatik başlatma yapılandırılır.

## 11. Mevcut proje durumu

- Kaynak kod hazır.
- Python ortamında uygulama çalışıyor.
- Sahte kamera ve sahte M4 ile test altyapısı mevcut.
- Otomatik testler mevcut.
- Git repository oluşturuldu.
- İlk commit oluşturuldu.
- GitHub repository oluşturuldu.
- Remote tanımlandı ve mevcut commit GitHub'a gönderildi.
- EXE paketleme yapılabiliyor; ancak Windows üzerindeki Smart App Control / Code Integrity politikası NumPy'nin native bileşenini engelleyebiliyor.
- Gerçek kamera ve gerçek M4 bilgileri girildiğinde mevcut arayüz üzerinden yapılandırma yapılabilir.
