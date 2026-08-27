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
typedef int32_t (*NokiaResample)(
    const int16_t *, int32_t, int16_t *, int32_t,
    int32_t *, int32_t *, int32_t *, const int32_t *, const int32_t *,
    const int32_t *, uint16_t, uint16_t, uint16_t, uint16_t, uint16_t,
    uint16_t, uint16_t, uint16_t *, uint16_t *, uint16_t *, uint32_t *);

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
    size_t resampler_hook;
    NokiaResample resample;
    uint64_t resampler_native_calls, resampler_fallback_calls;
    size_t frontend_hook;
    uint32_t frontend_count, frontend_table, frontend_values;
    uint64_t frontend_native_calls, frontend_fallback_calls;
    size_t prosody_hook[2];
    uint64_t prosody_entry[2];
    uint64_t prosody_native_calls, prosody_fallback_calls;
    size_t heap_hook[4];
    uint32_t heap_next, heap_limit;
    uint64_t heap_native_calls[4], heap_fallback_calls[4];
} NokiaKlattBridge;

static NokiaKlattBridge bridge;

typedef struct {
    uint32_t address, size;
    uint8_t used;
} NokiaHeapBlock;

static NokiaHeapBlock *heap_blocks;
static size_t heap_count, heap_capacity;

static uint16_t load_u16(const uint8_t *p) {
    uint16_t value; memcpy(&value, p, sizeof(value)); return value;
}

static uint32_t load_u32(const uint8_t *p) {
    uint32_t value; memcpy(&value, p, sizeof(value)); return value;
}

static void store_u16(uint8_t *p, uint16_t value) {
    memcpy(p, &value, sizeof(value));
}

static void store_u32(uint8_t *p, uint32_t value) {
    memcpy(p, &value, sizeof(value));
}

static int read_reg(void *uc, int id, uint32_t *value) {
    return bridge.reg_read(uc, id, value) == 0;
}

static int rom_u32(uint32_t address, uint32_t *value) {
    uint64_t offset;
    if (address < bridge.rom_base) return 0;
    offset = (uint64_t)address - bridge.rom_base;
    if (offset + 4 > bridge.rom_size) return 0;
    *value = load_u32(bridge.rom + offset);
    return 1;
}

static int guest_read(void *uc, uint32_t address, void *data, size_t size) {
    return address && bridge.mem_read(uc, address, data, size) == 0;
}

static int guest_write(void *uc, uint32_t address, const void *data,
                       size_t size) {
    return address && bridge.mem_write(uc, address, data, size) == 0;
}

static int heap_reserve(size_t wanted) {
    NokiaHeapBlock *grown;
    size_t capacity = heap_capacity ? heap_capacity : 256;
    if (wanted <= heap_capacity) return 1;
    while (capacity < wanted) capacity *= 2;
    grown = (NokiaHeapBlock *)realloc(heap_blocks,
                                      capacity * sizeof(*heap_blocks));
    if (!grown) return 0;
    heap_blocks = grown;
    heap_capacity = capacity;
    return 1;
}

static int heap_add(uint32_t address, uint32_t size, int used) {
    if (!address || !size || !heap_reserve(heap_count + 1)) return 0;
    heap_blocks[heap_count].address = address;
    heap_blocks[heap_count].size = size;
    heap_blocks[heap_count].used = used != 0;
    ++heap_count;
    return 1;
}

static void heap_sort_merge(void) {
    size_t i, out;
    for (i = 1; i < heap_count; ++i) {
        NokiaHeapBlock value = heap_blocks[i];
        size_t j = i;
        while (j && heap_blocks[j - 1].address > value.address) {
            heap_blocks[j] = heap_blocks[j - 1];
            --j;
        }
        heap_blocks[j] = value;
    }
    out = 0;
    for (i = 0; i < heap_count; ++i) {
        if (out && !heap_blocks[out - 1].used && !heap_blocks[i].used &&
            heap_blocks[out - 1].address + heap_blocks[out - 1].size ==
                heap_blocks[i].address) {
            heap_blocks[out - 1].size += heap_blocks[i].size;
        } else {
            heap_blocks[out++] = heap_blocks[i];
        }
    }
    heap_count = out;
}

