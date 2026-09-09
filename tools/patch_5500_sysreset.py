#!/usr/bin/env python3
"""Add the single Nokia 5500 Thumb instruction used by ``$SysReset``."""
from __future__ import annotations

import argparse
from pathlib import Path


DISPATCH_ANCHOR = "    case 0xf8451a14u: goto L_f8451a14;\n"
DISPATCH_LINE = "    case 0xf8451e3eu: goto L_f8451e3e;\n"
BODY_ANCHOR = "}\n\nstatic int nokia_frontend_chunk_21("
BODY = """L_f8451e3e:
    nokia_frontend_last_pc=0xf8451e3eu;
    reg_tmpCY = ((uint64_t)(nokia_carry((reg_r1 & UINT64_C(0xffffffff)), (UINT64_C(1) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpOV = ((uint64_t)(nokia_scarry((reg_r1 & UINT64_C(0xffffffff)), (UINT64_C(1) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_r1 = ((uint64_t)((reg_r1 & UINT64_C(0xffffffff)) + (UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r1 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r1 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_OV = ((uint64_t)((reg_tmpOV & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f8451e40;
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()

    text = args.source.read_text(encoding="utf-8")
    if "L_f8451e3e:" in text:
        print("Nokia 5500 $SysReset instruction is already present")
        return
    if text.count(DISPATCH_ANCHOR) != 1:
        raise SystemExit("5500 dispatch anchor is missing or ambiguous")
    if text.count(BODY_ANCHOR) != 1:
        raise SystemExit("5500 chunk boundary is missing or ambiguous")
    text = text.replace(DISPATCH_ANCHOR, DISPATCH_ANCHOR + DISPATCH_LINE, 1)
    text = text.replace(BODY_ANCHOR, BODY + BODY_ANCHOR, 1)
    args.source.write_text(text, encoding="utf-8")
    print("added Nokia 5500 $SysReset instruction at 0xf8451e3e")


if __name__ == "__main__":
    main()
