@echo off
title 投标自查卫士 BidShield
echo 🚀 正在启动 投标自查卫士 服务端...
start /b python3 server.py
timeout /t 2 >nul
echo 🌐 正在打开浏览器访问服务...
start http://localhost:8000
exit
