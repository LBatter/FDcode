#!/usr/bin/env python3
"""
collect_all.py - HPC数据采集脚本

数据结构：
  data/light_load/      - 轻负载数据（只有受害程序和攻击程序）
    - benign.csv        - 良性数据
    - prefetch.csv      - Prefetch攻击
    - primescope.csv    - Prime+Scope攻击
  data/heavy_load/      - 满负载数据（后台运行native）
    - benign.csv
    - prefetch.csv
    - primescope.csv
  data/traditional/     - 传统攻击数据
    - benign.csv        - 良性数据
    - fr.csv            - Flush+Reload
    - ff.csv            - Flush+Flush
    - pp.csv            - Prime+Probe

用法:
  python3 collect_all.py                    # 采集所有数据
  python3 collect_all.py --light            # 只采集轻负载
  python3 collect_all.py --heavy            # 只采集满负载
  python3 collect_all.py --traditional      # 只采集传统攻击
  python3 collect_all.py --force            # 强制重新采集
"""

import os
import sys
import time
import signal
import subprocess
from pathlib import Path
from datetime import datetime

# ========== 配置 ==========
BASE_DIR = Path(__file__).resolve().parent.parent
COLLECT_DIR = BASE_DIR / "collect"
DATA_DIR = BASE_DIR / "data"

# 攻击程序路径
PREFETCH_DIR = BASE_DIR / "attack/AdversarialPrefetch-main/covert_channels/build/bin"
PRIMESCOPE_DIR = BASE_DIR / "attack/PRIME-SCOPE-main/primescope_demo"
MASTIK_DIR = BASE_DIR / "attack/Mastik-main/demo"
PARSEC_DIR = BASE_DIR / "attack/parsec-workspace/parsec-3.0"

# 采集参数
DURATION = 60        # 采集时长（秒）
INTERVAL = 100       # 采样间隔（微秒）
STABILIZE = 5        # 系统稳定等待时间（秒）
ATTACK_WARMUP = 3    # 攻击启动后等待时间（秒）
MIN_LINES = 500000   # 有效文件最小行数（约50秒数据）

# 全局进程列表
processes = []

# 模式标志
force_mode = False


# ========== 工具函数 ==========
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    RED = '\033[91m'
    END = '\033[0m'


def log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{Colors.GREEN}[{timestamp}]{Colors.END} {msg}")


