#!/usr/bin/env python3
"""Insert the native 5320 rounded signed-division helper into split AOT."""
from __future__ import annotations

import argparse
from pathlib import Path

ENTRY = 0x830F9D60
ANCHOR = "    case 0x830f9db0u: {"
CASE = (
    "    case 0x830f9d60u: {\n"
    "        int32_t a=(int32_t)(uint32_t)reg_r0;\n"
    "        int32_t b=(int32_t)(uint32_t)reg_r1;\n"
    "        if(!b)goto unsupported;\n"
    "        int32_t half=b/2;\n"
    "        int32_t biased=(a>0)?(a+half):(a-half);\n"
    "        reg_r0=(uint32_t)(biased/b);\n"
    "        reg_pc=reg_lr;goto dispatch;\n"
    "    }\n"
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    args = ap.parse_args()
    text = args.source.read_text(encoding="utf-8")
    if text.count(f"case 0x{ENTRY:08x}u: {{"):
        print(f"rounded-div helper already present at {ENTRY:#x}")
        return
    if ANCHOR not in text:
        raise SystemExit("native Klatt boundary case missing")
    text = text.replace(ANCHOR, CASE + ANCHOR, 1)
    args.source.write_text(text, encoding="utf-8", newline="\n")
    if text.count(f"case 0x{ENTRY:08x}u: {{") != 1:
        raise SystemExit("failed to insert rounded-div helper exactly once")
    print(f"added native rounded-div helper at {ENTRY:#x}")


if __name__ == "__main__":
    main()
