#!/usr/bin/env python3
"""Add traced instructions directly to an already split 5320 AOT source.

The full frontend is split into small address-ranged functions for the ARM64
linker.  Rebuilding and splitting all 40,000+ translated instructions just to
add a few language-specific paths is unnecessarily expensive.  This tool
places each new instruction in the existing chunk selected by the dispatcher's
range table and routes cross-chunk control flow back through that dispatcher.
"""
from __future__ import annotations

import argparse
import bisect
import json
import re
from pathlib import Path

import pypcode

from extend_prime_aot import cname, emit, read_rom
from split_frontend_aot import route


DSP_START = 0x830F7A48
DSP_END = 0x83102E00


def extend(source_path: Path, trace_path: Path, rom_path: Path,
           output_path: Path, include_dsp: bool = False,
           rom_base: int = 0x80000000) -> None:
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
        if address not in existing
        and address >= rom_base
        and (include_dsp or not (DSP_START <= address < DSP_END))
    ]

    limit_match = re.search(
        r"static const uint32_t nokia_frontend_chunk_limits\[\]=\{\n"
        r"(?P<body>.*?)\n\};",
        source,
        re.S,
    )
    if not limit_match:
        raise ValueError("split frontend chunk-limit table was not found")
    limits = [
        int(value, 16)
        for value in re.findall(r"0x([0-9a-f]{8})u", limit_match.group("body"))
    ]
    chunk_matches = list(re.finditer(
        r"(?m)^static int nokia_frontend_chunk_(\d+)\(", source
    ))
    if len(chunk_matches) != len(limits):
        raise ValueError(
            f"chunk function/table mismatch: {len(chunk_matches)} functions, "
            f"{len(limits)} limits"
        )
    for expected, match in enumerate(chunk_matches):
        if int(match.group(1)) != expected:
            raise ValueError("split frontend chunk indices are not contiguous")

    by_chunk: dict[int, list[dict]] = {}
    for item in additions:
        index = bisect.bisect_left(limits, int(item["address"]))
        if index >= len(limits):
            raise ValueError(
                f"new address 0x{int(item['address']):08x} is beyond the "
                "existing split dispatcher range"
            )
        by_chunk.setdefault(index, []).append(item)

    variables = set()
    replacements = []
    for index, items in by_chunk.items():
        start = chunk_matches[index].start()
        end = (
            chunk_matches[index + 1].start()
            if index + 1 < len(chunk_matches)
            else source.index(
                "typedef int (*NokiaFrontendChunk)",
                chunk_matches[index].end(),
            )
        )
        chunk_source = source[start:end]
        local = {
            int(value, 16)
            for value in re.findall(
                r"(?m)^L_([0-9a-f]{8}):$", chunk_source
            )
        }
        local.update(int(item["address"]) for item in items)

        new_cases = []
        new_blocks = []
        for item in items:
            address = int(item["address"])
            thumb = bool(item.get("thumb", False))
            context = pypcode.Context(
                "ARM:LE:32:v8T" if thumb else "ARM:LE:32:v8"
            )
            translation = context.translate(
                rom[address - rom_base:address - rom_base + 16],
                base_address=address,
                max_instructions=1,
            )
            operations = list(translation.ops)
            for operation in operations:
                nodes = (
                    ([operation.output] if operation.output is not None else [])
                    + list(operation.inputs)
                )
                for node in nodes:
                    if node.space.name in ("register", "unique"):
                        variables.add(cname(node))

            new_cases.append(
                f"    case 0x{address:08x}u: goto L_{address:08x};"
            )
            new_blocks.extend([
                f"L_{address:08x}:",
                f"    nokia_frontend_last_pc=0x{address:08x}u;",
            ])
            controlled = False
            for operation in operations:
                new_blocks.extend(
                    route("    " + statement, local)
                    for statement in emit(
                        operation,
                        local,
                        address,
                        int(item["size"]),
                        thumb,
                    )
                )
                controlled |= operation.opcode.name in (
                    "BRANCH", "CALL", "BRANCHIND", "CALLIND", "RETURN"
                )
            if not controlled:
                following = address + int(item["size"])
                if following in local:
                    new_blocks.append(f"    goto L_{following:08x};")
                else:
                    new_blocks.append(
                        f"    reg_pc=UINT64_C({following}); "
                        "return NOKIA_FRONTEND_CONTINUE;"
                    )

        marker = "    default: return NOKIA_FRONTEND_YIELDED;"
        if marker not in chunk_source:
            raise ValueError(f"chunk {index} dispatch marker was not found")
        chunk_source = chunk_source.replace(
            marker,
            "\n".join(new_cases + [marker]),
            1,
        )
        close = chunk_source.rfind("\n}")
        if close < 0:
            raise ValueError(f"chunk {index} closing brace was not found")
        chunk_source = (
            chunk_source[:close]
            + "\n"
            + "\n".join(new_blocks)
            + chunk_source[close:]
        )
        replacements.append((start, end, chunk_source))

    for start, end, replacement in sorted(replacements, reverse=True):
        source = source[:start] + replacement + source[end:]

    state_end_marker = "\n} NokiaFrontendState;"
    state_end = source.find(state_end_marker)
    state_start = source.rfind("typedef struct {", 0, state_end)
    if state_end < 0 or state_start < 0:
        raise ValueError("NokiaFrontendState was not found")
    body_start = source.find("\n", state_start) + 1
    state_body = source[body_start:state_end]
    declared = set(re.findall(
        r"(?m)^    uint64_t ([A-Za-z0-9_]+);$", state_body
    ))
    missing = sorted(variables - declared)
    if missing:
        fields = "".join(f"\n    uint64_t {name};" for name in missing)
        source = source[:state_end] + fields + source[state_end:]
        macros = "".join(f"#define {name} (state->{name})\n" for name in missing)
        source = source.replace("#define machine (*machine_ptr)\n", macros +
                                "#define machine (*machine_ptr)\n", 1)
        undefs = "".join(f"#undef {name}\n" for name in missing)
        source = source.replace("#undef machine\n", "#undef machine\n" + undefs, 1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(source, encoding="utf-8", newline="\n")
    print("existing split AOT labels:", len(existing))
    print("new translated instructions:", len(additions))
    print("affected chunks:", len(by_chunk))
    print("new state variables:", len(missing))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-dsp", action="store_true")
    parser.add_argument("--rom-base", type=lambda value: int(value, 0),
                        default=0x80000000)
    args = parser.parse_args()
    extend(
        args.source,
        args.trace,
        args.rom,
        args.output,
        args.include_dsp,
        args.rom_base,
    )


if __name__ == "__main__":
    main()
