@echo off
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0Capturar-Trafego.ps1" -Gui -ContinuousMarket
if errorlevel 1 pause
