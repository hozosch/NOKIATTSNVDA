#!/usr/bin/env python3
"""Add Nokia E65 Klatt paths exercised by long NVDA diagnostics."""
from __future__ import annotations

import argparse
from pathlib import Path


DISPATCH_ANCHOR = "    case 0xf8407e80u: goto L_f8407e80;\n"
DISPATCH_LINE = "    case 0xf8407e82u: goto L_f8407e82;\n"
BODY_ANCHOR = "L_f8407e84:\n"
BODY = """L_f8407e82:
    nokia_at=0xf8407e82u;
    reg_tmpCY = ((uint64_t)((reg_r1 & UINT64_C(0xffffffff)) <= (reg_r0 & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_tmpOV = ((uint64_t)(nokia_sborrow((reg_r0 & UINT64_C(0xffffffff)), (reg_r1 & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_r0 = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) - (reg_r1 & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r0 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_OV = ((uint64_t)((reg_tmpOV & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f8407e84;
"""
UNTRACED_BRANCH = (
    "    if ((u_134800 & UINT64_C(0xff))) goto unsupported;\n"
    "    goto L_f8407e88;\n"
)
TRACED_BRANCH = (
    "    if ((u_134800 & UINT64_C(0xff))) goto L_f8407e82;\n"
    "    goto L_f8407e88;\n"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()

    text = args.source.read_text(encoding="utf-8")
    changed = False
    if "L_f8407e82:" not in text:
        if text.count(DISPATCH_ANCHOR) != 1:
            raise SystemExit("E65 Klatt dispatch anchor is missing or ambiguous")
        if text.count(BODY_ANCHOR) != 1:
            raise SystemExit("E65 Klatt body anchor is missing or ambiguous")
        text = text.replace(DISPATCH_ANCHOR, DISPATCH_ANCHOR + DISPATCH_LINE, 1)
        text = text.replace(BODY_ANCHOR, BODY + BODY_ANCHOR, 1)
        changed = True
    if UNTRACED_BRANCH in text:
        text = text.replace(UNTRACED_BRANCH, TRACED_BRANCH, 1)
        changed = True
    elif TRACED_BRANCH not in text:
        raise SystemExit("E65 Klatt regression branch is missing or ambiguous")

    if changed:
        args.source.write_text(text, encoding="utf-8")
        print("added Nokia E65 Klatt regression path")
    else:
        print("Nokia E65 Klatt regression path is already present")


if __name__ == "__main__":
    main()
