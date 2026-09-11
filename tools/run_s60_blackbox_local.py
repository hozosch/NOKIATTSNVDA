#!/usr/bin/env python3
"""Run an output-only S60 comparison and erase all transient PCM afterwards."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "tools" / "capture_s60_blackbox.py"
ANALYZE = ROOT / "tools" / "analyze_s60_blackbox.py"
EXPORT_PHONE_PROFILE = ROOT / "tools" / "export_s60_phone_profile.py"
DEFAULT_CORPUS = ROOT / "tools" / "s60_blackbox_corpus.json"


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare a separately operated reference with the independent core. "
            "Reference and candidate WAVs live only in a temporary directory."
        )
    )
    parser.add_argument("--reference-renderer", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--data-tree", type=Path, required=True)
    parser.add_argument("--candidate-dll", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--language", action="append")
    parser.add_argument("--voice", choices=("male", "female"), default="male")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--phone-profile-output",
        type=Path,
        help="also retain compact per-phone acoustic targets from the aggregate report",
    )
    parser.add_argument("--phone-profile-language", default="de-DE")
    parser.add_argument("--baseline-report", type=Path)
    parser.add_argument("--minimum-improvement-percent", type=float, default=15.0)
    parser.add_argument("--enforce-gate", action="store_true")
    parser.add_argument(
        "--confirm-authorized-reference",
        action="store_true",
        help="confirm that you are entitled to run the supplied reference installation",
    )
    args = parser.parse_args()

    if not args.confirm_authorized_reference:
        parser.error(
            "the reference may only be run by a person entitled to use that installation; "
            "pass --confirm-authorized-reference after verifying this"
        )
    for label, path, kind in (
        ("reference renderer", args.reference_renderer, "file"),
        ("ROM", args.rom, "file"),
        ("reference data tree", args.data_tree, "directory"),
        ("candidate DLL", args.candidate_dll, "file"),
        ("corpus", args.corpus, "file"),
    ):
        valid = path.is_file() if kind == "file" else path.is_dir()
        if not valid:
            parser.error(f"{label} does not identify a {kind}: {path}")
    if args.jobs < 1:
        parser.error("--jobs must be positive")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    languages = []
    for language in dict.fromkeys(args.language or ["de-DE"]):
        languages.extend(("--language", language))

    with tempfile.TemporaryDirectory(prefix="s60-output-only-") as temporary:
        temporary_root = Path(temporary)
        oracle = temporary_root / "reference"
        candidate = temporary_root / "candidate"
        run([
            sys.executable, str(CAPTURE),
            "--backend", "nk-render",
            "--renderer", str(args.reference_renderer.resolve()),
            "--rom", str(args.rom.resolve()),
            "--data-tree", str(args.data_tree.resolve()),
            "--corpus", str(args.corpus.resolve()),
            "--voice", args.voice,
            "--output-dir", str(oracle),
            "--jobs", str(args.jobs),
            *languages,
        ])
        run([
            sys.executable, str(CAPTURE),
            "--backend", "clean-core",
            "--renderer", str(args.candidate_dll.resolve()),
            "--corpus", str(args.corpus.resolve()),
            "--voice", args.voice,
            "--output-dir", str(candidate),
            *languages,
        ])
        command = [
            sys.executable, str(ANALYZE),
            "--oracle-dir", str(oracle),
            "--candidate-dir", str(candidate),
            "--output", str(args.output.resolve()),
            "--minimum-improvement-percent", str(args.minimum_improvement_percent),
        ]
        if args.baseline_report:
            command.extend(("--baseline-report", str(args.baseline_report.resolve())))
        if args.enforce_gate:
            command.append("--enforce-gate")
        run(command)

        if args.phone_profile_output:
            run([
                sys.executable,
                str(EXPORT_PHONE_PROFILE),
                str(args.output.resolve()),
                "--language",
                args.phone_profile_language,
                "--output",
                str(args.phone_profile_output.resolve()),
            ])

    print("transient reference and candidate PCM erased")
    print(f"retained aggregate report only: {args.output.resolve()}")
    if args.phone_profile_output:
        print(f"retained aggregate phone profile: {args.phone_profile_output.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
