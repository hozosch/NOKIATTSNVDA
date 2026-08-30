#!/usr/bin/env python3
"""Build an initialized Nokia 5320 snapshot for the native-only runtime.

Unicorn is used only here, at build time. The output has a fixed little-endian
binary layout so the shipped C runtime can restore it without JSON or Python.
The snapshot is taken after CDevTTS construction and style creation and before
an utterance.
"""
from __future__ import annotations

import argparse
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
MAGIC = b"NK5320S1"
VERSION = 1
HEADER_WORDS = 27


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("upstream", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--language", type=int, default=3)
    ap.add_argument("--voice", default="DefaultMale")
    args = ap.parse_args()

    addon = args.upstream / "addon"
    sys.path.insert(0, str(addon / "synthDrivers"))
    import _nokia.harness  # configure upstream's vendored Unicorn first
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

        pool_used = max(16, int(ep.pool) - POOL_BASE)
        pool_used = (pool_used + 0xfff) & ~0xfff
        regions = [
            (HEAP_BASE, HEAP_SIZE),
            (VT_BASE, VT_SIZE),
            (TRAP_BASE, TRAP_SIZE),
            (POOL_BASE, pool_used),
            (STACK_BASE, STACK_SIZE),
        ]
        allocations = [(int(a), int(s)) for a, s in sorted(ep.sizes.items())]
        free_cells = [(int(a), int(s)) for a, s in ep.free_cells]

        words = [
            VERSION, int(args.language), 1 if eng.voice_applied else 0,
            int(eng.dev), int(t.observer), int(style_id),
            int(eng._scheduler_error), int(ep.thread_data),
            int(ep.scheduler), int(ep.trap_handler), int(ep.pool),
            int(t.eps[Dev.SYNTHESIZE_L - 1]),
            int(t.eps[Dev.PRIME_SYNTHESIS_L - 1]),
            int(t.eps[Dev.STOP - 1]),
            int(t.eps[Dev.BUFFER_PROCESSED - 1]),
            int(t.common_eps[0]), int(t.common_eps[1]),
            int(t.common_eps[6]), int(t.common_eps[10]), int(t.common_eps[12]),
            int(ep.euser_export(RUN_IF_READY)),
            int(ep.euser_export(1265)), int(ep.euser_export(1268)),
            int(ep.euser_export(1278)),
            len(regions), len(allocations), len(free_cells),
        ]
        assert len(words) == HEADER_WORDS

        fixed = len(MAGIC) + HEADER_WORDS * 4
        tables = len(regions) * 12 + (len(allocations) + len(free_cells)) * 8
        offset = fixed + tables
        region_table = []
        blobs = []
        for address, size in regions:
            blob = bytes(uc.mem_read(address, size))
            region_table.append((address, size, offset))
            blobs.append(blob)
            offset += size

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("wb") as f:
            f.write(MAGIC)
            f.write(struct.pack("<" + "I" * HEADER_WORDS, *words))
            for row in region_table:
                f.write(struct.pack("<III", *row))
            for row in allocations:
                f.write(struct.pack("<II", *row))
            for row in free_cells:
                f.write(struct.pack("<II", *row))
            for blob in blobs:
                f.write(blob)

        print("snapshot bytes:", args.output.stat().st_size)
        print("pool used:", pool_used)
        print("allocation cells:", len(allocations), "free cells:", len(free_cells))
        print("dev:", hex(eng.dev), "style:", style_id,
              "scheduler:", hex(ep.scheduler))
    finally:
        eng.close()


if __name__ == "__main__":
    main()
