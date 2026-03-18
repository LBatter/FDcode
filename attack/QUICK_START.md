# 缓存侧信道攻击 - 快速运行指令

**系统**: Intel CPU (Skylake+) | Ubuntu 22.04 | 超线程已开启

---

## 一、Mastik 传统攻击

### 1. Flush+Reload (FR)
**类型**: 基于共享内存的缓存攻击

```bash
cd /home/x/first_collect/attack/Mastik-main/demo

# 编译（首次运行）
gcc -g -O2 -I.. -o FR-openssl-test FR-openssl-test.c -L../src -lmastik

# 运行（持续模式，Ctrl+C停止）
./FR-openssl-test
```

### 2. Flush+Flush (FF)
**类型**: 隐蔽的缓存计时攻击

```bash
cd /home/x/first_collect/attack/Mastik-main/demo

# 编译（首次运行）
gcc -g -O2 -I.. -o FF-openssl-test FF-openssl-test.c -L../src -lmastik

# 运行（持续模式，Ctrl+C停止）
./FF-openssl-test
```

### 3. Prime+Probe (PP) - L1缓存
**类型**: L1缓存Prime+Probe攻击

```bash
cd /home/x/first_collect/attack/Mastik-main/demo

# 编译（首次运行）
gcc -g -O2 -I.. -o PP-L1-test PP-L1-test.c -L../src -lmastik

# 运行（持续模式，Ctrl+C停止）
./PP-L1-test
```

### 4. Prime+Probe (PP) - L3/LLC缓存
**类型**: L3缓存Prime+Probe攻击（跨核心，与Prime+Scope相似）

```bash
cd /home/x/first_collect/attack/Mastik-main/demo

# 编译（首次运行）
gcc -g -O2 -I.. -o PP-L3-test PP-L3-test.c -L../src -lmastik

# 运行（持续模式，Ctrl+C停止）
# 注意：初始化需要几秒钟构建驱逐集
./PP-L3-test
```

### 5. L1 Prime+Probe AES密钥恢复
**类型**: 针对AES的L1 Prime+Probe攻击

```bash
cd /home/x/first_collect/attack/Mastik-main/demo
./ST-L1PP-AES
```

### 6. 阈值校准
```bash
# FR阈值
cd /home/x/first_collect/attack/Mastik-main/demo
./FR-threshold

# FF阈值
/home/x/first_collect/attack/Mastik-main/histogram/ff/calibration

# FR详细校准
/home/x/first_collect/attack/Mastik-main/histogram/fr/calibration_fr
```

---

## 二、Prefetch 攻击

### 7. Prefetch+Prefetch / Prefetch+Reload (持续模式 - 推荐)
**类型**: 跨核心隐蔽信道

**直接运行（无脚本噪音，推荐用于HPC采集）**:
```bash
cd /home/x/first_collect/attack/AdversarialPrefetch-main/covert_channels/build/bin

# Prefetch+Prefetch
./sender &
./receiver_pre_pre    # 等待READY信号后开始采集，Ctrl+C停止

# Prefetch+Reload
./sender &
./receiver_pre_relo   # 等待READY信号后开始采集，Ctrl+C停止

# 停止
pkill sender && pkill receiver
```

**脚本运行（旧方式）**:
```bash
cd /home/x/first_collect/attack/AdversarialPrefetch-main/covert_channels

# 持续运行（Ctrl+C停止）
./run_prefetch.sh pre_pre   # Prefetch+Prefetch
./run_prefetch.sh pre_relo  # Prefetch+Reload
```

---

## 三、PRIME+SCOPE 攻击

### 8. Prime+Scope 攻击 (持续模式 - 推荐)
**类型**: 基于LLC的跨核心攻击

**直接运行（无脚本噪音，推荐用于HPC采集）**:
```bash
cd /home/x/first_collect/attack/PRIME-SCOPE-main/primescope_demo

# 持续运行（已修改为100万次迭代，Ctrl+C停止）
./app --primescope

# 驱逐集构建测试
./app --evset
```

**脚本运行（旧方式）**:
```bash
cd /home/x/first_collect/attack/PRIME-SCOPE-main/primescope_demo

# 持续运行（Ctrl+C停止）
./run_continuous.sh
```

---

## 四、HPC数据采集（配合攻击使用）

### 方法1：自动同步采集（推荐）
```bash
cd /home/x/first_collect/collect

# 采集L3 Prime+Probe攻击数据（60秒）
./sync_collect.sh pp-l3 60

# 采集其他攻击类型
./sync_collect.sh fr 60      # Flush+Reload
./sync_collect.sh ff 60      # Flush+Flush
./sync_collect.sh pp-l1 60   # L1 Prime+Probe
```

脚本会自动：
1. 启动攻击程序
2. 等待初始化完成（PP-L3会等待READY信号）
3. 开始HPC采集
4. 采集完成后停止攻击

