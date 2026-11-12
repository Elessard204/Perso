@echo off
chcp 65001 >NUL
title Progim - Rapports clients
call "%~dp0_logiciel\preparer_python.cmd"
"%PY%" -B -c "import openpyxl, pypdf" 2>NUL || (echo Il manque un module Python ^(openpyxl ou pypdf^) dans Python portable. Avertir Eric. & pause & exit /b)
rem Le logiciel roule sans fenetre noire (pythonw) : on ne peut plus le fermer par accident.
rem Il s arrete tout seul une minute apres la fermeture de la page. Messages : %APPDATA%\Progim Rapports clients\journal.txt
set "PYW=%PYDIR%\pythonw.exe"
if not exist "%PYW%" set "PYW=%PY%"
start "" "%PYW%" -B "%~dp0_logiciel\interface.py" %*
