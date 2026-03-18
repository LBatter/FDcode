#!/usr/bin/env python3
"""
train.py - 统一训练脚本 (PyTorch)

支持选择数据集和模型进行训练。

用法:
  python3 train.py                                    # 默认: combined数据集, lstm模型
  python3 train.py -d heavy_load -m mlp              # 指定数据集和模型
  python3 train.py -d traditional -m rnn -w 10       # 指定窗口大小
  python3 train.py --list                            # 列出可用选项
"""

import argparse
import os
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    classification_report, confusion_matrix, accuracy_score,
    precision_recall_fscore_support
)

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
OUTPUT_DIR = BASE_DIR / "output"

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# 数据集配置
DATASETS = {
    'heavy_load': {
        'path': 'heavy_load',
        'labels': {0: 'Benign', 1: 'Prefetch', 2: 'Prime+Scope'},
        'has_test': True
    },
    'light_load': {
        'path': 'light_load',
        'labels': {0: 'Benign', 1: 'Prefetch', 2: 'Prime+Scope'},
        'has_test': True
    },
    'combined': {
        'path': 'combined',
        'labels': {0: 'Benign', 1: 'Prefetch', 2: 'Prime+Scope'},
        'has_test': False
    },
    'traditional': {
        'path': 'traditional',
        'labels': {0: 'Benign', 1: 'Flush', 2: 'Prime+Probe'},
        'has_test': True
    },
    'windows': {
        'path': 'windows',
        'labels': {0: 'Benign', 1: 'Prefetch', 2: 'Prime+Scope'},
        'has_test': True
    }
}

# 设置绘图字体
matplotlib.rcParams['font.family'] = 'serif'
matplotlib.rcParams['font.serif'] = ['Times New Roman', 'DejaVu Serif']
matplotlib.rcParams['font.size'] = 12
matplotlib.rcParams['axes.linewidth'] = 1.2


# ========== 工具函数 ==========
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    RED = '\033[91m'
    END = '\033[0m'


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{Colors.GREEN}[{ts}]{Colors.END} {msg}")


def section(title):
    print(f"\n{Colors.CYAN}{'='*60}{Colors.END}")
    print(f"{Colors.CYAN}{title}{Colors.END}")
    print(f"{Colors.CYAN}{'='*60}{Colors.END}")


# ========== 数据加载 ==========
def load_dataset(dataset_name, window_size):
    """加载数据集"""
    if dataset_name not in DATASETS:
        raise ValueError(f"Unknown dataset: {dataset_name}")

    config = DATASETS[dataset_name]
    data_dir = DATASET_DIR / config['path'] / f"window_{window_size}"

    if not data_dir.exists():
        raise FileNotFoundError(f"Dataset not found: {data_dir}")

    log(f"Loading dataset from {data_dir}")

    train_df = pd.read_csv(data_dir / "train.csv")
    val_df = pd.read_csv(data_dir / "val.csv")

    log(f"  Train: {len(train_df)} rows")
    log(f"  Val: {len(val_df)} rows")

    test_df = None
    if config['has_test']:
        test_path = data_dir / "test.csv"
        if test_path.exists():
            test_df = pd.read_csv(test_path)
            log(f"  Test: {len(test_df)} rows")

    return train_df, val_df, test_df, config['labels']


def prepare_data(train_df, val_df, test_df, window_size, model_type):
    """准备训练数据"""
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

    log(f"Extracted samples:")
    log(f"  Train: {X_train.shape}")
    log(f"  Val: {X_val.shape}")
    if X_test is not None:
        log(f"  Test: {X_test.shape}")

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
        'X_train': X_train_scaled,
        'y_train': y_train,
        'X_val': X_val_scaled,
        'y_val': y_val,
        'X_test': X_test_scaled,
        'y_test': y_test,
        'scaler': scaler
    }


def create_dataloader(X, y, batch_size, shuffle=True):
    """创建DataLoader"""
    X_tensor = torch.FloatTensor(X)
    y_tensor = torch.LongTensor(y)
    dataset = TensorDataset(X_tensor, y_tensor)
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle)


# ========== 训练 ==========
class EarlyStopping:
    """早停机制"""
    def __init__(self, patience=15, min_delta=0):
        self.patience = patience
        self.min_delta = min_delta
        self.counter = 0
        self.best_score = None
        self.early_stop = False
        self.best_model = None

    def __call__(self, score, model):
        if self.best_score is None:
            self.best_score = score
            self.best_model = model.state_dict().copy()
        elif score < self.best_score + self.min_delta:
            self.counter += 1
            if self.counter >= self.patience:
                self.early_stop = True
        else:
            self.best_score = score
            self.best_model = model.state_dict().copy()
            self.counter = 0


