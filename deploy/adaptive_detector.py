#!/usr/bin/env python3
"""
adaptive_detector.py - 自适应核心监控检测器

基于特征异常的两阶段检测：
1. 轮询模式：低频采集LLC_MISSES和CACHE_REFERENCES，检测异常核心
2. 聚焦模式：对可疑核心高频采集全部特征，使用LSTM检测攻击

用法:
  sudo python3 adaptive_detector.py                    # 默认参数运行
  sudo python3 adaptive_detector.py --baseline 10     # 建立10秒基线
  sudo python3 adaptive_detector.py --threshold 3     # 设置3-sigma阈值
"""

import os
import sys
import time
import argparse
import signal
import json
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import deque
from enum import Enum

# ========== 配置 ==========
BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "output" / "windows" / "window_12" / "lstm"
CONFIG_FILE = BASE_DIR / "deploy" / "baseline.json"

# 触发特征（轮询模式使用）
TRIGGER_EVENTS = [
    "LLC-load-misses",      # LLC_MISSES
    "cache-references",     # CACHE_REFERENCES
]

# 完整特征（聚焦模式使用，与训练时一致，共5个）
FULL_EVENTS = [
    "LLC-load-misses",
    "L1-dcache-load-misses",
    "branch-misses",
    "l1d.replacement",
    "sw_prefetch_access.prefetchw",
]

# 参数默认值
DEFAULT_PARAMS = {
    'poll_interval': 0.1,      # 轮询间隔 100ms
    'focus_interval': 0.01,    # 聚焦间隔 10ms
    'threshold_k': 5,          # 异常阈值 mean + k*std (提高到5)
    'window_size': 12,         # LSTM窗口大小
    'recovery_count': 5,       # 连续N次正常后恢复轮询
    'baseline_duration': 10,   # 基线建立时间（秒）
}


class DetectorState(Enum):
    BASELINE = "baseline"      # 建立基线
    POLLING = "polling"        # 轮询模式
    FOCUSING = "focusing"      # 聚焦模式


class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    END = '\033[0m'


def log(msg, level="info"):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    if level == "info":
        print(f"{Colors.GREEN}[{ts}]{Colors.END} {msg}")
    elif level == "warn":
        print(f"{Colors.YELLOW}[{ts}] WARNING:{Colors.END} {msg}")
    elif level == "error":
        print(f"{Colors.RED}[{ts}] ERROR:{Colors.END} {msg}")
    elif level == "alert":
        print(f"{Colors.RED}[{ts}] *** ALERT ***{Colors.END} {msg}")


def get_cpu_count():
    """获取CPU核心数"""
    try:
        return os.cpu_count() or 1
    except:
        return 1


def get_system_load():
    """获取系统负载信息"""
    try:
        # CPU使用率
        with open('/proc/stat', 'r') as f:
            line = f.readline()
            fields = line.split()[1:]
            idle = int(fields[3])
            total = sum(int(x) for x in fields[:8])
        return idle, total
    except:
        return 0, 1


def calculate_cpu_usage(prev_idle, prev_total, curr_idle, curr_total):
    """计算CPU使用率"""
    idle_delta = curr_idle - prev_idle
    total_delta = curr_total - prev_total
    if total_delta == 0:
        return 0
    return (1 - idle_delta / total_delta) * 100


