#!/usr/bin/env python3
"""Restore Symbian executive-call semantics in an already split 5320 AOT.

P-code represents ARM SVC instructions as CALLOTHER operations.  The frozen
frontend trace treated those operations as no-ops, but Unicorn's EPOC harness
returns zero from EExecLeaveStart and unhandled slow calls.  Leaving the old
r0 value in place makes the ROM's leave unwinder interpret an error sentinel
as a virtual-function pointer for some Norwegian input.
"""

from __future__ import annotations

import argparse
from pathlib import Path


MARKER = "/* Symbian slow executive defaults (EExecLeaveStart/End). */"
ANCHOR = (
    "    case 0x8019db70u: reg_r0=nokia_mem_load(&machine,0x53000014u,4);"
    "reg_pc=reg_lr;goto dispatch;\n"
)
PATCH = (
    f"    {MARKER}\n"
    "    case 0x8019e2f8u:\n"
    "    case 0x8019e300u:\n"
    "        reg_r0=0;reg_pc=reg_lr;goto dispatch;\n"
)


def patch(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        print("Symbian slow executive defaults already present")
        return
    count = text.count(ANCHOR)
    if count != 1:
        raise SystemExit(
            f"expected exactly one main-dispatch anchor, found {count}"
        )
    path.write_text(text.replace(ANCHOR, ANCHOR + PATCH, 1), encoding="utf-8")
    print("restored Symbian slow executive default return values")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    patch(args.source)


if __name__ == "__main__":
    main()
