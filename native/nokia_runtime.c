#include "nokia_runtime.h"

#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef NOKIA_DEBUG_PROSODY
#include <stdio.h>
#endif

#define HEAP_BASE  0x50000000u
#define VT_BASE    0x51000000u
#define TRAP_BASE  0x52000000u
#define POOL_BASE  0x53000000u
#define STACK_BASE 0x60000000u
#define ROM_BASE_5320 0x80000000u
#define ROM_BASE_5500 0xF80F1000u
#define RET_MAGIC  0x7fff0000u
#define HEAP_SIZE  0x100000u
#define VT_SIZE    0x1000u
#define TRAP_SIZE  0x10000u
#define POOL_SIZE  0x800000u
#define STACK_SIZE 0x100000u
#define SAMPLE_RATE 16000u
#define SNAP_WORDS 27u

#ifndef NOKIA_CONTINUE_PROSODY
#define NOKIA_CONTINUE_PROSODY 0
#endif


#define ROM_PACK_HEADER_SIZE 24u
#define ROM_PACK_PAGE_SIZE   4096u
static const uint8_t nokia_rom_pack_magic[8] =
    {'N','K','R','O','M','P','1','\0'};

static uint32_t rom_pack_u32(const uint8_t *p) {
    uint32_t value;
    memcpy(&value, p, sizeof(value));
    return value;
}
static int rom_pack_info(const uint8_t *rom, size_t rom_size,
                         uint32_t *virtual_size, uint32_t *page_count,
                         const uint8_t **index, const uint8_t **pages) {
    uint32_t version, page_size, size, count;
    uint64_t table_end, data_end;
    if (!rom || rom_size < ROM_PACK_HEADER_SIZE ||
        memcmp(rom, nokia_rom_pack_magic, sizeof(nokia_rom_pack_magic)) != 0)
        return 0;
    version = rom_pack_u32(rom + 8u);
    page_size = rom_pack_u32(rom + 12u);
    size = rom_pack_u32(rom + 16u);
    count = rom_pack_u32(rom + 20u);
    table_end = ROM_PACK_HEADER_SIZE + (uint64_t)count * 4u;
    data_end = table_end + (uint64_t)count * ROM_PACK_PAGE_SIZE;
    if (version != 1u || page_size != ROM_PACK_PAGE_SIZE || !size ||
        count > 65536u || data_end > rom_size)
        return 0;
    if (virtual_size) *virtual_size = size;
    if (page_count) *page_count = count;
    if (index) *index = rom + ROM_PACK_HEADER_SIZE;
    if (pages) *pages = rom + table_end;
    return 1;
}
static int rom_pack_validate(const uint8_t *rom, size_t rom_size) {
    const uint8_t *index;
    uint32_t size, count, i, previous = 0;
    if (!rom_pack_info(rom, rom_size, &size, &count, &index, NULL))
        return 0;
    for (i = 0; i < count; ++i) {
        uint32_t page = rom_pack_u32(index + i * 4u);
        if (page >= (size + ROM_PACK_PAGE_SIZE - 1u) / ROM_PACK_PAGE_SIZE ||
            (i && page <= previous))
            return 0;
        previous = page;
    }
    return 1;
}
int nokia_runtime_rom_is_flat(const uint8_t *rom, size_t rom_size) {
    return !(rom && rom_size >= sizeof(nokia_rom_pack_magic) &&
             memcmp(rom, nokia_rom_pack_magic,
                    sizeof(nokia_rom_pack_magic)) == 0);
}
static size_t nokia_runtime_rom_virtual_size(const uint8_t *rom,
                                             size_t rom_size) {
    uint32_t virtual_size;
    return rom_pack_info(rom, rom_size, &virtual_size, NULL, NULL, NULL)
        ? (size_t)virtual_size : rom_size;
}
int nokia_runtime_rom_read(const uint8_t *rom, size_t rom_size,
                           uint32_t rom_base, uint32_t address,
                           void *output, unsigned size) {
    const uint8_t *index, *pages;
    uint8_t *destination = (uint8_t *)output;
    uint32_t virtual_size, count;
    uint64_t offset;
    if (!output || !size || address < rom_base) return 0;
    offset = (uint64_t)address - rom_base;
    if (nokia_runtime_rom_is_flat(rom, rom_size)) {
        if (offset + size > rom_size) return 0;
        memcpy(output, rom + offset, size);
        return 1;
    }
    if (!rom_pack_info(rom, rom_size, &virtual_size, &count, &index, &pages) ||
        offset + size > virtual_size)
        return 0;
    while (size) {
        uint32_t page = (uint32_t)(offset / ROM_PACK_PAGE_SIZE);
        uint32_t within = (uint32_t)(offset % ROM_PACK_PAGE_SIZE);
        uint32_t take = ROM_PACK_PAGE_SIZE - within;
        uint32_t low = 0, high = count, found = count;
        while (low < high) {
            uint32_t middle = low + (high - low) / 2u;
            uint32_t candidate = rom_pack_u32(index + middle * 4u);
            if (candidate < page) low = middle + 1u;
            else { high = middle; if (candidate == page) found = middle; }
        }
        if (found == count) return 0;
        if (take > size) take = size;
        memcpy(destination, pages + (uint64_t)found * ROM_PACK_PAGE_SIZE + within,
               take);
        destination += take;
        offset += take;
        size -= take;
    }
    return 1;
}

#define ROM_TRACE_PAGE_SHIFT 12u
#define ROM_TRACE_PAGE_SIZE  (1u << ROM_TRACE_PAGE_SHIFT)
#define ROM_TRACE_MAX_PAGES  65536u

static uint8_t nokia_rom_trace_pages[ROM_TRACE_MAX_PAGES];
static uint32_t nokia_rom_trace_touched;

NOKIA_RUNTIME_EXPORT void nokia_runtime_rom_trace_reset(void) {
    memset(nokia_rom_trace_pages, 0, sizeof(nokia_rom_trace_pages));
    nokia_rom_trace_touched = 0;
}
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_rom_trace_page_size(void) {
    return ROM_TRACE_PAGE_SIZE;
}
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_rom_trace_page_used(uint32_t page) {
    return page < ROM_TRACE_MAX_PAGES && nokia_rom_trace_pages[page] != 0;
}
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_rom_trace_touched_pages(void) {
    return nokia_rom_trace_touched;
}

/* Called by the generated frontend and Klatt AOT memory readers. */
void nokia_runtime_trace_rom_read(const uint8_t *rom, size_t rom_size,
                                  uint32_t rom_base, uint32_t address,
                                  unsigned size) {
    uint64_t offset, last;
    size_t virtual_size = nokia_runtime_rom_virtual_size(rom, rom_size);
    uint32_t first_page, last_page, page;
    if (!size || address < rom_base) return;
    offset = (uint64_t)address - rom_base;
    if (offset >= virtual_size) return;
    last = offset + (uint64_t)size - 1u;
    if (last >= virtual_size) last = virtual_size - 1u;
    first_page = (uint32_t)(offset >> ROM_TRACE_PAGE_SHIFT);
    last_page = (uint32_t)(last >> ROM_TRACE_PAGE_SHIFT);
    if (first_page >= ROM_TRACE_MAX_PAGES) return;
    if (last_page >= ROM_TRACE_MAX_PAGES) last_page = ROM_TRACE_MAX_PAGES - 1u;
    for (page = first_page; page <= last_page; ++page) {
        if (!nokia_rom_trace_pages[page]) {
            nokia_rom_trace_pages[page] = 1u;
            ++nokia_rom_trace_touched;
        }
    }
}

extern int nokia_klatt_generate_aot(
    int16_t *, int32_t *, uint8_t[122], uint8_t[564], uint32_t,
    const uint8_t *, uint32_t, size_t, uint32_t[5]);

typedef struct {
    void *context;
    uint32_t (*alloc)(void *, uint32_t);
    void (*free)(void *, uint32_t);
    uint32_t (*realloc)(void *, uint32_t, uint32_t);
    uint32_t (*length)(void *, uint32_t);
    uint32_t (*event)(void *, uint32_t, uint32_t);
    uint32_t (*process)(void *, uint32_t);
    int (*klatt)(void *, uint32_t regs[17]);
} NokiaFrontendHost;

