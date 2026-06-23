@echo off
setlocal
cd /d "%~dp0.."

echo Gerando todos os pacotes Windows do SannyGold Sistema...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_all_windows.ps1"
set "EXITCODE=%ERRORLEVEL%"

echo.
if not "%EXITCODE%"=="0" (
  echo Falha ao gerar os pacotes Windows. Veja logs\build-windows.log.
  pause
  exit /b %EXITCODE%
)

echo Build Windows concluido.
pause
exit /b 0
