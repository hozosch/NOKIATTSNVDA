/*
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Independently authored compact formant synthesizer prototype.
 *
 * This file implements generic source/filter speech synthesis and a small
 * German pronunciation rule set. It contains no Nokia firmware bytes,
 * translated machine instructions, ROM addresses, extracted configuration
 * tables, voice snapshots, or other data from the historical runtimes.
 */

#include "classic_klatt.h"

#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32)
#include <windows.h>
#else
#include <stdatomic.h>
#endif

#define CK_SAMPLE_RATE 16000u
#define CK_CHUNK_SAMPLES 1024u
#define CK_MAX_WORD_UNITS 192u
#define CK_PI 3.14159265358979323846

typedef enum phoneme_id {
    PH_SIL,
    PH_A,
    PH_A_LONG,
    PH_E,
    PH_E_LONG,
    PH_I,
    PH_I_LONG,
    PH_O,
    PH_O_LONG,
    PH_U,
    PH_U_LONG,
    PH_AE,
    PH_OE,
    PH_UE,
    PH_SCHWA,
    PH_P,
    PH_B,
    PH_T,
    PH_D,
    PH_K,
    PH_G,
    PH_F,
    PH_V,
    PH_S,
    PH_Z,
    PH_SH,
    PH_CH,
    PH_X,
    PH_H,
    PH_M,
    PH_N,
    PH_NG,
    PH_L,
    PH_R,
    PH_Y,
} phoneme_id;

typedef enum source_kind {
    SOURCE_SILENCE,
    SOURCE_VOWEL,
    SOURCE_VOICED,
    SOURCE_FRICATIVE,
    SOURCE_STOP,
} source_kind;

typedef struct phoneme_spec {
    const char *name;
    source_kind source;
    float f1;
    float f2;
    float f3;
    float b1;
    float b2;
    float b3;
    float duration_ms;
    float gain;
    float noise;
} phoneme_spec;

typedef struct segment {
    phoneme_id phoneme;
    float duration_scale;
    float accent;
} segment;

typedef struct segment_list {
    segment *items;
    size_t count;
    size_t capacity;
} segment_list;

typedef struct resonator {
    double a1;
    double a2;
    double b0;
    double y1;
    double y2;
} resonator;

typedef struct pcm_writer {
    const classic_klatt_callbacks *callbacks;
    int16_t samples[CK_CHUNK_SAMPLES];
    uint32_t count;
} pcm_writer;

struct classic_klatt_engine {
#if defined(_WIN32)
    volatile LONG cancelled;
#else
    atomic_int cancelled;
#endif
    uint32_t noise_state;
    double phase;
    double previous_glottal;
};

