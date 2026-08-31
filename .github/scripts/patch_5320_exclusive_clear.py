#!/usr/bin/env python3
"""Repair the 5320 single-threaded LDREX/STREX clear helper.

The lifted AOT leaves the exclusive-monitor temporary uninitialised.  Its
STREX at 0x8019e4e0 consequently reports failure forever and loops back to
0x8019e4dc.  The native runtime invokes this ROM lifecycle synchronously, so
there is no competing guest thread: model the store-exclusive as succeeding
and then rejoin the original post-loop code at 0x8019e4ec.
"""
from __future__ import annotations

import argparse
from pathlib import Path


START = "L_8019e4dc:"
END = "L_8019e4ec:"

REPLACEMENT = r'''L_8019e4dc:
    nokia_frontend_last_pc=0x8019e4dcu;
    reg_r12=(uint64_t)nokia_mem_load(&machine,(uint32_t)reg_r1,4);
    if(!nokia_mem_store(&machine,(uint32_t)reg_r1,(uint32_t)reg_r3,4))
        return NOKIA_FRONTEND_UNSUPPORTED;
    reg_lr=0u;
    reg_ZR=1u;
    reg_NG=0u;
    goto L_8019e4ec;
L_8019e4e0:
L_8019e4e4:
L_8019e4e8:
    goto L_8019e4dc;
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    source = args.file.read_text(encoding="utf-8")
    start = source.find(START)
    end = source.find(END, start + len(START))
    if start < 0 or end < 0:
        raise SystemExit("5320 exclusive-clear labels not found")
    source = source[:start] + REPLACEMENT + source[end:]
    args.file.write_text(source, encoding="utf-8", newline="\n")
    print("native 5320 exclusive clear installed: 0x8019e4dc -> 0x8019e4ec")


if __name__ == "__main__":
    main()
