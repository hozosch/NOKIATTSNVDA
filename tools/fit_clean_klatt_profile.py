#!/usr/bin/env python3
"""Fit the independent Klatt core to an authorized output-only WAV.

The fitter compiles the independently authored core with temporary acoustic
constants, renders the supplied text, compares time-local audio features, and
deletes every temporary DLL and PCM buffer. It neither reads nor accepts a ROM,
runtime binary, disassembly, extracted table, or emulator state.

One recording is useful for ranking acoustic candidates, but it is not enough
to establish perceptual equivalence or general pronunciation quality. A result
must still pass the multi-case comparison gate and a listening test.
"""
from __future__ import annotations

import argparse
from array import array
from dataclasses import dataclass
import json
import math
import multiprocessing
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import wave


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from analyze_s60_blackbox import (  # noqa: E402
    compare_local_features,
    local_frame_features,
    read_pcm,
)
from render_clean_klatt_wav import SAMPLE_RATE, render  # noqa: E402


REFERENCE_FEATURES: list[dict] = []
SOURCE_PATH = Path()
PROBE_TEXT = ""
BUILD_ROOT = Path()


@dataclass(frozen=True)
class Parameter:
    name: str
    default: float
    minimum: float
    maximum: float


PARAMETERS = {
    parameter.name: parameter
    for parameter in (
        Parameter("CK_MALE_BASE_F0", 97.5918091, 88.0, 112.0),
        Parameter("CK_MALE_DURATION_SCALE", 1.05664782, 0.88, 1.16),
        Parameter("CK_PHRASE_BOOST", 0.14405538, 0.04, 0.38),
        Parameter("CK_ACCENT_BOOST", 0.047273345, 0.02, 0.18),
        Parameter("CK_WORD_SLOPE", 0.104450812, 0.06, 0.42),
        Parameter("CK_UTTERANCE_SLOPE", 0.153787217, 0.01, 0.22),
        Parameter("CK_PHRASE_PLATEAU", 1.12786119, 1.02, 1.26),
        Parameter("CK_PLATEAU_ACCENT_BOOST", 0.06676323, 0.0, 0.10),
        Parameter("CK_EARLY_PHRASE_SLOPE", 0.079164657, 0.0, 0.12),
        Parameter("CK_FINAL_FALL_START", 0.86521216, 0.62, 0.94),
        Parameter("CK_FINAL_FALL", 0.160639591, 0.08, 0.38),
        Parameter("CK_MALE_F1_SCALE", 1.08188636, 0.78, 1.30),
        Parameter("CK_MALE_F2_SCALE", 1.12919267, 0.68, 1.14),
        Parameter("CK_MALE_F3_SCALE", 1.03844375, 0.74, 1.18),
        Parameter("CK_MALE_F4", 3147.55531, 2900.0, 4400.0),
        Parameter("CK_MALE_F5", 4013.26247, 3700.0, 5600.0),
        Parameter("CK_MALE_HIGHPASS_HZ", 20.0, 20.0, 520.0),
        Parameter("CK_TRANSITION_FRACTION", 0.256351241, 0.08, 0.52),
        Parameter("CK_GLOTTAL_OPEN_END", 0.474641603, 0.20, 0.48),
        Parameter("CK_GLOTTAL_CLOSE_END", 0.587551227, 0.38, 0.82),
        Parameter("CK_SMOOTH_CLOSURE_BLEND", 0.244697096, 0.0, 1.0),
        Parameter("CK_SOURCE_TILT", 0.060060515, 0.0, 0.75),
        Parameter("CK_VOICED_STOP_GAIN", 0.312352975, 0.08, 0.75),
        Parameter("CK_GLOTTAL_SOURCE_GAIN", 2.99786494, 2.0, 5.2),
        Parameter("CK_MALE_VOICED_GAIN", 1.30658458, 1.30, 3.60),
        Parameter("CK_MALE_NOISE_GAIN", 0.517838913, 0.18, 0.90),
        Parameter("CK_VOWEL_R1_GAIN", 0.322358289, 0.03, 0.90),
        Parameter("CK_VOWEL_R2_GAIN", 2.13583081, 0.80, 3.80),
        Parameter("CK_VOWEL_R3_GAIN", 1.35040103, 0.45, 3.00),
        Parameter("CK_VOWEL_R4_GAIN", 0.913315824, 0.03, 1.30),
        Parameter("CK_VOWEL_R5_GAIN", 0.145375468, 0.02, 0.90),
        Parameter("CK_SONORANT_R1_GAIN", 0.402427918, 0.02, 0.45),
        Parameter("CK_SONORANT_R2_GAIN", 2.26586229, 0.70, 3.80),
        Parameter("CK_SONORANT_R3_GAIN", 2.19506716, 0.40, 3.00),
        Parameter("CK_SONORANT_R4_GAIN", 0.6603285, 0.02, 0.80),
        Parameter("CK_SONORANT_R5_GAIN", 0.118445332, 0.01, 0.50),
        Parameter("CK_NOISE_R1_GAIN", 0.318809823, 0.02, 0.55),
        Parameter("CK_NOISE_R2_GAIN", 0.559967656, 0.04, 0.90),
        Parameter("CK_NOISE_R3_GAIN", 0.120259968, 0.04, 0.90),
        Parameter("CK_NOISE_R4_GAIN", 0.412081087, 0.02, 0.60),
        Parameter("CK_NOISE_R5_GAIN", 0.084522225, 0.01, 0.40),
        Parameter("CK_STOP_RELEASE_START", 0.527823021, 0.15, 0.72),
        Parameter("CK_FRICATION_BANDWIDTH_SCALE", 0.324946285, 0.15, 1.0),
        Parameter("CK_IMPULSIVE_NOISE_BLEND", 0.409715241, 0.0, 1.0),
    )
}


