#!/usr/bin/env python3
"""Add standalone 5320 native DSP boundaries and ROM veneers."""
from __future__ import annotations

import argparse
from pathlib import Path

ENTRY = 0x830F9DB0
# Small ARM literal veneers that may be called independently of the specialised
# Klatt entry. They only load a ROM function pointer and dispatch to it. Keeping
# them here avoids turning them back into AOT yields when their labels overlap
# code that is deliberately removed from the lifecycle trace.
VENEERS = {
    0x8310182C: 0x83101830,
    0x83101854: 0x83101858,
    0x8310188C: 0x83101890,
    0x83105F48: 0x83105F4C,
    0x83105F50: 0x83105F54,
    0x83105F58: 0x83105F5C,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('source', type=Path)
    args = ap.parse_args()
    text = args.source.read_text(encoding='utf-8')

    needle = '    uint32_t (*process)(void *, uint32_t);\n} NokiaFrontendHost;'
    repl = ('    uint32_t (*process)(void *, uint32_t);\n'
            '    int (*klatt)(void *, uint32_t regs[17]);\n'
            '} NokiaFrontendHost;')
    if needle not in text:
        raise ValueError('extended NokiaFrontendHost was not found')
    text = text.replace(needle, repl, 1)

    anchor = ('    case 0x5200022cu: if(!host||!host->process)goto unsupported; '
              'reg_r0=host->process(host->context,(uint32_t)reg_r1);reg_pc=reg_lr;goto dispatch;')
    veneer_cases = ''
    for pc, slot in VENEERS.items():
        veneer_cases += f'''
    case 0x{pc:08x}u: {{
        uint32_t veneer=(uint32_t)nokia_mem_load(&machine,UINT64_C(0x{slot:08x}),4);
        reg_TB=(veneer&1u)!=0;reg_pc=veneer&~1u;goto dispatch;
    }}'''
    block = anchor + veneer_cases + '''
    case 0x830f9db0u: {
        uint32_t kr[17]={(uint32_t)reg_r0,(uint32_t)reg_r1,(uint32_t)reg_r2,(uint32_t)reg_r3,
            (uint32_t)reg_r4,(uint32_t)reg_r5,(uint32_t)reg_r6,(uint32_t)reg_r7,
            (uint32_t)reg_r8,(uint32_t)reg_r9,(uint32_t)reg_r10,(uint32_t)reg_r11,
            (uint32_t)reg_r12,(uint32_t)reg_sp,(uint32_t)reg_lr,(uint32_t)reg_pc,
            ((uint32_t)(reg_NG&1u)<<31)|((uint32_t)(reg_ZR&1u)<<30)|
            ((uint32_t)(reg_CY&1u)<<29)|((uint32_t)(reg_OV&1u)<<28)};
        if(!host||!host->klatt||!host->klatt(host->context,kr))goto unsupported;
        reg_r0=kr[0];reg_r1=kr[1];reg_r2=kr[2];reg_r3=kr[3];reg_r4=kr[4];reg_r5=kr[5];
        reg_r6=kr[6];reg_r7=kr[7];reg_r8=kr[8];reg_r9=kr[9];reg_r10=kr[10];reg_r11=kr[11];
        reg_r12=kr[12];reg_sp=kr[13];reg_lr=kr[14];
        reg_NG=(kr[16]>>31)&1u;reg_ZR=(kr[16]>>30)&1u;
        reg_CY=(kr[16]>>29)&1u;reg_OV=(kr[16]>>28)&1u;
        reg_pc=reg_lr;goto dispatch;
    }'''
    if anchor not in text:
        raise ValueError('observer process dispatcher case was not found')
    text = text.replace(anchor, block, 1)
    args.source.write_text(text, encoding='utf-8', newline='\n')
    print(f'added native Klatt host boundary at {ENTRY:#x}')
    print('added standalone ROM veneers:', ', '.join(f'{pc:#x}' for pc in VENEERS))


if __name__ == '__main__':
    main()
