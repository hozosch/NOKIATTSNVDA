#!/usr/bin/env python3
"""Instrument AOT ROM reads and make them compact-container aware."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


DECLARATION = (
    "extern void nokia_runtime_trace_rom_read(const uint8_t *, size_t, "
    "uint32_t, uint32_t, unsigned);\n"
    "extern int nokia_runtime_rom_is_flat(const uint8_t *, size_t);\n"
    "extern int nokia_runtime_rom_read(const uint8_t *, size_t, uint32_t, "
    "uint32_t, void *, unsigned);\n"
)
SIGNATURES = (
    "static uint64_t nokia_mem_load(NokiaFrontendMachine*m,uint64_t address,unsigned size)",
    "static uint64_t nokia_mem_load(NokiaAotMachine*m,uint64_t address,unsigned size)",
)
TRACE_CALL = (
    "nokia_runtime_trace_rom_read(m->rom,m->rom_size,m->rom_base,"
    "(uint32_t)address,size);"
)
ROM_BRANCH = re.compile(
    r"else if\(a>=m->rom_base&&\(uint64_t\)\(a-m->rom_base\)\+size<=m->rom_size\)"
    r"\s*memcpy\(&v,m->rom\+\(a-m->rom_base\),size\);"
)
ROM_READER = (
    "else if(nokia_runtime_rom_read(m->rom,m->rom_size,m->rom_base,a,&v,size)){}"
)
FAST_MAP = (
    "if((m->rom_base&0xffffu)==0)nokia_fast_map(m->rom_base,"
    "(uint8_t*)(uintptr_t)m->rom,m->rom_size&~(size_t)0xffffu,0);"
)
PACK_AWARE_FAST_MAP = (
    "if(nokia_runtime_rom_is_flat(m->rom,m->rom_size)&&"
    "(m->rom_base&0xffffu)==0)nokia_fast_map(m->rom_base,"
    "(uint8_t*)(uintptr_t)m->rom,m->rom_size&~(size_t)0xffffu,0);"
)


def instrument(source: str) -> str:
    signature = next((item for item in SIGNATURES if item in source), None)
    if signature is None:
        raise ValueError("generated memory-load helper was not recognised")
    include = "#include <string.h>\n"
    if include not in source:
        raise ValueError("string header marker is missing")
    if DECLARATION not in source:
        source = source.replace(include, include + DECLARATION, 1)
    if TRACE_CALL not in source:
        start = source.index(signature)
        brace = source.index("{", start + len(signature))
        source = source[: brace + 1] + TRACE_CALL + source[brace + 1 :]
    if ROM_READER not in source:
        source, count = ROM_BRANCH.subn(ROM_READER, source, count=1)
        if count != 1:
            raise ValueError("direct generated ROM reader was not recognised")
    if FAST_MAP in source:
        source = source.replace(FAST_MAP, PACK_AWARE_FAST_MAP, 1)
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.sources:
        text = path.read_text(encoding="utf-8")
        patched = instrument(text)
        path.write_text(patched, encoding="utf-8", newline="\n")
        print(f"instrumented compact ROM reads in {path}")


if __name__ == "__main__":
    main()
