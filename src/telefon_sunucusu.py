"""Telefondan fotoğraf almak için küçük web sunucusu.

Motorun içinde ayrı bir iş parçacığında çalışır. Varsayılan olarak KAPALIDIR;
ayarlardan açılır. Kamera döngüsünü ve arayüzü bekletmez: her istek kendi başına
çalışır, veritabanına yalnızca kısa işlemlerle dokunur.

GÜVENLİK SINIRLARI (gerçek kurulumda bilinmesi gerekenler):
  * Trafik düz HTTP'dir. Fotoğraf hastane ağında şifresiz gider. Gerçek kullanımda
    önüne HTTPS koyan bir vekil sunucu gerekir.
  * Sunucu ağdan gelen bağlantı kabul eder. Bilgisayar artık yalnızca dışarı
    bağlanmıyor; BT'nin bu portu bilmesi gerekir.
  * Giriş yapmayan hiç kimse fotoğraf yükleyemez. Kullanıcı yalnızca yetkili olduğu
    yatağa yükleyebilir.
"""
import threading
from functools import wraps

from flask import Flask, Response, make_response, redirect, request, url_for

import sahiplik
import telefon_oturum
from kullanicilar import KullaniciHatasi, giris as kullanici_girisi
from veritabani import olay
from yukleme import EN_BUYUK_BAYT, Sinirlayici, YuklemeHatasi, fotografi_al

VARSAYILAN_PORT = 8099
GIRIS_PENCERE_SN = 300
GIRIS_EN_FAZLA = 10          # aynı adresten 5 dakikada en fazla 10 giriş denemesi


def sunucu_ayari(ayarlar: dict) -> dict:
    """Ayarlardaki telefon yükleme bölümü; eksik alanlar varsayılanla tamamlanır."""
    d = (ayarlar or {}).get("telefon_yukleme") or {}
    return {"acik": bool(d.get("acik", False)),
            "port": int(d.get("port") or VARSAYILAN_PORT)}


# ---------- Sayfa parçaları ----------

SAYFA = """<!doctype html>
<html lang="tr"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{baslik}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:20px 16px 40px; font-family:-apple-system,"Segoe UI",Roboto,sans-serif;
         background:#f4f6f8; color:#1b1f24; }}
  .kutu {{ max-width:460px; margin:0 auto; background:#fff; border-radius:14px;
           padding:22px 18px; box-shadow:0 1px 4px rgba(0,0,0,.12); }}
  h1 {{ font-size:34px; margin:0 0 2px; letter-spacing:.5px; }}
  .alt {{ color:#5f6b7a; font-size:15px; margin:0 0 20px; }}
  label {{ display:block; font-size:14px; color:#5f6b7a; margin:14px 0 4px; }}
  input[type=email], input[type=password] {{ width:100%; padding:13px; font-size:17px;
           border:1px solid #c7ced6; border-radius:9px; }}
  .dugme {{ display:block; width:100%; padding:17px; font-size:19px; font-weight:600;
            border:0; border-radius:11px; background:#0b5ed7; color:#fff; margin-top:18px;
            cursor:pointer; text-align:center; text-decoration:none; }}
  .ikincil {{ background:#e9eef5; color:#1b1f24; }}
  .uyari {{ background:#f8d7da; color:#8a1020; padding:12px; border-radius:9px;
            margin-top:14px; font-size:15px; }}
  .tamam {{ background:#e7f6ec; color:#15603a; padding:16px; border-radius:9px;
            margin-top:14px; font-size:19px; font-weight:600; text-align:center; }}
  #onizleme {{ width:100%; border-radius:11px; margin-top:16px; display:none; }}
  input[type=file] {{ display:none; }}
  .kucuk {{ color:#8a94a0; font-size:13px; margin-top:18px; text-align:center; }}
</style></head>
<body><div class="kutu">{govde}</div></body></html>
"""

GIRIS_GOVDE = """
<h1>{yatak}</h1>
<p class="alt">{kamera} &middot; Devam etmek için giriş yapın.</p>
{uyari}
<form method="post" action="{eylem}">
  <label for="eposta">E-posta</label>
  <input id="eposta" type="email" name="eposta" autocomplete="username"
         inputmode="email" autocapitalize="off" required>
  <label for="sifre">Şifre</label>
  <input id="sifre" type="password" name="sifre" autocomplete="current-password" required>
  <button class="dugme" type="submit">Giriş yap</button>
</form>
<p class="kucuk">Uygulamanızdaki hesapla giriş yapın.</p>
"""

