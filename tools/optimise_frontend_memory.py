#!/usr/bin/env python3
"""Add a fast 64-KiB page table to the generated Nokia frontend runtime.

The split AOT frontend currently resolves every guest load/store by walking the
five synthetic RAM regions and then checking ROM.  That is correct but leaves
an emulator-shaped hot path in otherwise native C.  This post-processing step
adds a direct page table for all full 64-KiB chunks of heap, traps, pool, stack
and ROM.  Small/edge ranges (notably the 4-KiB vtable and the final partial ROM
page) keep using the existing checked fallback, so semantics stay unchanged.
"""
from __future__ import annotations

import argparse
from pathlib import Path


OLD_LOAD = (
    "static uint64_t nokia_mem_load(NokiaFrontendMachine*m,uint64_t address,unsigned size) "
    "{ uint64_t v=0;uint32_t a=(uint32_t)address;uint8_t*p=segment(m,a,size);"
    "if(p)memcpy(&v,p,size);else if(a>=m->rom_base&&(uint64_t)(a-m->rom_base)+size<=m->rom_size)"
    "memcpy(&v,m->rom+(a-m->rom_base),size);else{if(!m->bad_address)m->bad_address=a;"
    "return UINT64_MAX;}return v; }"
)

OLD_STORE_PREFIX = (
    "static int nokia_mem_store(NokiaFrontendMachine*m,uint64_t address,uint64_t value,unsigned size) "
    "{ uint32_t a=(uint32_t)address;uint8_t*p=segment(m,a,size);if(!p){if(!m->bad_address)m->bad_address=a;"
    "return 0;}nokia_frontend_dirty_mask|=nokia_dirty_segment(a);memcpy(p,&value,size);return 1; }"
)

FAST_RUNTIME = r'''static uint8_t *nokia_fast_pages[65536];
static uint8_t nokia_fast_writable[65536];
static const void *nokia_fast_heap_key,*nokia_fast_traps_key,*nokia_fast_pool_key,*nokia_fast_stack_key,*nokia_fast_rom_key;
static uint32_t nokia_fast_rom_base_key;
static size_t nokia_fast_rom_size_key;
static void nokia_fast_map(uint32_t guest,uint8_t*host,size_t size,int writable){
    size_t pages=size>>16;uint32_t index=guest>>16;size_t i;
    for(i=0;i<pages&&index+i<65536u;++i){nokia_fast_pages[index+i]=host+(i<<16);nokia_fast_writable[index+i]=(uint8_t)(writable!=0);}
}
static void nokia_fast_init(NokiaFrontendMachine*m){
    if(nokia_fast_heap_key==m->heap&&nokia_fast_traps_key==m->traps&&nokia_fast_pool_key==m->pool&&
       nokia_fast_stack_key==m->stack&&nokia_fast_rom_key==m->rom&&nokia_fast_rom_base_key==m->rom_base&&
       nokia_fast_rom_size_key==m->rom_size)return;
    memset(nokia_fast_pages,0,sizeof(nokia_fast_pages));memset(nokia_fast_writable,0,sizeof(nokia_fast_writable));
    nokia_fast_map(0x50000000u,m->heap,0x100000u,1);
    nokia_fast_map(0x52000000u,m->traps,0x10000u,1);
    nokia_fast_map(0x53000000u,m->pool,0x800000u,1);
    nokia_fast_map(0x60000000u,m->stack,0x100000u,1);
    if((m->rom_base&0xffffu)==0)nokia_fast_map(m->rom_base,(uint8_t*)(uintptr_t)m->rom,m->rom_size&~(size_t)0xffffu,0);
    nokia_fast_heap_key=m->heap;nokia_fast_traps_key=m->traps;nokia_fast_pool_key=m->pool;nokia_fast_stack_key=m->stack;
    nokia_fast_rom_key=m->rom;nokia_fast_rom_base_key=m->rom_base;nokia_fast_rom_size_key=m->rom_size;
}
static uint8_t*nokia_fast_ptr(uint32_t a,unsigned size,int write){
    uint8_t*base=nokia_fast_pages[a>>16];uint32_t off=a&0xffffu;
    if(!base||(uint64_t)off+size>0x10000u||(write&&!nokia_fast_writable[a>>16]))return NULL;
    return base+off;
}
static uint64_t nokia_mem_load(NokiaFrontendMachine*m,uint64_t address,unsigned size) { uint64_t v=0;uint32_t a=(uint32_t)address;uint8_t*p=nokia_fast_ptr(a,size,0);if(!p)p=segment(m,a,size);if(p)memcpy(&v,p,size);else if(a>=m->rom_base&&(uint64_t)(a-m->rom_base)+size<=m->rom_size)memcpy(&v,m->rom+(a-m->rom_base),size);else{if(!m->bad_address)m->bad_address=a;return UINT64_MAX;}return v; }'''

FAST_STORE = (
    "static int nokia_mem_store(NokiaFrontendMachine*m,uint64_t address,uint64_t value,unsigned size) "
    "{ uint32_t a=(uint32_t)address;uint8_t*p=nokia_fast_ptr(a,size,1);if(!p)p=segment(m,a,size);if(!p){if(!m->bad_address)m->bad_address=a;"
    "return 0;}nokia_frontend_dirty_mask|=nokia_dirty_segment(a);memcpy(p,&value,size);return 1; }"
)


def optimise(source: str) -> str:
    if OLD_LOAD not in source:
        raise ValueError("frontend memory-load helper was not recognised")
    source = source.replace(OLD_LOAD, FAST_RUNTIME, 1)
    if OLD_STORE_PREFIX not in source:
        raise ValueError("frontend memory-store helper was not recognised")
    source = source.replace(OLD_STORE_PREFIX, FAST_STORE, 1)
    needle = "    NokiaFrontendMachine*machine_ptr=&machine_storage;\n"
    if needle not in source:
        raise ValueError("frontend machine initialisation was not recognised")
    source = source.replace(needle, needle + "    nokia_fast_init(&machine_storage);\n", 1)
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    text = args.source.read_text(encoding="utf-8")
    args.source.write_text(optimise(text), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
