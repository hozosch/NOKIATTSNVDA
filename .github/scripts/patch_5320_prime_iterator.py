#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path

START='L_830e1952:'
END='L_830e195e:'

REPLACEMENT=r'''L_830e1954:
L_830e1956:
L_830e1958:
L_830e195a:
L_830e195c:
    goto L_830e1952;
L_830e1952:
    nokia_frontend_last_pc=0x830e1952u;
    {
        uint32_t off=(uint32_t)nokia_mem_load(&machine,(uint32_t)reg_r4,4);
        uint32_t val=(uint32_t)nokia_mem_load(&machine,(uint32_t)reg_r5+off,2);
        uint32_t next=off+2u;
        if(!nokia_mem_store(&machine,(uint32_t)reg_r4,next,4)) return NOKIA_FRONTEND_UNSUPPORTED;
        reg_r0=val;
        reg_r1=next;
        reg_CY=(uint64_t)nokia_carry(off,2u,4);
        reg_OV=(uint64_t)nokia_scarry(off,2u,4);
        reg_ZR=(uint64_t)(next==0u);
        reg_NG=(uint64_t)((int32_t)next<0);
        reg_mult_addr=(uint64_t)((uint32_t)reg_sp);
        reg_r4=(uint64_t)nokia_mem_load(&machine,(uint32_t)reg_mult_addr,4); reg_mult_addr+=4u;
        reg_r5=(uint64_t)nokia_mem_load(&machine,(uint32_t)reg_mult_addr,4); reg_mult_addr+=4u;
        reg_r6=(uint64_t)nokia_mem_load(&machine,(uint32_t)reg_mult_addr,4); reg_mult_addr+=4u;
        reg_pc=(uint64_t)nokia_mem_load(&machine,(uint32_t)reg_mult_addr,4); reg_mult_addr+=4u;
        reg_sp=reg_mult_addr;
        reg_TB=(uint64_t)(((uint32_t)reg_pc&1u)!=0u);
        reg_pc=(uint64_t)((uint32_t)reg_pc&~1u);
        return NOKIA_FRONTEND_CONTINUE;
    }
'''

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('file',type=Path); a=ap.parse_args()
    s=a.file.read_text(encoding='utf-8')
    i=s.find(START); j=s.find(END,i+len(START))
    if i<0 or j<0: raise SystemExit('Prime iterator labels not found')
    s=s[:i]+REPLACEMENT+s[j:]
    a.file.write_text(s,encoding='utf-8',newline='\n')
    print('native Prime iterator installed with resume aliases: 0x830e1952 -> return')
if __name__=='__main__': main()
