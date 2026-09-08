#!/usr/bin/env python3
"""Keep only trace instructions whose labels exist in a generated C source."""

from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path


def read_source(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return stream.read()
    return path.read_text(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--entry", type=lambda value: int(value, 0), required=True)
    args = parser.parse_args()

    labels = {
        int(value, 16)
        for value in re.findall(
            r"(?m)^L_([0-9a-f]{8}):$", read_source(args.source)
        )
    }
    payload = json.loads(args.trace.read_text(encoding="utf-8"))
    instructions = [
        item for item in payload.get("instructions", [])
        if (int(item["address"]) & ~1) in labels
    ]
    found = {int(item["address"]) & ~1 for item in instructions}
    missing = labels - found
    if missing:
        raise ValueError(
            "source labels missing from trace: "
            + ", ".join(f"0x{address:08x}" for address in sorted(missing)[:20])
        )
    result = {
        "profile": payload.get("profile"),
        "kind": "source-label-trace",
        "entry": args.entry & ~1,
        "instruction_count": len(instructions),
        "instructions": instructions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(f"kept {len(instructions)} instructions for {len(labels)} labels")


if __name__ == "__main__":
    main()