static const phoneme_spec PHONEMES[] = {
    [PH_SIL]    = {"_",  SOURCE_SILENCE,      0,    0,    0,  100,  100,  100,  55, 0.00f, 0.00f},
    [PH_A]      = {"a",  SOURCE_VOWEL,      760, 1180, 2550,   90,  120,  170,  92, 0.82f, 0.02f},
    [PH_A_LONG] = {"a:", SOURCE_VOWEL,      720, 1120, 2500,   80,  110,  160, 145, 0.84f, 0.02f},
    [PH_E]      = {"e",  SOURCE_VOWEL,      520, 1880, 2580,   80,  115,  170,  82, 0.76f, 0.02f},
    [PH_E_LONG] = {"e:", SOURCE_VOWEL,      440, 2050, 2650,   70,  105,  160, 138, 0.78f, 0.02f},
    [PH_I]      = {"i",  SOURCE_VOWEL,      340, 2180, 2920,   65,  105,  150,  78, 0.70f, 0.02f},
    [PH_I_LONG] = {"i:", SOURCE_VOWEL,      285, 2310, 3000,   60,   95,  145, 142, 0.72f, 0.02f},
    [PH_O]      = {"o",  SOURCE_VOWEL,      540,  920, 2450,   75,  110,  170,  88, 0.80f, 0.02f},
    [PH_O_LONG] = {"o:", SOURCE_VOWEL,      470,  820, 2380,   65,  100,  160, 142, 0.82f, 0.02f},
    [PH_U]      = {"u",  SOURCE_VOWEL,      380,  760, 2350,   70,  105,  165,  82, 0.76f, 0.02f},
    [PH_U_LONG] = {"u:", SOURCE_VOWEL,      320,  680, 2280,   60,   95,  155, 140, 0.78f, 0.02f},
    [PH_AE]     = {"ae", SOURCE_VOWEL,      610, 1720, 2500,   85,  115,  170,  94, 0.77f, 0.02f},
    [PH_OE]     = {"oe", SOURCE_VOWEL,      470, 1430, 2280,   75,  110,  165,  98, 0.76f, 0.02f},
    [PH_UE]     = {"ue", SOURCE_VOWEL,      330, 1660, 2350,   65,  105,  155,  92, 0.72f, 0.02f},
    [PH_SCHWA]  = {"@",  SOURCE_VOWEL,      510, 1460, 2450,  100,  140,  190,  62, 0.61f, 0.03f},
    [PH_P]      = {"p",  SOURCE_STOP,      1050, 2500, 4200,  220,  320,  500,  62, 0.52f, 1.00f},
    [PH_B]      = {"b",  SOURCE_STOP,       650, 1700, 3100,  190,  300,  480,  58, 0.49f, 0.55f},
    [PH_T]      = {"t",  SOURCE_STOP,      1800, 3600, 5200,  260,  420,  650,  55, 0.55f, 1.00f},
    [PH_D]      = {"d",  SOURCE_STOP,       850, 2200, 3900,  220,  350,  540,  54, 0.50f, 0.52f},
    [PH_K]      = {"k",  SOURCE_STOP,      1200, 2700, 4000,  260,  400,  600,  68, 0.54f, 0.95f},
    [PH_G]      = {"g",  SOURCE_STOP,       750, 1900, 3300,  220,  340,  520,  64, 0.49f, 0.48f},
    [PH_F]      = {"f",  SOURCE_FRICATIVE, 1100, 3100, 4900,  320,  500,  780,  92, 0.43f, 0.95f},
    [PH_V]      = {"v",  SOURCE_VOICED,     700, 1700, 3500,  220,  340,  560,  78, 0.48f, 0.38f},
    [PH_S]      = {"s",  SOURCE_FRICATIVE, 2500, 4700, 6500,  420,  650,  900, 105, 0.40f, 1.00f},
    [PH_Z]      = {"z",  SOURCE_VOICED,    2100, 4200, 6100,  420,  650,  900,  88, 0.43f, 0.58f},
    [PH_SH]     = {"sh", SOURCE_FRICATIVE, 1450, 2600, 4100,  330,  480,  720, 112, 0.48f, 1.00f},
    [PH_CH]     = {"ch", SOURCE_FRICATIVE, 1550, 3300, 5000,  300,  480,  760,  92, 0.40f, 0.78f},
    [PH_X]      = {"x",  SOURCE_FRICATIVE,  900, 1800, 3200,  300,  480,  720, 102, 0.46f, 0.88f},
    [PH_H]      = {"h",  SOURCE_FRICATIVE,  700, 1500, 2700,  480,  700,  950,  70, 0.31f, 0.55f},
    [PH_M]      = {"m",  SOURCE_VOICED,     260, 1050, 2150,  120,  180,  260,  84, 0.58f, 0.02f},
    [PH_N]      = {"n",  SOURCE_VOICED,     310, 1650, 2550,  120,  200,  280,  76, 0.57f, 0.02f},
    [PH_NG]     = {"ng", SOURCE_VOICED,     330, 2150, 2950,  130,  220,  300,  88, 0.55f, 0.02f},
    [PH_L]      = {"l",  SOURCE_VOICED,     390, 1180, 2650,  100,  170,  250,  72, 0.61f, 0.01f},
    [PH_R]      = {"r",  SOURCE_VOICED,     430, 1280, 1760,  130,  210,  280,  72, 0.56f, 0.06f},
    [PH_Y]      = {"j",  SOURCE_VOICED,     300, 2200, 2950,   80,  140,  210,  62, 0.55f, 0.01f},
};

static int engine_cancelled(const classic_klatt_engine *engine) {
#if defined(_WIN32)
    return InterlockedCompareExchange((volatile LONG *)&engine->cancelled, 0, 0) != 0;
#else
    return atomic_load_explicit(&engine->cancelled, memory_order_relaxed) != 0;
#endif
}

static void engine_set_cancelled(classic_klatt_engine *engine, int value) {
#if defined(_WIN32)
    InterlockedExchange(&engine->cancelled, value ? 1 : 0);
#else
    atomic_store_explicit(&engine->cancelled, value ? 1 : 0, memory_order_relaxed);
#endif
}

static int segments_reserve(segment_list *list, size_t needed) {
    segment *replacement;
    size_t capacity = list->capacity ? list->capacity : 64u;
    while (capacity < needed) {
        if (capacity > SIZE_MAX / 2u) {
            return 0;
        }
        capacity *= 2u;
    }
    replacement = (segment *)realloc(list->items, capacity * sizeof(*replacement));
    if (!replacement) {
        return 0;
    }
    list->items = replacement;
    list->capacity = capacity;
    return 1;
}

static int append_segment(segment_list *list, phoneme_id phoneme, float scale) {
    if (list->count == list->capacity && !segments_reserve(list, list->count + 1u)) {
        return 0;
    }
    list->items[list->count].phoneme = phoneme;
    list->items[list->count].duration_scale = scale;
    list->items[list->count].accent = 0.0f;
    list->count += 1u;
    return 1;
}

static int is_ascii_upper(uint16_t c) {
    return c >= (uint16_t)'A' && c <= (uint16_t)'Z';
}

static int is_ascii_digit(uint16_t c) {
    return c >= (uint16_t)'0' && c <= (uint16_t)'9';
}

static int is_word_character(uint16_t c) {
    return (c >= (uint16_t)'A' && c <= (uint16_t)'Z')
        || (c >= (uint16_t)'a' && c <= (uint16_t)'z')
        || is_ascii_digit(c)
        || c == 0x00c4u || c == 0x00d6u || c == 0x00dcu
        || c == 0x00e4u || c == 0x00f6u || c == 0x00fcu || c == 0x00dfu;
}

