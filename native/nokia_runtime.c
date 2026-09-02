#include "nokia_runtime.h"

#include <stdlib.h>
#include <string.h>
#include <time.h>

#define HEAP_BASE  0x50000000u
#define VT_BASE    0x51000000u
#define TRAP_BASE  0x52000000u
#define POOL_BASE  0x53000000u
#define STACK_BASE 0x60000000u
#define ROM_BASE   0x80000000u
#define RET_MAGIC  0x7fff0000u
#define HEAP_SIZE  0x100000u
#define VT_SIZE    0x1000u
#define TRAP_SIZE  0x10000u
#define POOL_SIZE  0x800000u
#define STACK_SIZE 0x100000u
#define SAMPLE_RATE 16000u
#define SNAP_WORDS 27u

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

struct NokiaRuntime {
    uint8_t *rom;
    size_t rom_size;
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
    uint64_t frontend_ticks, audio_ticks;
    const NokiaRuntimeCallbacks *callbacks;
    uint32_t *pending;
    uint32_t pending_count, pending_capacity;
    uint8_t done;
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
    if (!write && a >= ROM_BASE && e <= (uint64_t)ROM_BASE + r->rom_size)
        return r->rom + (a - ROM_BASE);
    return NULL;
}

static int guest_read(NokiaRuntime *r, uint32_t a, void *out, uint32_t n) {
    uint8_t *p = guest_ptr(r, a, n, 0);
    if (!p) return 0;
    memcpy(out, p, n); return 1;
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

static uint32_t rt_process(void *ctx, uint32_t descriptor) {
    NokiaRuntime *r = (NokiaRuntime *)ctx;
    uint8_t *data = NULL;
    uint32_t bytes = 0;
    clock_t before = clock();
    if (!descriptor_data(r, descriptor, &data, &bytes) ||
        !pending_add(r, descriptor)) {
        r->last_error = -1401; return 0;
    }
    if (bytes && r->callbacks && r->callbacks->pcm)
        r->callbacks->pcm(r->callbacks->user, (const int16_t *)data,
                          bytes / 2u, SAMPLE_RATE);
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
                                  r->rom, ROM_BASE, r->rom_size, after)) {
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

static NokiaRuntime *alloc_runtime(const uint8_t *rom, size_t rom_size) {
    NokiaRuntime *r;
    if (!rom || !rom_size) return NULL;
    r = (NokiaRuntime *)calloc(1, sizeof(*r)); if (!r) return NULL;
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
    NokiaRuntime *r = alloc_runtime(rom, rom_size);
    (void)root; (void)voice_id;
    if (r) { r->language_id = language_id; r->last_error = -1000; }
    return r;
}

NOKIA_RUNTIME_EXPORT NokiaRuntime *nokia_runtime_create_5320_snapshot(
    const uint8_t *rom, size_t rom_size,
    const uint8_t *s, size_t snapshot_size) {
    NokiaRuntime *r;
    const uint8_t *p, *end;
    uint32_t w[SNAP_WORDS], i, regions, used, freec;
    static const uint8_t magic[8] = {'N','K','5','3','2','0','S','1'};
    if (!s || snapshot_size < 8u + SNAP_WORDS * 4u || memcmp(s, magic, 8)) return NULL;
    p = s + 8; end = s + snapshot_size;
    for (i = 0; i < SNAP_WORDS; ++i) { w[i] = rd32(p); p += 4; }
    if (w[0] != 1u) return NULL;
    regions = w[24]; used = w[25]; freec = w[26];
    if ((uint64_t)(p - s) + (uint64_t)regions * 12u +
        (uint64_t)(used + freec) * 8u > snapshot_size) return NULL;
    r = alloc_runtime(rom, rom_size); if (!r) return NULL;
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

NOKIA_RUNTIME_EXPORT void nokia_runtime_destroy(NokiaRuntime *r) {
    if (!r) return;
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
                                r->rom,ROM_BASE,r->rom_size,regs,RET_MAGIC,&r->host);
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

NOKIA_RUNTIME_EXPORT int nokia_runtime_speak_utf16(
    NokiaRuntime *r,const uint16_t *text,uint32_t len,const NokiaRuntimeCallbacks *cb) {
    uint32_t txt=0,e8=0,e16=0,pt=0,seg=0,res=0,a[3],loops=0;
    clock_t start;
    if(!r||!text||!len||!r->dev){if(r)r->last_error=-3000;return 0;}
    r->cancelled=0;r->done=0;r->pending_count=0;r->callbacks=cb;r->last_error=0;r->frontend_ticks=0;r->audio_ticks=0;
    start=clock();
    txt=ptrc16(r,text,len);e8=ptrc8(r);e16=ptrc16(r,(const uint16_t*)L"",0);
    if(!txt||!e8||!e16){r->last_error=-3001;goto failed;}
    a[0]=txt;a[1]=e8;a[2]=e16;if(!native_call_l(r,r->pt_new,a,3,&pt)||!pt)goto failed;
    seg=rt_alloc(r,0x80u);if(!seg){r->last_error=-3002;goto failed;}
    a[0]=seg;a[1]=r->style_id;if(!native_call(r,r->seg_set_style_id,a,2,&res))goto failed;
    a[0]=seg;a[1]=txt;if(!native_call(r,r->seg_set_text_ptr,a,2,&res))goto failed;
    a[0]=pt;a[1]=seg;a[2]=0;if(!native_call_l(r,r->pt_add_segment,a,3,&res))goto failed;
    a[0]=r->dev;a[1]=pt;if(!native_call_l(r,r->dev_prime,a,2,&res))goto failed;
    /* Neutral-rate native-only milestone: pitch is already applied in the
       Klatt callback. The existing prosody-rate scaler will move here next. */
    a[0]=r->dev;a[1]=1;if(!native_call_l(r,r->dev_synthesize,a,2,&res))goto failed;
    r->frontend_ticks=(uint64_t)(clock()-start);
    while(!r->done&&!r->cancelled){
        if(!drain(r))goto failed;
        a[0]=r->scheduler_error;a[1]=(uint32_t)(int32_t)-100;
        if(!native_call(r,r->run_if_ready,a,2,&res))goto failed;
        if(!res&&!r->pending_count&&!r->done){r->last_error=-3003;goto failed;}
        if(++loops>100000u){r->last_error=-3004;goto failed;}
    }
    if(!drain(r))goto failed;
    if(r->cancelled){a[0]=r->dev;native_call(r,r->dev_stop,a,1,&res);}
    a[0]=pt;native_call(r,r->pt_delete,a,1,&res);pt=0;
    if(seg){rt_free(r,seg);seg=0;}free_desc(r,txt);free_desc(r,e8);free_desc(r,e16);
    r->callbacks=NULL;return r->done||r->cancelled;
failed:
    if(pt){a[0]=pt;native_call(r,r->pt_delete,a,1,&res);}
    if(seg)rt_free(r,seg);if(txt)free_desc(r,txt);if(e8)free_desc(r,e8);if(e16)free_desc(r,e16);
    r->callbacks=NULL;if(!r->last_error)r->last_error=-3099;return 0;
}

NOKIA_RUNTIME_EXPORT int nokia_runtime_last_error(const NokiaRuntime *r){return r?r->last_error:-1;}
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_klatt_failure(const NokiaRuntime *r){return r?r->klatt_failure:0;}
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_klatt_reg(const NokiaRuntime *r,uint32_t i){return r&&i<5u?r->klatt_regs[i]:0;}
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_klatt_count(const NokiaRuntime *r){return r?r->klatt_count:0;}
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_klatt_gain(const NokiaRuntime *r){return r?r->klatt_gain:0;}
NOKIA_RUNTIME_EXPORT uint64_t nokia_runtime_frontend_ticks(const NokiaRuntime *r){return r?r->frontend_ticks:0;}
NOKIA_RUNTIME_EXPORT uint64_t nokia_runtime_audio_ticks(const NokiaRuntime *r){return r?r->audio_ticks:0;}
