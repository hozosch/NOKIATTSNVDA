#!/usr/bin/env python3
"""Expose an installed historical renderer through the nk_render CLI shape.

This helper deliberately contains no emulator, firmware, speech package or
runtime implementation.  It loads a separately installed reference package
from ``S60_REFERENCE_DRIVER_DIR`` and exposes only text input and WAV output to
the black-box capture process.  The operator remains responsible for being
entitled to use that reference installation.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import wave


SAMPLE_RATE = 16000
REFERENCE_DRIVER_ENV = "S60_REFERENCE_DRIVER_DIR"


def load_engine_type():
    driver_dir = os.environ.get(REFERENCE_DRIVER_ENV)
    if not driver_dir:
        raise RuntimeError(
            f"set {REFERENCE_DRIVER_ENV} to the directory containing the "
            "installed _nokia reference package"
        )
    path = Path(driver_dir).expanduser().resolve()
    if not (path / "_nokia" / "engine.py").is_file():
        raise RuntimeError(f"no installed _nokia reference package below {path}")
    sys.path.insert(0, str(path))
    from _nokia.engine import Engine  # type: ignore[import-not-found]

    return Engine


def write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(pcm)


def main() -> int:
    if len(sys.argv) not in (7, 8):
        print(
            "usage: render_authorized_s60_reference.py "
            "<rom> <tree> <lang> <voice|-> <out.wav> <text> [bank]",
            file=sys.stderr,
        )
        return 2

    rom, tree, language_text, voice_text, output, text = sys.argv[1:7]
    try:
        language = int(language_text)
    except ValueError:
        print(f"invalid language id: {language_text}", file=sys.stderr)
        return 2

    engine_type = load_engine_type()
    engine = engine_type(
        str(Path(rom).resolve()),
        str(Path(tree).resolve()),
        language,
        voice="" if voice_text == "-" else voice_text,
    )
    pcm = bytearray()
    try:
        produced = engine.speak(text, pcm.extend)
    finally:
        engine.close()
    if not produced or not pcm:
        print("reference produced no audio", file=sys.stderr)
        return 1
    write_wav(Path(output), bytes(pcm))
    print(f"{len(pcm)} bytes at {SAMPLE_RATE} Hz")
    return 0


if __name__ == "__main__":
    sys.exit(main())