static uint16_t lower_character(uint16_t c) {
    if (c >= (uint16_t)'A' && c <= (uint16_t)'Z') {
        return (uint16_t)(c + ((uint16_t)'a' - (uint16_t)'A'));
    }
    if (c == 0x00c4u) return 0x00e4u;
    if (c == 0x00d6u) return 0x00f6u;
    if (c == 0x00dcu) return 0x00fcu;
    return c;
}

static int is_vowel_character(uint16_t c) {
    c = lower_character(c);
    return c == (uint16_t)'a' || c == (uint16_t)'e' || c == (uint16_t)'i'
        || c == (uint16_t)'o' || c == (uint16_t)'u' || c == (uint16_t)'y'
        || c == 0x00e4u || c == 0x00f6u || c == 0x00fcu;
}

static int match_pair(const uint16_t *word, size_t length, size_t at, uint16_t a, uint16_t b) {
    return at + 1u < length && word[at] == a && word[at + 1u] == b;
}

static int match_triple(
    const uint16_t *word,
    size_t length,
    size_t at,
    uint16_t a,
    uint16_t b,
    uint16_t c
) {
    return at + 2u < length && word[at] == a && word[at + 1u] == b && word[at + 2u] == c;
}

static int append_word(segment_list *list, const uint16_t *word, size_t length, int allow_spelling);
static int append_diphthong(segment_list *list, phoneme_id first, phoneme_id second);

static int append_ascii_word(segment_list *list, const char *word) {
    uint16_t units[32];
    size_t length = strlen(word);
    size_t i;
    if (length > sizeof(units) / sizeof(units[0])) {
        return 0;
    }
    for (i = 0; i < length; ++i) {
        units[i] = (uint16_t)(unsigned char)word[i];
    }
    return append_word(list, units, length, 0);
}

static int append_letter_name(segment_list *list, uint16_t c) {
    c = lower_character(c);
    switch (c) {
        case 'a': if (!append_segment(list, PH_A_LONG, 1.0f)) return 0; break;
        case 'b': if (!append_segment(list, PH_B, 0.8f) || !append_segment(list, PH_E_LONG, 1.0f)) return 0; break;
        case 'c': if (!append_segment(list, PH_T, 0.62f) || !append_segment(list, PH_S, 0.68f) || !append_segment(list, PH_E_LONG, 1.0f)) return 0; break;
        case 'd': if (!append_segment(list, PH_D, 0.8f) || !append_segment(list, PH_E_LONG, 1.0f)) return 0; break;
        case 'e': if (!append_segment(list, PH_E_LONG, 1.0f)) return 0; break;
        case 'f': if (!append_segment(list, PH_E, 0.78f) || !append_segment(list, PH_F, 0.82f)) return 0; break;
        case 'g': if (!append_segment(list, PH_G, 0.8f) || !append_segment(list, PH_E_LONG, 1.0f)) return 0; break;
        case 'h': if (!append_segment(list, PH_H, 0.72f) || !append_segment(list, PH_A_LONG, 1.0f)) return 0; break;
        case 'i': if (!append_segment(list, PH_I_LONG, 1.0f)) return 0; break;
        case 'j': if (!append_segment(list, PH_Y, 0.72f) || !append_segment(list, PH_O, 0.72f) || !append_segment(list, PH_T, 0.75f)) return 0; break;
        case 'k': if (!append_segment(list, PH_K, 0.82f) || !append_segment(list, PH_A_LONG, 1.0f)) return 0; break;
        case 'l': if (!append_segment(list, PH_E, 0.78f) || !append_segment(list, PH_L, 0.82f)) return 0; break;
        case 'm': if (!append_segment(list, PH_E, 0.78f) || !append_segment(list, PH_M, 0.82f)) return 0; break;
        case 'n': if (!append_segment(list, PH_E, 0.78f) || !append_segment(list, PH_N, 0.82f)) return 0; break;
        case 'o': if (!append_segment(list, PH_O_LONG, 1.0f)) return 0; break;
        case 'p': if (!append_segment(list, PH_P, 0.8f) || !append_segment(list, PH_E_LONG, 1.0f)) return 0; break;
        case 'q': if (!append_segment(list, PH_K, 0.78f) || !append_segment(list, PH_U_LONG, 1.0f)) return 0; break;
        case 'r': if (!append_segment(list, PH_E, 0.76f) || !append_segment(list, PH_R, 0.84f)) return 0; break;
        case 's': if (!append_segment(list, PH_E, 0.76f) || !append_segment(list, PH_S, 0.84f)) return 0; break;
        case 't': if (!append_segment(list, PH_T, 0.8f) || !append_segment(list, PH_E_LONG, 1.0f)) return 0; break;
        case 'u': if (!append_segment(list, PH_U_LONG, 1.0f)) return 0; break;
        case 'v': if (!append_segment(list, PH_F, 0.72f) || !append_diphthong(list, PH_A, PH_U)) return 0; break;
        case 'w': if (!append_segment(list, PH_V, 0.8f) || !append_segment(list, PH_E_LONG, 1.0f)) return 0; break;
        case 'x': if (!append_segment(list, PH_I, 0.72f) || !append_segment(list, PH_K, 0.64f) || !append_segment(list, PH_S, 0.72f)) return 0; break;
        case 'y':
            if (!append_segment(list, PH_UE, 0.84f) || !append_segment(list, PH_P, 0.60f)
                || !append_segment(list, PH_S, 0.60f) || !append_segment(list, PH_I, 0.72f)
                || !append_segment(list, PH_L, 0.64f) || !append_segment(list, PH_O, 0.72f)
                || !append_segment(list, PH_N, 0.72f)) return 0;
            break;
        case 'z':
            if (!append_segment(list, PH_T, 0.62f) || !append_segment(list, PH_S, 0.68f)
                || !append_segment(list, PH_E, 0.72f) || !append_segment(list, PH_T, 0.72f)) return 0;
            break;
        case 0x00e4u: if (!append_segment(list, PH_AE, 1.45f)) return 0; break;
        case 0x00f6u: if (!append_segment(list, PH_OE, 1.45f)) return 0; break;
        case 0x00fcu: if (!append_segment(list, PH_UE, 1.45f)) return 0; break;
        case 0x00dfu:
            if (!append_segment(list, PH_E, 0.72f) || !append_segment(list, PH_S, 0.72f)
                || !append_segment(list, PH_T, 0.58f) || !append_segment(list, PH_S, 0.62f)
                || !append_segment(list, PH_E, 0.68f) || !append_segment(list, PH_T, 0.68f)) return 0;
            break;
        default: return 1;
    }
    return append_segment(list, PH_SIL, 0.36f);
}

