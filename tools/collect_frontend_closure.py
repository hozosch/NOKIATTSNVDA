#!/usr/bin/env python3
"""Collect bounded ARM/Thumb control-flow closure from explicit entries."""

from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path

import pypcode


def parse_entry(value: str) -> tuple[int, bool]:
    fields = value.split(":")
    address = int(fields[0], 0) & ~1
    mode = fields[1].lower() if len(fields) > 1 else "thumb"
    if mode not in ("arm", "thumb"):
        raise argparse.ArgumentTypeError("entry mode must be arm or thumb")
    return address, mode == "thumb"


def read_text(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return stream.read()
    return path.read_text(encoding="utf-8")


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
    mode = current_thumb
    for operation in operations:
        text = str(operation).replace(" ", "")
        if re.search(r"(?:^|\W)TB=0x0(?:\W|$)", text):
            mode = False
        elif re.search(r"(?:^|\W)TB=0x1(?:\W|$)", text):
            mode = True
    return mode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--rom-base", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--entry", action="append", type=parse_entry, required=True)
    parser.add_argument("--exclude-labels-source", type=Path)
    parser.add_argument("--stop-labels-source", type=Path)
    parser.add_argument("--max-call-depth", type=int, default=2)
    parser.add_argument("--max-instructions", type=int, default=12000)
    parser.add_argument("--address-start", type=lambda value: int(value, 0))
    parser.add_argument("--address-end", type=lambda value: int(value, 0))
    args = parser.parse_args()

    rom = args.rom.read_bytes()
    rom_end = args.rom_base + len(rom)
    excluded: set[int] = set()
    if args.exclude_labels_source:
        excluded.update(
            int(value, 16)
            for value in re.findall(
                r"(?m)^L_([0-9a-f]{8}):$",
                read_text(args.exclude_labels_source),
            )
        )
    stops: set[int] = set()
    if args.stop_labels_source:
        stops.update(
            int(value, 16)
            for value in re.findall(
                r"(?m)^L_([0-9a-f]{8}):$",
                read_text(args.stop_labels_source),
            )
        )
    roots = {address for address, _thumb in args.entry}
    result: dict[tuple[int, bool], int] = {}
    best_depth: dict[tuple[int, bool], int] = {}
    pending: list[tuple[int, bool, int]] = [
        (address, thumb, 0) for address, thumb in args.entry
    ]
    skipped_bad_data: set[tuple[int, bool]] = set()

    def translate(address: int, thumb: bool):
        data = rom[address - args.rom_base:address - args.rom_base + 16]
        # SLEIGH contexts retain ARM/Thumb context changes made while decoding
        # an instruction.  Closure traversal is deliberately non-linear, so a
        # preceding BLX can otherwise make an unrelated Thumb instruction
        # decode as ARM.  Context.reset() does not discard every address-bound
        # context change, so each independent instruction needs a fresh one.
        context = pypcode.Context(
            "ARM:LE:32:v8T" if thumb else "ARM:LE:32:v8"
        )
        try:
            return context.translate(
                data,
                base_address=address,
                max_instructions=1,
            )
        except pypcode.BadDataError:
            skipped_bad_data.add((address, thumb))
            return None

    def allowed(address: int) -> bool:
        return (
            args.rom_base <= address < rom_end
            and (args.address_start is None or address >= args.address_start)
            and (args.address_end is None or address < args.address_end)
            and address not in excluded
            and (address not in stops or address in roots)
        )

    while pending:
        address, thumb, depth = pending.pop()
        address &= ~1
        if not allowed(address):
            continue
        key = (address, thumb)
        old_depth = best_depth.get(key)
        if old_depth is not None and old_depth <= depth:
            continue
        best_depth[key] = depth
        translation = translate(address, thumb)
        if translation is None:
            continue
        operations = list(translation.ops)
        size = instruction_size(operations)
        result[key] = size
        if len(result) > args.max_instructions:
            raise SystemExit(
                f"closure exceeded {args.max_instructions} instructions"
            )
        falls_through = True
        for operation in operations:
            name = operation.opcode.name
            if name in ("BRANCH", "CBRANCH"):
                target = direct_target(operation.inputs[0])
                if allowed(target):
                    pending.append((target, thumb, depth))
                if name == "BRANCH":
                    falls_through = False
            elif name == "CALL":
                if depth < args.max_call_depth:
                    target = direct_target(operation.inputs[0])
                    if allowed(target):
                        pending.append((
                            target, call_mode(operations, thumb), depth + 1
                        ))
            elif name in ("BRANCHIND", "RETURN"):
                falls_through = False
        if falls_through and allowed(address + size):
            pending.append((address + size, thumb, depth))

    instructions = [
        {"address": address, "size": size, "thumb": thumb,
         "source": "control-flow-closure"}
        for (address, thumb), size in sorted(result.items())
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({
            "profile": "5500",
            "kind": "control-flow-closure",
            "instruction_count": len(instructions),
            "instructions": instructions,
            "skipped_bad_data": [
                {"address": address, "thumb": thumb}
                for address, thumb in sorted(skipped_bad_data)
            ],
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"collected {len(instructions)} closure instructions; "
        f"skipped bad data: {len(skipped_bad_data)}"
    )


if __name__ == "__main__":
    main()
