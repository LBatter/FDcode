/*
 * L1 Prime+Probe Attack - Continuous Mode
 * Based on Mastik demo code
 * Runs continuously until Ctrl+C
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <signal.h>

#include <mastik/util.h>
#include <mastik/l1.h>

#define SAMPLES 1000

static volatile int running = 1;

void sigint_handler(int sig) {
    running = 0;
    printf("\nStopping...\n");
}

int main(int ac, char **av) {
    signal(SIGINT, sigint_handler);

    printf("L1 Prime+Probe Attack (Continuous Mode)\n");
    printf("Press Ctrl+C to stop\n\n");

    l1pp_t l1 = l1_prepare(NULL);
    if (l1 == NULL) {
        fprintf(stderr, "Failed to prepare L1 probe\n");
        return 1;
    }

    int nsets = l1_getmonitoredset(l1, NULL, 0);
    printf("L1 cache: Monitoring %d sets (total %d sets)\n\n", nsets, L1_SETS);

    uint16_t *res = calloc(SAMPLES * nsets, sizeof(uint16_t));
    if (res == NULL) {
        fprintf(stderr, "Failed to allocate memory\n");
        l1_release(l1);
        return 1;
    }

    // Touch pages
    for (int i = 0; i < SAMPLES * nsets; i += 4096/sizeof(uint16_t))
        res[i] = 1;

    uint64_t round = 0;
    while (running) {
        l1_repeatedprobe(l1, SAMPLES, res, 0);
        round++;

        if (round % 100 == 0) {
            printf("\r[Round %lu] Probing %d sets x %d samples    ",
                   round, nsets, SAMPLES);
            fflush(stdout);
        }
    }

    printf("\nTotal rounds: %lu\n", round);

    free(res);
    l1_release(l1);

    return 0;
}
