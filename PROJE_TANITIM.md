# Monitör Görüntü Aktarımı — Proje Tanıtımı

> **Bu dosya ne işe yarar?**
> Yeni bir yapay zekâ sohbeti açtığımda projeyi sıfırdan anlatmak zorunda kalmayayım diye hazırlandı.
> Bu dosyayı sohbete ekleyip "bu projede çalışıyorum" demem yeterli.
>
> **Yapay zekâya not:** Aşağıdakiler projenin bağlamıdır, görev listesi değildir. Okuduktan sonra
> beklemeye geç ve ne isteyeceğimi sor. Kodu görmeden varsayımda bulunma; dosya adı, fonksiyon
> veya ayar belirtirken bu dosyadaki haritaya bak. Benimle **sade Türkçe** konuş, adımları
> öğrenciye anlatır gibi açıkla.

---

## 1. Proje tek cümleyle

Hastane yoğun bakımındaki **hasta başı monitörlerin ekranını IP kameralarla belirli aralıklarla
fotoğraflayan**, görüntüyü hasta/yatak bilgisiyle eşleştirip **hastanenin M4 (HBYS) sistemine
otomatik gönderen** bir Windows uygulaması.

**Neden gerekli:** Monitörlerin çoğunda veri çıkışı (dijital entegrasyon) yok. Hemşirenin elle
deftere yazdığı değerler yerine, monitörün ekranının fotoğrafı periyodik olarak hasta dosyasına
düşsün isteniyor.

**Kim yazıyor:** Tek kişilik bir proje; yazan kişi (ben) öğrenme aşamasında. Bu yüzden anlatımın
sade ve gerekçeli olması önemli.

---

## 2. İki program, tek kurulum

Uygulama **iki ayrı çalıştırılabilir dosyadan** oluşur. İkisi aynı klasörde durur, aynı ayar
dosyasını ve aynı veritabanını kullanır, ama birbirinden bağımsız çalışır.

| | `motor.exe` | `arayuz.exe` |
|---|---|---|
| Giriş noktası | `main.py` | `arayuz.py` |
| Penceresi | **Yok** (arka planda) | Var (Tkinter) |
| Ne yapar | Görüntü çeker, kuyruklar, M4'e gönderir, tekrar dener, temizler, e-posta bildirir | Ayar girişi, kamera yönetimi, kullanıcı girişi, durum/kayıt/log izleme |
| Ne zaman çalışır | Sürekli (Görev Zamanlayıcı ile açılışta başlar) | Kullanıcı gerektiğinde açar |

**Aralarındaki bağ:**
- Ayarlar `config/ayarlar.json` dosyasında. Arayüz yazar, motor okur.
- Motor ayar dosyasını **5 saniyede bir kontrol eder**; değişirse kendini yeni ayarlarla yeniden
  başlatır. Motoru elle yeniden başlatmaya gerek yok. Ayar dosyası bozuksa motor eski ayarlarla
  devam eder (çökmez).
- Durum paylaşımı `durum.json` üzerinden: motor kamera durumlarını yazar, arayüz okuyup gösterir.
- Kayıtlar ve olaylar SQLite'ta (`veri/monitor.db`). İkisi aynı anda erişebilsin diye **WAL modu**
  açık; yanında `monitor.db-wal` ve `-shm` dosyalarının görünmesi normaldir, silinmemeli.

> **Kural:** Motor ve arayüz aynı anda çalışır. Yeni kod yazarken ikisinin birbirini kilitlememesi
> gözetilmeli.

---

## 3. Görüntünün yolculuğu (ana akış)

```
IP kamera
   │  (snapshot URL'den JPEG)
   ▼
kamera.py ──► her kamera için ayrı iş parçacığı (zamanlayici.py)
   │          çekim aralığı: varsayılan 60 sn
   │          "çift çekim": birkaç saniye arayla 2 kare
   ▼
kaydedici.py ──► goruntuler/<tarih>/<yatak>/ altına diske yaz
   │             format: AVIF (veya JPG), kalite ayarlanabilir
   ▼
veritabani.py ──► kayitlar tablosuna "bekliyor" olarak ekle
   │
   ▼
gonderici.py ──► M4 API'ye POST
   │              başarılı → durum "gonderildi"
   │              geçici hata (HTTP 503 vb.) → 10 sn sonra tekrar dene
   │              kalıcı hata → durum "hatali"
   ▼
temizlik.py ──► eski görüntüleri ve eski kayıtları sil
                 (saklama_gun: 7, kayit_saklama_gun: 90)
```

