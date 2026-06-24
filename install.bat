@echo off
REM JAMES / SEKOS — one-click setup launcher (Windows).
REM Double-click this file on a freshly-cloned repo. It runs install.ps1,
REM which sets up the virtualenv, dependencies, .env secrets, and guides
REM you through the native deps (Ollama etc.). Re-running is safe.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