static int append_digit_name(segment_list *list, uint16_t c) {
    if (!is_ascii_digit(c)) {
        return 1;
    }
    switch (c) {
        case '0':
            if (!append_segment(list, PH_N, 1.0f) || !append_segment(list, PH_U, 1.0f)
                || !append_segment(list, PH_L, 1.0f)) return 0;
            break;
        case '1':
            if (!append_diphthong(list, PH_A, PH_I) || !append_segment(list, PH_N, 0.82f)
                || !append_segment(list, PH_S, 0.84f)) return 0;
            break;
        case '2':
            if (!append_segment(list, PH_T, 0.58f) || !append_segment(list, PH_S, 0.62f)
                || !append_segment(list, PH_V, 0.76f) || !append_diphthong(list, PH_A, PH_I)) return 0;
            break;
        case '3':
            if (!append_segment(list, PH_D, 0.76f) || !append_segment(list, PH_R, 0.76f)
                || !append_diphthong(list, PH_A, PH_I)) return 0;
            break;
        case '4':
            if (!append_segment(list, PH_F, 0.82f) || !append_segment(list, PH_I_LONG, 1.0f)
                || !append_segment(list, PH_R, 0.74f)) return 0;
            break;
        case '5':
            if (!append_segment(list, PH_F, 0.82f) || !append_segment(list, PH_UE, 1.0f)
                || !append_segment(list, PH_N, 0.72f) || !append_segment(list, PH_F, 0.74f)) return 0;
            break;
        case '6':
            if (!append_segment(list, PH_Z, 0.74f) || !append_segment(list, PH_E, 0.90f)
                || !append_segment(list, PH_K, 0.66f) || !append_segment(list, PH_S, 0.72f)) return 0;
            break;
        case '7':
            if (!append_segment(list, PH_Z, 0.74f) || !append_segment(list, PH_I_LONG, 0.90f)
                || !append_segment(list, PH_B, 0.70f) || !append_segment(list, PH_SCHWA, 0.72f)
                || !append_segment(list, PH_N, 0.72f)) return 0;
            break;
        case '8':
            if (!append_segment(list, PH_A, 0.92f) || !append_segment(list, PH_X, 0.76f)
                || !append_segment(list, PH_T, 0.70f)) return 0;
            break;
        case '9':
            if (!append_segment(list, PH_N, 0.74f) || !append_segment(list, PH_O, 0.68f)
                || !append_segment(list, PH_UE, 0.68f) || !append_segment(list, PH_N, 0.72f)) return 0;
            break;
        default: return 1;
    }
    return append_segment(list, PH_SIL, 0.32f);
}

static int append_diphthong(segment_list *list, phoneme_id first, phoneme_id second) {
    return append_segment(list, first, 0.72f) && append_segment(list, second, 0.66f);
}

