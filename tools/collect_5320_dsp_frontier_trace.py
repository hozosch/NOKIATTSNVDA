#!/usr/bin/env python3
"""Close every missing sequential continuation at known 5320 DSP boundaries."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import collect_5320_dsp_wrapper_trace as dsp

MAX_FRONTIER_INSTRUCTIONS = 32768


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--known-trace",
        action="append",
        type=Path,
        required=True,
        help="JSON trace already present in the combined AOT corpus",
    )
    args = parser.parse_args()

    rom = args.rom.read_bytes()
    known: set[tuple[int, bool]] = set()
    known_sizes: dict[tuple[int, bool], int] = {}
    for trace_path in args.known_trace:
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
        for item in payload.get("instructions", []):
            raw_address = int(item["address"])
            key = (
                raw_address & ~1,
                bool(item.get("thumb", False)) or bool(raw_address & 1),
            )
            known.add(key)
            known_sizes[key] = int(item["size"])

    boundaries = sorted(
        key
        for key, size in known_sizes.items()
        if (
            dsp.allowed(key[0])
            and dsp.allowed(key[0] + size)
            and (key[0] + size, key[1]) not in known
        )
    )

    dsp.MAX_INSTRUCTIONS = MAX_FRONTIER_INSTRUCTIONS
    result: dict[tuple[int, bool], int] = {}
    best_depth: dict[tuple[int, bool], int] = {}
    terminals: set[int] = set()
    decode_errors: dict[tuple[int, bool, str, str], dict] = {}
    for address, thumb in boundaries:
        try:
            dsp.collect(
                rom,
                address,
                thumb,
                0,
                result,
                best_depth,
                terminals,
                known,
            )
        except Exception as error:
            match = re.search(r"r0x([0-9a-fA-F]+)", str(error))
            failed_address = (
                int(match.group(1), 16) if match else address
            )
            key = (
                failed_address,
                thumb,
                type(error).__name__,
                str(error),
            )
            decode_errors[key] = {
                "address": f"0x{failed_address:08x}",
                "thumb": thumb,
                "error": f"{type(error).__name__}: {error}",
            }

    resolved_addresses = {address for address, _thumb in known}
    resolved_addresses.update(address for address, _thumb in result)
    unresolved = sorted(
        address
        for address in terminals
        if dsp.allowed(address) and address not in resolved_addresses
    )
    if unresolved:
        raise ValueError(
            "DSP boundary closure left allowed terminal addresses unresolved: "
            + ", ".join(f"0x{x:08x}" for x in unresolved)
        )

    output = {
        "entry": None,
        "entries": [],
        "dsp_boundary_candidate_count": len(boundaries),
        "dsp_boundary_candidates": [
            {"address": address, "thumb": thumb}
            for address, thumb in boundaries
        ],
        "known_instruction_count": len(known),
        "known_dsp_instruction_count": sum(
            1 for address, _thumb in known if dsp.allowed(address)
        ),
        "instruction_count": len(result),
        "instructions": [
            {"address": address, "size": size, "thumb": thumb}
            for (address, thumb), size in sorted(result.items())
        ],
        "decode_errors": [
            decode_errors[key] for key in sorted(decode_errors)
        ],
        "terminals": [f"0x{x:08x}" for x in sorted(terminals)],
        "unresolved_terminals": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2) + "\n",
        encoding="utf-8",
    )
    print("known DSP boundary candidates:", len(boundaries))
    print("new DSP frontier instructions:", len(result))
    print("decode errors:", len(decode_errors))
    for item in output["decode_errors"]:
        print(
            f"  {item['address']} thumb={item['thumb']}: {item['error']}"
        )
    print("unresolved allowed terminals:", len(unresolved))


if __name__ == "__main__":
    main()
