@echo off
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  echo Configure o Python e a .venv conforme o README.md primeiro.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m hilf_print
if errorlevel 1 pause
