#!/bin/bash
# 持续运行Prefetch攻击用于特征采集
# 用法: ./run_prefetch.sh [pre_pre|pre_relo]
# 按Ctrl+C停止

ATTACK_TYPE=${1:-"pre_pre"}
cd "$(dirname "$0")"
cd build/bin

echo "=== Prefetch 持续攻击模式 ==="
echo "攻击类型: $ATTACK_TYPE"
echo "按Ctrl+C停止"
echo ""

# 清理旧进程
pkill -f sender 2>/dev/null
pkill -f receiver 2>/dev/null
sleep 0.5

# 捕获Ctrl+C信号
cleanup() {
    echo ""
    echo "停止攻击..."
    pkill -f sender 2>/dev/null
    pkill -f receiver 2>/dev/null
    exit 0
}
trap cleanup INT

# 启动sender（后台运行）
./sender &
SENDER_PID=$!
echo "Sender PID: $SENDER_PID"

sleep 1

# 输出READY信号
echo "READY"

# 选择receiver类型
case $ATTACK_TYPE in
    pre_pre)
        RECEIVER="./receiver_pre_pre"
        ;;
    pre_relo)
        RECEIVER="./receiver_pre_relo"
        ;;
    *)
        echo "未知类型: $ATTACK_TYPE (可用: pre_pre, pre_relo)"
        kill $SENDER_PID 2>/dev/null
        exit 1
        ;;
esac

echo "Receiver: $RECEIVER"
echo ""

# 持续运行receiver
iteration=0
while true; do
    iteration=$((iteration + 1))

    # 运行receiver（它会在ROUNDS次后退出）
    $RECEIVER > /dev/null 2>&1

    # 每10次显示进度
    if [ $((iteration % 10)) -eq 0 ]; then
        echo "[迭代 $iteration]" >&2
    fi

    # 检查sender是否还在运行
    if ! kill -0 $SENDER_PID 2>/dev/null; then
        echo "Sender已退出，重新启动..."
        ./sender &
        SENDER_PID=$!
        sleep 0.5
    fi
done
