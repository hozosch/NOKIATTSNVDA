#!/usr/bin/env python3
"""Repair the 6650 single-threaded LDREX/STREX helper.

The lifted AOT leaves the exclusive-monitor temporary uninitialised.  Its
STREX at 0x80183130 can consequently report failure forever and loop back to
0x8018312c.  Synthesis is synchronous and has no competing guest thread, so
model the store-exclusive as succeeding and rejoin the original flag update
at 0x80183134.
"""
from __future__ import annotations

import argparse
from pathlib import Path


START = "L_80183130:"
END = "L_80183134:"

REPLACEMENT = r'''L_80183130:
    nokia_frontend_last_pc=0x80183130u;
    /* Native 6650 single-threaded store-exclusive. */
    if(!nokia_mem_store(&machine,(uint32_t)reg_r1,(uint32_t)reg_r3,4))
        return NOKIA_FRONTEND_UNSUPPORTED;
    reg_lr=0u;
    goto L_80183134;
'''


def patch_source(source: str) -> str:
    start = source.find(START)
    end = source.find(END, start + len(START))
    if start < 0 or end < 0:
        raise ValueError("6650 exclusive-store labels not found")
    if source.find(START, start + len(START)) >= 0:
        raise ValueError("6650 exclusive-store start label is ambiguous")
    if source.find(END, end + len(END)) >= 0:
        raise ValueError("6650 exclusive-store end label is ambiguous")
    return source[:start] + REPLACEMENT + source[end:]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    source = args.file.read_text(encoding="utf-8")
    try:
        source = patch_source(source)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    args.file.write_text(source, encoding="utf-8", newline="\n")
    print("native 6650 exclusive store installed: 0x80183130 -> 0x80183134")


if __name__ == "__main__":
    main()
