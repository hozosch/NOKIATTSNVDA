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
typedef int (*UcCtl)(void *, uint32_t, ...);
typedef int32_t (*NokiaResample)(
    const int16_t *, int32_t, int16_t *, int32_t,
    int32_t *, int32_t *, int32_t *, const int32_t *, const int32_t *,
    const int32_t *, uint16_t, uint16_t, uint16_t, uint16_t, uint16_t,
    uint16_t, uint16_t, uint16_t *, uint16_t *, uint16_t *, uint32_t *);

extern int nokia_klatt_generate_aot(
    int16_t *, int32_t *, uint8_t[122], uint8_t[564], uint32_t,
    const uint8_t *, uint32_t, size_t, uint32_t[5]);

typedef struct {
    void *context;
    uint32_t (*alloc)(void *, uint32_t);
    void (*free)(void *, uint32_t);
    uint32_t (*realloc)(void *, uint32_t, uint32_t);
    uint32_t (*length)(void *, uint32_t);
} NokiaFrontendHost;
extern int nokia_frontend_aot(
    uint8_t *, uint8_t *, uint8_t *, uint8_t *, uint8_t *,
    const uint8_t *, uint32_t, size_t, uint32_t[17], uint32_t,
    const NokiaFrontendHost *);
extern uint32_t nokia_frontend_resume_count(void);
extern uint32_t nokia_frontend_resume_address(uint32_t);
extern uint32_t nokia_frontend_dirty_mask_value(void);

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
    UcCtl ctl;
    uint64_t native_calls, fallback_calls;
    size_t resampler_hook;
    NokiaResample resample;
    uint64_t resampler_native_calls, resampler_fallback_calls;
    size_t frontend_hook;
    uint32_t frontend_count, frontend_table, frontend_values;
    uint64_t frontend_native_calls, frontend_fallback_calls;
    size_t search_hook;
    uint32_t search_getter, search_compare_u16;
    uint32_t search_compare_length, search_compare_lexical;
    uint64_t search_native_calls, search_fallback_calls;
    size_t partition_hook;
    uint64_t partition_native_calls, partition_fallback_calls;
    size_t prosody_hook[2];
    uint64_t prosody_entry[2];
    uint64_t prosody_native_calls, prosody_fallback_calls;
    uint32_t prosody_object;
    size_t heap_hook[4];
    uint32_t heap_next, heap_limit;
    uint64_t heap_native_calls[4], heap_fallback_calls[4];
    size_t executive_hook[3];
    uint32_t thread_data;
    uint64_t executive_native_calls[3], executive_fallback_calls[3];
    size_t full_frontend_hook, full_frontend_return_hook;
    size_t *full_resume_hooks;
    uint32_t *full_resume_addresses, full_resume_hook_count;
    int full_frontend_regs[17];
    uint8_t *full_heap, *full_vtable, *full_traps, *full_pool, *full_stack;
    uint32_t full_return_address, full_callback_return, full_expected_resume;
    uint8_t full_active, full_yielded, full_static_initialized;
    uint64_t full_frontend_native_calls, full_frontend_fallback_calls;
    double pitch_factor;
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

static uint8_t *full_pool_pointer(uint32_t address, uint32_t size) {
    uint64_t offset;
    if (address < 0x53000000u) return NULL;
    offset = (uint64_t)address - 0x53000000u;
    if (offset + size > 0x800000u) return NULL;
    return bridge.full_pool + offset;
}

static uint32_t full_alloc(void *context, uint32_t requested) {
    uint32_t address = heap_alloc(requested);
    uint32_t size = requested < 4 ? 4 : requested;
    uint8_t *pointer;
    (void)context;
    size = (size + 15u) & ~15u;
    pointer = full_pool_pointer(address, size);
    if (pointer) memset(pointer, 0, size);
    return pointer ? address : 0;
}

static void full_free(void *context, uint32_t address) {
    (void)context;
    heap_free(address);
}

static uint32_t full_realloc(void *context, uint32_t address,
                             uint32_t requested) {
    uint32_t old_size = heap_size(address), result, copy_size;
    uint8_t *old_pointer, *new_pointer;
    (void)context;
    if (address && requested <= old_size) return address;
    result = full_alloc(NULL, requested);
    old_pointer = full_pool_pointer(address, old_size);
    new_pointer = full_pool_pointer(result, requested);
    if (!result || (address && (!old_pointer || !new_pointer))) return 0;
    copy_size = old_size < requested ? old_size : requested;
    if (copy_size) memmove(new_pointer, old_pointer, copy_size);
    if (address) heap_free(address);
    return result;
}

