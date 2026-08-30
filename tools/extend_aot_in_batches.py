#!/usr/bin/env python3
"""Run the AOT extender in fresh Python processes to bound pypcode memory use."""
from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def read_source(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return f.read()
    return path.read_text(encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lifter", type=Path, required=True)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--trace", type=Path, required=True)
    ap.add_argument("--rom", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--batch-size", type=int, default=700)
    ap.add_argument("--repair-fallthroughs", action="store_true")
    args = ap.parse_args()

    payload = json.loads(args.trace.read_text(encoding="utf-8"))
    instructions = payload.get("instructions", [])
    if not instructions:
        raise SystemExit("trace contains no instructions")

    existing = {
        int(value, 16)
        for value in re.findall(r"(?m)^L_([0-9a-f]{8}):$", read_source(args.source))
    }
    original_count = len(instructions)
    instructions = [item for item in instructions if int(item["address"]) not in existing]
    print(
        f"AOT batching: {original_count} traced, {len(existing)} existing labels, "
        f"{len(instructions)} addresses still need lifting",
        flush=True,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not instructions:
        if args.source.suffix == ".gz":
            args.output.write_text(read_source(args.source), encoding="utf-8")
        else:
            shutil.copyfile(args.source, args.output)
        return

    with tempfile.TemporaryDirectory(prefix="nokia-aot-batches-") as td:
        td = Path(td)
        current = args.source
        total = (len(instructions) + args.batch_size - 1) // args.batch_size
        for index, start in enumerate(range(0, len(instructions), args.batch_size), 1):
            batch = dict(payload)
            batch["instructions"] = instructions[start:start + args.batch_size]
            batch["instruction_count"] = len(batch["instructions"])
            trace_path = td / f"batch-{index:03d}.json"
            out_path = td / f"aot-{index:03d}.c"
            trace_path.write_text(json.dumps(batch), encoding="utf-8")
            cmd = [
                sys.executable, str(args.lifter),
                "--source", str(current),
                "--trace", str(trace_path),
                "--rom", str(args.rom),
                "--output", str(out_path),
            ]
            if args.repair_fallthroughs:
                cmd.append("--repair-fallthroughs")
            print(
                f"AOT batch {index}/{total}: {len(batch['instructions'])} new instructions",
                flush=True,
            )
            subprocess.run(cmd, check=True)
            current = out_path
        shutil.copyfile(current, args.output)


if __name__ == "__main__":
    main()
