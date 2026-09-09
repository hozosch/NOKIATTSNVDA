#!/usr/bin/env python3
"""Remove instructions already implemented by a model's native Klatt AOT."""

from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path


def read_text(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return stream.read()
    return path.read_text(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("klatt_source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--entry", type=lambda value: int(value, 0), required=True)
    args = parser.parse_args()

    payload = json.loads(args.trace.read_text(encoding="utf-8"))
    klatt = {
        int(value, 16)
        for value in re.findall(
            r"(?m)^L_([0-9a-f]{8}):$", read_text(args.klatt_source)
        )
    }
    outside_klatt = {
        int(item["address"]) & ~1
        for item in payload.get("outside_klatt_instructions", [])
    }
    before = len(payload.get("instructions", []))
    kept = [
        item
        for item in payload.get("instructions", [])
        if (int(item["address"]) & ~1) != args.entry
        and (
            (int(item["address"]) & ~1) not in klatt
            or (int(item["address"]) & ~1) in outside_klatt
        )
    ]
    payload["instructions"] = kept
    payload["instruction_count"] = len(kept)
    payload["native_klatt_entry"] = f"0x{args.entry:08x}"
    payload["klatt_labels_removed"] = before - len(kept)
    payload["shared_klatt_labels_kept"] = len(klatt & outside_klatt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    print("full lifecycle instructions:", before)
    print("native Klatt instructions removed:", before - len(kept))
    print("shared Klatt labels kept:", len(klatt & outside_klatt))
    print("remaining frontend instructions:", len(kept))


if __name__ == "__main__":
    main()