def warn(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{Colors.YELLOW}[{timestamp}]{Colors.END} {msg}")


def error(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{Colors.RED}[{timestamp}]{Colors.END} {msg}")


def section(title):
    print(f"\n{Colors.CYAN}========== {title} =========={Colors.END}")


def is_complete(filepath):
    """检查文件是否已完成采集"""
    if force_mode:
        return False
    if not filepath.exists():
        return False
    try:
        lines = sum(1 for _ in open(filepath))
        if lines >= MIN_LINES:
            log(f"Skipping {filepath.name} (already complete: {lines} lines)")
            return True
    except:
        pass
    return False


def cleanup():
    """清理所有相关进程"""
    global processes

    for p in processes:
        try:
            p.kill()
            p.wait(timeout=3)
        except:
            pass
    processes = []

    kill_patterns = [
        "cache_monitor", "sender", "receiver_pre",
        "app --primescope", "FR-openssl", "FF-openssl",
        "PP-L3", "streamcluster"
    ]
    for pattern in kill_patterns:
        subprocess.run(["pkill", "-9", "-f", pattern], capture_output=True)
    time.sleep(1)


def wait_stable():
    """等待系统稳定"""
    log(f"Waiting {STABILIZE}s for system to stabilize...")
    time.sleep(STABILIZE)


def wait_ready(process, timeout=30):
    """等待进程输出READY信号"""
    import select

    log(f"Waiting for READY signal (timeout: {timeout}s)...")
    start = time.time()
    buffer = ""

    while time.time() - start < timeout:
        if process.poll() is not None:
            warn("Process terminated unexpectedly")
            return False

        try:
            ready, _, _ = select.select([process.stderr], [], [], 0.1)
            if ready:
                chunk = os.read(process.stderr.fileno(), 4096)
                if chunk:
                    buffer += chunk.decode(errors='ignore')
                    if "READY" in buffer:
                        log("READY signal received")
                        return True
        except:
            pass

    warn("Timeout waiting for READY signal")
    return False


def start_process(cmd, cwd=None, capture_stderr=False):
    """启动进程并加入跟踪列表"""
    global processes

    stderr = subprocess.PIPE if capture_stderr else subprocess.DEVNULL
    p = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=stderr,
        preexec_fn=os.setsid
    )
    processes.append(p)
    return p


def start_background_load():
    """启动背景负载（streamcluster循环）"""
    log("Starting background load (streamcluster native)...")

    cmd = f"""
    cd {PARSEC_DIR} && source env.sh && \
    while true; do
        parsecmgmt -a run -p streamcluster -i native -n 4 -c gcc-pthreads
        sleep 1
    done
    """
    p = subprocess.Popen(
        ["bash", "-c", cmd],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid
    )
    processes.append(p)

    time.sleep(10)
    log("Background load started")
    return p


def stop_background_load():
    """停止背景负载"""
    log("Stopping background load...")
    subprocess.run(["pkill", "-9", "-f", "streamcluster"], capture_output=True)
    time.sleep(2)


def collect(output_file, duration):
    """采集HPC数据"""
    log(f"Collecting to {output_file} for {duration}s...")

    monitor = COLLECT_DIR / "cache_monitor"
    result = subprocess.run(
        [str(monitor), "-o", str(output_file), "-d", str(duration),
         "-i", str(INTERVAL), "-q"],
        capture_output=True
    )

    if result.returncode != 0:
        error(f"Monitor failed: {result.stderr.decode()}")
        return 0

    lines = sum(1 for _ in open(output_file))
    log(f"Collected {lines} lines")
    return lines


def collect_with_monitor(output_file, duration):
    """启动monitor后台采集，返回monitor进程"""
    log(f"Starting monitor for {output_file}...")

    monitor = start_process(
        [str(COLLECT_DIR / "cache_monitor"),
         "-o", str(output_file),
         "-i", str(INTERVAL), "-q"]
    )
    return monitor


def run_parsec(program, iterations=1, config=None):
    """运行PARSEC程序"""
    cmd = f"cd {PARSEC_DIR} && source env.sh && "

    if config:
        cmd += f"parsecmgmt -a run -p {program} -i native -n 4 -c {config}"
    else:
        cmd += f"parsecmgmt -a run -p {program} -i native -n 4"

    for i in range(iterations):
        log(f"  Running {program} iteration {i+1}/{iterations}...")
        subprocess.run(["bash", "-c", cmd],
                      stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL)


def append_to_file(src_file, dst_file):
    """将src_file的内容追加到dst_file（跳过header如果dst已存在）"""
    if not src_file.exists():
        return

    with open(src_file, 'r') as src:
        lines = src.readlines()

    if dst_file.exists():
        # 跳过header
        lines = lines[1:]

    with open(dst_file, 'a') as dst:
        dst.writelines(lines)


# ========== 轻负载采集 ==========
def collect_light_load():
    """采集轻负载数据（只有受害程序和攻击程序）"""
    section("Light Load Data Collection")
    output_dir = DATA_DIR / "light_load"
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Benign ---
    output_file = output_dir / "benign.csv"
    if not is_complete(output_file):
        log("--- Benign (Light Load) ---")
        cleanup()
        wait_stable()

        # 采集空闲状态
        temp_file = output_dir / "temp_benign.csv"
        collect(temp_file, DURATION)

        # 移动到目标文件
        if temp_file.exists():
            temp_file.rename(output_file)

    # --- Prefetch Attack ---
    output_file = output_dir / "prefetch.csv"
    if not is_complete(output_file):
        log("--- Prefetch Attack (Light Load) ---")

        # 采集多种Prefetch攻击变体
        temp_files = []

        # Prefetch+Prefetch
        log("  [1/2] Prefetch+Prefetch...")
        cleanup()
        wait_stable()

        sender = start_process([str(PREFETCH_DIR / "sender")], cwd=PREFETCH_DIR)
        time.sleep(1)
        receiver = start_process(
            [str(PREFETCH_DIR / "receiver_pre_pre")],
            cwd=PREFETCH_DIR, capture_stderr=True
        )
        wait_ready(receiver, timeout=30)
        time.sleep(ATTACK_WARMUP)

        temp1 = output_dir / "temp_pp.csv"
        collect(temp1, DURATION)
        temp_files.append(temp1)
        cleanup()

        # Prefetch+Reload
        log("  [2/2] Prefetch+Reload...")
        cleanup()
        wait_stable()

        sender = start_process([str(PREFETCH_DIR / "sender")], cwd=PREFETCH_DIR)
        time.sleep(1)
        receiver = start_process(
            [str(PREFETCH_DIR / "receiver_pre_relo")],
            cwd=PREFETCH_DIR, capture_stderr=True
        )
        wait_ready(receiver, timeout=30)
        time.sleep(ATTACK_WARMUP)

        temp2 = output_dir / "temp_pr.csv"
        collect(temp2, DURATION)
        temp_files.append(temp2)
        cleanup()

        # 合并文件
        log("  Merging prefetch data...")
        if temp_files[0].exists():
            temp_files[0].rename(output_file)
        for tf in temp_files[1:]:
            if tf.exists():
                append_to_file(tf, output_file)
                tf.unlink()

    # --- Prime+Scope Attack ---
    output_file = output_dir / "primescope.csv"
    if not is_complete(output_file):
        log("--- Prime+Scope Attack (Light Load) ---")
        cleanup()
        wait_stable()

        app = start_process(
            [str(PRIMESCOPE_DIR / "app"), "--primescope"],
            cwd=PRIMESCOPE_DIR
        )
        log("Waiting 15s for eviction set construction...")
        time.sleep(15)

        collect(output_file, DURATION)
        cleanup()


# ========== 满负载采集 ==========
def collect_heavy_load():
    """采集满负载数据（后台运行native）"""
    section("Heavy Load Data Collection")
    output_dir = DATA_DIR / "heavy_load"
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Benign ---
    output_file = output_dir / "benign.csv"
    if not is_complete(output_file):
        log("--- Benign (Heavy Load) ---")
        cleanup()
        start_background_load()
        wait_stable()

        collect(output_file, DURATION)
        cleanup()

    # --- Prefetch Attack ---
    output_file = output_dir / "prefetch.csv"
    if not is_complete(output_file):
        log("--- Prefetch Attack (Heavy Load) ---")

        temp_files = []

        # Prefetch+Prefetch with load
        log("  [1/2] Prefetch+Prefetch with load...")
        cleanup()
        start_background_load()
        wait_stable()

        sender = start_process([str(PREFETCH_DIR / "sender")], cwd=PREFETCH_DIR)
        time.sleep(1)
        receiver = start_process(
            [str(PREFETCH_DIR / "receiver_pre_pre")],
            cwd=PREFETCH_DIR, capture_stderr=True
        )
        wait_ready(receiver, timeout=30)
        time.sleep(ATTACK_WARMUP)

        temp1 = output_dir / "temp_pp.csv"
        collect(temp1, DURATION)
        temp_files.append(temp1)
        cleanup()

        # Prefetch+Reload with load
        log("  [2/2] Prefetch+Reload with load...")
        cleanup()
        start_background_load()
        wait_stable()

        sender = start_process([str(PREFETCH_DIR / "sender")], cwd=PREFETCH_DIR)
        time.sleep(1)
        receiver = start_process(
            [str(PREFETCH_DIR / "receiver_pre_relo")],
            cwd=PREFETCH_DIR, capture_stderr=True
        )
        wait_ready(receiver, timeout=30)
        time.sleep(ATTACK_WARMUP)

        temp2 = output_dir / "temp_pr.csv"
        collect(temp2, DURATION)
        temp_files.append(temp2)
        cleanup()

        # 合并文件
        log("  Merging prefetch data...")
        if temp_files[0].exists():
            temp_files[0].rename(output_file)
        for tf in temp_files[1:]:
            if tf.exists():
                append_to_file(tf, output_file)
                tf.unlink()

    # --- Prime+Scope Attack ---
    output_file = output_dir / "primescope.csv"
    if not is_complete(output_file):
        log("--- Prime+Scope Attack (Heavy Load) ---")
        cleanup()
        start_background_load()
        wait_stable()

        app = start_process(
            [str(PRIMESCOPE_DIR / "app"), "--primescope"],
            cwd=PRIMESCOPE_DIR
        )
        log("Waiting 15s for eviction set construction...")
        time.sleep(15)

        collect(output_file, DURATION)
        cleanup()


# ========== 传统攻击采集 ==========
def collect_traditional():
    """采集传统攻击数据"""
    section("Traditional Attack Data Collection")
    output_dir = DATA_DIR / "traditional"
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Benign ---
    output_file = output_dir / "benign.csv"
    if not is_complete(output_file):
        log("--- Benign (Traditional) ---")
        cleanup()
        wait_stable()
        collect(output_file, DURATION)

    # --- Flush+Reload ---
    output_file = output_dir / "fr.csv"
    if not is_complete(output_file):
        log("--- Flush+Reload ---")
        cleanup()
        wait_stable()

        attack = start_process(
            [str(MASTIK_DIR / "FR-openssl-test")],
            cwd=MASTIK_DIR
        )
        time.sleep(ATTACK_WARMUP)

        collect(output_file, DURATION)
        cleanup()

    # --- Flush+Flush ---
    output_file = output_dir / "ff.csv"
    if not is_complete(output_file):
        log("--- Flush+Flush ---")
        cleanup()
        wait_stable()

        attack = start_process(
            [str(MASTIK_DIR / "FF-openssl-test")],
            cwd=MASTIK_DIR
        )
        time.sleep(ATTACK_WARMUP)

        collect(output_file, DURATION)
        cleanup()

    # --- Prime+Probe L3 ---
    output_file = output_dir / "pp.csv"
    if not is_complete(output_file):
        log("--- Prime+Probe L3 ---")
        cleanup()
        wait_stable()

        attack = start_process(
            [str(MASTIK_DIR / "PP-L3-test")],
            cwd=MASTIK_DIR,
            capture_stderr=True
        )
        wait_ready(attack, timeout=120)
        time.sleep(ATTACK_WARMUP)

        collect(output_file, DURATION)
        cleanup()


# ========== 摘要打印 ==========
def print_summary():
    """打印采集结果摘要"""
    print("\n" + "=" * 60)
    print("Data Collection Summary")
    print("=" * 60)

    categories = [
        ("Light Load", DATA_DIR / "light_load"),
        ("Heavy Load", DATA_DIR / "heavy_load"),
        ("Traditional Attacks", DATA_DIR / "traditional"),
    ]

    total_lines = 0

    for name, path in categories:
        print(f"\n{name}:")
        if path.exists():
            for f in sorted(path.glob("*.csv")):
                lines = sum(1 for _ in open(f))
                size = f.stat().st_size / 1024 / 1024
                print(f"  {f.name}: {lines} lines ({size:.1f} MB)")
                total_lines += lines
        else:
            print("  (no files)")

    print(f"\nTotal: {total_lines} lines")


# ========== 主函数 ==========
def main():
    global force_mode

    # 解析命令行参数
    collect_light = True
    collect_heavy = True
    collect_trad = True

    if "--light" in sys.argv:
        collect_light = True
        collect_heavy = False
        collect_trad = False
    elif "--heavy" in sys.argv:
        collect_light = False
        collect_heavy = True
        collect_trad = False
    elif "--traditional" in sys.argv:
        collect_light = False
        collect_heavy = False
        collect_trad = True

    if "--force" in sys.argv or "-f" in sys.argv:
        force_mode = True
        log("Force mode: will re-collect all data")
    else:
        log("Resume mode: will skip completed files")

    # 信号处理
    def signal_handler(sig, frame):
        print("\nInterrupted, cleaning up...")
        cleanup()
        sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 检查cache_monitor
    monitor = COLLECT_DIR / "cache_monitor"
    if not monitor.exists():
        error(f"cache_monitor not found at {monitor}")
        sys.exit(1)

    start_time = time.time()

    try:
        # 创建数据目录
        (DATA_DIR / "light_load").mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "heavy_load").mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "traditional").mkdir(parents=True, exist_ok=True)

        # 采集数据
        if collect_light:
            collect_light_load()

        if collect_heavy:
            collect_heavy_load()

        if collect_trad:
            collect_traditional()

    finally:
        cleanup()

    elapsed = time.time() - start_time
    section("Collection Complete")
    log(f"Total time: {int(elapsed // 60)}m {int(elapsed % 60)}s")

    print_summary()


if __name__ == "__main__":
    main()