static uint32_t full_length(void *context, uint32_t address) {
    (void)context;
    return heap_size(address);
}

static const NokiaFrontendHost full_host = {
    NULL, full_alloc, full_free, full_realloc, full_length
};

static void full_frontend_return_hook(void *uc, uint64_t address, size_t size,
                                      void *user);

static void full_remove_resume_hooks(void) {
    uint32_t i;
    if (bridge.uc)
        for (i = 0; i < bridge.full_resume_hook_count; ++i)
            if (bridge.full_resume_hooks[i])
                bridge.hook_del(bridge.uc, bridge.full_resume_hooks[i]);
    free(bridge.full_resume_hooks);
    free(bridge.full_resume_addresses);
    bridge.full_resume_hooks = NULL;
    bridge.full_resume_addresses = NULL;
    bridge.full_resume_hook_count = 0;
}

static int full_prepare_resume(uint32_t pc, uint32_t lr) {
    uint32_t resume = lr & ~1u;
    /* The scheduler trap already has a permanent return hook. */
    if ((pc & ~1u) == 0x52000224u ||
        resume == bridge.full_callback_return) {
        bridge.full_expected_resume = bridge.full_callback_return;
        return 1;
    }
    if (!resume) return 0;
    for (uint32_t i = 0; i < bridge.full_resume_hook_count; ++i)
        if (bridge.full_resume_addresses[i] == resume) {
            bridge.full_expected_resume = resume;
            return 1;
        }
    return 0;
}

static int full_read_registers(void *uc, uint32_t registers[17]) {
    unsigned i;
    for (i = 0; i < 17; ++i)
        if (bridge.reg_read(uc, bridge.full_frontend_regs[i],
                            &registers[i]) != 0) return 0;
    return 1;
}

static int full_write_registers(void *uc, const uint32_t registers[17]) {
    unsigned i;
    for (i = 0; i < 17; ++i)
        if (bridge.reg_write(uc, bridge.full_frontend_regs[i],
                             &registers[i]) != 0) return 0;
    return 1;
}

static int full_read_memory(void *uc, int initial) {
    uint32_t pool_size = bridge.heap_next > 0x53000000u
        ? bridge.heap_next - 0x53000000u : 0;
    if (pool_size > 0x800000u) return 0;
    if (initial && !bridge.full_static_initialized &&
        (bridge.mem_read(uc, 0x50000000u, bridge.full_heap, 0x100000u) ||
         bridge.mem_read(uc, 0x51000000u, bridge.full_vtable, 0x1000u) ||
         bridge.mem_read(uc, 0x52000000u, bridge.full_traps, 0x10000u)))
        return 0;
    if (initial) bridge.full_static_initialized = 1;
    if ((pool_size && bridge.mem_read(uc, 0x53000000u, bridge.full_pool,
                                      pool_size)) ||
        bridge.mem_read(uc, 0x600f0000u, bridge.full_stack + 0xf0000u,
                        0x10000u)) return 0;
    return 1;
}

static int full_write_memory(void *uc, int complete) {
    uint32_t pool_size = bridge.heap_next > 0x53000000u
        ? bridge.heap_next - 0x53000000u : 0;
    uint32_t dirty = nokia_frontend_dirty_mask_value();
    (void)complete;
    if (pool_size > 0x800000u) return 0;
    if (((dirty & 1u) && bridge.mem_write(uc, 0x50000000u,
                                          bridge.full_heap, 0x100000u)) ||
        ((dirty & 2u) && bridge.mem_write(uc, 0x51000000u,
                                          bridge.full_vtable, 0x1000u)) ||
        ((dirty & 4u) && bridge.mem_write(uc, 0x52000000u,
                                          bridge.full_traps, 0x10000u)) ||
        ((dirty & 8u) && pool_size && bridge.mem_write(
            uc, 0x53000000u, bridge.full_pool, pool_size)) ||
        ((dirty & 16u) && bridge.mem_write(
            uc, 0x600f0000u, bridge.full_stack + 0xf0000u, 0x10000u)))
        return 0;
    return 1;
}

