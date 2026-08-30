#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path

START='L_830dbafe:'
END='L_830dbb04:'

REPLACEMENT=r'''L_830dbafe:
    nokia_frontend_last_pc=0x830dbafeu;
    {
        uint32_t p=(uint32_t)reg_sp+8u;
        uint32_t n=(uint32_t)nokia_mem_load(&machine,p,4)+1u;
        if(!nokia_mem_store(&machine,p,n,4)) return NOKIA_FRONTEND_UNSUPPORTED;
        reg_r0=n;
        reg_r5=((uint32_t)reg_r5)+1u;
        goto L_830dbb04;
    }
L_830dbb00:
    nokia_frontend_last_pc=0x830dbb00u;
    {
        uint32_t p=(uint32_t)reg_sp+8u;
        if(!nokia_mem_store(&machine,p,(uint32_t)reg_r0,4)) return NOKIA_FRONTEND_UNSUPPORTED;
        reg_r5=((uint32_t)reg_r5)+1u;
        goto L_830dbb04;
    }
L_830dbb02:
    nokia_frontend_last_pc=0x830dbb02u;
    reg_r5=((uint32_t)reg_r5)+1u;
    goto L_830dbb04;
'''

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('file',type=Path); a=ap.parse_args()
    s=a.file.read_text(encoding='utf-8')
    i=s.find(START); j=s.find(END,i+len(START))
    if i<0 or j<0: raise SystemExit('Prime counter-loop labels not found')
    s=s[:i]+REPLACEMENT+s[j:]
    a.file.write_text(s,encoding='utf-8',newline='\n')
    print('native Prime counter loop installed: 0x830dbafe..0x830dbb02; original compare preserved')
if __name__=='__main__': main()
