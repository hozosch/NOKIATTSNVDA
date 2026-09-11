/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "../native/clean/classic_klatt.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct capture {
    classic_klatt_engine *engine;
    uint64_t samples;
    uint64_t nonzero;
    uint32_t callbacks;
    uint32_t hash;
    uint32_t peak;
    uint64_t clipped;
    int cancel_after_first;
} capture;

static void capture_pcm(void *user, const int16_t *samples, uint32_t count, uint32_t rate) {
    capture *state = (capture *)user;
    uint32_t i;
    assert(rate == 16000u);
    assert(count > 0u);
    state->callbacks += 1u;
    state->samples += count;
    for (i = 0; i < count; ++i) {
        uint16_t bits = (uint16_t)samples[i];
        uint32_t magnitude = samples[i] < 0
            ? (uint32_t)(-(int32_t)samples[i]) : (uint32_t)samples[i];
        if (samples[i] != 0) state->nonzero += 1u;
        if (magnitude > state->peak) state->peak = magnitude;
        if (magnitude >= 32000u) state->clipped += 1u;
        state->hash ^= (uint8_t)(bits & 0xffu);
        state->hash *= 16777619u;
        state->hash ^= (uint8_t)(bits >> 8u);
        state->hash *= 16777619u;
    }
    if (state->cancel_after_first && state->callbacks == 1u) {
        classic_klatt_cancel(state->engine);
    }
}

static capture render(
    classic_klatt_engine *engine,
    const uint16_t *text,
    uint32_t units,
    int rate,
    int pitch,
    int voice,
    int expected_result
) {
    capture state = {0};
    classic_klatt_callbacks callbacks;
    int result;
    state.engine = engine;
    state.hash = 2166136261u;
    callbacks.pcm = capture_pcm;
    callbacks.user = &state;
    result = classic_klatt_speak_utf16(
        engine, text, units, rate, pitch, voice, &callbacks
    );
    assert(result == expected_result);
    return state;
}

static void assert_phonemes(
    const uint16_t *text,
    uint32_t units,
    const char *expected
) {
    char phonemes[256];
    uint32_t needed = classic_klatt_debug_phonemes_utf16(
        text, units, phonemes, (uint32_t)sizeof(phonemes)
    );
    assert(needed == strlen(expected));
    assert(strcmp(phonemes, expected) == 0);
}

int main(void) {
    static const uint16_t hallo[] = {'H', 'a', 'l', 'l', 'o'};
    static const uint16_t phrase[] = {
        'S', 'p', 'r', 'a', 'c', 'h', 'e', ' ', 'f', 0x00fcu, 'r', ' ',
        'N', 'V', 'D', 'A', '.',
    };
    static const uint16_t schule[] = {'S', 'c', 'h', 'u', 'l', 'e'};
    static const uint16_t guten[] = {'G', 'u', 't', 'e', 'n'};
    static const uint16_t tag[] = {'T', 'a', 'g'};
    static const uint16_t klatt[] = {'K', 'l', 'a', 't', 't'};
    static const uint16_t fuer[] = {'f', 0x00fcu, 'r'};
    classic_klatt_engine *engine = classic_klatt_create();
    capture male1;
    capture male2;
    capture female;
    capture slow;
    capture fast;
    capture cancelled = {0};
    classic_klatt_callbacks cancel_callbacks;

    assert(engine != NULL);
    assert(strstr(classic_klatt_version(), "clean") != NULL);

    assert_phonemes(schule, (uint32_t)(sizeof(schule) / sizeof(schule[0])), "sh u: l @ _");
    assert_phonemes(guten, (uint32_t)(sizeof(guten) / sizeof(guten[0])), "g u: t @ n _");
    assert_phonemes(tag, (uint32_t)(sizeof(tag) / sizeof(tag[0])), "t a: k _");
    assert_phonemes(klatt, (uint32_t)(sizeof(klatt) / sizeof(klatt[0])), "k l a t _");
    assert_phonemes(fuer, (uint32_t)(sizeof(fuer) / sizeof(fuer[0])), "f ue 6 _");

    male1 = render(engine, phrase, (uint32_t)(sizeof(phrase) / sizeof(phrase[0])), 50, 50, 0, 1);
    male2 = render(engine, phrase, (uint32_t)(sizeof(phrase) / sizeof(phrase[0])), 50, 50, 0, 1);
    female = render(engine, phrase, (uint32_t)(sizeof(phrase) / sizeof(phrase[0])), 50, 50, 1, 1);
    assert(male1.samples > 16000u);
    assert(male1.nonzero > male1.samples / 4u);
    assert(male1.peak > 1000u && male1.peak < 32767u);
    assert(male1.clipped < male1.samples / 100u);
    assert(male1.callbacks > 1u);
    assert(male1.samples == male2.samples);
    assert(male1.hash == male2.hash);
    assert(female.samples > male1.samples);
    assert(female.samples < male1.samples * 6u / 5u);
    assert(female.hash != male1.hash);

    slow = render(engine, hallo, (uint32_t)(sizeof(hallo) / sizeof(hallo[0])), 25, 50, 0, 1);
    fast = render(engine, hallo, (uint32_t)(sizeof(hallo) / sizeof(hallo[0])), 75, 50, 0, 1);
    assert(slow.samples > fast.samples * 2u);

    cancelled.engine = engine;
    cancelled.hash = 2166136261u;
    cancelled.cancel_after_first = 1;
    cancel_callbacks.pcm = capture_pcm;
    cancel_callbacks.user = &cancelled;
    assert(!classic_klatt_speak_utf16(
        engine, phrase, (uint32_t)(sizeof(phrase) / sizeof(phrase[0])), 20, 50, 0, &cancel_callbacks
    ));
    assert(cancelled.callbacks == 1u);
    classic_klatt_reset_cancel(engine);
    male2 = render(engine, hallo, (uint32_t)(sizeof(hallo) / sizeof(hallo[0])), 50, 50, 0, 1);
    assert(male2.nonzero > 0u);

    printf(
        "samples=%llu peak=%u clipped=%llu hash=%08x\n",
        (unsigned long long)male1.samples,
        male1.peak,
        (unsigned long long)male1.clipped,
        male1.hash
    );

    classic_klatt_destroy(engine);
    puts("classic Klatt independent core tests passed");
    return 0;
}