YUKLEME_GOVDE = """
<h1>{yatak}</h1>
<p class="alt">{kamera} &middot; {ad}</p>
{uyari}
<form id="form" method="post" action="{eylem}" enctype="multipart/form-data">
  <input id="dosya" type="file" name="fotograf" accept="image/*" capture="environment" required>
  <label for="dosya" class="dugme">Fotoğraf çek</label>
  <img id="onizleme" alt="">
  <button id="gonder" class="dugme" type="submit" style="display:none">Gönder</button>
  <label for="dosya" id="tekrar" class="dugme ikincil" style="display:none">Tekrar çek</label>
</form>
<p class="kucuk">Monitör ekranının net göründüğünden emin olun.</p>
<script>
  var dosya = document.getElementById('dosya');
  var onizleme = document.getElementById('onizleme');
  var gonder = document.getElementById('gonder');
  var tekrar = document.getElementById('tekrar');
  dosya.addEventListener('change', function () {{
    if (!dosya.files || !dosya.files[0]) return;
    onizleme.src = URL.createObjectURL(dosya.files[0]);
    onizleme.style.display = 'block';
    gonder.style.display = 'block';
    tekrar.style.display = 'block';
  }});
  document.getElementById('form').addEventListener('submit', function () {{
    gonder.textContent = 'Gönderiliyor...';
    gonder.disabled = true;
  }});
</script>
"""

SONUC_GOVDE = """
<h1>{yatak}</h1>
<p class="alt">{kamera}</p>
<div class="tamam">Gönderildi &#10003;</div>
<a class="dugme" href="{eylem}">Yeni fotoğraf gönder</a>
"""


def _sayfa(baslik: str, govde: str, kod: int = 200) -> Response:
    return make_response(SAYFA.format(baslik=baslik, govde=govde), kod)


def _uyari(metin: str) -> str:
    return f'<div class="uyari">{metin}</div>' if metin else ""


# ---------- Uygulama ----------

