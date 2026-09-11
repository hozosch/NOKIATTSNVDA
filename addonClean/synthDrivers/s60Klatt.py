"""Independent historical S60 speech reconstruction for NVDA."""

from __future__ import annotations

import ctypes
import queue
import struct
import sys
import threading
from collections import OrderedDict
from pathlib import Path

import config
from logHandler import log
import nvwave
from speech.commands import IndexCommand, PitchCommand
from synthDriverHandler import (
	SynthDriver as BaseSynthDriver,
	VoiceInfo,
	synthDoneSpeaking,
	synthIndexReached,
)


_PcmCallback = ctypes.CFUNCTYPE(
	None,
	ctypes.c_void_p,
	ctypes.POINTER(ctypes.c_int16),
	ctypes.c_uint32,
	ctypes.c_uint32,
)


class _Callbacks(ctypes.Structure):
	_fields_ = [
		("pcm", _PcmCallback),
		("user", ctypes.c_void_p),
	]


_VOICES = OrderedDict((
	(
		"5320-de-male",
		VoiceInfo(
			"5320-de-male",
			"5320 German male (independent reconstruction)",
			"de_DE",
		),
	),
	(
		"5320-de-female",
		VoiceInfo(
			"5320-de-female",
			"5320 German female (independent reconstruction)",
			"de_DE",
		),
	),
))


