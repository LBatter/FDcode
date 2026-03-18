# FDcode
# FG-Detector 实验指南

对应的数据集可在Zenodo获取https://doi.org/10.5281/zenodo.19094648
parsec过大，需自行下载

## 实验流程
---

## 第一步：数据准备

生成所有窗口大小的数据集：

```bash
cd /home/x/first_collect/process
python3 build_dataset.py --experiment
```

输出目录：`/home/x/first_collect/dataset/window_X/`

---

## 第二步：模型对比实验

对比 MLP、RNN、LSTM 三种模型，证明 LSTM 最优。

```bash
cd /home/x/first_collect/model
python3 train.py --compare -w 12
```

输出指标：
- 准确率 (Accuracy)
- 精确率 (Precision)
- 召回率 (Recall)
- F1 分数
- 误报率 (FPR)
- 漏报率 (FNR)

---

## 第三步：窗口大小敏感性实验

使用 LSTM 模型，测试不同窗口大小的效果。

```bash
cd /home/x/first_collect/model
python3 train.py --experiment
```

窗口大小：6, 8, 10, 12, 14, 16, 18, 20

---

## 第四步：超参数选择实验

---

## 第五步：测试部署性能

---

## 结果文件

所有实验结果保存在：

```
/home/x/first_collect/model/results/
├── model_comparison_summary.json    # 模型对比
├── window_experiment_summary.json   # 窗口实验
├── hyperparameter_search_summary.json  # 超参数实验
└── window_X/
    ├── lstm_best.pth               # 最佳模型
    └── lstm_results.json           # 详细结果
```

---

## 依赖安装

```bash
pip3 install torch numpy pandas scikit-learn
```
