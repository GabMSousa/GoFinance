@echo off
setlocal
cd /d "%~dp0"

start "GoFinance servidor" /min cmd /c "python manage.py runserver 127.0.0.1:8000"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8000/login/?fresh=1"

endlocal
