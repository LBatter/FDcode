#!/usr/bin/env python3
"""
build_windows_dataset.py - 从 data/windows 构建数据集

数据来源：
  data/windows/train/    - 训练数据 -> 划分为 train (75%) + val (25%)
    - benign.csv         -> label 0
    - prefetch.csv       -> label 1
    - primescope.csv     -> label 2
  data/windows/test/     - 测试数据 -> test (100%)
    - benign.csv         -> label 0
    - prefetch.csv       -> label 1
    - primescope.csv     -> label 2

输出结构：
  dataset/windows/window_X/
    - train.csv          - 训练集 (~60%)
    - val.csv            - 验证集 (~20%)
    - test.csv           - 测试集 (~20%)

用法:
  python3 build_windows_dataset.py                    # 默认窗口12
  python3 build_windows_dataset.py -w 10             # 指定窗口大小
  python3 build_windows_dataset.py --experiment      # 窗口实验(6-20)
"""

import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

# ========== 配置 ==========
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "windows"
OUTPUT_DIR = BASE_DIR / "dataset" / "windows"

SEED = 42

# ========== 工具函数 ==========
class Colors:
    GREEN = '\033[92m'
    CYAN = '\033[96m'
    END = '\033[0m'


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{Colors.GREEN}[{ts}]{Colors.END} {msg}")


def section(title):
    print(f"\n{Colors.CYAN}========== {title} =========={Colors.END}")


def create_samples(df, window_size, label):
    """将连续数据按窗口大小切分为样本"""
    feature_cols = [col for col in df.columns if col != 'Label']

    n_rows = len(df)
    n_samples = n_rows // window_size
    samples = []

    for i in range(n_samples):
        start_idx = i * window_size
        end_idx = start_idx + window_size

        sample_df = df.iloc[start_idx:end_idx][feature_cols].copy()
        sample_df['Label'] = np.nan
        sample_df.iloc[0, sample_df.columns.get_loc('Label')] = label

        samples.append(sample_df)

    return samples


def split_samples(samples, train_ratio, seed=42):
    """划分样本为训练集和验证集"""
    np.random.seed(seed)
    indices = np.random.permutation(len(samples))

    n_train = int(len(samples) * train_ratio)

    train_indices = indices[:n_train]
    val_indices = indices[n_train:]

    train_samples = [samples[i] for i in train_indices]
    val_samples = [samples[i] for i in val_indices]

    return train_samples, val_samples


def merge_and_shuffle(samples_list, seed=42):
    """合并多个样本列表并打乱"""
    if not samples_list:
        return pd.DataFrame()

    all_samples = []
    for samples in samples_list:
        all_samples.extend(samples)

    np.random.seed(seed)
    np.random.shuffle(all_samples)

    return pd.concat(all_samples, ignore_index=True)


