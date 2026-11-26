@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Запускаю HH Job Bot...
python bot.py
if errorlevel 1 pause
