@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Installation des modules Python requis...
py -m pip install --user -r requirements.txt
echo.
echo Installation terminee.
pause