static int heap_zero(uint32_t address, uint32_t size) {
    uint8_t zeros[4096] = {0};
    uint32_t offset = 0, limit = size < 0x10000u ? size : 0x10000u;
    while (offset < limit) {
        uint32_t chunk = limit - offset;
        if (chunk > sizeof(zeros)) chunk = sizeof(zeros);
        if (bridge.mem_write(bridge.uc, address + offset, zeros, chunk) != 0)
            return 0;
        offset += chunk;
    }
    return 1;
}

static uint32_t heap_alloc(uint32_t requested) {
    uint32_t size, address;
    size_t i;
    if (requested > 0x800000u) return 0;
    size = requested < 4 ? 4 : requested;
    if (size > 0xfffffff0u) return 0;
    size = (size + 15u) & ~15u;
    for (i = 0; i < heap_count; ++i) {
        if (heap_blocks[i].used || heap_blocks[i].size < size) continue;
        address = heap_blocks[i].address;
        if (heap_blocks[i].size == size) {
            heap_blocks[i].used = 1;
        } else {
            NokiaHeapBlock remainder;
            if (!heap_reserve(heap_count + 1)) return 0;
            remainder.address = address + size;
            remainder.size = heap_blocks[i].size - size;
            remainder.used = 0;
            heap_blocks[i].size = size;
            heap_blocks[i].used = 1;
            memmove(&heap_blocks[i + 2], &heap_blocks[i + 1],
                    (heap_count - i - 1) * sizeof(*heap_blocks));
            heap_blocks[i + 1] = remainder;
            ++heap_count;
        }
        if (!heap_zero(address, size)) return 0;
        return address;
    }
    if (bridge.heap_next > bridge.heap_limit ||
        size > bridge.heap_limit - bridge.heap_next) return 0;
    address = bridge.heap_next;
    if (!heap_add(address, size, 1)) return 0;
    bridge.heap_next += size;
    if (!heap_zero(address, size)) return 0;
    return address;
}

static uint32_t heap_size(uint32_t address) {
    size_t i;
    for (i = 0; i < heap_count; ++i)
        if (heap_blocks[i].used && heap_blocks[i].address == address)
            return heap_blocks[i].size;
    return 0;
}

static void heap_free(uint32_t address) {
    size_t i;
    for (i = 0; i < heap_count; ++i) {
        if (!heap_blocks[i].used || heap_blocks[i].address != address) continue;
        heap_blocks[i].used = 0;
        heap_sort_merge();
        return;
    }
}

static uint32_t heap_realloc(uint32_t address, uint32_t requested) {
    uint32_t old_size = heap_size(address), result, copy_size, offset = 0;
    uint8_t buffer[4096];
    if (address && requested <= old_size) return address;
    result = heap_alloc(requested);
    if (result && address) {
        copy_size = old_size < requested ? old_size : requested;
        while (offset < copy_size) {
            uint32_t chunk = copy_size - offset;
            if (chunk > sizeof(buffer)) chunk = sizeof(buffer);
            if (bridge.mem_read(bridge.uc, address + offset, buffer, chunk) ||
                bridge.mem_write(bridge.uc, result + offset, buffer, chunk))
                return 0;
            offset += chunk;
        }
        heap_free(address);
    }
    return result;
}

static void heap_hook(void *uc, uint64_t address, size_t size, void *user) {
    uint32_t r1, r2, lr, result = 0;
    unsigned index = (unsigned)(uintptr_t)user;
    (void)address; (void)size;
    if (index > 3 || !read_reg(uc, bridge.r1, &r1) ||
        !read_reg(uc, bridge.r2, &r2) || !read_reg(uc, bridge.lr, &lr)) {
        if (index < 4) bridge.heap_fallback_calls[index]++;
        return;
    }
    if (index == 0) result = heap_alloc(r1);
    else if (index == 1) heap_free(r1);
    else if (index == 2) result = heap_realloc(r1, r2);
    else result = heap_size(r1);
    bridge.reg_write(uc, bridge.r0, &result);
    bridge.reg_write(uc, bridge.pc, &lr);
    bridge.heap_native_calls[index]++;
}

static int16_t add_i16(int16_t a, int32_t b) {
    return (int16_t)((uint16_t)a + (uint16_t)b);
}

