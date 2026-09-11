#!/usr/bin/env python3
"""Render the independent S60 Klatt core to a mono 16 kHz WAV file."""
from __future__ import annotations

import argparse
import ctypes
import wave
from pathlib import Path


SAMPLE_RATE = 16000
PCM_CALLBACK = ctypes.CFUNCTYPE(
    None,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int16),
    ctypes.c_uint32,
    ctypes.c_uint32,
)


class Callbacks(ctypes.Structure):
    _fields_ = [("pcm", PCM_CALLBACK), ("user", ctypes.c_void_p)]


def bind(dll: ctypes.CDLL) -> None:
    dll.classic_klatt_create.argtypes = []
    dll.classic_klatt_create.restype = ctypes.c_void_p
    dll.classic_klatt_destroy.argtypes = [ctypes.c_void_p]
    dll.classic_klatt_cancel.argtypes = [ctypes.c_void_p]
    dll.classic_klatt_reset_cancel.argtypes = [ctypes.c_void_p]
    dll.classic_klatt_speak_utf16.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint16),
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(Callbacks),
    ]
    dll.classic_klatt_speak_utf16.restype = ctypes.c_int


def render(dll_path: Path, text: str, rate: int, pitch: int, voice: int) -> bytes:
    dll = ctypes.CDLL(str(dll_path.resolve()))
    bind(dll)
    engine = dll.classic_klatt_create()
    if not engine:
        raise RuntimeError("could not create the independent synthesis engine")

    chunks: list[bytes] = []
    callback_errors: list[str] = []

    @PCM_CALLBACK
    def on_pcm(_user, samples, count, sample_rate):
        if sample_rate != SAMPLE_RATE:
            callback_errors.append(f"unexpected sample rate {sample_rate}")
            return
        chunks.append(ctypes.string_at(samples, count * 2))

    callbacks = Callbacks(on_pcm, None)
    encoded = text.encode("utf-16-le")
    units = (ctypes.c_uint16 * (len(encoded) // 2)).from_buffer_copy(encoded)
    try:
        ok = dll.classic_klatt_speak_utf16(
            engine,
            units,
            len(units),
            rate,
            pitch,
            voice,
            ctypes.byref(callbacks),
        )
        if callback_errors:
            raise RuntimeError(callback_errors[0])
        if not ok:
            raise RuntimeError("the independent synthesis engine rejected the text")
        return b"".join(chunks)
    finally:
        dll.classic_klatt_destroy(engine)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dll", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("text")
    parser.add_argument("--rate", type=int, default=50)
    parser.add_argument("--pitch", type=int, default=50)
    parser.add_argument("--voice", choices=("male", "female"), default="male")
    args = parser.parse_args()

    pcm = render(
        args.dll,
        args.text,
        args.rate,
        args.pitch,
        1 if args.voice == "female" else 0,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(args.output), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm)
    print(f"wrote {len(pcm) // 2} samples to {args.output}")


if __name__ == "__main__":
    main()