static int append_word(segment_list *list, const uint16_t *input, size_t length, int allow_spelling) {
    uint16_t word[CK_MAX_WORD_UNITS];
    size_t i;
    size_t word_start;
    size_t before = list->count;
    int uppercase_count = 0;
    int letter_count = 0;
    int has_digit = 0;
    int accented = 0;

    if (!length) {
        return 1;
    }
    if (length > CK_MAX_WORD_UNITS) {
        length = CK_MAX_WORD_UNITS;
    }
    for (i = 0; i < length; ++i) {
        if (is_ascii_upper(input[i])) uppercase_count += 1;
        if (is_word_character(input[i]) && !is_ascii_digit(input[i])) {
            letter_count += 1;
        }
        if (is_ascii_digit(input[i])) has_digit = 1;
        word[i] = lower_character(input[i]);
    }

    if (has_digit) {
        for (i = 0; i < length; ++i) {
            if (is_ascii_digit(input[i]) && !append_digit_name(list, input[i])) return 0;
            if (!is_ascii_digit(input[i]) && !append_letter_name(list, input[i])) return 0;
        }
        return 1;
    }
    if (allow_spelling && letter_count > 0
        && ((length == 1u) || (uppercase_count == letter_count && letter_count <= 8))) {
        for (i = 0; i < length; ++i) {
            if (!append_letter_name(list, input[i])) return 0;
        }
        return 1;
    }

    word_start = list->count;
    for (i = 0; i < length;) {
        uint16_t c = word[i];

        if (match_triple(word, length, i, 't', 's', 'c') && i + 3u < length && word[i + 3u] == 'h') {
            if (!append_segment(list, PH_T, 0.70f) || !append_segment(list, PH_SH, 0.90f)) return 0;
            i += 4u;
            continue;
        }
        if (match_triple(word, length, i, 's', 'c', 'h')) {
            if (!append_segment(list, PH_SH, 1.0f)) return 0;
            i += 3u;
            continue;
        }
        if (match_pair(word, length, i, 'c', 'h')) {
            int dark = i > 0u && (word[i - 1u] == 'a' || word[i - 1u] == 'o' || word[i - 1u] == 'u');
            if (!append_segment(list, dark ? PH_X : PH_CH, 1.0f)) return 0;
            i += 2u;
            continue;
        }
        if (match_pair(word, length, i, 'n', 'g')) {
            if (!append_segment(list, PH_NG, 1.0f)) return 0;
            i += 2u;
            continue;
        }
        if (match_pair(word, length, i, 'n', 'k')) {
            if (!append_segment(list, PH_NG, 0.85f) || !append_segment(list, PH_K, 0.82f)) return 0;
            i += 2u;
            continue;
        }
        if (match_pair(word, length, i, 'p', 'f')) {
            if (!append_segment(list, PH_P, 0.68f) || !append_segment(list, PH_F, 0.78f)) return 0;
            i += 2u;
            continue;
        }
        if (match_pair(word, length, i, 'p', 'h')) {
            if (!append_segment(list, PH_F, 1.0f)) return 0;
            i += 2u;
            continue;
        }
        if (match_pair(word, length, i, 't', 'h')) {
            if (!append_segment(list, PH_T, 1.0f)) return 0;
            i += 2u;
            continue;
        }
        if (match_pair(word, length, i, 'q', 'u')) {
            if (!append_segment(list, PH_K, 0.78f) || !append_segment(list, PH_V, 0.72f)) return 0;
            i += 2u;
            continue;
        }
        if (i == 0u && match_pair(word, length, i, 's', 'p')) {
            if (!append_segment(list, PH_SH, 0.78f) || !append_segment(list, PH_P, 0.72f)) return 0;
            i += 2u;
            continue;
        }
        if (i == 0u && match_pair(word, length, i, 's', 't')) {
            if (!append_segment(list, PH_SH, 0.78f) || !append_segment(list, PH_T, 0.72f)) return 0;
            i += 2u;
            continue;
        }
        if (match_pair(word, length, i, 't', 'z')) {
            if (!append_segment(list, PH_T, 0.64f) || !append_segment(list, PH_S, 0.78f)) return 0;
            i += 2u;
            continue;
        }
        if (match_pair(word, length, i, 'c', 'k')) {
            if (!append_segment(list, PH_K, 1.0f)) return 0;
            i += 2u;
            continue;
        }
        if (match_pair(word, length, i, 's', 's')) {
            if (!append_segment(list, PH_S, 1.05f)) return 0;
            i += 2u;
            continue;
        }
        if (match_pair(word, length, i, 'e', 'i') || match_pair(word, length, i, 'a', 'i')
            || match_pair(word, length, i, 'a', 'y') || match_pair(word, length, i, 'e', 'y')) {
            if (!append_diphthong(list, PH_A, PH_I)) return 0;
            i += 2u;
            continue;
        }
        if (match_pair(word, length, i, 'a', 'u')) {
            if (!append_diphthong(list, PH_A, PH_U)) return 0;
            i += 2u;
            continue;
        }
        if (match_pair(word, length, i, 'e', 'u') || match_pair(word, length, i, 0x00e4u, 'u')) {
            if (!append_diphthong(list, PH_O, PH_UE)) return 0;
            i += 2u;
            continue;
        }
        if (match_pair(word, length, i, 'i', 'e')) {
            if (!append_segment(list, PH_I_LONG, 1.0f)) return 0;
            i += 2u;
            continue;
        }
        if (i + 1u < length && word[i + 1u] == c && is_vowel_character(c)) {
            phoneme_id long_vowel = c == 'a' ? PH_A_LONG : c == 'e' ? PH_E_LONG
                : c == 'i' ? PH_I_LONG : c == 'o' ? PH_O_LONG : PH_U_LONG;
            if (!append_segment(list, long_vowel, 1.0f)) return 0;
            i += 2u;
            continue;
        }
        if (c == 'h' && i > 0u && is_vowel_character(word[i - 1u])) {
            i += 1u;
            continue;
        }

        switch (c) {
            case 'a': if (!append_segment(list, PH_A, 1.0f)) return 0; break;
            case 'e':
                if (!append_segment(list, (i + 1u == length || (i + 2u == length && word[i + 1u] == 'r')) ? PH_SCHWA : PH_E, 1.0f)) return 0;
                break;
            case 'i': if (!append_segment(list, PH_I, 1.0f)) return 0; break;
            case 'o': if (!append_segment(list, PH_O, 1.0f)) return 0; break;
            case 'u': if (!append_segment(list, PH_U, 1.0f)) return 0; break;
            case 0x00e4u: if (!append_segment(list, PH_AE, 1.0f)) return 0; break;
            case 0x00f6u: if (!append_segment(list, PH_OE, 1.0f)) return 0; break;
            case 0x00fcu: if (!append_segment(list, PH_UE, 1.0f)) return 0; break;
            case 0x00dfu: if (!append_segment(list, PH_S, 1.05f)) return 0; break;
            case 'b': if (!append_segment(list, i + 1u == length ? PH_P : PH_B, 1.0f)) return 0; break;
            case 'c':
                if (!append_segment(list, i + 1u < length && (word[i + 1u] == 'e' || word[i + 1u] == 'i' || word[i + 1u] == 0x00e4u) ? PH_S : PH_K, 1.0f)) return 0;
                break;
            case 'd': if (!append_segment(list, i + 1u == length ? PH_T : PH_D, 1.0f)) return 0; break;
            case 'f': if (!append_segment(list, PH_F, 1.0f)) return 0; break;
            case 'g': if (!append_segment(list, i + 1u == length ? PH_K : PH_G, 1.0f)) return 0; break;
            case 'h': if (!append_segment(list, PH_H, 1.0f)) return 0; break;
            case 'j': if (!append_segment(list, PH_Y, 1.0f)) return 0; break;
            case 'k': if (!append_segment(list, PH_K, 1.0f)) return 0; break;
            case 'l': if (!append_segment(list, PH_L, 1.0f)) return 0; break;
            case 'm': if (!append_segment(list, PH_M, 1.0f)) return 0; break;
            case 'n': if (!append_segment(list, PH_N, 1.0f)) return 0; break;
            case 'p': if (!append_segment(list, PH_P, 1.0f)) return 0; break;
            case 'r': if (!append_segment(list, PH_R, 1.0f)) return 0; break;
            case 's':
                if (!append_segment(list, i == 0u && i + 1u < length && is_vowel_character(word[i + 1u]) ? PH_Z : PH_S, 1.0f)) return 0;
                break;
            case 't': if (!append_segment(list, PH_T, 1.0f)) return 0; break;
            case 'v': if (!append_segment(list, PH_F, 1.0f)) return 0; break;
            case 'w': if (!append_segment(list, PH_V, 1.0f)) return 0; break;
            case 'x':
                if (!append_segment(list, PH_K, 0.72f) || !append_segment(list, PH_S, 0.78f)) return 0;
                break;
            case 'y': if (!append_segment(list, PH_UE, 1.0f)) return 0; break;
            case 'z':
                if (!append_segment(list, PH_T, 0.64f) || !append_segment(list, PH_S, 0.78f)) return 0;
                break;
            default: break;
        }
        i += 1u;
    }

    for (i = word_start; i < list->count; ++i) {
        if (!accented && PHONEMES[list->items[i].phoneme].source == SOURCE_VOWEL) {
            list->items[i].accent = 1.0f;
            accented = 1;
        }
    }
    if (list->count > before) {
        return append_segment(list, PH_SIL, 0.50f);
    }
    return 1;
}

