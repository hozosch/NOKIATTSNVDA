#include <assert.h>
#include <math.h>
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
                          double factor, int seams) {
    memset(r, 0, sizeof(*r));
    r->callbacks = callbacks;
    r->rate_factor = factor;
    r->seam_enabled = seams ? 1u : 0u;
    if (factor != 1.0) {
        r->rate = rate_create(factor);
        assert(r->rate);
    }
    output_samples = 0;
}

int main(void) {
    NokiaRuntime runtime;
    NokiaRuntimeCallbacks callbacks = {pcm, NULL, NULL};
    int16_t first[1100], second[1300], rate_input[4800];
    size_t i;

    for (i = 0; i < 100; ++i) first[i] = 1000;
    memset(first + 100, 0, 1000 * sizeof(*first));
    memset(second, 0, 1000 * sizeof(*second));
    for (i = 1000; i < 1100; ++i) second[i] = -1000;
    memset(second + 1100, 0, 200 * sizeof(*second));

    reset_runtime(&runtime, &callbacks, 1.0, 1);
    assert(seam_feed(&runtime, first, 1100));
    assert(seam_finish_chunk(&runtime, 0));
    assert(seam_feed(&runtime, second, 1300));
    assert(seam_finish_chunk(&runtime, 1));
    assert(output_samples == 464u);
    assert(runtime.seam_trimmed_samples == 1936u);
    free(runtime.seam_quiet);

    for (i = 0; i < 4800; ++i)
        rate_input[i] = (int16_t)(12000.0 * sin((double)i * 0.07));
    reset_runtime(&runtime, &callbacks, 2.0, 0);
    assert(emit_pcm(&runtime, rate_input, 4800, 0));
    assert(emit_pcm(&runtime, NULL, 0, 1));
    assert(output_samples < 4800u * 8u / 10u);
    rate_destroy(runtime.rate);
    free(runtime.rate_output);

    reset_runtime(&runtime, &callbacks, 0.5, 0);
    assert(emit_pcm(&runtime, rate_input, 4800, 0));
    assert(emit_pcm(&runtime, NULL, 0, 1));
    assert(output_samples > 4800u * 15u / 10u);
    rate_destroy(runtime.rate);
    free(runtime.rate_output);
    puts("runtime output filters passed");
    return 0;
}