def train_model(model, data, epochs=100, batch_size=32, learning_rate=0.001):
    """训练模型"""
    model = model.to(DEVICE)

    train_loader = create_dataloader(data['X_train'], data['y_train'], batch_size, shuffle=True)
    val_loader = create_dataloader(data['X_val'], data['y_val'], batch_size, shuffle=False)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='max', factor=0.5, patience=10)

    early_stopping = EarlyStopping(patience=15)

    history = {'loss': [], 'accuracy': [], 'val_loss': [], 'val_accuracy': []}

    log(f"Training on {DEVICE}")
    log(f"  Samples: {len(data['X_train'])}")
    log(f"  Batch size: {batch_size}")
    log(f"  Max epochs: {epochs}")

    for epoch in range(epochs):
        # 训练阶段
        model.train()
        train_loss, train_correct, train_total = 0, 0, 0

        for X_batch, y_batch in train_loader:
            X_batch, y_batch = X_batch.to(DEVICE), y_batch.to(DEVICE)

            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * X_batch.size(0)
            _, predicted = outputs.max(1)
            train_total += y_batch.size(0)
            train_correct += predicted.eq(y_batch).sum().item()

        train_loss /= train_total
        train_acc = train_correct / train_total

        # 验证阶段
        model.eval()
        val_loss, val_correct, val_total = 0, 0, 0

        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                X_batch, y_batch = X_batch.to(DEVICE), y_batch.to(DEVICE)
                outputs = model(X_batch)
                loss = criterion(outputs, y_batch)

                val_loss += loss.item() * X_batch.size(0)
                _, predicted = outputs.max(1)
                val_total += y_batch.size(0)
                val_correct += predicted.eq(y_batch).sum().item()

        val_loss /= val_total
        val_acc = val_correct / val_total

        history['loss'].append(train_loss)
        history['accuracy'].append(train_acc)
        history['val_loss'].append(val_loss)
        history['val_accuracy'].append(val_acc)

        scheduler.step(val_acc)

        if (epoch + 1) % 10 == 0 or epoch == 0:
            print(f"  Epoch {epoch+1:3d}: loss={train_loss:.4f}, acc={train_acc:.4f}, "
                  f"val_loss={val_loss:.4f}, val_acc={val_acc:.4f}")

        early_stopping(val_acc, model)
        if early_stopping.early_stop:
            log(f"Early stopping at epoch {epoch+1}")
            model.load_state_dict(early_stopping.best_model)
            break

    return history


# ========== 评估 ==========
def evaluate_model(model, data, label_names):
    """评估模型"""
    section("Model Evaluation")

    model = model.to(DEVICE)
    model.eval()

    if data['X_test'] is not None:
        X_eval, y_eval = data['X_test'], data['y_test']
        eval_name = "Test"
    else:
        X_eval, y_eval = data['X_val'], data['y_val']
        eval_name = "Validation"

    X_tensor = torch.FloatTensor(X_eval).to(DEVICE)

    with torch.no_grad():
        outputs = model(X_tensor)
        _, y_pred = outputs.max(1)
        y_pred = y_pred.cpu().numpy()

    accuracy = accuracy_score(y_eval, y_pred)
    log(f"{eval_name} Accuracy: {accuracy:.4f}")

    target_names = [label_names[i] for i in range(3)]
    print("\nClassification Report:")
    print(classification_report(y_eval, y_pred, target_names=target_names, digits=4))

    cm = confusion_matrix(y_eval, y_pred)
    print("Confusion Matrix:")
    print(cm)

    precision, recall, f1, support = precision_recall_fscore_support(y_eval, y_pred, average=None)

    print("\nPer-class Metrics:")
    for i, name in enumerate(target_names):
        print(f"  {name:15s}: P={precision[i]:.4f}, R={recall[i]:.4f}, F1={f1[i]:.4f}")

    print(f"\nMacro Average:")
    print(f"  Precision: {np.mean(precision):.4f}")
    print(f"  Recall: {np.mean(recall):.4f}")
    print(f"  F1-Score: {np.mean(f1):.4f}")

    return {
        'accuracy': accuracy,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'confusion_matrix': cm,
        'predictions': y_pred
    }