static int append_punctuation_name(segment_list *list, uint16_t c) {
    const char *name = NULL;
    switch (c) {
        case '.': name = "punkt"; break;
        case ',': name = "komma"; break;
        case ':': name = "doppelpunkt"; break;
        case ';': name = "semikolon"; break;
        case '!': name = "ausrufezeichen"; break;
        case '?': name = "fragezeichen"; break;
        case '-': name = "bindestrich"; break;
        case '_': name = "unterstrich"; break;
        case '/': name = "schraegstrich"; break;
        case '\\': name = "backslash"; break;
        case '@': name = "at"; break;
        default: break;
    }
    return !name || append_ascii_word(list, name);
}

static int phonemize_text(
    const uint16_t *text,
    uint32_t text_units,
    segment_list *list
) {
    uint32_t at = 0;
    int only_punctuation = text_units == 1u && !is_word_character(text[0]);
    while (at < text_units) {
        if (is_word_character(text[at])) {
            uint32_t start = at;
            while (at < text_units && is_word_character(text[at])) at += 1u;
            if (!append_word(list, text + start, at - start, 1)) return 0;
            continue;
        }
        if (only_punctuation && !append_punctuation_name(list, text[at])) return 0;
        if (text[at] == '.' || text[at] == '!' || text[at] == '?') {
            if (!append_segment(list, PH_SIL, 3.1f)) return 0;
        } else if (text[at] == ',' || text[at] == ';' || text[at] == ':') {
            if (!append_segment(list, PH_SIL, 1.8f)) return 0;
        } else if (text[at] == '\n' || text[at] == '\r') {
            if (!append_segment(list, PH_SIL, 2.4f)) return 0;
        }
        at += 1u;
    }
    return 1;
}