**Çift çekim neden var:** Monitör ekranı o an alarm/menü gösteriyor olabilir. İki kare arasında
birkaç saniye bırakılarak en az birinin okunabilir olma ihtimali artırılıyor. İki kare `cift_id`
ile birbirine bağlanıyor.

**Kamera arızası:** `durum.py` kameranın sağlığını izler. Yanıt vermemeye başlarsa **ARIZA**,
düzelince **DÜZELDİ** olayı üretir ve `bildirim.py` e-posta yollar. Bildirimler veritabanında
kuyruklanır, SMTP o an çalışmasa bile kaybolmaz.

---

## 4. Teknoloji

- **Python 3.14.2**, sanal ortam `.venv` içinde
- **Tkinter** (ttk) — arayüz; ek GUI kütüphanesi yok
- **OpenCV + NumPy** — kameradan görüntü alma
- **Pillow** — görüntü sıkıştırma (AVIF desteği Pillow 12 ile hazır gelir)
- **pillow-heif** — iPhone fotoğrafları (HEIC) için
- **requests** — M4 API'ye gönderim
- **pywin32** — Windows DPAPI ile şifreleme
- **SQLite** (Python'un kendi `sqlite3`'ü) — veritabanı, WAL modunda
- **pytest** — testler
- **PyInstaller** — EXE paketleme
- Geliştirme için: **Flask** (sahte M4), **aiosmtpd** (sahte SMTP)

Sürümler `requirements.txt` içinde sabitlenmiş. `requirements-dev.txt` bunun üstüne test ve
paketleme araçlarını ekler.

---

## 5. Dosya haritası

```
C:\Projeler\monitor-okuma\
├── main.py              Motor giriş noktası (106 satır)
├── arayuz.py            Arayüz giriş noktası, sekmeleri kurar (498 satır)
├── config/
│   ├── ayarlar.json         Gerçek ayarlar — GIT'E GİRMEZ
│   └── ayarlar.ornek.json   Boş şablon
├── src/                 27 modül, aşağıda
├── tests/               27 test dosyası, 359 test
├── araclar/             Sahte kamera + sahte M4 (sadece test)
└── .venv/
```

### `src/` modülleri

**Çekim ve gönderim (motor tarafı)**
| Dosya | İş |
|---|---|
| `kamera.py` | Kameradan görüntü alma |
| `zamanlayici.py` | Her kamera için ayrı iş parçacığında periyodik çekim |
| `kaydedici.py` | Kareyi diske kaydetme |
| `gonderici.py` | Kuyruğa yazma ve kuyruktan M4'e gönderme |
| `durum.py` | Kamera sağlık takibi; arıza/düzelme anlarını yakalar |
| `temizlik.py` | Eski görüntü ve kayıtların silinmesi |
| `bildirim.py` | ARIZA/DÜZELDİ e-postaları (SMTP) |

**Altyapı**
| Dosya | İş |
|---|---|
| `veritabani.py` | SQLite şeması ve bağlantı |
| `ayarlar.py` | Ayar dosyasını okuma/yazma, kamera nesnesi üretme |
| `sifreleme.py` | Windows DPAPI ile şifreleme/çözme |
| `kimlik.py` | Okunabilir kayıt kimlikleri |
| `zaman.py` | Zaman biçimleri |
| `log.py` | Loglama ayarları |
| `gecis.py` | Eski biçimlerden yeniye tek seferlik veri göçü (motor açılışında) |

**Kullanıcı ve yetki**
| Dosya | İş |
|---|---|
| `kullanicilar.py` | Kayıt, e-posta doğrulama, giriş, kilitlenme, şifre sıfırlama |
| `giris_ekrani.py` | Giriş penceresi (ilk yönetici / giriş / kayıt / kod / sıfırlama) |
| `oturum.py` | "Beni hatırla" — cihazda kalıcı oturum |
| `onay.py` | Kamera kullanım onayı kontrolü |
| `kamera_onay.py` | Onayın e-posta koduyla alınması |

