#!/usr/bin/env python3
"""Extract only previously untranslated instructions from 5320 traces."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("traces", nargs="+", type=Path)
    args = parser.parse_args()

    source = args.source.read_text(encoding="utf-8")
    existing = {
        int(value, 16)
        for value in re.findall(r"(?m)^L_([0-9a-f]{8}):$", source)
    }
    missing: dict[int, dict] = {}
    for path in args.traces:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("profile") != "5320":
            raise ValueError(f"{path} is not a 5320 trace")
        for item in payload.get("instructions", []):
            address = int(item["address"]) & ~1
            if address in existing:
                continue
            candidate = {
                "address": address,
                "size": int(item["size"]),
                "thumb": bool(item.get("thumb", False)),
                "phase": item.get("phase", "unknown"),
            }
            previous = missing.get(address)
            if previous is not None and (
                previous["size"] != candidate["size"]
                or previous["thumb"] != candidate["thumb"]
            ):
                raise ValueError(f"conflicting trace entry at 0x{address:08x}")
            missing[address] = candidate

    instructions = [missing[address] for address in sorted(missing)]
    payload = {
        "profile": "5320",
        "kind": "regression-aot-delta",
        "instruction_count": len(instructions),
        "instructions": instructions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    print(f"existing labels: {len(existing)}")
    print(f"new traced instructions: {len(instructions)}")


if __name__ == "__main__":
    main()