extern int nokia_frontend_aot(
    uint8_t *, uint8_t *, uint8_t *, uint8_t *, uint8_t *,
    const uint8_t *, uint32_t, size_t, uint32_t[17], uint32_t,
    const NokiaFrontendHost *);

typedef struct {
    uint32_t address;
    uint32_t size;
    uint8_t used;
} RuntimeBlock;

#define SEAM_QUIET_LEVEL 16
#define SEAM_PREROLL     16u
#define PCM_TAIL_SAMPLES 64u
#define PROSODY_MIN_DURATION 8
#define PROSODY_CONTINUATION_TAIL 1600u
#define PROSODY_TIME_BACKSTEP_MAX 32

static int quiet_sample(int16_t sample);

struct NokiaRuntime {
    uint8_t *rom;
    size_t rom_size;
    uint32_t rom_base;
    uint8_t *heap, *vtable, *traps, *pool, *stack;
    RuntimeBlock *blocks;
    uint32_t block_count, block_capacity;
    uint32_t pool_next;
    uint32_t language_id, voice_applied;
    uint32_t dev, observer, style_id, scheduler_error;
    uint32_t thread_data, scheduler, trap_handler;
    uint32_t dev_synthesize, dev_prime, dev_stop, dev_buffer_processed;
    uint32_t seg_set_style_id, seg_set_text_ptr, pt_add_segment;
    uint32_t pt_new, pt_delete;
    uint32_t run_if_ready, cleanup_prev, cleanup_pop, cleanup_next;
    double rate_factor, pitch_factor;
    volatile long cancelled;
    int last_error;
    uint32_t klatt_failure, klatt_regs[5], klatt_count, klatt_gain;
    uint64_t frontend_ticks, audio_ticks, first_pcm_ticks;
    clock_t speak_started;
    const NokiaRuntimeCallbacks *callbacks;
    uint32_t *pending;
    uint32_t pending_count, pending_capacity, text_chunks;
    int16_t *seam_quiet;
    size_t seam_quiet_count, seam_quiet_capacity;
    uint32_t seam_trimmed_samples, seam_leading_seen;
    int16_t seam_leading[SEAM_PREROLL];
    uint32_t seam_leading_count;
    int16_t *pcm_pending;
    size_t pcm_pending_count, pcm_pending_capacity;
    uint32_t pcm_wrap_repairs;
    int32_t pcm_unwrapped_previous, pcm_wrap_offset;
    uint8_t done, first_pcm_seen, seam_enabled, seam_skip_leading;
    uint8_t pcm_unwrapped_have;
    NokiaFrontendHost host;
};

static uint32_t rd32(const uint8_t *p) {
    uint32_t v; memcpy(&v, p, 4); return v;
}
static void wr32(uint8_t *p, uint32_t v) { memcpy(p, &v, 4); }
static uint16_t rd16(const uint8_t *p) {
    uint16_t v; memcpy(&v, p, 2); return v;
}
static uint32_t cell_size(uint32_t n) {
    n = n < 4u ? 4u : n;
    return (n + 15u) & ~15u;
}

static uint8_t *guest_ptr(NokiaRuntime *r, uint32_t a, uint32_t n, int write) {
    uint64_t e = (uint64_t)a + n;
    if (a >= HEAP_BASE && e <= (uint64_t)HEAP_BASE + HEAP_SIZE)
        return r->heap + (a - HEAP_BASE);
    if (a >= VT_BASE && e <= (uint64_t)VT_BASE + VT_SIZE)
        return r->vtable + (a - VT_BASE);
    if (a >= TRAP_BASE && e <= (uint64_t)TRAP_BASE + TRAP_SIZE)
        return r->traps + (a - TRAP_BASE);
    if (a >= POOL_BASE && e <= (uint64_t)POOL_BASE + POOL_SIZE)
        return r->pool + (a - POOL_BASE);
    if (a >= STACK_BASE && e <= (uint64_t)STACK_BASE + STACK_SIZE)
        return r->stack + (a - STACK_BASE);
    if (!write && nokia_runtime_rom_is_flat(r->rom, r->rom_size) &&
        a >= r->rom_base && e <= (uint64_t)r->rom_base + r->rom_size)
        return r->rom + (a - r->rom_base);
    return NULL;
}

static int guest_read(NokiaRuntime *r, uint32_t a, void *out, uint32_t n) {
    uint8_t *p = guest_ptr(r, a, n, 0);
    if (p) { memcpy(out, p, n); return 1; }
    return nokia_runtime_rom_read(
        r->rom, r->rom_size, r->rom_base, a, out, (unsigned)n);
}
static int guest_write(NokiaRuntime *r, uint32_t a, const void *in, uint32_t n) {
    uint8_t *p = guest_ptr(r, a, n, 1);
    if (!p) return 0;
    memcpy(p, in, n); return 1;
}
static uint32_t guest_u32(NokiaRuntime *r, uint32_t a) {
    uint32_t v = 0; guest_read(r, a, &v, 4); return v;
}

static int reserve_blocks(NokiaRuntime *r, uint32_t want) {
    RuntimeBlock *b;
    uint32_t cap = r->block_capacity ? r->block_capacity : 256u;
    if (want <= r->block_capacity) return 1;
    while (cap < want) cap *= 2u;
    b = (RuntimeBlock *)realloc(r->blocks, (size_t)cap * sizeof(*b));
    if (!b) return 0;
    r->blocks = b; r->block_capacity = cap; return 1;
}
static int add_block(NokiaRuntime *r, uint32_t a, uint32_t n, int used) {
    if (!a || !n || !reserve_blocks(r, r->block_count + 1u)) return 0;
    r->blocks[r->block_count].address = a;
    r->blocks[r->block_count].size = n;
    r->blocks[r->block_count].used = used ? 1u : 0u;
    ++r->block_count; return 1;
}
static void merge_free(NokiaRuntime *r) {
    uint32_t i, j;
    for (i = 0; i < r->block_count; ++i) {
        if (r->blocks[i].used) continue;
        for (j = i + 1; j < r->block_count;) {
            if (!r->blocks[j].used &&
                r->blocks[i].address + r->blocks[i].size == r->blocks[j].address) {
                r->blocks[i].size += r->blocks[j].size;
                memmove(&r->blocks[j], &r->blocks[j + 1],
                        (r->block_count - j - 1u) * sizeof(*r->blocks));
                --r->block_count;
            } else if (!r->blocks[j].used &&
                       r->blocks[j].address + r->blocks[j].size == r->blocks[i].address) {
                r->blocks[i].address = r->blocks[j].address;
                r->blocks[i].size += r->blocks[j].size;
                memmove(&r->blocks[j], &r->blocks[j + 1],
                        (r->block_count - j - 1u) * sizeof(*r->blocks));
                --r->block_count;
            } else ++j;
        }
    }
}
static uint32_t rt_alloc(void *ctx, uint32_t requested) {
    NokiaRuntime *r = (NokiaRuntime *)ctx;
    uint32_t need = cell_size(requested), i, a;
    uint8_t *p;
    for (i = 0; i < r->block_count; ++i) {
        RuntimeBlock *b = &r->blocks[i];
        if (b->used || b->size < need) continue;
        a = b->address;
        if (b->size == need) b->used = 1;
        else {
            uint32_t rest_a = b->address + need, rest_n = b->size - need;
            b->size = need; b->used = 1;
            if (!add_block(r, rest_a, rest_n, 0)) return 0;
        }
        p = guest_ptr(r, a, need, 1); if (!p) return 0;
        memset(p, 0, need); return a;
    }
    if ((uint64_t)r->pool_next + need > (uint64_t)POOL_BASE + POOL_SIZE) return 0;
    a = r->pool_next; r->pool_next += need;
    if (!add_block(r, a, need, 1)) return 0;
    p = guest_ptr(r, a, need, 1); if (!p) return 0;
    memset(p, 0, need); return a;
}
static void rt_free(void *ctx, uint32_t a) {
    NokiaRuntime *r = (NokiaRuntime *)ctx;
    uint32_t i;
    if (!a) return;
    for (i = 0; i < r->block_count; ++i)
        if (r->blocks[i].used && r->blocks[i].address == a) {
            r->blocks[i].used = 0; merge_free(r); return;
        }
}
static uint32_t rt_length(void *ctx, uint32_t a) {
    NokiaRuntime *r = (NokiaRuntime *)ctx;
    uint32_t i;
    for (i = 0; i < r->block_count; ++i)
        if (r->blocks[i].used && r->blocks[i].address == a) return r->blocks[i].size;
    return 0;
}
static uint32_t rt_realloc(void *ctx, uint32_t a, uint32_t requested) {
    NokiaRuntime *r = (NokiaRuntime *)ctx;
    uint32_t old, n, copy;
    uint8_t *src, *dst;
    if (!a) return rt_alloc(ctx, requested);
    if (!requested) { rt_free(ctx, a); return 0; }
    old = rt_length(ctx, a);
    if (!old) return 0;
    if (cell_size(requested) <= old) return a;
    n = rt_alloc(ctx, requested); if (!n) return 0;
    copy = old < requested ? old : requested;
    src = guest_ptr(r, a, copy, 0); dst = guest_ptr(r, n, copy, 1);
    if (!src || !dst) { rt_free(ctx, n); return 0; }
    memcpy(dst, src, copy); rt_free(ctx, a); return n;
}

