@echo off
chcp 65001 >NUL
title Progim - Révision des bons
call "%~dp0_logiciel\preparer_python.cmd"
"%PY%" -B -c "import anthropic" 2>NUL && goto lancer
echo Première utilisation : installation du module anthropic dans Python portable...
"%PY%" -m pip install --quiet --disable-pip-version-check "anthropic>=2.8" 2>NUL
"%PY%" -B -c "import anthropic" 2>NUL || (echo Il manque le module anthropic dans Python portable. Avertir le responsable TI. & pause & exit /b)
:lancer
"%PY%" -B "%~dp0_logiciel\interface.py" %*
