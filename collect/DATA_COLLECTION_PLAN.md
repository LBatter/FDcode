# 数据采集方案

## 一、分类任务

**三分类**：

| 标签 | 类别 | 攻击类型 |
|------|------|---------|
| **0** | 良性 | PARSEC程序、系统空闲 |
| **1** | Prefetch类 | Prefetch+Prefetch, Prefetch+Reload |
| **2** | Prime+Scope类 | Prime+Scope |

---

## 二、采集参数

- **采样间隔**：100μs
- **采集时长**：60秒/每项
- **背景负载**：streamcluster -i native（~2分钟）
- **HPC事件**：LLC-load-misses, L1-dcache-load-misses, branch-misses, l1d.replacement, sw_prefetch_access.prefetchw

---

## 三、训练数据

### 良性数据（标签=0）

| 程序 | 命令 | 输出文件 |
|------|------|---------|
| 系统空闲 | 无程序运行 | `benign_idle.csv` |
| blackscholes | `parsecmgmt -a run -p blackscholes -i native -n 4` | `benign_blackscholes.csv` |
| swaptions | `parsecmgmt -a run -p swaptions -i native -n 4 -c gcc-pthreads` | `benign_swaptions.csv` |
| streamcluster | `parsecmgmt -a run -p streamcluster -i native -n 4 -c gcc-pthreads` | `benign_streamcluster.csv` |

### Prefetch类攻击（标签=1）

| 攻击 | 负载 | 命令 | 输出文件 |
|------|------|------|---------|
| Prefetch+Prefetch | 无 | `./sender & ./receiver_pre_pre` | `prefetch_pp_noload.csv` |
| Prefetch+Prefetch | 有 | 攻击 + streamcluster native | `prefetch_pp_load.csv` |
| Prefetch+Reload | 无 | `./sender & ./receiver_pre_relo` | `prefetch_pr_noload.csv` |
| Prefetch+Reload | 有 | 攻击 + streamcluster native | `prefetch_pr_load.csv` |

### Prime+Scope类攻击（标签=2）

| 攻击 | 负载 | 命令 | 输出文件 |
|------|------|------|---------|
| Prime+Scope | 无 | `./app --primescope` | `ps_noload.csv` |
| Prime+Scope | 有 | 攻击 + streamcluster native | `ps_load.csv` |

---

## 四、测试数据（验证泛化能力）

用训练好的模型测试传统攻击：

| 期望标签 | 攻击 | 负载 | 命令 | 输出文件 |
|---------|------|------|------|---------|
| **1** | Flush+Reload | 无 | `./FR-openssl-test` | `test_fr_noload.csv` |
| **1** | Flush+Reload | 有 | 攻击 + streamcluster native | `test_fr_load.csv` |
| **1** | Flush+Flush | 无 | `./FF-openssl-test` | `test_ff_noload.csv` |
| **1** | Flush+Flush | 有 | 攻击 + streamcluster native | `test_ff_load.csv` |
| **2** | Prime+Probe L3 | 无 | `./PP-L3-test` | `test_pp_l3_noload.csv` |
| **2** | Prime+Probe L3 | 有 | 攻击 + streamcluster native | `test_pp_l3_load.csv` |

---

## 五、文件组织

```
/home/x/first_collect/data/
├── train/
│   ├── benign/
│   │   ├── benign_idle.csv
│   │   ├── benign_blackscholes.csv
│   │   ├── benign_swaptions.csv
│   │   └── benign_streamcluster.csv
│   ├── prefetch/
│   │   ├── prefetch_pp_noload.csv
│   │   ├── prefetch_pp_load.csv
│   │   ├── prefetch_pr_noload.csv
│   │   └── prefetch_pr_load.csv
│   └── primescope/
│       ├── ps_noload.csv
│       └── ps_load.csv
└── test/
    ├── test_fr_noload.csv
    ├── test_fr_load.csv
    ├── test_ff_noload.csv
    ├── test_ff_load.csv
    ├── test_pp_l3_noload.csv
    └── test_pp_l3_load.csv
```

---

## 六、采集步骤

### 1. 准备工作

```bash
# 创建数据目录
mkdir -p /home/x/first_collect/data/train/{benign,prefetch,primescope}
mkdir -p /home/x/first_collect/data/test

# 初始化PARSEC环境
cd /home/x/first_collect/attack/parsec-workspace/parsec-3.0
source env.sh
```

### 2. 采集良性数据

