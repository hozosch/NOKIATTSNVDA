#!/usr/bin/env python3
"""Split oversized functions in an already split frontend AOT source.

The original splitter groups a fixed number of guest instructions.  A later
closure extension can add much more p-code to one address range than another,
leaving a few generated C functions large enough to exhaust the MSVC ARM64
linker's Cortex-A53 erratum-thunk placement.  Repartition each existing
address range by emitted C line count while preserving the existing outer
ranges, and route newly cross-chunk jumps through the normal dispatcher.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

try:
    from .split_frontend_aot import route
except ImportError:  # direct script execution
    from split_frontend_aot import route


DEFAULT_MAX_LINES = 6000
CHUNK_FUNCTION = re.compile(
    r"(?m)^static int nokia_frontend_chunk_(\d+)\("
)
GUEST_LABEL = re.compile(r"(?m)^L_([0-9a-f]{8}):$")
TABLE_START = "typedef int (*NokiaFrontendChunk)"
LIMIT_TABLE = re.compile(
    r"static const uint32_t nokia_frontend_chunk_limits\[\]=\{\n"
    r".*?\n\};",
    re.S,
)


def _blocks(function: str) -> list[tuple[int, list[str]]]:
    close = function.rfind("\n}")
    if close < 0:
        raise ValueError("split frontend chunk closing brace was not found")
    body = function[:close]
    labels = list(GUEST_LABEL.finditer(body))
    if not labels:
        raise ValueError("split frontend chunk contains no guest labels")
    result = []
    for index, match in enumerate(labels):
        end = labels[index + 1].start() if index + 1 < len(labels) else len(body)
        result.append((
            int(match.group(1), 16),
            body[match.start():end].rstrip().splitlines(),
        ))
    return result


def _partition(
    blocks: list[tuple[int, list[str]]], max_lines: int
) -> list[list[tuple[int, list[str]]]]:
    groups: list[list[tuple[int, list[str]]]] = []
    current: list[tuple[int, list[str]]] = []
    current_lines = 4
    for block in sorted(blocks):
        block_lines = len(block[1]) + 1  # one switch case plus the block
        if current and current_lines + block_lines + 1 > max_lines:
            groups.append(current)
            current = []
            current_lines = 4
        current.append(block)
        current_lines += block_lines
    if current:
        groups.append(current)
    return groups


def _render_function(
    index: int, blocks: list[tuple[int, list[str]]]
) -> str:
    local = {address for address, _lines in blocks}
    out = [
        f"static int nokia_frontend_chunk_{index}(NokiaFrontendState*state,",
        " NokiaFrontendMachine*machine_ptr,const NokiaFrontendHost*host){",
        "    switch((uint32_t)reg_pc&~1u){",
    ]
    out.extend(
        f"    case 0x{address:08x}u: goto L_{address:08x};"
        for address, _lines in blocks
    )
    out.extend(("    default: return NOKIA_FRONTEND_YIELDED;", "    }"))
    for _address, lines in blocks:
        out.extend(route(line, local) for line in lines)
    out.append("}")

    rendered = "\n".join(out)
    labels = {int(value, 16) for value in GUEST_LABEL.findall(rendered)}
    targets = {
        int(value, 16)
        for value in re.findall(r"goto L_([0-9a-f]{8});", rendered)
    }
    external = targets - labels
    if external:
        values = ", ".join(f"0x{value:08x}" for value in sorted(external))
        raise ValueError(f"chunk {index} retains cross-chunk gotos: {values}")
    return rendered


def rechunk_source(source: str, max_lines: int = DEFAULT_MAX_LINES) -> str:
    if max_lines < 16:
        raise ValueError("max_lines must be at least 16")
    matches = list(CHUNK_FUNCTION.finditer(source))
    if not matches:
        raise ValueError("split frontend chunk functions were not found")
    for expected, match in enumerate(matches):
        if int(match.group(1)) != expected:
            raise ValueError("split frontend chunk indices are not contiguous")

    table_at = source.index(TABLE_START, matches[-1].end())
    limit_match = LIMIT_TABLE.search(source, table_at)
    if not limit_match:
        raise ValueError("split frontend chunk-limit table was not found")

    old_blocks: list[list[tuple[int, list[str]]]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else table_at
        old_blocks.append(_blocks(source[match.start():end]))

    seen: set[int] = set()
    groups: list[list[tuple[int, list[str]]]] = []
    for blocks in old_blocks:
        addresses = {address for address, _lines in blocks}
        duplicate = addresses & seen
        if duplicate:
            values = ", ".join(f"0x{value:08x}" for value in sorted(duplicate))
            raise ValueError(f"duplicate guest labels: {values}")
        seen.update(addresses)
        groups.extend(_partition(blocks, max_lines))

    functions = "\n\n".join(
        _render_function(index, blocks)
        for index, blocks in enumerate(groups)
    )
    table = "\n".join([
        "typedef int (*NokiaFrontendChunk)(NokiaFrontendState*,NokiaFrontendMachine*,const NokiaFrontendHost*);",
        "static NokiaFrontendChunk nokia_frontend_chunks[]={",
        *(f"    nokia_frontend_chunk_{index}," for index in range(len(groups))),
        "};",
        "static const uint32_t nokia_frontend_chunk_limits[]={",
        *(f"    0x{blocks[-1][0]:08x}u," for blocks in groups),
        "};",
    ])
    tail = source[limit_match.end():].lstrip("\n")
    return (
        source[:matches[0].start()].rstrip()
        + "\n\n"
        + functions
        + "\n\n"
        + table
        + "\n\n"
        + tail
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES)
    args = parser.parse_args()
    source = args.source.read_text(encoding="utf-8")
    old_count = len(CHUNK_FUNCTION.findall(source))
    output = rechunk_source(source, args.max_lines)
    new_count = len(CHUNK_FUNCTION.findall(output))
    args.source.write_text(output, encoding="utf-8", newline="\n")
    print(
        f"rechunked split frontend: {old_count} -> {new_count} functions; "
        f"maximum {args.max_lines} generated lines"
    )


if __name__ == "__main__":
    main()
