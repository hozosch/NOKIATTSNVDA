#!/usr/bin/env python3
"""Generate one frontend AOT source from a trace, translating in parallel."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import re
from pathlib import Path

import pypcode

from extend_prime_aot import branch_to, cname, emit, read_rom, read_text


_rom = b""
_rom_base = 0
_known: set[int] = set()


def _init_worker(rom_path: str, rom_base: int, known: tuple[int, ...]) -> None:
    global _rom, _rom_base, _known
    _rom, _rom_base = read_rom(Path(rom_path), rom_base)
    _known = set(known)


def _translate(item: dict) -> tuple[int, str, str, tuple[str, ...]]:
    address = int(item["address"]) & ~1
    size = int(item["size"])
    thumb = bool(item.get("thumb", False))
    context = pypcode.Context(
        "ARM:LE:32:v8T" if thumb else "ARM:LE:32:v8"
    )
    translation = context.translate(
        _rom[address - _rom_base:address - _rom_base + 16],
        base_address=address,
        max_instructions=1,
    )
    operations = list(translation.ops)
    variables: set[str] = set()
    lines = [
        f"L_{address:08x}:",
        f"    nokia_frontend_last_pc=0x{address:08x}u;",
    ]
    controlled = False
    for operation in operations:
        nodes = (
            ([operation.output] if operation.output is not None else [])
            + list(operation.inputs)
        )
        for node in nodes:
            if node.space.name in ("register", "unique"):
                variables.add(cname(node))
        lines.extend(
            "    " + statement
            for statement in emit(operation, _known, address, size, thumb)
        )
        controlled |= operation.opcode.name in (
            "BRANCH", "CALL", "BRANCHIND", "CALLIND", "RETURN"
        )
    if not controlled:
        lines.append(branch_to(address + size, _known, "    "))
    return (
        address,
        f"    case 0x{address:08x}u: goto L_{address:08x};",
        "\n".join(lines),
        tuple(sorted(variables)),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rom-base", type=lambda value: int(value, 0),
                        default=0x80000000)
    parser.add_argument("--default-entry", type=lambda value: int(value, 0),
                        required=True)
    parser.add_argument("--jobs", type=int, default=max(1, multiprocessing.cpu_count()))
    args = parser.parse_args()

    source = read_text(args.source)
    payload = json.loads(args.trace.read_text(encoding="utf-8"))
    items_by_address: dict[int, dict] = {}
    for raw in payload.get("instructions", []):
        item = dict(raw)
        address = int(item["address"]) & ~1
        item["address"] = address
        previous = items_by_address.get(address)
        if previous and (
            int(previous["size"]) != int(item["size"])
            or bool(previous.get("thumb", False)) != bool(item.get("thumb", False))
        ):
            raise ValueError(f"conflicting trace entry at 0x{address:08x}")
        items_by_address[address] = item
    items = [items_by_address[address] for address in sorted(items_by_address)]
    known = tuple(items_by_address)
    if not items:
        raise SystemExit("trace contains no frontend instructions")

    jobs = max(1, min(args.jobs, len(items)))
    with multiprocessing.Pool(
        jobs,
        initializer=_init_worker,
        initargs=(str(args.rom), args.rom_base, known),
    ) as pool:
        translated = pool.map(_translate, items, chunksize=32)

    variables = {name for _, _, _, names in translated for name in names}
    declared = set(re.findall(
        r"(?m)^    uint64_t ([A-Za-z0-9_]+)=0;$", source
    ))
    missing = sorted(variables - declared)
    declaration_point = source.index("    if(!reg_pc)reg_pc=")
    if missing:
        declarations = "".join(f"    uint64_t {name}=0;\n" for name in missing)
        source = source[:declaration_point] + declarations + source[declaration_point:]
    source = re.sub(
        r"    if\(!reg_pc\)reg_pc=UINT64_C\(\d+\);",
        f"    if(!reg_pc)reg_pc=UINT64_C({args.default_entry});",
        source,
        count=1,
    )
    marker = "    default: goto yielded;"
    cases_at = source.index(marker)
    source = (
        source[:cases_at]
        + "\n".join(case for _, case, _, _ in translated)
        + "\n"
        + source[cases_at:]
    )
    labels_at = source.index("finished:")
    source = (
        source[:labels_at]
        + "\n".join(block for _, _, block, _ in translated)
        + "\n"
        + source[labels_at:]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(source, encoding="utf-8", newline="\n")
    print(
        f"generated {len(translated)} frontend instructions with "
        f"{len(missing)} new temporaries using {jobs} workers"
    )


if __name__ == "__main__":
    main()
