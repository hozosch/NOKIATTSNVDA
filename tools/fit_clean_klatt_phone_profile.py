#!/usr/bin/env python3
"""Fit the independent core to an aggregate output-derived phone profile.

The input contains compact measurements for controlled phone probes, not PCM
or reference-runtime state.  Every trial compiles only the independently
authored core, renders the self-authored probe text, and ranks its acoustic
signature against the stored targets.
"""
from __future__ import annotations

from array import array
import argparse
import json
import math
import multiprocessing
from pathlib import Path
import random
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from analyze_s60_blackbox import (  # noqa: E402
    local_frame_features,
    phone_signature,
)
from fit_clean_klatt_profile import (  # noqa: E402
    PARAMETERS,
    STAGES,
    compile_defines,
    coordinate_candidates,
    load_initial_values,
    normalize,
    random_candidates,
)
from render_clean_klatt_wav import SAMPLE_RATE, render  # noqa: E402


PROBES: list[dict] = []
SOURCE_PATH = Path()
BUILD_ROOT = Path()


def pcm_samples(pcm: bytes) -> list[int]:
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    return list(samples)


def load_profile(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if (
        document.get("schema") != 1
        or document.get("kind") != "independent-output-derived-phone-profile"
        or document.get("analysisMetricVersion") != 2
    ):
        raise ValueError("expected a metric-version-2 output-derived phone profile")
    probes = [
        probe
        for phone in document.get("phones", {}).values()
        for probe in phone.get("probes", [])
    ]
    if not probes or any(
        not {"id", "group", "text", "signature"}.issubset(probe)
        for probe in probes
    ):
        raise ValueError("phone profile has no complete probes")
    document["_probes"] = sorted(probes, key=lambda probe: probe["id"])
    return document


def _vector_mae(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return math.inf
    return sum(abs(a - b) for a, b in zip(left, right)) / len(left)


def _vector_rmse(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return math.inf
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)) / len(left))


def compare_signatures(reference: dict, candidate: dict | None) -> dict:
    if candidate is None:
        return {"score": math.inf}
    source_distance = 0.5 * sum(
        abs(a - b)
        for a, b in zip(reference["sourceMix"], candidate["sourceMix"])
    )
    spectrum_distance = _vector_mae(
        reference["meanSpectrumDb"], candidate["meanSpectrumDb"]
    )
    cepstral_distance = _vector_rmse(
        reference["meanCepstralShape"], candidate["meanCepstralShape"]
    )
    reference_f0 = reference.get("medianF0Hz")
    candidate_f0 = candidate.get("medianF0Hz")
    if reference_f0 and candidate_f0:
        f0_cents = abs(1200.0 * math.log2(candidate_f0 / reference_f0))
    elif reference_f0 is None and candidate_f0 is None:
        f0_cents = 0.0
    else:
        f0_cents = 600.0
    duration_delta = abs(
        candidate["focusDurationMs"] - reference["focusDurationMs"]
    )
    periodicity_delta = abs(
        candidate["meanPeriodicity"] - reference["meanPeriodicity"]
    )
    crest_delta = abs(
        candidate["meanCrestFactor"] - reference["meanCrestFactor"]
    )
    derivative_delta = abs(
        candidate["meanDerivativeRatio"] - reference["meanDerivativeRatio"]
    )
    score = 100.0 * (
        0.26 * min(2.0, spectrum_distance / 12.0)
        + 0.22 * min(2.0, cepstral_distance / 14.0)
        + 0.15 * min(2.0, source_distance / 0.5)
        + 0.10 * min(2.0, f0_cents / 400.0)
        + 0.09 * min(2.0, periodicity_delta / 0.5)
        + 0.07 * min(2.0, duration_delta / 160.0)
        + 0.07 * min(2.0, crest_delta / 2.5)
        + 0.04 * min(2.0, derivative_delta)
    )
    return {
        "score": score,
        "spectrumDistanceDb": spectrum_distance,
        "cepstralShapeDistance": cepstral_distance,
        "sourceMixDistance": source_distance,
        "f0DistanceCents": f0_cents,
        "periodicityDistance": periodicity_delta,
        "durationDistanceMs": duration_delta,
        "crestFactorDistance": crest_delta,
        "derivativeRatioDistance": derivative_delta,
    }


def initialize_worker(probes: list[dict], source: str, build_root: str) -> None:
    global PROBES, SOURCE_PATH, BUILD_ROOT
    PROBES = probes
    SOURCE_PATH = Path(source)
    BUILD_ROOT = Path(build_root)


