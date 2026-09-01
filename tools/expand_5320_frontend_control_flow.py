#!/usr/bin/env python3
"""Complete direct frontend control flow around a recorded 5320 lifecycle.

The lifecycle trace remains the semantic root: this tool does not translate the
whole Symbian ROM.  It decodes every recorded frontend instruction and follows
both sides of conditional branches, linear fallthroughs, tail branches, and a
bounded number of direct calls.  The result turns input-dependent alternatives
into build-time AOT work instead of discovering one missing label per NVDA run.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import deque
from pathlib import Path

import pypcode

ROM_BASE = 0x80000000
DSP_START = 0x830F7A48
DSP_END = 0x83102E00


def parse_address(value: int | str) -> int:
    if isinstance(value, str):
        return int(value, 0)
    return int(value)


def parse_switch16(value: str) -> tuple[int, int, int]:
    """Parse TABLE_BASE:TARGET_BASE:CASE_COUNT for a Thumb halfword table."""
    fields = value.split(":")
    if len(fields) != 3:
        raise argparse.ArgumentTypeError(
            "switch16 must be TABLE_BASE:TARGET_BASE:CASE_COUNT"
        )
    try:
        table_base, target_base, case_count = (
            int(field, 0) for field in fields
        )
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    if table_base & 1 or target_base & 1 or case_count <= 0:
        raise argparse.ArgumentTypeError(
            "switch16 bases must be even and CASE_COUNT must be positive"
        )
    return table_base, target_base, case_count


def instruction_size(operations) -> int:
    for operation in operations:
        if operation.opcode.name == "IMARK":
            return operation.inputs[0].size
    raise ValueError("instruction has no IMARK")


def direct_target(varnode) -> int:
    if varnode.space.name != "ram":
        raise ValueError(f"non-RAM control target: {varnode}")
    return varnode.offset & ~1


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


def in_frontend_rom(address: int, rom_size: int) -> bool:
    return (
        ROM_BASE <= address < ROM_BASE + rom_size
        and not (DSP_START <= address < DSP_END)
    )


def translate_one(rom: bytes, address: int, thumb: bool):
    context = pypcode.Context("ARM:LE:32:v8T" if thumb else "ARM:LE:32:v8")
    offset = address - ROM_BASE
    translation = context.translate(
        rom[offset:offset + 16],
        base_address=address,
        max_instructions=1,
    )
    operations = list(translation.ops)
    return operations, instruction_size(operations)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("trace", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--max-external-call-depth", type=int, default=2)
    parser.add_argument("--max-new-instructions", type=int, default=120000)
    parser.add_argument(
        "--thumb-switch16",
        action="append",
        type=parse_switch16,
        default=[],
        metavar="TABLE_BASE:TARGET_BASE:CASE_COUNT",
        help=(
            "close every destination encoded by an unsigned Thumb halfword "
            "jump table; destination = TARGET_BASE + 2 * table[index]"
        ),
    )
    args = parser.parse_args()

    rom = args.rom.read_bytes()
    payload = json.loads(args.trace.read_text(encoding="utf-8"))

    original: dict[int, dict] = {}
    original_mode_conflicts: list[str] = []
    for raw_item in payload["instructions"]:
        item = dict(raw_item)
        raw_address = parse_address(item["address"])
        address = raw_address & ~1
        thumb = bool(item.get("thumb", False)) or bool(raw_address & 1)
        if address in original and bool(original[address].get("thumb", False)) != thumb:
            original_mode_conflicts.append(f"0x{address:08x}")
            continue
        item["address"] = address
        item["thumb"] = thumb
        original[address] = item

    original_pages = {
        address >> 12
        for address in original
        if in_frontend_rom(address, len(rom))
    }
    selected_mode = {
        address: bool(item.get("thumb", False))
        for address, item in original.items()
    }
    generated: dict[int, dict] = {}
    best_scheduled_depth: dict[int, int] = {}
    processed_depth: dict[int, int] = {}
    pending: deque[tuple[int, bool, int]] = deque()
    mode_conflicts: set[str] = set(original_mode_conflicts)
    decode_errors: list[str] = []
    control_errors: list[str] = []
    skipped_calls: set[str] = set()
    edges_followed = 0

    def enqueue(address: int, thumb: bool, external_depth: int) -> None:
        address &= ~1
        if not in_frontend_rom(address, len(rom)):
            return
        chosen = selected_mode.get(address)
        if chosen is not None and chosen != thumb:
            mode_conflicts.add(
                f"0x{address:08x} ({'Thumb' if chosen else 'ARM'} vs "
                f"{'Thumb' if thumb else 'ARM'})"
            )
            return
        selected_mode.setdefault(address, thumb)
        previous = best_scheduled_depth.get(address)
        if previous is not None and previous <= external_depth:
            return
        best_scheduled_depth[address] = external_depth
        pending.append((address, thumb, external_depth))

    for address, item in original.items():
        enqueue(address, bool(item.get("thumb", False)), 0)

    switch16_tables = []
    for table_base, target_base, case_count in args.thumb_switch16:
        table_offset = table_base - ROM_BASE
        table_size = case_count * 2
        if table_offset < 0 or table_offset + table_size > len(rom):
            raise SystemExit(
                f"switch16 table 0x{table_base:08x} exceeds the ROM"
            )
        entries = [
            target_base + 2 * int.from_bytes(
                rom[table_offset + index * 2:table_offset + index * 2 + 2],
                "little",
            )
            for index in range(case_count)
        ]
        unique_entries = sorted(set(entries))
        invalid_entries = [
            address
            for address in unique_entries
            if not in_frontend_rom(address, len(rom))
        ]
        if invalid_entries:
            raise SystemExit(
                f"switch16 table 0x{table_base:08x} leaves the frontend ROM: "
                + ", ".join(f"0x{x:08x}" for x in invalid_entries)
            )
        for address in unique_entries:
            enqueue(address, True, 0)
        switch16_tables.append({
            "table_base": f"0x{table_base:08x}",
            "target_base": f"0x{target_base:08x}",
            "case_count": case_count,
            "unique_target_count": len(unique_entries),
            "targets": [f"0x{x:08x}" for x in unique_entries],
        })

    while pending:
        address, thumb, external_depth = pending.popleft()
        previous = processed_depth.get(address)
        if previous is not None and previous <= external_depth:
            continue
        processed_depth[address] = external_depth

        try:
            operations, size = translate_one(rom, address, thumb)
        except Exception as error:
            decode_errors.append(f"0x{address:08x}: {type(error).__name__}: {error}")
            continue

        if address not in original and address not in generated:
            generated[address] = {
                "address": address,
                "size": size,
                "thumb": thumb,
                "source": "static-control-flow",
            }
            if len(generated) > args.max_new_instructions:
                raise SystemExit(
                    "static control-flow closure exceeded "
                    f"{args.max_new_instructions} new instructions at "
                    f"0x{address:08x}; refusing to emit a partial corpus"
                )

        falls_through = True
        for operation in operations:
            name = operation.opcode.name
            if name in ("BRANCH", "CBRANCH"):
                try:
                    target = direct_target(operation.inputs[0])
                except ValueError as error:
                    control_errors.append(f"0x{address:08x} {name}: {error}")
                else:
                    enqueue(target, thumb, external_depth)
                    edges_followed += 1
                if name == "BRANCH":
                    falls_through = False
            elif name == "CALL":
                try:
                    target = direct_target(operation.inputs[0])
                except ValueError as error:
                    control_errors.append(f"0x{address:08x} CALL: {error}")
                else:
                    target_thumb = call_mode(operations, thumb)
                    target_is_recorded_component = (target >> 12) in original_pages
                    if (
                        target_is_recorded_component
                        or external_depth < args.max_external_call_depth
                    ):
                        next_depth = (
                            external_depth
                            if target_is_recorded_component
                            else external_depth + 1
                        )
                        enqueue(target, target_thumb, next_depth)
                        edges_followed += 1
                    else:
                        skipped_calls.add(
                            f"0x{address:08x}->0x{target:08x}"
                        )
                # A call returns to the adjacent instruction.
            elif name in ("BRANCHIND", "RETURN"):
                falls_through = False
            elif name == "CALLIND":
                # The target is dynamic, but a normal indirect call still
                # returns to the adjacent instruction already rooted by trace.
                pass

        if falls_through:
            enqueue(address + size, thumb, external_depth)
            edges_followed += 1

    merged = dict(original)
    merged.update(generated)
    payload["instructions"] = [
        merged[address] for address in sorted(merged)
    ]
    payload["instruction_count"] = len(payload["instructions"])
    payload["static_control_flow_original_instructions"] = len(original)
    payload["static_control_flow_additions"] = len(generated)
    payload["static_control_flow_processed_instructions"] = len(processed_depth)
    payload["static_control_flow_edges_followed"] = edges_followed
    payload["static_control_flow_max_external_call_depth"] = (
        args.max_external_call_depth
    )
    payload["static_control_flow_skipped_calls"] = len(skipped_calls)
    payload["static_control_flow_skipped_call_samples"] = sorted(skipped_calls)[:64]
    payload["static_control_flow_decode_errors"] = len(decode_errors)
    payload["static_control_flow_decode_error_samples"] = decode_errors[:64]
    payload["static_control_flow_control_errors"] = len(control_errors)
    payload["static_control_flow_control_error_samples"] = control_errors[:64]
    payload["static_control_flow_mode_conflicts"] = len(mode_conflicts)
    payload["static_control_flow_mode_conflict_samples"] = sorted(mode_conflicts)[:64]
    payload["static_control_flow_switch16_tables"] = switch16_tables

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    print("recorded frontend instructions:", len(original))
    print("static control-flow additions:", len(generated))
    print("closed frontend instructions:", len(merged))
    print("control-flow edges followed:", edges_followed)
    print("direct calls left beyond depth limit:", len(skipped_calls))
    print("decode errors:", len(decode_errors))
    print("control-target errors:", len(control_errors))
    print("ARM/Thumb mode conflicts:", len(mode_conflicts))
    for table in switch16_tables:
        print(
            "closed switch16 table:",
            table["table_base"],
            "cases:", table["case_count"],
            "unique targets:", table["unique_target_count"],
        )
    for error in decode_errors[:10]:
        print("  decode warning:", error)
    for error in control_errors[:10]:
        print("  control warning:", error)
    for conflict in sorted(mode_conflicts)[:10]:
        print("  mode warning:", conflict)


if __name__ == "__main__":
    main()
