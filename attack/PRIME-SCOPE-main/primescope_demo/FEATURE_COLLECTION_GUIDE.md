# PRIME+SCOPE 特征采集指南

## 修复说明

✅ **栈溢出问题已修复**

**问题**：`evset[EV_LLC]`数组大小固定为12，但实际驱逐集有17-32个元素，导致缓冲区溢出。

**解决**：将`EV_LLC`从`LLC_WAYS`(12)改为`MAX_EXTENSION`(32)，允许更大的驱逐集。

**修改文件**：`attacker_inclusive.c:106`

---

## 快速开始

### 1. 单次运行（测试）

```bash
cd /home/x/attack/PRIME-SCOPE-main/primescope_demo
./app --primescope
```

**输出示例**：
```
Eviction set is constructed successfully
Testing Prime+Scope
Success at test 0
Failure at test 1
...
Success 1/10
```

### 2. 持续运行（特征采集）

```bash
# 终端1：运行攻击
bash run_continuous.sh

# 终端2：采集特征（需要sudo）
sudo perf record -e cache-misses,LLC-loads,LLC-load-misses \
  -a -g -o primescope.data sleep 60
```

---

## 特征采集方案

### 方案A：使用perf record（推荐）

**采集完整的调用栈和事件**：

```bash
# 1. 启动攻击
cd /home/x/attack/PRIME-SCOPE-main/primescope_demo
bash run_continuous.sh &
ATTACK_PID=$!

# 2. 采集60秒的数据
sudo perf record -e cache-misses,LLC-loads,LLC-load-misses,cycles \
  -a -g -F 99 -o primescope.data sleep 60

# 3. 停止攻击
kill $ATTACK_PID

# 4. 分析数据
sudo perf report -i primescope.data
sudo perf script -i primescope.data > primescope_trace.txt
```

### 方案B：使用perf stat（实时监控）

**实时查看性能计数器**：

```bash
# 终端1：运行攻击
bash run_continuous.sh

# 终端2：实时监控（每秒输出）
sudo perf stat -e cache-misses,cache-references,LLC-loads,LLC-load-misses,\
cycles,instructions,branch-misses -a -I 1000
```

### 方案C：采集特定进程

```bash
# 1. 启动攻击
./app --primescope &
PID=$!

# 2. 只监控该进程
sudo perf record -e cache-misses,LLC-loads -p $PID -g sleep 30

# 3. 分析
sudo perf report
```

---

## 关键特征指标

### 1. 缓存相关特征

| 事件 | 说明 | 预期特征 |
|------|------|----------|
| `cache-misses` | 总缓存未命中 | 高频率 |
| `cache-references` | 总缓存访问 | 非常高 |
| `LLC-loads` | LLC加载 | 周期性峰值 |
| `LLC-load-misses` | LLC未命中 | 持续高值 |
| `LLC-stores` | LLC存储 | 中等 |

### 2. 跨核心特征

```bash
# 使用perf c2c检测跨核心缓存争用
sudo perf c2c record -a sleep 30
sudo perf c2c report
```

### 3. 时间测量特征

PRIME+SCOPE使用RDTSC指令频繁测量时间：

```bash
# 监控RDTSC使用
sudo perf stat -e cpu/event=0x00,umask=0x01/ -a sleep 30
```

---

## 对比实验

### 采集正常程序的基线

```bash
# 运行一个正常程序作为对比
stress-ng --cpu 1 --timeout 30s &
sudo perf record -e cache-misses,LLC-loads -a -g sleep 30
sudo perf report -i perf.data > baseline.txt
```

### 采集其他攻击的特征

```bash
# Flush+Reload攻击
cd "/home/x/attack/Cache-Side-Channel-Attacks-master/AES - HalfKey/Flush+Reload"
taskset -c 0 ./spy &
sudo perf record -e cache-misses,LLC-loads -a -g sleep 30
sudo perf report > flush_reload.txt
```

---

## 数据分析

### 1. 查看热点函数

```bash
sudo perf report -i primescope.data --stdio | head -50
```

### 2. 生成火焰图

```bash
# 安装FlameGraph
git clone https://github.com/brendangregg/FlameGraph.git

# 生成火焰图
sudo perf script -i primescope.data | \
  FlameGraph/stackcollapse-perf.pl | \
  FlameGraph/flamegraph.pl > primescope_flame.svg
```

### 3. 导出为CSV

```bash
sudo perf script -i primescope.data -F time,event,ip,sym | \
  awk '{print $1","$2","$4}' > primescope_events.csv
```

---

## 机器学习特征工程

### 推荐特征

1. **时间序列特征**：
   - 缓存未命中率的时间序列
   - LLC加载的周期性
   - 事件间隔的统计分布

2. **统计特征**：
   - 均值、方差、峰度、偏度
   - 最大值、最小值、中位数
   - 95th/99th百分位数

3. **频域特征**：
   - FFT变换
   - 功率谱密度
   - 主频率成分

### 特征提取示例

```python
import pandas as pd
import numpy as np

# 读取perf数据
df = pd.read_csv('primescope_events.csv', 
                 names=['time', 'event', 'function'])

# 计算缓存未命中率
cache_misses = df[df['event'] == 'cache-misses']
miss_rate = cache_misses.groupby(pd.Grouper(key='time', freq='1S')).size()

# 统计特征
features = {
    'mean': miss_rate.mean(),
    'std': miss_rate.std(),
    'max': miss_rate.max(),
    'p95': miss_rate.quantile(0.95)
}
```

---

## 故障排除

### 问题1：perf权限不足

```bash
# 临时允许非root用户使用perf
sudo sysctl -w kernel.perf_event_paranoid=-1

# 或使用sudo运行
sudo perf record ...
```

### 问题2：采集数据过大

```bash
# 限制采样频率
perf record -F 99 ...  # 每秒99次采样

# 只采集特定事件
perf record -e cache-misses ...
```

### 问题3：攻击检测率低

这是正常的！PRIME+SCOPE在有噪声的环境下检测率本来就不高（10-30%）。
重要的是采集攻击过程中的特征模式，而不是攻击成功率。

---

## 参考资料

- PRIME+SCOPE论文：https://www.esat.kuleuven.be/cosic/publications/article-3405.pdf
- perf文档：https://perf.wiki.kernel.org/
- 缓存侧信道攻击综述：https://arxiv.org/abs/1811.00364