def build_windows_dataset(window_size):
    """构建 windows 数据集"""
    section(f"Building Windows Dataset (window={window_size})")

    train_dir = DATA_DIR / "train"
    test_dir = DATA_DIR / "test"
    output_dir = OUTPUT_DIR / f"window_{window_size}"

    files = {
        'benign': 0,
        'prefetch': 1,
        'primescope': 2
    }

    # 先统计测试集大小，用于计算验证集比例
    log("Counting test samples...")
    test_sample_counts = {}
    for name, label in files.items():
        test_file = test_dir / f"{name}.csv"
        if test_file.exists():
            df = pd.read_csv(test_file)
            n_samples = len(df) // window_size
            test_sample_counts[name] = n_samples
            log(f"  {name}: {n_samples} test samples")

    total_test_samples = sum(test_sample_counts.values())
    log(f"Total test samples: {total_test_samples}")

    # 处理训练数据
    log("\nProcessing train data...")
    all_train = []
    all_val = []
    train_sample_counts = {}

    for name, label in files.items():
        train_file = train_dir / f"{name}.csv"
        if not train_file.exists():
            log(f"Warning: {train_file} not found, skipping...")
            continue

        log(f"Processing {name} (label={label})...")
        df = pd.read_csv(train_file)
        log(f"  Loaded {len(df)} rows")

        samples = create_samples(df, window_size, label)
        log(f"  Created {len(samples)} samples")
        train_sample_counts[name] = len(samples)

        # 计算验证集比例：使验证集大小接近测试集
        # 目标：train:val:test ≈ 60:20:20
        # val 应该和 test 差不多大
        test_count = test_sample_counts.get(name, 0)
        total_train_samples = len(samples)

        # val_ratio 使得 val ≈ test
        # val = total_train * val_ratio
        # 我们希望 val ≈ test，所以 val_ratio ≈ test / total_train
        if total_train_samples > 0:
            val_ratio = min(test_count / total_train_samples, 0.4)  # 最多40%作为验证集
            val_ratio = max(val_ratio, 0.2)  # 至少20%作为验证集
        else:
            val_ratio = 0.25

        train_ratio = 1 - val_ratio

        train, val = split_samples(samples, train_ratio, SEED + label)
        log(f"  Split: train={len(train)}, val={len(val)} (val_ratio={val_ratio:.2f})")

        all_train.append(train)
        all_val.append(val)

    # 处理测试数据
    log("\nProcessing test data...")
    all_test = []

    for name, label in files.items():
        test_file = test_dir / f"{name}.csv"
        if not test_file.exists():
            log(f"Warning: {test_file} not found, skipping...")
            continue

        log(f"Processing {name} (label={label})...")
        df = pd.read_csv(test_file)
        log(f"  Loaded {len(df)} rows")

        samples = create_samples(df, window_size, label)
        log(f"  Created {len(samples)} samples")

        all_test.append(samples)

    # 合并并保存
    train_df = merge_and_shuffle(all_train, SEED)
    val_df = merge_and_shuffle(all_val, SEED + 1)
    test_df = merge_and_shuffle(all_test, SEED + 2)

    output_dir.mkdir(parents=True, exist_ok=True)

    train_df.to_csv(output_dir / "train.csv", index=False)
    val_df.to_csv(output_dir / "val.csv", index=False)
    test_df.to_csv(output_dir / "test.csv", index=False)

    log(f"\nSaved to {output_dir}")
    log(f"  Train: {len(train_df)} rows")
    log(f"  Val: {len(val_df)} rows")
    log(f"  Test: {len(test_df)} rows")

    # 打印标签分布
    section("Label Distribution")

    for name, df in [("Train", train_df), ("Val", val_df), ("Test", test_df)]:
        labels = df[df['Label'].notna()]['Label'].astype(int)
        n_samples = len(labels)
        print(f"\n{name} ({n_samples} samples):")
        for label in sorted(labels.unique()):
            count = (labels == label).sum()
            pct = count / n_samples * 100
            print(f"  Label {label}: {count} ({pct:.1f}%)")

    # 打印比例
    train_samples = len(train_df) // window_size
    val_samples = len(val_df) // window_size
    test_samples = len(test_df) // window_size
    total = train_samples + val_samples + test_samples

    print(f"\nDataset Split Ratio:")
    print(f"  Train: {train_samples} ({train_samples/total*100:.1f}%)")
    print(f"  Val:   {val_samples} ({val_samples/total*100:.1f}%)")
    print(f"  Test:  {test_samples} ({test_samples/total*100:.1f}%)")

    return output_dir


def run_experiment():
    """运行窗口大小实验"""
    section("Window Size Experiment")

    window_sizes = [6, 8, 10, 12, 14, 16, 18, 20]

    for ws in window_sizes:
        log(f"\n>>> Window size: {ws}")
        build_windows_dataset(ws)

    section("Experiment Summary")
    print("Window sizes processed:", window_sizes)


def main():
    parser = argparse.ArgumentParser(description='Build windows dataset')
    parser.add_argument('-w', '--window', type=int, default=12,
                        help='Window size (default: 12)')
    parser.add_argument('--experiment', action='store_true',
                        help='Run window size experiment (6-20)')

    args = parser.parse_args()

    if args.experiment:
        run_experiment()
    else:
        build_windows_dataset(args.window)

    section("Done!")


if __name__ == "__main__":
    main()
