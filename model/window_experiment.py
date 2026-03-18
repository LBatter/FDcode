#!/usr/bin/env python3
"""
window_experiment.py - 窗口大小敏感性实验 (PyTorch)

用于回答审稿人关于"如何确定窗口大小"的问题。
测试不同窗口大小对检测准确率的影响。

用法:
  python3 window_experiment.py                        # 默认: combined数据集, lstm模型
  python3 window_experiment.py -d heavy_load -m mlp  # 指定数据集和模型
  python3 window_experiment.py --all-models          # 测试所有模型
"""

import argparse
import os
import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset

import warnings
warnings.filterwarnings('ignore')

from models import get_model, MODEL_REGISTRY

# ========== 配置 ==========
BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BASE_DIR / "dataset"
OUTPUT_DIR = BASE_DIR / "output" / "window_experiment"

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# 窗口大小范围
WINDOW_SIZES = [6, 8, 10, 12, 14, 16, 18, 20]

# 数据集配置
DATASETS = {
    'heavy_load': {'path': 'heavy_load', 'has_test': True},
    'light_load': {'path': 'light_load', 'has_test': True},
    'combined': {'path': 'combined', 'has_test': False},
    'traditional': {'path': 'traditional', 'has_test': True},
    'windows': {'path': 'windows', 'has_test': True}
}

# 绘图设置
matplotlib.rcParams['font.family'] = 'serif'
matplotlib.rcParams['font.serif'] = ['Times New Roman', 'DejaVu Serif']
matplotlib.rcParams['font.size'] = 12
matplotlib.rcParams['axes.linewidth'] = 1.2


# ========== 工具函数 ==========
class Colors:
    GREEN = '\033[92m'
    CYAN = '\033[96m'
    END = '\033[0m'


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{Colors.GREEN}[{ts}]{Colors.END} {msg}")


def section(title):
    print(f"\n{Colors.CYAN}{'='*60}{Colors.END}")
    print(f"{Colors.CYAN}{title}{Colors.END}")
    print(f"{Colors.CYAN}{'='*60}{Colors.END}")


# ========== 数据处理 ==========
def load_and_prepare_data(dataset_name, window_size, model_type):
    """加载并准备数据"""
    config = DATASETS[dataset_name]
    data_dir = DATASET_DIR / config['path'] / f"window_{window_size}"

    if not data_dir.exists():
        return None

    train_df = pd.read_csv(data_dir / "train.csv")
    val_df = pd.read_csv(data_dir / "val.csv")

    test_df = None
    if config['has_test']:
        test_path = data_dir / "test.csv"
        if test_path.exists():
            test_df = pd.read_csv(test_path)

    feature_cols = [col for col in train_df.columns if col != 'Label']

    def extract_samples(df):
        label_mask = df['Label'].notna()
        label_indices = df.index[label_mask].tolist()

        X_list, y_list = [], []
        for idx in label_indices:
            sample = df.loc[idx:idx + window_size - 1, feature_cols].values
            if len(sample) == window_size:
                X_list.append(sample)
                y_list.append(int(df.loc[idx, 'Label']))

        return np.array(X_list), np.array(y_list)

    X_train, y_train = extract_samples(train_df)
    X_val, y_val = extract_samples(val_df)

    X_test, y_test = None, None
    if test_df is not None:
        X_test, y_test = extract_samples(test_df)

    # 标准化
    scaler = StandardScaler()
    n_train, seq_len, n_feat = X_train.shape

    X_train_2d = X_train.reshape(-1, n_feat)
    X_train_scaled = scaler.fit_transform(X_train_2d).reshape(n_train, seq_len, n_feat)

    n_val = X_val.shape[0]
    X_val_2d = X_val.reshape(-1, n_feat)
    X_val_scaled = scaler.transform(X_val_2d).reshape(n_val, seq_len, n_feat)

    X_test_scaled = None
    if X_test is not None:
        n_test = X_test.shape[0]
        X_test_2d = X_test.reshape(-1, n_feat)
        X_test_scaled = scaler.transform(X_test_2d).reshape(n_test, seq_len, n_feat)

    # MLP需要展平
    if model_type == 'mlp':
        X_train_scaled = X_train_scaled.reshape(n_train, -1)
        X_val_scaled = X_val_scaled.reshape(n_val, -1)
        if X_test_scaled is not None:
            X_test_scaled = X_test_scaled.reshape(n_test, -1)

    return {
        'X_train': X_train_scaled, 'y_train': y_train,
        'X_val': X_val_scaled, 'y_val': y_val,
        'X_test': X_test_scaled, 'y_test': y_test
    }


