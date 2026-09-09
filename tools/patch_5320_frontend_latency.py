#!/usr/bin/env python3
"""Collapse the hottest verified Nokia 5320 frontend iterator paths.

The lifted frontend preserves each ARM instruction as an individual C label.
That is useful while reconstructing control flow, but two ordinary Prime paths
cross the split-AOT dispatcher tens of thousands of times before the first PCM
buffer.  The replacements below preserve the guest registers, condition flags
and final memory while executing the verified loops directly in C.
"""
from __future__ import annotations

import argparse
from pathlib import Path


ITERATOR_ENTRY = "L_830e1934:\n"
FILL_LOOP_ENTRY = "L_830dbae8:\n"
DISPATCH_ENTRY = (
    "    case 0x8019db50u: reg_r0=nokia_mem_load(&machine,0x53000010u,4);"
    "reg_pc=reg_lr;goto dispatch;"
)

ITERATOR = r'''L_830e1934:
    /* Native 5320 latency path: bounded 16-bit Prime iterator. */
    nokia_frontend_last_pc=0x830e1934u;
    {
        uint32_t base=(uint32_t)reg_r0;
        uint32_t cursor_address=(uint32_t)reg_r1;
        uint32_t limit=(uint32_t)reg_r2;
        uint32_t offset=(uint32_t)nokia_mem_load(&machine,cursor_address,4);
        if(offset&1u){
            ++offset;
            if(!nokia_mem_store(&machine,cursor_address,offset,4))
                return NOKIA_FRONTEND_UNSUPPORTED;
        }
        if(offset>limit) goto L_830e1934_slow;
        {
            uint32_t value=(uint32_t)nokia_mem_load(&machine,base+offset,2);
            uint32_t next=offset+2u;
            if(!nokia_mem_store(&machine,cursor_address,next,4))
                return NOKIA_FRONTEND_UNSUPPORTED;
            reg_r0=value;reg_r1=next;
            reg_CY=(uint64_t)nokia_carry(offset,2u,4);
            reg_OV=(uint64_t)nokia_scarry(offset,2u,4);
            reg_ZR=(uint64_t)(next==0u);
            reg_NG=(uint64_t)((int32_t)next<0);
            reg_TB=(uint64_t)(((uint32_t)reg_lr&1u)!=0u);
            reg_pc=(uint64_t)((uint32_t)reg_lr&~1u);
            return NOKIA_FRONTEND_CONTINUE;
        }
    }
L_830e1934_slow:
'''

FILL_LOOP = r'''L_830dbae8:
    /* Native 5320 latency path: packed Prime segment fill loop. */
    nokia_frontend_last_pc=0x830dbae8u;
    {
        uint32_t base=(uint32_t)nokia_mem_load(&machine,(uint32_t)reg_sp+12u,4);
        uint32_t cursor_address=(uint32_t)nokia_mem_load(&machine,(uint32_t)reg_sp+32u,4);
        uint32_t limit=(uint32_t)nokia_mem_load(&machine,(uint32_t)reg_sp+28u,4);
        uint32_t row_offset=(uint32_t)nokia_mem_load(&machine,(uint32_t)reg_sp+16u,4);
        uint32_t row_table=(uint32_t)nokia_mem_load(&machine,(uint32_t)reg_r4+8u,4);
        uint32_t destination=(uint32_t)nokia_mem_load(&machine,row_table+row_offset,4);
        uint32_t total=(uint32_t)nokia_mem_load(&machine,(uint32_t)reg_sp+8u,4);
        uint32_t index=(uint32_t)reg_r5;
        uint32_t count=(uint32_t)reg_r6;
        while(index<count){
            uint32_t offset=(uint32_t)nokia_mem_load(&machine,cursor_address,4);
            uint32_t value;
            if(offset&1u){
                ++offset;
                if(!nokia_mem_store(&machine,cursor_address,offset,4))
                    return NOKIA_FRONTEND_UNSUPPORTED;
            }
            if(offset>limit){
                if(!nokia_mem_store(&machine,(uint32_t)reg_sp+8u,total,4))
                    return NOKIA_FRONTEND_UNSUPPORTED;
                reg_r5=index;reg_r0=base;reg_r1=cursor_address;reg_r2=limit;
                goto L_830dbae8_slow;
            }
            value=(uint32_t)nokia_mem_load(&machine,base+offset,2);
            if(!nokia_mem_store(&machine,cursor_address,offset+2u,4) ||
               !nokia_mem_store(&machine,destination+(index<<1),value,2))
                return NOKIA_FRONTEND_UNSUPPORTED;
            ++total;++index;
        }
        if(!nokia_mem_store(&machine,(uint32_t)reg_sp+8u,total,4))
            return NOKIA_FRONTEND_UNSUPPORTED;
        reg_r0=total;reg_r1=destination;reg_r2=row_offset;reg_r5=index;
        reg_CY=(uint64_t)(count<=index);
        reg_OV=(uint64_t)nokia_sborrow(index,count,4);
        reg_ZR=(uint64_t)(index==count);
        reg_NG=(uint64_t)((int32_t)(index-count)<0);
        goto L_830dbb08;
    }
L_830dbae8_slow:
'''

POINTER_HELPER = r'''    /* Native 5320 latency path: fixed-stride element address. */
    case 0x8053bc64u: {
        uint32_t object=(uint32_t)reg_r0;
        uint32_t base=(uint32_t)nokia_mem_load(&machine,object+16u,4);
        uint32_t stride=(uint32_t)nokia_mem_load(&machine,object+8u,4);
        uint32_t product=stride*(uint32_t)reg_r1;
        uint32_t result=base+product;
        reg_r0=result;reg_r2=base;
        reg_CY=(uint64_t)nokia_carry(base,product,4);
        reg_OV=(uint64_t)nokia_scarry(base,product,4);
        reg_ZR=(uint64_t)(result==0u);
        reg_NG=(uint64_t)((int32_t)result<0);
        reg_TB=(uint64_t)(((uint32_t)reg_lr&1u)!=0u);
        reg_pc=(uint64_t)((uint32_t)reg_lr&~1u);
        goto dispatch;
    }
'''


def _replace_once(source: str, needle: str, replacement: str, label: str) -> str:
    count = source.count(needle)
    if count != 1:
        raise ValueError(f"expected exactly one {label}, found {count}")
    return source.replace(needle, replacement, 1)


def patch_source(source: str) -> str:
    if "Native 5320 latency path" in source:
        raise ValueError("5320 frontend latency path is already installed")
    source = _replace_once(source, ITERATOR_ENTRY, ITERATOR, "Prime iterator")
    source = _replace_once(source, FILL_LOOP_ENTRY, FILL_LOOP, "Prime fill loop")
    return _replace_once(
        source,
        DISPATCH_ENTRY,
        POINTER_HELPER + DISPATCH_ENTRY,
        "frontend dispatcher anchor",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    text = args.source.read_text(encoding="utf-8")
    args.source.write_text(
        patch_source(text), encoding="utf-8", newline="\n"
    )
    print(
        "native 5320 latency paths installed: iterator, segment fill and "
        "fixed-stride helper"
    )


if __name__ == "__main__":
    main()
