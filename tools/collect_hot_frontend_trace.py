#!/usr/bin/env python3
"""Collect bounded hot 5320 frontend paths for AOT extension.

This intentionally targets the dominant non-DSP Unicorn yield PCs observed in
NVDA.  Local branches are followed fully; direct calls are followed only to a
small bounded depth so the trace grows by hot helpers rather than whole ROM
subsystems.  The still-emulated Nokia DSP range remains excluded here.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pypcode

ROM_BASE = 0x80000000
ROM_LIMIT = 0x90000000
DSP_START = 0x830F7A48
DSP_END = 0x83102E00
HOT_ENTRIES = (
    (0x827FD6FE, True),
    (0x801A73D2, True),
    (0x801A3756, True),
    (0x801AE76A, True),
)
MAX_CALL_DEPTH = 2
MAX_TOTAL_INSTRUCTIONS = 4096


def direct_target(varnode) -> int:
    if varnode.space.name != "ram":
        raise ValueError(f"non-RAM control target: {varnode}")
    return varnode.offset & ~1


def instruction_size(operations) -> int:
    for operation in operations:
        if operation.opcode.name == "IMARK":
            return operation.inputs[0].size
    raise ValueError("instruction has no IMARK")


def call_mode(operations, current_thumb: bool) -> bool:
    """Infer BL/BLX target mode from the p-code TB assignment when present."""
    mode = current_thumb
    for operation in operations:
        text = str(operation).replace(" ", "")
        if re.search(r"(?:^|\W)TB=0x0(?:\W|$)", text):
            mode = False
        elif re.search(r"(?:^|\W)TB=0x1(?:\W|$)", text):
            mode = True
    return mode


def in_allowed_rom(address: int) -> bool:
    return ROM_BASE <= address < ROM_LIMIT and not (DSP_START <= address < DSP_END)


def translate_one(rom: bytes, address: int, thumb: bool):
    context = pypcode.Context("ARM:LE:32:v8T" if thumb else "ARM:LE:32:v8")
    offset = address - ROM_BASE
    translation = context.translate(
        rom[offset:offset + 16], base_address=address, max_instructions=1
    )
    operations = list(translation.ops)
    return operations, instruction_size(operations)


def collect_function(rom: bytes, entry: int, thumb: bool, depth: int,
                     result: dict[tuple[int, bool], int]) -> None:
    pending = [entry]
    local_seen: set[int] = set()
    while pending:
        address = pending.pop()
        if address in local_seen or not in_allowed_rom(address):
            continue
        local_seen.add(address)
        operations, size = translate_one(rom, address, thumb)
        result[(address, thumb)] = size
        if len(result) > MAX_TOTAL_INSTRUCTIONS:
            raise ValueError("hot AOT trace exceeded bounded instruction budget")

        falls_through = True
        for operation in operations:
            name = operation.opcode.name
            if name in ("BRANCH", "CBRANCH"):
                target = direct_target(operation.inputs[0])
                if in_allowed_rom(target):
                    pending.append(target)
                if name == "BRANCH":
                    falls_through = False
            elif name == "CALL":
                if depth < MAX_CALL_DEPTH:
                    target = direct_target(operation.inputs[0])
                    if in_allowed_rom(target):
                        collect_function(
                            rom, target, call_mode(operations, thumb), depth + 1, result
                        )
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
    for entry, thumb in HOT_ENTRIES:
        collect_function(rom, entry, thumb, 0, result)

    instructions = [
        {"address": address, "size": size, "thumb": thumb}
        for (address, thumb), size in sorted(result.items())
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"instructions": instructions}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"collected {len(instructions)} hot frontend instructions")
    for entry, _ in HOT_ENTRIES:
        print(f"  hot entry 0x{entry:08x}")


if __name__ == "__main__":
    main()
