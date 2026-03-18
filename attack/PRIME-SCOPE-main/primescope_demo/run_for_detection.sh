#!/bin/bash
# 运行PRIME+SCOPE攻击用于特征采集
# 即使遇到错误也会重启，持续运行

cd /home/x/attack/PRIME-SCOPE-main/primescope_demo

echo "开始运行PRIME+SCOPE攻击用于特征采集..."
echo "建议同时运行性能监控工具（perf, PMU计数器等）"
echo ""

# 持续运行，遇到错误自动重启
while true; do
    echo "[$(date)] 启动攻击..."
    ulimit -s unlimited
    timeout 30 ./app --primescope 2>&1 | head -50
    
    echo "[$(date)] 进程退出，3秒后重启..."
    sleep 3
done
