#!/usr/bin/env python3
"""Report the remaining yield/resume islands in the generated 5320 frontend AOT source.

The generated frontend exposes the addresses at which native AOT execution must
return to the transition runtime.  Keeping this report in CI makes the remaining
Unicorn dependency measurable while the yield islands are ported away.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--json", dest="json_path", type=Path)
    args = parser.parse_args()

    text = args.source.read_text(encoding="utf-8")

    resume_addresses = sorted({
        int(value, 16)
        for value in re.findall(r"(?:return|case\s+\d+\s*:)\s*(?:UINT64_C\()?\s*0x([0-9a-fA-F]{6,8})", text)
        if int(value, 16) >= 0x10000000
    })

    # The generated source names every translated instruction label L_xxxxxxxx.
    labels = {int(value, 16) for value in re.findall(r"(?m)^L_([0-9a-fA-F]{8}):", text)}

    # Locate blocks which explicitly yield and associate them with the nearest
    # preceding instruction label. This is independent of the generated resume
    # table representation and therefore useful as a cross-check.
    yielded_from = []
    last_label = None
    for line in text.splitlines():
        match = re.match(r"L_([0-9a-fA-F]{8}):", line)
        if match:
            last_label = int(match.group(1), 16)
        if "goto yielded;" in line and last_label is not None:
            yielded_from.append(last_label)
    yielded_from = sorted(set(yielded_from))

    # Prefer the explicit exported resume table when it can be identified by
    # looking at the small function body.
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

    report = {
        "translated_instruction_labels": len(labels),
        "resume_address_count": len(resume_addresses),
        "resume_addresses": [f"0x{x:08x}" for x in resume_addresses],
        "yield_site_count": len(yielded_from),
        "yield_sites": [f"0x{x:08x}" for x in yielded_from],
    }

    print("5320 native frontend AOT coverage report")
    print(f"  translated instruction labels: {report['translated_instruction_labels']}")
    print(f"  exported resume addresses:     {report['resume_address_count']}")
    for address in report["resume_addresses"]:
        print(f"    resume {address}")
    print(f"  explicit yield sites:          {report['yield_site_count']}")
    for address in report["yield_sites"]:
        print(f"    yield  {address}")

    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
