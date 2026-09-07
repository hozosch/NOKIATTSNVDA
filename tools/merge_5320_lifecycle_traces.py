#!/usr/bin/env python3
"""Merge complete 5320 Unicorn lifecycle traces into one AOT input corpus."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("traces", nargs="+", type=Path)
    args = parser.parse_args()

    merged: dict[int, dict] = {}
    sources = []
    total_audio_bytes = 0
    for path in args.traces:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("profile") != "5320":
            raise ValueError(f"{path} is not a 5320 lifecycle trace")
        sources.append({
            "path": str(path),
            "language": payload.get("language"),
            "voice": payload.get("voice"),
            "text": payload.get("text"),
            "instruction_count": len(payload.get("instructions", [])),
        })
        total_audio_bytes += int(payload.get("audio_bytes", 0))
        for item in payload.get("instructions", []):
            address = int(item["address"]) & ~1
            candidate = {
                "address": address,
                "size": int(item["size"]),
                "thumb": bool(item.get("thumb", False)) or bool(
                    int(item["address"]) & 1
                ),
                "phase": item.get("phase", "unknown"),
            }
            previous = merged.get(address)
            if previous is not None and (
                previous["size"] != candidate["size"]
                or previous["thumb"] != candidate["thumb"]
            ):
                raise ValueError(
                    f"conflicting decode mode or size at 0x{address:08x}: "
                    f"{previous!r} versus {candidate!r}"
                )
            if previous is None:
                merged[address] = candidate

    instructions = [merged[address] for address in sorted(merged)]
    phase_counts: dict[str, int] = {}
    for item in instructions:
        phase = item["phase"]
        phase_counts[phase] = phase_counts.get(phase, 0) + 1
    output = {
        "profile": "5320",
        "kind": "merged-lifecycle",
        "sources": sources,
        "audio_bytes": total_audio_bytes,
        "instruction_count": len(instructions),
        "phase_counts": phase_counts,
        "instructions": instructions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2) + "\n",
        encoding="utf-8",
    )
    print("merged traces:", len(sources))
    print("unique instructions:", len(instructions))
    print("phase counts:", phase_counts)


if __name__ == "__main__":
    main()
