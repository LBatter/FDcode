/*
 * cache_monitor.c - HPC事件采集程序
 *
 * 功能：采集5个HPC事件用于缓存侧信道攻击检测
 * 事件：LLC-load-misses, L1-dcache-load-misses, branch-misses,
 *       l1d.replacement, sw_prefetch_access.prefetchw
 *
 * 用法：
 *   ./cache_monitor -o output.csv -d 60 -i 100
 *   ./cache_monitor -o output.csv              # 默认无限运行，100us间隔
 *   ./cache_monitor                            # 输出到stdout
 *
 * 参数：
 *   -o <file>   输出文件路径（默认stdout）
 *   -d <sec>    采集时长秒数（默认0=无限）
 *   -i <us>     采样间隔微秒（默认100）
 *   -q          安静模式，不输出到stderr
 *   -h          显示帮助
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/syscall.h>
#include <linux/perf_event.h>
#include <sys/ioctl.h>
#include <errno.h>
#include <time.h>
#include <signal.h>
#include <getopt.h>

#define MAX_CPUS 128
#define NUM_EVENTS 5

// 事件名称
static const char* event_names[NUM_EVENTS] = {
    "LLC-load-misses",
    "L1-dcache-load-misses",
    "branch-misses",
    "l1d.replacement",
    "sw_prefetch_access.prefetchw"
};

// 事件配置
struct event_config {
    __u32 type;
    __u64 config;
};

static struct event_config events[NUM_EVENTS] = {
    // LLC-load-misses
    {PERF_TYPE_HW_CACHE,
     (PERF_COUNT_HW_CACHE_LL) |
     (PERF_COUNT_HW_CACHE_OP_READ << 8) |
     (PERF_COUNT_HW_CACHE_RESULT_MISS << 16)},
    // L1-dcache-load-misses
    {PERF_TYPE_HW_CACHE,
     (PERF_COUNT_HW_CACHE_L1D) |
     (PERF_COUNT_HW_CACHE_OP_READ << 8) |
     (PERF_COUNT_HW_CACHE_RESULT_MISS << 16)},
    // branch-misses
    {PERF_TYPE_HARDWARE, PERF_COUNT_HW_BRANCH_MISSES},
    // l1d.replacement (Intel RAW event 0x51d1)
    {PERF_TYPE_RAW, 0x51d1},
    // sw_prefetch_access.prefetchw (Intel RAW event 0x32d0)
    {PERF_TYPE_RAW, 0x32d0}
};

// 全局变量
static int num_cpus;
static int event_fds[MAX_CPUS][NUM_EVENTS];
static long long prev_counts[MAX_CPUS][NUM_EVENTS];
static long long curr_counts[MAX_CPUS][NUM_EVENTS];
static volatile int running = 1;
static int quiet_mode = 0;

// 信号处理
static void signal_handler(int sig) {
    (void)sig;
    running = 0;
}

// perf_event_open系统调用
static long perf_event_open(struct perf_event_attr *attr, pid_t pid,
                            int cpu, int group_fd, unsigned long flags) {
    return syscall(__NR_perf_event_open, attr, pid, cpu, group_fd, flags);
}

// 初始化perf事件
static int init_perf_events(void) {
    struct perf_event_attr pe;
    int success_count = 0;

    for (int cpu = 0; cpu < num_cpus; cpu++) {
        for (int ev = 0; ev < NUM_EVENTS; ev++) {
            memset(&pe, 0, sizeof(pe));
            pe.size = sizeof(pe);
            pe.type = events[ev].type;
            pe.config = events[ev].config;
            pe.disabled = 1;
            pe.exclude_kernel = 0;
            pe.exclude_hv = 1;

            event_fds[cpu][ev] = perf_event_open(&pe, -1, cpu, -1, 0);
            if (event_fds[cpu][ev] == -1) {
                if (!quiet_mode && cpu == 0) {
                    fprintf(stderr, "Warning: Event %s not available: %s\n",
                            event_names[ev], strerror(errno));
                }
            } else {
                success_count++;
            }
        }
    }

    if (success_count == 0) {
        fprintf(stderr, "Error: No events could be opened\n");
        return -1;
    }

    return 0;
}

// 启动监控
static void start_monitoring(void) {
    for (int cpu = 0; cpu < num_cpus; cpu++) {
        for (int ev = 0; ev < NUM_EVENTS; ev++) {
            if (event_fds[cpu][ev] != -1) {
                ioctl(event_fds[cpu][ev], PERF_EVENT_IOC_RESET, 0);
                ioctl(event_fds[cpu][ev], PERF_EVENT_IOC_ENABLE, 0);
            }
        }
    }
}

// 停止监控
static void stop_monitoring(void) {
    for (int cpu = 0; cpu < num_cpus; cpu++) {
        for (int ev = 0; ev < NUM_EVENTS; ev++) {
            if (event_fds[cpu][ev] != -1) {
                ioctl(event_fds[cpu][ev], PERF_EVENT_IOC_DISABLE, 0);
            }
        }
    }
}

// 读取事件计数
static void read_counts(void) {
    long long value;

    for (int cpu = 0; cpu < num_cpus; cpu++) {
        for (int ev = 0; ev < NUM_EVENTS; ev++) {
            if (event_fds[cpu][ev] != -1) {
                if (read(event_fds[cpu][ev], &value, sizeof(value)) == sizeof(value)) {
                    curr_counts[cpu][ev] = value;
                } else {
                    curr_counts[cpu][ev] = 0;
                }
            } else {
                curr_counts[cpu][ev] = 0;
            }
        }
    }
}

// 输出增量数据
static void output_deltas(FILE *out, struct timespec *ts) {
    static int first = 1;
    long long deltas[NUM_EVENTS] = {0};

    if (first) {
        first = 0;
        memcpy(prev_counts, curr_counts, sizeof(curr_counts));
        return;
    }

    // 计算所有CPU的总增量
    for (int cpu = 0; cpu < num_cpus; cpu++) {
        for (int ev = 0; ev < NUM_EVENTS; ev++) {
            long long delta = curr_counts[cpu][ev] - prev_counts[cpu][ev];
            if (delta > 0) {
                deltas[ev] += delta;
            }
        }
    }

    // 输出CSV行：时间戳,事件1,事件2,事件3,事件4,事件5
    fprintf(out, "%.6f", ts->tv_sec + ts->tv_nsec / 1e9);
    for (int ev = 0; ev < NUM_EVENTS; ev++) {
        fprintf(out, ",%lld", deltas[ev]);
    }
    fprintf(out, "\n");
    fflush(out);

    memcpy(prev_counts, curr_counts, sizeof(curr_counts));
}

// 清理资源
static void cleanup(void) {
    stop_monitoring();
    for (int cpu = 0; cpu < num_cpus; cpu++) {
        for (int ev = 0; ev < NUM_EVENTS; ev++) {
            if (event_fds[cpu][ev] != -1) {
                close(event_fds[cpu][ev]);
            }
        }
    }
}

// 显示帮助
static void show_help(const char *prog) {
    printf("Usage: %s [options]\n\n", prog);
    printf("Options:\n");
    printf("  -o <file>   Output file (default: stdout)\n");
    printf("  -d <sec>    Duration in seconds (default: 0 = infinite)\n");
    printf("  -i <us>     Sample interval in microseconds (default: 100)\n");
    printf("  -q          Quiet mode (no stderr output)\n");
    printf("  -h          Show this help\n\n");
    printf("Events monitored:\n");
    for (int i = 0; i < NUM_EVENTS; i++) {
        printf("  %d. %s\n", i+1, event_names[i]);
    }
}

int main(int argc, char *argv[]) {
    char *output_file = NULL;
    int duration = 0;  // 0 = infinite
    int interval_us = 100;
    FILE *out = stdout;
    int opt;

    // 解析参数
    while ((opt = getopt(argc, argv, "o:d:i:qh")) != -1) {
        switch (opt) {
            case 'o':
                output_file = optarg;
                break;
            case 'd':
                duration = atoi(optarg);
                break;
            case 'i':
                interval_us = atoi(optarg);
                if (interval_us < 10) interval_us = 10;
                break;
            case 'q':
                quiet_mode = 1;
                break;
            case 'h':
                show_help(argv[0]);
                return 0;
            default:
                show_help(argv[0]);
                return 1;
        }
    }

    // 获取CPU数量
    num_cpus = sysconf(_SC_NPROCESSORS_ONLN);
    if (num_cpus > MAX_CPUS) num_cpus = MAX_CPUS;

    // 打开输出文件
    if (output_file) {
        out = fopen(output_file, "w");
        if (!out) {
            fprintf(stderr, "Error: Cannot open %s: %s\n", output_file, strerror(errno));
            return 1;
        }
    }

    // 初始化事件fd为-1
    memset(event_fds, -1, sizeof(event_fds));

    // 设置信号处理
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    // 初始化perf事件
    if (init_perf_events() != 0) {
        if (out != stdout) fclose(out);
        return 1;
    }

    // 写CSV头
    fprintf(out, "timestamp");
    for (int i = 0; i < NUM_EVENTS; i++) {
        fprintf(out, ",%s", event_names[i]);
    }
    fprintf(out, "\n");
    fflush(out);

    if (!quiet_mode) {
        fprintf(stderr, "Starting HPC monitoring (CPUs: %d, interval: %dus)\n",
                num_cpus, interval_us);
        if (duration > 0) {
            fprintf(stderr, "Duration: %d seconds\n", duration);
        } else {
            fprintf(stderr, "Duration: infinite (Ctrl+C to stop)\n");
        }
        fprintf(stderr, "READY\n");
    }

    // 启动监控
    start_monitoring();

    struct timespec start_ts, curr_ts, sleep_ts;
    clock_gettime(CLOCK_REALTIME, &start_ts);

    sleep_ts.tv_sec = 0;
    sleep_ts.tv_nsec = interval_us * 1000;

    // 主循环
    while (running) {
        clock_gettime(CLOCK_REALTIME, &curr_ts);

        // 检查时长
        if (duration > 0 && (curr_ts.tv_sec - start_ts.tv_sec) >= duration) {
            break;
        }

        read_counts();
        output_deltas(out, &curr_ts);
        nanosleep(&sleep_ts, NULL);
    }

    cleanup();

    if (out != stdout) {
        fclose(out);
    }

    if (!quiet_mode) {
        fprintf(stderr, "Monitoring stopped\n");
    }

    return 0;
}
