#!/usr/bin/env python3
"""Keep the tiny 5320 zero-return DSP veneer native.

The lifecycle reaches Thumb 0x830fbfb0 dynamically.  It is only
``movs r0, #0; bx lr`` but overlaps the filtered native Klatt corpus, so the
generated frontend otherwise yields before PCM.  Handle it in the central
dispatcher without restoring any emulation fallback.
"""
from __future__ import annotations

import argparse
from pathlib import Path


MARKER = "    case 0x52000000u:"
CASE = (
    "    case 0x830fbfb0u: "
    "reg_r0=0u;reg_ZR=1u;reg_NG=0u;"
    "reg_TB=((uint32_t)reg_lr&1u)!=0u;"
    "reg_pc=(uint32_t)reg_lr&~1u;goto dispatch;\n"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    source = args.file.read_text(encoding="utf-8")
    if source.count(MARKER) != 1:
        raise SystemExit("frontend dispatcher marker not found exactly once")
    if "case 0x830fbfb0u:" in source:
        raise SystemExit("5320 zero veneer already installed")
    source = source.replace(MARKER, CASE + MARKER, 1)
    args.file.write_text(source, encoding="utf-8", newline="\n")
    print("native 5320 zero veneer installed: 0x830fbfb0 -> lr")


if __name__ == "__main__":
    main()
