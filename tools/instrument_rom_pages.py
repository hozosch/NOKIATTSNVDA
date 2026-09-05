#!/usr/bin/env python3
"""Instrument generated Nokia AOT sources with ROM-page read tracing."""

from __future__ import annotations

import argparse
from pathlib import Path


DECLARATION = (
    "extern void nokia_runtime_trace_rom_read(const uint8_t *, size_t, "
    "uint32_t, uint32_t, unsigned);\n"
)
SIGNATURES = (
    "static uint64_t nokia_mem_load(NokiaFrontendMachine*m,uint64_t address,unsigned size)",
    "static uint64_t nokia_mem_load(NokiaAotMachine*m,uint64_t address,unsigned size)",
)
TRACE_CALL = (
    "nokia_runtime_trace_rom_read(m->rom,m->rom_size,m->rom_base,"
    "(uint32_t)address,size);"
)


def instrument(source: str) -> str:
    if TRACE_CALL in source:
        return source
    signature = next((item for item in SIGNATURES if item in source), None)
    if signature is None:
        raise ValueError("generated memory-load helper was not recognised")
    include = "#include <string.h>\n"
    if include not in source:
        raise ValueError("string header marker is missing")
    source = source.replace(include, include + DECLARATION, 1)
    start = source.index(signature)
    brace = source.index("{", start + len(signature))
    source = source[: brace + 1] + TRACE_CALL + source[brace + 1 :]
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.sources:
        text = path.read_text(encoding="utf-8")
        patched = instrument(text)
        path.write_text(patched, encoding="utf-8", newline="\n")
        print(f"instrumented ROM reads in {path}")


if __name__ == "__main__":
    main()
