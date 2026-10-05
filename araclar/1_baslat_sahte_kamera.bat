@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Sahte Kamera (test) - localhost:8080

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

python -c "import cv2, numpy" >nul 2>&1
if errorlevel 1 (
    echo Gerekli paketler eksik, kuruluyor ^(numpy, opencv-python^)...
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
echo Sahte kamera baslatiliyor. Bu pencereyi KAPATMAYIN.
echo Test adresi: http://127.0.0.1:8080/K1/shot.jpg
echo Durdurmak icin Ctrl+C.
echo.
python sahte_kamera.py
pause
