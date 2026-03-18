#!/usr/bin/env python3
"""
build_dataset.py - 构建数据集（支持窗口大小实验）

数据来源：
  data/heavy_load/      - 满负载数据
    - benign.csv        -> label 0
    - prefetch.csv      -> label 1
    - primescope.csv    -> label 2
  data/light_load/      - 轻负载数据
    - benign.csv        -> label 0
    - prefetch.csv      -> label 1
    - primescope.csv    -> label 2
  data/traditional/     - 传统攻击数据
    - benign.csv        -> label 0
    - fr.csv + ff.csv   -> flush.csv -> label 1
    - pp.csv            -> label 2

输出结构：
  dataset/heavy_load/window_X/
    - train.csv         - 训练集 (60%)
    - val.csv           - 验证集 (20%)
    - test.csv          - 测试集 (20%)
  dataset/light_load/window_X/
    - train.csv         - 训练集 (60%)
    - val.csv           - 验证集 (20%)
    - test.csv          - 测试集 (20%)
  dataset/combined/window_X/
    - train.csv         - 合并的训练集 (heavy + light)
    - val.csv           - 合并的验证集 (heavy + light)
  dataset/traditional/window_X/
    - train.csv
    - val.csv
    - test.csv

用法:
  python3 build_dataset.py                          # 默认窗口12
  python3 build_dataset.py -w 10                    # 指定窗口大小
  python3 build_dataset.py --experiment             # 窗口实验(6-20)
  python3 build_dataset.py --traditional            # 只处理传统攻击
  python3 build_dataset.py --heavy                  # 只处理满负载
  python3 build_dataset.py --light                  # 只处理轻负载
  python3 build_dataset.py --combined               # 只处理合并数据
"""

import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

# ========== 配置 ==========
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "dataset"

# 特征列
FEATURE_COLS = [
    "timestamp",
    "LLC-load-misses",
    "L1-dcache-load-misses",
    "branch-misses",
    "l1d.replacement",
    "sw_prefetch_access.prefetchw"
]

# 随机种子
SEED = 42

# 数据集划分比例
TRAIN_RATIO = 0.6
VAL_RATIO = 0.2
TEST_RATIO = 0.2


# ========== 工具函数 ==========
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    END = '\033[0m'


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{Colors.GREEN}[{ts}]{Colors.END} {msg}")


def section(title):
    print(f"\n{Colors.CYAN}========== {title} =========={Colors.END}")


def load_csv(filepath):
    """加载CSV文件"""
    df = pd.read_csv(filepath)
    return df


def create_samples(df, window_size, label):
    """
    将连续数据按窗口大小切分为样本

    参数:
        df: 原始数据DataFrame
        window_size: 窗口大小
        label: 标签值

    返回:
        samples: list of DataFrames，每个是一个样本（window_size行）
    """
    # 获取特征列（排除可能存在的Label列）
    feature_cols = [col for col in df.columns if col != 'Label']

    n_rows = len(df)
    n_samples = n_rows // window_size
    samples = []

    for i in range(n_samples):
        start_idx = i * window_size
        end_idx = start_idx + window_size

        sample_df = df.iloc[start_idx:end_idx][feature_cols].copy()

        # 添加Label列，只有第一行有标签值
        sample_df['Label'] = np.nan
        sample_df.iloc[0, sample_df.columns.get_loc('Label')] = label

        samples.append(sample_df)

    return samples


def split_samples(samples, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2, seed=42):
    """
    划分样本为训练集、验证集、测试集

    参数:
        samples: 样本列表
        train_ratio: 训练集比例
        val_ratio: 验证集比例
        test_ratio: 测试集比例
        seed: 随机种子

    返回:
        train_samples, val_samples, test_samples
    """
    np.random.seed(seed)
    indices = np.random.permutation(len(samples))

    n_train = int(len(samples) * train_ratio)
    n_val = int(len(samples) * val_ratio)

    train_indices = indices[:n_train]
    val_indices = indices[n_train:n_train + n_val]
    test_indices = indices[n_train + n_val:]

    train_samples = [samples[i] for i in train_indices]
    val_samples = [samples[i] for i in val_indices]
    test_samples = [samples[i] for i in test_indices]

    return train_samples, val_samples, test_samples


