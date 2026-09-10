#!/usr/bin/env python3
"""Verify all eight Nokia 6650 language/voice snapshots against reference PCM."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
from pathlib import Path

from smoke_native_5500_voices import (
    Callbacks,
    DIAGNOSTICS,
    INDEX,
    PCM,
    byte_array,
    config_blobs,
    write_rom_trace,
)
from native_text_regressions import cases_for


SAMPLES = {
    10: "Hello world 123. NVDA menu options tools settings.",
    51: "Bonjour le monde 123. Menu NVDA options outils paramètres.",
    76: "Olá mundo 123. Menu NVDA opções ferramentas configurações.",
    83: "Hola mundo 123. Menú NVDA opciones herramientas configuración.",
}

# Each digest covers two consecutive calls on one restored runtime. Besides
# output fidelity, this guards paths that are used only after a warm call.
EXPECTED_REPEATED_SHA256 = {
    (10, "male"): "29df75bf8bbba122e86fcfb8a0462d7d1d9f14212397d7225fab7c43b603ad16",
    (10, "female"): "addab163296fcd92d14cc312229733386df2e4bad3383bfe773f3aa8edbf3f91",
    (51, "male"): "63324d2bbba91843855aea2cd721f78ab86dcd3600010638e0e3c82de92b53c8",
    (51, "female"): "869d6d86d448cd9a602bc8e2e2e1587f9b9872cbd410015b98ebfe9862921512",
    (76, "male"): "6fc5c75b7cb1a9ca6f886b21644694c2a268aa53500a2e861bbd2062fb668ac4",
    (76, "female"): "deb9f3a687a3dc4513be5f304037ecfd02e0d164c23bd86e81af432e35d3aec7",
    (83, "male"): "5d609962e229e670b3957cab298635923b5359f75ee46466704e796cb9a47e84",
    (83, "female"): "6108701d1d96f6693cb9a69bdb4083ef2903b64061f432f411155e243e9b8b2d",
}

KLATT_DIAGNOSTICS = (
    ("klattLastPc", "nokia_klatt_last_pc"),
    ("klattLastR0", "nokia_klatt_last_r0"),
    ("klattLastR7", "nokia_klatt_last_r7"),
    ("klattBadAddress", "nokia_klatt_last_bad_address"),
)


def bind(dll) -> None:
    dll.nokia_register_config_blob.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    dll.nokia_register_config_blob.restype = ctypes.c_int
    dll.nokia_runtime_create_6650_snapshot.argtypes = [
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_size_t,
    ]
    dll.nokia_runtime_create_6650_snapshot.restype = ctypes.c_void_p
    dll.nokia_runtime_speak_utf16.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint16),
        ctypes.c_uint32,
        ctypes.POINTER(Callbacks),
    ]
    dll.nokia_runtime_speak_utf16.restype = ctypes.c_int
    dll.nokia_runtime_set_rate.argtypes = [ctypes.c_void_p, ctypes.c_double]
    dll.nokia_runtime_set_rate.restype = ctypes.c_int
    dll.nokia_runtime_set_pitch.argtypes = [ctypes.c_void_p, ctypes.c_double]
    dll.nokia_runtime_set_pitch.restype = ctypes.c_int
    dll.nokia_runtime_last_error.argtypes = [ctypes.c_void_p]
    dll.nokia_runtime_last_error.restype = ctypes.c_int
    dll.nokia_runtime_destroy.argtypes = [ctypes.c_void_p]
    dll.nokia_runtime_rom_trace_reset.argtypes = []
    dll.nokia_runtime_rom_trace_page_size.restype = ctypes.c_uint32
    dll.nokia_runtime_rom_trace_page_used.argtypes = [ctypes.c_uint32]
    dll.nokia_runtime_rom_trace_page_used.restype = ctypes.c_int
    for _label, export in (*DIAGNOSTICS, *KLATT_DIAGNOSTICS):
        function = getattr(dll, export, None)
        if function:
            function.argtypes = []
            function.restype = ctypes.c_uint32


def synthesize_repeated_and_prosody(
    dll, rom, rom_size, snapshot_path: Path, text: str
) -> tuple[bytes, bytes]:
    snapshot_data, snapshot = byte_array(snapshot_path)
    runtime = dll.nokia_runtime_create_6650_snapshot(
        rom, rom_size, snapshot, len(snapshot_data)
    )
    if not runtime:
        raise RuntimeError("snapshot restore failed")
    if not dll.nokia_runtime_set_rate(runtime, 1.0):
        dll.nokia_runtime_destroy(runtime)
        raise RuntimeError("setting neutral rate failed")
    if not dll.nokia_runtime_set_pitch(runtime, 1.0):
        dll.nokia_runtime_destroy(runtime)
        raise RuntimeError("setting neutral pitch failed")
    output = []

    @PCM
    def on_pcm(_user, samples, count, sample_rate):
        if sample_rate != 16000:
            raise RuntimeError(f"unexpected sample rate {sample_rate}")
        output.append(ctypes.string_at(samples, count * 2))

    @INDEX
    def on_index(_user, _index):
        pass

    callbacks = Callbacks(on_pcm, on_index, None)
    encoded = text.encode("utf-16-le")
    units = (ctypes.c_uint16 * (len(encoded) // 2)).from_buffer_copy(encoded)
    try:
        for call in range(2):
            ok = dll.nokia_runtime_speak_utf16(
                runtime, units, len(units), ctypes.byref(callbacks)
            )
            error = dll.nokia_runtime_last_error(runtime)
            if not ok or error:
                diagnostics = ", ".join(
                    f"{label}=0x{function():08x}"
                    for label, export in (*KLATT_DIAGNOSTICS, *DIAGNOSTICS)
                    if (function := getattr(dll, export, None))
                )
                raise RuntimeError(
                    f"call={call + 1}, result={ok}, error={error}"
                    + (f", {diagnostics}" if diagnostics else "")
                )
        repeated_audio = b"".join(output)
        if not repeated_audio or not any(repeated_audio):
            raise RuntimeError(
                f"silent repeated output: pcm_bytes={len(repeated_audio)}"
            )

        # Exercise both native prosody controls only after two calls on the
        # same restored engine. This detects state-reuse problems while the
        # reference digest above remains limited to neutral output.
        if not dll.nokia_runtime_set_rate(runtime, 4.0):
            raise RuntimeError("setting high rate failed")
        if not dll.nokia_runtime_set_pitch(runtime, 1.25):
            raise RuntimeError("setting raised pitch failed")
        output.clear()
        ok = dll.nokia_runtime_speak_utf16(
            runtime, units, len(units), ctypes.byref(callbacks)
        )
        error = dll.nokia_runtime_last_error(runtime)
        prosody_audio = b"".join(output)
        if not ok or error or not prosody_audio or not any(prosody_audio):
            diagnostics = ", ".join(
                f"{label}=0x{function():08x}"
                for label, export in (*KLATT_DIAGNOSTICS, *DIAGNOSTICS)
                if (function := getattr(dll, export, None))
            )
            raise RuntimeError(
                "prosody call failed: "
                f"result={ok}, error={error}, pcm_bytes={len(prosody_audio)}"
                + (f", {diagnostics}" if diagnostics else "")
            )
        return repeated_audio, prosody_audio
    finally:
        dll.nokia_runtime_destroy(runtime)


def synthesize_once(
    dll, rom, rom_size, snapshot_path: Path, text: str
) -> bytes:
    snapshot_data, snapshot = byte_array(snapshot_path)
    runtime = dll.nokia_runtime_create_6650_snapshot(
        rom, rom_size, snapshot, len(snapshot_data)
    )
    if not runtime:
        raise RuntimeError("snapshot restore failed")
    output = []

    @PCM
    def on_pcm(_user, samples, count, sample_rate):
        if sample_rate != 16000:
            raise RuntimeError(f"unexpected sample rate {sample_rate}")
        output.append(ctypes.string_at(samples, count * 2))

    @INDEX
    def on_index(_user, _index):
        pass

    callbacks = Callbacks(on_pcm, on_index, None)
    encoded = text.encode("utf-16-le")
    units = (ctypes.c_uint16 * (len(encoded) // 2)).from_buffer_copy(encoded)
    try:
        if not dll.nokia_runtime_set_rate(runtime, 1.0):
            raise RuntimeError("setting neutral rate failed")
        if not dll.nokia_runtime_set_pitch(runtime, 1.0):
            raise RuntimeError("setting neutral pitch failed")
        ok = dll.nokia_runtime_speak_utf16(
            runtime, units, len(units), ctypes.byref(callbacks)
        )
        error = dll.nokia_runtime_last_error(runtime)
        audio = b"".join(output)
        if not ok or error or not audio or not any(audio):
            diagnostics = ", ".join(
                f"{label}=0x{function():08x}"
                for label, export in (*KLATT_DIAGNOSTICS, *DIAGNOSTICS)
                if (function := getattr(dll, export, None))
            )
            raise RuntimeError(
                f"result={ok}, error={error}, pcm_bytes={len(audio)}"
                + (f", {diagnostics}" if diagnostics else "")
            )
        return audio
    finally:
        dll.nokia_runtime_destroy(runtime)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dll", type=Path)
    parser.add_argument("rom", type=Path)
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("config", type=Path)
    parser.add_argument(
        "--coverage-one-gender",
        action="store_true",
        help="run the broad text corpus on male snapshots only",
    )
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
    dll.nokia_runtime_rom_trace_reset()
    failures = []
    validated = 0
    for language_id, sample in SAMPLES.items():
        for gender in ("male", "female"):
            voice = f"{language_id}-{gender}"
            snapshot = args.snapshot_dir / f"6650-{voice}.snapshot"
            if not snapshot.is_file():
                failures.append(f"{voice}: snapshot missing")
                continue
            try:
                audio, prosody_audio = synthesize_repeated_and_prosody(
                    dll, rom, len(rom_data), snapshot, sample
                )
            except Exception as error:
                failures.append(f"{voice}: {error}")
                continue
            digest = hashlib.sha256(audio).hexdigest()
            expected = EXPECTED_REPEATED_SHA256[(language_id, gender)]
            print(
                f"{voice}: pcm_bytes={len(audio)} sha256={digest} "
                f"prosody_pcm_bytes={len(prosody_audio)}"
            )
            if digest != expected:
                failures.append(f"{voice}: expected {expected}, got {digest}")
            else:
                validated += 1
            if args.coverage_one_gender and gender != "male":
                continue
            for case_name, regression_text in cases_for("6650", language_id):
                try:
                    regression_audio = synthesize_once(
                        dll, rom, len(rom_data), snapshot, regression_text
                    )
                except Exception as error:
                    failures.append(
                        f"{voice} {case_name} {regression_text!r}: {error}"
                    )
                else:
                    print(
                        f"{voice} {case_name}: "
                        f"pcm_bytes={len(regression_audio)}"
                    )

    if args.rom_trace:
        write_rom_trace(dll, rom_data, args.rom_trace)
        print("wrote ROM trace:", args.rom_trace)
    print(f"validated repeated voices: {validated}/8; failures: {len(failures)}")
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
