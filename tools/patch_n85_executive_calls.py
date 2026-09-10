#!/usr/bin/env python3
"""Restore the N85 slow-executive default used by text analysis.

The ARM SVC instruction is represented as a P-code CALLOTHER operation.  The
generic AOT emitter intentionally ignores CALLOTHER, but Symbian's unhandled
slow-call default returns zero in r0.  Keeping the incoming object pointer
causes the N85 Vietnamese frontend to call through an invalid vtable entry for
some long alphanumeric strings.
"""
from __future__ import annotations

import argparse
from pathlib import Path


START = "L_802940f0:"
END = "L_802940f4:"
MARKER = "/* Nokia N85 SVC 0xde default return. */"
INCLUDE_ANCHOR = "#include <string.h>\n"
TLS_DECLARATIONS = """/* Nokia N85 Dll::Tls host bridge. */
extern uint32_t nokia_runtime_tls_get(void *, uint32_t);
extern uint32_t nokia_runtime_tls_set(void *, uint32_t, uint32_t);
extern uint32_t nokia_runtime_tls_free(void *, uint32_t);
"""
TLS_GET = (
    "    case 0x80293c70u: reg_r0=0;"
    "reg_pc=UINT64_C(2150186100);goto dispatch;"
)
TLS_GET_PATCH = (
    "    case 0x80293c70u: reg_r0=nokia_runtime_tls_get("
    "host?host->context:0,(uint32_t)reg_r0);"
    "reg_pc=UINT64_C(2150186100);goto dispatch;"
)
TLS_SET = (
    "    case 0x80293db0u: reg_r0=0;"
    "reg_pc=UINT64_C(2150186420);goto dispatch;"
)
TLS_SET_PATCH = (
    "    case 0x80293db0u: reg_r0=nokia_runtime_tls_set("
    "host?host->context:0,(uint32_t)reg_r0,(uint32_t)reg_r2);"
    "reg_pc=UINT64_C(2150186420);goto dispatch;"
)
TLS_FREE = (
    "    case 0x80293db8u: reg_r0=0;"
    "reg_pc=UINT64_C(2150186428);goto dispatch;"
)
TLS_FREE_PATCH = (
    "    case 0x80293db8u: reg_r0=nokia_runtime_tls_free("
    "host?host->context:0,(uint32_t)reg_r0);"
    "reg_pc=UINT64_C(2150186428);goto dispatch;"
)
REPLACEMENT = f'''L_802940f0:
    nokia_frontend_last_pc=0x802940f0u;
    {MARKER}
    reg_r0=0;reg_pc=reg_lr;return NOKIA_FRONTEND_CONTINUE;
'''


def patch_source(source: str) -> str:
    if MARKER not in source:
        start = source.find(START)
        end = source.find(END, start + len(START))
        if start < 0 or end < 0:
            raise ValueError("N85 SVC 0xde labels not found")
        if source.find(START, start + len(START)) >= 0:
            raise ValueError("N85 SVC 0xde start label is ambiguous")
        if source.find(END, end + len(END)) >= 0:
            raise ValueError("N85 SVC 0xde end label is ambiguous")
        source = source[:start] + REPLACEMENT + source[end:]
    if TLS_DECLARATIONS not in source:
        if source.count(INCLUDE_ANCHOR) != 1:
            raise ValueError("N85 include anchor is missing or ambiguous")
        source = source.replace(
            INCLUDE_ANCHOR, INCLUDE_ANCHOR + TLS_DECLARATIONS, 1
        )
    for original, replacement, name in (
        (TLS_GET, TLS_GET_PATCH, "get"),
        (TLS_SET, TLS_SET_PATCH, "set"),
        (TLS_FREE, TLS_FREE_PATCH, "free"),
    ):
        if replacement in source:
            continue
        if source.count(original) != 1:
            raise ValueError(f"N85 Dll::Tls {name} case is missing or ambiguous")
        source = source.replace(original, replacement, 1)
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    source = args.file.read_text(encoding="utf-8")
    try:
        patched = patch_source(source)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if patched == source:
        print("Nokia N85 SVC 0xde default already present")
        return
    args.file.write_text(patched, encoding="utf-8", newline="\n")
    print("restored Nokia N85 slow-executive and Dll::Tls semantics")


if __name__ == "__main__":
    main()
