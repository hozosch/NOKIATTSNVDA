#!/usr/bin/env python3
"""Restore Nokia 5500 slow executive calls used by isolated letters.

P-code represents ARM SVC instructions as CALLOTHER operations, so closures
added after the original lifecycle trace otherwise fall through into the next
veneer.  The isolated-letter path needs Dll::Tls() at SVC 0x4d and the slow
default at SVC 0xde.  The preserved 5500 snapshot has no TLS entry, so DllTls
must return zero.
"""

from __future__ import annotations

import argparse
from pathlib import Path


MARKER = "/* Nokia 5500 isolated-letter slow executive default. */"
LABEL_MARKER = "/* Nokia 5500 SVC 0xde default return. */"
TLS_LABEL_MARKER = "/* Nokia 5500 SVC 0x4d Dll::Tls null. */"
ANCHOR = (
    "    case 0x8019db70u: reg_r0=nokia_mem_load(&machine,0x53000014u,4);"
    "reg_pc=reg_lr;goto dispatch;\n"
)
PATCH = (
    f"    {MARKER}\n"
    "    case 0xf81c1208u:\n"
    "        reg_r0=0;reg_pc=reg_lr;goto dispatch;\n"
    "    case 0xf81c1688u:\n"
    "        reg_r0=0;reg_pc=reg_lr;goto dispatch;\n"
)
TLS_LABEL = (
    "L_f81c1208:\n"
    "    nokia_frontend_last_pc=0xf81c1208u;\n"
    "    goto L_f81c120c;\n"
)
TLS_LABEL_PATCH = (
    "L_f81c1208:\n"
    "    nokia_frontend_last_pc=0xf81c1208u;\n"
    f"    {TLS_LABEL_MARKER}\n"
    "    reg_r0=0;reg_pc=reg_lr;return NOKIA_FRONTEND_CONTINUE;\n"
)
LABEL = (
    "L_f81c1688:\n"
    "    nokia_frontend_last_pc=0xf81c1688u;\n"
    "    goto L_f81c168c;\n"
)
LABEL_PATCH = (
    "L_f81c1688:\n"
    "    nokia_frontend_last_pc=0xf81c1688u;\n"
    f"    {LABEL_MARKER}\n"
    "    reg_r0=0;reg_pc=reg_lr;return NOKIA_FRONTEND_CONTINUE;\n"
)


def patch(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    changed = False
    if MARKER not in text:
        count = text.count(ANCHOR)
        if count != 1:
            raise SystemExit(
                f"expected exactly one main-dispatch anchor, found {count}"
            )
        text = text.replace(ANCHOR, ANCHOR + PATCH, 1)
        changed = True
    if TLS_LABEL_MARKER not in text:
        count = text.count(TLS_LABEL)
        if count != 1:
            raise SystemExit(
                f"expected exactly one SVC 0x4d label, found {count}"
            )
        text = text.replace(TLS_LABEL, TLS_LABEL_PATCH, 1)
        changed = True
    if LABEL_MARKER not in text:
        count = text.count(LABEL)
        if count != 1:
            raise SystemExit(
                f"expected exactly one SVC 0xde label, found {count}"
            )
        text = text.replace(LABEL, LABEL_PATCH, 1)
        changed = True
    if changed:
        path.write_text(text, encoding="utf-8")
        print("restored Nokia 5500 slow executive default")
    else:
        print("Nokia 5500 slow executive default already present")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    patch(args.source)


if __name__ == "__main__":
    main()
