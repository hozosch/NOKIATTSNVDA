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
        "#define NOKIA_FRONTEND_YIELD_SLOTS 64u\n"
        "static uint32_t nokia_frontend_yield_pc;\n"
        "static uint32_t nokia_frontend_yield_reason;\n"
        "static uint64_t nokia_frontend_yield_count;\n"
        "static uint32_t nokia_frontend_yield_pcs[NOKIA_FRONTEND_YIELD_SLOTS];\n"
        "static uint64_t nokia_frontend_yield_hits[NOKIA_FRONTEND_YIELD_SLOTS];\n"
        "static uint32_t nokia_frontend_yield_used;\n"
        "static void nokia_frontend_record_yield(uint32_t pc,uint32_t reason){\n"
        " uint32_t i; nokia_frontend_yield_pc=pc;nokia_frontend_yield_reason=reason;++nokia_frontend_yield_count;\n"
        " for(i=0;i<nokia_frontend_yield_used;++i)if(nokia_frontend_yield_pcs[i]==pc){++nokia_frontend_yield_hits[i];return;}\n"
        " if(nokia_frontend_yield_used<NOKIA_FRONTEND_YIELD_SLOTS){i=nokia_frontend_yield_used++;nokia_frontend_yield_pcs[i]=pc;nokia_frontend_yield_hits[i]=1;}\n"
        "}\n"
        "NOKIA_EXPORT uint32_t nokia_frontend_yield_pc_value(void){return nokia_frontend_yield_pc;}\n"
        "NOKIA_EXPORT uint32_t nokia_frontend_yield_reason_value(void){return nokia_frontend_yield_reason;}\n"
        "NOKIA_EXPORT uint64_t nokia_frontend_yield_count_value(void){return nokia_frontend_yield_count;}\n"
        "NOKIA_EXPORT uint32_t nokia_frontend_yield_histogram_count(void){return nokia_frontend_yield_used;}\n"
        "NOKIA_EXPORT uint32_t nokia_frontend_yield_histogram_pc(uint32_t i){return i<nokia_frontend_yield_used?nokia_frontend_yield_pcs[i]:0;}\n"
        "NOKIA_EXPORT uint64_t nokia_frontend_yield_histogram_hits(uint32_t i){return i<nokia_frontend_yield_used?nokia_frontend_yield_hits[i]:0;}\n\n"
    )
    source = source.replace(signature, telemetry + signature, 1)

    # Older generated frontends deliberately yielded for the observer/config
    # callback.  Keep its diagnostic label when present, but do not require it:
    # the native config registry handles this callback in newer builds.
    observer_old = "    case 0x52000224u: goto yielded;"
    if observer_old in source:
        source = source.replace(
            observer_old,
            "    case 0x52000224u: nokia_frontend_record_yield(0x52000224u,1u); goto yielded;",
            1,
        )

    replacements = {
        "      if(lo>=sizeof(nokia_frontend_chunks)/sizeof(nokia_frontend_chunks[0]))goto yielded;":
            "      if(lo>=sizeof(nokia_frontend_chunks)/sizeof(nokia_frontend_chunks[0])){nokia_frontend_record_yield(pc,2u);goto yielded;}",
        "      if(result==NOKIA_FRONTEND_YIELDED)goto yielded;":
            "      if(result==NOKIA_FRONTEND_YIELDED){nokia_frontend_record_yield(pc,3u);goto yielded;}",
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
