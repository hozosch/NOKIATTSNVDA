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
ACOUSTIC_FRAME_MS = 40
ACOUSTIC_HOP_MS = 20
MIN_F0_HZ = 65
MAX_F0_HZ = 320
SPECTRUM_STEP_HZ = 25
SPECTRUM_MAX_HZ = 5000


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


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    left = int(position)
    right = min(left + 1, len(ordered) - 1)
    blend = position - left
    return ordered[left] * (1.0 - blend) + ordered[right] * blend


def _pitch_for_frame(frame: list[int], rate: int) -> tuple[float | None, float]:
    decimation = 4
    reduced = [
        sum(frame[index:index + decimation]) / decimation
        for index in range(0, len(frame) - decimation + 1, decimation)
    ]
    mean = sum(reduced) / len(reduced)
    reduced = [value - mean for value in reduced]
    reduced_rate = rate / decimation
    minimum_lag = max(1, int(reduced_rate / MAX_F0_HZ))
    maximum_lag = min(len(reduced) // 2, int(reduced_rate / MIN_F0_HZ))
    best_lag = 0
    best_score = -1.0
    for lag in range(minimum_lag, maximum_lag + 1):
        left = reduced[:-lag]
        right = reduced[lag:]
        numerator = sum(a * b for a, b in zip(left, right))
        left_energy = sum(value * value for value in left)
        right_energy = sum(value * value for value in right)
        denominator = math.sqrt(left_energy * right_energy)
        score = numerator / denominator if denominator else 0.0
        if score > best_score:
            best_score = score
            best_lag = lag
    if best_lag == 0 or best_score < 0.35:
        return None, round(best_score, 4)
    return reduced_rate / best_lag, round(best_score, 4)


def _goertzel_power(frame: list[float], rate: int, frequency: int) -> float:
    coefficient = 2.0 * math.cos(2.0 * math.pi * frequency / rate)
    previous = 0.0
    previous2 = 0.0
    for sample in frame:
        current = sample + coefficient * previous - previous2
        previous2 = previous
        previous = current
    return max(0.0, previous2 * previous2 + previous * previous - coefficient * previous * previous2)


def _binned_pitch(points: list[tuple[int, float, float]], total_samples: int) -> list[float | None]:
    bins = 24
    values: list[list[float]] = [[] for _ in range(bins)]
    for start, frequency, _periodicity in points:
        index = min(bins - 1, int(start * bins / max(1, total_samples)))
        values[index].append(frequency)
    return [
        round(percentile(group, 0.5), 3) if group else None
        for group in values
    ]


def acoustic_metrics(samples: list[int], rate: int) -> dict:
    frame_size = max(32, rate * ACOUSTIC_FRAME_MS // 1000)
    hop = max(1, rate * ACOUSTIC_HOP_MS // 1000)
    if len(samples) < frame_size:
        frames = [(0, samples + [0] * (frame_size - len(samples)))]
    else:
        frames = [
            (start, samples[start:start + frame_size])
            for start in range(0, len(samples) - frame_size + 1, hop)
        ]
    rms_values = [
        math.sqrt(sum(value * value for value in frame) / len(frame))
        for _start, frame in frames
    ]
    active_threshold = max(24.0, max(rms_values, default=0.0) * 0.06)
    active_frames = [
        (start, frame)
        for (start, frame), rms in zip(frames, rms_values)
        if rms >= active_threshold
    ]

    pitch_points = []
    for start, frame in active_frames:
        frequency, periodicity = _pitch_for_frame(frame, rate)
        if frequency is not None:
            pitch_points.append((start, frequency, periodicity))
    raw_pitch_center = percentile([point[1] for point in pitch_points], 0.5)
    if raw_pitch_center is not None:
        pitch_points = [
            point for point in pitch_points
            if raw_pitch_center * 0.55 <= point[1] <= raw_pitch_center * 1.65
        ]
    pitches = [point[1] for point in pitch_points]
    periodicities = [point[2] for point in pitch_points]

    spectral_frames = active_frames
    if len(spectral_frames) > 16:
        indexes = {
            round(index * (len(spectral_frames) - 1) / 15)
            for index in range(16)
        }
        spectral_frames = [spectral_frames[index] for index in sorted(indexes)]
    frequencies = list(range(SPECTRUM_STEP_HZ, SPECTRUM_MAX_HZ + 1, SPECTRUM_STEP_HZ))
    accumulated = [0.0] * len(frequencies)
    for _start, integer_frame in spectral_frames:
        mean = sum(integer_frame) / len(integer_frame)
        denominator = max(1, len(integer_frame) - 1)
        windowed = [
            (sample - mean) * (0.54 - 0.46 * math.cos(2.0 * math.pi * index / denominator))
            for index, sample in enumerate(integer_frame)
        ]
        for index, frequency in enumerate(frequencies):
            accumulated[index] += _goertzel_power(windowed, rate, frequency)
    if spectral_frames:
        powers = [value / len(spectral_frames) for value in accumulated]
    else:
        powers = accumulated
    raw_maximum_power = max(powers, default=0.0)
    maximum_power = raw_maximum_power or 1.0
    spectrum_db = [round(max(-80.0, 10.0 * math.log10(max(value, 1e-20) / maximum_power)), 3) for value in powers]
    total_power = sum(powers) or 1.0

    def band_level(first: int, last: int) -> float:
        power = sum(
            value for frequency, value in zip(frequencies, powers)
            if first <= frequency <= last
        )
        return round(10.0 * math.log10(max(power, 1e-20) / total_power), 3)

    smoothed = []
    smoothing_radius = max(1, 100 // SPECTRUM_STEP_HZ)
    for index, value in enumerate(powers):
        first = max(0, index - smoothing_radius)
        last = min(len(powers), index + smoothing_radius + 1)
        smoothed.append(sum(powers[first:last]) / (last - first))

    def peak_in(first: int, last: int) -> int | None:
        candidates = [
            (value, frequency)
            for frequency, value in zip(frequencies, smoothed)
            if first <= frequency <= last
        ]
        return max(candidates)[1] if candidates and max(candidates)[0] > 0.0 else None

    positive = [(frequency, value) for frequency, value in zip(frequencies, powers) if value > 0.0]
    centroid = sum(frequency * value for frequency, value in positive) / total_power if positive else None
    peak_frequency = frequencies[powers.index(raw_maximum_power)] if raw_maximum_power > 0.0 else None
    slope_points = [
        (math.log2(frequency / 100.0), level)
        for frequency, level in zip(frequencies, spectrum_db)
        if 200 <= frequency <= 4000 and level > -75.0
    ]
    if len(slope_points) > 1:
        mean_x = sum(point[0] for point in slope_points) / len(slope_points)
        mean_y = sum(point[1] for point in slope_points) / len(slope_points)
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in slope_points)
        denominator = sum((x - mean_x) ** 2 for x, _y in slope_points)
        slope = numerator / denominator if denominator else 0.0
    else:
        slope = 0.0

    return {
        "medianF0Hz": round(percentile(pitches, 0.5), 3) if pitches else None,
        "f0P10Hz": round(percentile(pitches, 0.1), 3) if pitches else None,
        "f0P90Hz": round(percentile(pitches, 0.9), 3) if pitches else None,
        "medianPeriodicity": round(percentile(periodicities, 0.5), 4) if periodicities else None,
        "voicedFrameRatio": round(len(pitch_points) / max(1, len(active_frames)), 4),
        "f0ContourHz": _binned_pitch(pitch_points, len(samples)),
        "spectrumFrequenciesHz": frequencies,
        "spectrumDb": spectrum_db,
        "spectrumPeakHz": peak_frequency,
        "spectralCentroidHz": round(centroid, 3) if centroid is not None else None,
        "spectralTiltDbPerOctave": round(slope, 3),
        "spectralBandsDb": {
            "100-500": band_level(100, 500),
            "600-1000": band_level(600, 1000),
            "1100-2000": band_level(1100, 2000),
            "2100-3500": band_level(2100, 3500),
            "3600-5000": band_level(3600, 5000),
        },
        "spectralRegionPeaksHz": [
            peak_in(200, 1000),
            peak_in(1100, 2500),
            peak_in(2600, 3800),
        ],
    }


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
    metrics = {
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
    metrics.update(acoustic_metrics(samples, rate))
    return metrics


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
    f0_pairs = [
        (a, b) for a, b in zip(left["f0ContourHz"], right["f0ContourHz"])
        if a is not None and b is not None
    ]
    f0_rmse = math.sqrt(
        sum((a - b) ** 2 for a, b in f0_pairs) / len(f0_pairs)
    ) if f0_pairs else None
    spectrum_pairs = list(zip(left["spectrumDb"], right["spectrumDb"]))
    spectrum_distance = (
        sum(abs(a - b) for a, b in spectrum_pairs) / len(spectrum_pairs)
        if spectrum_pairs else None
    )
    left_f0 = left["medianF0Hz"]
    right_f0 = right["medianF0Hz"]
    left_centroid = left["spectralCentroidHz"]
    right_centroid = right["spectralCentroidHz"]
    return {
        "pcmIdentical": left["pcmSha256"] == right["pcmSha256"],
        "durationDeltaMs": round(right["durationMs"] - left["durationMs"], 3),
        "internalSilenceDeltaMs": (
            right["internalSilenceMs"] - left["internalSilenceMs"]
        ),
        "energyEnvelopeDistance": round(distance, 6),
        "medianF0DeltaHz": round(right_f0 - left_f0, 3) if left_f0 is not None and right_f0 is not None else None,
        "f0ContourRmseHz": round(f0_rmse, 3) if f0_rmse is not None else None,
        "spectralCentroidDeltaHz": (
            round(right_centroid - left_centroid, 3)
            if left_centroid is not None and right_centroid is not None else None
        ),
        "spectrumDistanceDb": round(spectrum_distance, 3) if spectrum_distance is not None else None,
        "spectralRegionPeakDeltasHz": [
            right_peak - left_peak if left_peak is not None and right_peak is not None else None
            for left_peak, right_peak in zip(
                left["spectralRegionPeaksHz"], right["spectralRegionPeaksHz"]
            )
        ],
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


def summarize_comparisons(rows: list[dict]) -> list[dict]:
    summaries = []
    for group in sorted({row["group"] for row in rows}):
        group_rows = [row for row in rows if row["group"] == group]

        def mean_absolute(key: str) -> float | None:
            values = [abs(row[key]) for row in group_rows if row.get(key) is not None]
            return round(sum(values) / len(values), 3) if values else None

        def mean_value(key: str) -> float | None:
            values = [row[key] for row in group_rows if row.get(key) is not None]
            return round(sum(values) / len(values), 3) if values else None

        summaries.append({
            "group": group,
            "cases": len(group_rows),
            "meanAbsoluteDurationDeltaMs": mean_absolute("durationDeltaMs"),
            "meanAbsoluteMedianF0DeltaHz": mean_absolute("medianF0DeltaHz"),
            "meanF0ContourRmseHz": mean_value("f0ContourRmseHz"),
            "meanAbsoluteSpectralCentroidDeltaHz": mean_absolute("spectralCentroidDeltaHz"),
            "meanSpectrumDistanceDb": mean_value("spectrumDistanceDb"),
        })
    return summaries


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
        report["candidateSummary"] = summarize_comparisons(comparisons)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Black-box punctuation and boundary comparisons:")
    for row in report["behaviorComparisons"]:
        if not row["group"].startswith("punctuation"):
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
        for row in report["candidateSummary"]:
            if row["group"] not in {"acoustic-vowel", "acoustic-liquid", "prosody"}:
                continue
            print(
                f"{row['group']}: {row['cases']} cases; "
                f"F0 contour RMSE {row['meanF0ContourRmseHz']} Hz; "
                f"spectrum distance {row['meanSpectrumDistanceDb']} dB"
            )
    print(f"wrote aggregate report {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