static int full_drive(void *uc, uint32_t registers[17]) {
    int result = nokia_frontend_aot(
        bridge.full_heap, bridge.full_vtable, bridge.full_traps,
        bridge.full_pool, bridge.full_stack, bridge.rom, bridge.rom_base,
        bridge.rom_size, registers, bridge.full_return_address, &full_host);
    if (result == 2) {
        bridge.full_yielded = 1;
        return full_prepare_resume(registers[15], registers[14]) &&
               full_write_memory(uc, 0) &&
               full_write_registers(uc, registers);
    }
    if (result == 1) {
        if (!full_write_memory(uc, 1) ||
            !full_write_registers(uc, registers))
            return 0;
        bridge.full_frontend_native_calls++;
        bridge.full_active = bridge.full_yielded = 0;
        bridge.full_expected_resume = 0;
        return 1;
    }
    bridge.full_frontend_fallback_calls++;
    bridge.full_active = bridge.full_yielded = 0;
    bridge.full_static_initialized = 0;
    return 0;
}

static void full_frontend_entry_hook(void *uc, uint64_t address, size_t size,
                                     void *user) {
    uint32_t registers[17];
    (void)address; (void)size; (void)user;
    if (bridge.full_active || !full_read_registers(uc, registers) ||
        !full_read_memory(uc, 1)) return;
    bridge.full_active = 1;
    bridge.full_yielded = 0;
    bridge.full_return_address = registers[14] & ~1u;
    if (!full_drive(uc, registers) && bridge.full_yielded)
        bridge.full_frontend_fallback_calls++;
}

