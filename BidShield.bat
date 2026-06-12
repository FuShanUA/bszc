@echo off
chcp 65001 >nul
title BidShield Windows Helper
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0win_setup.ps1"
