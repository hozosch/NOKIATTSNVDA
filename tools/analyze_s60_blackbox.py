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
LOCAL_FRAME_MS = 30
LOCAL_HOP_MS = 20
LOCAL_SPECTRUM_HZ = (
    100, 150, 200, 250, 300, 400, 500, 650, 800,
    1000, 1250, 1500, 1800, 2200, 2700, 3300, 4000, 4800,
)


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


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _frame_spectrum(frame: list[int], rate: int) -> tuple[list[float], float]:
    mean = sum(frame) / len(frame)
    denominator = max(1, len(frame) - 1)
    windowed = [
        (sample - mean) * (0.54 - 0.46 * math.cos(2.0 * math.pi * index / denominator))
        for index, sample in enumerate(frame)
    ]
    powers = [_goertzel_power(windowed, rate, frequency) for frequency in LOCAL_SPECTRUM_HZ]
    total = sum(powers) or 1.0
    maximum = max(powers, default=0.0) or 1.0
    spectrum = [
        max(-80.0, 10.0 * math.log10(max(power, 1e-20) / maximum))
        for power in powers
    ]
    high = sum(
        power for frequency, power in zip(LOCAL_SPECTRUM_HZ, powers)
        if frequency >= 2200
    )
    high_band = 10.0 * math.log10(max(high, 1e-20) / total)
    return spectrum, high_band


def _regional_peaks(spectrum: list[float]) -> list[int | None]:
    peaks = []
    for first, last in ((200, 1000), (1100, 2500), (2600, 4800)):
        candidates = [
            (level, frequency)
            for frequency, level in zip(LOCAL_SPECTRUM_HZ, spectrum)
            if first <= frequency <= last
        ]
        peaks.append(max(candidates)[1] if candidates else None)
    return peaks


