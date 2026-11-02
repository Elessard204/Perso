@echo off
chcp 65001 >NUL
title Progim - Rapports clients
call "%~dp0preparer_python.cmd"
"%PY%" -B -c "import openpyxl, pypdf" 2>NUL || (echo Il manque un module Python ^(openpyxl ou pypdf^) dans Python portable. Avertir Eric. & pause & exit /b)
"%PY%" -B "%~dp0interface.py" %*
