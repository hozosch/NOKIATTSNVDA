#!/usr/bin/env python3
"""Smoke-test all five packaged Nokia 5500 language snapshots."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import re
import string
import struct
from pathlib import Path

from build_config_pack import read as read_config_pack


SAMPLES = {
    1: "Hello world 123",
    2: "Bonjour le monde 123",
    3: "Gegen Google Einstellungen 123",
    4: "Hola mundo 123",
    37: "مرحبا بالعالم 123",
}
EXPECTED_SHA256 = {
    1: "90773ec6e248756faadc31953c64fe8a7bcfd4434997f1a43dc0d5c9acda933e",
    2: "5a04f9d51e7b8264283eef41b6c7e5d0d7d8444219f7e822bba1c45d3fc0ec8e",
    3: "3faa562fea3db0030bf4e9f44b59f87a2248c9a6905b3d84e2c7a4adc75dcef3",
    4: "61e871ce235714ae418c6b1d485ab9d40ae35ba24077d6d57985a94cc1ccf6ad",
    37: "3e8256f46110d5649352534a7b86e7cb2964a4af5cc5875bb0c42b329094d3db",
}
EXTENDED_SAMPLES = {
    1: "Hello Google settings quotation marks.",
    2: "À bientôt, élève, Noël, cœur.",
    3: "Während später ÄÖÜ äöü ß.",
    4: "Árbol, niño, corazón, pingüino.",
    37: "1234567890",
}

PCM = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int16),
    ctypes.c_uint32, ctypes.c_uint32,
)
INDEX = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint32)


class Callbacks(ctypes.Structure):
    _fields_ = [("pcm", PCM), ("index", INDEX), ("user", ctypes.c_void_p)]


def byte_array(path: Path):
    data = path.read_bytes()
    return data, (ctypes.c_uint8 * len(data)).from_buffer_copy(data)


def config_blobs(path: Path):
    if path.is_file():
        yield from read_config_pack(path)
        return
    for item in sorted(path.glob("srsf_*_*.bin")):
        match = re.fullmatch(r"srsf_(\d+)_(\d+)\.bin", item.name, re.I)
        if match:
            yield int(match.group(1)), int(match.group(2)), item.read_bytes()


def bind(dll):
    dll.nokia_register_config_blob.argtypes = [
        ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32,
    ]
    dll.nokia_register_config_blob.restype = ctypes.c_int
    dll.nokia_runtime_create_5500_snapshot.argtypes = [
        ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
    ]
    dll.nokia_runtime_create_5500_snapshot.restype = ctypes.c_void_p
    dll.nokia_runtime_speak_utf16.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint16), ctypes.c_uint32,
        ctypes.POINTER(Callbacks),
    ]
    dll.nokia_runtime_speak_utf16.restype = ctypes.c_int
    dll.nokia_runtime_set_rate.argtypes = [ctypes.c_void_p, ctypes.c_double]
    dll.nokia_runtime_set_rate.restype = ctypes.c_int
    dll.nokia_runtime_last_error.argtypes = [ctypes.c_void_p]
    dll.nokia_runtime_last_error.restype = ctypes.c_int
    dll.nokia_runtime_destroy.argtypes = [ctypes.c_void_p]
    dll.nokia_runtime_rom_trace_page_size.restype = ctypes.c_uint32
    dll.nokia_runtime_rom_trace_page_used.argtypes = [ctypes.c_uint32]
    dll.nokia_runtime_rom_trace_page_used.restype = ctypes.c_int


def synthesize(dll, rom, rom_size, snapshot_path: Path, text: str, rate=1.0):
    snapshot_data, snapshot = byte_array(snapshot_path)
    runtime = dll.nokia_runtime_create_5500_snapshot(
        rom, rom_size, snapshot, len(snapshot_data)
    )
    if not runtime:
        raise RuntimeError("snapshot restore failed")
    if not dll.nokia_runtime_set_rate(runtime, rate):
        dll.nokia_runtime_destroy(runtime)
        raise RuntimeError(f"setting rate {rate} failed")
    pcm = []

    @PCM
    def on_pcm(_user, samples, count, sample_rate):
        if sample_rate != 16000:
            raise RuntimeError(f"unexpected sample rate {sample_rate}")
        pcm.append(ctypes.string_at(samples, count * 2))

    @INDEX
    def on_index(_user, _index):
        pass

    callbacks = Callbacks(on_pcm, on_index, None)
    encoded = text.encode("utf-16-le")
    units = (ctypes.c_uint16 * (len(encoded) // 2)).from_buffer_copy(encoded)
    try:
        ok = dll.nokia_runtime_speak_utf16(
            runtime, units, len(units), ctypes.byref(callbacks)
        )
        error = dll.nokia_runtime_last_error(runtime)
        audio = b"".join(pcm)
        if not ok or not audio or not any(audio):
            raise RuntimeError(
                f"synthesis result={ok}, error={error}, pcm_bytes={len(audio)}"
            )
        return audio
    finally:
        dll.nokia_runtime_destroy(runtime)


def write_rom_trace(dll, rom_data: bytes, output: Path) -> None:
    page_size = dll.nokia_runtime_rom_trace_page_size()
    virtual_size = (
        struct.unpack_from("<I", rom_data, 16)[0]
        if len(rom_data) >= 24 and rom_data[:8] == b"NKROMP1\0"
        else len(rom_data)
    )
    total_pages = (virtual_size + page_size - 1) // page_size
    used_pages = [
        page for page in range(total_pages)
        if dll.nokia_runtime_rom_trace_page_used(page)
    ]
    ranges = []
    for page in used_pages:
        if ranges and page == ranges[-1][1] + 1:
            ranges[-1][1] = page
        else:
            ranges.append([page, page])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "format": "nokia-rom-pages-v1",
        "pageSize": page_size,
        "virtualSize": virtual_size,
        "usedPageCount": len(used_pages),
        "usedPages": used_pages,
        "usedRanges": ranges,
    }, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dll", type=Path)
    parser.add_argument("rom", type=Path)
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("config", type=Path)
    parser.add_argument("--rom-trace", type=Path)
    args = parser.parse_args()

    dll = ctypes.CDLL(str(args.dll.resolve()))
    bind(dll)
    held = []
    for type_id, data_id, data in config_blobs(args.config):
        buffer = ctypes.create_string_buffer(data)
        held.append(buffer)
        if not dll.nokia_register_config_blob(type_id, data_id, buffer, len(data)):
            raise SystemExit(f"failed registering srsf_{type_id}_{data_id}.bin")
    if not held:
        raise SystemExit("no configuration blobs found")

    rom_data, rom = byte_array(args.rom)
    failures = []
    validated_voices = 0
    extended_passed = 0
    high_rate_passed = 0
    for language_id, sample in SAMPLES.items():
        snapshot = args.snapshot_dir / f"5500-{language_id}.snapshot"
        if not snapshot.is_file():
            failures.append(f"{language_id}: snapshot missing")
            continue
        try:
            audio = synthesize(dll, rom, len(rom_data), snapshot, sample)
        except Exception as error:
            failures.append(f"{language_id}: {error}")
            continue
        digest = hashlib.sha256(audio).hexdigest()
        print(f"{language_id}: pcm_bytes={len(audio)} sha256={digest}")
        if digest != EXPECTED_SHA256[language_id]:
            failures.append(
                f"{language_id}: expected {EXPECTED_SHA256[language_id]}, got {digest}"
            )
        else:
            validated_voices += 1
        for value in (*string.ascii_letters, EXTENDED_SAMPLES[language_id]):
            try:
                extended = synthesize(dll, rom, len(rom_data), snapshot, value)
            except Exception as error:
                failures.append(f"{language_id} {value!r}: {error}")
                continue
            if not extended or not any(extended):
                failures.append(f"{language_id} {value!r}: silent output")
                continue
            extended_passed += 1
        try:
            fast = synthesize(
                dll, rom, len(rom_data), snapshot, sample, rate=4.0
            )
        except Exception as error:
            failures.append(f"{language_id} high-rate {sample!r}: {error}")
        else:
            if not fast or not any(fast):
                failures.append(f"{language_id} high-rate {sample!r}: silent output")
            else:
                high_rate_passed += 1

    if args.rom_trace:
        write_rom_trace(dll, rom_data, args.rom_trace)
        print("wrote ROM trace:", args.rom_trace)
    print(f"validated voices: {validated_voices}/{len(SAMPLES)}; failures: {len(failures)}")
    print(f"extended utterances passed: {extended_passed}/{len(SAMPLES) * 53}")
    print(f"high-rate utterances passed: {high_rate_passed}/{len(SAMPLES)}")
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