def local_frame_features(samples: list[int], rate: int) -> list[dict]:
    """Return transient frame features used only while comparing two WAVs.

    Leading and trailing quiet frames are dropped so the historical renderer's
    file padding cannot encourage latency in the independent implementation.
    Internal quiet frames remain and therefore still influence alignment.
    """
    frame_size = max(32, rate * LOCAL_FRAME_MS // 1000)
    hop = max(1, rate * LOCAL_HOP_MS // 1000)
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
    maximum_rms = max(rms_values, default=0.0)
    active_threshold = max(24.0, maximum_rms * 0.04)
    active_indexes = [index for index, rms in enumerate(rms_values) if rms >= active_threshold]
    if not active_indexes:
        return []
    first = max(0, active_indexes[0] - 1)
    last = min(len(frames) - 1, active_indexes[-1] + 1)
    features = []
    previous_spectrum: list[float] | None = None
    for index in range(first, last + 1):
        start, frame = frames[index]
        rms = rms_values[index]
        active = rms >= active_threshold
        spectrum, high_band = _frame_spectrum(frame, rate)
        frequency, periodicity = _pitch_for_frame(frame, rate) if active else (None, 0.0)
        crossings = sum(
            1 for left, right in zip(frame, frame[1:])
            if (left < 0 <= right) or (left >= 0 > right)
        )
        flux = (
            _mean([abs(a - b) for a, b in zip(spectrum, previous_spectrum)])
            if previous_spectrum is not None else 0.0
        )
        features.append({
            "timeMs": round(start * 1000.0 / rate, 3),
            "active": active,
            "energyDb": 20.0 * math.log10(max(rms, 1e-9) / max(maximum_rms, 1e-9)),
            "zeroCrossingRate": crossings / max(1, len(frame) - 1),
            "f0Hz": frequency,
            "periodicity": periodicity,
            "spectrumDb": spectrum,
            "highBandDb": high_band,
            "regionalPeaksHz": _regional_peaks(spectrum),
            "spectralFluxDb": flux or 0.0,
        })
        previous_spectrum = spectrum
    return features


def _frame_cost(left: dict, right: dict) -> float:
    activity_mismatch = 1.0 if left["active"] != right["active"] else 0.0
    energy = min(2.0, abs(left["energyDb"] - right["energyDb"]) / 24.0)
    if not left["active"] and not right["active"]:
        return 0.8 * energy
    spectrum = _mean([
        abs(a - b) for a, b in zip(left["spectrumDb"], right["spectrumDb"])
    ]) or 0.0
    periodicity = abs(left["periodicity"] - right["periodicity"])
    zcr = abs(left["zeroCrossingRate"] - right["zeroCrossingRate"])
    if left["f0Hz"] is not None and right["f0Hz"] is not None:
        f0 = min(2.0, abs(1200.0 * math.log2(right["f0Hz"] / left["f0Hz"])) / 500.0)
        voicing_mismatch = 0.0
    else:
        f0 = 0.0
        voicing_mismatch = 1.0 if (left["f0Hz"] is None) != (right["f0Hz"] is None) else 0.0
    return (
        0.46 * min(2.0, spectrum / 12.0)
        + 0.14 * energy
        + 0.10 * periodicity
        + 0.08 * min(2.0, zcr * 8.0)
        + 0.10 * f0
        + 0.07 * voicing_mismatch
        + 0.05 * activity_mismatch
    )


def align_frame_features(left: list[dict], right: list[dict]) -> list[tuple[int, int]]:
    """Align frame sequences with bounded dynamic time warping."""
    if not left or not right:
        return []
    rows = len(left)
    columns = len(right)
    band = max(abs(rows - columns) + 3, int(max(rows, columns) * 0.30))
    infinity = float("inf")
    costs = [[infinity] * (columns + 1) for _ in range(rows + 1)]
    moves = [[0] * (columns + 1) for _ in range(rows + 1)]
    costs[0][0] = 0.0
    for i in range(1, rows + 1):
        centre = i * columns / rows
        first = max(1, int(centre - band))
        last = min(columns, int(centre + band) + 1)
        for j in range(first, last + 1):
            diagonal = costs[i - 1][j - 1]
            vertical = costs[i - 1][j] + 0.045
            horizontal = costs[i][j - 1] + 0.045
            previous, move = min(
                ((diagonal, 1), (vertical, 2), (horizontal, 3)),
                key=lambda item: item[0],
            )
            if math.isfinite(previous):
                costs[i][j] = previous + _frame_cost(left[i - 1], right[j - 1])
                moves[i][j] = move
    if not math.isfinite(costs[rows][columns]):
        return []
    path = []
    i, j = rows, columns
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        move = moves[i][j]
        if move == 1:
            i -= 1
            j -= 1
        elif move == 2:
            i -= 1
        elif move == 3:
            j -= 1
        else:
            return []
    path.reverse()
    return path


def compare_local_features(left: list[dict], right: list[dict]) -> dict:
    path = align_frame_features(left, right)
    if not path:
        return {
            "alignedFrameCount": 0,
            "localFeatureScore": None,
            "frameSpectrumDistanceDb": None,
            "transitionSpectrumDistanceDb": None,
            "f0ContourRmseCents": None,
            "voicingMismatchRate": None,
            "periodicityDistance": None,
            "unvoicedHighBandDistanceDb": None,
            "spectralFluxDistanceDb": None,
            "timeWarpRatio": None,
            "regionalPeakMeanAbsoluteDeltasHz": [None, None, None],
        }

    active_pairs = [
        (left[i], right[j]) for i, j in path
        if left[i]["active"] and right[j]["active"]
    ]
    spectrum_distances = [
        _mean([abs(a - b) for a, b in zip(a_frame["spectrumDb"], b_frame["spectrumDb"])]) or 0.0
        for a_frame, b_frame in active_pairs
    ]
    f0_cents = [
        1200.0 * math.log2(b_frame["f0Hz"] / a_frame["f0Hz"])
        for a_frame, b_frame in active_pairs
        if a_frame["f0Hz"] is not None and b_frame["f0Hz"] is not None
    ]
    voicing_mismatches = [
        (a_frame["f0Hz"] is None) != (b_frame["f0Hz"] is None)
        for a_frame, b_frame in active_pairs
    ]
    unvoiced_pairs = [
        (a_frame, b_frame) for a_frame, b_frame in active_pairs
        if a_frame["f0Hz"] is None and b_frame["f0Hz"] is None
    ]
    transition_distances = []
    for (previous_i, previous_j), (i, j) in zip(path, path[1:]):
        if i == previous_i or j == previous_j:
            continue
        frames = (left[previous_i], right[previous_j], left[i], right[j])
        if not all(frame["active"] for frame in frames):
            continue
        left_delta = [
            current - previous
            for previous, current in zip(left[previous_i]["spectrumDb"], left[i]["spectrumDb"])
        ]
        right_delta = [
            current - previous
            for previous, current in zip(right[previous_j]["spectrumDb"], right[j]["spectrumDb"])
        ]
        transition_distances.append(
            _mean([abs(a - b) for a, b in zip(left_delta, right_delta)]) or 0.0
        )
    regional_deltas: list[list[float]] = [[], [], []]
    for a_frame, b_frame in active_pairs:
        for region, (a_peak, b_peak) in enumerate(zip(
            a_frame["regionalPeaksHz"], b_frame["regionalPeaksHz"]
        )):
            if a_peak is not None and b_peak is not None:
                regional_deltas[region].append(abs(b_peak - a_peak))

    spectrum = _mean(spectrum_distances)
    transition = _mean(transition_distances)
    f0_rmse = math.sqrt(_mean([value * value for value in f0_cents]) or 0.0) if f0_cents else None
    voicing = _mean([float(value) for value in voicing_mismatches])
    periodicity = _mean([
        abs(a_frame["periodicity"] - b_frame["periodicity"])
        for a_frame, b_frame in active_pairs
    ])
    high_band = _mean([
        abs(a_frame["highBandDb"] - b_frame["highBandDb"])
        for a_frame, b_frame in unvoiced_pairs
    ])
    flux = _mean([
        abs(a_frame["spectralFluxDb"] - b_frame["spectralFluxDb"])
        for a_frame, b_frame in unvoiced_pairs
    ])
    warp_moves = sum(
        1 for (previous_i, previous_j), (i, j) in zip(path, path[1:])
        if i == previous_i or j == previous_j
    )
    warp = warp_moves / max(1, len(path) - 1)

    # This score is a release-ranking aid, not a claim about perceptual
    # equivalence.  A listening test remains mandatory for a final candidate.
    score = 100.0 * (
        0.35 * min(2.0, (spectrum or 0.0) / 12.0)
        + 0.20 * min(2.0, (transition or 0.0) / 10.0)
        + 0.12 * min(2.0, (f0_rmse or 0.0) / 400.0)
        + 0.10 * (voicing or 0.0)
        + 0.07 * min(2.0, (periodicity or 0.0) / 0.5)
        + 0.06 * min(2.0, (high_band or 0.0) / 12.0)
        + 0.05 * min(2.0, (flux or 0.0) / 10.0)
        + 0.05 * min(2.0, warp / 0.5)
    )
    return {
        "alignedFrameCount": len(path),
        "localFeatureScore": round(score, 3),
        "frameSpectrumDistanceDb": round(spectrum, 3) if spectrum is not None else None,
        "transitionSpectrumDistanceDb": round(transition, 3) if transition is not None else None,
        "f0ContourRmseCents": round(f0_rmse, 3) if f0_rmse is not None else None,
        "voicingMismatchRate": round(voicing, 5) if voicing is not None else None,
        "periodicityDistance": round(periodicity, 5) if periodicity is not None else None,
        "unvoicedHighBandDistanceDb": round(high_band, 3) if high_band is not None else None,
        "spectralFluxDistanceDb": round(flux, 3) if flux is not None else None,
        "timeWarpRatio": round(warp, 5),
        "regionalPeakMeanAbsoluteDeltasHz": [
            round(value, 3) if value is not None else None
            for value in (_mean(group) for group in regional_deltas)
        ],
    }


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
        "_localFrames": local_frame_features(samples, rate),
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
    comparison = {
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
    comparison.update(compare_local_features(left["_localFrames"], right["_localFrames"]))
    return comparison


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
            if key not in {"pcmSha256", "energyEnvelope"} and not key.startswith("_")
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
            "meanLocalFeatureScore": mean_value("localFeatureScore"),
            "meanFrameSpectrumDistanceDb": mean_value("frameSpectrumDistanceDb"),
            "meanTransitionSpectrumDistanceDb": mean_value("transitionSpectrumDistanceDb"),
            "meanF0ContourRmseCents": mean_value("f0ContourRmseCents"),
            "meanVoicingMismatchRate": mean_value("voicingMismatchRate"),
            "meanUnvoicedHighBandDistanceDb": mean_value("unvoicedHighBandDistanceDb"),
            "meanTimeWarpRatio": mean_value("timeWarpRatio"),
        })
    return summaries


def candidate_decision(
    rows: list[dict],
    baseline_score: float | None = None,
    minimum_improvement_percent: float = 15.0,
) -> dict:
    """Build a conservative non-punctuation release gate.

    Punctuation is deliberately excluded because matching punctuation while
    phones and transitions still sound wrong would be a false improvement.
    """
    focus_rows = [
        row for row in rows
        if not row["group"].startswith("punctuation")
        and row.get("localFeatureScore") is not None
    ]
    score = _mean([row["localFeatureScore"] for row in focus_rows])
    decision = {
        "scope": "non-punctuation acoustic, pronunciation and prosody probes",
        "cases": len(focus_rows),
        "score": round(score, 3) if score is not None else None,
        "lowerIsBetter": True,
        "minimumImprovementPercent": minimum_improvement_percent,
        "listeningValidationRequired": True,
        "status": "no-comparable-cases" if score is None else "baseline-only",
    }
    if score is None or baseline_score is None:
        return decision
    improvement = 100.0 * (baseline_score - score) / max(abs(baseline_score), 1e-9)
    decision.update({
        "baselineScore": round(baseline_score, 3),
        "improvementPercent": round(improvement, 3),
        "status": "eligible-for-listening" if improvement >= minimum_improvement_percent else "rejected-small-improvement",
    })
    return decision


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle-dir", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path)
    parser.add_argument("--baseline-report", type=Path)
    parser.add_argument("--minimum-improvement-percent", type=float, default=15.0)
    parser.add_argument("--enforce-gate", action="store_true")
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
        baseline_score = None
        if args.baseline_report:
            baseline = json.loads(args.baseline_report.read_text(encoding="utf-8"))
            baseline_score = baseline.get("candidateDecision", {}).get("score")
            if not isinstance(baseline_score, (int, float)):
                parser.error("baseline report has no numeric candidateDecision.score")
        report["candidateDecision"] = candidate_decision(
            comparisons,
            baseline_score=baseline_score,
            minimum_improvement_percent=args.minimum_improvement_percent,
        )

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
                f"spectrum distance {row['meanSpectrumDistanceDb']} dB; "
                f"time-local score {row['meanLocalFeatureScore']}"
            )
        decision = report["candidateDecision"]
        print(
            f"Non-punctuation release gate: {decision['status']}; "
            f"score {decision['score']}"
        )
    print(f"wrote aggregate report {args.output}")
    if args.enforce_gate and report.get("candidateDecision", {}).get("status") != "eligible-for-listening":
        print("candidate did not clear the objective improvement gate", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
