#!/usr/bin/env python3
"""Repair the missing taken edge of the 5320 Klatt normalization loop."""

from pathlib import Path
import argparse
import re

SOURCE = 0x830FA42A
TARGET = 0x830FA426


def patch(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    label = f"L_{SOURCE:08x}:"
    target = f"L_{TARGET:08x}"
    start = text.find(label)
    if start < 0:
        raise SystemExit(f"source label {label} is missing")
    end_match = re.search(r"(?m)^L_[0-9a-f]{8}:$", text[start + len(label):])
    end = len(text) if end_match is None else start + len(label) + end_match.start()
    block = text[start:end]
    old = "goto unsupported;"
    new = f"goto {target};"
    if new in block:
        print(f"Klatt edge 0x{SOURCE:08x} -> 0x{TARGET:08x} already repaired")
        return
    count = block.count(old)
    if count != 1:
        raise SystemExit(
            f"expected exactly one unsupported edge in {label}, found {count}"
        )
    if f"{target}:" not in text:
        raise SystemExit(f"existing loop target {target}: is missing")
    block = block.replace(old, new, 1)
    path.write_text(text[:start] + block + text[end:], encoding="utf-8")
    print(f"repaired Klatt BGT edge 0x{SOURCE:08x} -> 0x{TARGET:08x}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    patch(args.source)


if __name__ == "__main__":
    main()