# ========== 单次实验 ==========
def run_single_experiment(dataset_name, window_size, model_type, epochs=50, batch_size=32):
    """运行单次实验"""
    data = load_and_prepare_data(dataset_name, window_size, model_type)
    if data is None:
        return None

    # 构建模型
    input_shape = data['X_train'].shape[1:]
    model = get_model(model_type, input_shape, num_classes=3)
    model = model.to(DEVICE)

    # 准备数据
    X_train = torch.FloatTensor(data['X_train'])
    y_train = torch.LongTensor(data['y_train'])
    train_dataset = TensorDataset(X_train, y_train)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

    X_val = torch.FloatTensor(data['X_val'])
    y_val = torch.LongTensor(data['y_val'])
    val_dataset = TensorDataset(X_val, y_val)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    # 训练
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)

    best_val_acc = 0
    patience_counter = 0
    patience = 10

    for epoch in range(epochs):
        model.train()
        for X_batch, y_batch in train_loader:
            X_batch, y_batch = X_batch.to(DEVICE), y_batch.to(DEVICE)
            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()

        # 验证
        model.eval()
        val_correct, val_total = 0, 0
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                X_batch, y_batch = X_batch.to(DEVICE), y_batch.to(DEVICE)
                outputs = model(X_batch)
                _, predicted = outputs.max(1)
                val_total += y_batch.size(0)
                val_correct += predicted.eq(y_batch).sum().item()

        val_acc = val_correct / val_total

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                break

    # 评估
    if data['X_test'] is not None:
        X_eval = torch.FloatTensor(data['X_test']).to(DEVICE)
        y_eval = data['y_test']
    else:
        X_eval = torch.FloatTensor(data['X_val']).to(DEVICE)
        y_eval = data['y_val']

    model.eval()
    with torch.no_grad():
        outputs = model(X_eval)
        _, y_pred = outputs.max(1)
        y_pred = y_pred.cpu().numpy()

    accuracy = accuracy_score(y_eval, y_pred)
    precision, recall, f1, _ = precision_recall_fscore_support(y_eval, y_pred, average='macro')

    return {
        'accuracy': accuracy,
        'precision': precision,
        'recall': recall,
        'f1': f1
    }


# ========== 窗口实验 ==========
def run_window_experiment(dataset_name, model_type, window_sizes=WINDOW_SIZES,
                          epochs=50, batch_size=32, runs=3):
    """运行窗口大小实验"""
    section(f"Window Experiment: {dataset_name} + {model_type.upper()}")
    log(f"Device: {DEVICE}")

    results = []

    for ws in window_sizes:
        log(f"Testing window size: {ws}")

        ws_results = []
        for run in range(runs):
            result = run_single_experiment(dataset_name, ws, model_type, epochs, batch_size)
            if result:
                ws_results.append(result)
                print(f"  Run {run+1}/{runs}: Acc={result['accuracy']:.4f}")

        if ws_results:
            avg_result = {
                'window_size': ws,
                'accuracy_mean': np.mean([r['accuracy'] for r in ws_results]),
                'accuracy_std': np.std([r['accuracy'] for r in ws_results]),
                'precision_mean': np.mean([r['precision'] for r in ws_results]),
                'recall_mean': np.mean([r['recall'] for r in ws_results]),
                'f1_mean': np.mean([r['f1'] for r in ws_results]),
            }
            results.append(avg_result)
            log(f"  Window {ws}: Acc={avg_result['accuracy_mean']:.4f} +/- {avg_result['accuracy_std']:.4f}")

    return results


