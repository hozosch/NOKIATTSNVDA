#!/usr/bin/env python3
"""Add the standalone 5320 native Klatt boundary to a split frontend source."""
from __future__ import annotations

import argparse
from pathlib import Path

ENTRY = 0x830F9DB0


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
    block = anchor + '''
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


if __name__ == '__main__':
    main()
