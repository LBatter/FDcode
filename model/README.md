# 模型训练 (PyTorch)

支持 MLP、RNN、LSTM 三种模型，可选择不同数据集进行训练。

## 可用模型

| 模型 | 说明 |
|------|------|
| `mlp` | 多层感知机，将时序数据展平后输入 |
| `rnn` | 简单循环神经网络 |
| `lstm` | 长短期记忆网络 |

## 可用数据集

| 数据集 | 说明 | 标签 |
|--------|------|------|
| `heavy_load` | 满负载数据 | 0:Benign, 1:Prefetch, 2:Prime+Scope |
| `light_load` | 轻负载数据 | 0:Benign, 1:Prefetch, 2:Prime+Scope |
| `combined` | 合并数据(heavy+light) | 0:Benign, 1:Prefetch, 2:Prime+Scope |
| `traditional` | 传统攻击数据 | 0:Benign, 1:Flush, 2:Prime+Probe |

## 训练指令

```bash
cd ~/first_collect/model

# 默认: combined数据集 + lstm模型 + 窗口12
python3 train.py

# 指定数据集和模型
python3 train.py -d heavy_load -m mlp
python3 train.py -d traditional -m rnn

# 指定窗口大小
python3 train.py -d combined -m lstm -w 10

# 调整训练参数
python3 train.py -e 150 -b 64 -lr 0.0005

# 查看可用选项
python3 train.py --list
```

## 窗口大小实验


```bash
cd ~/first_collect/model

# 单模型实验
python3 window_experiment.py -d combined -m lstm

# 测试所有模型
python3 window_experiment.py -d combined --all-models

# 调整实验参数
python3 window_experiment.py -d heavy_load -r 5 -e 80
```

## 输出结构

```
output/
├── {dataset}/window_{X}/{model}/
│   ├── model.pt              # PyTorch模型权重
│   ├── training_history.png  # 训练曲线
│   └── confusion_matrix.png  # 混淆矩阵
└── window_experiment/{dataset}/
    ├── {model}_window_sensitivity.png  # 窗口敏感性曲线
    ├── model_comparison.png            # 多模型对比图
    └── {dataset}_results.json          # 实验结果数据
```

## 依赖

```bash
pip install torch pandas numpy scikit-learn matplotlib seaborn
```
