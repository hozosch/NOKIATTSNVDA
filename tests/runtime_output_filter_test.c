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
static int16_t output_previous, output_final;
static int output_have_previous;
static int32_t output_max_delta;

static void pcm(void *user, const int16_t *samples, uint32_t count,
                uint32_t rate) {
    uint32_t i;
    (void)user;
    assert(rate == 16000u);
    for (i = 0; i < count; ++i) {
        int32_t delta;
        if (output_have_previous) {
            delta = (int32_t)samples[i] - output_previous;
            if (delta < 0) delta = -delta;
            if (delta > output_max_delta) output_max_delta = delta;
        }
        output_previous = output_final = samples[i];
        output_have_previous = 1;
    }
    output_samples += count;
}

static void reset_runtime(NokiaRuntime *r, NokiaRuntimeCallbacks *callbacks,
                          int seams) {
    memset(r, 0, sizeof(*r));
    r->callbacks = callbacks;
    r->rate_factor = 1.0;
    r->seam_enabled = seams ? 1u : 0u;
    output_samples = 0;
    output_previous = output_final = 0;
    output_have_previous = 0;
    output_max_delta = 0;
}

static void put_i16(uint8_t *base, size_t offset, const int16_t *values,
                    size_t count) {
    memcpy(base + offset, values, count * sizeof(*values));
}

