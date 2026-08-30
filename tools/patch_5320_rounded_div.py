#!/usr/bin/env python3
"""Insert small semantically native 5320 DSP helpers into split AOT."""
from __future__ import annotations

import argparse
from pathlib import Path

ANCHOR = "    case 0x830f9db0u: {"
HELPERS = {
    0x830F9D60: (
        "    case 0x830f9d60u: {\n"
        "        int32_t a=(int32_t)(uint32_t)reg_r0;\n"
        "        int32_t b=(int32_t)(uint32_t)reg_r1;\n"
        "        if(!b)goto unsupported;\n"
        "        int32_t half=b/2;\n"
        "        int32_t biased=(a>0)?(a+half):(a-half);\n"
        "        reg_r0=(uint32_t)(biased/b);\n"
        "        reg_pc=reg_lr;goto dispatch;\n"
        "    }\n"
    ),
    # Thumb bytes 00 20 70 47: MOVS r0,#0 ; BX lr.
    0x830FBFB0: (
        "    case 0x830fbfb0u: {\n"
        "        reg_r0=0;reg_pc=reg_lr;goto dispatch;\n"
        "    }\n"
    ),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    args = ap.parse_args()
    text = args.source.read_text(encoding="utf-8")
    if ANCHOR not in text:
        raise SystemExit("native Klatt boundary case missing")
    inserted = []
    for entry, code in HELPERS.items():
        marker = f"case 0x{entry:08x}u: {{"
        if text.count(marker):
            continue
        text = text.replace(ANCHOR, code + ANCHOR, 1)
        inserted.append(entry)
    args.source.write_text(text, encoding="utf-8", newline="\n")
    for entry in HELPERS:
        if text.count(f"case 0x{entry:08x}u: {{") != 1:
            raise SystemExit(f"failed to retain helper {entry:#x} exactly once")
    print("native DSP helpers:", ", ".join(f"{x:#x}" for x in HELPERS))
    print("newly inserted:", ", ".join(f"{x:#x}" for x in inserted) or "none")


if __name__ == "__main__":
    main()
