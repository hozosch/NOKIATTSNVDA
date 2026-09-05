#!/usr/bin/env python3
"""Restore missing taken edges in the traced 5320 Klatt routine.

The build-time trace did not take two signed 16-bit saturation branches or
one normalization-loop back edge.  The original Thumb code contains all
three branches, so repair the generated C before compiling the native DLL.
"""

from pathlib import Path
import argparse
import re

NORMALIZE_SOURCE = 0x830FA42A
NORMALIZE_TARGET = 0x830FA426
SATURATE_SOURCES = (0x830FA20E, 0x830FA214)
SATURATE_TARGET = 0x830FA22C


def label_block(text: str, address: int) -> tuple[int, int, str]:
    label = f"L_{address:08x}:"
    start = text.find(label)
    if start < 0:
        raise SystemExit(f"source label {label} is missing")
    match = re.search(r"(?m)^L_[0-9a-f]{8}:$", text[start + len(label):])
    end = len(text) if match is None else start + len(label) + match.start()
    return start, end, text[start:end]


def replace_unsupported_edge(text: str, source: int, target: int) -> str:
    start, end, block = label_block(text, source)
    old = "goto unsupported;"
    new = f"goto L_{target:08x};"
    if new in block:
        return text
    count = block.count(old)
    if count != 1:
        raise SystemExit(
            f"expected exactly one unsupported edge in L_{source:08x}, "
            f"found {count}"
        )
    return text[:start] + block.replace(old, new, 1) + text[end:]


def add_saturation_target(text: str) -> str:
    target_label = f"L_{SATURATE_TARGET:08x}:"
    if target_label in text:
        return text
    continuation = "L_830fa232:"
    if continuation not in text:
        raise SystemExit(f"saturation continuation {continuation} is missing")
    target_code = (
        f"{target_label}\n"
        f"  nokia_at = 0x{SATURATE_TARGET:08x}u;\n"
        "  reg_r3 = nokia_mem_load(&machine, "
        "(reg_sp + UINT64_C(68)) & UINT64_C(0xffffffff), 4);\n"
        "  reg_r1 = (reg_r7 << 1) & UINT64_C(0xffffffff);\n"
        "  if (!nokia_mem_store(&machine, "
        "(reg_r3 + reg_r1) & UINT64_C(0xffffffff), "
        "reg_r2 & UINT64_C(0xffff), 2)) goto unsupported;\n"
        "  goto L_830fa232;\n"
    )
    return text.replace(continuation, target_code + continuation, 1)


def add_normalization_target(text: str) -> str:
    target_label = f"L_{NORMALIZE_TARGET:08x}:"
    if target_label in text:
        return text
    continuation = "L_830fa428:"
    if continuation not in text:
        raise SystemExit(f"loop continuation {continuation} is missing")
    target_code = (
        f"{target_label}\n"
        f"  nokia_at = 0x{NORMALIZE_TARGET:08x}u;\n"
        "  reg_r0 = reg_r0 - reg_r1;\n"
        "  goto L_830fa428;\n"
    )
    return text.replace(continuation, target_code + continuation, 1)


def patch(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = add_saturation_target(text)
    for source in SATURATE_SOURCES:
        text = replace_unsupported_edge(text, source, SATURATE_TARGET)
    text = add_normalization_target(text)
    text = replace_unsupported_edge(
        text, NORMALIZE_SOURCE, NORMALIZE_TARGET
    )
    path.write_text(text, encoding="utf-8")
    print(
        "repaired Klatt signed-saturation edges "
        "0x830fa20e/0x830fa214 -> 0x830fa22c and normalization edge "
        "0x830fa42a -> 0x830fa426"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    patch(args.source)


if __name__ == "__main__":
    main()
