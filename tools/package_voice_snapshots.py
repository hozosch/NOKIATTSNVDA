#!/usr/bin/env python3
"""Store Nokia voice snapshots as deterministic gzip files for packaging."""
from __future__ import annotations

import argparse
import gzip
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("snapshots", nargs="+", type=Path)
    parser.add_argument("--expected-count", type=int)
    args = parser.parse_args()

    if args.expected_count is not None and len(args.snapshots) != args.expected_count:
        raise SystemExit(
            f"expected {args.expected_count} snapshots, got {len(args.snapshots)}"
        )
    args.destination.mkdir(parents=True, exist_ok=True)
    names: set[str] = set()
    compressed_size = 0
    uncompressed_size = 0
    for source in args.snapshots:
        if not source.is_file():
            raise SystemExit(f"snapshot is missing: {source}")
        name = source.name + ".gz"
        if name in names:
            raise SystemExit(f"duplicate snapshot name: {source.name}")
        names.add(name)
        raw = source.read_bytes()
        packed = gzip.compress(raw, compresslevel=9, mtime=0)
        if gzip.decompress(packed) != raw:
            raise SystemExit(f"snapshot compression verification failed: {source}")
        (args.destination / name).write_bytes(packed)
        uncompressed_size += len(raw)
        compressed_size += len(packed)
    print(
        f"packaged snapshots: {len(names)}; "
        f"uncompressed bytes: {uncompressed_size}; "
        f"compressed bytes: {compressed_size}"
    )


if __name__ == "__main__":
    main()
