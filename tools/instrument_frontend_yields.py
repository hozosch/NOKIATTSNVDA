#!/usr/bin/env python3
"""Add precise runtime yield telemetry to the split 5320 frontend AOT source."""
from __future__ import annotations

import argparse
from pathlib import Path


def instrument(source: str) -> str:
    signature = "NOKIA_EXPORT int nokia_frontend_aot("
    if signature not in source:
        raise ValueError("split frontend entry point not found")

    telemetry = (
        "static uint32_t nokia_frontend_yield_pc;\n"
        "static uint32_t nokia_frontend_yield_reason;\n"
        "static uint64_t nokia_frontend_yield_count;\n"
        "NOKIA_EXPORT uint32_t nokia_frontend_yield_pc_value(void){return nokia_frontend_yield_pc;}\n"
        "NOKIA_EXPORT uint32_t nokia_frontend_yield_reason_value(void){return nokia_frontend_yield_reason;}\n"
        "NOKIA_EXPORT uint64_t nokia_frontend_yield_count_value(void){return nokia_frontend_yield_count;}\n\n"
    )
    source = source.replace(signature, telemetry + signature, 1)

    replacements = {
        "    case 0x52000224u: goto yielded;":
            "    case 0x52000224u: nokia_frontend_yield_pc=0x52000224u; nokia_frontend_yield_reason=1u; ++nokia_frontend_yield_count; goto yielded;",
        "      if(lo>=sizeof(nokia_frontend_chunks)/sizeof(nokia_frontend_chunks[0]))goto yielded;":
            "      if(lo>=sizeof(nokia_frontend_chunks)/sizeof(nokia_frontend_chunks[0])){nokia_frontend_yield_pc=pc;nokia_frontend_yield_reason=2u;++nokia_frontend_yield_count;goto yielded;}",
        "      if(result==NOKIA_FRONTEND_YIELDED)goto yielded;":
            "      if(result==NOKIA_FRONTEND_YIELDED){nokia_frontend_yield_pc=pc;nokia_frontend_yield_reason=3u;++nokia_frontend_yield_count;goto yielded;}",
    }
    for old, new in replacements.items():
        if old not in source:
            raise ValueError(f"frontend yield form not found: {old}")
        source = source.replace(old, new, 1)
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    text = args.source.read_text(encoding="utf-8")
    args.source.write_text(instrument(text), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
