#!/usr/bin/env python3
"""Unit checks for the native NVDA driver's multi-model voice discovery."""
from __future__ import annotations

import importlib.util
import queue
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path


class _Setting:
    pass


class _BaseSynthDriver:
    VoiceSetting = RateSetting = PitchSetting = _Setting


class _VoiceInfo:
    def __init__(self, voice_id, name, language):
        self.id = voice_id
        self.name = name
        self.language = language


class _Notification:
    def notify(self, **_kwargs):
        pass


class _IndexCommand:
    def __init__(self, index):
        self.index = index


class _PitchCommand:
    def __init__(self, new_value):
        self.newValue = new_value


class _WavePlayer:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.feeds = []
        self.idle_calls = 0
        self.__class__.instances.append(self)

    def feed(self, data):
        self.feeds.append(data)

    def idle(self):
        self.idle_calls += 1


def load_driver():
    modules = {
        "config": types.SimpleNamespace(conf={"audio": {"outputDevice": ""}}),
        "logHandler": types.SimpleNamespace(log=types.SimpleNamespace(error=lambda *a, **k: None)),
        "nvwave": types.SimpleNamespace(WavePlayer=_WavePlayer),
        "speech": types.ModuleType("speech"),
        "speech.commands": types.SimpleNamespace(
            IndexCommand=_IndexCommand,
            PitchCommand=_PitchCommand,
        ),
        "synthDriverHandler": types.SimpleNamespace(
            SynthDriver=_BaseSynthDriver,
            VoiceInfo=_VoiceInfo,
            synthDoneSpeaking=_Notification(),
            synthIndexReached=_Notification(),
        ),
    }
    saved = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    try:
        path = (
            Path(__file__).resolve().parents[1]
            / "addon"
            / "synthDrivers"
            / "nokiaNative5320.py"
        )
        spec = importlib.util.spec_from_file_location("nokiaNative5320_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


DRIVER = load_driver()


class VoiceDiscoveryTest(unittest.TestCase):
    def make_driver(self, root):
        driver = DRIVER.SynthDriver.__new__(DRIVER.SynthDriver)
        driver._root = root
        driver._voiceSnapshots = driver._findVoiceSnapshots()
        driver._voices = driver._buildVoiceList()
        driver._voice = "5320:3-male"
        return driver

    def test_all_66_snapshots_are_exposed_with_stable_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data"
            data.mkdir()
            for language_id, _name, _locale in DRIVER._LANGUAGES:
                for gender in DRIVER._GENDERS:
                    (data / f"5320-{language_id}-{gender}.snapshot").write_bytes(b"x")
            driver = self.make_driver(root)
            self.assertEqual(66, len(driver._voices))
            self.assertIn("5320:1-female", driver._voices)
            self.assertIn("5320:402-male", driver._voices)
            self.assertEqual("de_DE", driver._get_language())

    def test_5500_voices_are_grouped_after_same_language_5320_voices(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data"
            data.mkdir()
            for language_id, _name, _locale in DRIVER._LANGUAGES:
                for gender in DRIVER._GENDERS:
                    (data / f"5320-{language_id}-{gender}.snapshot").write_bytes(b"x")
            for language_id in DRIVER._5500_LANGUAGE_IDS:
                (data / f"5500-{language_id}.snapshot").write_bytes(b"x")
            driver = self.make_driver(root)
            self.assertEqual(71, len(driver._voices))
            voices = list(driver._voices)
            for language_id in sorted(DRIVER._5500_LANGUAGE_IDS):
                self.assertEqual(
                    [
                        f"5320:{language_id}-male",
                        f"5320:{language_id}-female",
                        f"5500:{language_id}",
                    ],
                    [voice for voice in voices if voice.split(":", 1)[1].split("-", 1)[0] == str(language_id)],
                )
            self.assertEqual(
                "German male (Nokia 5500)",
                driver._voices["5500:3"].name,
            )

    def test_test43_german_snapshot_name_remains_compatible(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data"
            data.mkdir()
            legacy = data / "5320-de-male.snapshot"
            legacy.write_bytes(b"legacy")
            driver = self.make_driver(root)
            self.assertEqual(
                legacy,
                driver._voiceSnapshots["5320:3-male"],
            )
            self.assertEqual(["5320:3-male"], list(driver._voices))

    def test_queued_utterance_keeps_selected_voice(self):
        driver = DRIVER.SynthDriver.__new__(DRIVER.SynthDriver)
        driver._rate = 50
        driver._pitch = 50
        driver._voice = "5320:1-female"
        driver._generation = 7
        driver._lock = threading.Lock()
        driver._requests = queue.Queue()
        driver.speak(["Hello"])
        request = driver._requests.get_nowait()
        self.assertEqual(7, request[0])
        self.assertEqual("5320:1-female", request[1])

    def test_nvda_rate_64_starts_high_rate_pcm_fix(self):
        self.assertLess(DRIVER.SynthDriver._rateFactor(63), 1.45)
        self.assertGreater(DRIVER.SynthDriver._rateFactor(64), 1.45)


if __name__ == "__main__":
    unittest.main()