**Arayüz parçaları** — *her sekme kendi dosyasında*
| Dosya | İş |
|---|---|
| `ayar_sekmesi.py` | Ayarlar sekmesi (yalnızca yönetici) |
| `kayitlar_sekmesi.py` | Kayıtlar sekmesi — gönderim kuyruğu ve geçmişi |
| `loglar_sekmesi.py` | Loglar sekmesi — olaylar tablosu |
| `kullanicilar_sekmesi.py` | Kullanıcılar sekmesi (yalnızca yönetici) |
| `eposta_bolumu.py` | Ayarlar içindeki SMTP bölümü |
| `eposta_girisi.py` | E-posta alanı: biçim denetimi + alan adı önerisi |
| `onizleme.py` | Görüntüyü ayrı pencerede gösterme |
| `arka_plan.py` | Uzun işi pencereyi dondurmadan çalıştırma |

---

## 6. Veritabanı

`veri/monitor.db` — 7 tablo:

| Tablo | İçerik |
|---|---|
| `kayitlar` | Gönderim kuyruğu ve geçmişi. Durum: `bekliyor` / `gonderildi` / `hatali` |
| `olaylar` | Arıza, düzelme, uyarı, hata, motor başlama/durma/ayar değişikliği |
| `bildirimler` | E-posta kuyruğu (SMTP erişilemezse kaybolmasın diye kalıcı) |
| `kullanicilar` | Hesaplar ve roller |
| `dogrulama_kodlari` | E-posta ile gelen kayıt/sıfırlama kodları |
| `kamera_onay_kodlari` | Kamera kullanım onay kodları |
| `oturumlar` | "Beni hatırla" — cihazdaki anahtarın yalnızca hash'i saklanır |

### Kimlikler ve zaman

Her görüntünün okunabilir bir kimliği var ve dosya adı bu kimlik:

- `kayit_id` = `<tesis>_<kamera>_<yatak>_<tarih>_<saat>_<sıra>`
  → `H01_K1_Y1_2026-10-02_15-12-13_1`
- `cift_id` = aynı çekimin iki karesini bağlar (sırasız)
  → `H01_K1_Y1_2026-10-02_15-12-13`
- Aynı kimlik zaten varsa sonuna `_2`, `_3` eklenir.

Zaman biçimleri bilinçli olarak üç yerde farklı:
- **Veritabanı:** `2026-10-02 15:12:13`, saat dilimi ayrı sütunda (`+03:00`)
- **M4'e giden:** ISO + saat dilimi → `2026-10-02T15:12:13+03:00`
- **Arayüzde görünen:** `02.10.2026 15:12:13`

> **Dikkat:** Veritabanı motor çalışırken bir SQLite programıyla açılacaksa **salt okunur**
> açılmalı. Düzenleme modunda açık kalan program veritabanını kilitler, motor kayıt ekleyemez.

---

## 7. Güvenlik ve gizlilik — pazarlık edilmez kurallar

Bu bir **hasta verisi** uygulaması. Aşağıdakiler proje kuralıdır:

1. **Sır asla loga veya ekrana yazılmaz.** Şifre, API anahtarı, SMTP şifresi, doğrulama kodu —
   hiçbiri log dosyasına, konsola veya arayüze düşmez.
2. **Sırlar diske şifreli yazılır.** `src/sifreleme.py` Windows DPAPI kullanır. Şifreli değerler
   `dpapi:` önekiyle saklanır; önek yoksa değer düz metin kabul edilir ve olduğu gibi döner.
3. **DPAPI makineye bağlıdır.** `ayarlar.json` başka bilgisayara kopyalanırsa şifreler çözülemez
   ve motor açılmaz. Yeni makinede `ayarlar.ornek.json` kopyalanıp sırlar arayüzden yeniden girilir.
4. **Onaysız kameradan görüntü alınmaz.** Her kamera için e-posta koduyla kullanım onayı gerekir.
   Onay yoksa motor o kamerayı atlar.
5. **`config/ayarlar.json` git'e girmez** (`.gitignore`'da). Aynı şekilde `veri/`, `loglar/`,
   `goruntuler/`, `durum.json` da girmez.

### Kullanıcılar ve roller

