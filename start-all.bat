@echo off
title Launch IMAGEKEY (Server + Tunnel)
cd /d "%~dp0"
echo ====================================================
echo   IMAGEKEY Optical Vault - All-In-One Launcher
echo ====================================================
echo 1. Starting FastAPI Uvicorn Server...
start "IMAGEKEY Local Server" cmd /k "call start.bat"

echo 2. Waiting for server to initialize...
timeout /t 2 /nobreak >nul

echo 3. Starting Cloudflare Public HTTPS Tunnel...
start "IMAGEKEY Cloudflare Tunnel" cmd /k "cloudflared.exe tunnel --url http://127.0.0.1:8000"

echo.
echo Both services are running in their own separate windows!
echo - Local Web App: http://127.0.0.1:8000
echo - Check the Cloudflare Tunnel window for your public HTTPS URL.
echo.
