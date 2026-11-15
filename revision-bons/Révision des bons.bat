@echo off
chcp 65001 >NUL
title Progim - Révision des bons
call "%~dp0_logiciel\preparer_python.cmd"
rem Les modules de l'IA sont fournis dans _logiciel\roues et décompressés par l'outil au premier lancement.
"%PY%" -B "%~dp0_logiciel\interface.py" %*
if errorlevel 1 pause