def uygulama_olustur(ayarlari_getir, log) -> Flask:
    """Flask uygulamasını kurar.

    ayarlari_getir(): her istekte güncel ayarları döndürür (yönetici değiştirmiş olabilir).
    """
    uygulama = Flask(__name__)
    uygulama.config["MAX_CONTENT_LENGTH"] = EN_BUYUK_BAYT
    yukleme_sinir = Sinirlayici()
    giris_sinir = Sinirlayici(GIRIS_PENCERE_SN, GIRIS_EN_FAZLA)

    def kamerayi_bul(kod: str):
        for k in (ayarlari_getir() or {}).get("kameralar", []):
            if k["kod"] == kod:
                return k
        return None

    def oturumdaki():
        return telefon_oturum.kullanici(request.cookies.get(telefon_oturum.CEREZ_ADI))

    def yatak_sayfasi(f):
        """Kamerayı bulur, kullanıcıyı ve yetkisini denetler."""
        @wraps(f)
        def sarmal(kod, *a, **k):
            kamera = kamerayi_bul(kod)
            if kamera is None:
                return _sayfa("Bulunamadı", "<h1>Bulunamadı</h1>"
                              '<p class="alt">Bu QR artık geçerli değil. '
                              "Yöneticinize başvurun.</p>", 404)
            kullanici = oturumdaki()
            if kullanici is None:
                return _giris_sayfasi(kamera)
            if not sahiplik.gorebilir_mi(kamera, kullanici):
                olay(log, "WARNING", kamera["kod"],
                     f"{kamera['kod']} yatağına yetkisiz telefon erişimi: {kullanici['eposta']}")
                return _sayfa("Yetki yok", f"<h1>{kamera['yatak']}</h1>"
                              '<p class="alt">Bu yatağa fotoğraf gönderme yetkiniz yok.</p>', 403)
            return f(kamera, kullanici, *a, **k)
        return sarmal

    def _giris_sayfasi(kamera, uyari: str = "", kod: int = 200):
        govde = GIRIS_GOVDE.format(yatak=kamera["yatak"], kamera=kamera["kod"],
                                   uyari=_uyari(uyari),
                                   eylem=url_for("giris", kod=kamera["kod"]))
        return _sayfa(f"{kamera['yatak']} — Giriş", govde, kod)

    def _yukleme_sayfasi(kamera, kullanici, uyari: str = "", kod: int = 200):
        govde = YUKLEME_GOVDE.format(yatak=kamera["yatak"], kamera=kamera["kod"],
                                     ad=kullanici["ad"], uyari=_uyari(uyari),
                                     eylem=url_for("yukle", kod=kamera["kod"]))
        return _sayfa(kamera["yatak"], govde, kod)

    @uygulama.get("/yatak/<kod>")
    @yatak_sayfasi
    def yatak(kamera, kullanici):
        return _yukleme_sayfasi(kamera, kullanici)

    @uygulama.post("/yatak/<kod>/giris")
    def giris(kod):
        kamera = kamerayi_bul(kod)
        if kamera is None:
            return _sayfa("Bulunamadı", "<h1>Bulunamadı</h1>", 404)
        if not giris_sinir.izin_var_mi(request.remote_addr or "?"):
            return _giris_sayfasi(kamera, "Çok fazla deneme. Birkaç dakika sonra tekrar deneyin.", 429)
        try:
            # Şifre hiçbir yere yazılmaz; yalnızca doğrulamaya verilir
            kullanici = kullanici_girisi(request.form.get("eposta", ""),
                                         request.form.get("sifre", ""))
        except KullaniciHatasi as e:
            return _giris_sayfasi(kamera, str(e), 401)
        if not sahiplik.gorebilir_mi(kamera, kullanici):
            return _sayfa("Yetki yok", f"<h1>{kamera['yatak']}</h1>"
                          '<p class="alt">Bu yatağa fotoğraf gönderme yetkiniz yok.</p>', 403)
        anahtar = telefon_oturum.oturum_ac(kullanici["id"])
        olay(log, "INFO", kamera["kod"],
             f"{kamera['kod']} için telefondan giriş yapıldı: {kullanici['eposta']}")
        yanit = redirect(url_for("yatak", kod=kod))
        yanit.set_cookie(telefon_oturum.CEREZ_ADI, anahtar, httponly=True, samesite="Lax",
                         max_age=telefon_oturum.GECERLILIK_SAAT * 3600)
        return yanit

    @uygulama.post("/yatak/<kod>/yukle")
    @yatak_sayfasi
    def yukle(kamera, kullanici):
        if not yukleme_sinir.izin_var_mi(f"{kullanici['eposta']}|{kamera['kod']}"):
            return _yukleme_sayfasi(kamera, kullanici,
                                    "Çok sık gönderiyorsunuz. Biraz bekleyin.", 429)
        dosya = request.files.get("fotograf")
        if dosya is None:
            return _yukleme_sayfasi(kamera, kullanici, "Önce bir fotoğraf çekin.", 400)
        try:
            fotografi_al(dosya.read(), ayarlari_getir(), kamera, kullanici["eposta"], log)
        except YuklemeHatasi as e:
            return _yukleme_sayfasi(kamera, kullanici, str(e), 400)
        except Exception:
            log.exception(f"{kamera['kod']} | telefon fotoğrafı işlenemedi")
            return _yukleme_sayfasi(kamera, kullanici,
                                    "Fotoğraf kaydedilemedi. Tekrar deneyin.", 500)
        govde = SONUC_GOVDE.format(yatak=kamera["yatak"], kamera=kamera["kod"],
                                   eylem=url_for("yatak", kod=kamera["kod"]))
        return _sayfa("Gönderildi", govde)

    @uygulama.errorhandler(413)
    def cok_buyuk(_):
        mb = EN_BUYUK_BAYT // (1024 * 1024)
        return _sayfa("Çok büyük", f"<h1>Çok büyük</h1>"
                      f'<p class="alt">Fotoğraf en fazla {mb} MB olabilir.</p>', 413)

    return uygulama


# ---------- Motorun içinde çalıştırma ----------

def sunucuyu_baslat(ayarlari_getir, log, dur: threading.Event) -> threading.Thread | None:
    """Ayarlarda açıksa sunucuyu ayrı iş parçacığında başlatır.

    Kapalıysa None döner. Hata olursa motor durmaz; yalnızca olaylara yazılır.
    """
    ayar = sunucu_ayari(ayarlari_getir() or {})
    if not ayar["acik"]:
        return None

    uygulama = uygulama_olustur(ayarlari_getir, log)

    def calis():
        try:
            from werkzeug.serving import make_server
            sunucu = make_server("0.0.0.0", ayar["port"], uygulama, threaded=True)
        except Exception:
            olay(log, "ERROR", "sistem",
                 f"Telefon yükleme sunucusu açılamadı (port {ayar['port']} kullanımda olabilir)",
                 ayrinti=True)
            return
        olay(log, "INFO", "sistem", f"Telefon yükleme sunucusu açıldı (port {ayar['port']})")

        # Durdurma bayrağı gelince serve_forever'dan çıkılır; istek beklenmez
        def kapatmayi_bekle():
            dur.wait()
            sunucu.shutdown()

        threading.Thread(target=kapatmayi_bekle, name="telefon-kapat", daemon=True).start()
        try:
            sunucu.serve_forever(poll_interval=0.5)
        finally:
            sunucu.server_close()
            olay(log, "INFO", "sistem", "Telefon yükleme sunucusu kapandı")

    is_parcacigi = threading.Thread(target=calis, name="telefon", daemon=True)
    is_parcacigi.start()
    return is_parcacigi
