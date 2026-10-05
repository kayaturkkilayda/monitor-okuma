@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Sahte M4 API (test) - localhost:9000

python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo HATA: Python bulunamadi.
    echo Python 3.11 veya uzeri kurun: https://www.python.org/downloads/
    echo Kurulumda "Add python.exe to PATH" secenegini isaretleyin.
    echo.
    pause
    exit /b 1
)

python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo Gerekli paket eksik, kuruluyor ^(Flask^)...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo HATA: Paketler kurulamadi. Elle deneyin:
        echo     python -m pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)

echo.
echo Sahte M4 API baslatiliyor. Bu pencereyi KAPATMAYIN.
echo Adres: http://127.0.0.1:9000/api/goruntu
echo Gelen her goruntu bu pencereye "ALINDI ..." olarak yazilir.
echo Durdurmak icin Ctrl+C.
echo.
python sahte_m4.py
pause
