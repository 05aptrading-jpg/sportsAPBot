@echo off
cd /d %~dp0
git pull
echo.
echo CSV actualizado. Presiona cualquier tecla para cerrar...
pause >nul