static void full_frontend_return_hook(void *uc, uint64_t address, size_t size,
                                      void *user) {
    uint32_t registers[17];
    (void)address; (void)size; (void)user;
    if (!bridge.full_active || !bridge.full_yielded ||
        ((uint32_t)address & ~1u) != bridge.full_expected_resume) return;
    bridge.full_yielded = 0;
    if (!full_read_registers(uc, registers)) {
        bridge.full_frontend_fallback_calls++;
        bridge.full_active = 0;
        return;
    }
    if (!full_read_memory(uc, 0) ||
        !full_drive(uc, registers)) {
        bridge.full_frontend_fallback_calls++;
        bridge.full_active = 0;
    }
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

static void executive_hook(void *uc, uint64_t address, size_t size,
                           void *user) {
    static const uint32_t offsets[3] = {0, 8, 4};
    uint32_t result, previous, lr, next = (uint32_t)address + 4;
    unsigned index = (unsigned)(uintptr_t)user;
    (void)size;
    if (index > 2 || !bridge.thread_data ||
        bridge.mem_read(uc, bridge.thread_data + offsets[index],
                        &result, sizeof(result)) != 0) {
        if (index < 3) bridge.executive_fallback_calls[index]++;
        return;
    }
    /* Symbian 9.1 executive tables save LR in IP and place consecutive SVCs
       directly beside each other; later EKA2 tables use one bx lr per SVC.
       Match Epoc._stub_returns_to_lr instead of falling into the next slot. */
    if (bridge.mem_read(uc, address - 4, &previous, sizeof(previous)) == 0 &&
        previous == 0xe1a0c00eu && read_reg(uc, bridge.lr, &lr))
        next = lr;
    bridge.reg_write(uc, bridge.r0, &result);
    bridge.reg_write(uc, bridge.pc, &next);
    bridge.executive_native_calls[index]++;
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
    bridge.prosody_object = r0;
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

/* Native form of the 5320's RArray binary-search comparison adapter.
   The guest implementation crosses from euser into a virtual getter and then
   into one of three frontend comparators for every search step.  Keeping the
   complete adapter here removes thousands of tiny ARM/module transitions
   before the first audio buffer without changing the search algorithm. */
static int compare_descriptor(void *uc, uint32_t left, uint32_t right,
                              int lexical, int32_t *result) {
    uint32_t left_data, right_data;
    uint16_t left_length, right_length, a, b;
    uint32_t i, count;
    if (!guest_read(uc, left, &left_data, 4) ||
        !guest_read(uc, right, &right_data, 4) ||
        !guest_read(uc, left + 4, &left_length, 2) ||
        !guest_read(uc, right + 4, &right_length, 2)) return 0;
    if (!lexical && left_length != right_length) {
        *result = (int32_t)left_length - (int32_t)right_length;
        return 1;
    }
    count = left_length < right_length ? left_length : right_length;
    for (i = 0; i < count; ++i) {
        if (!guest_read(uc, left_data + i * 2, &a, 2) ||
            !guest_read(uc, right_data + i * 2, &b, 2)) return 0;
        if (a != b) {
            *result = (int32_t)a - (int32_t)b;
            return 1;
        }
    }
    *result = (int32_t)left_length - (int32_t)right_length;
    return 1;
}

static int search_compare(void *uc, uint32_t object, uint32_t key_index,
                          uint32_t item_index, int32_t *result) {
    uint32_t vtable, getter, comparator;
    uint32_t element_size, base, key_pointer, left, right;
    uint16_t a, b;
    if (!guest_read(uc, object, &vtable, 4) ||
        !guest_read(uc, vtable + 4, &getter, 4) ||
        !guest_read(uc, object + 8, &element_size, 4) ||
        !guest_read(uc, object + 16, &base, 4) ||
        !guest_read(uc, object + 20, &key_pointer, 4) ||
        !guest_read(uc, object + 24, &comparator, 4) ||
        (getter & ~1u) != bridge.search_getter || !element_size) return 0;
    left = base + key_index * element_size;
    right = item_index == UINT32_MAX
        ? key_pointer : base + item_index * element_size;
    comparator &= ~1u;
    if (comparator == bridge.search_compare_u16 ||
        comparator == bridge.search_compare_u16 + 8) {
        if (!guest_read(uc, left, &a, 2) || !guest_read(uc, right, &b, 2))
            return 0;
        *result = (int32_t)a - (int32_t)b;
    } else if (comparator == bridge.search_compare_length) {
        if (!compare_descriptor(uc, left, right, 0, result)) return 0;
    } else if (comparator == bridge.search_compare_lexical) {
        if (!compare_descriptor(uc, left, right, 1, result)) return 0;
    } else return 0;
    return 1;
}

static void search_adapter_hook(void *uc, uint64_t address, size_t size,
                                void *user) {
    uint32_t object, key_index, item_index, lr;
    int32_t result;
    (void)address; (void)size; (void)user;
    if (!read_reg(uc, bridge.r0, &object) ||
        !read_reg(uc, bridge.r1, &key_index) ||
        !read_reg(uc, bridge.r2, &item_index) ||
        !read_reg(uc, bridge.lr, &lr) ||
        !search_compare(uc, object, key_index, item_index, &result))
        goto fallback;
    bridge.reg_write(uc, bridge.r0, &result);
    bridge.reg_write(uc, bridge.pc, &lr);
    bridge.search_native_calls++;
    return;
fallback:
    bridge.search_fallback_calls++;
}

static int swap_items(void *uc, uint32_t object, uint32_t first,
                      uint32_t second, uint8_t *a, uint8_t *b,
                      uint32_t capacity) {
    uint32_t base, element_size;
    if (!guest_read(uc, object + 4, &base, 4) ||
        !guest_read(uc, object + 8, &element_size, 4) ||
        !element_size || element_size > capacity) return 0;
    first = base + first * element_size;
    second = base + second * element_size;
    if (!guest_read(uc, first, a, element_size) ||
        !guest_read(uc, second, b, element_size) ||
        !guest_write(uc, first, b, element_size) ||
        !guest_write(uc, second, a, element_size)) return 0;
    return 1;
}

/* Symbian's non-recursive quicksort partition.  Its only callbacks in these
   builds are the verified adapter above and the byte-array swap adapter. */
static void partition_hook(void *uc, uint64_t address, size_t size,
                           void *user) {
    uint32_t count, low, compare_object, swap_object, lr, element_size;
    int32_t i, j, high, pivot, value;
    uint8_t *a = NULL, *b = NULL;
    (void)address; (void)size; (void)user;
    if (!read_reg(uc, bridge.r0, &count) ||
        !read_reg(uc, bridge.r1, &low) ||
        !read_reg(uc, bridge.r2, &compare_object) ||
        !read_reg(uc, bridge.r3, &swap_object) ||
        !read_reg(uc, bridge.lr, &lr) || !count || count > 0x100000 ||
        !guest_read(uc, swap_object + 8, &element_size, 4) ||
        !element_size || element_size > 0x10000 ||
        !search_compare(uc, compare_object, low, low, &value)) goto fallback;
    a = (uint8_t *)malloc(element_size);
    b = (uint8_t *)malloc(element_size);
    if (!a || !b) goto fallback;
    i = (int32_t)low - 1;
    high = i + (int32_t)count;
    pivot = (high + (int32_t)low) >> 1;
    if (!swap_items(uc, swap_object, (uint32_t)pivot, (uint32_t)high,
                    a, b, element_size)) goto fallback;
    j = high;
    do {
        do {
            ++i;
            if (!search_compare(uc, compare_object, (uint32_t)i,
                                (uint32_t)pivot, &value)) goto fallback;
        } while (value < 0);
        do {
            --j;
            if (!search_compare(uc, compare_object, (uint32_t)j,
                                (uint32_t)pivot,
                                &value)) goto fallback;
        } while (value > 0);
        if (i < j && !swap_items(uc, swap_object, (uint32_t)i,
                                (uint32_t)j, a, b, element_size))
            goto fallback;
    } while (i < j);
    if (!swap_items(uc, swap_object, (uint32_t)i, (uint32_t)high,
                    a, b, element_size)) goto fallback;
    bridge.reg_write(uc, bridge.r0, &i);
    bridge.reg_write(uc, bridge.pc, &lr);
    bridge.partition_native_calls++;
    free(a); free(b);
    return;
fallback:
    bridge.partition_fallback_calls++;
    free(a); free(b);
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
    /* The signed 16-bit value at +0x18 is Nokia's frame F0 in tenths of a
       hertz (roughly 950..1320 for DefaultMale and 1720..2290 for
       DefaultFemale).  Scaling it here changes the excitation period before
       waveform generation; it is not resampling or PCM pitch shifting. */
    if (bridge.pitch_factor > 0.0 && bridge.pitch_factor != 1.0) {
        int16_t f0;
        int32_t scaled;
        memcpy(&f0, parameters + 0x18, sizeof(f0));
        if (f0 > 0) {
            scaled = (int32_t)(f0 * bridge.pitch_factor + 0.5);
            if (scaled < 300) scaled = 300;
            if (scaled > 5000) scaled = 5000;
            f0 = (int16_t)scaled;
            memcpy(parameters + 0x18, &f0, sizeof(f0));
        }
    }
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
    void *mem_write, void *ctl) {
    memset(&bridge, 0, sizeof(bridge));
    bridge.pitch_factor = 1.0;
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
    bridge.ctl=(UcCtl)ctl;
    if (!bridge.hook_add || !bridge.hook_del || !bridge.reg_read ||
        !bridge.reg_write || !bridge.mem_read || !bridge.mem_write)
        return 0;
    return bridge.hook_add(uc, &bridge.hook, 4, (void *)klatt_hook, NULL,
                           entry, entry) == 0;
}

NOKIA_EXPORT void nokia_set_pitch_factor(double factor) {
    if (factor < 0.5) factor = 0.5;
    if (factor > 2.0) factor = 2.0;
    bridge.pitch_factor = factor;
}

NOKIA_EXPORT int nokia_install_resampler_hook(uint64_t entry,
                                               void *resample) {
    if (!bridge.uc || !bridge.hook_add || !resample) return 0;
    bridge.resample = (NokiaResample)resample;
    return bridge.hook_add(bridge.uc, &bridge.resampler_hook, 4,
                           (void *)resampler_hook, NULL, entry, entry) == 0;
}

NOKIA_EXPORT int nokia_install_full_frontend_hook(
    uint64_t entry, uint64_t callback_return, const int register_ids[17]) {
    unsigned i;
    uint32_t resume_count;
    if (!bridge.uc || !bridge.hook_add || !entry || !callback_return ||
        !register_ids || bridge.full_frontend_hook) return 0;
    bridge.full_heap = (uint8_t *)calloc(1, 0x100000u);
    bridge.full_vtable = (uint8_t *)calloc(1, 0x1000u);
    bridge.full_traps = (uint8_t *)calloc(1, 0x10000u);
    bridge.full_pool = (uint8_t *)calloc(1, 0x800000u);
    bridge.full_stack = (uint8_t *)calloc(1, 0x100000u);
    if (!bridge.full_heap || !bridge.full_vtable || !bridge.full_traps ||
        !bridge.full_pool || !bridge.full_stack) return 0;
    for (i = 0; i < 17; ++i) bridge.full_frontend_regs[i] = register_ids[i];
    bridge.full_callback_return = (uint32_t)callback_return & ~1u;
    resume_count = nokia_frontend_resume_count();
    bridge.full_resume_hooks = (size_t *)calloc(resume_count, sizeof(size_t));
    bridge.full_resume_addresses = (uint32_t *)calloc(
        resume_count, sizeof(uint32_t));
    if (!bridge.full_resume_hooks || !bridge.full_resume_addresses) return 0;
    bridge.full_resume_hook_count = resume_count;
    for (i = 0; i < resume_count; ++i) {
        uint32_t resume = nokia_frontend_resume_address(i) & ~1u;
        bridge.full_resume_addresses[i] = resume;
        if (!resume || resume == bridge.full_callback_return) continue;
        if (bridge.hook_add(bridge.uc, &bridge.full_resume_hooks[i], 4,
                            (void *)full_frontend_return_hook, NULL,
                            resume, resume) != 0)
            return 0;
        if (bridge.ctl && bridge.ctl(bridge.uc, 0x48000009u,
                                     (uint64_t)resume,
                                     (uint64_t)resume + 4u) != 0)
            return 0;
    }
    if (bridge.hook_add(bridge.uc, &bridge.full_frontend_hook, 4,
                        (void *)full_frontend_entry_hook, NULL,
                        entry, entry) != 0 ||
        bridge.hook_add(bridge.uc, &bridge.full_frontend_return_hook, 4,
                        (void *)full_frontend_return_hook, NULL,
                        callback_return, callback_return) != 0)
        return 0;
    bridge.full_frontend_native_calls = 0;
    bridge.full_frontend_fallback_calls = 0;
    bridge.full_static_initialized = 0;
    return 1;
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

NOKIA_EXPORT int nokia_install_search_adapter_hook(
    uint64_t entry, uint32_t getter, uint32_t compare_u16,
    uint32_t compare_length, uint32_t compare_lexical) {
    if (!bridge.uc || !bridge.hook_add || !entry || !getter || !compare_u16 ||
        !compare_length || !compare_lexical) return 0;
    bridge.search_getter = getter & ~1u;
    bridge.search_compare_u16 = compare_u16 & ~1u;
    bridge.search_compare_length = compare_length & ~1u;
    bridge.search_compare_lexical = compare_lexical & ~1u;
    bridge.search_native_calls = bridge.search_fallback_calls = 0;
    return bridge.hook_add(bridge.uc, &bridge.search_hook, 4,
                           (void *)search_adapter_hook, NULL,
                           entry, entry) == 0;
}

NOKIA_EXPORT int nokia_install_partition_hook(uint64_t entry) {
    if (!bridge.uc || !bridge.hook_add || !entry) return 0;
    bridge.partition_native_calls = bridge.partition_fallback_calls = 0;
    return bridge.hook_add(bridge.uc, &bridge.partition_hook, 4,
                           (void *)partition_hook, NULL,
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

NOKIA_EXPORT void nokia_begin_prosody_utterance(void) {
    bridge.prosody_object = 0;
}

static int pool_array(const uint8_t *pool, uint32_t pool_size,
                      uint32_t address, uint32_t count, const int16_t **out) {
    uint64_t offset;
    if (address < 0x53000000u) return 0;
    offset = (uint64_t)address - 0x53000000u;
    if (offset + (uint64_t)count * 2u > pool_size) return 0;
    *out = (const int16_t *)(pool + offset);
    return 1;
}

static int prosody_object_valid(const uint8_t *pool, uint32_t pool_size,
                                uint32_t address, uint32_t *score) {
    static const uint8_t pointer_offsets[6] = {8, 12, 16, 20, 28, 32};
    uint64_t offset;
    const uint8_t *object;
    const int16_t *phones, *durations, *pitch, *time1, *amplitude, *time2;
    uint32_t n0, n1, n2, pointers[6], i, maximum;
    if (address < 0x53000000u) return 0;
    offset = (uint64_t)address - 0x53000000u;
    if (offset + 0x28u > pool_size) return 0;
    object = pool + offset;
    n0 = load_u16(object); n1 = load_u16(object + 2);
    n2 = load_u16(object + 4);
    if (!n0 || n0 > 4096 || !n1 || n1 > 1024 || !n2 || n2 > 1024)
        return 0;
    for (i = 0; i < 6; ++i)
        pointers[i] = load_u32(object + pointer_offsets[i]);
    if (!pool_array(pool, pool_size, pointers[0], n0, &phones) ||
        !pool_array(pool, pool_size, pointers[1], n0, &durations) ||
        !pool_array(pool, pool_size, pointers[2], n1, &pitch) ||
        !pool_array(pool, pool_size, pointers[3], n1, &time1) ||
        !pool_array(pool, pool_size, pointers[4], n2, &amplitude) ||
        !pool_array(pool, pool_size, pointers[5], n2, &time2)) return 0;
    for (i = 0; i < n0; ++i)
        if (phones[i] < 0 || phones[i] > 255 ||
            durations[i] <= 0 || durations[i] > 2000) return 0;
    for (i = 0; i < n1; ++i) {
        if (pitch[i] < 0 || pitch[i] > 5000 || time1[i] < 0) return 0;
        if (i && time1[i] < time1[i - 1]) return 0;
    }
    for (i = 0; i < n2; ++i) {
        if (amplitude[i] < 0 || time2[i] < 0) return 0;
        if (i && time2[i] < time2[i - 1]) return 0;
    }
    maximum = address;
    for (i = 0; i < 6; ++i) if (pointers[i] > maximum) maximum = pointers[i];
    *score = maximum;
    return 1;
}

static int scale_prosody_array(uint32_t address, uint32_t count,
                               double factor, int duration) {
    int16_t *values;
    uint32_t i;
    int16_t previous_original = 0, previous_scaled = 0;
    values = (int16_t *)malloc((count ? count : 1) * sizeof(int16_t));
    if (!values || (count && !guest_read(bridge.uc, address, values,
                                         count * sizeof(int16_t)))) {
        free(values); return 0;
    }
    for (i = 0; i < count; ++i) {
        int16_t original = values[i];
        double divided = original / factor;
        int32_t scaled = (int32_t)(divided + (divided >= 0 ? 0.5 : -0.5));
        if (duration && scaled < 1) scaled = 1;
        if (!duration && i && original > previous_original &&
            scaled <= previous_scaled) scaled = previous_scaled + 1;
        if (scaled < -32768) scaled = -32768;
        if (scaled > 32767) scaled = 32767;
        values[i] = (int16_t)scaled;
        previous_original = original;
        previous_scaled = values[i];
    }
    i = guest_write(bridge.uc, address, values, count * sizeof(int16_t));
    free(values);
    return i;
}

/* Scale Nokia's phoneme durations and the two prosody-control timelines after
   PrimeSynthesisL, before the scheduler makes Klatt frames. */
NOKIA_EXPORT int nokia_apply_prosody_rate(double factor) {
    uint8_t *pool = NULL, object[0x28];
    uint32_t pool_size, address, score = 0, candidate_score, offset;
    uint32_t n0, n1, n2, durations, time1, time2;
    if (!bridge.uc || !bridge.mem_read || !bridge.mem_write) return 0;
    if (factor < 0.4) factor = 0.4;
    if (factor > 4.0) factor = 4.0;
    if (factor > 0.999 && factor < 1.001) return 1;
    address = bridge.prosody_object;
    pool_size = bridge.heap_next > 0x53000000u
        ? bridge.heap_next - 0x53000000u : 0;
    if (!pool_size || pool_size > 0x800000u) return 0;
    pool = (uint8_t *)malloc(pool_size);
    if (!pool || bridge.mem_read(bridge.uc, 0x53000000u, pool, pool_size))
        goto failed;
    if (!prosody_object_valid(pool, pool_size, address, &score)) {
        address = 0;
        for (offset = 0; offset + 0x28u <= pool_size; offset += 4) {
            uint32_t possible = 0x53000000u + offset;
            if (prosody_object_valid(pool, pool_size, possible,
                                     &candidate_score) &&
                (!address || candidate_score > score)) {
                address = possible; score = candidate_score;
            }
        }
    }
    if (!address || bridge.mem_read(bridge.uc, address, object,
                                    sizeof(object))) goto failed;
    n0 = load_u16(object); n1 = load_u16(object + 2);
    n2 = load_u16(object + 4);
    durations = load_u32(object + 0x0c);
    time1 = load_u32(object + 0x14);
    time2 = load_u32(object + 0x20);
    if (!scale_prosody_array(durations, n0, factor, 1) ||
        !scale_prosody_array(time1, n1, factor, 0) ||
        !scale_prosody_array(time2, n2, factor, 0)) goto failed;
    bridge.prosody_object = address;
    free(pool);
    return 1;
failed:
    free(pool);
    return 0;
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

NOKIA_EXPORT uint32_t nokia_heap_realloc(uint32_t address, uint32_t size) {
    return heap_realloc(address, size);
}

NOKIA_EXPORT uint32_t nokia_heap_size(uint32_t address) {
    return heap_size(address);
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

NOKIA_EXPORT int nokia_install_executive_hooks(
    uint32_t thread_data, const uint64_t entries[3]) {
    unsigned i;
    if (!bridge.uc || !bridge.hook_add || !thread_data || !entries) return 0;
    bridge.thread_data = thread_data;
    memset(bridge.executive_native_calls, 0,
           sizeof(bridge.executive_native_calls));
    memset(bridge.executive_fallback_calls, 0,
           sizeof(bridge.executive_fallback_calls));
    for (i = 0; i < 3; ++i) {
        if (!entries[i] ||
            bridge.hook_add(bridge.uc, &bridge.executive_hook[i], 4,
                            (void *)executive_hook, (void *)(uintptr_t)i,
                            entries[i], entries[i]) != 0) {
            while (i) {
                --i;
                bridge.hook_del(bridge.uc, bridge.executive_hook[i]);
                bridge.executive_hook[i] = 0;
            }
            return 0;
        }
    }
    return 1;
}

NOKIA_EXPORT void nokia_executive_hook_counters(uint64_t out[6]) {
    unsigned i;
    for (i = 0; i < 3; ++i) {
        out[i] = bridge.executive_native_calls[i];
        out[3 + i] = bridge.executive_fallback_calls[i];
    }
}

NOKIA_EXPORT void nokia_frontend_lookup_hook_counters(uint64_t out[2]) {
    out[0] = bridge.frontend_native_calls;
    out[1] = bridge.frontend_fallback_calls;
}

NOKIA_EXPORT void nokia_full_frontend_hook_counters(uint64_t out[2]) {
    out[0] = bridge.full_frontend_native_calls;
    out[1] = bridge.full_frontend_fallback_calls;
}

NOKIA_EXPORT void nokia_search_adapter_hook_counters(uint64_t out[2]) {
    out[0] = bridge.search_native_calls;
    out[1] = bridge.search_fallback_calls;
}

NOKIA_EXPORT void nokia_partition_hook_counters(uint64_t out[2]) {
    out[0] = bridge.partition_native_calls;
    out[1] = bridge.partition_fallback_calls;
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
    if (bridge.uc && bridge.search_hook)
        bridge.hook_del(bridge.uc, bridge.search_hook);
    if (bridge.uc && bridge.partition_hook)
        bridge.hook_del(bridge.uc, bridge.partition_hook);
    if (bridge.uc && bridge.full_frontend_hook)
        bridge.hook_del(bridge.uc, bridge.full_frontend_hook);
    if (bridge.uc && bridge.full_frontend_return_hook)
        bridge.hook_del(bridge.uc, bridge.full_frontend_return_hook);
    full_remove_resume_hooks();
    for (int i = 0; i < 2; ++i)
        if (bridge.uc && bridge.prosody_hook[i])
            bridge.hook_del(bridge.uc, bridge.prosody_hook[i]);
    for (int i = 0; i < 4; ++i)
        if (bridge.uc && bridge.heap_hook[i])
            bridge.hook_del(bridge.uc, bridge.heap_hook[i]);
    for (int i = 0; i < 3; ++i)
        if (bridge.uc && bridge.executive_hook[i])
            bridge.hook_del(bridge.uc, bridge.executive_hook[i]);
    bridge.hook = 0;
    bridge.resampler_hook = 0;
    bridge.frontend_hook = 0;
    bridge.search_hook = 0;
    bridge.partition_hook = 0;
    bridge.full_frontend_hook = bridge.full_frontend_return_hook = 0;
    bridge.full_callback_return = 0;
    bridge.full_static_initialized = 0;
    bridge.prosody_hook[0] = bridge.prosody_hook[1] = 0;
    memset(bridge.heap_hook, 0, sizeof(bridge.heap_hook));
    memset(bridge.executive_hook, 0, sizeof(bridge.executive_hook));
    free(heap_blocks);
    heap_blocks = NULL;
    heap_count = heap_capacity = 0;
    free(bridge.full_heap); free(bridge.full_vtable);
    free(bridge.full_traps); free(bridge.full_pool); free(bridge.full_stack);
    bridge.full_heap = bridge.full_vtable = bridge.full_traps = NULL;
    bridge.full_pool = bridge.full_stack = NULL;
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
