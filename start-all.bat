@echo off
chcp 65001 >nul
set "ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%start-all.ps1"
if errorlevel 1 (
  echo.
  echo 启动失败，请根据上方提示检查配置。
  pause
)
