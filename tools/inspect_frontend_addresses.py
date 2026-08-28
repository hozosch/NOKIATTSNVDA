#!/usr/bin/env python3
"""Print generated frontend blocks around selected guest addresses."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def block_for(text: str, address: int) -> str:
    label = f"L_{address:08x}:"
    at = text.find(label)
    if at < 0:
        return f"0x{address:08x}: label not present"
    next_label = re.search(r"(?m)^L_[0-9a-fA-F]{8}:$", text[at + len(label):])
    end = at + len(label) + (next_label.start() if next_label else 1200)
    return text[at:min(end, at + 2200)].rstrip()


def nearby_labels(text: str, address: int, radius: int = 8) -> list[int]:
    labels = [int(x, 16) for x in re.findall(r"(?m)^L_([0-9a-fA-F]{8}):$", text)]
    labels.sort()
    before = [x for x in labels if x <= address][-radius:]
    after = [x for x in labels if x > address][:radius]
    return before + after


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("source", type=Path)
    p.add_argument("addresses", nargs="+")
    args = p.parse_args()
    text = args.source.read_text(encoding="utf-8")
    for raw in args.addresses:
        address = int(raw, 0)
        print(f"=== address 0x{address:08x} ===")
        print("nearby labels:", " ".join(f"0x{x:08x}" for x in nearby_labels(text, address)))
        print(block_for(text, address))
        print()


if __name__ == "__main__":
    main()
