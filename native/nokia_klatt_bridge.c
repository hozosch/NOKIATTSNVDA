#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>

#ifdef _WIN32
#define NOKIA_EXPORT __declspec(dllexport)
#else
#define NOKIA_EXPORT __attribute__((visibility("default")))
#endif

typedef int (*UcHookAdd)(void *, size_t *, int, void *, void *, uint64_t, uint64_t, ...);
typedef int (*UcHookDel)(void *, size_t);
typedef int (*UcRegRead)(void *, int, void *);
typedef int (*UcRegWrite)(void *, int, const void *);
typedef int (*UcMemRead)(void *, uint64_t, void *, size_t);
typedef int (*UcMemWrite)(void *, uint64_t, const void *, size_t);

extern int nokia_klatt_generate_aot(
    int16_t *, int32_t *, uint8_t[122], uint8_t[564], uint32_t,
    const uint8_t *, uint32_t, size_t, uint32_t[5]);

typedef struct {
    void *uc;
    size_t hook;
    const uint8_t *rom;
    uint32_t rom_base;
    size_t rom_size;
    int r0, r1, r2, r3, r12, sp, lr, pc, cpsr;
    UcHookAdd hook_add;
    UcHookDel hook_del;
    UcRegRead reg_read;
    UcRegWrite reg_write;
    UcMemRead mem_read;
    UcMemWrite mem_write;
    uint64_t native_calls, fallback_calls;
} NokiaKlattBridge;

static NokiaKlattBridge bridge;

static int read_reg(void *uc, int id, uint32_t *value) {
    return bridge.reg_read(uc, id, value) == 0;
}

static void klatt_hook(void *uc, uint64_t address, size_t size, void *user) {
    uint32_t r[4], sp, lr, cpsr, gain, caller_after[5];
    uint8_t parameters[122], state[564];
    int16_t output[8192];
    int32_t peak;
    int16_t count;
    (void)address; (void)size; (void)user;
    if (!read_reg(uc, bridge.r0, &r[0]) ||
        !read_reg(uc, bridge.r1, &r[1]) ||
        !read_reg(uc, bridge.r2, &r[2]) ||
        !read_reg(uc, bridge.r3, &r[3]) ||
        !read_reg(uc, bridge.sp, &sp) ||
        !read_reg(uc, bridge.lr, &lr) ||
        !read_reg(uc, bridge.cpsr, &cpsr) ||
        bridge.mem_read(uc, sp, &gain, 4) ||
        bridge.mem_read(uc, r[2], parameters, sizeof(parameters)) ||
        bridge.mem_read(uc, r[3], state, sizeof(state)) ||
        bridge.mem_read(uc, r[1], &peak, sizeof(peak))) {
        bridge.fallback_calls++;
        return;
    }
    memcpy(&count, parameters + 2, sizeof(count));
    if (count < 0 || count > 8192 ||
        !nokia_klatt_generate_aot(output, &peak, parameters, state, gain,
                                  bridge.rom, bridge.rom_base,
                                  bridge.rom_size, caller_after)) {
        bridge.fallback_calls++;
        return;
    }
    if ((count && bridge.mem_write(uc, r[0], output, (size_t)count * 2)) ||
        bridge.mem_write(uc, r[1], &peak, sizeof(peak)) ||
        bridge.mem_write(uc, r[2], parameters, sizeof(parameters)) ||
        bridge.mem_write(uc, r[3], state, sizeof(state))) {
        bridge.fallback_calls++;
        return;
    }
    r[0] = (uint32_t)(int32_t)count;
    bridge.reg_write(uc, bridge.r0, &r[0]);
    bridge.reg_write(uc, bridge.r1, &caller_after[0]);
    bridge.reg_write(uc, bridge.r2, &caller_after[1]);
    bridge.reg_write(uc, bridge.r3, &caller_after[2]);
    bridge.reg_write(uc, bridge.r12, &caller_after[3]);
    cpsr = (cpsr & 0x0fffffffu) | caller_after[4];
    bridge.reg_write(uc, bridge.cpsr, &cpsr);
    bridge.reg_write(uc, bridge.pc, &lr);
    bridge.native_calls++;
}

NOKIA_EXPORT int nokia_install_klatt_hook(
    void *uc, uint64_t entry, const uint8_t *rom, uint32_t rom_base,
    size_t rom_size, const int register_ids[9], void *hook_add,
    void *hook_del, void *reg_read, void *reg_write, void *mem_read,
    void *mem_write) {
    memset(&bridge, 0, sizeof(bridge));
    bridge.uc = uc; bridge.rom = rom; bridge.rom_base = rom_base;
    bridge.rom_size = rom_size;
    bridge.r0=register_ids[0]; bridge.r1=register_ids[1];
    bridge.r2=register_ids[2]; bridge.r3=register_ids[3];
    bridge.r12=register_ids[4]; bridge.sp=register_ids[5];
    bridge.lr=register_ids[6]; bridge.pc=register_ids[7];
    bridge.cpsr=register_ids[8];
    bridge.hook_add=(UcHookAdd)hook_add; bridge.hook_del=(UcHookDel)hook_del;
    bridge.reg_read=(UcRegRead)reg_read; bridge.reg_write=(UcRegWrite)reg_write;
    bridge.mem_read=(UcMemRead)mem_read; bridge.mem_write=(UcMemWrite)mem_write;
    if (!bridge.hook_add || !bridge.hook_del || !bridge.reg_read ||
        !bridge.reg_write || !bridge.mem_read || !bridge.mem_write)
        return 0;
    return bridge.hook_add(uc, &bridge.hook, 4, (void *)klatt_hook, NULL,
                           entry, entry) == 0;
}

