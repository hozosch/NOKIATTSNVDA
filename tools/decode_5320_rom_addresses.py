#!/usr/bin/env python3
"""Decode selected 5320 ROM addresses with pypcode for AOT gap repair."""
from __future__ import annotations
import argparse
from pathlib import Path
import pypcode

ROM_BASE = 0x80000000


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("rom", type=Path)
    p.add_argument("addresses", nargs="+")
    args = p.parse_args()
    rom = args.rom.read_bytes()
    for raw in args.addresses:
        address = int(raw, 0)
        offset = address - ROM_BASE
        print(f"=== 0x{address:08x} ===")
        print("bytes:", rom[offset:offset+16].hex(" "))
        for lang in ("ARM:LE:32:v8", "ARM:LE:32:v8T"):
            try:
                ctx = pypcode.Context(lang)
                trans = ctx.translate(rom[offset:offset+16], base_address=address, max_instructions=2)
                print(lang)
                for op in trans.ops:
                    print(" ", op)
            except Exception as e:
                print(lang, "ERROR", repr(e))

if __name__ == "__main__":
    main()
