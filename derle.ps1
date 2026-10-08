<#
.SYNOPSIS
    motor.exe ve arayuz.exe'yi temiz derler, teslim ZIP'ini hazirlar.

.DESCRIPTION
    Derleme recetelerini (motor.spec, arayuz.spec) kullanir. Her ikisi de --onedir
    biciminde derlenir: bilesenler kurulum klasorunde sabit durur. --onefile
    kullanilmaz, cunku her acilista bilesenleri gecici klasore cikarir ve Windows
    guvenlik yazilimlari bu davranisi engeller.

    ZIP'e yalnizca calismak icin gerekenler girer. Gercek ayar dosyasi, veritabani,
    log ve goruntu ASLA girmez.

.PARAMETER Surum
    ZIP adinda kullanilacak surum etiketi. Varsayilan: v1.0.0

.PARAMETER ZipYok
    Yalnizca derler, ZIP uretmez.

.EXAMPLE
    .\derle.ps1
    .\derle.ps1 -Surum v1.0.1
    .\derle.ps1 -ZipYok
#>
param(
    [string]$Surum = "v1.0.0",
    [switch]$ZipYok
)

$ErrorActionPreference = "Stop"
$kok = $PSScriptRoot
Set-Location $kok

function Adim($metin) { Write-Host "`n=== $metin ===" -ForegroundColor Cyan }
function Bilgi($metin) { Write-Host "    $metin" -ForegroundColor DarkGray }

function Calistir {
    <#
      Yerel bir programi calistirir ve cikis koduna bakar.

      Windows PowerShell 5.1, bir .exe stderr'e yazdiginda bunu hata sayar;
      $ErrorActionPreference = "Stop" ile betik orada durur. Oysa PyInstaller ve
      pytest ilerleme satirlarini stderr'e yazar, bu bir hata degildir. Bu yuzden
      cagri sirasinda hata tercihi gevsetilir, basari yalnizca cikis koduyla olculur.
    #>
    param([string]$Program, [string[]]$Argumanlar, [string]$Hata)

    $onceki = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Program @Argumanlar
        $kod = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $onceki
    }
    if ($kod -ne 0) { throw "$Hata (cikis kodu $kod)" }
}

# ---------- 1. Onkosullar ----------

Adim "Onkosullar"