STAGES = (
    (
        "timing-and-intonation",
        (
            "CK_MALE_BASE_F0", "CK_MALE_DURATION_SCALE", "CK_PHRASE_BOOST",
            "CK_ACCENT_BOOST", "CK_WORD_SLOPE", "CK_UTTERANCE_SLOPE",
            "CK_PHRASE_PLATEAU", "CK_PLATEAU_ACCENT_BOOST",
            "CK_EARLY_PHRASE_SLOPE", "CK_FINAL_FALL_START",
            "CK_FINAL_FALL",
        ),
    ),
    (
        "resonances-and-transitions",
        (
            "CK_MALE_F1_SCALE", "CK_MALE_F2_SCALE", "CK_MALE_F3_SCALE",
            "CK_MALE_F4", "CK_MALE_F5", "CK_MALE_HIGHPASS_HZ",
            "CK_TRANSITION_FRACTION",
        ),
    ),
    (
        "source-and-vowel-balance",
        (
            "CK_GLOTTAL_OPEN_END", "CK_GLOTTAL_CLOSE_END",
            "CK_SMOOTH_CLOSURE_BLEND", "CK_SOURCE_TILT",
            "CK_VOICED_STOP_GAIN",
            "CK_GLOTTAL_SOURCE_GAIN", "CK_MALE_VOICED_GAIN",
            "CK_VOWEL_R1_GAIN", "CK_VOWEL_R2_GAIN", "CK_VOWEL_R3_GAIN",
            "CK_VOWEL_R4_GAIN", "CK_VOWEL_R5_GAIN",
        ),
    ),
    (
        "consonant-balance",
        (
            "CK_MALE_NOISE_GAIN",
            "CK_SONORANT_R1_GAIN", "CK_SONORANT_R2_GAIN",
            "CK_SONORANT_R3_GAIN", "CK_SONORANT_R4_GAIN",
            "CK_SONORANT_R5_GAIN", "CK_NOISE_R1_GAIN",
            "CK_NOISE_R2_GAIN", "CK_NOISE_R3_GAIN", "CK_NOISE_R4_GAIN",
            "CK_NOISE_R5_GAIN", "CK_STOP_RELEASE_START",
            "CK_FRICATION_BANDWIDTH_SCALE", "CK_IMPULSIVE_NOISE_BLEND",
        ),
    ),
)


def default_values() -> dict[str, float]:
    return {name: parameter.default for name, parameter in PARAMETERS.items()}


def load_initial_values(path: Path | None) -> dict[str, float]:
    if path is None:
        return default_values()
    document = json.loads(path.read_text(encoding="utf-8"))
    supplied = document.get("defines", document)
    missing = sorted(set(PARAMETERS) - set(supplied))
    unknown = sorted(set(supplied) - set(PARAMETERS))
    if unknown:
        raise ValueError(
            f"initial values do not match fitter parameters; missing={missing}, unknown={unknown}"
        )
    values = default_values()
    values.update({name: float(value) for name, value in supplied.items()})
    return normalize(values)


