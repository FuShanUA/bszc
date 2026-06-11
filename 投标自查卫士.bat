@echo off
chcp 65001 >nul
title 投标自查卫士 Windows 助手
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0win_setup.ps1"
