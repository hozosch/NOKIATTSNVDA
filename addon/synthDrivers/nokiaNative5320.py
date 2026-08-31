"""Experimental in-process NVDA driver for the native-only Nokia 5320 runtime."""

from __future__ import annotations

import ctypes
import os
import platform
import queue
import threading
from pathlib import Path

import config
from logHandler import log
import nvwave
from speech.commands import IndexCommand
from synthDriverHandler import (
	SynthDriver as BaseSynthDriver,
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
_IndexCallback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint32)


class _Callbacks(ctypes.Structure):
	_fields_ = [
		("pcm", _PcmCallback),
		("index", _IndexCallback),
		("user", ctypes.c_void_p),
	]


class SynthDriver(BaseSynthDriver):
	name = "nokiaNative5320"
	description = "Nokia 5320 Native (experimental)"
	supportedSettings = (BaseSynthDriver.PitchSetting(),)
	supportedCommands = {IndexCommand}
	supportedNotifications = {synthIndexReached, synthDoneSpeaking}

	@classmethod
	def check(cls):
		try:
			root = Path(__file__).resolve().parent.parent
			return (root / "data" / "5320-de-male.snapshot").is_file() and (
				root / "data" / "SYM.ROM"
			).is_file()
		except Exception:
			return False

	def __init__(self):
		self._pitch = 50
		self._root = Path(__file__).resolve().parent.parent
		machine = platform.machine().lower()
		if ctypes.sizeof(ctypes.c_void_p) == 4:
			arch = "x86"
		else:
			arch = "arm64" if machine in {"arm64", "aarch64"} else "x64"
		self._dll = ctypes.CDLL(
			str(self._root / "bin" / arch / f"nokia_runtime_5320_{arch}.dll")
		)
		self._bindApi()
		self._romBytes = (self._root / "data" / "SYM.ROM").read_bytes()
		self._snapshotBytes = (self._root / "data" / "5320-de-male.snapshot").read_bytes()
		self._rom = (ctypes.c_uint8 * len(self._romBytes)).from_buffer_copy(self._romBytes)
		self._snapshot = (ctypes.c_uint8 * len(self._snapshotBytes)).from_buffer_copy(
			self._snapshotBytes
		)
		self._player = nvwave.WavePlayer(
			channels=1,
			samplesPerSec=16000,
			bitsPerSample=16,
			outputDevice=config.conf["audio"]["outputDevice"],
		)
		self._requests: queue.Queue = queue.Queue()
		self._stopEvent = threading.Event()
		self._lock = threading.Lock()
		self._activeRuntime = None
		self._generation = 0
		self._thread = threading.Thread(
			target=self._worker,
			name="NokiaNative5320",
			daemon=True,
		)
		self._thread.start()

	def _bindApi(self):
		self._dll.nokia_runtime_create_5320_snapshot.argtypes = [
			ctypes.POINTER(ctypes.c_uint8),
			ctypes.c_size_t,
			ctypes.POINTER(ctypes.c_uint8),
			ctypes.c_size_t,
		]
		self._dll.nokia_runtime_create_5320_snapshot.restype = ctypes.c_void_p
		self._dll.nokia_runtime_destroy.argtypes = [ctypes.c_void_p]
		self._dll.nokia_runtime_set_pitch.argtypes = [ctypes.c_void_p, ctypes.c_double]
		self._dll.nokia_runtime_set_pitch.restype = ctypes.c_int
		self._dll.nokia_runtime_speak_utf16.argtypes = [
			ctypes.c_void_p,
			ctypes.POINTER(ctypes.c_uint16),
			ctypes.c_uint32,
			ctypes.POINTER(_Callbacks),
		]
		self._dll.nokia_runtime_speak_utf16.restype = ctypes.c_int
		self._dll.nokia_runtime_cancel.argtypes = [ctypes.c_void_p]
		self._dll.nokia_runtime_last_error.argtypes = [ctypes.c_void_p]
		self._dll.nokia_runtime_last_error.restype = ctypes.c_int

	def _get_pitch(self):
		return self._pitch

	def _set_pitch(self, value):
		self._pitch = max(0, min(100, int(value)))

	@staticmethod
	def _pitchFactor(value):
		# 0..100 maps exponentially to the runtime's native 0.5x..2x range.
		return 2.0 ** ((value - 50) / 50.0)

	def speak(self, speechSequence):
		parts = []
		indexes = []
		for item in speechSequence:
			if isinstance(item, str):
				parts.append(item)
			elif isinstance(item, IndexCommand):
				indexes.append(item.index)
		text = "".join(parts)
		if not text:
			for index in indexes:
				synthIndexReached.notify(synth=self, index=index)
			synthDoneSpeaking.notify(synth=self)
			return
		with self._lock:
			generation = self._generation
		self._requests.put((generation, text, tuple(indexes), self._pitch))

	def cancel(self):
		with self._lock:
			self._generation += 1
			runtime = self._activeRuntime
		if runtime:
			self._dll.nokia_runtime_cancel(runtime)
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

	def _worker(self):
		while not self._stopEvent.is_set():
			request = self._requests.get()
			if request is None:
				break
			generation, text, indexes, pitch = request
			with self._lock:
				if generation != self._generation:
					continue
			try:
				self._runUtterance(generation, text, indexes, pitch)
			except Exception:
				log.error("Native Nokia 5320 synthesis failed", exc_info=True)

	def _runUtterance(self, generation, text, indexes, pitch):
		runtime = self._dll.nokia_runtime_create_5320_snapshot(
			self._rom,
			len(self._romBytes),
			self._snapshot,
			len(self._snapshotBytes),
		)
		if not runtime:
			raise RuntimeError("Could not restore the Nokia 5320 native snapshot")
		with self._lock:
			if generation != self._generation:
				self._dll.nokia_runtime_destroy(runtime)
				return
			self._activeRuntime = runtime

		def onPcm(_user, samples, sampleCount, sampleRate):
			if sampleRate != 16000 or generation != self._generation:
				return
			self._player.feed(ctypes.string_at(samples, sampleCount * 2))

		def onIndex(_user, index):
			if generation == self._generation:
				synthIndexReached.notify(synth=self, index=index)

		pcmCallback = _PcmCallback(onPcm)
		indexCallback = _IndexCallback(onIndex)
		callbacks = _Callbacks(pcmCallback, indexCallback, None)
		encoded = text.encode("utf-16-le")
		units = len(encoded) // 2
		textBuffer = (ctypes.c_uint16 * units).from_buffer_copy(encoded)
		try:
			self._dll.nokia_runtime_set_pitch(runtime, self._pitchFactor(pitch))
			ok = self._dll.nokia_runtime_speak_utf16(
				runtime,
				textBuffer,
				units,
				ctypes.byref(callbacks),
			)
			if not ok and generation == self._generation:
				error = self._dll.nokia_runtime_last_error(runtime)
				raise RuntimeError(f"Native runtime error {error}")
			if generation == self._generation:
				for index in indexes:
					synthIndexReached.notify(synth=self, index=index)
				self._player.idle()
				synthDoneSpeaking.notify(synth=self)
		finally:
			with self._lock:
				if self._activeRuntime == runtime:
					self._activeRuntime = None
			self._dll.nokia_runtime_destroy(runtime)