def normalize(values: dict[str, float]) -> dict[str, float]:
    result = {
        name: min(parameter.maximum, max(parameter.minimum, values[name]))
        for name, parameter in PARAMETERS.items()
    }
    # The glottal return must have a positive, numerically safe duration.
    result["CK_GLOTTAL_CLOSE_END"] = max(
        result["CK_GLOTTAL_CLOSE_END"],
        result["CK_GLOTTAL_OPEN_END"] + 0.08,
    )
    result["CK_GLOTTAL_CLOSE_END"] = min(
        PARAMETERS["CK_GLOTTAL_CLOSE_END"].maximum,
        result["CK_GLOTTAL_CLOSE_END"],
    )
    return result


def compile_defines(values: dict[str, float]) -> list[str]:
    return ["-DCK_USE_PLATEAU_INTONATION=1", *[
        f"-D{name}={values[name]:.9g}" for name in sorted(PARAMETERS)
    ]]


def pcm_samples(pcm: bytes) -> list[int]:
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    return list(samples)


def initialize_worker(
    reference_features: list[dict], source: str, text: str, build_root: str
) -> None:
    global REFERENCE_FEATURES, SOURCE_PATH, PROBE_TEXT, BUILD_ROOT
    REFERENCE_FEATURES = reference_features
    SOURCE_PATH = Path(source)
    PROBE_TEXT = text
    BUILD_ROOT = Path(build_root)