static int pending_add(NokiaRuntime *r, uint32_t a) {
    uint32_t cap;
    uint32_t *p;
    if (r->pending_count == r->pending_capacity) {
        cap = r->pending_capacity ? r->pending_capacity * 2u : 16u;
        p = (uint32_t *)realloc(r->pending, (size_t)cap * sizeof(*p));
        if (!p) return 0;
        r->pending = p; r->pending_capacity = cap;
    }
    r->pending[r->pending_count++] = a; return 1;
}

static uint32_t rt_event(void *ctx, uint32_t event, uint32_t value) {
    NokiaRuntime *r = (NokiaRuntime *)ctx;
    (void)value;
    if (event == 0u) r->done = 1u;
    return 0;
}

static int descriptor_data(NokiaRuntime *r, uint32_t d,
                           uint8_t **data, uint32_t *bytes) {
    uint32_t h, type, len, ptr;
    uint8_t *p = guest_ptr(r, d, 12, 0);
    if (!p) return 0;
    h = rd32(p); type = h >> 28; len = h & 0x0fffffffu;
    if (type == 0u) ptr = d + 4u;
    else if (type == 1u) ptr = rd32(p + 4);
    else if (type == 2u) ptr = rd32(p + 8);
    else if (type == 3u) ptr = d + 8u;
    else if (type == 4u) { uint32_t hb = rd32(p + 8); ptr = hb + 4u; }
    else return 0;
    *data = guest_ptr(r, ptr, len, 0);
    *bytes = len;
    return *data != NULL || len == 0;
}

static int reserve_i16(int16_t **buffer, size_t *capacity, size_t wanted) {
    size_t grown_capacity;
    int16_t *grown;
    if (wanted <= *capacity) return 1;
    grown_capacity = *capacity ? *capacity : 1024u;
    while (grown_capacity < wanted) {
        if (grown_capacity > (size_t)-1 / 2u) return 0;
        grown_capacity *= 2u;
    }
    grown = (int16_t *)realloc(*buffer,
                               grown_capacity * sizeof(*grown));
    if (!grown) return 0;
    *buffer = grown;
    *capacity = grown_capacity;
    return 1;
}

static int deliver_pcm(NokiaRuntime *r, const int16_t *samples, size_t count) {
    if (count && r->callbacks && r->callbacks->pcm)
        r->callbacks->pcm(r->callbacks->user, samples,
                          (uint32_t)count, SAMPLE_RATE);
    return 1;
}

/* The Klatt output is a 16-bit signal, but at short high-rate frames an
   internal peak can occasionally wrap from one signed extreme to the other.
   Follow the continuous 16-bit phase and saturate only samples that actually
   crossed that boundary; ordinary consonant attacks remain unchanged. */
static int16_t declick_pcm_sample(NokiaRuntime *r, int16_t sample) {
    int32_t unwrapped = (int32_t)sample + r->pcm_wrap_offset;
    if (r->pcm_unwrapped_have) {
        int32_t delta = unwrapped - r->pcm_unwrapped_previous;
        if (delta > 32768) {
            r->pcm_wrap_offset -= 65536;
            unwrapped -= 65536;
            ++r->pcm_wrap_repairs;
        } else if (delta < -32768) {
            r->pcm_wrap_offset += 65536;
            unwrapped += 65536;
            ++r->pcm_wrap_repairs;
        }
    }
    r->pcm_unwrapped_previous = unwrapped;
    r->pcm_unwrapped_have = 1u;
    if (unwrapped < -32768) return -32768;
    if (unwrapped > 32767) return 32767;
    return (int16_t)unwrapped;
}

/* Keep four milliseconds of PCM uncommitted so a genuinely abrupt final
   sample can still be faded without delaying the first audio callback. */
static int emit_pcm(NokiaRuntime *r, const int16_t *samples, size_t count) {
    size_t total, release, i;
    if (!count) return 1;
    total = r->pcm_pending_count + count;
    if (!reserve_i16(&r->pcm_pending, &r->pcm_pending_capacity, total))
        return 0;
    for (i = 0; i < count; ++i)
        r->pcm_pending[r->pcm_pending_count + i] =
            declick_pcm_sample(r, samples[i]);
    r->pcm_pending_count = total;
    if (total <= PCM_TAIL_SAMPLES) return 1;
    release = total - PCM_TAIL_SAMPLES;
    if (!deliver_pcm(r, r->pcm_pending, release)) return 0;
    memmove(r->pcm_pending, r->pcm_pending + release,
            PCM_TAIL_SAMPLES * sizeof(*r->pcm_pending));
    r->pcm_pending_count = PCM_TAIL_SAMPLES;
    return 1;
}

static int finish_pcm_output(NokiaRuntime *r) {
    size_t i, count;
    if (!r->pcm_pending_count) return 1;
    count = r->pcm_pending_count;
    if (!quiet_sample(r->pcm_pending[count - 1u])) {
        uint32_t denominator = count > 1u ? (uint32_t)count - 1u : 1u;
        for (i = 0; i < count; ++i)
            r->pcm_pending[i] = (int16_t)(
                (int32_t)r->pcm_pending[i] *
                (int32_t)(count - 1u - i) / (int32_t)denominator
            );
        r->pcm_pending[count - 1u] = 0;
    }
    if (!deliver_pcm(r, r->pcm_pending, count)) return 0;
    r->pcm_pending_count = 0u;
    return 1;
}

static int quiet_sample(int16_t sample) {
    return sample >= -SEAM_QUIET_LEVEL && sample <= SEAM_QUIET_LEVEL;
}

static int remember_leading(NokiaRuntime *r, const int16_t *samples,
                            size_t count) {
    size_t keep, old_keep;
    if (!count) return 1;
    r->seam_leading_seen += (uint32_t)count;
    keep = count < SEAM_PREROLL ? count : SEAM_PREROLL;
    old_keep = r->seam_leading_count;
    if (keep == SEAM_PREROLL) {
        memcpy(r->seam_leading, samples + count - keep,
               keep * sizeof(*samples));
        r->seam_leading_count = (uint32_t)keep;
        return 1;
    }
    if (old_keep + keep > SEAM_PREROLL) {
        size_t drop = old_keep + keep - SEAM_PREROLL;
        memmove(r->seam_leading, r->seam_leading + drop,
                (old_keep - drop) * sizeof(*samples));
        old_keep -= drop;
    }
    memcpy(r->seam_leading + old_keep, samples + count - keep,
           keep * sizeof(*samples));
    r->seam_leading_count = (uint32_t)(old_keep + keep);
    return 1;
}

