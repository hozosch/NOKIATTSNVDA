#!/usr/bin/env python3
"""Capture controlled WAVs through a renderer's public text/audio boundary.

The ``nk-render`` backend starts the external historical reference renderer as
a separate process.  This module never imports its code or reads its runtime
memory.  The ``clean-core`` backend renders the independent candidate through
its public DLL API so that both sides use the same self-authored corpus.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import wave

from render_clean_klatt_wav import SAMPLE_RATE, render as render_clean


VALID_VOICES = {"male": "DefaultMale", "female": "DefaultFemale"}


def load_corpus(path: Path) -> list[dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != 1 or not isinstance(document.get("cases"), list):
        raise ValueError("corpus must use schema 1 and contain a cases list")
    cases = document["cases"]
    identifiers: set[str] = set()
    for case in cases:
        required = {"id", "language", "languageId", "group", "text"}
        if not required.issubset(case):
            raise ValueError(f"corpus case lacks fields: {case!r}")
        identifier = case["id"]
        if not isinstance(identifier, str) or not identifier.replace("_", "").isalnum():
            raise ValueError(f"unsafe case id: {identifier!r}")
        if identifier in identifiers:
            raise ValueError(f"duplicate case id: {identifier}")
        identifiers.add(identifier)
        if not isinstance(case["text"], str) or not case["text"]:
            raise ValueError(f"empty case text: {identifier}")
        if not isinstance(case["languageId"], int):
            raise ValueError(f"invalid language id: {identifier}")
        phone_target = case.get("phoneTarget")
        if phone_target is not None and (
            not isinstance(phone_target, str)
            or not phone_target
            or not phone_target.replace("_", "").isalnum()
        ):
            raise ValueError(f"invalid phone target: {identifier}")
    for case in cases:
        comparison = case.get("compareTo")
        if comparison and comparison not in identifiers:
            raise ValueError(f"unknown comparison {comparison!r} in {case['id']}")
    return cases


def nk_render_command(
    renderer: Path,
    rom: Path,
    data_tree: Path,
    case: dict,
    voice: str,
    output: Path,
) -> list[str]:
    return [
        str(renderer),
        str(rom),
        str(data_tree),
        str(case["languageId"]),
        VALID_VOICES[voice],
        str(output),
        case["text"],
    ]


def wav_details(path: Path) -> dict:
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        width = source.getsampwidth()
        rate = source.getframerate()
        frames = source.getnframes()
    if (channels, width, rate) != (1, 2, SAMPLE_RATE):
        raise RuntimeError(
            f"unexpected WAV format for {path}: {channels}ch/{width * 8}bit/{rate}Hz"
        )
    data = path.read_bytes()
    return {
        "file": path.name,
        "bytes": len(data),
        "samples": frames,
        "durationMs": round(frames * 1000.0 / rate, 3),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def capture_case(
    backend: str,
    renderer: Path,
    rom: Path | None,
    data_tree: Path | None,
    case: dict,
    voice: str,
    output_dir: Path,
    force: bool,
) -> dict:
    output = output_dir / f"{case['id']}.wav"
    if output.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {output}; pass --force")
    if backend == "nk-render":
        assert rom is not None and data_tree is not None
        command = nk_render_command(renderer, rom, data_tree, case, voice, output)
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode:
            raise RuntimeError(
                f"reference renderer failed for {case['id']} ({completed.returncode}): "
                f"{completed.stdout[-800:]}"
            )
    else:
        if case["language"] != "de-DE":
            raise RuntimeError("the current clean core supports only de-DE")
        pcm = render_clean(renderer, case["text"], 50, 50, 1 if voice == "female" else 0)
        with wave.open(str(output), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(SAMPLE_RATE)
            target.writeframes(pcm)
    row = {
        key: case[key]
        for key in ("id", "language", "languageId", "group", "text")
    }
    if case.get("compareTo"):
        row["compareTo"] = case["compareTo"]
    if case.get("phoneTarget"):
        row["phoneTarget"] = case["phoneTarget"]
    row.update(wav_details(output))
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("nk-render", "clean-core"), required=True)
    parser.add_argument("--renderer", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, default=Path("tools/s60_blackbox_corpus.json"))
    parser.add_argument("--rom", type=Path)
    parser.add_argument("--data-tree", type=Path)
    parser.add_argument("--language", action="append", dest="languages")
    parser.add_argument("--voice", choices=tuple(VALID_VOICES), default="male")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.renderer.is_file():
        parser.error(f"renderer does not exist: {args.renderer}")
    if args.backend == "nk-render":
        if not args.rom or not args.rom.is_file():
            parser.error("--rom must identify the external renderer's ROM image")
        if not args.data_tree or not args.data_tree.is_dir():
            parser.error("--data-tree must identify the external renderer's data tree")
    if args.jobs < 1:
        parser.error("--jobs must be positive")

    cases = load_corpus(args.corpus)
    if args.languages:
        selected = set(args.languages)
        cases = [case for case in cases if case["language"] in selected]
    if not cases:
        parser.error("no corpus cases selected")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {
            pool.submit(
                capture_case,
                args.backend,
                args.renderer.resolve(),
                args.rom.resolve() if args.rom else None,
                args.data_tree.resolve() if args.data_tree else None,
                case,
                args.voice,
                args.output_dir.resolve(),
                args.force,
            ): case
            for case in cases
        }
        for future in as_completed(futures):
            case = futures[future]
            row = future.result()
            rows.append(row)
            print(f"captured {case['id']}: {row['durationMs']:.1f} ms")

    rows.sort(key=lambda row: row["id"])
    manifest = {
        "schema": 1,
        "backend": args.backend,
        "voice": args.voice,
        "sampleRate": SAMPLE_RATE,
        "cases": rows,
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {manifest_path} ({len(rows)} cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