def merge_samples(samples_list):
    """合并多个样本列表为一个DataFrame"""
    if not samples_list:
        return pd.DataFrame()

    all_samples = []
    for samples in samples_list:
        all_samples.extend(samples)

    # 打乱顺序
    np.random.seed(SEED)
    np.random.shuffle(all_samples)

    return pd.concat(all_samples, ignore_index=True)


def save_dataset(train_df, val_df, test_df, output_dir):
    """保存数据集（包含测试集）"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    train_df.to_csv(output_dir / "train.csv", index=False)
    val_df.to_csv(output_dir / "val.csv", index=False)
    test_df.to_csv(output_dir / "test.csv", index=False)

    log(f"Saved to {output_dir}")
    log(f"  Train: {len(train_df)} rows")
    log(f"  Val: {len(val_df)} rows")
    log(f"  Test: {len(test_df)} rows")


def save_dataset_no_test(train_df, val_df, output_dir):
    """保存数据集（不包含测试集）"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    train_df.to_csv(output_dir / "train.csv", index=False)
    val_df.to_csv(output_dir / "val.csv", index=False)

    log(f"Saved to {output_dir}")
    log(f"  Train: {len(train_df)} rows")
    log(f"  Val: {len(val_df)} rows")


def print_label_distribution(train_df, val_df, test_df, window_size):
    """打印标签分布"""
    section("Label Distribution")

    for name, df in [("Train", train_df), ("Val", val_df), ("Test", test_df)]:
        if df is None or len(df) == 0:
            continue
        labels = df[df['Label'].notna()]['Label'].astype(int)
        n_samples = len(labels)
        print(f"\n{name} ({n_samples} samples):")
        for label in sorted(labels.unique()):
            count = (labels == label).sum()
            pct = count / n_samples * 100
            print(f"  Label {label}: {count} ({pct:.1f}%)")


# ========== 通用数据处理函数 ==========
def process_load_data(data_dir, output_dir, window_size, dataset_name):
    """
    处理负载数据（满负载或轻负载）

    标签:
        benign -> 0
        prefetch -> 1
        primescope -> 2
    """
    section(f"Building {dataset_name} Dataset (window={window_size})")

    files = {
        'benign': (data_dir / "benign.csv", 0),
        'prefetch': (data_dir / "prefetch.csv", 1),
        'primescope': (data_dir / "primescope.csv", 2)
    }

    all_train = []
    all_val = []
    all_test = []

    for name, (filepath, label) in files.items():
        if not filepath.exists():
            log(f"Warning: {filepath} not found, skipping...")
            continue

        log(f"Processing {name} (label={label})...")
        df = load_csv(filepath)
        log(f"  Loaded {len(df)} rows")

        # 创建样本
        samples = create_samples(df, window_size, label)
        log(f"  Created {len(samples)} samples")

        # 划分数据集
        train, val, test = split_samples(samples, TRAIN_RATIO, VAL_RATIO, TEST_RATIO, SEED)
        log(f"  Split: train={len(train)}, val={len(val)}, test={len(test)}")

        all_train.append(train)
        all_val.append(val)
        all_test.append(test)

    # 合并所有类别
    train_df = merge_samples(all_train)
    val_df = merge_samples(all_val)
    test_df = merge_samples(all_test)

    # 保存
    save_dataset(train_df, val_df, test_df, output_dir)

    # 打印统计
    print_label_distribution(train_df, val_df, test_df, window_size)

    return train_df, val_df, test_df


# ========== 满负载数据处理 ==========
def build_heavy_load_dataset(window_size):
    """构建满负载数据集"""
    data_dir = DATA_DIR / "heavy_load"
    output_dir = OUTPUT_DIR / "heavy_load" / f"window_{window_size}"
    return process_load_data(data_dir, output_dir, window_size, "Heavy Load")


# ========== 轻负载数据处理 ==========
def build_light_load_dataset(window_size):
    """构建轻负载数据集"""
    data_dir = DATA_DIR / "light_load"
    output_dir = OUTPUT_DIR / "light_load" / f"window_{window_size}"
    return process_load_data(data_dir, output_dir, window_size, "Light Load")