# ========== 可视化 ==========
def plot_window_sensitivity(results, dataset_name, model_type, save_path):
    """绘制窗口大小敏感性曲线"""
    if not results:
        return

    windows = [r['window_size'] for r in results]
    accuracies = [r['accuracy_mean'] for r in results]
    stds = [r['accuracy_std'] for r in results]

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.errorbar(windows, accuracies, yerr=stds, fmt='o-', linewidth=2,
                markersize=8, capsize=5, capthick=2, color='#1f77b4')

    best_idx = np.argmax(accuracies)
    ax.scatter([windows[best_idx]], [accuracies[best_idx]], s=200,
               color='red', zorder=5, marker='*', label=f'Best: w={windows[best_idx]}')

    ax.set_xlabel('Window Size', fontsize=14)
    ax.set_ylabel('Accuracy', fontsize=14)
    ax.set_title(f'Window Size Sensitivity ({dataset_name}, {model_type.upper()})', fontsize=14)
    ax.set_xticks(windows)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=12)

    y_min = min(accuracies) - max(stds) - 0.02
    y_max = max(accuracies) + max(stds) + 0.02
    ax.set_ylim(max(0, y_min), min(1, y_max))

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    log(f"Saved: {save_path}")


def plot_window_sensitivity_paper(results, dataset_name, model_type, output_dir):
    """生成论文级别的窗口大小敏感性图 - IEEE格式"""
    if not results:
        return

    # 设置论文级别的字体和样式 (IEEE格式)
    plt.rcParams.update({
        'font.family': 'serif',
        'font.serif': ['Times New Roman', 'DejaVu Serif'],
        'font.size': 9,
        'axes.linewidth': 0.8,
        'axes.labelsize': 9,
        'axes.titlesize': 9,
        'xtick.labelsize': 8,
        'ytick.labelsize': 8,
        'legend.fontsize': 8,
        'figure.dpi': 300,
        'savefig.dpi': 300,
        'text.usetex': False,
    })

    windows = [r['window_size'] for r in results]
    accuracies = [r['accuracy_mean'] for r in results]

    # 转换为百分比
    accuracies_pct = [a * 100 for a in accuracies]

    # IEEE单栏宽度约3.5inch
    fig, ax = plt.subplots(figsize=(3.5, 2.4))

    # 绘制折线图
    ax.plot(windows, accuracies_pct, 'o-', linewidth=1.2, markersize=5,
            color='#1f77b4', markerfacecolor='#1f77b4',
            markeredgecolor='#1f77b4', markeredgewidth=0.8)

    # 在每个节点标记具体数值
    for i, (x, y) in enumerate(zip(windows, accuracies_pct)):
        offset_y = 0.06 if i % 2 == 0 else -0.10  # 交替上下偏移避免重叠
        ax.annotate(f'{y:.2f}', xy=(x, y), xytext=(0, offset_y * 100),
                    textcoords='offset points', ha='center', va='bottom' if offset_y > 0 else 'top',
                    fontsize=7, color='#333333')

    # 设置坐标轴
    ax.set_xlabel('Window Size (w)')
    ax.set_ylabel('Accuracy (%)')
    ax.set_xticks(windows)
    ax.set_xlim(min(windows) - 1, max(windows) + 1)

    # 动态设置y轴范围
    y_min = min(accuracies_pct)
    y_max = max(accuracies_pct)
    y_range = y_max - y_min
    ax.set_ylim(y_min - y_range * 0.3 - 0.05, y_max + y_range * 0.3 + 0.05)

    # 设置y轴刻度
    y_bottom = int(y_min * 10) / 10  # 向下取整到0.1
    ax.set_yticks([y_bottom, y_bottom + 0.10, y_bottom + 0.20, y_bottom + 0.30])
    ax.set_yticklabels([f'{y_bottom:.2f}', f'{y_bottom + 0.10:.2f}', f'{y_bottom + 0.20:.2f}', f'{y_bottom + 0.30:.2f}'])

    # 网格线
    ax.grid(True, linestyle=':', alpha=0.5, linewidth=0.5)
    ax.set_axisbelow(True)

    # 调整布局
    plt.tight_layout(pad=0.3)

    # 保存为多种格式
    for fmt in ['pdf', 'png']:
        save_path = output_dir / f"{model_type}_window_sensitivity_paper.{fmt}"
        plt.savefig(save_path, format=fmt, bbox_inches='tight',
                    dpi=300 if fmt == 'png' else None)
        print(f"Saved: {save_path}")

    plt.close()
    log(f"Saved paper figure: {output_dir / f'{model_type}_window_sensitivity_paper.pdf'}")


