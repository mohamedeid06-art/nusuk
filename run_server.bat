@echo off
chcp 65001 >nul
title Nusuk ERP & Automation Pro Server
cd /d "%~dp0"
echo ===================================================
echo   Nusuk ERP & Automation Pro - Local Server
echo ===================================================
echo [INFO] Running server from: %CD%
echo.
py server.py
pause
