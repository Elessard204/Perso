@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Envoi des rapports clients
echo.
set /p MOIS=Mois des rapports (ex. 2026-09) : 
echo Glisse ici le dossier des rapports Hopem du mois, puis appuie sur Entree :
set /p DOSSIER=
py envoi_rapports.py --mois %MOIS% --clients "clients_rapports.xlsx" --exports %DOSSIER% --completer
if exist "sortie\%MOIS%\rapport.html" start "" "sortie\%MOIS%\rapport.html"
pause