static int append_quiet(NokiaRuntime *r, const int16_t *samples,
                        size_t count) {
    if (!count) return 1;
    if (!reserve_i16(&r->seam_quiet, &r->seam_quiet_capacity,
                     r->seam_quiet_count + count))
        return 0;
    memcpy(r->seam_quiet + r->seam_quiet_count, samples,
           count * sizeof(*samples));
    r->seam_quiet_count += count;
    return 1;
}

/* Preserve all pauses produced inside a Nokia chunk.  Only silence immediately
   before and after an artificial long-text boundary is shortened. */
static int seam_feed(NokiaRuntime *r, const int16_t *samples, size_t count) {
    size_t start = 0, end;
    if (!r->seam_enabled) return emit_pcm(r, samples, count);
    if (r->seam_skip_leading) {
        while (start < count && quiet_sample(samples[start])) ++start;
        if (!remember_leading(r, samples, start)) return 0;
        if (start == count) return 1;
        if (r->seam_leading_seen > r->seam_leading_count)
            r->seam_trimmed_samples +=
                r->seam_leading_seen - r->seam_leading_count;
        if (r->seam_leading_count &&
            !emit_pcm(r, r->seam_leading, r->seam_leading_count))
            return 0;
        r->seam_leading_seen = 0u;
        r->seam_leading_count = 0u;
        r->seam_skip_leading = 0u;
    }
    end = count;
    while (end > start && quiet_sample(samples[end - 1u])) --end;
    if (end == start)
        return append_quiet(r, samples + start, count - start);
    if (r->seam_quiet_count) {
        if (!emit_pcm(r, r->seam_quiet, r->seam_quiet_count)) return 0;
        r->seam_quiet_count = 0u;
    }
    if (end > start && !emit_pcm(r, samples + start, end - start)) return 0;
    return append_quiet(r, samples + end, count - end);
}

static int seam_finish_chunk(NokiaRuntime *r, int final) {
    size_t keep;
    if (!r->seam_enabled) return 1;
    if (final) {
        if (r->seam_skip_leading && r->seam_leading_count) {
            if (r->seam_leading_seen > r->seam_leading_count)
                r->seam_trimmed_samples +=
                    r->seam_leading_seen - r->seam_leading_count;
            if (!emit_pcm(r, r->seam_leading,
                          r->seam_leading_count)) return 0;
        }
        if (r->seam_quiet_count &&
            !emit_pcm(r, r->seam_quiet, r->seam_quiet_count))
            return 0;
        r->seam_quiet_count = 0u;
        r->seam_leading_seen = r->seam_leading_count = 0u;
        return 1;
    }
    keep = r->seam_quiet_count < SEAM_PREROLL
        ? r->seam_quiet_count : SEAM_PREROLL;
    if (r->seam_quiet_count > keep)
        r->seam_trimmed_samples +=
            (uint32_t)(r->seam_quiet_count - keep);
    if (keep && !emit_pcm(r, r->seam_quiet + r->seam_quiet_count - keep,
                          keep))
        return 0;
    r->seam_quiet_count = 0u;
    r->seam_skip_leading = 1u;
    r->seam_leading_seen = r->seam_leading_count = 0u;
    return 1;
}

static uint32_t rt_process(void *ctx, uint32_t descriptor) {
    NokiaRuntime *r = (NokiaRuntime *)ctx;
    uint8_t *data = NULL;
    uint32_t bytes = 0;
    clock_t before = clock();
    if (!descriptor_data(r, descriptor, &data, &bytes) ||
        !pending_add(r, descriptor)) {
        r->last_error = -1401; return 0;
    }
    if (bytes && !r->first_pcm_seen) {
        r->first_pcm_seen = 1u;
        r->first_pcm_ticks = (uint64_t)(clock() - r->speak_started);
    }
    if (bytes && !seam_feed(r, (const int16_t *)data, bytes / 2u))
        r->last_error = -1402;
    r->audio_ticks += (uint64_t)(clock() - before);
    return 0;
}

static int rt_klatt(void *ctx, uint32_t regs[17]) {
    NokiaRuntime *r = (NokiaRuntime *)ctx;
    uint8_t parameters[122], state[564];
    int16_t output[8192], count, f0;
    int32_t peak, scaled;
    uint32_t gain, after[5];
    uint8_t *p0, *p1, *p2, *p3, *ps;
    uint32_t missing;
    r->klatt_failure = 0;
    r->klatt_regs[0]=regs[0];r->klatt_regs[1]=regs[1];
    r->klatt_regs[2]=regs[2];r->klatt_regs[3]=regs[3];
    r->klatt_regs[4]=regs[13];r->klatt_count=0xffffffffu;r->klatt_gain=0;
    p1 = guest_ptr(r, regs[1], 4, 1);
    p2 = guest_ptr(r, regs[2], sizeof(parameters), 1);
    p3 = guest_ptr(r, regs[3], sizeof(state), 1);
    ps = guest_ptr(r, regs[13], 4, 0);
    missing=(!p1?2u:0u)|(!p2?4u:0u)|(!p3?8u:0u)|(!ps?16u:0u);
    if (missing) {
        r->klatt_failure=0x100u|missing;r->last_error=-2101;return 0;
    }
    memcpy(&peak, p1, 4); memcpy(parameters, p2, sizeof(parameters));
    memcpy(state, p3, sizeof(state)); memcpy(&gain, ps, 4);
    memcpy(&count, parameters + 2, 2);
    r->klatt_count=(uint32_t)(int32_t)count;r->klatt_gain=gain;
    if (count < 0 || count > 8192) {
        r->klatt_failure=0x200u;r->last_error=-2102;return 0;
    }
    /* Validate only the bytes this frame will actually write.  The former
       fixed 16384-byte check rejected valid short buffers near a region end. */
    p0 = guest_ptr(r, regs[0], (uint32_t)count * 2u, 1);
    if (!p0) {
        r->klatt_failure=0x101u;r->last_error=-2101;return 0;
    }
    if (r->pitch_factor > 0.0 && r->pitch_factor != 1.0) {
        memcpy(&f0, parameters + 0x18, 2);
        if (f0 > 0) {
            scaled = (int32_t)(f0 * r->pitch_factor + 0.5);
            if (scaled < 300) scaled = 300; if (scaled > 5000) scaled = 5000;
            f0 = (int16_t)scaled; memcpy(parameters + 0x18, &f0, 2);
        }
    }
    if (!nokia_klatt_generate_aot(output, &peak, parameters, state, gain,
                                  r->rom, r->rom_base, r->rom_size, after)) {
        r->klatt_failure=0x300u;r->last_error=-2103;return 0;
    }
    if (count) memcpy(p0, output, (size_t)count * 2u);
    memcpy(p1, &peak, 4); memcpy(p2, parameters, sizeof(parameters));
    memcpy(p3, state, sizeof(state));
    regs[0] = (uint32_t)(int32_t)count;
    regs[1] = after[0]; regs[2] = after[1]; regs[3] = after[2];
    regs[12] = after[3]; regs[16] = after[4];
    return 1;
}

static NokiaRuntime *alloc_runtime(const uint8_t *rom, size_t rom_size,
                                   uint32_t rom_base) {
    NokiaRuntime *r;
    if (!rom || !rom_size ||
        (!nokia_runtime_rom_is_flat(rom, rom_size) &&
         !rom_pack_validate(rom, rom_size)))
        return NULL;
    r = (NokiaRuntime *)calloc(1, sizeof(*r)); if (!r) return NULL;
    r->rom_base = rom_base;
    r->rom = (uint8_t *)malloc(rom_size);
    r->heap = (uint8_t *)calloc(1, HEAP_SIZE);
    r->vtable = (uint8_t *)calloc(1, VT_SIZE);
    r->traps = (uint8_t *)calloc(1, TRAP_SIZE);
    r->pool = (uint8_t *)calloc(1, POOL_SIZE);
    r->stack = (uint8_t *)calloc(1, STACK_SIZE);
    if (!r->rom || !r->heap || !r->vtable || !r->traps || !r->pool || !r->stack) {
        nokia_runtime_destroy(r); return NULL;
    }
    memcpy(r->rom, rom, rom_size); r->rom_size = rom_size;
    r->rate_factor = r->pitch_factor = 1.0;
    r->host.context = r; r->host.alloc = rt_alloc; r->host.free = rt_free;
    r->host.realloc = rt_realloc; r->host.length = rt_length;
    r->host.event = rt_event; r->host.process = rt_process; r->host.klatt = rt_klatt;
    return r;
}