- İlk açılışta **ilk yönetici hesabı** oluşturulur.
- Kayıt e-posta + şifre ile; e-postaya gelen kodla doğrulanır.
- **Rol: Yönetici / normal kullanıcı.** `Ayarlar` ve `Kullanıcılar` sekmeleri **yalnızca
  yöneticide görünür**.
- **İzin verilen alan adları:** Yönetici birden fazla alan adı tanımlayabilir (`kurum1.com.tr`
  gibi). Liste **boşsa** her geçerli e-posta kayıt olabilir; **doluysa** yalnızca listedekiler.
- Art arda hatalı girişte hesap kilitlenir.

---

## 8. Arayüz sekmeleri

| Sekme | Kim görür | İçerik |
|---|---|---|
| **Kameralar** | Herkes | Kamera ekle/düzenle/sil, bağlantı testi, anlık durum, kullanım onayı |
| **Kayıtlar** | Herkes | Gönderim kuyruğu ve geçmişi, görüntü önizleme |
| **Loglar** | Herkes | Olaylar tablosu |
| **Ayarlar** | **Yalnızca yönetici** | Tesis kodu, M4 API, SMTP, izin verilen alan adları, çekim ayarları |
| **Kullanıcılar** | **Yalnızca yönetici** | Hesaplar, yönetici yapma |

> **Kural:** Her yeni sekme `src/` altında **kendi dosyası** olur. `arayuz.py` yalnızca sekmeleri
> kurar, içerik mantığı barındırmaz.

---

## 9. Nasıl çalıştırılır

### Geliştirme ortamı

```powershell
cd C:\Projeler\monitor-okuma
.venv\Scripts\activate

python main.py      # motor   (bir pencerede)
python arayuz.py    # arayüz  (başka pencerede)
```

İlk kurulumda: `python -m venv .venv` → `pip install -r requirements-dev.txt`

### Gerçek kamera olmadan uçtan uca test

`araclar/` klasöründe iki sahte sunucu var. İkisi de **tamamen local** çalışır, hiçbir yere
bağlanmaz:

- `sahte_kamera.py` → port **8080**, `http://127.0.0.1:8080/K1/shot.jpg`
  Siyah zeminde HR / SpO2 / NIBP yazan, monitöre benzeyen görüntü üretir.
- `sahte_m4.py` → port **9000**, `http://127.0.0.1:9000/api/goruntu`, API anahtarı `test-anahtar`

Adımlar:
1. `araclar\1_baslat_sahte_kamera.bat` ve `araclar\2_baslat_sahte_m4.bat` — pencereler açık kalsın
2. `araclar\ayarlar.test.json` → `config\ayarlar.json` olarak kopyala
3. `python main.py`

> **Sahte M4 isteklerin ~%20'sine HTTP 503 döner** (`HATA_ORANI = 0.2`). Bu bilerek eklenmiş bir
> hatadır; motorun "gönderilemedi, tekrar denenecek" mantığını sınar. Loglarda görmek normaldir.

> **Önemli davranış:** Motor açılırken `os.chdir` ile **kendi bulunduğu klasöre geçer**
> (`main.py:8-9`). Yani ayar dosyasını her zaman `main.py`'nin (ya da EXE'nin) yanındaki
> `config/ayarlar.json`'dan okur — nereden başlatıldığının önemi yoktur.

### Testler

```powershell
pytest
```
Şu an **359 test**, 27 dosya. Proje kuralı: **her değişiklikten sonra çalıştır, test sayısı
düşmesin, her yeni özellik için test yaz.**

### EXE paketleme

```powershell
pyinstaller --onedir --noconsole --name motor  --contents-directory _motor  --paths src --hidden-import win32crypt main.py
pyinstaller --onedir --noconsole --name arayuz --contents-directory _arayuz --paths src --hidden-import win32crypt arayuz.py
```

- `--onedir` şart: `--onefile` her açılışta geçici klasöre açtığı için güvenlik yazılımları
  engelliyordu.
- `--contents-directory` ayrı: iki programın bileşenleri aynı klasörde çakışmasın diye.
- Paketlemeden önce çalışan EXE'ler kapatılmalı, yoksa dosyalar kilitli.

Çıktı `dist\motor` ve `dist\arayuz` → `C:\MonitorOkuma` klasörüne kopyalanır (`config/`'e
dokunulmaz).

### Otomatik başlatma

