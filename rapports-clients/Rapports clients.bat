@echo off
rem Ouvre l'outil d'envoi des rapports clients. Double-cliquer sur ce fichier.
cd /d "%~dp0"
where py >NUL 2>&1 || (echo Python n'est pas installe sur cet ordinateur. Voir le README. & pause & exit /b)
py -c "import openpyxl, pypdf, msal" >NUL 2>&1 || (echo Premiere utilisation : installation des modules, environ une minute... & py -m pip install --user -q -r requirements.txt)
start "" pyw app.py
