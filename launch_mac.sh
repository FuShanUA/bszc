#!/bin/bash
echo "🚀 正在启动 BidShield 服务端..."
/Users/shanfu/.gemini/antigravity/scratch/bid_collusion_check/.venv/bin/python3 server.py &
sleep 2
echo "🌐 正在打开浏览器访问服务..."
open http://localhost:8000