### 方法2：手动分开运行
```bash
cd /home/x/first_collect/collect

# 终端1：启动HPC监控
./cache_monitor

# 终端2：运行攻击程序（选择一个）
cd /home/x/first_collect/attack/Mastik-main/demo
./FR-openssl-test   # Flush+Reload
./FF-openssl-test   # Flush+Flush
./PP-L1-test        # L1 Prime+Probe
./PP-L3-test        # L3 Prime+Probe (等待READY后再启动采集)
./ST-L1PP-AES       # L1 Prime+Probe AES
```

---

## 目录结构

```
/home/x/first_collect/attack/
├── Mastik-main/              # FR, FF, PP攻击
│   └── demo/
│       ├── FR-openssl-test   # Flush+Reload (持续模式)
│       ├── FF-openssl-test   # Flush+Flush (持续模式)
│       ├── PP-L1-test        # L1 Prime+Probe (持续模式)
│       ├── PP-L3-test        # L3 Prime+Probe (持续模式)
│       └── ST-L1PP-AES       # L1 Prime+Probe AES密钥恢复
├── AdversarialPrefetch-main/ # Prefetch攻击
│   └── covert_channels/
│       ├── build/bin/
│       │   ├── sender            # 发送端（后台运行）
│       │   ├── receiver_pre_pre  # Prefetch+Prefetch (持续模式，输出READY)
│       │   └── receiver_pre_relo # Prefetch+Reload (持续模式，输出READY)
│       └── run_prefetch.sh       # 脚本方式（旧）
├── PRIME-SCOPE-main/         # Prime+Scope攻击
│   └── primescope_demo/
│       ├── app                   # Prime+Scope (持续模式，100万次迭代)
│       └── run_continuous.sh     # 脚本方式（旧）
└── openssl-1.0.1f/           # 攻击目标库
```

## 修改说明

### 源码修改（用于持续运行）
- **Prefetch攻击**: `libs/util.h` 中 `ROUNDS=1000`，receiver代码添加无限循环和READY信号
- **Prime+Scope**: `configuration.h` 中 `TEST_LEN=1000000`（100万次迭代）

---

## 五、PARSEC 基准测试（性能开销测试）

### 部署步骤（首次使用）

```bash
# 1. 安装依赖
sudo apt-get install -y m4

# 2. 进入PARSEC目录
cd /home/x/first_collect/attack/parsec-workspace/parsec-3.0

# 3. 初始化环境
source env.sh

# 4. 编译基准测试程序
parsecmgmt -a build -p blackscholes -c gcc
parsecmgmt -a build -p streamcluster -c gcc-pthreads
parsecmgmt -a build -p swaptions -c gcc-pthreads

# 5. 解压native输入（如未解压）
cd /home/x/first_collect/attack/parsec-workspace
cat parsec-3.0-input-native.tar.gz.* | tar -xzf -
```

### 运行基准测试

```bash
cd /home/x/first_collect/attack/parsec-workspace/parsec-3.0
source env.sh

# 快速测试（验证程序可用）
parsecmgmt -a run -p blackscholes -i test -n 4

# Native输入（真实性能测试）
parsecmgmt -a run -p blackscholes -i native -n 4      # ~31秒
parsecmgmt -a run -p streamcluster -i native -n 4 -c gcc-pthreads  # ~2分钟
parsecmgmt -a run -p swaptions -i native -n 4 -c gcc-pthreads      # ~47秒
```

### 输入大小选项

| 选项 | 用途 | 运行时间 |
|------|------|----------|
| `-i test` | 验证程序 | 瞬间 |
| `-i simsmall` | 小规模测试 | ~1秒 |
| `-i simmedium` | 中规模测试 | ~3-5秒 |
| `-i simlarge` | 大规模测试 | ~12-20秒 |
| `-i native` | **真实负载** | **30秒-几分钟** |

### 已编译的程序

| 程序 | 类型 | native运行时间 |
|------|------|----------------|
| blackscholes | 金融计算 | ~31秒 |
| streamcluster | 在线聚类 | ~2分钟 |
| swaptions | 利率定价 | ~47秒 |

### 性能开销测试方法

```bash
# 1. 基准运行（无检测器）
parsecmgmt -a run -p blackscholes -i native -n 4
# 记录 real 时间

# 2. 带检测器运行
# 终端1: 启动检测器
cd /home/x/first_collect/collect && ./cache_monitor

# 终端2: 运行基准测试
cd /home/x/first_collect/attack/parsec-workspace/parsec-3.0
source env.sh
parsecmgmt -a run -p blackscholes -i native -n 4
# 记录 real 时间

# 3. 计算开销
# 开销 = (带检测器时间 - 基准时间) / 基准时间 × 100%
```

### 常用命令

```bash
# 查看所有可用程序
parsecmgmt -a info

# 查看编译状态
parsecmgmt -a status

# 清理编译
parsecmgmt -a fullclean -p blackscholes

# 指定线程数
parsecmgmt -a run -p blackscholes -i native -n 8  # 8线程
```