/* Two 5320 duration-field helpers (guest 0x830ffaa2/0x830ffafe). */
static void prosody_duration_hook(void *uc, uint64_t address, size_t size,
                                  void *user) {
    uint32_t r0, r1, r2, lr, durations_address, thresholds_address;
    uint8_t object[0x24];
    uint16_t *durations = NULL;
    int16_t *thresholds = NULL;
    uint32_t duration_count, threshold_count, i, index;
    int16_t sum = 0;
    int ok = 0;
    (void)size; (void)user;
    if (!read_reg(uc, bridge.r0, &r0) ||
        !read_reg(uc, bridge.r1, &r1) ||
        !read_reg(uc, bridge.r2, &r2) ||
        !read_reg(uc, bridge.lr, &lr) ||
        !guest_read(uc, r0, object, sizeof(object))) goto done;
    durations_address = load_u32(object + 0x0c);
    thresholds_address = load_u32(object +
        (address == bridge.prosody_entry[1] ? 0x14 : 0x20));
    threshold_count = load_u16(object +
        (address == bridge.prosody_entry[1] ? 0x02 : 0x04));
    duration_count = r1 + (address == bridge.prosody_entry[1]);
    if (duration_count > 32768 || threshold_count > 32768 ||
        !durations_address || !thresholds_address) goto done;
    durations = (uint16_t *)malloc((duration_count ? duration_count : 1) * 2);
    thresholds = (int16_t *)malloc((threshold_count ? threshold_count : 1) * 2);
    if (!durations || !thresholds ||
        (duration_count && !guest_read(uc, durations_address, durations,
                                       duration_count * 2)) ||
        (threshold_count && !guest_read(uc, thresholds_address, thresholds,
                                        threshold_count * 2))) goto done;
    for (i = 0; i < r1; ++i) sum = add_i16(sum, durations[i]);
    index = 0;
    { int16_t boundary = 0;
      while (boundary < sum && index < threshold_count)
          boundary = thresholds[index++]; }
    if (address == bridge.prosody_entry[0]) {
        /* nokia_duration_shift: add r2 from the selected boundary onward. */
        if (index < threshold_count) {
            if (index) --index;
            if (!index) {
                int16_t first = add_i16(thresholds[0], (int32_t)r2);
                if (first >= 0) { thresholds[0] = first; index = 1; }
            }
            for (i = index; i < threshold_count; ++i)
                thresholds[i] = add_i16(thresholds[i], (int32_t)r2);
        }
        if (threshold_count && !guest_write(uc, thresholds_address, thresholds,
                                             threshold_count * 2)) goto done;
        bridge.reg_write(uc, bridge.r1, &threshold_count);
        bridge.reg_write(uc, bridge.r3, &threshold_count);
    } else {
        /* nokia_duration_spread: distribute r2 across the next boundaries. */
        uint32_t span = 0;
        uint32_t result = (uint32_t)(int32_t)sum;
        int16_t step = 0;
        if (index < threshold_count) {
            if (index) --index;
            while (index + span < threshold_count &&
                   thresholds[index + span] <
                       add_i16(sum, durations[r1]))
                ++span;
            if (span) step = (int16_t)((int32_t)r2 / (int32_t)span);
            for (i = 0; i < span; ++i)
                thresholds[index + i] = add_i16(
                    thresholds[index + i], (int32_t)(i + 1) * step);
            index += span;
            if (!index && threshold_count) {
                int16_t first = add_i16(thresholds[0], (int32_t)r2);
                if (first >= 0) { thresholds[0] = first; index = 1; }
            }
            for (i = index; i < threshold_count; ++i)
                thresholds[i] = add_i16(thresholds[i], (int32_t)r2);
            result = threshold_count;
        }
        if (threshold_count && !guest_write(uc, thresholds_address, thresholds,
                                             threshold_count * 2)) goto done;
        r0 = result;
        { uint32_t original_r0;
          if (!read_reg(uc, bridge.r0, &original_r0)) goto done;
          bridge.reg_write(uc, bridge.r1, &original_r0); }
        r1 = duration_count - 1;
        bridge.reg_write(uc, bridge.r2, &r1);
        bridge.reg_write(uc, bridge.r3, &r2);
        bridge.reg_write(uc, bridge.r0, &r0);
    }
    bridge.reg_write(uc, bridge.pc, &lr);
    bridge.prosody_native_calls++;
    ok = 1;
done:
    free(durations); free(thresholds);
    if (!ok) bridge.prosody_fallback_calls++;
}

