#!/usr/bin/env python3
"""Build an initialized Nokia 5320 runtime snapshot for the native-only DLL.

This is a build-time migration tool. It runs the preservation harness under
Unicorn only while producing the snapshot. The shipped runtime restores these
bytes directly and therefore does not need Unicorn or a bundled Python helper.

The snapshot is taken after CDevTTS construction and style creation, but before
an utterance. All guest addresses remain unchanged.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

HEAP_BASE = 0x50000000
HEAP_SIZE = 0x100000
VT_BASE = 0x51000000
VT_SIZE = 0x1000
TRAP_BASE = 0x52000000
TRAP_SIZE = 0x10000
POOL_BASE = 0x53000000
STACK_BASE = 0x60000000
STACK_SIZE = 0x100000
ROM_BASE = 0x80000000
MAGIC = b"NK5320S1"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("upstream", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--language", type=int, default=3)
    ap.add_argument("--voice", default="DefaultMale")
    args = ap.parse_args()

    addon = args.upstream / "addon"
    sys.path.insert(0, str(addon / "synthDrivers"))
    import _nokia.harness  # configures upstream's vendored Unicorn first
    from _nokia.engine import Engine, RUN_IF_READY
    from _nokia.harness.devtts import Dev

    rom = addon / "roms" / "5320" / "SYM.ROM"
    tree = addon / "roms" / "5320" / "files"
    eng = Engine(str(rom), str(tree), args.language, args.voice)
    try:
        style_id = eng._ensure_style()
        t = eng.tts
        ep = t.epoc
        uc = ep.uc

        # Only the used pool prefix needs to be stored; the native runtime
        # allocates the complete pool and zero-fills the remainder.
        pool_used = max(16, int(ep.pool) - POOL_BASE)
        pool_used = (pool_used + 0xfff) & ~0xfff

        regions = [
            ("heap", HEAP_BASE, HEAP_SIZE),
            ("vtable", VT_BASE, VT_SIZE),
            ("traps", TRAP_BASE, TRAP_SIZE),
            ("pool", POOL_BASE, pool_used),
            ("stack", STACK_BASE, STACK_SIZE),
        ]

        allocations = [
            {"address": int(address), "size": int(size)}
            for address, size in sorted(ep.sizes.items())
        ]
        free_cells = [
            {"address": int(address), "size": int(size)}
            for address, size in getattr(ep, "free_cells", [])
        ]

        meta = {
            "format": 1,
            "profile": "5320",
            "language": args.language,
            "voice": args.voice,
            "voice_applied": bool(eng.voice_applied),
            "rom_base": ROM_BASE,
            "dev": int(eng.dev),
            "observer": int(t.observer),
            "style_id": int(style_id),
            "scheduler_error": int(eng._scheduler_error),
            "thread_data": int(ep.thread_data),
            "scheduler": int(ep.scheduler),
            "trap_handler": int(ep.trap_handler),
            "pool_next": int(ep.pool),
            "allocations": allocations,
            "free_cells": free_cells,
            "dev_entries": {
                "synthesize": int(t.eps[Dev.SYNTHESIZE_L - 1]),
                "prime": int(t.eps[Dev.PRIME_SYNTHESIS_L - 1]),
                "stop": int(t.eps[Dev.STOP - 1]),
                "buffer_processed": int(t.eps[Dev.BUFFER_PROCESSED - 1]),
            },
            "common_entries": {
                "seg_set_style_id": int(t.common_eps[0]),
                "seg_set_text_ptr": int(t.common_eps[1]),
                "pt_add_segment": int(t.common_eps[6]),
                "pt_new": int(t.common_eps[10]),
                "pt_delete": int(t.common_eps[12]),
            },
            "euser_entries": {
                "run_if_ready": int(ep.euser_export(RUN_IF_READY)),
                "cleanup_prevlevel": int(ep.euser_export(1265)),
                "cleanup_pop_n": int(ep.euser_export(1268)),
                "cleanup_nextlevel": int(ep.euser_export(1278)),
            },
            "regions": [],
        }

        blobs = []
        offset = 0
        for name, address, size in regions:
            data = bytes(uc.mem_read(address, size))
            meta["regions"].append({
                "name": name,
                "address": address,
                "size": size,
                "file_offset": offset,
            })
            blobs.append(data)
            offset += len(data)

        header = json.dumps(meta, separators=(",", ":")).encode("utf-8")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("wb") as f:
            f.write(MAGIC)
            f.write(struct.pack("<II", len(header), offset))
            f.write(header)
            for blob in blobs:
                f.write(blob)
        print("snapshot bytes:", args.output.stat().st_size)
        print("pool used:", pool_used)
        print("dev:", hex(eng.dev), "style:", style_id,
              "scheduler:", hex(ep.scheduler))
    finally:
        eng.close()


if __name__ == "__main__":
    main()