# ========== 合并数据集 ==========
def build_combined_dataset(window_size):
    """
    合并轻负载和满负载的训练集和验证集
    """
    section(f"Building Combined Dataset (window={window_size})")

    heavy_dir = OUTPUT_DIR / "heavy_load" / f"window_{window_size}"
    light_dir = OUTPUT_DIR / "light_load" / f"window_{window_size}"
    output_dir = OUTPUT_DIR / "combined" / f"window_{window_size}"

    # 检查是否已有数据，如果没有则先构建
    if not (heavy_dir / "train.csv").exists():
        log("Heavy load dataset not found, building...")
        build_heavy_load_dataset(window_size)

    if not (light_dir / "train.csv").exists():
        log("Light load dataset not found, building...")
        build_light_load_dataset(window_size)

    # 加载训练集和验证集
    log("Loading heavy load data...")
    heavy_train = pd.read_csv(heavy_dir / "train.csv")
    heavy_val = pd.read_csv(heavy_dir / "val.csv")
    log(f"  Train: {len(heavy_train)} rows, Val: {len(heavy_val)} rows")

    log("Loading light load data...")
    light_train = pd.read_csv(light_dir / "train.csv")
    light_val = pd.read_csv(light_dir / "val.csv")
    log(f"  Train: {len(light_train)} rows, Val: {len(light_val)} rows")

    # 合并
    log("Merging datasets...")
    combined_train = pd.concat([heavy_train, light_train], ignore_index=True)
    combined_val = pd.concat([heavy_val, light_val], ignore_index=True)

    # 打乱
    np.random.seed(SEED)
    combined_train = combined_train.sample(frac=1, random_state=SEED).reset_index(drop=True)
    combined_val = combined_val.sample(frac=1, random_state=SEED).reset_index(drop=True)

    # 保存
    save_dataset_no_test(combined_train, combined_val, output_dir)

    # 打印统计
    section("Label Distribution (Combined)")
    for name, df in [("Train", combined_train), ("Val", combined_val)]:
        labels = df[df['Label'].notna()]['Label'].astype(int)
        n_samples = len(labels)
        print(f"\n{name} ({n_samples} samples):")
        for label in sorted(labels.unique()):
            count = (labels == label).sum()
            pct = count / n_samples * 100
            print(f"  Label {label}: {count} ({pct:.1f}%)")

    return combined_train, combined_val


# ========== 传统攻击数据处理 ==========
def build_traditional_dataset(window_size):
    """
    构建传统攻击数据集

    标签:
        benign -> 0
        flush (fr + ff) -> 1
        pp -> 2
    """
    section(f"Building Traditional Dataset (window={window_size})")

    data_dir = DATA_DIR / "traditional"
    output_dir = OUTPUT_DIR / "traditional" / f"window_{window_size}"

    all_train = []
    all_val = []
    all_test = []

    # --- Benign (label=0) ---
    benign_file = data_dir / "benign.csv"
    if benign_file.exists():
        log("Processing benign (label=0)...")
        df = load_csv(benign_file)
        log(f"  Loaded {len(df)} rows")

        samples = create_samples(df, window_size, 0)
        log(f"  Created {len(samples)} samples")

        train, val, test = split_samples(samples, TRAIN_RATIO, VAL_RATIO, TEST_RATIO, SEED)
        log(f"  Split: train={len(train)}, val={len(val)}, test={len(test)}")

        all_train.append(train)
        all_val.append(val)
        all_test.append(test)
    else:
        log(f"Warning: {benign_file} not found")

    # --- Flush (fr + ff -> label=1) ---
    log("Processing flush (fr + ff -> label=1)...")
    flush_dfs = []

    fr_file = data_dir / "fr.csv"
    if fr_file.exists():
        fr_df = load_csv(fr_file)
        flush_dfs.append(fr_df)
        log(f"  Loaded fr.csv: {len(fr_df)} rows")

    ff_file = data_dir / "ff.csv"
    if ff_file.exists():
        ff_df = load_csv(ff_file)
        flush_dfs.append(ff_df)
        log(f"  Loaded ff.csv: {len(ff_df)} rows")

    if flush_dfs:
        # 合并fr和ff
        flush_df = pd.concat(flush_dfs, ignore_index=True)
        log(f"  Merged flush: {len(flush_df)} rows")

        samples = create_samples(flush_df, window_size, 1)
        log(f"  Created {len(samples)} samples")

        train, val, test = split_samples(samples, TRAIN_RATIO, VAL_RATIO, TEST_RATIO, SEED + 1)
        log(f"  Split: train={len(train)}, val={len(val)}, test={len(test)}")

        all_train.append(train)
        all_val.append(val)
        all_test.append(test)

    # --- Prime+Probe (label=2) ---
    pp_file = data_dir / "pp.csv"
    if pp_file.exists():
        log("Processing pp (label=2)...")
        df = load_csv(pp_file)
        log(f"  Loaded {len(df)} rows")

        samples = create_samples(df, window_size, 2)
        log(f"  Created {len(samples)} samples")

        train, val, test = split_samples(samples, TRAIN_RATIO, VAL_RATIO, TEST_RATIO, SEED + 2)
        log(f"  Split: train={len(train)}, val={len(val)}, test={len(test)}")

        all_train.append(train)
        all_val.append(val)
        all_test.append(test)
    else:
        log(f"Warning: {pp_file} not found")

    # 合并所有类别
    train_df = merge_samples(all_train)
    val_df = merge_samples(all_val)
    test_df = merge_samples(all_test)

    # 保存
    save_dataset(train_df, val_df, test_df, output_dir)

    # 打印统计
    print_label_distribution(train_df, val_df, test_df, window_size)

    return output_dir


