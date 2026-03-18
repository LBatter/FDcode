# 数据集构建

将原始 HPC 数据处理为模型训练用的数据集。

## 标签定义

| 数据集 | Label 0 | Label 1 | Label 2 |
|--------|---------|---------|---------|
| heavy_load | benign | prefetch | primescope |
| light_load | benign | prefetch | primescope |
| combined | benign | prefetch | primescope |
| traditional | benign | flush (fr+ff) | pp |

## 构建指令

```bash
cd ~/first_collect/process

# 默认窗口大小 12，处理所有数据
python3 build_dataset.py

# 指定窗口大小
python3 build_dataset.py -w 10

# 只处理特定数据集
python3 build_dataset.py --heavy
python3 build_dataset.py --light
python3 build_dataset.py --combined
python3 build_dataset.py --traditional

# 窗口大小实验（6, 8, 10, 12, 14, 16, 18, 20）
python3 build_dataset.py --experiment
python3 build_dataset.py --experiment --traditional
```

## 输出结构

```
dataset/
├── heavy_load/window_X/
│   ├── train.csv    (60%)
│   ├── val.csv      (20%)
│   └── test.csv     (20%)
├── light_load/window_X/
│   ├── train.csv    (60%)
│   ├── val.csv      (20%)
│   └── test.csv     (20%)
├── combined/window_X/
│   ├── train.csv    (heavy + light 训练集合并)
│   └── val.csv      (heavy + light 验证集合并)
└── traditional/window_X/
    ├── train.csv
    ├── val.csv
    └── test.csv
```

## 数据格式

每个样本由 `window_size` 行组成，只有第一行包含标签值：

```
timestamp,LLC-load-misses,L1-dcache-load-misses,branch-misses,l1d.replacement,sw_prefetch_access.prefetchw,Label
1234567,100,200,50,80,10,0      <- 标签在这里
1234568,101,201,51,81,11,
1234569,102,202,52,82,12,
...
```