# ========== 可视化 ==========
def plot_training_history(history, save_path):
    """绘制训练历史"""
    colors = {'train': '#1f77b4', 'val': '#ff7f0e'}

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

    epochs = len(history['accuracy'])
    epoch_range = np.arange(epochs)

    ax1.plot(epoch_range, history['accuracy'], color=colors['train'], linewidth=2, label='Training')
    ax1.plot(epoch_range, history['val_accuracy'], color=colors['val'], linewidth=2, linestyle='--', label='Validation')
    ax1.set_xlabel('Epoch', fontsize=12)
    ax1.set_ylabel('Accuracy', fontsize=12)
    ax1.legend(frameon=False)
    ax1.grid(True, alpha=0.3)

    ax2.plot(epoch_range, history['loss'], color=colors['train'], linewidth=2, label='Training')
    ax2.plot(epoch_range, history['val_loss'], color=colors['val'], linewidth=2, linestyle='--', label='Validation')
    ax2.set_xlabel('Epoch', fontsize=12)
    ax2.set_ylabel('Loss', fontsize=12)
    ax2.legend(frameon=False)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    log(f"Saved training history: {save_path}")


def plot_confusion_matrix(cm, label_names, save_path):
    """绘制混淆矩阵"""
    class_names = [label_names[i] for i in range(3)]

    fig, ax = plt.subplots(figsize=(5, 4.5))

    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                cbar=False, linewidths=1.5, linecolor='white',
                square=True, ax=ax, annot_kws={'size': 14})

    ax.set_xticklabels(class_names, rotation=0, ha='center', fontsize=11)
    ax.set_yticklabels(class_names, rotation=90, va='center', fontsize=11)
    ax.set_xlabel('Predicted', fontsize=12)
    ax.set_ylabel('Actual', fontsize=12)

    threshold = cm.max() * 0.5
    for text in ax.texts:
        pos = text.get_position()
        row, col = int(pos[1]), int(pos[0])
        if cm[row, col] > threshold:
            text.set_color('white')

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    log(f"Saved confusion matrix: {save_path}")


# ========== 主函数 ==========
def main():
    parser = argparse.ArgumentParser(description='Train attack detection model (PyTorch)')
    parser.add_argument('-d', '--dataset', type=str, default='combined',
                        choices=list(DATASETS.keys()),
                        help='Dataset to use (default: combined)')
    parser.add_argument('-m', '--model', type=str, default='lstm',
                        choices=list(MODEL_REGISTRY.keys()),
                        help='Model to use (default: lstm)')
    parser.add_argument('-w', '--window', type=int, default=12,
                        help='Window size (default: 12)')
    parser.add_argument('-e', '--epochs', type=int, default=100,
                        help='Max epochs (default: 100)')
    parser.add_argument('-b', '--batch', type=int, default=32,
                        help='Batch size (default: 32)')
    parser.add_argument('-lr', '--learning-rate', type=float, default=0.001,
                        help='Learning rate (default: 0.001)')
    parser.add_argument('--list', action='store_true',
                        help='List available options')

    args = parser.parse_args()

    if args.list:
        print("Available datasets:", list(DATASETS.keys()))
        print("Available models:", list(MODEL_REGISTRY.keys()))
        return

    section(f"Training {args.model.upper()} on {args.dataset}")
    log(f"Window size: {args.window}")
    log(f"Device: {DEVICE}")

    output_dir = OUTPUT_DIR / args.dataset / f"window_{args.window}" / args.model
    output_dir.mkdir(parents=True, exist_ok=True)

    train_df, val_df, test_df, label_names = load_dataset(args.dataset, args.window)
    data = prepare_data(train_df, val_df, test_df, args.window, args.model)

    input_shape = data['X_train'].shape[1:]
    log(f"Input shape: {input_shape}")

    model = get_model(args.model, input_shape, num_classes=3)
    log(f"Model parameters: {sum(p.numel() for p in model.parameters()):,}")

    history = train_model(model, data, epochs=args.epochs, batch_size=args.batch,
                          learning_rate=args.learning_rate)

    results = evaluate_model(model, data, label_names)

    plot_training_history(history, output_dir / "training_history.png")
    plot_confusion_matrix(results['confusion_matrix'], label_names,
                          output_dir / "confusion_matrix.png")
    torch.save(model.state_dict(), output_dir / "model.pt")

    section("Done!")
    log(f"Results saved to: {output_dir}")


if __name__ == "__main__":
    main()