# ========== 窗口实验 ==========
def run_window_experiment(dataset_type='all'):
    """运行窗口大小实验"""
    section(f"Window Size Experiment ({dataset_type})")

    window_sizes = [6, 8, 10, 12, 14, 16, 18, 20]
    results = []

    for ws in window_sizes:
        log(f"\n>>> Window size: {ws}")

        if dataset_type == 'heavy':
            build_heavy_load_dataset(ws)
        elif dataset_type == 'light':
            build_light_load_dataset(ws)
        elif dataset_type == 'combined':
            build_combined_dataset(ws)
        elif dataset_type == 'traditional':
            build_traditional_dataset(ws)
        else:
            # 处理所有
            build_heavy_load_dataset(ws)
            build_light_load_dataset(ws)
            build_combined_dataset(ws)
            build_traditional_dataset(ws)

        results.append({'window': ws})

    # 打印汇总
    section("Experiment Summary")
    print("Window sizes processed:", [r['window'] for r in results])


# ========== 主函数 ==========
def main():
    parser = argparse.ArgumentParser(description='Build dataset with sliding window')
    parser.add_argument('-w', '--window', type=int, default=12,
                        help='Window size (default: 12)')
    parser.add_argument('--experiment', action='store_true',
                        help='Run window size experiment (6-20)')
    parser.add_argument('--heavy', action='store_true',
                        help='Only process heavy load data')
    parser.add_argument('--light', action='store_true',
                        help='Only process light load data')
    parser.add_argument('--combined', action='store_true',
                        help='Only process combined data')
    parser.add_argument('--traditional', action='store_true',
                        help='Only process traditional attack data')

    args = parser.parse_args()

    if args.experiment:
        if args.traditional:
            run_window_experiment('traditional')
        elif args.heavy:
            run_window_experiment('heavy')
        elif args.light:
            run_window_experiment('light')
        elif args.combined:
            run_window_experiment('combined')
        else:
            run_window_experiment('all')
    else:
        if args.traditional:
            build_traditional_dataset(args.window)
        elif args.heavy:
            build_heavy_load_dataset(args.window)
        elif args.light:
            build_light_load_dataset(args.window)
        elif args.combined:
            build_combined_dataset(args.window)
        else:
            # 默认处理所有
            build_heavy_load_dataset(args.window)
            build_light_load_dataset(args.window)
            build_combined_dataset(args.window)
            build_traditional_dataset(args.window)

    section("Done!")


if __name__ == "__main__":
    main()
