@echo off
chcp 65001 >NUL
title Progim - Révision des bons
call "%~dp0_logiciel\preparer_python.cmd"
rem Les modules de l'IA sont téléchargés par l'outil au premier lancement (liste dans _logiciel\roues.toml).
"%PY%" -B "%~dp0_logiciel\demarrer.py" %*
if errorlevel 1 pause
