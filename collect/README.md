# HPC 数据采集

采集缓存侧信道攻击的 HPC (Hardware Performance Counter) 数据。

## 数据类型

| 目录 | 说明 |
|------|------|
| `data/light_load/` | 轻负载（仅攻击程序） |
| `data/heavy_load/` | 满负载（攻击 + PARSEC 背景负载） |
| `data/traditional/` | 传统攻击（Flush+Reload, Flush+Flush, Prime+Probe） |

## 前置条件

```bash
# 编译 cache_monitor
cd ~/first_collect/collect
make
```

## 采集指令

```bash
cd ~/first_collect/collect

# 采集所有数据
sudo python3 collect_all.py

# 只采集轻负载
sudo python3 collect_all.py --light

# 只采集满负载
sudo python3 collect_all.py --heavy

# 只采集传统攻击
sudo python3 collect_all.py --traditional

# 强制重新采集（覆盖已有数据）
sudo python3 collect_all.py --force
```

## 输出文件

```
data/
├── light_load/
│   ├── benign.csv
│   ├── prefetch.csv
│   └── primescope.csv
├── heavy_load/
│   ├── benign.csv
│   ├── prefetch.csv
│   └── primescope.csv
└── traditional/
    ├── benign.csv
    ├── fr.csv
    ├── ff.csv
    └── pp.csv
```

## 采集参数

- 采集时长: 60 秒/类型
- 采样间隔: 100 微秒
- 有效文件最小行数: 500,000