NOKIA_RUNTIME_EXPORT NokiaRuntime *nokia_runtime_create_5320(
    const uint8_t *rom, size_t rom_size, const char *root,
    uint32_t language_id, uint32_t voice_id) {
    NokiaRuntime *r = alloc_runtime(rom, rom_size, ROM_BASE_5320);
    (void)root; (void)voice_id;
    if (r) { r->language_id = language_id; r->last_error = -1000; }
    return r;
}

static NokiaRuntime *create_snapshot(
    const uint8_t *rom, size_t rom_size,
    const uint8_t *s, size_t snapshot_size,
    const uint8_t magic[8], uint32_t rom_base) {
    NokiaRuntime *r;
    const uint8_t *p, *end;
    uint32_t w[SNAP_WORDS], i, regions, used, freec;
    if (!s || snapshot_size < 8u + SNAP_WORDS * 4u || memcmp(s, magic, 8)) return NULL;
    p = s + 8; end = s + snapshot_size;
    for (i = 0; i < SNAP_WORDS; ++i) { w[i] = rd32(p); p += 4; }
    if (w[0] != 1u) return NULL;
    regions = w[24]; used = w[25]; freec = w[26];
    if ((uint64_t)(p - s) + (uint64_t)regions * 12u +
        (uint64_t)(used + freec) * 8u > snapshot_size) return NULL;
    r = alloc_runtime(rom, rom_size, rom_base); if (!r) return NULL;
    r->language_id=w[1];r->voice_applied=w[2];r->dev=w[3];r->observer=w[4];r->style_id=w[5];
    r->scheduler_error=w[6];r->thread_data=w[7];r->scheduler=w[8];r->trap_handler=w[9];r->pool_next=w[10];
    r->dev_synthesize=w[11];r->dev_prime=w[12];r->dev_stop=w[13];r->dev_buffer_processed=w[14];
    r->seg_set_style_id=w[15];r->seg_set_text_ptr=w[16];r->pt_add_segment=w[17];r->pt_new=w[18];r->pt_delete=w[19];
    r->run_if_ready=w[20];r->cleanup_prev=w[21];r->cleanup_pop=w[22];r->cleanup_next=w[23];
    for (i = 0; i < regions; ++i) {
        uint32_t a=rd32(p), n=rd32(p+4), off=rd32(p+8); uint8_t *dst;
        p += 12;
        if ((uint64_t)off + n > snapshot_size || !(dst=guest_ptr(r,a,n,1))) { nokia_runtime_destroy(r); return NULL; }
        memcpy(dst, s + off, n);
    }
    for (i = 0; i < used; ++i) { uint32_t a=rd32(p), n=rd32(p+4);p+=8;if(!add_block(r,a,n,1)){nokia_runtime_destroy(r);return NULL;} }
    for (i = 0; i < freec; ++i) { uint32_t a=rd32(p), n=rd32(p+4);p+=8;if(!add_block(r,a,n,0)){nokia_runtime_destroy(r);return NULL;} }
    (void)end;
    r->last_error = 0; return r;
}

NOKIA_RUNTIME_EXPORT NokiaRuntime *nokia_runtime_create_5320_snapshot(
    const uint8_t *rom, size_t rom_size,
    const uint8_t *s, size_t snapshot_size) {
    static const uint8_t magic[8] = {'N','K','5','3','2','0','S','1'};
    return create_snapshot(
        rom, rom_size, s, snapshot_size, magic, ROM_BASE_5320);
}

NOKIA_RUNTIME_EXPORT NokiaRuntime *nokia_runtime_create_5500_snapshot(
    const uint8_t *rom, size_t rom_size,
    const uint8_t *s, size_t snapshot_size) {
    static const uint8_t magic[8] = {'N','K','5','5','0','0','S','1'};
    return create_snapshot(
        rom, rom_size, s, snapshot_size, magic, ROM_BASE_5500);
}

NOKIA_RUNTIME_EXPORT void nokia_runtime_destroy(NokiaRuntime *r) {
    if (!r) return;
    free(r->pcm_pending); free(r->seam_quiet);
    free(r->pending); free(r->blocks); free(r->heap); free(r->vtable);
    free(r->traps); free(r->pool); free(r->stack); free(r->rom); free(r);
}

static int native_call(NokiaRuntime *r, uint32_t entry,
                       const uint32_t *args, uint32_t argc, uint32_t *result) {
    uint32_t regs[17] = {0}, i, sp = STACK_BASE + STACK_SIZE - 0x1000u;
    int status;
    for (i = 0; i < argc && i < 4u; ++i) regs[i] = args[i];
    if (argc > 4u) {
        uint32_t extra = argc - 4u;
        sp -= (extra * 4u + 7u) & ~7u;
        for (i = 0; i < extra; ++i)
            if (!guest_write(r, sp + i * 4u, &args[i + 4u], 4)) return 0;
    }
    regs[13]=sp;regs[14]=RET_MAGIC;regs[15]=entry;regs[16]=0;
    status = nokia_frontend_aot(r->heap,r->vtable,r->traps,r->pool,r->stack,
                                r->rom,r->rom_base,r->rom_size,regs,RET_MAGIC,&r->host);
    if (status != 1) {
        if (!r->last_error) r->last_error = status == 2 ? -2002 : -2001;
        return 0;
    }
    if (result) *result = regs[0]; return 1;
}
static uint32_t cleanup_ptr(NokiaRuntime *r) { return guest_u32(r, r->trap_handler + 4u); }
static uint32_t cleanup_depth(NokiaRuntime *r) {
    uint32_t c=cleanup_ptr(r), base=guest_u32(r,c+4u), next=guest_u32(r,c+12u);
    return c && next>=base ? (next-base)/8u : 0u;
}
static int native_call_l(NokiaRuntime *r, uint32_t entry,
                         const uint32_t *args, uint32_t argc, uint32_t *result) {
    uint32_t c=cleanup_ptr(r), a[2], before, after, dummy;
    if (!c) return 0;
    a[0]=c; if(!native_call(r,r->cleanup_next,a,1,&dummy))return 0;
    before=cleanup_depth(r);
    if(!native_call(r,entry,args,argc,result))return 0;
    after=cleanup_depth(r);
    if(after>before){a[0]=c;a[1]=after-before;if(!native_call(r,r->cleanup_pop,a,2,&dummy))return 0;}
    a[0]=c;return native_call(r,r->cleanup_prev,a,1,&dummy);
}
static uint32_t ptrc8(NokiaRuntime *r) {
    uint32_t d=rt_alloc(r,4),h=rt_alloc(r,8),z=0;
    uint8_t *p;if(!d||!h)return 0;p=guest_ptr(r,h,8,1);if(!p)return 0;wr32(p,0x10000000u);wr32(p+4,d);guest_write(r,d,&z,4);return h;
}
static uint32_t ptrc16(NokiaRuntime *r,const uint16_t *text,uint32_t len) {
    uint32_t bytes=len*2u,d=rt_alloc(r,bytes?bytes:4),h=rt_alloc(r,8);uint8_t*p;
    if(!d||!h)return 0;if(bytes&&!guest_write(r,d,text,bytes))return 0;p=guest_ptr(r,h,8,1);if(!p)return 0;
    wr32(p,0x10000000u|len);wr32(p+4,d);return h;
}
static void free_desc(NokiaRuntime *r,uint32_t h){uint32_t d=guest_u32(r,h+4u);rt_free(r,d);rt_free(r,h);}
static int drain(NokiaRuntime *r) {
    uint32_t i=0,res,a[2];
    while(i<r->pending_count){a[0]=r->dev;a[1]=r->pending[i];if(!native_call(r,r->dev_buffer_processed,a,2,&res))return 0;++i;}
    r->pending_count=0;return 1;
}

