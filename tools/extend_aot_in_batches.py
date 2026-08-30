#!/usr/bin/env python3
"""Run the AOT extender in fresh Python processes to bound pypcode memory use."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


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
    args.output.parent.mkdir(parents=True, exist_ok=True)

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
            print(f"AOT batch {index}/{total}: {len(batch['instructions'])} trace instructions", flush=True)
            subprocess.run(cmd, check=True)
            current = out_path
        shutil.copyfile(current, args.output)


if __name__ == "__main__":
    main()
