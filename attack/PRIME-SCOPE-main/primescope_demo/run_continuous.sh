#!/bin/bash
# 持续运行PRIME+SCOPE攻击用于特征采集
# 用法: ./run_continuous.sh
# 按Ctrl+C停止

cd "$(dirname "$0")"

echo "=== PRIME+SCOPE 持续攻击模式 ==="
echo "按Ctrl+C停止"
echo ""

# 输出READY信号供采集脚本检测
echo "READY"

# 捕获Ctrl+C信号
trap 'echo ""; echo "停止攻击..."; exit 0' INT

iteration=0
while true; do
    iteration=$((iteration + 1))

    # 运行攻击，只显示关键信息
    ./app --primescope 2>&1 | grep -E "Success|constructed" | head -3

    # 每10次显示进度
    if [ $((iteration % 10)) -eq 0 ]; then
        echo "[迭代 $iteration]" >&2
    fi
done
