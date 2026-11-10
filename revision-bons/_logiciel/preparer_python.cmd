@echo off
rem Prepare Python portable sur ce poste (une seule fois) et definit %PY%.
rem Meme Python que l outil de facturation : s il est deja decompresse sur ce poste, rien a faire.
set "PYDIR=%LOCALAPPDATA%\ProgimFacturation\python-3.12.10"
set "ZIPPY=%~dp0python_portable.zip"
if exist "%PYDIR%\python.exe" goto pret
echo Premiere utilisation sur ce poste : installation de Python portable (quelques secondes)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath $env:ZIPPY -DestinationPath $env:PYDIR -Force"
:pret
set "PY=%PYDIR%\python.exe"
