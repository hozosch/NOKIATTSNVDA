#!/usr/bin/env python3
"""Extend the existing 5320 AOT corpus to the real PrimeSynthesisL core.

The original generated corpus already contains Nokia's frontend, its euser
callbacks and the relevant descriptor helpers, but its public entry was a
small frontend wrapper.  This tool adds the DevTTS orchestration instructions
observed by collect_prime_control_flow.py and changes unsupported destinations
into resumable yields to the still-emulated DSP.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import struct
from pathlib import Path

import pypcode


def cname(varnode) -> str:
    if varnode.space.name in ("const", "ram"):
        return f"UINT64_C({varnode.offset})"
    if varnode.space.name == "register":
        return "reg_" + re.sub(r"[^A-Za-z0-9_]", "_", str(varnode))
    if varnode.space.name == "unique":
        return f"u_{varnode.offset:x}"
    raise ValueError(f"unsupported space {varnode.space.name}: {varnode}")


def mask(size: int) -> str:
    return "UINT64_MAX" if size >= 8 else f"UINT64_C(0x{(1 << (8 * size)) - 1:x})"


def value(varnode) -> str:
    if varnode.space.name == "ram":
        return (f"(nokia_mem_load(&machine, UINT64_C({varnode.offset}), "
                f"{varnode.size}) & {mask(varnode.size)})")
    return f"({cname(varnode)} & {mask(varnode.size)})"


def signed(varnode) -> str:
    return f"nokia_sext({value(varnode)}, {varnode.size})"


def assign(output, expression: str) -> str:
    return f"{cname(output)} = ((uint64_t)({expression})) & {mask(output.size)};"


def direct_target(varnode) -> int:
    if varnode.space.name != "ram":
        raise ValueError(f"non-RAM control target: {varnode}")
    return varnode.offset & ~1


def branch_to(destination: int, known: set[int], indent: str = "") -> str:
    if destination in known:
        return f"{indent}goto L_{destination:08x};"
    return (f"{indent}reg_pc=UINT64_C({destination}); "
            "goto dispatch;")


def emit(op, known: set[int], address: int, size: int, thumb: bool) -> list[str]:
    name, output, inputs = op.opcode.name, op.output, list(op.inputs)
    if name == "IMARK":
        return []
    if name == "COPY":
        return [assign(output, value(inputs[0]))]
    binary = {
        "INT_ADD": "+", "INT_SUB": "-", "INT_MULT": "*",
        "INT_AND": "&", "INT_OR": "|", "INT_XOR": "^",
        "BOOL_AND": "&&", "BOOL_OR": "||", "BOOL_XOR": "!=",
    }
    if name in binary:
        return [assign(output, f"{value(inputs[0])} {binary[name]} {value(inputs[1])}")]
    if name == "INT_LEFT":
        return [assign(output, f"nokia_shl({value(inputs[0])}, {value(inputs[1])}, {inputs[0].size})")]
    if name == "INT_RIGHT":
        return [assign(output, f"nokia_shr({value(inputs[0])}, {value(inputs[1])}, {inputs[0].size})")]
    if name == "INT_SRIGHT":
        return [assign(output, f"nokia_sar({value(inputs[0])}, {value(inputs[1])}, {inputs[0].size})")]
    if name == "INT_EQUAL":
        return [assign(output, f"{value(inputs[0])} == {value(inputs[1])}")]
    if name == "INT_NOTEQUAL":
        return [assign(output, f"{value(inputs[0])} != {value(inputs[1])}")]
    if name == "INT_SLESS":
        return [assign(output, f"{signed(inputs[0])} < {signed(inputs[1])}")]
    if name == "INT_LESSEQUAL":
        return [assign(output, f"{value(inputs[0])} <= {value(inputs[1])}")]
    if name == "BOOL_NEGATE":
        return [assign(output, f"!{value(inputs[0])}")]
    if name == "INT_NEGATE":
        return [assign(output, f"~{value(inputs[0])}")]
    if name == "INT_ZEXT":
        return [assign(output, value(inputs[0]))]
    if name == "INT_SEXT":
        return [assign(output, f"nokia_sext({value(inputs[0])}, {inputs[0].size})")]
    if name == "SUBPIECE":
        return [assign(output, f"{value(inputs[0])} >> (8 * {value(inputs[1])})")]
    if name == "INT_CARRY":
        return [assign(output, f"nokia_carry({value(inputs[0])}, {value(inputs[1])}, {inputs[0].size})")]
    if name == "INT_SCARRY":
        return [assign(output, f"nokia_scarry({value(inputs[0])}, {value(inputs[1])}, {inputs[0].size})")]
    if name == "INT_SBORROW":
        return [assign(output, f"nokia_sborrow({value(inputs[0])}, {value(inputs[1])}, {inputs[0].size})")]
    if name == "LOAD":
        return [assign(output, f"nokia_mem_load(&machine, {value(inputs[1])}, {output.size})")]
    if name == "STORE":
        return [(f"if (!nokia_mem_store(&machine, {value(inputs[1])}, "
                 f"{value(inputs[2])}, {inputs[2].size})) goto unsupported;")]
    if name == "CALLOTHER":
        return []
    if name == "CBRANCH":
        destination = direct_target(inputs[0])
        action = (f"goto L_{destination:08x};" if destination in known else
                  f"reg_pc=UINT64_C({destination}); goto dispatch;")
        return [f"if ({value(inputs[1])}) {{ {action} }}"]
    if name in ("BRANCH", "CALL"):
        destination = direct_target(inputs[0])
        statements = []
        if name == "CALL":
            statements.append(
                f"reg_lr=UINT64_C({(address + size) | (1 if thumb else 0)});")
        statements.append(branch_to(destination, known))
        return statements
    if name in ("BRANCHIND", "CALLIND", "RETURN"):
        return [f"reg_pc={value(inputs[0])};", "goto dispatch;"]
    raise ValueError(f"unsupported P-code operation {name} at {address:#x}")


def read_text(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return stream.read()
    return path.read_text(encoding="utf-8")


def read_rom(path: Path) -> tuple[bytes, int]:
    raw = path.read_bytes()
    if not raw.startswith(b"NKTTSROM1"):
        return raw, 0x80000000
    magic, base, logical_size, count = struct.unpack_from("<9s3xIII", raw)
    if magic != b"NKTTSROM1":
        raise ValueError("invalid compact Nokia ROM")
    blob = bytearray(logical_size)
    offset = struct.calcsize("<9s3xIII")
    for _ in range(count):
        page = struct.unpack_from("<I", raw, offset)[0]
        offset += 4
        start = page * 0x1000
        blob[start:start + 0x1000] = raw[offset:offset + 0x1000]
        offset += 0x1000
    if offset != len(raw):
        raise ValueError("trailing or truncated compact Nokia ROM data")
    return bytes(blob), base


def collect_function(rom: bytes, rom_base: int, entry: int,
                     thumb: bool = False) -> set[int]:
    """Follow one small ARM/Thumb helper without pulling in its callees."""
    pending = [entry]
    found = set()
    context = pypcode.Context(
        "ARM:LE:32:v8T" if thumb else "ARM:LE:32:v8")
    while pending:
        address = pending.pop()
        if address in found:
            continue
        translation = context.translate(
            rom[address - rom_base:address - rom_base + 8],
            base_address=address, max_instructions=1,
        )
        operations = list(translation.ops)
        size = operations[0].inputs[0].size
        found.add(address)
        falls_through = True
        for operation in operations:
            name = operation.opcode.name
            if name in ("BRANCH", "CBRANCH"):
                target = direct_target(operation.inputs[0])
                if rom_base <= target < rom_base + len(rom):
                    pending.append(target)
                if name == "BRANCH":
                    falls_through = False
            elif name in ("BRANCHIND", "RETURN"):
                falls_through = False
        if falls_through:
            pending.append(address + size)
        if len(found) > 4096:
            raise ValueError(f"ARM helper at {entry:#x} did not stay bounded")
    return found


def extend(source_path: Path, trace_path: Path, rom_path: Path,
           output_path: Path, repair_fallthroughs: bool = False) -> None:
    source = read_text(source_path)
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    rom, rom_base = read_rom(rom_path)
    # This EUser type helper is normally hidden behind a Unicorn-side system
    # hook, so the instruction tracer does not see it.  Prime calls it before
    # its main frontend work; statically following its 25-instruction body is
    # both smaller and more reliable than yielding through two hook layers.
    static_modes = {}
    for entry, thumb in ((0x8019FFD0, False), (0x8019F3E8, False),
                         (0x801A0CD4, False), (0x827FB6CC, False),
                         (0x827FB6AC, False), (0x8019E544, False)):
        for address in collect_function(rom, rom_base, entry, thumb):
            static_modes[address] = thumb
    static_helpers = set(static_modes)
    existing = {int(value, 16) for value in
                re.findall(r"(?m)^L_([0-9a-f]{8}):$", source)}
    traced = {item["address"]: item for item in trace["instructions"]}
    for address in static_helpers:
        if address not in traced:
            thumb = static_modes[address]
            translation = pypcode.Context(
                "ARM:LE:32:v8T" if thumb else "ARM:LE:32:v8").translate(
                rom[address - rom_base:address - rom_base + 8],
                base_address=address, max_instructions=1,
            )
            traced[address] = {
                "address": address,
                "size": list(translation.ops)[0].inputs[0].size,
                "thumb": thumb,
            }
    additions = [item for item in traced.values()
                 if item["address"] not in existing and
                 item["address"] >= rom_base and
                 # Keep only the still-emulated Nokia DSP as a yield island.
                 # Everything observed before it (DevTTS, EUser and Common)
                 # belongs to the cohesive Prime boundary.
                 not (0x830F7A48 <= item["address"] < 0x83102E00)]
    known = existing | {item["address"] for item in additions}
    lifted = {}
    variables = set()
    for item in additions:
        address = item["address"]
        context = pypcode.Context(
            "ARM:LE:32:v8T" if item["thumb"] else "ARM:LE:32:v8"
        )
        translation = context.translate(
            rom[address - rom_base:address - rom_base + 8],
            base_address=address, max_instructions=1,
        )
        operations = list(translation.ops)
        lifted[address] = (item["size"], item["thumb"], operations)
        for operation in operations:
            nodes = (([operation.output] if operation.output is not None else [])
                     + list(operation.inputs))
            for node in nodes:
                if node.space.name in ("register", "unique"):
                    variables.add(cname(node))

    declared = set(re.findall(r"(?m)^    uint64_t ([A-Za-z0-9_]+)=0;$", source))
    missing_variables = sorted(variables - declared)
    declaration_point = source.index("    if(!reg_pc)reg_pc=")
    if missing_variables:
        declarations = "".join(
            f"    uint64_t {name}=0;\n" for name in missing_variables
        )
        source = source[:declaration_point] + declarations + source[declaration_point:]

    # The bridge supplies the live PC, but the default documents the real
    # outer native boundary and permits direct test calls.
    source = re.sub(
        r"    if\(!reg_pc\)reg_pc=UINT64_C\(\d+\);",
        "    if(!reg_pc)reg_pc=UINT64_C(2189404854);",  # 0x827faab6
        source, count=1,
    )
    dispatch_marker = ("    default: goto yielded;"
                       if "    default: goto yielded;" in source
                       else "    default: goto unsupported;")
    cases_at = source.index(dispatch_marker)
    cases = "".join(
        f"    case 0x{address:08x}u: goto L_{address:08x};\n"
        for address in sorted(lifted)
    )
    source = source[:cases_at] + cases + source[cases_at:]
    # A destination outside the AOT corpus is a controlled call into the
    # remaining DSP, not a permanent failure.  The bridge resumes at LR.
    if dispatch_marker.endswith("unsupported;"):
        source = source.replace("    default: goto unsupported;",
                                "    default: goto yielded;", 1)

    labels = []
    for address in sorted(lifted):
        size, thumb, operations = lifted[address]
        labels.append(f"L_{address:08x}:")
        labels.append(f"    nokia_frontend_last_pc=0x{address:08x}u;")
        controlled = False
        for operation in operations:
            labels.extend("    " + statement
                          for statement in emit(operation, known, address,
                                                size, thumb))
            controlled |= operation.opcode.name in (
                "BRANCH", "CALL", "BRANCHIND", "CALLIND", "RETURN"
            )
        if not controlled:
            following = address + size
            labels.append(branch_to(following, known, "    "))
    insert_at = source.index("finished:")
    source = source[:insert_at] + "\n".join(labels) + "\n" + source[insert_at:]

    # Older corpus captures sometimes ended a conditional fallthrough in
    # ``unsupported`` simply because that adjacent instruction was not seen
    # in the original sentence.  A later trace can make the destination
    # known without regenerating the predecessor.  Repair only proven linear
    # or conditional fallthroughs; calls and unconditional control transfers
    # remain untouched.
    terminal = re.compile(
        r"(?m)^L_([0-9a-f]{8}):\n"
        r"(?:(?!^L_)[\s\S])*?    goto unsupported;\n(?=L_|finished:)"
    )
    repairs = []
    for match in terminal.finditer(source) if repair_fallthroughs else ():
        address = int(match.group(1), 16)
        item = traced.get(address)
        if item is None or address + item["size"] not in lifted:
            continue
        context = pypcode.Context(
            "ARM:LE:32:v8T" if item["thumb"] else "ARM:LE:32:v8")
        operations = list(context.translate(
            rom[address - rom_base:address - rom_base + 8],
            base_address=address, max_instructions=1).ops)
        controls = {operation.opcode.name for operation in operations}
        if controls & {"BRANCH", "CALL", "BRANCHIND", "CALLIND", "RETURN"}:
            continue
        old = "    goto unsupported;\n"
        at = source.rfind(old, match.start(), match.end())
        if at >= 0:
            repairs.append((at, at + len(old),
                            f"    goto L_{address + item['size']:08x};\n"))
    for start, end, replacement in reversed(repairs):
        source = source[:start] + replacement + source[end:]

    branch_repairs = []
    if repair_fallthroughs:
        block_pattern = re.compile(
            r"(?m)^L_([0-9a-f]{8}):\n(?:(?!^L_)[\s\S])*?(?=^L_|finished:)"
        )
        for match in block_pattern.finditer(source):
            if "goto unsupported;" not in match.group(0):
                continue
            address = int(match.group(1), 16)
            item = traced.get(address)
            if item is None:
                continue
            context = pypcode.Context(
                "ARM:LE:32:v8T" if item["thumb"] else "ARM:LE:32:v8")
            operations = list(context.translate(
                rom[address - rom_base:address - rom_base + 8],
                base_address=address, max_instructions=1).ops)
            branches = [operation for operation in operations
                        if operation.opcode.name == "CBRANCH"]
            if len(branches) != 1:
                continue
            target = direct_target(branches[0].inputs[0])
            if target not in lifted:
                continue
            conditional = re.search(
                r"(?m)^(    if \(.*\)) goto unsupported;$", match.group(0))
            if conditional:
                start = match.start() + conditional.start()
                end = match.start() + conditional.end()
                branch_repairs.append(
                    (start, end, conditional.group(1) +
                     f" goto L_{target:08x};"))
        for start, end, replacement in reversed(branch_repairs):
            source = source[:start] + replacement + source[end:]
    output_path.write_text(source, encoding="utf-8", newline="\n")
    print(f"added {len(lifted)} Prime instructions; "
          f"{len(missing_variables)} new temporaries; "
          f"repaired {len(repairs)} fallthroughs and "
          f"{len(branch_repairs)} branches")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repair-fallthroughs", action="store_true")
    args = parser.parse_args()
    extend(args.source, args.trace, args.rom, args.output,
           args.repair_fallthroughs)


if __name__ == "__main__":
    main()
