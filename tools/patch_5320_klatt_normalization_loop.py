#!/usr/bin/env python3
"""Restore missing edges in the traced 5320 Klatt routine.

The build-time trace did not take two signed 16-bit saturation branches or
several voice-dependent fallthroughs.  The original Thumb code contains
these paths, so repair the generated C before compiling the native DLL.
"""

from pathlib import Path
import argparse
import re

NORMALIZE_SOURCE = 0x830FA42A
NORMALIZE_TARGET = 0x830FA426
SATURATE_SOURCES = (0x830FA20E, 0x830FA214)
SATURATE_TARGET = 0x830FA22C
MISSING_FALLTHROUGHS = (
    (0x830F99EA, 0x830F99EC, 0x830F99F0, (
        "reg_r1 = (reg_r1 - UINT64_C(1)) & UINT64_C(0xffffffff);",
        "reg_r3 = UINT64_C(1);",
    )),
    (0x830F9A00, 0x830F9A02, 0x830F9A06, (
        "reg_r1 = (reg_r1 - reg_r2) & UINT64_C(0xffffffff);",
        "reg_r0 = (reg_r0 + UINT64_C(1)) & UINT64_C(0xffffffff);",
    )),
    (0x830F9A16, 0x830F9A18, 0x830F9A1C, (
        "reg_r1 = (reg_r1 - reg_r2) & UINT64_C(0xffffffff);",
        "reg_r0 = (reg_r0 + UINT64_C(1)) & UINT64_C(0xffffffff);",
    )),
    (0x830F9A2C, 0x830F9A2E, 0x830F9A32, (
        "reg_r1 = (reg_r1 - reg_r2) & UINT64_C(0xffffffff);",
        "reg_r0 = (reg_r0 + UINT64_C(1)) & UINT64_C(0xffffffff);",
    )),
    # The German trace only took the signed-greater-than branch at 0x830fa55a.
    # Several Slavic voices also take its ordinary fallthrough, which sets r5
    # to one before joining the already translated continuation.
    (0x830FA55A, 0x830FA55C, 0x830FA55E, (
        "reg_r5 = UINT64_C(1);",
        "reg_tmpNG = UINT64_C(0);",
        "reg_tmpZR = UINT64_C(0);",
        "reg_ZR = reg_tmpZR;",
        "reg_NG = reg_tmpNG;",
    )),
    # The original German-male trace only took the non-zero branch here.
    # German and Dutch female voices can fall through to the Thumb
    # ``movs r1, #0`` before rejoining the translated continuation.
    (0x830FAB9E, 0x830FABA0, 0x830FABA2, (
        "reg_r1 = UINT64_C(0);",
        "reg_tmpNG = UINT64_C(0);",
        "reg_tmpZR = UINT64_C(1);",
        "reg_ZR = reg_tmpZR;",
        "reg_NG = reg_tmpNG;",
    )),
)


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


def add_fallthrough_target(
    text: str, target: int, continuation: int, operations: tuple[str, ...]
) -> str:
    target_label = f"L_{target:08x}:"
    if target_label in text:
        return text
    continuation_label = f"L_{continuation:08x}:"
    if continuation_label not in text:
        raise SystemExit(
            f"division continuation {continuation_label} is missing"
        )
    body = [target_label, f"  nokia_at = 0x{target:08x}u;"]
    body.extend(f"  {operation}" for operation in operations)
    body.append(f"  goto L_{continuation:08x};")
    return text.replace(continuation_label, "\n".join(body) + "\n" + continuation_label, 1)


def patch(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = add_saturation_target(text)
    for source in SATURATE_SOURCES:
        text = replace_unsupported_edge(text, source, SATURATE_TARGET)
    for source, target, continuation, operations in MISSING_FALLTHROUGHS:
        text = add_fallthrough_target(text, target, continuation, operations)
        text = replace_unsupported_edge(text, source, target)
    text = add_normalization_target(text)
    text = replace_unsupported_edge(
        text, NORMALIZE_SOURCE, NORMALIZE_TARGET
    )
    path.write_text(text, encoding="utf-8")
    print(
        "repaired Klatt signed-saturation, fixed-point division, comparison, "
        "voice-dependent fallthrough, and normalization-loop edges"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    patch(args.source)


if __name__ == "__main__":
    main()
