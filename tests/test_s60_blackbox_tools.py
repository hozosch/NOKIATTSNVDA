#!/usr/bin/env python3
"""Regression tests for the output-only S60 measurement tools."""
from __future__ import annotations

import math
from pathlib import Path
import sys
import tempfile
import unittest
import wave


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import analyze_s60_blackbox as ANALYZE  # noqa: E402
import capture_s60_blackbox as CAPTURE  # noqa: E402
import export_s60_phone_profile as EXPORT  # noqa: E402
import fit_clean_klatt_profile as FIT  # noqa: E402
import fit_clean_klatt_phone_profile as PHONE_FIT  # noqa: E402


def write_test_wav(
    path: Path,
    sections: list[tuple[int, bool]],
    frequency: float = 200.0,
) -> None:
    samples = []
    position = 0
    for milliseconds, voiced in sections:
        count = 16 * milliseconds
        for _ in range(count):
            value = int(8000 * math.sin(2.0 * math.pi * frequency * position / 16000.0)) if voiced else 0
            samples.append(value)
            position += 1
    pcm = bytearray()
    for value in samples:
        pcm.extend(int(value).to_bytes(2, "little", signed=True))
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16000)
        target.writeframes(pcm)


class BlackBoxToolsTest(unittest.TestCase):
    def test_phone_fitter_signature_score_is_zero_only_for_equal_target(self):
        signature = {
            "focusDurationMs": 180,
            "sourceMix": [0.0, 0.75, 0.25],
            "medianF0Hz": 100.0,
            "meanPeriodicity": 0.7,
            "meanSpectrumDb": [0.0, -5.0, -12.0],
            "meanCepstralShape": [4.0, -2.0],
            "meanCrestFactor": 3.2,
            "meanDerivativeRatio": 0.4,
        }
        self.assertEqual(0.0, PHONE_FIT.compare_signatures(signature, signature)["score"])
        changed = dict(signature)
        changed["meanSpectrumDb"] = [0.0, -12.0, -30.0]
        self.assertGreater(
            PHONE_FIT.compare_signatures(signature, changed)["score"], 5.0
        )

    def test_fitter_defaults_are_valid_and_compile_defines_are_stable(self):
        values = FIT.default_values()
        self.assertEqual(set(FIT.PARAMETERS), set(values))
        self.assertEqual(values, FIT.normalize(values))
        defines = FIT.compile_defines(values)
        self.assertEqual("-DCK_USE_PLATEAU_INTONATION=1", defines[0])
        self.assertEqual(sorted(defines[1:]), defines[1:])
        self.assertIn("-DCK_MALE_BASE_F0=97.5918091", defines)

    def test_fitter_keeps_glottal_close_after_open(self):
        values = FIT.default_values()
        values["CK_GLOTTAL_OPEN_END"] = 0.48
        values["CK_GLOTTAL_CLOSE_END"] = 0.38
        normalized = FIT.normalize(values)
        self.assertGreaterEqual(
            normalized["CK_GLOTTAL_CLOSE_END"],
            normalized["CK_GLOTTAL_OPEN_END"] + 0.08,
        )

    def test_fitter_accepts_its_report_as_a_new_search_centre(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fit.json"
            expected = FIT.default_values()
            path.write_text(
                __import__("json").dumps({"defines": expected}), encoding="utf-8"
            )
            self.assertEqual(expected, FIT.load_initial_values(path))

    def test_coordinate_candidates_change_one_parameter(self):
        values = FIT.default_values()
        candidates = FIT.coordinate_candidates(
            values, ("CK_MALE_BASE_F0", "CK_MALE_F1_SCALE"), 0.1
        )
        self.assertEqual(4, len(candidates))
        for candidate in candidates:
            changed = [name for name in values if candidate[name] != values[name]]
            self.assertEqual(1, len(changed))

    def test_repository_corpus_is_valid_and_language_separated(self):
        cases = CAPTURE.load_corpus(TOOLS / "s60_blackbox_corpus.json")
        languages = {case["language"] for case in cases}
        self.assertEqual({"de-DE", "en-GB", "fi-FI", "fr-FR", "it-IT"}, languages)
        self.assertEqual(175, len(cases))
        self.assertTrue(any(case.get("compareTo") for case in cases))
        german_targets = [
            case for case in cases
            if case["language"] == "de-DE" and case.get("phoneTarget")
        ]
        self.assertEqual(28, len(german_targets))

    def test_nk_renderer_command_is_an_explicit_process_boundary(self):
        case = {
            "languageId": 3,
            "text": "Anna, Maria",
        }
        command = CAPTURE.nk_render_command(
            Path("nk_render.exe"),
            Path("SYM.ROM"),
            Path("files"),
            case,
            "female",
            Path("out.wav"),
        )
        self.assertEqual(
            [
                "nk_render.exe", "SYM.ROM", "files", "3",
                "DefaultFemale", "out.wav", "Anna, Maria",
            ],
            command,
        )

    def test_timing_analysis_detects_only_internal_silence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "probe.wav"
            write_test_wav(path, [(40, False), (100, True), (90, False), (100, True), (50, False)])
            metrics = ANALYZE.wav_metrics(path)
        self.assertEqual(380.0, metrics["durationMs"])
        self.assertEqual(1, metrics["internalSilenceCount"])
        self.assertEqual(90, metrics["internalSilenceMs"])
        self.assertEqual(40, metrics["activeStartMs"])

    def test_acoustic_analysis_tracks_f0_and_spectral_peak(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tone.wav"
            write_test_wav(path, [(400, True)], frequency=200.0)
            metrics = ANALYZE.wav_metrics(path)
        self.assertAlmostEqual(200.0, metrics["medianF0Hz"], delta=8.0)
        self.assertEqual(200, metrics["spectrumPeakHz"])
        self.assertEqual(200, len(metrics["spectrumDb"]))
        self.assertGreater(metrics["voicedFrameRatio"], 0.9)
        self.assertGreater(sum(value is not None for value in metrics["f0ContourHz"]), 15)

    def test_comparison_distinguishes_identical_and_paused_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            continuous = root / "continuous.wav"
            copy = root / "copy.wav"
            paused = root / "paused.wav"
            write_test_wav(continuous, [(200, True)])
            write_test_wav(copy, [(200, True)])
            write_test_wav(paused, [(100, True), (80, False), (100, True)])
            base_metrics = ANALYZE.wav_metrics(continuous)
            same = ANALYZE.compare_metrics(base_metrics, ANALYZE.wav_metrics(copy))
            different = ANALYZE.compare_metrics(base_metrics, ANALYZE.wav_metrics(paused))
        self.assertTrue(same["pcmIdentical"])
        self.assertEqual(0.0, same["durationDeltaMs"])
        self.assertEqual(0.0, same["localFeatureScore"])
        self.assertGreater(same["alignedFrameCount"], 5)
        self.assertFalse(different["pcmIdentical"])
        self.assertEqual(80.0, different["durationDeltaMs"])
        self.assertGreater(different["energyEnvelopeDistance"], 0.05)
        self.assertGreater(different["timeWarpRatio"], 0.0)

    def test_time_local_analysis_detects_pitch_and_spectrum_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            low = root / "low.wav"
            high = root / "high.wav"
            write_test_wav(low, [(500, True)], frequency=160.0)
            write_test_wav(high, [(500, True)], frequency=260.0)
            comparison = ANALYZE.compare_metrics(
                ANALYZE.wav_metrics(low), ANALYZE.wav_metrics(high)
            )
        self.assertGreater(comparison["localFeatureScore"], 5.0)
        self.assertGreater(comparison["f0ContourRmseCents"], 500.0)
        self.assertGreater(comparison["frameSpectrumDistanceDb"], 1.0)

    def test_source_shape_distinguishes_smooth_and_impulsive_excitation(self):
        smooth = [
            int(8000 * math.sin(2.0 * math.pi * 8 * index / 160))
            for index in range(160)
        ]
        impulsive = [16000 if index % 20 == 0 else 0 for index in range(160)]
        smooth_crest, smooth_derivative = ANALYZE._temporal_source_shape(smooth)
        impulse_crest, impulse_derivative = ANALYZE._temporal_source_shape(impulsive)
        self.assertGreater(impulse_crest, smooth_crest * 2.0)
        self.assertGreater(impulse_derivative, smooth_derivative)

    def test_phone_focus_uses_vcv_centre_and_periodic_vowel_frames(self):
        frames = [
            {
                "active": True,
                "f0Hz": 200.0 if index % 2 == 0 else None,
                "periodicity": 0.8 if index % 2 == 0 else 0.1,
            }
            for index in range(10)
        ]
        consonant = ANALYZE.phone_focus_features(frames, "acoustic-fricative")
        vowel = ANALYZE.phone_focus_features(frames, "acoustic-vowel")
        self.assertEqual(6, len(consonant))
        self.assertEqual(5, len(vowel))
        self.assertTrue(all(frame["f0Hz"] is not None for frame in vowel))

    def test_phone_profile_export_aggregates_contexts_without_pcm(self):
        signature = {
            "focusDurationMs": 100,
            "sourceMix": [0.0, 1.0, 0.0],
            "medianF0Hz": 120.0,
            "meanPeriodicity": 0.8,
            "meanSpectrumDb": [0.0, -3.0],
            "meanCepstralShape": [1.0, 2.0],
            "meanCrestFactor": 1.4,
            "meanDerivativeRatio": 0.5,
        }
        report = {
            "schema": 1,
            "metricVersion": 2,
            "oracle": {
                "backend": "separate-reference-process",
                "voice": "male",
                "cases": [
                    {
                        "id": "de_tone_a",
                        "language": "de-DE",
                        "group": "acoustic-vowel",
                        "text": "Baba",
                        "phoneTarget": "a",
                        "phoneSignature": signature,
                    }
                ],
            },
        }
        profile = EXPORT.build_profile(report, "de-DE")
        self.assertEqual(1, profile["phoneCount"])
        self.assertEqual(1, profile["phones"]["a"]["aggregate"]["contexts"])
        self.assertNotIn("pcm", str(profile).lower())

    def test_phone_profile_fitter_signature_score_is_zero_only_for_identity(self):
        signature = {
            "focusDurationMs": 100,
            "sourceMix": [0.0, 1.0, 0.0],
            "medianF0Hz": 100.0,
            "meanPeriodicity": 0.8,
            "meanSpectrumDb": [0.0, -3.0],
            "meanCepstralShape": [1.0, 2.0],
            "meanCrestFactor": 2.0,
            "meanDerivativeRatio": 0.4,
        }
        self.assertEqual(
            0.0,
            PHONE_FIT.compare_signatures(signature, dict(signature))["score"],
        )
        changed = dict(signature)
        changed["sourceMix"] = [0.0, 0.0, 1.0]
        changed["meanCrestFactor"] = 4.0
        self.assertGreater(
            PHONE_FIT.compare_signatures(signature, changed)["score"], 20.0
        )

    def test_candidate_gate_ignores_punctuation_and_requires_large_gain(self):
        rows = [
            {"group": "punctuation", "localFeatureScore": 0.0},
            {"group": "acoustic-vowel", "localFeatureScore": 40.0},
            {"group": "consonants", "localFeatureScore": 50.0},
        ]
        baseline = ANALYZE.candidate_decision(rows)
        self.assertEqual(45.0, baseline["score"])
        rejected = ANALYZE.candidate_decision(rows, baseline_score=50.0)
        self.assertEqual("rejected-small-improvement", rejected["status"])
        accepted = ANALYZE.candidate_decision(rows, baseline_score=60.0)
        self.assertEqual("eligible-for-listening", accepted["status"])

    def test_candidate_gate_requires_isolated_phone_improvement(self):
        rows = [
            {
                "group": "acoustic-vowel",
                "localFeatureScore": 40.0,
                "phoneFeatureScore": 55.0,
            },
            {"group": "prosody", "localFeatureScore": 40.0},
        ]
        decision = ANALYZE.candidate_decision(
            rows,
            baseline_score=60.0,
            baseline_phone_score=60.0,
        )
        self.assertGreater(decision["improvementPercent"], 15.0)
        self.assertLess(decision["phoneImprovementPercent"], 15.0)
        self.assertEqual("rejected-small-improvement", decision["status"])

    def test_local_score_does_not_reward_missing_unvoiced_alignment(self):
        def feature(f0):
            return {
                "active": True,
                "energyDb": 0.0,
                "spectrumDb": [0.0] * len(ANALYZE.LOCAL_SPECTRUM_HZ),
                "cepstralShape": [0.0] * ANALYZE.CEPSTRAL_SHAPE_COEFFICIENTS,
                "crestFactor": 1.0,
                "derivativeRatio": 0.5,
                "periodicity": 0.8 if f0 else 0.1,
                "zeroCrossingRate": 0.1,
                "f0Hz": f0,
                "highBandDb": -8.0,
                "regionalPeaksHz": [500, 1500, 3300],
                "spectralFluxDb": 0.0,
            }

        comparison = ANALYZE.compare_local_features(
            [feature(None)], [feature(100.0)]
        )
        self.assertEqual(12.0, comparison["unvoicedHighBandDistanceDb"])
        self.assertEqual(10.0, comparison["spectralFluxDistanceDb"])


if __name__ == "__main__":
    unittest.main()
