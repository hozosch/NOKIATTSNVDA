#include "nokia_runtime.h"

#include <stdlib.h>
#include <string.h>

/*
 * This file is deliberately independent from nokia_klatt_bridge.c.  The old
 * bridge remains the verifier/migration path while this runtime becomes the
 * shipped path.  Do not add uc_* types or Unicorn callbacks here.
 */

struct NokiaRuntime {
    uint8_t *rom;
    size_t rom_size;
    char *resource_root;
    uint32_t language_id;
    uint32_t voice_id;
    double rate_factor;
    double pitch_factor;
    volatile long cancelled;
    int last_error;
    uint64_t frontend_ticks;
    uint64_t audio_ticks;

    /* Stable guest-address backing owned directly by this process. */
    uint8_t *heap;     /* guest 0x50000000, 1 MiB */
    uint8_t *vtable;   /* guest 0x51000000, 4 KiB */
    uint8_t *traps;    /* guest 0x52000000, 64 KiB */
    uint8_t *pool;     /* guest 0x53000000, 8 MiB */
    uint8_t *stack;    /* guest 0x60000000, 1 MiB */
    uint32_t regs[17];
};

static char *copy_string(const char *text) {
    size_t n;
    char *copy;
    if (!text) return NULL;
    n = strlen(text) + 1;
    copy = (char *)malloc(n);
    if (copy) memcpy(copy, text, n);
    return copy;
}

static void runtime_free_memory(NokiaRuntime *runtime) {
    if (!runtime) return;
    free(runtime->heap);
    free(runtime->vtable);
    free(runtime->traps);
    free(runtime->pool);
    free(runtime->stack);
    free(runtime->rom);
    free(runtime->resource_root);
}

NOKIA_RUNTIME_EXPORT NokiaRuntime *nokia_runtime_create_5320(
    const uint8_t *rom, size_t rom_size,
    const char *resource_root_utf8,
    uint32_t language_id, uint32_t voice_id) {
    NokiaRuntime *runtime;
    if (!rom || !rom_size) return NULL;
    runtime = (NokiaRuntime *)calloc(1, sizeof(*runtime));
    if (!runtime) return NULL;
    runtime->rom = (uint8_t *)malloc(rom_size);
    runtime->resource_root = copy_string(resource_root_utf8);
    runtime->heap = (uint8_t *)calloc(1, 0x100000u);
    runtime->vtable = (uint8_t *)calloc(1, 0x1000u);
    runtime->traps = (uint8_t *)calloc(1, 0x10000u);
    runtime->pool = (uint8_t *)calloc(1, 0x800000u);
    runtime->stack = (uint8_t *)calloc(1, 0x100000u);
    if (!runtime->rom || !runtime->heap || !runtime->vtable ||
        !runtime->traps || !runtime->pool || !runtime->stack ||
        (resource_root_utf8 && !runtime->resource_root)) {
        runtime_free_memory(runtime);
        free(runtime);
        return NULL;
    }
    memcpy(runtime->rom, rom, rom_size);
    runtime->rom_size = rom_size;
    runtime->language_id = language_id;
    runtime->voice_id = voice_id;
    runtime->rate_factor = 1.0;
    runtime->pitch_factor = 1.0;
    /* Guest stack starts at the top of the native backing region. */
    runtime->regs[13] = 0x60100000u - 16u;
    return runtime;
}

NOKIA_RUNTIME_EXPORT void nokia_runtime_destroy(NokiaRuntime *runtime) {
    if (!runtime) return;
    runtime_free_memory(runtime);
    free(runtime);
}

NOKIA_RUNTIME_EXPORT int nokia_runtime_set_rate(
    NokiaRuntime *runtime, double factor) {
    if (!runtime) return 0;
    if (factor < 0.20) factor = 0.20;
    if (factor > 5.00) factor = 5.00;
    runtime->rate_factor = factor;
    return 1;
}

NOKIA_RUNTIME_EXPORT int nokia_runtime_set_pitch(
    NokiaRuntime *runtime, double factor) {
    if (!runtime) return 0;
    if (factor < 0.50) factor = 0.50;
    if (factor > 2.00) factor = 2.00;
    runtime->pitch_factor = factor;
    return 1;
}

NOKIA_RUNTIME_EXPORT void nokia_runtime_cancel(NokiaRuntime *runtime) {
    if (runtime) runtime->cancelled = 1;
}

NOKIA_RUNTIME_EXPORT int nokia_runtime_speak_utf16(
    NokiaRuntime *runtime, const uint16_t *text, uint32_t text_length,
    const NokiaRuntimeCallbacks *callbacks) {
    (void)text;
    (void)text_length;
    (void)callbacks;
    if (!runtime) return 0;
    runtime->cancelled = 0;
    runtime->last_error = -1000; /* lifecycle AOT not wired yet */
    return 0;
}

NOKIA_RUNTIME_EXPORT int nokia_runtime_last_error(
    const NokiaRuntime *runtime) {
    return runtime ? runtime->last_error : -1;
}

NOKIA_RUNTIME_EXPORT uint64_t nokia_runtime_frontend_ticks(
    const NokiaRuntime *runtime) {
    return runtime ? runtime->frontend_ticks : 0;
}

NOKIA_RUNTIME_EXPORT uint64_t nokia_runtime_audio_ticks(
    const NokiaRuntime *runtime) {
    return runtime ? runtime->audio_ticks : 0;
}
