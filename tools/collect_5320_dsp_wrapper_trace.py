#!/usr/bin/env python3
"""Collect bounded 5320 DSP wrapper/helper paths before native Klatt.

Besides ordinary direct entries, this collector can close every decodable case
of Symbian's switch8 thunk.  The 5320 frontend reaches the switch through an
indirect ARM veneer, so a dynamic trace otherwise reveals one case at a time.
Invalid halfword entries (the middle of 32-bit instructions) are recorded and
skipped; every valid entry is recursively closed over branches and direct calls.
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
DEFAULT_ENTRY = 0x830F7BCE
NATIVE_KLATT_ENTRY = 0x830F9DB0
MAX_CALL_DEPTH = 6
MAX_INSTRUCTIONS = 4096


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
    context = pypcode.Context("ARM:LE:32:v8T" if thumb else "ARM:LE:32:v8")
    off = address - ROM_BASE
    result = context.translate(
        rom[off:off + 16],
        base_address=address,
        max_instructions=1,
    )
    ops = list(result.ops)
    return ops, instruction_size(ops)


def switch8_entries_from_lr(rom: bytes, lr: int) -> dict:
    """Decode the exact destinations of an EABI ``__switch8`` inline table.

    The ARM helper reads the maximum case index from ``lr - 1``, selects one
    unsigned byte at ``lr + index``, and branches to ``lr + 2 * byte``.  Thumb
    LR is odd, so clear the mode bit only after applying the table offset.
    """
    if not (lr & 1):
        raise ValueError(f"switch8 LR must be a Thumb address: 0x{lr:08x}")
    max_index_offset = lr - 1 - ROM_BASE
    table_offset = lr - ROM_BASE
    if max_index_offset < 0 or table_offset >= len(rom):
        raise ValueError(f"switch8 LR is outside the ROM: 0x{lr:08x}")
    max_index = rom[max_index_offset]
    table_end = table_offset + max_index + 1
    if table_end > len(rom):
        raise ValueError(f"switch8 table exceeds the ROM: 0x{lr:08x}")
    offsets = rom[table_offset:table_end]
    entries = sorted({(lr + 2 * offset) & ~1 for offset in offsets})
    invalid = [address for address in entries if not allowed(address)]
    if invalid:
        raise ValueError(
            f"switch8 table 0x{lr:08x} leaves the DSP region: "
            + ", ".join(f"0x{x:08x}" for x in invalid)
        )
    return {
        "lr": lr,
        "max_index": max_index,
        "case_count": len(offsets),
        "entries": entries,
    }


def collect(rom: bytes, entry: int, thumb: bool, depth: int,
            result: dict[tuple[int, bool], int],
            best_depth: dict[tuple[int, bool], int],
            terminals: set[int],
            known: set[tuple[int, bool]]) -> None:
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
        if key in known:
            continue
        old = best_depth.get(key)
        if old is not None and old <= depth:
            continue
        best_depth[key] = depth
        ops, size = translate(rom, address, thumb)
        result[key] = size
        if len(result) > MAX_INSTRUCTIONS:
            raise ValueError("DSP helper trace exceeded instruction budget")

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
                    collect(
                        rom,
                        target,
                        call_mode(ops, thumb),
                        depth + 1,
                        result,
                        best_depth,
                        terminals,
                        known,
                    )
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
    parser.add_argument(
        "--entry",
        action="append",
        type=lambda x: int(x, 0),
        help="direct helper entry; may be repeated",
    )
    parser.add_argument("--arm", action="store_true",
                        help="start direct entries in ARM instead of Thumb mode")
    parser.add_argument("--switch8-base", type=lambda x: int(x, 0))
    parser.add_argument("--switch8-last", type=lambda x: int(x, 0))
    parser.add_argument(
        "--switch8-lr",
        action="append",
        type=lambda x: int(x, 0),
        help=(
            "Thumb LR of an EABI __switch8 inline byte table; may be repeated. "
            "Exact branch destinations are decoded from the ROM."
        ),
    )
    parser.add_argument(
        "--known-trace",
        action="append",
        type=Path,
        help=(
            "JSON trace whose instruction labels are already available; may "
            "be repeated to stop recursion at the existing AOT boundary."
        ),
    )
    args = parser.parse_args()

    if (args.switch8_base is None) != (args.switch8_last is None):
        parser.error("--switch8-base and --switch8-last must be used together")
    if (
        args.switch8_base is not None
        and (
            args.switch8_base & 1
            or args.switch8_last & 1
            or args.switch8_last < args.switch8_base
        )
    ):
        parser.error("switch8 range must be an ascending halfword range")

    direct_entries = [value & ~1 for value in (args.entry or [])]
    range_switch_entries = (
        list(range(args.switch8_base, args.switch8_last + 1, 2))
        if args.switch8_base is not None
        else []
    )

    rom = args.rom.read_bytes()
    known: set[tuple[int, bool]] = set()
    for trace_path in args.known_trace or []:
        trace_payload = json.loads(trace_path.read_text(encoding="utf-8"))
        for item in trace_payload.get("instructions", []):
            raw_address = int(item["address"])
            known.add((
                raw_address & ~1,
                bool(item.get("thumb", False)) or bool(raw_address & 1),
            ))
    inline_switch_tables = [
        switch8_entries_from_lr(rom, lr)
        for lr in (args.switch8_lr or [])
    ]
    switch_entries = list(dict.fromkeys([
        *range_switch_entries,
        *(
            entry
            for table in inline_switch_tables
            for entry in table["entries"]
        ),
    ]))
    if not direct_entries and not switch_entries:
        direct_entries = [DEFAULT_ENTRY]
    result: dict[tuple[int, bool], int] = {}
    terminals: set[int] = set()
    successful_entries: list[int] = []
    skipped_entries: list[dict[str, str]] = []

    best_depth: dict[tuple[int, bool], int] = {}
    for entry in direct_entries:
        collect(
            rom,
            entry,
            not args.arm,
            0,
            result,
            best_depth,
            terminals,
            known,
        )
        successful_entries.append(entry)

    # Validate each switch slot itself before following any paths.  The eight
    # invalid values are the second halfwords of 32-bit Thumb instructions.
    # Once validated, use one shared visited/depth map so overlapping case
    # bodies and callees are decoded only once.
    valid_switch_entries: list[int] = []
    for entry in switch_entries:
        try:
            ops, _size = translate(rom, entry, True)
            for op in ops:
                if op.opcode.name in ("BRANCH", "CBRANCH", "CALL"):
                    direct_target(op.inputs[0])
        except Exception as error:
            skipped_entries.append({
                "entry": f"0x{entry:08x}",
                "error": f"{type(error).__name__}: {error}",
            })
            continue
        valid_switch_entries.append(entry)
        successful_entries.append(entry)

    for entry in valid_switch_entries:
        collect(
            rom,
            entry,
            True,
            0,
            result,
            best_depth,
            terminals,
            known,
        )
    if len(result) > MAX_INSTRUCTIONS:
        raise ValueError("combined DSP helper trace exceeded instruction budget")
    candidates = [
        *(entry for entry in direct_entries),
        *(entry for entry in switch_entries),
    ]

    result_addresses = {address for address, _thumb in result}
    result_addresses.update(address for address, _thumb in known)
    unresolved = sorted(
        address
        for address in terminals
        if allowed(address) and address not in result_addresses
    )
    if unresolved:
        raise ValueError(
            "DSP helper closure left allowed terminal addresses unresolved: "
            + ", ".join(f"0x{x:08x}" for x in unresolved)
        )

    all_entries = direct_entries + switch_entries
    payload = {
        "entry": f"0x{all_entries[0]:08x}",
        "entries": [f"0x{x:08x}" for x in all_entries],
        "successful_entries": [
            f"0x{x:08x}" for x in successful_entries
        ],
        "skipped_entries": skipped_entries,
        "switch8_base": (
            f"0x{args.switch8_base:08x}"
            if args.switch8_base is not None
            else None
        ),
        "switch8_last": (
            f"0x{args.switch8_last:08x}"
            if args.switch8_last is not None
            else None
        ),
        "switch8_lrs": [
            f"0x{table['lr']:08x}" for table in inline_switch_tables
        ],
        "switch8_tables": [
            {
                "lr": f"0x{table['lr']:08x}",
                "max_index": table["max_index"],
                "case_count": table["case_count"],
                "entries": [
                    f"0x{entry:08x}" for entry in table["entries"]
                ],
            }
            for table in inline_switch_tables
        ],
        "native_klatt_entry": f"0x{NATIVE_KLATT_ENTRY:08x}",
        "known_instruction_count": len(known),
        "instruction_count": len(result),
        "instructions": [
            {"address": address, "size": size, "thumb": thumb}
            for (address, thumb), size in sorted(result.items())
        ],
        "terminals": [f"0x{x:08x}" for x in sorted(terminals)],
        "unresolved_terminals": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"collected {len(result)} DSP wrapper instructions from "
        f"{len(successful_entries)} of {len(candidates)} entries"
    )
    print("skipped switch8 entries:", len(skipped_entries))
    for item in skipped_entries:
        print(f"  {item['entry']}: {item['error']}")
    print("terminals:", ", ".join(payload["terminals"]))
    print("unresolved allowed terminals:", len(unresolved))


if __name__ == "__main__":
    main()
