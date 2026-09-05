#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

#include "../native/nokia_runtime.c"

int nokia_klatt_generate_aot(int16_t *a, int32_t *b, uint8_t c[122],
                            uint8_t d[564], uint32_t e, const uint8_t *f,
                            uint32_t g, size_t h, uint32_t i[5]) {
    (void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;(void)h;(void)i;
    return 0;
}

int nokia_frontend_aot(uint8_t *a, uint8_t *b, uint8_t *c, uint8_t *d,
                       uint8_t *e, const uint8_t *f, uint32_t g, size_t h,
                       uint32_t i[17], uint32_t j,
                       const NokiaFrontendHost *k) {
    (void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;(void)h;(void)i;
    (void)j;(void)k;
    return 0;
}

static size_t output_samples;

static void pcm(void *user, const int16_t *samples, uint32_t count,
                uint32_t rate) {
    (void)user;(void)samples;
    assert(rate == 16000u);
    output_samples += count;
}

static void reset_runtime(NokiaRuntime *r, NokiaRuntimeCallbacks *callbacks,
                          int seams) {
    memset(r, 0, sizeof(*r));
    r->callbacks = callbacks;
    r->rate_factor = 1.0;
    r->seam_enabled = seams ? 1u : 0u;
    output_samples = 0;
}

static void put_i16(uint8_t *base, size_t offset, const int16_t *values,
                    size_t count) {
    memcpy(base + offset, values, count * sizeof(*values));
}

int main(void) {
    NokiaRuntime runtime;
    NokiaRuntimeCallbacks callbacks = {pcm, NULL, NULL};
    int16_t first[1100], second[1300];
    int16_t phones[3] = {1, 2, 3};
    int16_t durations[3] = {100, 201, 1};
    int16_t pitch[3] = {1000, 1100, 1200};
    int16_t pitch_time[3] = {0, 101, 200};
    int16_t amplitude[2] = {100, 120};
    int16_t amplitude_time[2] = {0, 151};
    uint8_t *object;
    size_t i;

    for (i = 0; i < 100; ++i) first[i] = 1000;
    memset(first + 100, 0, 1000 * sizeof(*first));
    memset(second, 0, 1000 * sizeof(*second));
    for (i = 1000; i < 1100; ++i) second[i] = -1000;
    memset(second + 1100, 0, 200 * sizeof(*second));

    reset_runtime(&runtime, &callbacks, 1);
    assert(seam_feed(&runtime, first, 1100));
    assert(seam_finish_chunk(&runtime, 0));
    assert(seam_feed(&runtime, second, 1300));
    assert(seam_finish_chunk(&runtime, 1));
    assert(output_samples == 464u);
    assert(runtime.seam_trimmed_samples == 1936u);
    free(runtime.seam_quiet);

    reset_runtime(&runtime, &callbacks, 0);
    runtime.pool = (uint8_t *)calloc(1, 0x400u);
    assert(runtime.pool);
    runtime.pool_next = POOL_BASE + 0x400u;
    runtime.rate_factor = 2.0;
    object = runtime.pool + 0x100u;
    memcpy(object, "\003\000\003\000\002\000", 6u);
    wr32(object + 0x08u, POOL_BASE + 0x200u);
    wr32(object + 0x0cu, POOL_BASE + 0x220u);
    wr32(object + 0x10u, POOL_BASE + 0x240u);
    wr32(object + 0x14u, POOL_BASE + 0x260u);
    wr32(object + 0x1cu, POOL_BASE + 0x280u);
    wr32(object + 0x20u, POOL_BASE + 0x2a0u);
    put_i16(runtime.pool, 0x200u, phones, 3u);
    put_i16(runtime.pool, 0x220u, durations, 3u);
    put_i16(runtime.pool, 0x240u, pitch, 3u);
    put_i16(runtime.pool, 0x260u, pitch_time, 3u);
    put_i16(runtime.pool, 0x280u, amplitude, 2u);
    put_i16(runtime.pool, 0x2a0u, amplitude_time, 2u);
    assert(apply_prosody_rate(&runtime, 0));
    assert(((int16_t *)(runtime.pool + 0x220u))[0] == 50);
    assert(((int16_t *)(runtime.pool + 0x220u))[1] == 101);
    assert(((int16_t *)(runtime.pool + 0x220u))[2] == 1);
    assert(((int16_t *)(runtime.pool + 0x260u))[1] == 51);
    assert(((int16_t *)(runtime.pool + 0x260u))[2] == 100);
    assert(((int16_t *)(runtime.pool + 0x2a0u))[1] == 76);
    /* F0 and amplitude values are deliberately not rate-scaled. */
    assert(((int16_t *)(runtime.pool + 0x240u))[1] == 1100);
    assert(((int16_t *)(runtime.pool + 0x280u))[1] == 120);
#if NOKIA_CONTINUE_PROSODY
    {
        int16_t continuation_pitch[6] = {1140, 1320, 1140, 1320, 880, 880};
        int16_t continuation_time[6] = {0, 100, 200, 300, 400, 500};
        put_i16(runtime.pool, 0x240u, continuation_pitch, 6u);
        put_i16(runtime.pool, 0x260u, continuation_time, 6u);
        assert(continue_prosody_pitch(
            &runtime, POOL_BASE + 0x240u, POOL_BASE + 0x260u, 6u
        ));
        assert(((int16_t *)(runtime.pool + 0x240u))[4] == 1230);
        assert(((int16_t *)(runtime.pool + 0x240u))[5] == 1140);
    }
#endif
    free(runtime.pool);
    puts("runtime output filters passed");
    return 0;
}