def evaluate(task: tuple[int, dict[str, float]]) -> dict:
    trial, raw_values = task
    values = normalize(raw_values)
    dll = BUILD_ROOT / f"candidate-{trial}.so"
    command = [
        "gcc", "-std=c11", "-O2", "-fPIC", "-shared",
        *compile_defines(values), str(SOURCE_PATH), "-lm", "-o", str(dll),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode:
            return {
                "trial": trial,
                "score": math.inf,
                "error": completed.stderr.strip() or "compiler failed",
                "values": values,
            }
        pcm = render(dll, PROBE_TEXT, 50, 50, 0)
        features = local_frame_features(pcm_samples(pcm), SAMPLE_RATE)
        comparison = compare_local_features(REFERENCE_FEATURES, features)
        score = comparison.get("localFeatureScore")
        return {
            "trial": trial,
            "score": float(score) if score is not None else math.inf,
            "sampleCount": len(pcm) // 2,
            "comparison": comparison,
            "values": values,
        }
    except Exception as error:  # pragma: no cover - diagnostic boundary
        return {
            "trial": trial,
            "score": math.inf,
            "error": str(error),
            "values": values,
        }
    finally:
        dll.unlink(missing_ok=True)


def random_candidates(
    centre: dict[str, float], names: tuple[str, ...], count: int,
    rng: random.Random, contraction: float,
) -> list[dict[str, float]]:
    candidates = []
    for _ in range(count):
        candidate = dict(centre)
        for name in names:
            parameter = PARAMETERS[name]
            radius = (parameter.maximum - parameter.minimum) * 0.5 * contraction
            low = max(parameter.minimum, centre[name] - radius)
            high = min(parameter.maximum, centre[name] + radius)
            candidate[name] = rng.uniform(low, high)
        candidates.append(normalize(candidate))
    return candidates


def coordinate_candidates(
    centre: dict[str, float], names: tuple[str, ...], fraction: float
) -> list[dict[str, float]]:
    candidates = []
    for name in names:
        parameter = PARAMETERS[name]
        step = (parameter.maximum - parameter.minimum) * fraction
        for direction in (-1.0, 1.0):
            candidate = dict(centre)
            candidate[name] += direction * step
            candidates.append(normalize(candidate))
    return candidates


def write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(pcm)


def compile_and_render(source: Path, text: str, values: dict[str, float]) -> bytes:
    with tempfile.TemporaryDirectory(prefix="clean-klatt-final-") as directory:
        dll = Path(directory) / "candidate.so"
        subprocess.run(
            [
                "gcc", "-std=c11", "-O2", "-fPIC", "-shared",
                *compile_defines(values), str(source), "-lm", "-o", str(dll),
            ],
            check=True,
        )
        return render(dll, text, 50, 50, 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("text")
    parser.add_argument(
        "--source", type=Path, default=ROOT / "native" / "clean" / "classic_klatt.c"
    )
    parser.add_argument("--trials-per-stage", type=int, default=24)
    parser.add_argument("--workers", type=int, default=min(4, multiprocessing.cpu_count()))
    parser.add_argument("--seed", type=int, default=5320)
    parser.add_argument("--baseline-score", type=float)
    parser.add_argument(
        "--coordinate-only", action="store_true",
        help="replace broad random passes with one-parameter coordinate refinement",
    )
    parser.add_argument(
        "--initial-values", type=Path,
        help="JSON fitter report (or defines object) used as the search centre",
    )
    parser.add_argument(
        "--only-stage", action="append", choices=[name for name, _values in STAGES],
        help="run only the named stage; may be supplied more than once",
    )
    parser.add_argument("--write-best-wav", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--confirm-authorized-reference",
        action="store_true",
        help="confirm that the recording may be used for this output-only analysis",
    )
    args = parser.parse_args()
    if not args.confirm_authorized_reference:
        parser.error("--confirm-authorized-reference is required")
    if args.trials_per_stage < 2:
        parser.error("--trials-per-stage must be at least 2")
    if args.workers < 1:
        parser.error("--workers must be at least 1")

    rate, samples, reference_sha256 = read_pcm(args.reference)
    if rate != SAMPLE_RATE:
        parser.error(f"reference must use {SAMPLE_RATE} Hz PCM")
    reference_features = local_frame_features(samples, rate)
    if not reference_features:
        parser.error("reference has no active audio")

    rng = random.Random(args.seed)
    trial = 0
    history = []
    initial_values = load_initial_values(args.initial_values)
    selected_stages = [
        stage for stage in STAGES
        if not args.only_stage or stage[0] in args.only_stage
    ]
    with tempfile.TemporaryDirectory(prefix="clean-klatt-fit-") as directory:
        with multiprocessing.Pool(
            processes=args.workers,
            initializer=initialize_worker,
            initargs=(reference_features, str(args.source), args.text, directory),
        ) as pool:
            baseline = pool.map(evaluate, [(trial, initial_values)])[0]
            trial += 1
            if not math.isfinite(baseline["score"]):
                raise RuntimeError(baseline.get("error", "baseline evaluation failed"))
            best = baseline
            history.append({"stage": "baseline", "bestScore": best["score"]})
            print(f"baseline: {best['score']:.3f}", flush=True)

            for stage_index, (stage_name, names) in enumerate(selected_stages):
                # The first random pass explores broadly and the second
                # refines its selected centre. Coordinate-only mode is useful
                # after that broad search and changes exactly one constant per
                # trial, making small coupled regressions less likely.
                pass_settings = (0.10, 0.035) if args.coordinate_only else (1.0, 0.34)
                for pass_index, contraction in enumerate(pass_settings):
                    if args.coordinate_only:
                        candidates = coordinate_candidates(best["values"], names, contraction)
                    else:
                        candidates = random_candidates(
                            best["values"], names, args.trials_per_stage,
                            rng, contraction,
                        )
                    tasks = [(trial + index, values) for index, values in enumerate(candidates)]
                    trial += len(tasks)
                    results = pool.map(evaluate, tasks)
                    viable = [item for item in results if math.isfinite(item["score"])]
                    if not viable:
                        raise RuntimeError(f"every {stage_name} candidate failed")
                    candidate = min(viable, key=lambda item: item["score"])
                    if candidate["score"] < best["score"]:
                        best = candidate
                    history.append({
                        "stage": stage_name,
                        "pass": pass_index + 1,
                        "bestScore": best["score"],
                    })
                    print(
                        f"{stage_index + 1}.{pass_index + 1} {stage_name}: "
                        f"{best['score']:.3f}",
                        flush=True,
                    )

    gate_baseline = args.baseline_score if args.baseline_score is not None else baseline["score"]
    improvement = 100.0 * (gate_baseline - best["score"]) / gate_baseline
    threshold = gate_baseline * 0.85
    report = {
        "method": "authorized-output-only-time-local-feature-search",
        "referencePcmSha256": reference_sha256,
        "seed": args.seed,
        "evaluations": trial,
        "baselineScore": round(gate_baseline, 3),
        "bestScore": round(best["score"], 3),
        "improvementPercent": round(improvement, 3),
        "listeningGateThreshold": round(threshold, 3),
        "eligibleForListening": best["score"] <= threshold,
        "comparison": best.get("comparison"),
        "defines": {
            name: round(value, 9) for name, value in sorted(best["values"].items())
        },
        "history": history,
        "limitations": [
            "A single utterance cannot validate general pronunciation behavior.",
            "The score ranks candidates and does not establish perceptual equivalence.",
            "Multi-case measurement and listening remain required before release.",
        ],
    }
    rendered_pcm = None
    if args.write_best_wav:
        rendered_pcm = compile_and_render(args.source, args.text, best["values"])
        write_wav(args.write_best_wav, rendered_pcm)
        report["bestWav"] = str(args.write_best_wav)
    output = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if report["eligibleForListening"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
