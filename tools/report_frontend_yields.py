#!/usr/bin/env python3
"""Report the remaining yield/resume islands in the generated 5320 frontend AOT source.

The generated frontend exposes the addresses at which native AOT execution must
return to the transition runtime. Keeping this report in CI makes the remaining
Unicorn dependency measurable while the yield islands are ported away.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _label_blocks(text: str) -> dict[int, list[str]]:
    blocks: dict[int, list[str]] = {}
    current: int | None = None
    for line in text.splitlines():
        match = re.match(r"L_([0-9a-fA-F]{8}):", line)
        if match:
            current = int(match.group(1), 16)
            blocks[current] = [line]
        elif current is not None:
            if line == "finished:" or re.match(r"L_[0-9a-fA-F]{8}:", line):
                current = None
            else:
                blocks[current].append(line)
    return blocks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--json", dest="json_path", type=Path)
    args = parser.parse_args()

    text = args.source.read_text(encoding="utf-8")
    blocks = _label_blocks(text)

    resume_addresses = sorted({
        int(value, 16)
        for value in re.findall(r"(?:return|case\s+\d+\s*:)\s*(?:UINT64_C\()?\s*0x([0-9a-fA-F]{6,8})", text)
        if int(value, 16) >= 0x10000000
    })

    labels = set(blocks)
    yielded_from = sorted(
        address for address, lines in blocks.items()
        if any("goto yielded;" in line for line in lines)
    )

    resume_body = re.search(
        r"uint32_t\s+nokia_frontend_resume_address\s*\([^)]*\)\s*\{([\s\S]*?)\n\}",
        text,
    )
    explicit = []
    if resume_body:
        explicit = sorted({
            int(value, 16)
            for value in re.findall(r"0x([0-9a-fA-F]{6,8})", resume_body.group(1))
        })
    if explicit:
        resume_addresses = explicit

    yield_blocks = {
        f"0x{address:08x}": blocks[address]
        for address in yielded_from
    }
    report = {
        "translated_instruction_labels": len(labels),
        "resume_address_count": len(resume_addresses),
        "resume_addresses": [f"0x{x:08x}" for x in resume_addresses],
        "yield_site_count": len(yielded_from),
        "yield_sites": [f"0x{x:08x}" for x in yielded_from],
        "yield_blocks": yield_blocks,
    }

    print("5320 native frontend AOT coverage report")
    print(f"  translated instruction labels: {report['translated_instruction_labels']}")
    print(f"  exported resume addresses:     {report['resume_address_count']}")
    for address in report["resume_addresses"]:
        print(f"    resume {address}")
    print(f"  explicit yield sites:          {report['yield_site_count']}")
    for address in report["yield_sites"]:
        print(f"    yield  {address}")
        print("      generated block:")
        for line in yield_blocks[address]:
            print(f"        {line}")

    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
