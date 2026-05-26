@echo off
chcp 65001 >nul
echo ======================================
echo   WSK Tracker - Wielki Szlem Komandosa
echo ======================================
echo.

cd /d "%~dp0"

echo [1/3] Sprawdzam Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo BŁĄD: Python nie jest zainstalowany!
    echo Pobierz z https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [2/3] Instaluję zależności...
pip install -r requirements.txt -q
if errorlevel 1 (
    echo BŁĄD: Nie udało się zainstalować zależności
    pause
    exit /b 1
)

echo [3/3] Uruchamiam serwer...
echo.
echo ========================================
echo   Serwer działa na: http://localhost:8000
echo   Otwórz w przeglądarce!
echo   Ctrl+C aby zatrzymać
echo ========================================
echo.

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

pause
