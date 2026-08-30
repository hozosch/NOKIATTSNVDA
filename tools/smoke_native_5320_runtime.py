#!/usr/bin/env python3
"""Build-time smoke test for the standalone 5320 DLL.

Python is only the test harness here. The DLL itself must not import Python or
Unicorn and must synthesize PCM from its native snapshot/AOT path.
"""
from __future__ import annotations

import argparse
import ctypes
import re
from pathlib import Path


class Callbacks(ctypes.Structure):
    pass

PCM = ctypes.CFUNCTYPE(None, ctypes.c_void_p,
                       ctypes.POINTER(ctypes.c_int16), ctypes.c_uint32,
                       ctypes.c_uint32)
INDEX = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint32)
Callbacks._fields_ = [('pcm', PCM), ('index', INDEX), ('user', ctypes.c_void_p)]


def blob_arg(data: bytes):
    array = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
    return array, ctypes.cast(array, ctypes.POINTER(ctypes.c_uint8))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('dll', type=Path)
    ap.add_argument('rom', type=Path)
    ap.add_argument('snapshot', type=Path)
    ap.add_argument('data_dir', type=Path)
    args = ap.parse_args()

    dll = ctypes.CDLL(str(args.dll.resolve()))
    dll.nokia_register_config_blob.argtypes = [ctypes.c_uint32, ctypes.c_uint32,
                                                ctypes.c_void_p, ctypes.c_uint32]
    dll.nokia_register_config_blob.restype = ctypes.c_int
    dll.nokia_runtime_create_5320_snapshot.argtypes = [
        ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
    dll.nokia_runtime_create_5320_snapshot.restype = ctypes.c_void_p
    dll.nokia_runtime_speak_utf16.argtypes = [ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint16), ctypes.c_uint32,
        ctypes.POINTER(Callbacks)]
    dll.nokia_runtime_speak_utf16.restype = ctypes.c_int
    dll.nokia_runtime_last_error.argtypes = [ctypes.c_void_p]
    dll.nokia_runtime_last_error.restype = ctypes.c_int
    dll.nokia_runtime_destroy.argtypes = [ctypes.c_void_p]

    held = []
    for path in sorted(args.data_dir.glob('srsf_*_*.bin')):
        match = re.fullmatch(r'srsf_(\d+)_(\d+)\.bin', path.name, re.I)
        if not match:
            continue
        data = path.read_bytes()
        buf = ctypes.create_string_buffer(data)
        held.append(buf)
        if not dll.nokia_register_config_blob(int(match.group(1)),
                                               int(match.group(2)),
                                               buf, len(data)):
            raise SystemExit(f'failed registering {path.name}')
    print('registered config blobs:', len(held))

    rom_data = args.rom.read_bytes()
    snapshot_data = args.snapshot.read_bytes()
    rom_buf, rom_ptr = blob_arg(rom_data)
    snap_buf, snap_ptr = blob_arg(snapshot_data)
    runtime = dll.nokia_runtime_create_5320_snapshot(
        rom_ptr, len(rom_data), snap_ptr, len(snapshot_data))
    if not runtime:
        raise SystemExit('native snapshot constructor failed')

    samples = [0]
    calls = [0]
    @PCM
    def on_pcm(_user, _samples, count, rate):
        if rate != 16000:
            raise RuntimeError(f'unexpected sample rate {rate}')
        samples[0] += int(count)
        calls[0] += 1
    @INDEX
    def on_index(_user, _index):
        pass
    callbacks = Callbacks(on_pcm, on_index, None)
    text = 'Hallo Welt'.encode('utf-16-le')
    words = (ctypes.c_uint16 * (len(text)//2)).from_buffer_copy(text)
    try:
        ok = dll.nokia_runtime_speak_utf16(runtime, words, len(words),
                                            ctypes.byref(callbacks))
        error = dll.nokia_runtime_last_error(runtime)
        print('native speak result:', ok, 'error:', error,
              'pcm callbacks:', calls[0], 'samples:', samples[0])
        if not ok or samples[0] <= 0:
            raise SystemExit(f'native synthesis failed: error={error}, samples={samples[0]}')
    finally:
        dll.nokia_runtime_destroy(runtime)


if __name__ == '__main__':
    main()
