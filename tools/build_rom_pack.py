#!/usr/bin/env python3
"""Build a compact, address-preserving Nokia ROM page container."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


MAGIC = b"NKROMP1\0"
VERSION = 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("trace", nargs="+", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--padding-pages", type=int, default=2)
    args = parser.parse_args()

    rom = args.rom.read_bytes()
    used: set[int] = set()
    page_size = 0
    for path in args.trace:
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("format") != "nokia-rom-pages-v1":
            raise SystemExit(f"unsupported ROM trace: {path}")
        current_page_size = int(report["pageSize"])
        if page_size and page_size != current_page_size:
            raise SystemExit("ROM traces use different page sizes")
        page_size = current_page_size
        if int(report["virtualSize"]) != len(rom):
            raise SystemExit(f"ROM size mismatch in {path}")
        used.update(map(int, report["usedPages"]))

    if page_size != 4096:
        raise SystemExit(f"unsupported page size: {page_size}")
    total_pages = (len(rom) + page_size - 1) // page_size
    expanded = set()
    padding = max(0, args.padding_pages)
    for page in used:
        expanded.update(
            range(max(0, page - padding), min(total_pages, page + padding + 1))
        )
    pages = sorted(expanded)
    if not pages:
        raise SystemExit("ROM trace is empty")

    header = MAGIC + struct.pack(
        "<IIII", VERSION, page_size, len(rom), len(pages)
    )
    index = struct.pack(f"<{len(pages)}I", *pages)
    body = bytearray()
    for page in pages:
        block = rom[page * page_size : (page + 1) * page_size]
        body.extend(block)
        body.extend(b"\0" * (page_size - len(block)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(header + index + body)
    print(
        f"ROM pack: {len(used)} observed pages, {len(pages)} with padding, "
        f"{len(header) + len(index) + len(body)} bytes"
    )


if __name__ == "__main__":
    main()