int main(void) {
    NokiaRuntime runtime;
    NokiaRuntimeCallbacks callbacks = {pcm, NULL, NULL};
    NokiaRuntime *snapshot_runtime;
    uint8_t minimal_snapshot[8u + SNAP_WORDS * 4u] = {0};
    const uint8_t minimal_rom[1] = {0};
    int16_t first[1100], second[1300];
    int16_t phones[3] = {2, 19, 0};
    int16_t durations[3] = {100, 201, 66};
    int16_t pitch[3] = {1000, 1100, 1200};
    /* Nokia can place two final control points a few units out of order. */
    int16_t pitch_time[3] = {0, 101, 93};
    int16_t amplitude[2] = {100, 120};
    int16_t amplitude_time[2] = {0, 151};
    int16_t wrapped[70] = {-26985, 32730, 32343, 32732, 32485, -29144};
    int16_t abrupt[128];
    uint8_t *object;
    size_t i;

    memcpy(minimal_snapshot, "NK5500S1", 8u);
    wr32(minimal_snapshot + 8u, 1u);
    snapshot_runtime = nokia_runtime_create_5500_snapshot(
        minimal_rom, sizeof(minimal_rom),
        minimal_snapshot, sizeof(minimal_snapshot));
    assert(snapshot_runtime);
    assert(snapshot_runtime->rom_base == ROM_BASE_5500);
    assert(!nokia_runtime_create_5320_snapshot(
        minimal_rom, sizeof(minimal_rom),
        minimal_snapshot, sizeof(minimal_snapshot)));
    nokia_runtime_destroy(snapshot_runtime);

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
    assert(finish_pcm_output(&runtime));
    assert(output_samples == 432u);
    assert(runtime.seam_trimmed_samples == 1968u);
    free(runtime.seam_quiet);
    free(runtime.pcm_pending);

    for (i = 6u; i < 70u; ++i) wrapped[i] = 0;

    reset_runtime(&runtime, &callbacks, 0);
    runtime.rate_factor = 1.4339552480158273; /* NVDA rate 63 */
    assert(!high_rate_pcm_fix_enabled(&runtime));
    assert(seam_feed(&runtime, wrapped, 70u));
    assert(output_samples == 70u);
    assert(output_max_delta > 60000);
    assert(runtime.pcm_wrap_repairs == 0u);
    assert(finish_pcm_output(&runtime));

    reset_runtime(&runtime, &callbacks, 0);
    runtime.rate_factor = 1.4742692172911012; /* NVDA rate 64 */
    assert(high_rate_pcm_fix_enabled(&runtime));
    assert(seam_feed(&runtime, wrapped, 70u));
    assert(output_samples == 6u);
    assert(runtime.pcm_wrap_repairs == 2u);
    assert(output_max_delta < 10000);
    assert(finish_pcm_output(&runtime));
    assert(output_samples == 70u);
    assert(output_final == 0);
    free(runtime.pcm_pending);

    for (i = 0; i < 128u; ++i) abrupt[i] = 10000;
    reset_runtime(&runtime, &callbacks, 0);
    runtime.rate_factor = 1.4742692172911012; /* NVDA rate 64 */
    assert(seam_feed(&runtime, abrupt, 128u));
    assert(output_samples == 64u);
    assert(finish_pcm_output(&runtime));
    assert(output_samples == 128u);
    assert(output_final == 0);
    free(runtime.pcm_pending);

    reset_runtime(&runtime, &callbacks, 0);
    runtime.pool = (uint8_t *)calloc(1, 0x400u);
    assert(runtime.pool);
    runtime.pool_next = POOL_BASE + 0x400u;
    runtime.rate_factor = 2.0;
    assert(add_block(&runtime, POOL_BASE + 0x100u, 0x30u, 1));
    assert(add_block(&runtime, POOL_BASE + 0x200u, 0x20u, 1));
    assert(add_block(&runtime, POOL_BASE + 0x220u, 0x20u, 1));
    assert(add_block(&runtime, POOL_BASE + 0x240u, 0x20u, 1));
    assert(add_block(&runtime, POOL_BASE + 0x260u, 0x20u, 1));
    assert(add_block(&runtime, POOL_BASE + 0x280u, 0x20u, 1));
    assert(add_block(&runtime, POOL_BASE + 0x2a0u, 0x20u, 1));
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
    /* The final zero-phone duration is the resonator drain and stays intact. */
    assert(((int16_t *)(runtime.pool + 0x220u))[2] == 66);
    assert(((int16_t *)(runtime.pool + 0x260u))[1] == 51);
    assert(((int16_t *)(runtime.pool + 0x260u))[2] == 47);
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
        assert(((int16_t *)(runtime.pool + 0x240u))[4] == 1140);
        assert(((int16_t *)(runtime.pool + 0x240u))[5] == 1140);

        /* The neutral continuation floor also catches a cadence which starts
           more than 1.2 seconds before the artificial text boundary. */
        {
            int16_t long_pitch[8] = {
                1140, 1320, 1140, 1320, 880, 880, 880, 880
            };
            int16_t long_time[8] = {
                0, 300, 600, 1200, 1500, 1800, 2200, 2600
            };
            put_i16(runtime.pool, 0x240u, long_pitch, 8u);
            put_i16(runtime.pool, 0x260u, long_time, 8u);
            assert(continue_prosody_pitch(
                &runtime, POOL_BASE + 0x240u, POOL_BASE + 0x260u, 8u
            ));
            assert(((int16_t *)(runtime.pool + 0x240u))[4] == 1140);
            assert(((int16_t *)(runtime.pool + 0x240u))[7] == 1140);
        }

        {
            int16_t short_phones[3] = {2, 2, 0};
            int16_t short_durations[3] = {10, 21, 66};
            put_i16(runtime.pool, 0x200u, short_phones, 3u);
            put_i16(runtime.pool, 0x220u, short_durations, 3u);
            assert(scale_phone_durations(
                &runtime, POOL_BASE + 0x200u, POOL_BASE + 0x220u,
                3u, 2.0
            ));
            assert(((int16_t *)(runtime.pool + 0x220u))[0] == 8);
            assert(((int16_t *)(runtime.pool + 0x220u))[1] == 11);
            assert(((int16_t *)(runtime.pool + 0x220u))[2] == 66);
        }
    }
#endif
    free(runtime.pool);
    free(runtime.blocks);

    reset_runtime(&runtime, &callbacks, 0);
    runtime.pool = (uint8_t *)calloc(1, 0x100u);
    assert(runtime.pool);
    runtime.pool_next = POOL_BASE + 0x100u;
    runtime.rate_factor = 4.0;
    /* Optional speed/intonation post-processing must never reject an
       otherwise valid silent or unfamiliar frontend result as -3007. */
    assert(apply_prosody_rate(&runtime, 1));
    free(runtime.pool);
    puts("runtime output filters passed");
    return 0;
}