NOKIA_RUNTIME_EXPORT int nokia_runtime_set_rate(NokiaRuntime *r,double f){if(!r)return 0;if(f<0.2)f=0.2;if(f>5.0)f=5.0;r->rate_factor=f;return 1;}
NOKIA_RUNTIME_EXPORT int nokia_runtime_set_pitch(NokiaRuntime *r,double f){if(!r)return 0;if(f<0.5)f=0.5;if(f>2.0)f=2.0;r->pitch_factor=f;return 1;}
NOKIA_RUNTIME_EXPORT void nokia_runtime_cancel(NokiaRuntime *r){if(r)r->cancelled=1;}

#ifndef NOKIA_LONG_TEXT_THRESHOLD
#define NOKIA_LONG_TEXT_THRESHOLD 256u
#endif
#ifndef NOKIA_TEXT_CHUNK_MIN
#define NOKIA_TEXT_CHUNK_MIN       96u
#endif
#ifndef NOKIA_TEXT_CHUNK_TARGET
#define NOKIA_TEXT_CHUNK_TARGET   192u
#endif
#ifndef NOKIA_TEXT_CHUNK_LIMIT
#define NOKIA_TEXT_CHUNK_LIMIT    384u
#endif

static int text_space16(uint16_t c) {
    return c <= 0x20u || c == 0x00a0u || c == 0x2028u || c == 0x2029u;
}
static int text_terminal16(uint16_t c) {
    return c == '.' || c == '!' || c == '?' || c == 0x2026u ||
           c == 0x3002u || c == 0xff01u || c == 0xff1fu;
}
static int text_closer16(uint16_t c) {
    return c == '"' || c == '\'' || c == ')' || c == ']' || c == '}' ||
           c == 0x00bbu || c == 0x2019u || c == 0x201du;
}
static int text_period_is_internal(const uint16_t *text, uint32_t pos,
                                   uint32_t len) {
    uint32_t i, letters = 0;
    if (pos && pos + 1u < len &&
        text[pos - 1u] >= '0' && text[pos - 1u] <= '9' &&
        text[pos + 1u] >= '0' && text[pos + 1u] <= '9')
        return 1;
    i = pos;
    while (i && ((text[i - 1u] >= 'A' && text[i - 1u] <= 'Z') ||
                 (text[i - 1u] >= 'a' && text[i - 1u] <= 'z'))) {
        --i; ++letters;
    }
    /* Do not split initials such as "z. B." or "A. Smith". */
    return letters == 1u;
}
static uint32_t next_text_chunk(const uint16_t *text, uint32_t len) {
    uint32_t i, j, last_terminal = 0, last_soft = 0, last_word = 0;
    for (i = 0; i < len; ++i) {
        uint16_t c = text[i];
        if (c == '\r' || c == '\n' || c == 0x2028u || c == 0x2029u) {
            j = i + 1u;
            if (c == '\r' && j < len && text[j] == '\n') ++j;
            while (j < len && text_space16(text[j])) ++j;
            return j;
        }
        if (text_space16(c)) last_word = i + 1u;
        if ((c == ';' || c == ':') && i + 1u >= NOKIA_TEXT_CHUNK_TARGET)
            last_soft = i + 1u;
        if (text_terminal16(c) &&
            !(c == '.' && text_period_is_internal(text, i, len))) {
            j = i + 1u;
            while (j < len &&
                   (text_terminal16(text[j]) || text_closer16(text[j])))
                ++j;
            if (j == len || text_space16(text[j])) {
                while (j < len && text_space16(text[j])) ++j;
                last_terminal = j;
                if (j >= NOKIA_TEXT_CHUNK_MIN) return j;
                i = j ? j - 1u : i;
                continue;
            }
        }
        if (i + 1u >= NOKIA_TEXT_CHUNK_LIMIT) {
            if (last_terminal) return last_terminal;
            if (last_soft) return last_soft;
            if (last_word) return last_word;
            return i + 1u;
        }
    }
    if (last_terminal && last_terminal < len) return last_terminal;
    return len;
}

static int prosody_array(NokiaRuntime *r, uint32_t address, uint32_t count,
                         int16_t **out) {
    uint64_t bytes = (uint64_t)count * sizeof(int16_t);
    if (bytes > 0xffffffffu) return 0;
    *out = (int16_t *)guest_ptr(r, address, (uint32_t)bytes, 1);
    return *out != NULL;
}

static int prosody_range_used(NokiaRuntime *r, uint32_t address,
                              uint32_t count) {
    uint64_t bytes = (uint64_t)count * sizeof(int16_t);
    uint64_t end = (uint64_t)address + bytes;
    uint32_t i;
    if (!count) return 1;
    for (i = 0; i < r->block_count; ++i) {
        const RuntimeBlock *block = &r->blocks[i];
        uint64_t block_end = (uint64_t)block->address + block->size;
        if (block->used && address >= block->address && end <= block_end)
            return 1;
    }
    return 0;
}

/* Validate the duration object produced by PrimeSynthesisL.  Its six arrays
   hold phone ids, durations, F0 values/times and amplitude values/times. */
static int prosody_object_valid(NokiaRuntime *r, uint32_t address,
                                uint32_t *score) {
    static const uint8_t pointer_offsets[6] = {8, 12, 16, 20, 28, 32};
    uint8_t *object;
    int16_t *phones, *durations, *pitch, *time1, *amplitude, *time2;
    uint32_t n0, n1, n2, pointers[6], i, maximum;
    object = guest_ptr(r, address, 0x28u, 1);
    if (!object || !prosody_range_used(r, address, 0x28u / 2u)) return 0;
    n0 = rd16(object); n1 = rd16(object + 2u); n2 = rd16(object + 4u);
    /* Normal speech objects always contain all three curves.  Requiring them
       rejects unrelated C++ objects whose first halfword happens to look like
       a phone count.  A genuinely silent frontend result needs no rate or
       continuation processing and is safely ignored by the caller. */
    if (!n0 || !n1 || !n2) return 0;
    for (i = 0; i < 6u; ++i) pointers[i] = rd32(object + pointer_offsets[i]);
    if (!prosody_range_used(r, pointers[0], n0) ||
        !prosody_range_used(r, pointers[1], n0) ||
        !prosody_range_used(r, pointers[2], n1) ||
        !prosody_range_used(r, pointers[3], n1) ||
        !prosody_range_used(r, pointers[4], n2) ||
        !prosody_range_used(r, pointers[5], n2) ||
        !prosody_array(r, pointers[0], n0, &phones) ||
        !prosody_array(r, pointers[1], n0, &durations) ||
        (n1 && (!prosody_array(r, pointers[2], n1, &pitch) ||
                !prosody_array(r, pointers[3], n1, &time1))) ||
        (n2 && (!prosody_array(r, pointers[4], n2, &amplitude) ||
                !prosody_array(r, pointers[5], n2, &time2))))
        return 0;
    for (i = 0; i < n0; ++i) {
        if (phones[i] < 0 || phones[i] > 255 ||
            durations[i] < 0 || durations[i] > 4096)
            return 0;
    }
    if (durations[n0 - 1u] <= 0) return 0;
    for (i = 0; i < n1; ++i) {
        if (pitch[i] <= 0 || pitch[i] > 8192 || time1[i] < 0) return 0;
        /* Nokia occasionally places two final F0 control points a few time
           units out of order (for example whatRust/WhatsAppRust: -8).  This
           is a legitimate interpolation overlap, not a corrupt object. */
        if (i && (int32_t)time1[i] + PROSODY_TIME_BACKSTEP_MAX <
                     (int32_t)time1[i - 1u])
            return 0;
    }
    for (i = 0; i < n2; ++i) {
        if (amplitude[i] < 0 || time2[i] < 0) return 0;
        if (i && (int32_t)time2[i] + PROSODY_TIME_BACKSTEP_MAX <
                     (int32_t)time2[i - 1u])
            return 0;
    }
    maximum = address;
    for (i = 0; i < 2u; ++i)
        if (pointers[i] > maximum) maximum = pointers[i];
    if (n1)
        for (i = 2u; i < 4u; ++i)
            if (pointers[i] > maximum) maximum = pointers[i];
    if (n2)
        for (i = 4u; i < 6u; ++i)
            if (pointers[i] > maximum) maximum = pointers[i];
    *score = maximum;
    return 1;
}

