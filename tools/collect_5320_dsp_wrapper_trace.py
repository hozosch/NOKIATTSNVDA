#!/usr/bin/env python3
"""Collect the small 5320 DSP wrapper path before the native Klatt entry.

The regular frontend AOT deliberately excludes the DSP range. This trace starts
at the remaining hot yield 0x830f7bce and follows only local control flow and a
small call closure inside the wrapper. The already-native Klatt entry at
0x830f9db0 is treated as a terminal host boundary rather than translated again.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pypcode

ROM_BASE = 0x80000000
DSP_START = 0x830F7A48
DSP_END = 0x83102E00
ENTRY = 0x830F7BCE
NATIVE_KLATT_ENTRY = 0x830F9DB0
MAX_CALL_DEPTH = 3
MAX_INSTRUCTIONS = 2048


def direct_target(varnode) -> int:
    if varnode.space.name != "ram":
        raise ValueError(f"non-RAM control target: {varnode}")
    return varnode.offset & ~1


def instruction_size(ops) -> int:
    for op in ops:
        if op.opcode.name == "IMARK":
            return op.inputs[0].size
    raise ValueError("instruction has no IMARK")


def call_mode(ops, current_thumb: bool) -> bool:
    mode = current_thumb
    for op in ops:
        text = str(op).replace(" ", "")
        if re.search(r"(?:^|\W)TB=0x0(?:\W|$)", text):
            mode = False
        elif re.search(r"(?:^|\W)TB=0x1(?:\W|$)", text):
            mode = True
    return mode


def allowed(address: int) -> bool:
    return DSP_START <= address < DSP_END and address != NATIVE_KLATT_ENTRY


def translate(rom: bytes, address: int, thumb: bool):
    ctx = pypcode.Context("ARM:LE:32:v8T" if thumb else "ARM:LE:32:v8")
    off = address - ROM_BASE
    result = ctx.translate(rom[off:off + 16], base_address=address,
                           max_instructions=1)
    ops = list(result.ops)
    return ops, instruction_size(ops)


def collect(rom: bytes, entry: int, thumb: bool, depth: int,
            result: dict[tuple[int, bool], int],
            best_depth: dict[tuple[int, bool], int],
            terminals: set[int]) -> None:
    pending = [entry]
    local_seen: set[int] = set()
    while pending:
        address = pending.pop()
        if address == NATIVE_KLATT_ENTRY:
            terminals.add(address)
            continue
        if address in local_seen or not allowed(address):
            terminals.add(address)
            continue
        local_seen.add(address)
        key = (address, thumb)
        old = best_depth.get(key)
        if old is not None and old <= depth:
            continue
        best_depth[key] = depth
        ops, size = translate(rom, address, thumb)
        result[key] = size
        if len(result) > MAX_INSTRUCTIONS:
            raise ValueError("DSP wrapper trace exceeded instruction budget")

        falls_through = True
        for op in ops:
            name = op.opcode.name
            if name in ("BRANCH", "CBRANCH"):
                target = direct_target(op.inputs[0])
                if target == NATIVE_KLATT_ENTRY:
                    terminals.add(target)
                elif allowed(target):
                    pending.append(target)
                else:
                    terminals.add(target)
                if name == "BRANCH":
                    falls_through = False
            elif name == "CALL":
                target = direct_target(op.inputs[0])
                if target == NATIVE_KLATT_ENTRY:
                    terminals.add(target)
                elif depth < MAX_CALL_DEPTH and allowed(target):
                    collect(rom, target, call_mode(ops, thumb), depth + 1,
                            result, best_depth, terminals)
                else:
                    terminals.add(target)
            elif name in ("BRANCHIND", "CALLIND", "RETURN"):
                falls_through = False
        if falls_through:
            pending.append(address + size)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    rom = args.rom.read_bytes()
    result: dict[tuple[int, bool], int] = {}
    best_depth: dict[tuple[int, bool], int] = {}
    terminals: set[int] = set()
    collect(rom, ENTRY, True, 0, result, best_depth, terminals)

    payload = {
        "entry": f"0x{ENTRY:08x}",
        "native_klatt_entry": f"0x{NATIVE_KLATT_ENTRY:08x}",
        "instruction_count": len(result),
        "instructions": [
            {"address": address, "size": size, "thumb": thumb}
            for (address, thumb), size in sorted(result.items())
        ],
        "terminals": [f"0x{x:08x}" for x in sorted(terminals)],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n",
                           encoding="utf-8")
    print(f"collected {len(result)} DSP wrapper instructions")
    print("terminals:", ", ".join(payload["terminals"]))


if __name__ == "__main__":
    main()
