#!/usr/bin/env python3
"""Remove already-native Klatt instructions from a full 5320 lifecycle trace.

The remaining trace contains frontend, scheduler and the small DSP wrapper that
must be AOT-lifted into the standalone runtime. The Klatt entry itself remains a
native host boundary and is handled directly by the generated dispatcher.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path

KLATT_ENTRY = 0x830F9DB0
# These addresses also occur in the specialised Klatt corpus, but they are
# standalone ROM veneers used by the surrounding DSP/frontend path.  Removing
# them from the lifecycle corpus leaves an otherwise-native call stranded at a
# dispatcher yield, so keep them in the standalone frontend AOT.
KEEP_LIFECYCLE = {0x8310182C, 0x83101854, 0x8310188C}


def read_text(path: Path) -> str:
    if path.suffix == '.gz':
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return f.read()
    return path.read_text(encoding='utf-8')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('trace', type=Path)
    ap.add_argument('klatt_source', type=Path)
    ap.add_argument('output', type=Path)
    args = ap.parse_args()

    payload = json.loads(args.trace.read_text(encoding='utf-8'))
    klatt = {int(x, 16) for x in re.findall(
        r'(?m)^L_([0-9a-f]{8}):$', read_text(args.klatt_source))}
    before = len(payload['instructions'])
    removed = 0
    kept = []
    for item in payload['instructions']:
        address = int(item['address']) & ~1
        if address == KLATT_ENTRY:
            removed += 1
            continue
        if address in klatt and address not in KEEP_LIFECYCLE:
            removed += 1
            continue
        kept.append(item)
    payload['instructions'] = kept
    payload['instruction_count'] = len(kept)
    payload['klatt_labels_removed'] = removed
    payload['native_klatt_entry'] = f'0x{KLATT_ENTRY:08x}'
    payload['lifecycle_klatt_overlap_kept'] = [
        f'0x{x:08x}' for x in sorted(KEEP_LIFECYCLE)
        if any((int(i['address']) & ~1) == x for i in kept)
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    dsp = sum(1 for x in kept if 0x830F7A48 <= int(x['address']) < 0x83102E00)
    print('full lifecycle instructions:', before)
    print('already-native Klatt instructions removed:', removed)
    print('remaining instructions:', len(kept))
    print('remaining DSP-wrapper instructions:', dsp)
    print('kept standalone DSP veneers:', ', '.join(payload['lifecycle_klatt_overlap_kept']))


if __name__ == '__main__':
    main()
