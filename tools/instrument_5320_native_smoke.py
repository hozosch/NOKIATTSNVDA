#!/usr/bin/env python3
"""Prepare bounded diagnostic sources for the 5320 native-only smoke test."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def patch_runtime(src: str) -> str:
    replacements = {
        'if(!native_call_l(r,r->pt_new,a,3,&pt)||!pt)goto failed;':
            'if(!native_call_l(r,r->pt_new,a,3,&pt)||!pt){r->last_error=-3101;goto failed;}',
        'if(!native_call(r,r->seg_set_style_id,a,2,&res))goto failed;':
            'if(!native_call(r,r->seg_set_style_id,a,2,&res)){r->last_error=-3102;goto failed;}',
        'if(!native_call(r,r->seg_set_text_ptr,a,2,&res))goto failed;':
            'if(!native_call(r,r->seg_set_text_ptr,a,2,&res)){r->last_error=-3103;goto failed;}',
        'if(!native_call_l(r,r->pt_add_segment,a,3,&res))goto failed;':
            'if(!native_call_l(r,r->pt_add_segment,a,3,&res)){r->last_error=-3104;goto failed;}',
        'if(!native_call_l(r,r->dev_prime,a,2,&res))goto failed;':
            'if(!native_call_l(r,r->dev_prime,a,2,&res)){r->last_error=-3105;goto failed;}',
        'if(!native_call_l(r,r->dev_synthesize,a,2,&res))goto failed;':
            'if(!native_call_l(r,r->dev_synthesize,a,2,&res)){r->last_error=-3106;goto failed;}',
        'if(!native_call(r,r->run_if_ready,a,2,&res))goto failed;':
            'if(!native_call(r,r->run_if_ready,a,2,&res)){r->last_error=-3107;goto failed;}',
    }
    for old, new in replacements.items():
        if old not in src:
            raise SystemExit(f'lifecycle stage marker not found: {old}')
        src = src.replace(old, new, 1)
    old = 'if(++loops>100000u){r->last_error=-3004;goto failed;}'
    new = 'if(++loops>2000u){r->last_error=-3004;goto failed;}'
    if old not in src:
        raise SystemExit('scheduler pump limit marker not found')
    return src.replace(old, new, 1)


def patch_aot(aot: str) -> tuple[str, int]:
    chunk0 = 'static int nokia_frontend_chunk_0('
    if chunk0 not in aot:
        raise SystemExit('first AOT chunk marker not found')
    decl_lines = [
        'static uint32_t nokia_frontend_debug_budget;',
        'static uint32_t nokia_frontend_debug_r0,nokia_frontend_debug_r1,nokia_frontend_debug_r2,nokia_frontend_debug_r3;',
        'static uint32_t nokia_frontend_debug_r4,nokia_frontend_debug_r5,nokia_frontend_debug_r6,nokia_frontend_debug_r7,nokia_frontend_debug_sp;',
        'static uint32_t nokia_frontend_debug_s0,nokia_frontend_debug_s2,nokia_frontend_debug_s4;',
    ]
    for label in ('r0','r1','r2','r3','r4','r5','r6','r7','sp','s0','s2','s4'):
        decl_lines.append(
            f'NOKIA_EXPORT uint32_t nokia_frontend_debug_{label}_value(void)'
            f'{{return nokia_frontend_debug_{label};}}'
        )
    debug_decl = '\n'.join(decl_lines) + '\n\n'
    aot = aot.replace(chunk0, debug_decl + chunk0, 1)

    reset = '    nokia_frontend_dirty_mask=0;'
    if reset not in aot:
        raise SystemExit('AOT call reset marker not found')
    aot = aot.replace(reset, reset + '\n    nokia_frontend_debug_budget=500000u;', 1)

    pat = re.compile(r'(nokia_frontend_last_pc=0x[0-9a-f]+u;)')
    capture = (
        r'\1 if(!nokia_frontend_debug_budget--){'
        r'nokia_frontend_debug_r0=(uint32_t)reg_r0;nokia_frontend_debug_r1=(uint32_t)reg_r1;'
        r'nokia_frontend_debug_r2=(uint32_t)reg_r2;nokia_frontend_debug_r3=(uint32_t)reg_r3;'
        r'nokia_frontend_debug_r4=(uint32_t)reg_r4;nokia_frontend_debug_r5=(uint32_t)reg_r5;'
        r'nokia_frontend_debug_r6=(uint32_t)reg_r6;nokia_frontend_debug_r7=(uint32_t)reg_r7;'
        r'nokia_frontend_debug_sp=(uint32_t)reg_sp;'
        r'nokia_frontend_debug_s0=(uint32_t)nokia_mem_load(&machine,(uint32_t)reg_r4,2);'
        r'nokia_frontend_debug_s2=(uint32_t)nokia_mem_load(&machine,(uint32_t)reg_r4+2u,2);'
        r'nokia_frontend_debug_s4=(uint32_t)nokia_mem_load(&machine,(uint32_t)reg_r4+4u,4);'
        r'return NOKIA_FRONTEND_YIELDED;}'
    )
    aot, count = pat.subn(capture, aot)
    if count < 1000:
        raise SystemExit(f'unexpectedly few AOT labels instrumented: {count}')

    old_yield = 'if(result==NOKIA_FRONTEND_YIELDED){nokia_frontend_record_yield(pc,3u);goto yielded;}'
    new_yield = 'if(result==NOKIA_FRONTEND_YIELDED){nokia_frontend_record_yield(nokia_frontend_last_pc,3u);goto yielded;}'
    if old_yield not in aot:
        raise SystemExit('chunk yield recorder marker not found')
    return aot.replace(old_yield, new_yield, 1), count


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('runtime_in', type=Path)
    ap.add_argument('runtime_out', type=Path)
    ap.add_argument('aot', type=Path)
    args = ap.parse_args()

    runtime = patch_runtime(args.runtime_in.read_text(encoding='utf-8'))
    args.runtime_out.parent.mkdir(parents=True, exist_ok=True)
    args.runtime_out.write_text(runtime, encoding='utf-8', newline='\n')

    aot, count = patch_aot(args.aot.read_text(encoding='utf-8'))
    args.aot.write_text(aot, encoding='utf-8', newline='\n')
    print('lifecycle failures tagged -3101..-3107')
    print('fast smoke scheduler pump limit: 2000')
    print('AOT per-call label budget: 500000; register capture enabled; labels:', count)


if __name__ == '__main__':
    main()