class SystemMonitor:
    """系统负载监控器"""

    def __init__(self):
        self.samples_before = []  # 部署前的负载样本
        self.samples_during = []  # 部署中的负载样本
        self.prev_idle = 0
        self.prev_total = 0
        self._init_cpu_stats()

    def _init_cpu_stats(self):
        """初始化CPU统计"""
        self.prev_idle, self.prev_total = get_system_load()

    def sample(self):
        """采样一次CPU使用率"""
        curr_idle, curr_total = get_system_load()
        usage = calculate_cpu_usage(self.prev_idle, self.prev_total, curr_idle, curr_total)
        self.prev_idle, self.prev_total = curr_idle, curr_total
        return usage

    def collect_baseline(self, duration=30):
        """采集部署前的基线负载"""
        log(f"Collecting system load baseline for {duration} seconds...")
        self.samples_before = []
        start = time.time()

        while time.time() - start < duration:
            usage = self.sample()
            self.samples_before.append(usage)
            time.sleep(1)

        mean = np.mean(self.samples_before)
        std = np.std(self.samples_before)
        log(f"Baseline load: {mean:.2f}% ± {std:.2f}%")
        return self.samples_before

    def add_sample(self, usage):
        """添加运行中的负载样本"""
        self.samples_during.append(usage)

    def get_stats(self):
        """获取统计信息"""
        stats = {}
        if self.samples_before:
            stats['before'] = {
                'mean': np.mean(self.samples_before),
                'std': np.std(self.samples_before),
                'max': np.max(self.samples_before),
                'min': np.min(self.samples_before),
            }
        if self.samples_during:
            stats['during'] = {
                'mean': np.mean(self.samples_during),
                'std': np.std(self.samples_during),
                'max': np.max(self.samples_during),
                'min': np.min(self.samples_during),
            }
        return stats

    def save_data(self, filepath):
        """保存负载数据"""
        data = {
            'before': self.samples_before,
            'during': self.samples_during,
            'stats': self.get_stats()
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        log(f"Load data saved to {filepath}")

    def plot_comparison(self, output_path):
        """生成论文级别的负载对比图 - 柱状图对比"""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            # IEEE论文格式设置
            plt.rcParams.update({
                'font.family': 'serif',
                'font.serif': ['Times New Roman', 'DejaVu Serif'],
                'font.size': 9,
                'axes.linewidth': 0.8,
                'axes.labelsize': 9,
                'xtick.labelsize': 8,
                'ytick.labelsize': 8,
                'legend.fontsize': 8,
                'figure.dpi': 300,
            })

            stats = self.get_stats()

            # 单图：柱状图对比 + 开销标注
            fig, ax = plt.subplots(figsize=(3.5, 2.5))

            if stats.get('before') and stats.get('during'):
                before_mean = stats['before']['mean']
                during_mean = stats['during']['mean']
                before_std = stats['before']['std']
                during_std = stats['during']['std']
                overhead = during_mean - before_mean

                # 柱状图 - 使用浅灰和浅蓝
                x = [0, 1]
                heights = [before_mean, during_mean]
                colors = ['#b0b0b0', '#6baed6']  # 浅灰、浅蓝
                labels = ['Baseline\n(idle)', 'With\nDetector']

                bars = ax.bar(x, heights, color=colors,
                             width=0.5, edgecolor='black', linewidth=0.8)

                # 在柱子上标注数值
                for bar, h in zip(bars, heights):
                    ax.annotate(f'{h:.2f}%', xy=(bar.get_x() + bar.get_width()/2, h + 0.3),
                               ha='center', va='bottom', fontsize=8)

                # 标注开销
                ax.annotate('', xy=(1, during_mean), xytext=(1, before_mean),
                           arrowprops=dict(arrowstyle='<->', color='#333333', lw=1.2))
                ax.annotate(f'Overhead:\n+{overhead:.2f}%',
                           xy=(1.25, (before_mean + during_mean)/2),
                           ha='left', va='center', fontsize=8, color='#333333')

                ax.set_xticks(x)
                ax.set_xticklabels(labels)
                ax.set_ylabel('CPU Usage (%)')
                ax.set_ylim(0, max(heights) * 1.4)
                ax.grid(True, linestyle=':', alpha=0.5, axis='y')

                # 添加标题说明
                ax.set_title(f'Detection Overhead: +{overhead:.2f}% CPU', fontsize=9, pad=10)

            plt.tight_layout()

            # 保存
            for fmt in ['pdf', 'png']:
                save_path = output_path.parent / f"{output_path.stem}.{fmt}"
                plt.savefig(save_path, format=fmt, bbox_inches='tight', dpi=300)
                log(f"Saved: {save_path}")

            plt.close()

            # 打印统计对比
            self._print_comparison_stats(stats)

        except Exception as e:
            log(f"Failed to generate plot: {e}", "error")

    def _print_comparison_stats(self, stats):
        """打印统计对比"""
        print(f"\n{Colors.CYAN}{'='*60}{Colors.END}")
        print(f"{Colors.CYAN}System Load Comparison (for paper){Colors.END}")
        print(f"{Colors.CYAN}{'='*60}{Colors.END}")
        print(f"{'Metric':<20} {'Before':<15} {'During':<15} {'Overhead':<15}")
        print("-" * 60)

        if stats.get('before') and stats.get('during'):
            before_mean = stats['before']['mean']
            during_mean = stats['during']['mean']
            overhead = during_mean - before_mean
            overhead_pct = (overhead / before_mean * 100) if before_mean > 0 else 0

            print(f"{'Mean CPU (%)':<20} {before_mean:<15.2f} {during_mean:<15.2f} {overhead:+.2f} ({overhead_pct:+.1f}%)")
            print(f"{'Std CPU (%)':<20} {stats['before']['std']:<15.2f} {stats['during']['std']:<15.2f}")
            print(f"{'Max CPU (%)':<20} {stats['before']['max']:<15.2f} {stats['during']['max']:<15.2f}")
            print(f"{'Min CPU (%)':<20} {stats['before']['min']:<15.2f} {stats['during']['min']:<15.2f}")

        print(f"{Colors.CYAN}{'='*60}{Colors.END}")


class HPCCollector:
    """HPC数据采集器（使用perf）"""

    def __init__(self, events, cpu_id, interval=0.01):
        self.events = events
        self.cpu_id = cpu_id
        self.interval = interval

    def collect_once(self):
        """采集一次HPC数据"""
        import subprocess

        event_str = ",".join(self.events)
        cmd = [
            "perf", "stat",
            "-e", event_str,
            "-C", str(self.cpu_id),
            "-x", ",",
            "--", "sleep", str(self.interval)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return self._parse_output(result.stderr)
        except subprocess.TimeoutExpired:
            return None
        except Exception as e:
            log(f"Perf error: {e}", "error")
            return None

    def _parse_output(self, output):
        """解析perf输出"""
        values = {}
        for line in output.strip().split('\n'):
            if not line or line.startswith('#'):
                continue
            parts = line.split(',')
            if len(parts) >= 3:
                try:
                    value = float(parts[0]) if parts[0] != '<not counted>' else 0
                    event_name = parts[2]
                    values[event_name] = value
                except (ValueError, IndexError):
                    continue
        return values if values else None


class AdaptiveDetector:
    """自适应核心监控检测器"""

    def __init__(self, params=None):
        self.params = {**DEFAULT_PARAMS, **(params or {})}
        self.state = DetectorState.BASELINE
        self.cpu_count = get_cpu_count()

        # 基线数据
        self.baseline = {
            'llc_misses': {'mean': 0, 'std': 0},
            'cache_refs': {'mean': 0, 'std': 0},
            'miss_rate': {'mean': 0, 'std': 0},
        }

        # 聚焦模式数据
        self.focus_cpu = None
        self.focus_buffer = deque(maxlen=self.params['window_size'])
        self.normal_count = 0

        # LSTM模型
        self.model = None
        self.scaler = None

        # 统计
        self.stats = {
            'polls': 0,
            'anomalies': 0,
            'detections': 0,
            'false_alarms': 0,
        }

        # 系统负载监控
        self.system_monitor = SystemMonitor()

        # 运行标志
        self.running = False

    def load_model(self):
        """加载训练好的LSTM模型"""
        try:
            import torch
            sys.path.insert(0, str(BASE_DIR / "model"))
            from models import get_model

            model_path = MODEL_DIR / "model.pt"
            if not model_path.exists():
                log(f"Model not found: {model_path}", "error")
                return False

            # 创建模型并加载权重
            input_shape = (self.params['window_size'], len(FULL_EVENTS))  # (12, 5)
            self.model = get_model('lstm', input_shape, num_classes=3)
            self.model.load_state_dict(torch.load(model_path, map_location='cpu'))
            self.model.eval()

            log(f"Loaded model from {model_path}")
            return True
        except Exception as e:
            log(f"Failed to load model: {e}", "error")
            return False

    def build_baseline(self, duration=None):
        """建立基线"""
        duration = duration or self.params['baseline_duration']
        log(f"Building baseline for {duration} seconds...")
        self.state = DetectorState.BASELINE

        llc_misses_list = []
        cache_refs_list = []
        miss_rate_list = []

        start_time = time.time()
        sample_count = 0

        while time.time() - start_time < duration:
            for cpu_id in range(self.cpu_count):
                collector = HPCCollector(TRIGGER_EVENTS, cpu_id, 0.05)
                data = collector.collect_once()

                if data:
                    llc = data.get('LLC-load-misses', 0)
                    refs = data.get('cache-references', 1)
                    rate = llc / refs if refs > 0 else 0

                    llc_misses_list.append(llc)
                    cache_refs_list.append(refs)
                    miss_rate_list.append(rate)
                    sample_count += 1

            time.sleep(0.1)

        if sample_count < 10:
            log("Not enough samples for baseline", "error")
            return False

        # 计算统计值
        self.baseline['llc_misses']['mean'] = np.mean(llc_misses_list)
        self.baseline['llc_misses']['std'] = np.std(llc_misses_list)
        self.baseline['cache_refs']['mean'] = np.mean(cache_refs_list)
        self.baseline['cache_refs']['std'] = np.std(cache_refs_list)
        self.baseline['miss_rate']['mean'] = np.mean(miss_rate_list)
        self.baseline['miss_rate']['std'] = np.std(miss_rate_list)

        log(f"Baseline established ({sample_count} samples):")
        log(f"  LLC_MISSES: mean={self.baseline['llc_misses']['mean']:.2f}, std={self.baseline['llc_misses']['std']:.2f}")
        log(f"  CACHE_REFS: mean={self.baseline['cache_refs']['mean']:.2f}, std={self.baseline['cache_refs']['std']:.2f}")
        log(f"  MISS_RATE:  mean={self.baseline['miss_rate']['mean']:.4f}, std={self.baseline['miss_rate']['std']:.4f}")

        # 保存基线
        self._save_baseline()
        return True

    def _save_baseline(self):
        """保存基线到文件"""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.baseline, f, indent=2)
        log(f"Baseline saved to {CONFIG_FILE}")

    def _load_baseline(self):
        """从文件加载基线"""
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r') as f:
                self.baseline = json.load(f)
            log(f"Baseline loaded from {CONFIG_FILE}")
            return True
        return False

    def is_anomaly(self, llc_misses, cache_refs):
        """检测是否异常"""
        k = self.params['threshold_k']

        # 检查LLC_MISSES
        threshold_llc = self.baseline['llc_misses']['mean'] + k * self.baseline['llc_misses']['std']
        if llc_misses > threshold_llc:
            return True

        # 检查缺失率
        miss_rate = llc_misses / cache_refs if cache_refs > 0 else 0
        threshold_rate = self.baseline['miss_rate']['mean'] + k * self.baseline['miss_rate']['std']
        if miss_rate > threshold_rate:
            return True

        return False

    def poll_all_cores(self):
        """轮询所有核心"""
        anomaly_cores = []

        for cpu_id in range(self.cpu_count):
            collector = HPCCollector(TRIGGER_EVENTS, cpu_id, 0.05)
            data = collector.collect_once()

            if data:
                llc = data.get('LLC-load-misses', 0)
                refs = data.get('cache-references', 1)

                if self.is_anomaly(llc, refs):
                    anomaly_cores.append({
                        'cpu': cpu_id,
                        'llc_misses': llc,
                        'cache_refs': refs,
                        'miss_rate': llc / refs if refs > 0 else 0
                    })

        self.stats['polls'] += 1
        return anomaly_cores

    def focus_collect(self, cpu_id):
        """聚焦采集全部特征"""
        collector = HPCCollector(FULL_EVENTS, cpu_id, self.params['focus_interval'])
        data = collector.collect_once()

        if data:
            # 按照训练时的特征顺序排列
            features = [data.get(event, 0) for event in FULL_EVENTS]
            return features
        return None

    def predict(self, window_data):
        """使用LSTM预测"""
        if self.model is None:
            return None, 0

        try:
            import torch

            # 转换为tensor
            X = np.array(window_data)

            # 标准化（简单的z-score）
            X = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-8)

            X_tensor = torch.FloatTensor(X).unsqueeze(0)  # (1, window, features)

            with torch.no_grad():
                output = self.model(X_tensor)
                probs = torch.softmax(output, dim=1)
                pred = output.argmax(dim=1).item()
                confidence = probs[0, pred].item()

            return pred, confidence
        except Exception as e:
            log(f"Prediction error: {e}", "error")
            return None, 0

    def run(self, collect_load_baseline=False, load_baseline_duration=30):
        """主运行循环"""
        self.running = True
        log("Starting adaptive detector...")
        log(f"Monitoring {self.cpu_count} CPU cores")
        log(f"Trigger features: {TRIGGER_EVENTS}")
        log(f"Threshold: mean + {self.params['threshold_k']}*std")

        # 采集部署前的系统负载基线
        if collect_load_baseline:
            self.system_monitor.collect_baseline(load_baseline_duration)

        # 加载或建立基线
        if not self._load_baseline():
            if not self.build_baseline():
                return

        # 加载模型
        if not self.load_model():
            log("Running without LSTM model (anomaly detection only)", "warn")

        self.state = DetectorState.POLLING
        log("Entering polling mode...")

        labels = {0: 'Benign', 1: 'Prefetch Attack', 2: 'Prime+Scope Attack'}

        # 负载采样计时器
        last_load_sample = time.time()
        load_sample_interval = 1.0  # 每秒采样一次负载

        try:
            while self.running:
                # 定期采样系统负载
                if time.time() - last_load_sample >= load_sample_interval:
                    usage = self.system_monitor.sample()
                    self.system_monitor.add_sample(usage)
                    last_load_sample = time.time()

                if self.state == DetectorState.POLLING:
                    # 轮询模式
                    anomalies = self.poll_all_cores()

                    if anomalies:
                        self.stats['anomalies'] += 1
                        # 选择异常最严重的核心
                        worst = max(anomalies, key=lambda x: x['miss_rate'])
                        self.focus_cpu = worst['cpu']
                        self.focus_buffer.clear()
                        self.normal_count = 0
                        self.state = DetectorState.FOCUSING

                        log(f"Anomaly detected on CPU {self.focus_cpu}! "
                            f"LLC_MISSES={worst['llc_misses']:.0f}, "
                            f"MISS_RATE={worst['miss_rate']:.4f}", "warn")
                        log(f"Switching to focus mode on CPU {self.focus_cpu}")

                    time.sleep(self.params['poll_interval'])

                elif self.state == DetectorState.FOCUSING:
                    # 聚焦模式
                    features = self.focus_collect(self.focus_cpu)

                    if features:
                        self.focus_buffer.append(features)

                        # 窗口填满后进行预测
                        if len(self.focus_buffer) >= self.params['window_size']:
                            window_data = list(self.focus_buffer)
                            pred, conf = self.predict(window_data)

                            if pred is not None:
                                if pred != 0:  # 检测到攻击
                                    self.stats['detections'] += 1
                                    log(f"*** ATTACK DETECTED on CPU {self.focus_cpu}! ***", "alert")
                                    log(f"    Type: {labels[pred]}, Confidence: {conf:.2%}", "alert")
                                    self.normal_count = 0
                                else:
                                    self.normal_count += 1
                                    if self.normal_count >= self.params['recovery_count']:
                                        log(f"CPU {self.focus_cpu} returned to normal, resuming polling")
                                        self.state = DetectorState.POLLING
                                        self.focus_cpu = None

                            # 滑动窗口
                            self.focus_buffer.popleft()

                    time.sleep(self.params['focus_interval'])

        except KeyboardInterrupt:
            log("\nStopping detector...")

        self.print_stats()

        # 保存负载数据并生成对比图
        output_dir = BASE_DIR / "output" / "overhead"
        output_dir.mkdir(parents=True, exist_ok=True)
        self.system_monitor.save_data(output_dir / "load_data.json")
        self.system_monitor.plot_comparison(output_dir / "load_comparison")

    def print_stats(self):
        """打印统计信息"""
        print(f"\n{Colors.CYAN}{'='*50}{Colors.END}")
        print(f"{Colors.CYAN}Detection Statistics{Colors.END}")
        print(f"{Colors.CYAN}{'='*50}{Colors.END}")
        print(f"  Total polls:     {self.stats['polls']}")
        print(f"  Anomalies found: {self.stats['anomalies']}")
        print(f"  Attacks detected:{self.stats['detections']}")
        print(f"{Colors.CYAN}{'='*50}{Colors.END}")

    def stop(self):
        """停止检测器"""
        self.running = False