static int scale_prosody_array(NokiaRuntime *r, uint32_t address,
                               uint32_t count, double factor,
                               int duration) {
    int16_t *values;
    uint32_t i;
    int16_t previous_original = 0, previous_scaled = 0;
    if (!count) return 1;
    if (!prosody_array(r, address, count, &values)) return 0;
    for (i = 0; i < count; ++i) {
        int16_t original = values[i];
        double divided = original / factor;
        int32_t scaled = (int32_t)(divided +
            (divided >= 0.0 ? 0.5 : -0.5));
        if (duration && original <= 0) continue;
        if (duration && scaled < 1) scaled = 1;
        if (!duration && i && original > previous_original &&
            scaled <= previous_scaled)
            scaled = previous_scaled + 1;
        if (scaled < -32768) scaled = -32768;
        if (scaled > 32767) scaled = 32767;
        values[i] = (int16_t)scaled;
        previous_original = original;
        previous_scaled = values[i];
    }
    return 1;
}

/* Speed up Nokia's phone durations without collapsing its shortest transition
   frames into one-to-four-unit parameter steps.  The last phone is the
   frontend's resonator drain; keeping its original duration lets Klatt settle
   naturally, while artificial long-text silence is still removed later. */
static int scale_phone_durations(NokiaRuntime *r, uint32_t phone_address,
                                 uint32_t duration_address, uint32_t count,
                                 double factor) {
    int16_t *phones, *durations;
    uint32_t i;
    if (!prosody_array(r, phone_address, count, &phones) ||
        !prosody_array(r, duration_address, count, &durations))
        return 0;
    for (i = 0; i < count; ++i) {
        int16_t original = durations[i];
        int32_t scaled;
        if (original <= 0) continue;
        if (i + 1u == count && phones[i] == 0) continue;
        scaled = (int32_t)(original / factor + 0.5);
        if (scaled < PROSODY_MIN_DURATION)
            scaled = PROSODY_MIN_DURATION;
        if (scaled > 32767) scaled = 32767;
        durations[i] = (int16_t)scaled;
    }
    return 1;
}

#if NOKIA_CONTINUE_PROSODY
/* PrimeSynthesisL gives every independently analysed chunk a low utterance-
   final F0 tail.  For a non-final chunk, retain Nokia's contour but guide
   only that tail back to the chunk's own opening baseline. */
static int continue_prosody_pitch(NokiaRuntime *r, uint32_t pitch_address,
                                  uint32_t time_address, uint32_t count) {
    int16_t *pitch, *times, opening[6];
    uint32_t opening_count, i, j, anchor = count, end_time, start_time;
    int32_t target;
    if (count < 3u) return 1;
    if (!prosody_array(r, pitch_address, count, &pitch) ||
        !prosody_array(r, time_address, count, &times))
        return 0;
    opening_count = count < 6u ? count : 6u;
    for (i = 0; i < opening_count; ++i) {
        opening[i] = pitch[i];
        for (j = i; j && opening[j - 1u] > opening[j]; --j) {
            int16_t swap = opening[j - 1u];
            opening[j - 1u] = opening[j];
            opening[j] = swap;
        }
    }
    target = opening[(opening_count - 1u) / 2u];
    end_time = (uint32_t)times[count - 1u];
    start_time = end_time > PROSODY_CONTINUATION_TAIL
        ? end_time - PROSODY_CONTINUATION_TAIL : 0u;
    for (i = count; i-- > 0u;) {
        if ((uint32_t)times[i] < start_time) break;
        if (pitch[i] >= target + 60) {
            anchor = i;
            break;
        }
    }
    if (anchor == count) {
        for (i = 0; i < count; ++i)
            if ((uint32_t)times[i] >= start_time) {
                anchor = i;
                break;
            }
    }
    if (anchor == count || anchor + 1u >= count) return 1;
    /* Lift only Nokia's utterance-final low point to the chunk's own neutral
       baseline.  Holding the complete last accent changes intonation which
       was already correct in other parts of a long block. */
    for (i = anchor + 1u; i < count; ++i) {
        if (pitch[i] < target) pitch[i] = (int16_t)target;
    }
    return 1;
}
#endif

/* Change speed in Nokia's own parameter domain: scale phoneme durations and
   both prosody timelines after PrimeSynthesisL, before any Klatt frame exists.
   F0 and amplitude values remain untouched. */
static int apply_prosody_rate(NokiaRuntime *r, int continuation) {
    uint8_t *object;
    uint32_t address = 0, score = 0, candidate_score, i, offset;
    uint32_t n0, n1, n2, phones, durations, pitch, time1, time2;
    double factor = r->rate_factor;
    if (factor < 0.4) factor = 0.4;
    if (factor > 4.0) factor = 4.0;
#ifndef NOKIA_DEBUG_PROSODY
    if (factor > 0.999 && factor < 1.001 &&
        !(NOKIA_CONTINUE_PROSODY && continuation)) return 1;
#endif
    /* Prime allocates this object at the beginning of a live pool block.  By
       following allocator metadata first, the finder no longer depends on
       language-specific phone values or arbitrary array-count ceilings. */
    for (i = 0; i < r->block_count; ++i) {
        uint32_t possible = r->blocks[i].address;
        if (!r->blocks[i].used || r->blocks[i].size < 0x28u) continue;
        if (prosody_object_valid(r, possible, &candidate_score) &&
            (!address || candidate_score > score)) {
            address = possible;
            score = candidate_score;
        }
    }
    /* Keep a contained-object fallback for a future frontend whose C++ object
       is embedded in a larger allocation rather than returned directly. */
    if (!address) {
        for (i = 0; i < r->block_count; ++i) {
            const RuntimeBlock *block = &r->blocks[i];
            if (!block->used || block->size < 0x28u) continue;
            for (offset = 4u; offset + 0x28u <= block->size; offset += 4u) {
                uint32_t possible = block->address + offset;
                if (prosody_object_valid(r, possible, &candidate_score) &&
                    (!address || candidate_score > score)) {
                    address = possible;
                    score = candidate_score;
                }
            }
        }
    }
    /* Rate/continuation processing is an enhancement.  A chunk which contains
       no speakable phones (or a future unfamiliar object layout) must still
       reach Nokia's own SynthesizeL instead of becoming error -3007. */
    if (!address || !(object = guest_ptr(r, address, 0x28u, 1))) return 1;
    n0 = rd16(object); n1 = rd16(object + 2u); n2 = rd16(object + 4u);
    phones = rd32(object + 0x08u);
    durations = rd32(object + 0x0cu);
    pitch = rd32(object + 0x10u);
    time1 = rd32(object + 0x14u);
    time2 = rd32(object + 0x20u);
#ifdef NOKIA_DEBUG_PROSODY
    {
        int16_t *phone_values, *duration_values;
        int16_t *pitch_values, *pitch_times;
        int16_t *amplitude_values, *amplitude_times;
        uint32_t i, first = n1 > 16u ? n1 - 16u : 0u;
        uint32_t phone_first = n0 > 24u ? n0 - 24u : 0u;
        if (prosody_array(r, rd32(object + 0x08u), n0, &phone_values) &&
            prosody_array(r, durations, n0, &duration_values)) {
            fprintf(stderr, "phones chunk=%u n0=%u:", r->text_chunks, n0);
            for (i = phone_first; i < n0; ++i)
                fprintf(stderr, " %d:%d", phone_values[i],
                        duration_values[i]);
            fputc('\n', stderr);
        }
        if (prosody_array(r, rd32(object + 0x10u), n1, &pitch_values) &&
            prosody_array(r, time1, n1, &pitch_times)) {
            fprintf(stderr, "prosody chunk=%u n0=%u n1=%u:",
                    r->text_chunks, n0, n1);
            for (i = 0; i < n1 && i < 6u; ++i)
                fprintf(stderr, " %d@%d", pitch_values[i], pitch_times[i]);
            fprintf(stderr, " ...");
            for (i = first; i < n1; ++i)
                fprintf(stderr, " %d@%d", pitch_values[i], pitch_times[i]);
            fputc('\n', stderr);
        }
        if (prosody_array(r, rd32(object + 0x1cu), n2,
                          &amplitude_values) &&
            prosody_array(r, time2, n2, &amplitude_times)) {
            uint32_t amplitude_first = n2 > 16u ? n2 - 16u : 0u;
            fprintf(stderr, "amplitude chunk=%u n2=%u:",
                    r->text_chunks, n2);
            for (i = amplitude_first; i < n2; ++i)
                fprintf(stderr, " %d@%d", amplitude_values[i],
                        amplitude_times[i]);
            fputc('\n', stderr);
        }
    }
#endif
#if NOKIA_CONTINUE_PROSODY
    if (continuation && !continue_prosody_pitch(r, pitch, time1, n1))
        return 0;
#ifdef NOKIA_DEBUG_PROSODY
    if (continuation) {
        int16_t *pitch_values, *pitch_times;
        uint32_t i, first = n1 > 8u ? n1 - 8u : 0u;
        if (prosody_array(r, pitch, n1, &pitch_values) &&
            prosody_array(r, time1, n1, &pitch_times)) {
            fprintf(stderr, "continued chunk=%u:", r->text_chunks);
            for (i = first; i < n1; ++i)
                fprintf(stderr, " %d@%d", pitch_values[i], pitch_times[i]);
            fputc('\n', stderr);
        }
    }
#endif
#else
    (void)continuation;
    (void)pitch;
#endif
    if (factor > 0.999 && factor < 1.001) return 1;
    return scale_phone_durations(r, phones, durations, n0, factor) &&
           scale_prosody_array(r, time1, n1, factor, 0) &&
           scale_prosody_array(r, time2, n2, factor, 0);
}

