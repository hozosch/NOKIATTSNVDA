#!/usr/bin/env python3
"""Unit checks for the independent S60 Klatt NVDA driver."""
from __future__ import annotations

import importlib.util
import queue
import sys
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
	def __init__(self, **_kwargs):
		pass


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
			/ "addonClean"
			/ "synthDrivers"
			/ "s60Klatt.py"
		)
		spec = importlib.util.spec_from_file_location("s60Klatt_test", path)
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


class S60KlattDriverTest(unittest.TestCase):
	def make_driver(self):
		driver = DRIVER.SynthDriver.__new__(DRIVER.SynthDriver)
		driver._rate = 50
		driver._pitch = 50
		driver._voice = "5320-de-male"
		driver._generation = 3
		driver._lock = threading.Lock()
		driver._requests = queue.Queue()
		return driver

	def test_two_independent_german_5320_reconstructions(self):
		voices = DRIVER.SynthDriver._get_availableVoices(self.make_driver())
		self.assertEqual(["5320-de-male", "5320-de-female"], list(voices))
		self.assertTrue(all(voice.language == "de_DE" for voice in voices.values()))
		self.assertTrue(all("Nokia" not in voice.name for voice in voices.values()))

	def test_speech_request_keeps_voice_rate_and_pitch_runs(self):
		driver = self.make_driver()
		driver._voice = "5320-de-female"
		driver._rate = 61
		driver.speak(["Hallo ", _PitchCommand(70), "Welt"])
		request = driver._requests.get_nowait()
		self.assertEqual(3, request[0])
		self.assertEqual("5320-de-female", request[1])
		self.assertEqual((("Hallo ", 50), ("Welt", 70)), request[2])
		self.assertEqual(61, request[4])

	def test_settings_are_clamped(self):
		driver = self.make_driver()
		driver._set_rate(150)
		driver._set_pitch(-20)
		self.assertEqual(100, driver._get_rate())
		self.assertEqual(0, driver._get_pitch())

	def test_clean_addon_tree_has_no_firmware_derived_payloads(self):
		root = Path(__file__).resolve().parents[1] / "addonClean"
		for path in root.rglob("*"):
			if path.is_file():
				self.assertNotIn(path.suffix.lower(), {".rom", ".nrp", ".ncf", ".snapshot"})
				self.assertNotIn("nokia_runtime", path.name.lower())


if __name__ == "__main__":
	unittest.main()
