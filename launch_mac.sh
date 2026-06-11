#!/bin/bash
echo "🚀 正在启动 投标自查卫士 服务端..."
python3 server.py &
sleep 2
echo "🌐 正在打开浏览器访问服务..."
open http://localhost:8000
