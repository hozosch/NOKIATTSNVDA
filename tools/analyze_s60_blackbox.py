#!/usr/bin/env python3
"""Measure black-box WAV captures without retaining or publishing their PCM."""
from __future__ import annotations

import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import sys
import wave


FRAME_MS = 10
MIN_INTERNAL_SILENCE_MS = 30


def read_pcm(path: Path) -> tuple[int, list[int], str]:
    with wave.open(str(path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth()) != (1, 2):
            raise ValueError(f"expected mono 16-bit PCM: {path}")
        rate = source.getframerate()
        frames = source.readframes(source.getnframes())
    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder != "little":
        samples.byteswap()
    return rate, list(samples), hashlib.sha256(frames).hexdigest()


def frame_rms(samples: list[int], frame_size: int) -> list[float]:
    values = []
    for start in range(0, len(samples), frame_size):
        frame = samples[start:start + frame_size]
        if frame:
            values.append(math.sqrt(sum(value * value for value in frame) / len(frame)))
    return values


def _runs(bits: list[bool]) -> list[tuple[int, int, bool]]:
    if not bits:
        return []
    runs = []
    start = 0
    current = bits[0]
    for index, value in enumerate(bits[1:], 1):
        if value != current:
            runs.append((start, index, current))
            start = index
            current = value
    runs.append((start, len(bits), current))
    return runs


def wav_metrics(path: Path) -> dict:
    rate, samples, pcm_hash = read_pcm(path)
    if not samples:
        raise ValueError(f"empty WAV: {path}")
    size = max(1, rate * FRAME_MS // 1000)
    energy = frame_rms(samples, size)
    maximum = max(energy, default=0.0)
    threshold = max(24.0, maximum * 0.01)
    active = [value >= threshold for value in energy]
    active_indexes = [index for index, value in enumerate(active) if value]
    internal = []
    if active_indexes:
        first, last = active_indexes[0], active_indexes[-1]
        for start, end, is_active in _runs(active[first:last + 1]):
            duration = (end - start) * FRAME_MS
            if not is_active and duration >= MIN_INTERNAL_SILENCE_MS:
                internal.append(duration)
    sample_rms = math.sqrt(sum(value * value for value in samples) / len(samples))
    peak = max(abs(value) for value in samples)
    zero_crossings = sum(
        1 for previous, current in zip(samples, samples[1:])
        if (previous < 0 <= current) or (previous >= 0 > current)
    )
    return {
        "sampleRate": rate,
        "samples": len(samples),
        "durationMs": round(len(samples) * 1000.0 / rate, 3),
        "peakDbfs": round(20.0 * math.log10(peak / 32768.0), 3) if peak else None,
        "rmsDbfs": round(20.0 * math.log10(sample_rms / 32768.0), 3) if sample_rms else None,
        "activeStartMs": active_indexes[0] * FRAME_MS if active_indexes else None,
        "activeEndMs": (active_indexes[-1] + 1) * FRAME_MS if active_indexes else None,
        "internalSilenceCount": len(internal),
        "internalSilenceMs": sum(internal),
        "longestInternalSilenceMs": max(internal, default=0),
        "zeroCrossingsPerSecond": round(zero_crossings * rate / len(samples), 3),
        "pcmSha256": pcm_hash,
        "energyEnvelope": [round(value, 3) for value in energy],
    }


def resample_envelope(values: list[float], points: int = 128) -> list[float]:
    if not values:
        return [0.0] * points
    maximum = max(values) or 1.0
    normalized = [value / maximum for value in values]
    if len(normalized) == 1:
        return normalized * points
    output = []
    for index in range(points):
        position = index * (len(normalized) - 1) / (points - 1)
        left = int(position)
        right = min(left + 1, len(normalized) - 1)
        fraction = position - left
        output.append(normalized[left] * (1.0 - fraction) + normalized[right] * fraction)
    return output


def compare_metrics(left: dict, right: dict) -> dict:
    left_envelope = resample_envelope(left["energyEnvelope"])
    right_envelope = resample_envelope(right["energyEnvelope"])
    distance = sum(abs(a - b) for a, b in zip(left_envelope, right_envelope)) / len(left_envelope)
    return {
        "pcmIdentical": left["pcmSha256"] == right["pcmSha256"],
        "durationDeltaMs": round(right["durationMs"] - left["durationMs"], 3),
        "internalSilenceDeltaMs": (
            right["internalSilenceMs"] - left["internalSilenceMs"]
        ),
        "energyEnvelopeDistance": round(distance, 6),
    }


def load_manifest(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1:
        raise ValueError(f"unsupported manifest in {directory}")
    return manifest


def analyze_capture(directory: Path) -> tuple[dict, dict[str, dict]]:
    manifest = load_manifest(directory)
    rows = []
    by_id = {}
    for case in manifest["cases"]:
        metrics = wav_metrics(directory / case["file"])
        public_metrics = {
            key: value for key, value in metrics.items()
            if key not in {"pcmSha256", "energyEnvelope"}
        }
        row = {
            key: case[key]
            for key in ("id", "language", "languageId", "group", "text")
        }
        if case.get("compareTo"):
            row["compareTo"] = case["compareTo"]
        row["metrics"] = public_metrics
        rows.append(row)
        by_id[case["id"]] = {"case": case, "metrics": metrics}
    return {
        "backend": manifest["backend"],
        "voice": manifest["voice"],
        "cases": rows,
    }, by_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle-dir", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    oracle_public, oracle = analyze_capture(args.oracle_dir)
    report = {"schema": 1, "oracle": oracle_public, "behaviorComparisons": []}

    for identifier, item in sorted(oracle.items()):
        compare_to = item["case"].get("compareTo")
        if not compare_to:
            continue
        comparison = compare_metrics(oracle[compare_to]["metrics"], item["metrics"])
        comparison.update({
            "id": identifier,
            "compareTo": compare_to,
            "language": item["case"]["language"],
            "group": item["case"]["group"],
        })
        report["behaviorComparisons"].append(comparison)

    if args.candidate_dir:
        candidate_public, candidate = analyze_capture(args.candidate_dir)
        comparisons = []
        for identifier in sorted(set(oracle) & set(candidate)):
            comparison = compare_metrics(
                oracle[identifier]["metrics"], candidate[identifier]["metrics"]
            )
            comparison.update({
                "id": identifier,
                "language": oracle[identifier]["case"]["language"],
                "group": oracle[identifier]["case"]["group"],
            })
            comparisons.append(comparison)
        report["candidate"] = candidate_public
        report["candidateComparisons"] = comparisons

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Black-box punctuation and boundary comparisons:")
    for row in report["behaviorComparisons"]:
        if row["group"] != "punctuation":
            continue
        identical = "identical" if row["pcmIdentical"] else "different"
        print(
            f"{row['id']}: {identical}; duration {row['durationDeltaMs']:+.1f} ms; "
            f"silence {row['internalSilenceDeltaMs']:+d} ms"
        )
    candidate_rows = report.get("candidateComparisons", [])
    if candidate_rows:
        mean_duration = sum(abs(row["durationDeltaMs"]) for row in candidate_rows) / len(candidate_rows)
        mean_envelope = sum(row["energyEnvelopeDistance"] for row in candidate_rows) / len(candidate_rows)
        print(
            f"Candidate versus oracle: {len(candidate_rows)} cases; "
            f"mean absolute duration delta {mean_duration:.1f} ms; "
            f"mean energy-envelope distance {mean_envelope:.4f}"
        )
    print(f"wrote aggregate report {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