def evaluate(task: tuple[int, dict[str, float]]) -> dict:
    trial, raw_values = task
    values = normalize(raw_values)
    library = BUILD_ROOT / f"phone-candidate-{trial}.so"
    try:
        completed = subprocess.run(
            [
                "gcc", "-std=c11", "-O2", "-fPIC", "-shared",
                *compile_defines(values), str(SOURCE_PATH), "-lm",
                "-o", str(library),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode:
            return {
                "trial": trial,
                "score": math.inf,
                "error": completed.stderr.strip() or "compiler failed",
                "values": values,
            }

        comparisons = []
        for probe in PROBES:
            pcm = render(library, probe["text"], 50, 50, 0)
            frames = local_frame_features(pcm_samples(pcm), SAMPLE_RATE)
            signature = phone_signature(frames, probe["group"])
            comparison = compare_signatures(probe["signature"], signature)
            comparisons.append({
                "id": probe["id"],
                "group": probe["group"],
                **comparison,
            })
        score = sum(item["score"] for item in comparisons) / len(comparisons)
        return {
            "trial": trial,
            "score": score,
            "values": values,
            "comparisons": comparisons,
        }
    except Exception as error:  # pragma: no cover - diagnostic boundary
        return {
            "trial": trial,
            "score": math.inf,
            "error": str(error),
            "values": values,
        }
    finally:
        library.unlink(missing_ok=True)


def group_summary(comparisons: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for comparison in comparisons:
        groups.setdefault(comparison["group"], []).append(comparison)
    return [
        {
            "group": group,
            "cases": len(rows),
            "score": round(sum(row["score"] for row in rows) / len(rows), 3),
        }
        for group, rows in sorted(groups.items())
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument(
        "--source", type=Path,
        default=ROOT / "native" / "clean" / "classic_klatt.c",
    )
    parser.add_argument("--trials-per-stage", type=int, default=24)
    parser.add_argument(
        "--workers", type=int, default=min(4, multiprocessing.cpu_count())
    )
    parser.add_argument("--seed", type=int, default=5320)
    parser.add_argument("--initial-values", type=Path)
    parser.add_argument(
        "--coordinate-only", action="store_true",
        help="search one parameter at a time around the supplied centre",
    )
    parser.add_argument(
        "--only-stage", action="append", choices=[name for name, _ in STAGES]
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.trials_per_stage < 2:
        parser.error("--trials-per-stage must be at least 2")
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    if not args.source.is_file():
        parser.error(f"source does not exist: {args.source}")

    profile = load_profile(args.profile)
    probes = profile["_probes"]
    initial_values = load_initial_values(args.initial_values)
    selected_stages = [
        stage for stage in STAGES
        if not args.only_stage or stage[0] in args.only_stage
    ]
    rng = random.Random(args.seed)
    history = []
    trial = 0

    with tempfile.TemporaryDirectory(prefix="clean-klatt-phone-fit-") as directory:
        with multiprocessing.Pool(
            processes=args.workers,
            initializer=initialize_worker,
            initargs=(probes, str(args.source.resolve()), directory),
        ) as pool:
            baseline = pool.map(evaluate, [(trial, initial_values)])[0]
            trial += 1
            if not math.isfinite(baseline["score"]):
                raise RuntimeError(baseline.get("error", "baseline evaluation failed"))
            best = baseline
            history.append({"stage": "baseline", "bestScore": best["score"]})
            print(f"baseline: {best['score']:.3f}", flush=True)

            for stage_name, names in selected_stages:
                pass_settings = (0.10, 0.035) if args.coordinate_only else (1.0, 0.34)
                for pass_index, contraction in enumerate(pass_settings, 1):
                    candidates = (
                        coordinate_candidates(best["values"], names, contraction)
                        if args.coordinate_only
                        else random_candidates(
                            best["values"], names, args.trials_per_stage,
                            rng, contraction,
                        )
                    )
                    tasks = [
                        (trial + index, values)
                        for index, values in enumerate(candidates)
                    ]
                    trial += len(tasks)
                    results = pool.map(evaluate, tasks)
                    viable = [
                        result for result in results
                        if math.isfinite(result["score"])
                    ]
                    if not viable:
                        raise RuntimeError(f"every {stage_name} candidate failed")
                    candidate = min(viable, key=lambda result: result["score"])
                    if candidate["score"] < best["score"]:
                        best = candidate
                    history.append({
                        "stage": stage_name,
                        "pass": pass_index,
                        "bestScore": best["score"],
                    })
                    print(
                        f"{stage_name} pass {pass_index}: {best['score']:.3f}",
                        flush=True,
                    )

    result = {
        "schema": 1,
        "kind": "clean-klatt-phone-profile-fit",
        "language": profile.get("language"),
        "voice": profile.get("voice"),
        "profileMetricVersion": profile.get("analysisMetricVersion"),
        "probeCount": len(probes),
        "seed": args.seed,
        "trials": trial,
        "baselineScore": round(baseline["score"], 6),
        "bestScore": round(best["score"], 6),
        "improvementPercent": round(
            100.0 * (baseline["score"] - best["score"]) / baseline["score"], 3
        ),
        "defines": {
            name: round(value, 9) for name, value in sorted(best["values"].items())
        },
        "groupSummary": group_summary(best["comparisons"]),
        "history": [
            {**row, "bestScore": round(row["bestScore"], 6)} for row in history
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"best: {best['score']:.3f} "
        f"({result['improvementPercent']:.1f}% lower); wrote {args.output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
