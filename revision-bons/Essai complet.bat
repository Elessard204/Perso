@echo off
chcp 65001 >NUL
title Progim - Essai complet de Révision des bons
rem Essai en lecture seule : vraie IA et Google Maps, rien n est ecrit dans Progression. Rapport dans _logiciel\essais.
call "%~dp0_logiciel\preparer_python.cmd"
"%PY%" -B "%~dp0_logiciel\essai_complet.py" %*
pause