static void resonator_set(resonator *filter, double frequency, double bandwidth) {
    double radius;
    if (frequency < 80.0) frequency = 80.0;
    if (frequency > (double)CK_SAMPLE_RATE * 0.46) frequency = (double)CK_SAMPLE_RATE * 0.46;
    if (bandwidth < 30.0) bandwidth = 30.0;
    radius = exp(-CK_PI * bandwidth / (double)CK_SAMPLE_RATE);
    filter->a1 = 2.0 * radius * cos(2.0 * CK_PI * frequency / (double)CK_SAMPLE_RATE);
    filter->a2 = radius * radius;
    filter->b0 = 1.0 - radius;
}

static double resonator_tick(resonator *filter, double input) {
    double output = filter->b0 * input + filter->a1 * filter->y1 - filter->a2 * filter->y2;
    filter->y2 = filter->y1;
    filter->y1 = output;
    return output;
}

static double next_noise(classic_klatt_engine *engine) {
    engine->noise_state = engine->noise_state * 1664525u + 1013904223u;
    return ((double)((engine->noise_state >> 8u) & 0x00ffffffu) / 8388607.5) - 1.0;
}

static int pcm_flush(pcm_writer *writer) {
    if (!writer->count) return 1;
    writer->callbacks->pcm(writer->callbacks->user, writer->samples, writer->count, CK_SAMPLE_RATE);
    writer->count = 0;
    return 1;
}

static int pcm_put(pcm_writer *writer, int16_t sample) {
    writer->samples[writer->count++] = sample;
    if (writer->count == CK_CHUNK_SAMPLES) return pcm_flush(writer);
    return 1;
}

static int16_t quantize_sample(double sample) {
    if (sample > 0.98) sample = 0.98;
    if (sample < -0.98) sample = -0.98;
    return (int16_t)lrint(sample * 32767.0);
}

static double rate_duration_scale(int rate) {
    if (rate < 0) rate = 0;
    if (rate > 100) rate = 100;
    return pow(2.0, (50.0 - (double)rate) / 32.0);
}

static double pitch_frequency_scale(int pitch) {
    if (pitch < 0) pitch = 0;
    if (pitch > 100) pitch = 100;
    return pow(2.0, ((double)pitch - 50.0) / 58.0);
}

static int synthesize_segments(
    classic_klatt_engine *engine,
    const segment_list *segments,
    int rate,
    int pitch,
    int voice,
    const classic_klatt_callbacks *callbacks,
    int question
) {
    resonator f1 = {0}, f2 = {0}, f3 = {0};
    pcm_writer writer = {0};
    double duration_scale = rate_duration_scale(rate);
    double base_f0 = voice == CLASSIC_KLATT_VOICE_FEMALE ? 184.0 : 108.0;
    double pitch_scale = pitch_frequency_scale(pitch);
    double previous_f1 = 500.0, previous_f2 = 1500.0, previous_f3 = 2500.0;
    size_t segment_index;

    writer.callbacks = callbacks;
    engine->noise_state = 0x434b4c54u;
    engine->phase = 0.0;
    engine->previous_glottal = 0.0;

    for (segment_index = 0; segment_index < segments->count; ++segment_index) {
        const segment *segment = &segments->items[segment_index];
        const phoneme_spec *spec = &PHONEMES[segment->phoneme];
        uint32_t sample_count = (uint32_t)lrint(
            spec->duration_ms * (double)segment->duration_scale * duration_scale
            * (double)CK_SAMPLE_RATE / 1000.0
        );
        uint32_t sample_index;
        if (sample_count < 8u) sample_count = 8u;

        for (sample_index = 0; sample_index < sample_count; ++sample_index) {
            double position = (double)sample_index / (double)sample_count;
            double transition = position < 0.34 ? position / 0.34 : 1.0;
            double utterance_position = segments->count > 1u
                ? ((double)segment_index + position) / (double)segments->count : position;
            double final_lift = question && utterance_position > 0.72
                ? 0.22 * (utterance_position - 0.72) / 0.28 : 0.0;
            double f0 = base_f0 * pitch_scale
                * (1.06 - 0.16 * utterance_position + 0.075 * segment->accent + final_lift);
            double amplitude_envelope = 1.0;
            double source = 0.0;
            double noise = next_noise(engine);
            double output;

            if ((sample_index & 63u) == 0u && engine_cancelled(engine)) {
                return 0;
            }
            if (position < 0.055) amplitude_envelope = position / 0.055;
            if (position > 0.91) amplitude_envelope *= (1.0 - position) / 0.09;
            if (amplitude_envelope < 0.0) amplitude_envelope = 0.0;

            resonator_set(&f1, previous_f1 + transition * ((double)spec->f1 - previous_f1), spec->b1);
            resonator_set(&f2, previous_f2 + transition * ((double)spec->f2 - previous_f2), spec->b2);
            resonator_set(&f3, previous_f3 + transition * ((double)spec->f3 - previous_f3), spec->b3);

            if (spec->source == SOURCE_VOWEL || spec->source == SOURCE_VOICED) {
                double glottal;
                engine->phase += f0 / (double)CK_SAMPLE_RATE;
                if (engine->phase >= 1.0) engine->phase -= floor(engine->phase);
                if (engine->phase < 0.42) {
                    glottal = 0.5 - 0.5 * cos(CK_PI * engine->phase / 0.42);
                } else if (engine->phase < 0.68) {
                    glottal = cos(0.5 * CK_PI * (engine->phase - 0.42) / 0.26);
                } else {
                    glottal = 0.0;
                }
                source = (glottal - engine->previous_glottal) * 3.2;
                engine->previous_glottal = glottal;
                source += noise * spec->noise * 0.18;
            } else if (spec->source == SOURCE_FRICATIVE) {
                source = noise * spec->noise;
            } else if (spec->source == SOURCE_STOP) {
                if (position < 0.58) {
                    source = spec->noise < 0.8f ? 0.04 * sin(2.0 * CK_PI * engine->phase) : 0.0;
                    engine->phase += f0 / (double)CK_SAMPLE_RATE;
                    if (engine->phase >= 1.0) engine->phase -= 1.0;
                } else {
                    double burst = (position - 0.58) / 0.42;
                    source = noise * spec->noise * exp(-5.0 * burst);
                }
            }

            if (spec->source == SOURCE_SILENCE) {
                output = 0.0;
            } else {
                double r1 = resonator_tick(&f1, source);
                double r2 = resonator_tick(&f2, source);
                double r3 = resonator_tick(&f3, source);
                output = (0.62 * r1 + 0.31 * r2 + 0.18 * r3)
                    * (double)spec->gain * amplitude_envelope * 1.45;
                output = tanh(output * 1.35) * 0.86;
            }
            if (!pcm_put(&writer, quantize_sample(output))) return 0;
        }
        if (spec->source != SOURCE_SILENCE) {
            previous_f1 = spec->f1;
            previous_f2 = spec->f2;
            previous_f3 = spec->f3;
        }
    }
    return pcm_flush(&writer);
}