def main():
    parser = argparse.ArgumentParser(description='Adaptive Core Monitoring Detector')
    parser.add_argument('--baseline', type=int, default=10,
                        help='Baseline duration in seconds (default: 10)')
    parser.add_argument('--threshold', type=float, default=5,
                        help='Anomaly threshold k for mean+k*std (default: 5)')
    parser.add_argument('--poll-interval', type=float, default=0.1,
                        help='Polling interval in seconds (default: 0.1)')
    parser.add_argument('--rebuild-baseline', action='store_true',
                        help='Force rebuild baseline')
    parser.add_argument('--measure-overhead', action='store_true',
                        help='Measure system overhead (collect load before and during)')
    parser.add_argument('--load-baseline', type=int, default=30,
                        help='Duration to collect load baseline before detection (default: 30)')

    args = parser.parse_args()

    # 检查root权限
    if os.geteuid() != 0:
        log("This script requires root privileges for perf", "error")
        log("Please run with: sudo python3 adaptive_detector.py")
        sys.exit(1)

    params = {
        'baseline_duration': args.baseline,
        'threshold_k': args.threshold,
        'poll_interval': args.poll_interval,
    }

    detector = AdaptiveDetector(params)

    # 信号处理
    def signal_handler(sig, frame):
        detector.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 强重建基线
    if args.rebuild_baseline:
        CONFIG_FILE.unlink(missing_ok=True)

    detector.run(
        collect_load_baseline=args.measure_overhead,
        load_baseline_duration=args.load_baseline
    )


if __name__ == "__main__":
    main()
