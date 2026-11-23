@echo off
title IMAGEKEY Cloudflare Tunnel
cd /d "%~dp0"
echo ====================================================
echo   IMAGEKEY Cloudflare Public Tunnel
echo   Forwarding to http://127.0.0.1:8000
echo ====================================================
if exist cloudflared.exe (
    cloudflared.exe tunnel --url http://127.0.0.1:8000
) else (
    echo [ERROR] cloudflared.exe not found in %~dp0
    pause
)
