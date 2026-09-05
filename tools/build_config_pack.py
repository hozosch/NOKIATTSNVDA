#!/usr/bin/env python3
"""Deduplicate Nokia srsf blobs into one compact, architecture-neutral file."""

from __future__ import annotations

import argparse
import hashlib
import re
import struct
from pathlib import Path


MAGIC = b"NKCFGP1\0"
VERSION = 1
HEADER = struct.Struct("<8sIIII")
ENTRY = struct.Struct("<III")
BLOB = struct.Struct("<II")
NAME = re.compile(r"srsf_(\d+)_(\d+)\.bin", re.IGNORECASE)


def build(source: Path) -> tuple[bytes, int, int]:
    entries: list[tuple[int, int, int]] = []
    payloads: list[bytes] = []
    payload_by_hash: dict[bytes, int] = {}
    keys: set[tuple[int, int]] = set()
    for path in sorted(source.glob("srsf_*_*.bin")):
        match = NAME.fullmatch(path.name)
        if not match:
            continue
        key = (int(match.group(1)), int(match.group(2)))
        if key in keys:
            raise ValueError(f"duplicate configuration key {key}")
        keys.add(key)
        data = path.read_bytes()
        digest = hashlib.sha256(data).digest()
        index = payload_by_hash.get(digest)
        if index is None:
            index = len(payloads)
            payload_by_hash[digest] = index
            payloads.append(data)
        elif payloads[index] != data:
            raise ValueError("SHA-256 collision in configuration data")
        entries.append((key[0], key[1], index))
    if not entries:
        raise ValueError(f"no srsf configuration blobs found in {source}")

    payload_offset = HEADER.size + len(entries) * ENTRY.size + len(payloads) * BLOB.size
    offsets: list[tuple[int, int]] = []
    position = 0
    for data in payloads:
        offsets.append((position, len(data)))
        position += len(data)
    packed = bytearray(HEADER.pack(
        MAGIC, VERSION, len(entries), len(payloads), payload_offset
    ))
    for item in entries:
        packed.extend(ENTRY.pack(*item))
    for item in offsets:
        packed.extend(BLOB.pack(*item))
    for data in payloads:
        packed.extend(data)
    return bytes(packed), len(entries), len(payloads)


def read(path: Path) -> list[tuple[int, int, bytes]]:
    raw = path.read_bytes()
    if len(raw) < HEADER.size:
        raise ValueError("configuration pack is truncated")
    magic, version, entry_count, blob_count, payload_offset = HEADER.unpack_from(raw)
    if magic != MAGIC or version != VERSION:
        raise ValueError("unsupported configuration pack")
    table_end = HEADER.size + entry_count * ENTRY.size + blob_count * BLOB.size
    if payload_offset != table_end or table_end > len(raw):
        raise ValueError("invalid configuration pack tables")
    entries = [
        ENTRY.unpack_from(raw, HEADER.size + index * ENTRY.size)
        for index in range(entry_count)
    ]
    blobs = [
        BLOB.unpack_from(raw, HEADER.size + entry_count * ENTRY.size + index * BLOB.size)
        for index in range(blob_count)
    ]
    result = []
    for type_id, data_id, blob_index in entries:
        if blob_index >= blob_count:
            raise ValueError("configuration entry references an invalid blob")
        offset, size = blobs[blob_index]
        start = payload_offset + offset
        end = start + size
        if start < payload_offset or end > len(raw):
            raise ValueError("configuration blob lies outside the pack")
        result.append((type_id, data_id, raw[start:end]))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    packed, entries, unique = build(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(packed)
    print(
        f"packed {entries} configurations as {unique} unique payloads: "
        f"{len(packed)} bytes"
    )


if __name__ == "__main__":
    main()
