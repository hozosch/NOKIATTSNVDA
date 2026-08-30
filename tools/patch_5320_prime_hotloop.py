#!/usr/bin/env python3
"""Replace the verified hot 5320 Prime scan loop with direct C.

The original Thumb loop from 0x830db9ea through 0x830dba1c has been compared
against a known-good Unicorn run. It builds an array of byte-buffer segment
starts and tracks the maximum segment length. Keeping this as dozens of AOT
labels per byte is needlessly expensive, so collapse it to an equivalent C
loop and rejoin at the original epilogue 0x830dba1e.
"""
from __future__ import annotations

import argparse
from pathlib import Path

LABEL = "L_830db9ea:\n"
HOT = r'''L_830db9ea:
    nokia_frontend_last_pc=0x830db9eau;
    {
        uint32_t hp_count=(uint32_t)nokia_mem_load(&machine,((uint32_t)reg_r4)+0u,2);
        uint32_t hp_max=(uint32_t)nokia_mem_load(&machine,((uint32_t)reg_r4)+2u,2);
        uint32_t hp_out=(uint32_t)nokia_mem_load(&machine,((uint32_t)reg_r4)+4u,4);
        uint32_t hp_limit=(uint32_t)nokia_mem_load(&machine,((uint32_t)reg_sp)+8u,4);
        uint32_t hp_pos=0u;
        uint32_t hp_i=0u;
        for(;hp_i<hp_count;++hp_i){
            uint32_t hp_start=hp_pos;
            uint32_t hp_ptr=((uint32_t)reg_r5)+hp_start;
            if(!nokia_mem_store(&machine,hp_out+(hp_i<<2),hp_ptr,4)) return NOKIA_FRONTEND_UNSUPPORTED;
            while(hp_pos<hp_limit){
                uint32_t hp_b=(uint32_t)nokia_mem_load(&machine,((uint32_t)reg_r5)+hp_pos,1);
                if(hp_b==255u) break;
                ++hp_pos;
            }
            {
                uint32_t hp_span=hp_pos-hp_start;
                if(hp_span>hp_max){
                    hp_max=hp_span;
                    if(!nokia_mem_store(&machine,((uint32_t)reg_r4)+2u,hp_max,2)) return NOKIA_FRONTEND_UNSUPPORTED;
                }
            }
            ++hp_pos;
        }
    }
    goto L_830dba1e;
'''


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument('source',type=Path)
    args=ap.parse_args()
    text=args.source.read_text(encoding='utf-8')
    if text.count(LABEL)!=1:
        raise SystemExit('expected exactly one Prime hot-loop entry label')
    start=text.index(LABEL)
    end=text.index('L_830db9ec:\n',start)
    # Replace the entry label itself. The legacy inner labels remain in the
    # chunk for resume compatibility, but normal execution bypasses them.
    text=text[:start]+HOT+text[end:]
    args.source.write_text(text,encoding='utf-8',newline='\n')
    if text.count('goto L_830dba1e;') < 1:
        raise SystemExit('Prime hot-loop patch verification failed')
    print('native Prime hot loop installed: 0x830db9ea -> 0x830dba1e')


if __name__=='__main__':
    main()