Windows Görev Zamanlayıcı'da `MonitorGoruntuMotor` görevi; `-AtStartup`, SYSTEM hesabı,
süre sınırı yok, kapanırsa dakikada bir yeniden dener.

---

## 10. Klasörler

| Yol | Ne |
|---|---|
| `C:\Projeler\monitor-okuma` | Kaynak kod (git deposu) |
| `C:\MonitorOkuma` | Kurulu uygulama |
| `C:\MonitorOkuma_Teslim` | Teslim paketleri (ZIP'ler) |

Teslim klasöründe üç ayrı paket var, karıştırmamak gerekir:

- **`Monitor_Okuma_Projesi_Tam_Teslim`** — asıl teslim. `01_CALISTIRILABILIR_TESLIM\` (EXE'ler,
  test araçları yok) + `02_KAYNAK_KOD\` (kaynak kodun tamamı)
- **`Monitor_Okuma_Projesi_Teslim`** — demo paketi; EXE'lerin yanında `test_araclari\` de var
- **`Monitor_Okuma_Projesi_Kaynak_Kod`** — yalnızca kaynak kod

> Paketleme **script'i yok**, elle yapılıyor. Teslim `README.txt` dosyaları repoda değil, yalnızca
> o klasörlerin içinde — orada yapılan düzeltme git'e yansımaz.

---

## 11. Şu anki durum

**Çalışıyor:**
- Kameradan çekim, çift çekim, diske kaydetme, kuyruklama
- M4'e gönderim, geçici hatada tekrar deneme, kalıcı hatada `hatali` işaretleme
- SQLite veritabanı, okunabilir kimlikler, eski biçimden göç
- Kullanıcı girişi, e-posta doğrulama, roller, izin verilen alan adları
- Kamera kullanım onayı (onaysız kameradan görüntü alınmaz)
- E-posta bildirimleri ve kalıcı bildirim kuyruğu
- Kayıtlar / Loglar / Ayarlar / Kullanıcılar sekmeleri
- Sahte kamera + sahte M4 ile uçtan uca test ortamı
- 359 otomatik test
- `--onedir` ile EXE paketleme
- Git deposu: `https://github.com/kayaturkkilayda/monitor-okuma.git`, dal `main`, 12 commit

**Açık konular:**

1. **Kod imzalama sertifikası yok.** EXE'ler imzasız. Windows 11'de **Smart App Control** açık
   makinelerde yeni üretilmiş imzasız dosya engellenebiliyor
   ("Uygulama Denetimi ilkesi bu dosyayı engelledi"). Engel genelde **geçicidir** — aynı dosya
   birkaç dakika sonra çalışabiliyor, çünkü Windows'un itibar kararı sonradan geliyor.
   *Kalıcı çözüm kod imzalamadır; Smart App Control kapatılmamalı* (Windows'ta bir kez kapatılınca
   sistem sıfırlanmadan geri açılamıyor).

2. **Gerçek M4 API bilgileri henüz yok.** Adres ve anahtar geldiğinde arayüzden girilecek.
   Gönderim formatı farklı çıkarsa yalnızca `src/gonderici.py` içindeki `_gonder` fonksiyonu
   uyarlanacak.

3. **Gerçek IP kameralarla denenmedi.** Snapshot adresi kamera modeline göre değişir.

---

## 12. Benimle nasıl çalış

- **Sade Türkçe**, öğrenciye anlatır gibi. Kod satırı listeleme — **mantığı** anlat: hangi dosya
  neden değişti, nasıl çalışıyor.
- Her değişiklikten sonra **`pytest` çalıştır**, sonucu söyle. Test sayısı düşmesin.
- Her yeni özellik için **test yaz**.
- **Sır loglama.** Şifre/anahtar/kod ekrana veya loga yazılmaz; `src/sifreleme.py` üzerinden
  şifreli saklanır.
- Her yeni arayüz sekmesi **`src/` altında kendi dosyası** olsun.
- Motor ve arayüz **aynı anda çalışır** — birbirini kilitleyecek çözüm önerme.
- Bir şey **varsaymak yerine dosyayı aç ve bak**. Yanlış hatırlamaktansa kontrol et.
- İşi bitirdiğini söylemeden önce **gerçekten çalıştığını doğrula**.