def plot_multi_model_comparison(all_results, dataset_name, save_path):
    """绘制多模型对比图"""
    fig, ax = plt.subplots(figsize=(10, 6))

    colors = {'mlp': '#1f77b4', 'rnn': '#ff7f0e', 'lstm': '#2ca02c'}
    markers = {'mlp': 'o', 'rnn': 's', 'lstm': '^'}

    for model_type, results in all_results.items():
        if not results:
            continue

        windows = [r['window_size'] for r in results]
        accuracies = [r['accuracy_mean'] for r in results]
        stds = [r['accuracy_std'] for r in results]

        ax.errorbar(windows, accuracies, yerr=stds, fmt=f'{markers[model_type]}-',
                    linewidth=2, markersize=8, capsize=4, capthick=1.5,
                    color=colors[model_type], label=model_type.upper())

    ax.set_xlabel('Window Size', fontsize=14)
    ax.set_ylabel('Accuracy', fontsize=14)
    ax.set_title(f'Window Size Sensitivity Comparison ({dataset_name})', fontsize=14)
    ax.set_xticks(WINDOW_SIZES)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=12)

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    log(f"Saved: {save_path}")


# ========== 结果汇总 ==========
def print_summary(all_results, dataset_name):
    """打印结果汇总"""
    section("Results Summary")

    print(f"\nDataset: {dataset_name}")
    print("-" * 70)
    print(f"{'Model':<8} {'Best Window':<12} {'Best Accuracy':<15} {'Worst Accuracy':<15}")
    print("-" * 70)

    for model_type, results in all_results.items():
        if not results:
            continue

        accuracies = [r['accuracy_mean'] for r in results]
        best_idx = np.argmax(accuracies)
        worst_idx = np.argmin(accuracies)

        best_ws = results[best_idx]['window_size']
        best_acc = results[best_idx]['accuracy_mean']
        worst_acc = results[worst_idx]['accuracy_mean']

        print(f"{model_type.upper():<8} {best_ws:<12} {best_acc:<15.4f} {worst_acc:<15.4f}")

    print("-" * 70)


def save_results(all_results, dataset_name, output_dir):
    """保存结果到JSON"""
    output_file = output_dir / f"{dataset_name}_results.json"

    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)

    log(f"Saved results: {output_file}")


# ========== 主函数 ==========
def main():
    parser = argparse.ArgumentParser(description='Window size sensitivity experiment (PyTorch)')
    parser.add_argument('-d', '--dataset', type=str, default='combined',
                        choices=list(DATASETS.keys()),
                        help='Dataset to use (default: combined)')
    parser.add_argument('-m', '--model', type=str, default='lstm',
                        choices=list(MODEL_REGISTRY.keys()),
                        help='Model to use (default: lstm)')
    parser.add_argument('--all-models', action='store_true',
                        help='Test all models')
    parser.add_argument('-e', '--epochs', type=int, default=50,
                        help='Max epochs per run (default: 50)')
    parser.add_argument('-r', '--runs', type=int, default=3,
                        help='Number of runs per window size (default: 3)')
    parser.add_argument('-b', '--batch', type=int, default=32,
                        help='Batch size (default: 32)')

    args = parser.parse_args()

    output_dir = OUTPUT_DIR / args.dataset
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.all_models:
        models_to_test = list(MODEL_REGISTRY.keys())
    else:
        models_to_test = [args.model]

    all_results = {}
    for model_type in models_to_test:
        results = run_window_experiment(
            args.dataset, model_type, WINDOW_SIZES,
            args.epochs, args.batch, args.runs
        )
        all_results[model_type] = results

        plot_window_sensitivity(
            results, args.dataset, model_type,
            output_dir / f"{model_type}_window_sensitivity.png"
        )

        # 生成论文级别的图
        plot_window_sensitivity_paper(
            results, args.dataset, model_type, output_dir
        )

    if len(models_to_test) > 1:
        plot_multi_model_comparison(all_results, args.dataset,
                                    output_dir / "model_comparison.png")

    print_summary(all_results, args.dataset)
    save_results(all_results, args.dataset, output_dir)

    section("Experiment Complete!")
    log(f"Results saved to: {output_dir}")


if __name__ == "__main__":
    main()
