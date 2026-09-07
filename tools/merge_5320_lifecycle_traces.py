#!/usr/bin/env python3
"""Merge complete Nokia Unicorn lifecycle traces into one AOT input corpus.

The historical filename is retained because the 5320 workflows call it, while
``--profile`` also supports later model ports such as the Nokia 5500.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("traces", nargs="+", type=Path)
    parser.add_argument("--profile", default="5320",
                        help="ROM profile expected in every input trace")
    args = parser.parse_args()

    merged: dict[int, dict] = {}
    executive_calls: dict[tuple[bool, int, int, bool], dict] = {}
    sources = []
    total_audio_bytes = 0
    for path in args.traces:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("profile") != args.profile:
            raise ValueError(
                f"{path} is not a {args.profile} lifecycle trace"
            )
        sources.append({
            "path": str(path),
            "language": payload.get("language"),
            "voice": payload.get("voice"),
            "text": payload.get("text"),
            "instruction_count": len(payload.get("instructions", [])),
        })
        total_audio_bytes += int(payload.get("audio_bytes", 0))
        for call in payload.get("executive_calls", []):
            key = (
                bool(call["fast"]),
                int(call["number"]),
                int(call["svc_address"]),
                bool(call.get("returns_to_lr", False)),
            )
            aggregate = executive_calls.setdefault(key, {
                "fast": key[0],
                "number": key[1],
                "svc_address": key[2],
                "thumb": bool(call.get("thumb", False)),
                "returns_to_lr": key[3],
                "phases": set(),
                "count": 0,
            })
            aggregate["phases"].update(
                call.get("phases", [call.get("first_phase", "unknown")])
            )
            aggregate["count"] += int(call.get("count", 1))
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
        "profile": args.profile,
        "kind": "merged-lifecycle",
        "sources": sources,
        "audio_bytes": total_audio_bytes,
        "instruction_count": len(instructions),
        "phase_counts": phase_counts,
        "executive_calls": [
            dict(item, phases=sorted(item["phases"]))
            for _, item in sorted(executive_calls.items())
        ],
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
