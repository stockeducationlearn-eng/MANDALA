@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Bilgi Arastirma kurulum sihirbazi
where py >nul 2>nul
if errorlevel 1 (
  echo Python bulunamadi. Python 3.10+ kurun ve Add Python to PATH secenegini isaretleyin.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" py -m venv .venv
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Kurulumda hata olustu. Internet baglantisini ve hata mesajlarini kontrol edin.
  pause
  exit /b 1
)
echo Kurulum tamamlandi. Uygulama baslatiliyor...
".venv\Scripts\python.exe" app.py
pause
