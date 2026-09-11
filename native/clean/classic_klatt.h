/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CLASSIC_KLATT_H
#define CLASSIC_KLATT_H

#include <stdint.h>

#if defined(_WIN32)
#define CK_API __declspec(dllexport)
#else
#define CK_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

enum {
    CLASSIC_KLATT_VOICE_MALE = 0,
    CLASSIC_KLATT_VOICE_FEMALE = 1,
};

typedef struct classic_klatt_engine classic_klatt_engine;

typedef void (*classic_klatt_pcm_callback)(
    void *user,
    const int16_t *samples,
    uint32_t sample_count,
    uint32_t sample_rate
);

typedef struct classic_klatt_callbacks {
    classic_klatt_pcm_callback pcm;
    void *user;
} classic_klatt_callbacks;

CK_API const char *classic_klatt_version(void);
CK_API classic_klatt_engine *classic_klatt_create(void);
CK_API void classic_klatt_destroy(classic_klatt_engine *engine);
CK_API void classic_klatt_cancel(classic_klatt_engine *engine);
CK_API void classic_klatt_reset_cancel(classic_klatt_engine *engine);

/*
 * Synchronously synthesize UTF-16 text. Rate and pitch use NVDA's 0..100
 * range. PCM is emitted in bounded chunks through callbacks->pcm.
 * Returns 1 on completion, 0 on cancellation or invalid input.
 */
CK_API int classic_klatt_speak_utf16(
    classic_klatt_engine *engine,
    const uint16_t *text,
    uint32_t text_units,
    int rate,
    int pitch,
    int voice,
    const classic_klatt_callbacks *callbacks
);

/* Test-only observability for the independently authored pronunciation rules. */
CK_API uint32_t classic_klatt_debug_phonemes_utf16(
    const uint16_t *text,
    uint32_t text_units,
    char *output,
    uint32_t output_size
);

#ifdef __cplusplus
}
#endif

#endif
