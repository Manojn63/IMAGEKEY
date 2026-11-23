@echo off
title IMAGEKEY Optical Vault Server
cd /d "%~dp0"
echo ====================================================
echo   IMAGEKEY Optical Vault Platform
echo   Starting local server at http://127.0.0.1:8000
echo ====================================================
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