static int synthesize_text_chunk(NokiaRuntime *r, const uint16_t *text,
                                 uint32_t len, int continuation) {
    uint32_t txt=0,e8=0,e16=0,pt=0,seg=0,res=0,a[3],loops=0;
    clock_t start = clock();
    r->done=0;r->pending_count=0;
    txt=ptrc16(r,text,len);e8=ptrc8(r);e16=ptrc16(r,(const uint16_t*)L"",0);
    if(!txt||!e8||!e16){r->last_error=-3001;goto failed;}
    a[0]=txt;a[1]=e8;a[2]=e16;if(!native_call_l(r,r->pt_new,a,3,&pt)||!pt)goto failed;
    seg=rt_alloc(r,0x80u);if(!seg){r->last_error=-3002;goto failed;}
    a[0]=seg;a[1]=r->style_id;if(!native_call(r,r->seg_set_style_id,a,2,&res))goto failed;
    a[0]=seg;a[1]=txt;if(!native_call(r,r->seg_set_text_ptr,a,2,&res))goto failed;
    a[0]=pt;a[1]=seg;a[2]=0;if(!native_call_l(r,r->pt_add_segment,a,3,&res))goto failed;
    a[0]=r->dev;a[1]=pt;if(!native_call_l(r,r->dev_prime,a,2,&res))goto failed;
    if(!apply_prosody_rate(r,continuation)){r->last_error=-3007;goto failed;}
    r->frontend_ticks += (uint64_t)(clock()-start);
    a[0]=r->dev;a[1]=1;if(!native_call_l(r,r->dev_synthesize,a,2,&res))goto failed;
    while(!r->done&&!r->cancelled){
        if(!drain(r))goto failed;
        a[0]=r->scheduler_error;a[1]=(uint32_t)(int32_t)-100;
        if(!native_call(r,r->run_if_ready,a,2,&res))goto failed;
        if(!res&&!r->pending_count&&!r->done){r->last_error=-3003;goto failed;}
        if(++loops>100000u){r->last_error=-3004;goto failed;}
    }
    if(!drain(r))goto failed;
    if(r->last_error)goto failed;
    if(r->cancelled){a[0]=r->dev;native_call(r,r->dev_stop,a,1,&res);}
    a[0]=pt;native_call(r,r->pt_delete,a,1,&res);pt=0;
    if(seg){rt_free(r,seg);seg=0;}free_desc(r,txt);free_desc(r,e8);free_desc(r,e16);
    return r->done||r->cancelled;
failed:
    if(pt){a[0]=pt;native_call(r,r->pt_delete,a,1,&res);}
    if(seg)rt_free(r,seg);if(txt)free_desc(r,txt);if(e8)free_desc(r,e8);if(e16)free_desc(r,e16);
    if(!r->last_error)r->last_error=-3099;return 0;
}

NOKIA_RUNTIME_EXPORT int nokia_runtime_speak_utf16(
    NokiaRuntime *r,const uint16_t *text,uint32_t len,const NokiaRuntimeCallbacks *cb) {
    uint32_t offset = 0, chunk, remaining;
    int incremental;
    if(!r||!text||!len||!r->dev){if(r)r->last_error=-3000;return 0;}
    r->cancelled=0;r->done=0;r->pending_count=0;r->callbacks=cb;r->last_error=0;r->frontend_ticks=0;r->audio_ticks=0;
    r->first_pcm_ticks=0;r->first_pcm_seen=0;r->text_chunks=0;
    r->seam_trimmed_samples=0;r->seam_quiet_count=0;
    r->seam_leading_seen=0;r->seam_leading_count=0;r->seam_skip_leading=0;
    r->pcm_pending_count=0;r->pcm_wrap_repairs=0;r->pcm_wrap_offset=0;
    r->pcm_unwrapped_previous=0;r->pcm_unwrapped_have=0;
    r->speak_started=clock();
    incremental = len > NOKIA_LONG_TEXT_THRESHOLD;
    r->seam_enabled = incremental ? 1u : 0u;
    while(offset < len && !r->cancelled) {
        remaining = len - offset;
        chunk = incremental ? next_text_chunk(text + offset, remaining) : remaining;
        if(!chunk || chunk > remaining){r->last_error=-3010;goto failed;}
        ++r->text_chunks;
        if(!synthesize_text_chunk(r,text + offset,chunk,offset+chunk<len))goto failed;
        offset += chunk;
        if(!r->cancelled && !seam_finish_chunk(r,offset==len)){
            r->last_error=-3006;goto failed;
        }
    }
    if(!finish_pcm_output(r)){r->last_error=-3008;goto failed;}
    r->callbacks=NULL;
    return offset == len || r->cancelled;
failed:
    finish_pcm_output(r);
    r->callbacks=NULL;return 0;
}

NOKIA_RUNTIME_EXPORT int nokia_runtime_last_error(const NokiaRuntime *r){return r?r->last_error:-1;}
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_klatt_failure(const NokiaRuntime *r){return r?r->klatt_failure:0;}
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_klatt_reg(const NokiaRuntime *r,uint32_t i){return r&&i<5u?r->klatt_regs[i]:0;}
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_klatt_count(const NokiaRuntime *r){return r?r->klatt_count:0;}
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_klatt_gain(const NokiaRuntime *r){return r?r->klatt_gain:0;}
NOKIA_RUNTIME_EXPORT uint64_t nokia_runtime_frontend_ticks(const NokiaRuntime *r){return r?r->frontend_ticks:0;}
NOKIA_RUNTIME_EXPORT uint64_t nokia_runtime_audio_ticks(const NokiaRuntime *r){return r?r->audio_ticks:0;}
NOKIA_RUNTIME_EXPORT uint64_t nokia_runtime_first_pcm_ticks(const NokiaRuntime *r){return r?r->first_pcm_ticks:0;}
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_text_chunks(const NokiaRuntime *r){return r?r->text_chunks:0;}
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_seam_trimmed_samples(const NokiaRuntime *r){return r?r->seam_trimmed_samples:0;}