```bash
cd /home/x/first_collect/collect

# 系统空闲
./cache_monitor > ../data/train/benign/benign_idle.csv &
sleep 60 && pkill cache_monitor

# blackscholes (需要循环运行，因为native只跑31秒)
./cache_monitor > ../data/train/benign/benign_blackscholes.csv &
for i in {1..2}; do parsecmgmt -a run -p blackscholes -i native -n 4; done
pkill cache_monitor

# swaptions (~47秒，循环运行)
./cache_monitor > ../data/train/benign/benign_swaptions.csv &
for i in {1..2}; do parsecmgmt -a run -p swaptions -i native -n 4 -c gcc-pthreads; done
pkill cache_monitor

# streamcluster (~2分钟)
./cache_monitor > ../data/train/benign/benign_streamcluster.csv &
parsecmgmt -a run -p streamcluster -i native -n 4 -c gcc-pthreads
pkill cache_monitor
```

### 3. 采集Prefetch攻击数据

```bash
cd /home/x/first_collect/attack/AdversarialPrefetch-main/covert_channels/build/bin

# Prefetch+Prefetch 无负载
../../collect/cache_monitor > ../../data/train/prefetch/prefetch_pp_noload.csv &
./sender &
timeout 60 ./receiver_pre_pre
pkill sender; pkill cache_monitor

# Prefetch+Prefetch 有负载
../../collect/cache_monitor > ../../data/train/prefetch/prefetch_pp_load.csv &
./sender &
./receiver_pre_pre &
parsecmgmt -a run -p streamcluster -i native -n 4 -c gcc-pthreads
pkill receiver; pkill sender; pkill cache_monitor

# Prefetch+Reload 无负载
../../collect/cache_monitor > ../../data/train/prefetch/prefetch_pr_noload.csv &
./sender &
timeout 60 ./receiver_pre_relo
pkill sender; pkill cache_monitor

# Prefetch+Reload 有负载
../../collect/cache_monitor > ../../data/train/prefetch/prefetch_pr_load.csv &
./sender &
./receiver_pre_relo &
parsecmgmt -a run -p streamcluster -i native -n 4 -c gcc-pthreads
pkill receiver; pkill sender; pkill cache_monitor
```

### 4. 采集Prime+Scope数据

```bash
cd /home/x/first_collect/attack/PRIME-SCOPE-main/primescope_demo

# Prime+Scope 无负载
../../collect/cache_monitor > ../../data/train/primescope/ps_noload.csv &
timeout 60 ./app --primescope
pkill cache_monitor

# Prime+Scope 有负载
../../collect/cache_monitor > ../../data/train/primescope/ps_load.csv &
./app --primescope &
parsecmgmt -a run -p streamcluster -i native -n 4 -c gcc-pthreads
pkill app; pkill cache_monitor
```

### 5. 采集测试数据（传统攻击）

```bash
cd /home/x/first_collect/attack/Mastik-main/demo

# Flush+Reload
../../collect/cache_monitor > ../../data/test/test_fr_noload.csv &
timeout 60 ./FR-openssl-test
pkill cache_monitor

../../collect/cache_monitor > ../../data/test/test_fr_load.csv &
./FR-openssl-test &
parsecmgmt -a run -p streamcluster -i native -n 4 -c gcc-pthreads
pkill FR-openssl; pkill cache_monitor

# Flush+Flush
../../collect/cache_monitor > ../../data/test/test_ff_noload.csv &
timeout 60 ./FF-openssl-test
pkill cache_monitor

../../collect/cache_monitor > ../../data/test/test_ff_load.csv &
./FF-openssl-test &
parsecmgmt -a run -p streamcluster -i native -n 4 -c gcc-pthreads
pkill FF-openssl; pkill cache_monitor

# Prime+Probe L3
../../collect/cache_monitor > ../../data/test/test_pp_l3_noload.csv &
timeout 60 ./PP-L3-test
pkill cache_monitor

../../collect/cache_monitor > ../../data/test/test_pp_l3_load.csv &
./PP-L3-test &
parsecmgmt -a run -p streamcluster -i native -n 4 -c gcc-pthreads
pkill PP-L3; pkill cache_monitor
```

---

## 七、预计数据量

- 采样间隔 100μs = 10000次/秒
- 60秒采集 = 600000行/文件
- 训练数据：10个文件 × 600000行 ≈ 6M行
- 测试数据：6个文件 × 600000行 ≈ 3.6M行

---

## 八、验证

采集完成后检查：
1. 每个CSV文件行数是否接近600000
2. 数据格式是否正确（5个HPC事件列）
3. 时间戳是否连续