const char *classic_klatt_version(void) {
    return "0.1.0-clean-test1";
}

classic_klatt_engine *classic_klatt_create(void) {
    classic_klatt_engine *engine = (classic_klatt_engine *)calloc(1u, sizeof(*engine));
    if (!engine) return NULL;
#if !defined(_WIN32)
    atomic_init(&engine->cancelled, 0);
#endif
    engine->noise_state = 0x434b4c54u;
    return engine;
}

void classic_klatt_destroy(classic_klatt_engine *engine) {
    free(engine);
}

void classic_klatt_cancel(classic_klatt_engine *engine) {
    if (engine) engine_set_cancelled(engine, 1);
}

void classic_klatt_reset_cancel(classic_klatt_engine *engine) {
    if (engine) engine_set_cancelled(engine, 0);
}

int classic_klatt_speak_utf16(
    classic_klatt_engine *engine,
    const uint16_t *text,
    uint32_t text_units,
    int rate,
    int pitch,
    int voice,
    const classic_klatt_callbacks *callbacks
) {
    segment_list segments = {0};
    int question = 0;
    uint32_t i;
    int result;
    if (!engine || !text || !text_units || !callbacks || !callbacks->pcm) return 0;
    if (voice != CLASSIC_KLATT_VOICE_MALE && voice != CLASSIC_KLATT_VOICE_FEMALE) return 0;
    for (i = 0; i < text_units; ++i) {
        if (text[i] == '?') question = 1;
    }
    if (engine_cancelled(engine)) return 0;
    if (!phonemize_text(text, text_units, &segments)) {
        free(segments.items);
        return 0;
    }
    result = segments.count
        ? synthesize_segments(engine, &segments, rate, pitch, voice, callbacks, question)
        : 1;
    free(segments.items);
    return result;
}

uint32_t classic_klatt_debug_phonemes_utf16(
    const uint16_t *text,
    uint32_t text_units,
    char *output,
    uint32_t output_size
) {
    segment_list segments = {0};
    size_t i;
    uint32_t required = 0;
    uint32_t written = 0;
    if (!text || !text_units || !phonemize_text(text, text_units, &segments)) {
        if (output && output_size) output[0] = '\0';
        free(segments.items);
        return 0;
    }
    for (i = 0; i < segments.count; ++i) {
        const char *name = PHONEMES[segments.items[i].phoneme].name;
        size_t length = strlen(name);
        size_t j;
        if (i) {
            if (output && written + 1u < output_size) output[written] = ' ';
            written += 1u;
            required += 1u;
        }
        for (j = 0; j < length; ++j) {
            if (output && written + 1u < output_size) output[written] = name[j];
            written += 1u;
            required += 1u;
        }
    }
    if (output && output_size) {
        uint32_t terminator = written < output_size ? written : output_size - 1u;
        output[terminator] = '\0';
    }
    free(segments.items);
    return required;
}
