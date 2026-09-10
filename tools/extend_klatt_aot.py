#!/usr/bin/env python3
"""Add bounded, original-ROM instructions to a generated Klatt AOT source."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pypcode

from extend_prime_aot import cname, direct_target, emit, read_rom


def extend(
    source_path: Path,
    trace_path: Path,
    rom_path: Path,
    output_path: Path,
    rom_base: int = 0x80000000,
) -> None:
    source = source_path.read_text(encoding="utf-8")
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    rom, rom_base = read_rom(rom_path, rom_base)
    existing = {
        int(value, 16)
        for value in re.findall(r"(?m)^L_([0-9a-f]{8}):$", source)
    }
    traced: dict[int, dict] = {}
    for item in trace.get("instructions", []):
        address = int(item["address"]) & ~1
        candidate = dict(item, address=address)
        previous = traced.get(address)
        if previous is not None and (
            int(previous["size"]) != int(candidate["size"])
            or bool(previous.get("thumb", False))
            != bool(candidate.get("thumb", False))
        ):
            raise ValueError(f"conflicting trace entries at 0x{address:08x}")
        traced[address] = candidate
    additions = [
        item
        for address, item in sorted(traced.items())
        if address not in existing and address >= rom_base
    ]
    known = existing | {int(item["address"]) for item in additions}

    lifted = {}
    variables = set()
    for item in additions:
        address = int(item["address"])
        thumb = bool(item.get("thumb", False))
        context = pypcode.Context(
            "ARM:LE:32:v8T" if thumb else "ARM:LE:32:v8"
        )
        operations = list(context.translate(
            rom[address - rom_base:address - rom_base + 16],
            base_address=address,
            max_instructions=1,
        ).ops)
        lifted[address] = (int(item["size"]), thumb, operations)
        for operation in operations:
            nodes = (
                ([operation.output] if operation.output is not None else [])
                + list(operation.inputs)
            )
            for node in nodes:
                if node.space.name in ("register", "unique"):
                    variables.add(cname(node))

    declared = set(re.findall(
        r"(?m)^    uint64_t ([A-Za-z0-9_]+)=0;$", source
    ))
    missing = sorted(variables - declared)
    declaration_marker = "    uint32_t nokia_at=0;"
    declaration_at = source.index(declaration_marker)
    if missing:
        declarations = "".join(
            f"    uint64_t {name}=0;\n" for name in missing
        )
        source = source[:declaration_at] + declarations + source[declaration_at:]

    dispatch_marker = "    default: goto unsupported;"
    dispatch_at = source.index(dispatch_marker)
    cases = "".join(
        f"    case 0x{address:08x}u: goto L_{address:08x};\n"
        for address in sorted(lifted)
    )
    source = source[:dispatch_at] + cases + source[dispatch_at:]

    blocks = []
    for address in sorted(lifted):
        size, thumb, operations = lifted[address]
        blocks.extend((f"L_{address:08x}:", f"    nokia_at=0x{address:08x}u;"))
        controlled = False
        for operation in operations:
            blocks.extend(
                "    " + statement
                for statement in emit(operation, known, address, size, thumb)
            )
            controlled |= operation.opcode.name in (
                "BRANCH", "CALL", "BRANCHIND", "CALLIND", "RETURN"
            )
        if not controlled:
            following = address + size
            if following in known:
                blocks.append(f"    goto L_{following:08x};")
            else:
                blocks.extend((
                    f"    reg_pc=UINT64_C({following});",
                    "    goto dispatch;",
                ))
    insert_at = source.index("finished:")
    source = source[:insert_at] + "\n".join(blocks) + "\n" + source[insert_at:]

    # A new target can make an old, formerly unsupported conditional edge or
    # linear fallthrough valid. Re-lift only the affected predecessor blocks.
    new_addresses = set(lifted)
    block_pattern = re.compile(
        r"(?m)^L_([0-9a-f]{8}):\n(?:(?!^L_)[\s\S])*?(?=^L_|finished:)"
    )
    repairs = []
    for match in block_pattern.finditer(source):
        block = match.group(0)
        if "goto unsupported;" not in block:
            continue
        address = int(match.group(1), 16)
        candidates = []
        for thumb in (False, True):
            try:
                operations = list(pypcode.Context(
                    "ARM:LE:32:v8T" if thumb else "ARM:LE:32:v8"
                ).translate(
                    rom[address - rom_base:address - rom_base + 16],
                    base_address=address,
                    max_instructions=1,
                ).ops)
            except pypcode.BadDataError:
                continue
            size = next(
                op.inputs[0].size
                for op in operations
                if op.opcode.name == "IMARK"
            )
            statements = [
                statement
                for operation in operations
                if operation.opcode.name not in {
                    "IMARK", "CBRANCH", "BRANCH", "CALL", "BRANCHIND",
                    "CALLIND", "RETURN",
                }
                for statement in emit(operation, existing, address, size, thumb)
            ]
            score = sum(statement in block for statement in statements)
            candidates.append((score, thumb, size, operations))
        score, _thumb, size, operations = max(candidates, key=lambda item: item[0])
        if score == 0:
            continue
        branches = [op for op in operations if op.opcode.name == "CBRANCH"]
        if len(branches) == 1 and direct_target(branches[0].inputs[0]) \
                in new_addresses:
            target = direct_target(branches[0].inputs[0])
            conditional = re.search(
                r"(?m)^(    if \(.*\)) goto unsupported;$", block
            )
            if conditional:
                start = match.start() + conditional.start()
                end = match.start() + conditional.end()
                repairs.append((
                    start,
                    end,
                    conditional.group(1) + f" goto L_{target:08x};",
                ))
        controls = {op.opcode.name for op in operations}
        following = address + size
        if not controls & {
            "BRANCH", "CALL", "BRANCHIND", "CALLIND", "RETURN"
        } and following in new_addresses:
            marker = "    goto unsupported;\n"
            at = source.rfind(marker, match.start(), match.end())
            if at >= 0:
                repairs.append((
                    at,
                    at + len(marker),
                    f"    goto L_{following:08x};\n",
                ))
    for start, end, replacement in sorted(repairs, reverse=True):
        source = source[:start] + replacement + source[end:]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(source, encoding="utf-8", newline="\n")
    print(
        f"existing Klatt labels: {len(existing)}; "
        f"new instructions: {len(additions)}; "
        f"new variables: {len(missing)}; repaired edges: {len(repairs)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--rom-base", type=lambda value: int(value, 0), default=0x80000000
    )
    args = parser.parse_args()
    extend(args.source, args.trace, args.rom, args.output, args.rom_base)


if __name__ == "__main__":
    main()