$python = Join-Path $kok ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Sanal ortam bulunamadi: $python`nOnce: python -m venv .venv ; .venv\Scripts\activate ; pip install -r requirements-dev.txt"
}
Bilgi "Python: $python"

# Calisan EXE varsa dosyalar kilitli olur, uzerine yazilamaz
foreach ($ad in @("motor", "arayuz")) {
    $acik = Get-Process -Name $ad -ErrorAction SilentlyContinue
    if ($acik) {
        throw "$ad.exe su anda calisiyor. Once kapatin (Gorev Yoneticisi), sonra tekrar deneyin."
    }
}
Bilgi "Calisan motor.exe / arayuz.exe yok"

# ---------- 2. Testler ----------

Adim "Testler"
Calistir $python @("-m", "pytest", "-q") "Testler gecmedi; derleme durduruldu."

# ---------- 3. Temizlik ----------

Adim "Eski cikti temizleniyor"
foreach ($klasor in @("build", "dist")) {
    if (Test-Path $klasor) {
        Remove-Item $klasor -Recurse -Force
        Bilgi "silindi: $klasor"
    }
}

# ---------- 4. Derleme ----------

foreach ($recete in @("motor.spec", "arayuz.spec")) {
    Adim "Derleniyor: $recete"
    Calistir $python @("-m", "PyInstaller", "--noconfirm", "--clean", $recete) "$recete derlenemedi."
}

foreach ($ad in @("motor", "arayuz")) {
    $exe = "dist\$ad\$ad.exe"
    if (-not (Test-Path $exe)) { throw "Beklenen cikti yok: $exe" }
    Bilgi ("{0}  ({1:N1} MB)" -f $exe, ((Get-Item $exe).Length / 1MB))
}

# ---------- 5. Teslim klasoru ----------

Adim "Teslim klasoru hazirlaniyor"

$teslim = "dist\MonitorOkuma-$Surum"
if (Test-Path $teslim) { Remove-Item $teslim -Recurse -Force }
New-Item -ItemType Directory -Path $teslim | Out-Null

# Iki programin ciktisi ayni klasorde birlesir (_motor ve _arayuz cakismaz)
foreach ($ad in @("motor", "arayuz")) {
    Copy-Item "dist\$ad\*" $teslim -Recurse -Force
}

New-Item -ItemType Directory -Path "$teslim\config" | Out-Null
Copy-Item "config\ayarlar.ornek.json" "$teslim\config\"

# Test araclari: sahte kamera + sahte M4 (elle_denemeler disarida kalir)
New-Item -ItemType Directory -Path "$teslim\araclar" | Out-Null
Get-ChildItem "araclar" -File | Copy-Item -Destination "$teslim\araclar\"

# Belgeler ve KURULUM.md'nin ekran goruntuleri
Copy-Item "KURULUM.md", "README.md" $teslim
New-Item -ItemType Directory -Path "$teslim\docs\ekranlar" -Force | Out-Null
Copy-Item "docs\ekranlar\*.png" "$teslim\docs\ekranlar\"

# ---------- 6. Guvenlik kontrolu ----------

Adim "Guvenlik kontrolu (gercek ayar / veritabani / log / goruntu girmemeli)"

$yasak = @(
    @{ Desen = "ayarlar.json";  Aciklama = "gercek ayar dosyasi (sifreli API anahtari icerir)" },
    @{ Desen = "*.db";          Aciklama = "veritabani" },
    @{ Desen = "*.db-wal";      Aciklama = "veritabani" },
    @{ Desen = "*.db-shm";      Aciklama = "veritabani" },
    @{ Desen = "*.log";         Aciklama = "log dosyasi" },
    @{ Desen = "durum.json";    Aciklama = "calisma durumu" },
    @{ Desen = "*.avif";        Aciklama = "goruntu" },
    @{ Desen = "*.jpg";         Aciklama = "goruntu" }
)
$bulunan = @()
foreach ($k in $yasak) {
    Get-ChildItem $teslim -Recurse -File -Filter $k.Desen -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne "ayarlar.ornek.json" } |
        ForEach-Object { $bulunan += "$($_.FullName)  <- $($k.Aciklama)" }
}
if ($bulunan) {
    $bulunan | ForEach-Object { Write-Host "    HATA: $_" -ForegroundColor Red }
    throw "Teslim klasorune girmemesi gereken dosyalar bulundu; ZIP uretilmedi."
}
Bilgi "temiz: gercek ayar, veritabani, log ve goruntu yok"

# ---------- 7. ZIP ----------

if ($ZipYok) {
    Adim "Bitti (ZIP istenmedi)"
    Bilgi $teslim
    return
}

Adim "ZIP olusturuluyor"
$zip = Join-Path $kok "dist\MonitorOkuma-$Surum.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }

# Compress-Archive yerine .NET: binlerce dosyada Compress-Archive cok yavas ve
# bu boyutta sessizce basarisiz olabiliyor. ZipFile hem hizli hem guvenilir.
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    (Resolve-Path $teslim).Path, $zip,
    [System.IO.Compression.CompressionLevel]::Optimal, $false)

if (-not (Test-Path $zip)) { throw "ZIP olusturulamadi: $zip" }
$boyut = (Get-Item $zip).Length / 1MB
Write-Host ""
Write-Host "TAMAM" -ForegroundColor Green
Write-Host ("  {0}  ({1:N1} MB)" -f $zip, $boyut)
Write-Host "  Icerik listesi:  Get-ChildItem '$teslim' -Recurse -File | Select-Object FullName"