/* Bit-exact 5320 frontend Unicode/range lookup (guest 0x830ee500). */
static void frontend_lookup_hook(void *uc, uint64_t address, size_t size,
                                 void *user) {
    uint32_t key, out_class, out_code, lr, lo = 0, hi, a, b, mid, base;
    uint32_t result = 0;
    int found = 0;
    (void)address; (void)size; (void)user;
    if (!read_reg(uc, bridge.r0, &key) ||
        !read_reg(uc, bridge.r1, &out_class) ||
        !read_reg(uc, bridge.r2, &out_code) ||
        !read_reg(uc, bridge.lr, &lr)) goto fallback;
    hi = bridge.frontend_count;
    while (hi > lo) {
        mid = (lo + hi) >> 1;
        if (!rom_u32(bridge.frontend_table + mid * 8, &a) ||
            !rom_u32(bridge.frontend_table + mid * 8 + 4, &b))
            goto fallback;
        base = a & 0x001fffffu;
        if (base == key ||
            (base < key && ((a >> 20) & 0xfu) &&
             base + (b & 0xffffu) >= key)) {
            uint32_t index = b >> 26;
            if (!rom_u32(bridge.frontend_values + index * 4, &result))
                goto fallback;
            a >>= 24;
            if (bridge.mem_write(uc, out_class, &index, 4) ||
                bridge.mem_write(uc, out_code, &a, 4)) goto fallback;
            found = 1;
            break;
        }
        if (base > key) hi = mid; else lo = mid + 1;
    }
    if (!found) {
        a = 2; b = 9;
        if (bridge.mem_write(uc, out_class, &a, 4) ||
            bridge.mem_write(uc, out_code, &b, 4)) goto fallback;
    }
    bridge.reg_write(uc, bridge.r0, &result);
    bridge.reg_write(uc, bridge.pc, &lr);
    bridge.frontend_native_calls++;
    return;
fallback:
    bridge.frontend_fallback_calls++;
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

static void resampler_hook(void *uc, uint64_t address, size_t size, void *user) {
    uint32_t input_address, output_address, count, state_address, lr;
    uint8_t fields[0x34];
    uint32_t ring_address[3], coefficient_address[3], phase;
    uint16_t length[3], repeat[3], divisor, position[3];
    int16_t *input = NULL, *output = NULL;
    int32_t *ring[3] = {NULL, NULL, NULL};
    int32_t *coefficient[3] = {NULL, NULL, NULL};
    size_t coefficient_count[3], capacity;
    int32_t produced;
    int ok = 0;
    (void)address; (void)size; (void)user;
    if (!bridge.resample ||
        !read_reg(uc, bridge.r0, &input_address) ||
        !read_reg(uc, bridge.r1, &output_address) ||
        !read_reg(uc, bridge.r2, &count) ||
        !read_reg(uc, bridge.r3, &state_address) ||
        !read_reg(uc, bridge.lr, &lr) || count > 65536 ||
        bridge.mem_read(uc, state_address, fields, sizeof(fields)))
        goto done;
    if (load_u16(fields + 2) == 1) goto done;
    for (int i = 0; i < 3; ++i) {
        ring_address[i] = load_u32(fields + 4 + i * 4);
        coefficient_address[i] = load_u32(fields + 16 + i * 4);
        length[i] = load_u16(fields + 28 + i * 2);
        repeat[i] = load_u16(fields + 34 + i * 2);
        position[i] = load_u16(fields + 42 + i * 2);
        if (!ring_address[i] || !coefficient_address[i] || !length[i])
            goto done;
    }
    divisor = load_u16(fields + 40);
    phase = load_u32(fields + 48);
    if (!divisor) goto done;
    coefficient_count[0] = (length[0] + 1) / 2;
    coefficient_count[1] = length[1] / 2;
    coefficient_count[2] = (length[2] + 1) / 2;
    capacity = (size_t)count;
    for (int i = 0; i < 3; ++i)
        capacity *= repeat[i] ? repeat[i] : 1;
    capacity += 4;
    input = (int16_t *)malloc((size_t)count * 2);
    output = (int16_t *)malloc(capacity * 2);
    if ((!input && count) || !output) goto done;
    if (count && bridge.mem_read(uc, input_address, input, (size_t)count * 2))
        goto done;
    for (int i = 0; i < 3; ++i) {
        ring[i] = (int32_t *)malloc((size_t)length[i] * 4);
        coefficient[i] = (int32_t *)malloc(coefficient_count[i] * 4);
        if (!ring[i] || !coefficient[i] ||
            bridge.mem_read(uc, ring_address[i], ring[i], (size_t)length[i] * 4) ||
            bridge.mem_read(uc, coefficient_address[i], coefficient[i],
                            coefficient_count[i] * 4))
            goto done;
    }
    produced = bridge.resample(
        input, (int32_t)count, output, (int32_t)capacity,
        ring[0], ring[1], ring[2], coefficient[0], coefficient[1],
        coefficient[2], length[0], length[1], length[2], repeat[0],
        repeat[1], repeat[2], divisor, &position[0], &position[1],
        &position[2], &phase);
    if (produced < 0 || (size_t)produced > capacity) goto done;
    for (int i = 0; i < 3; ++i)
        if (bridge.mem_write(uc, ring_address[i], ring[i],
                             (size_t)length[i] * 4)) goto done;
    store_u16(fields + 42, position[0]);
    store_u16(fields + 44, position[1]);
    store_u16(fields + 46, position[2]);
    store_u32(fields + 48, phase);
    if (bridge.mem_write(uc, state_address + 42, fields + 42, 10) ||
        (produced && bridge.mem_write(uc, output_address, output,
                                     (size_t)produced * 2)))
        goto done;
    bridge.reg_write(uc, bridge.pc, &lr);
    bridge.resampler_native_calls++;
    ok = 1;
done:
    free(input); free(output);
    for (int i = 0; i < 3; ++i) { free(ring[i]); free(coefficient[i]); }
    if (!ok) bridge.resampler_fallback_calls++;
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

NOKIA_EXPORT int nokia_install_resampler_hook(uint64_t entry,
                                               void *resample) {
    if (!bridge.uc || !bridge.hook_add || !resample) return 0;
    bridge.resample = (NokiaResample)resample;
    return bridge.hook_add(bridge.uc, &bridge.resampler_hook, 4,
                           (void *)resampler_hook, NULL, entry, entry) == 0;
}

NOKIA_EXPORT int nokia_install_frontend_lookup_hook(
    uint64_t entry, uint32_t count, uint32_t table, uint32_t values) {
    if (!bridge.uc || !bridge.hook_add || !count || !table || !values)
        return 0;
    bridge.frontend_count = count;
    bridge.frontend_table = table;
    bridge.frontend_values = values;
    return bridge.hook_add(bridge.uc, &bridge.frontend_hook, 4,
                           (void *)frontend_lookup_hook, NULL,
                           entry, entry) == 0;
}

NOKIA_EXPORT int nokia_install_prosody_duration_hooks(uint64_t shift_entry,
                                                       uint64_t spread_entry) {
    if (!bridge.uc || !bridge.hook_add || !shift_entry || !spread_entry)
        return 0;
    bridge.prosody_entry[0] = shift_entry;
    bridge.prosody_entry[1] = spread_entry;
    if (bridge.hook_add(bridge.uc, &bridge.prosody_hook[0], 4,
                        (void *)prosody_duration_hook, NULL,
                        shift_entry, shift_entry) != 0) return 0;
    if (bridge.hook_add(bridge.uc, &bridge.prosody_hook[1], 4,
                        (void *)prosody_duration_hook, NULL,
                        spread_entry, spread_entry) != 0) {
        bridge.hook_del(bridge.uc, bridge.prosody_hook[0]);
        bridge.prosody_hook[0] = 0;
        return 0;
    }
    return 1;
}

NOKIA_EXPORT int nokia_heap_begin(uint32_t next, uint32_t limit) {
    heap_count = 0;
    bridge.heap_next = next;
    bridge.heap_limit = limit;
    memset(bridge.heap_native_calls, 0, sizeof(bridge.heap_native_calls));
    memset(bridge.heap_fallback_calls, 0, sizeof(bridge.heap_fallback_calls));
    return bridge.uc && next && next <= limit;
}

NOKIA_EXPORT int nokia_heap_import(uint32_t address, uint32_t size,
                                   int used) {
    return heap_add(address, size, used);
}

NOKIA_EXPORT int nokia_install_heap_hooks(uint64_t trap_base,
                                           uint64_t alloc_entry) {
    unsigned i;
    if (!bridge.uc || !bridge.hook_add || !trap_base) return 0;
    heap_sort_merge();
    for (i = 0; i < 4; ++i) {
        uint64_t entry = i ? trap_base + i * 4 : alloc_entry;
        uint16_t instruction;
        /* Alloc already ran while EPOC bootstrapped, so Unicorn may have a
           translated block for this two-byte SVC. Rewriting it unchanged
           invalidates that block and makes the newly added code hook visible. */
        if (bridge.mem_read(bridge.uc, entry, &instruction,
                            sizeof(instruction)) != 0 ||
            bridge.mem_write(bridge.uc, entry, &instruction,
                             sizeof(instruction)) != 0)
            return 0;
        if (bridge.hook_add(bridge.uc, &bridge.heap_hook[i], 4,
                            (void *)heap_hook, (void *)(uintptr_t)i,
                            entry, entry) != 0) {
            while (i) {
                --i;
                bridge.hook_del(bridge.uc, bridge.heap_hook[i]);
                bridge.heap_hook[i] = 0;
            }
            return 0;
        }
    }
    return 1;
}

NOKIA_EXPORT uint32_t nokia_heap_alloc(uint32_t size) {
    return heap_alloc(size);
}

NOKIA_EXPORT void nokia_heap_free(uint32_t address) {
    heap_free(address);
}

NOKIA_EXPORT uint32_t nokia_heap_position(void) {
    return bridge.heap_next;
}

NOKIA_EXPORT void nokia_heap_hook_counters(uint64_t out[8]) {
    unsigned i;
    for (i = 0; i < 4; ++i) {
        out[i] = bridge.heap_native_calls[i];
        out[4 + i] = bridge.heap_fallback_calls[i];
    }
}

NOKIA_EXPORT void nokia_frontend_lookup_hook_counters(uint64_t out[2]) {
    out[0] = bridge.frontend_native_calls;
    out[1] = bridge.frontend_fallback_calls;
}

NOKIA_EXPORT void nokia_prosody_duration_hook_counters(uint64_t out[2]) {
    out[0] = bridge.prosody_native_calls;
    out[1] = bridge.prosody_fallback_calls;
}

NOKIA_EXPORT void nokia_resampler_hook_counters(uint64_t out[2]) {
    out[0] = bridge.resampler_native_calls;
    out[1] = bridge.resampler_fallback_calls;
}

NOKIA_EXPORT void nokia_remove_klatt_hook(void) {
    if (bridge.uc && bridge.hook) bridge.hook_del(bridge.uc, bridge.hook);
    if (bridge.uc && bridge.resampler_hook)
        bridge.hook_del(bridge.uc, bridge.resampler_hook);
    if (bridge.uc && bridge.frontend_hook)
        bridge.hook_del(bridge.uc, bridge.frontend_hook);
    for (int i = 0; i < 2; ++i)
        if (bridge.uc && bridge.prosody_hook[i])
            bridge.hook_del(bridge.uc, bridge.prosody_hook[i]);
    for (int i = 0; i < 4; ++i)
        if (bridge.uc && bridge.heap_hook[i])
            bridge.hook_del(bridge.uc, bridge.heap_hook[i]);
    bridge.hook = 0;
    bridge.resampler_hook = 0;
    bridge.frontend_hook = 0;
    bridge.prosody_hook[0] = bridge.prosody_hook[1] = 0;
    memset(bridge.heap_hook, 0, sizeof(bridge.heap_hook));
    free(heap_blocks);
    heap_blocks = NULL;
    heap_count = heap_capacity = 0;
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