class SynthDriver(BaseSynthDriver):
	name = "s60Klatt"
	description = "S60 Klatt (independent 5320 reconstruction, test 3 probe 1)"
	supportedSettings = (
		BaseSynthDriver.VoiceSetting(),
		BaseSynthDriver.RateSetting(),
		BaseSynthDriver.PitchSetting(),
	)
	supportedCommands = {IndexCommand, PitchCommand}
	supportedNotifications = {synthIndexReached, synthDoneSpeaking}

	@classmethod
	def check(cls):
		try:
			root = Path(__file__).resolve().parent.parent
			arch = cls._getProcessArchitecture()
			return (root / "bin" / arch / f"classic_klatt_{arch}.dll").is_file()
		except Exception:
			return False

	def __init__(self):
		self._rate = 50
		self._pitch = 50
		self._voice = "5320-de-male"
		self._arch = self._getProcessArchitecture()
		root = Path(__file__).resolve().parent.parent
		self._dllPath = root / "bin" / self._arch / f"classic_klatt_{self._arch}.dll"
		try:
			self._dll = ctypes.CDLL(str(self._dllPath))
		except OSError as error:
			raise OSError(
				f"Could not load the {self._arch} independent S60 Klatt runtime: "
				f"{self._dllPath}; loader error: {error!r}; "
				f"winerror={getattr(error, 'winerror', None)}"
			) from error
		self._bindApi()
		self._engine = self._dll.classic_klatt_create()
		if not self._engine:
			raise RuntimeError("Could not create the independent S60 Klatt engine")
		self._player = nvwave.WavePlayer(
			channels=1,
			samplesPerSec=16000,
			bitsPerSample=16,
			outputDevice=config.conf["audio"]["outputDevice"],
		)
		self._requests: queue.Queue = queue.Queue()
		self._stopEvent = threading.Event()
		self._lock = threading.Lock()
		self._generation = 0
		self._thread = threading.Thread(
			target=self._worker,
			name="S60Klatt",
			daemon=True,
		)
		self._thread.start()

	@staticmethod
	def _getProcessArchitecture():
		"""Return the architecture of NVDA itself, including ARM64EC."""
		imageMachine = None
		try:
			with open(sys.executable, "rb") as executable:
				executable.seek(0x3C)
				peOffset = struct.unpack("<I", executable.read(4))[0]
				executable.seek(peOffset + 4)
				imageMachine = struct.unpack("<H", executable.read(2))[0]
		except (OSError, EOFError, struct.error):
			imageMachine = None
		if ctypes.sizeof(ctypes.c_void_p) == 4:
			return "x86"
		processMachine = ctypes.c_ushort()
		nativeMachine = ctypes.c_ushort()
		isWow64Process2 = ctypes.windll.kernel32.IsWow64Process2
		isWow64Process2.argtypes = [
			ctypes.c_void_p,
			ctypes.POINTER(ctypes.c_ushort),
			ctypes.POINTER(ctypes.c_ushort),
		]
		isWow64Process2.restype = ctypes.c_int
		if not isWow64Process2(
			ctypes.windll.kernel32.GetCurrentProcess(),
			ctypes.byref(processMachine),
			ctypes.byref(nativeMachine),
		):
			raise ctypes.WinError()
		machine = processMachine.value or nativeMachine.value
		if imageMachine in {0xA641, 0xA64E}:
			return "arm64ec"
		if (
			imageMachine == 0x8664
			and processMachine.value == 0
			and nativeMachine.value == 0xAA64
		):
			return "arm64ec"
		if imageMachine == 0x8664 or machine == 0x8664:
			return "x64"
		if machine == 0xAA64:
			return "arm64"
		raise RuntimeError(f"Unsupported NVDA process architecture: 0x{machine:04x}")

	def _bindApi(self):
		self._dll.classic_klatt_version.argtypes = []
		self._dll.classic_klatt_version.restype = ctypes.c_char_p
		self._dll.classic_klatt_create.argtypes = []
		self._dll.classic_klatt_create.restype = ctypes.c_void_p
		self._dll.classic_klatt_destroy.argtypes = [ctypes.c_void_p]
		self._dll.classic_klatt_destroy.restype = None
		self._dll.classic_klatt_cancel.argtypes = [ctypes.c_void_p]
		self._dll.classic_klatt_cancel.restype = None
		self._dll.classic_klatt_reset_cancel.argtypes = [ctypes.c_void_p]
		self._dll.classic_klatt_reset_cancel.restype = None
		self._dll.classic_klatt_speak_utf16.argtypes = [
			ctypes.c_void_p,
			ctypes.POINTER(ctypes.c_uint16),
			ctypes.c_uint32,
			ctypes.c_int,
			ctypes.c_int,
			ctypes.c_int,
			ctypes.POINTER(_Callbacks),
		]
		self._dll.classic_klatt_speak_utf16.restype = ctypes.c_int

	def _get_availableVoices(self):
		return _VOICES

	def _get_voice(self):
		return self._voice

	def _set_voice(self, value):
		if value in _VOICES:
			self._voice = value

	def _get_language(self):
		return "de_DE"

	def _get_rate(self):
		return self._rate

	def _set_rate(self, value):
		self._rate = max(0, min(100, int(value)))

	def _get_pitch(self):
		return self._pitch

	def _set_pitch(self, value):
		self._pitch = max(0, min(100, int(value)))

	@staticmethod
	def _voiceNumber(voiceId):
		return 1 if voiceId == "5320-de-female" else 0

	def speak(self, speechSequence):
		runs = []
		parts = []
		indexes = []
		currentPitch = self._pitch

		def flushText():
			if not parts:
				return
			text = "".join(parts)
			parts.clear()
			if text:
				runs.append((text, currentPitch))

		for item in speechSequence:
			if isinstance(item, str):
				parts.append(item)
			elif isinstance(item, IndexCommand):
				indexes.append(item.index)
			elif isinstance(item, PitchCommand):
				flushText()
				currentPitch = max(0, min(100, int(item.newValue)))
		flushText()
		if not runs:
			for index in indexes:
				synthIndexReached.notify(synth=self, index=index)
			synthDoneSpeaking.notify(synth=self)
			return
		with self._lock:
			generation = self._generation
			self._requests.put((
				generation,
				self._voice,
				tuple(runs),
				tuple(indexes),
				self._rate,
			))

	def cancel(self):
		with self._lock:
			self._generation += 1
			engine = self._engine
		if engine:
			self._dll.classic_klatt_cancel(engine)
		self._player.stop()
		while True:
			try:
				self._requests.get_nowait()
			except queue.Empty:
				break

	def pause(self, switch):
		self._player.pause(switch)

	def terminate(self):
		self.cancel()
		self._stopEvent.set()
		self._requests.put(None)
		self._thread.join(timeout=3)
		self._player.close()
		if self._engine:
			self._dll.classic_klatt_destroy(self._engine)
			self._engine = None

	def _worker(self):
		while not self._stopEvent.is_set():
			request = self._requests.get()
			if request is None:
				break
			generation, voiceId, runs, indexes, rate = request
			with self._lock:
				if generation != self._generation:
					continue
			try:
				self._runUtterance(generation, voiceId, runs, indexes, rate)
			except Exception:
				log.error("Independent S60 Klatt synthesis failed", exc_info=True)

	def _runUtterance(self, generation, voiceId, runs, indexes, rate):
		with self._lock:
			if generation != self._generation:
				return
			self._dll.classic_klatt_reset_cancel(self._engine)

		def onPcm(_user, samples, sampleCount, sampleRate):
			if sampleRate == 16000 and generation == self._generation:
				self._player.feed(ctypes.string_at(samples, sampleCount * 2))

		pcmCallback = _PcmCallback(onPcm)
		callbacks = _Callbacks(pcmCallback, None)
		for text, pitch in runs:
			if generation != self._generation:
				return
			encoded = text.encode("utf-16-le")
			units = len(encoded) // 2
			if not units:
				continue
			textBuffer = (ctypes.c_uint16 * units).from_buffer_copy(encoded)
			ok = self._dll.classic_klatt_speak_utf16(
				self._engine,
				textBuffer,
				units,
				rate,
				pitch,
				self._voiceNumber(voiceId),
				ctypes.byref(callbacks),
			)
			if not ok and generation == self._generation:
				raise RuntimeError(
					f"Independent S60 Klatt runtime rejected synthesis; "
					f"version={self._dll.classic_klatt_version().decode('ascii', 'replace')}, "
					f"arch={self._arch}, voice={voiceId}"
				)
		if generation == self._generation:
			for index in indexes:
				synthIndexReached.notify(synth=self, index=index)
			self._player.idle()
			synthDoneSpeaking.notify(synth=self)
