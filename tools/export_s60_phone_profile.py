#!/usr/bin/env python3
"""Export compact phone targets from an output-only S60 analysis report.

The resulting JSON contains only aggregate acoustic measurements from the
self-authored probe corpus.  It contains no PCM, firmware data, reference
runtime state, phone stream or translated instructions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


VECTOR_KEYS = ("sourceMix", "meanSpectrumDb", "meanCepstralShape")
SCALAR_KEYS = (
    "focusDurationMs",
    "medianF0Hz",
    "meanPeriodicity",
    "meanCrestFactor",
    "meanDerivativeRatio",
)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate(signatures: list[dict]) -> dict:
    result: dict[str, object] = {"contexts": len(signatures)}
    for key in SCALAR_KEYS:
        values = [float(signature[key]) for signature in signatures if signature.get(key) is not None]
        value = _mean(values)
        result[key] = round(value, 5) if value is not None else None
    for key in VECTOR_KEYS:
        vectors = [signature[key] for signature in signatures if signature.get(key)]
        if not vectors:
            result[key] = []
            continue
        width = len(vectors[0])
        if any(len(vector) != width for vector in vectors):
            raise ValueError(f"inconsistent {key} widths")
        result[key] = [
            round(sum(float(vector[index]) for vector in vectors) / len(vectors), 5)
            for index in range(width)
        ]
    return result


def build_profile(report: dict, language: str) -> dict:
    if report.get("schema") != 1 or report.get("metricVersion") != 2:
        raise ValueError("report must use schema 1 and acoustic metric version 2")
    oracle = report.get("oracle")
    if not isinstance(oracle, dict):
        raise ValueError("report has no oracle capture")
    grouped: dict[str, list[dict]] = {}
    contexts: dict[str, list[dict]] = {}
    for case in oracle.get("cases", []):
        if case.get("language") != language or not case.get("phoneTarget"):
            continue
        signature = case.get("phoneSignature")
        if not isinstance(signature, dict):
            continue
        phone = case["phoneTarget"]
        grouped.setdefault(phone, []).append(signature)
        contexts.setdefault(phone, []).append({
            "id": case["id"],
            "group": case["group"],
            "text": case["text"],
            "signature": signature,
        })
    if not grouped:
        raise ValueError(f"report has no phone targets for {language}")
    return {
        "schema": 1,
        "kind": "independent-output-derived-phone-profile",
        "language": language,
        "voice": oracle.get("voice"),
        "referenceBackend": oracle.get("backend"),
        "analysisMetricVersion": report["metricVersion"],
        "phoneCount": len(grouped),
        "probeCount": sum(len(items) for items in grouped.values()),
        "phones": {
            phone: {
                "aggregate": aggregate(grouped[phone]),
                "probes": contexts[phone],
            }
            for phone in sorted(grouped)
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--language", default="de-DE")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    profile = build_profile(report, args.language)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.output} ({profile['phoneCount']} phones, "
        f"{profile['probeCount']} probes)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
