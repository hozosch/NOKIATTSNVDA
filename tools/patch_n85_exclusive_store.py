#!/usr/bin/env python3
"""Repair the N85 single-threaded LDREX/STREX helper."""
from __future__ import annotations

import argparse
from pathlib import Path


START = "L_802942d8:"
END = "L_802942dc:"

REPLACEMENT = r'''L_802942d8:
    nokia_frontend_last_pc=0x802942d8u;
    /* Native N85 single-threaded store-exclusive. */
    if(!nokia_mem_store(&machine,(uint32_t)reg_r1,(uint32_t)reg_r3,4))
        return NOKIA_FRONTEND_UNSUPPORTED;
    reg_lr=0u;
    goto L_802942dc;
'''


def patch_source(source: str) -> str:
    start = source.find(START)
    end = source.find(END, start + len(START))
    if start < 0 or end < 0:
        raise ValueError("N85 exclusive-store labels not found")
    if source.find(START, start + len(START)) >= 0:
        raise ValueError("N85 exclusive-store start label is ambiguous")
    if source.find(END, end + len(END)) >= 0:
        raise ValueError("N85 exclusive-store end label is ambiguous")
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
    print("native N85 exclusive store installed: 0x802942d8 -> 0x802942dc")


if __name__ == "__main__":
    main()