NOKIA_EXPORT void nokia_remove_klatt_hook(void) {
    if (bridge.uc && bridge.hook) bridge.hook_del(bridge.uc, bridge.hook);
    bridge.hook = 0;
}

NOKIA_EXPORT void nokia_klatt_hook_counters(uint64_t out[2]) {
    out[0] = bridge.native_calls; out[1] = bridge.fallback_calls;
}

enum { RATE_FRAME=480, RATE_OVERLAP=240, RATE_SEARCH=64,
       RATE_STEP=4, RATE_CORR=96 };
typedef struct {
    double factor, position;
    int16_t *samples;
    size_t count, capacity;
    int16_t tail[RATE_OVERLAP];
    int have_tail;
} NokiaRate;

static int reserve_samples(NokiaRate *s, size_t wanted) {
    if (wanted <= s->capacity) return 1;
    size_t capacity = s->capacity ? s->capacity : 2048;
    while (capacity < wanted) capacity *= 2;
    int16_t *grown = (int16_t *)realloc(s->samples, capacity * 2);
    if (!grown) return 0;
    s->samples = grown; s->capacity = capacity; return 1;
}

NOKIA_EXPORT void *nokia_rate_create(double factor) {
    NokiaRate *s = (NokiaRate *)calloc(1, sizeof(*s));
    if (!s) return NULL;
    s->factor = factor < 0.25 ? 0.25 : factor > 4.0 ? 4.0 : factor;
    return s;
}

NOKIA_EXPORT int nokia_rate_feed(void *handle, const int16_t *input,
                                 size_t input_count, int final,
                                 int16_t *output, size_t output_capacity) {
    NokiaRate *s = (NokiaRate *)handle;
    size_t produced = 0;
    if (!s || (!input && input_count) || !output) return -1;
    if (!reserve_samples(s, s->count + input_count)) return -2;
    if (input_count) memcpy(s->samples + s->count, input, input_count * 2);
    s->count += input_count;
    for (;;) {
        size_t ideal = (size_t)s->position;
        size_t margin = final ? RATE_FRAME : RATE_FRAME+RATE_SEARCH+RATE_CORR;
        if (ideal + margin > s->count) break;
        size_t read = ideal;
        if (s->have_tail) {
            int64_t best_score = INT64_MIN;
            size_t lo = ideal > RATE_SEARCH ? ideal-RATE_SEARCH : 0;
            size_t hi = ideal+RATE_SEARCH;
            if (hi + RATE_CORR > s->count) hi = s->count-RATE_CORR;
            for (size_t candidate=lo; candidate<=hi; candidate+=RATE_STEP) {
                int64_t score=0;
                for (size_t k=0;k<RATE_CORR;k+=2)
                    score += (int32_t)s->tail[k] * s->samples[candidate+k];
                if (score > best_score) { best_score=score; read=candidate; }
            }
        }
        if (read + RATE_FRAME > s->count || produced+RATE_OVERLAP > output_capacity)
            break;
        if (!s->have_tail) {
            memcpy(output+produced,s->samples+read,RATE_OVERLAP*2);
        } else {
            for (size_t k=0;k<RATE_OVERLAP;k++) {
                int32_t numerator=(int32_t)s->tail[k]*(RATE_OVERLAP-k)+
                                  (int32_t)s->samples[read+k]*k;
                int32_t mixed=numerator/RATE_OVERLAP;
                if (numerator < 0 && numerator % RATE_OVERLAP) mixed--;
                output[produced+k]=(int16_t)(mixed < -32768 ? -32768 :
                                             mixed > 32767 ? 32767 : mixed);
            }
        }
        memcpy(s->tail,s->samples+read+RATE_OVERLAP,RATE_OVERLAP*2);
        s->have_tail=1; produced+=RATE_OVERLAP;
        s->position += RATE_OVERLAP * s->factor;
    }
    size_t keep = s->position > RATE_SEARCH+1 ?
                  (size_t)s->position-RATE_SEARCH-1 : 0;
    if (keep) {
        size_t drop = keep > s->count ? s->count : keep;
        memmove(s->samples,s->samples+drop,(s->count-drop)*2);
        s->count-=drop; s->position-=keep;
    }
    if (final && s->have_tail) {
        if (produced+RATE_OVERLAP > output_capacity) return -3;
        memcpy(output+produced,s->tail,RATE_OVERLAP*2);
        produced+=RATE_OVERLAP; s->have_tail=0; s->count=0; s->position=0;
    }
    return (int)produced;
}

NOKIA_EXPORT void nokia_rate_destroy(void *handle) {
    NokiaRate *s=(NokiaRate *)handle;
    if (s) { free(s->samples); free(s); }
}
