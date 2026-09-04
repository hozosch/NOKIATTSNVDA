"""Experimental in-process NVDA driver for the native-only Nokia 5320 runtime."""

from __future__ import annotations

import ctypes
import os
import queue
import re
import struct
import sys
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
		arch = self._getProcessArchitecture()
		dllPath = self._root / "bin" / arch / f"nokia_runtime_5320_{arch}.dll"
		self._arch = arch
		self._dllPath = dllPath
		try:
			self._dll = ctypes.CDLL(str(dllPath))
		except OSError as error:
			raise OSError(
				f"Could not load the {arch} Nokia runtime for this NVDA process: {dllPath}; "
				f"original loader error: {error!r}; winerror={getattr(error, 'winerror', None)}"
			) from error
		self._bindApi()
		self._registerConfigBlobs()
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

	@staticmethod
	def _getProcessArchitecture():
		"""Return the architecture of NVDA itself, not that of the host OS."""
		# ARM64EC and ARM64X are deliberately distinguished from pure ARM64:
		# they use the x64-compatible ABI and cannot load a plain ARM64 DLL.
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
		# Final ARM64EC images intentionally use the AMD64 PE machine value.
		# A native ARM process with an AMD64 image is therefore ARM64EC;
		# an emulated x64 process reports AMD64 in processMachine instead.
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
		self._dll.nokia_register_config_blob.argtypes = [
			ctypes.c_uint32,
			ctypes.c_uint32,
			ctypes.c_void_p,
			ctypes.c_uint32,
		]
		self._dll.nokia_register_config_blob.restype = ctypes.c_int
		self._dll.nokia_clear_config_blobs.argtypes = []
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
		for export in (
			"nokia_runtime_klatt_failure",
			"nokia_runtime_klatt_count",
			"nokia_runtime_klatt_gain",
		):
			function = getattr(self._dll, export)
			function.argtypes = [ctypes.c_void_p]
			function.restype = ctypes.c_uint32
		self._dll.nokia_runtime_klatt_reg.argtypes = [
			ctypes.c_void_p,
			ctypes.c_uint32,
		]
		self._dll.nokia_runtime_klatt_reg.restype = ctypes.c_uint32
		self._diagnosticFunctions = {}
		for label, export in (
			("klattLastPc", "nokia_klatt_last_pc"),
			("klattLastR0", "nokia_klatt_last_r0"),
			("klattLastR7", "nokia_klatt_last_r7"),
			("klattBadAddress", "nokia_klatt_last_bad_address"),
			("failedLastPc", "nokia_runtime_failed_last_pc_value"),
			("failedPc", "nokia_runtime_failed_pc_value"),
			("failedLr", "nokia_runtime_failed_lr_value"),
			("failedSp", "nokia_runtime_failed_sp_value"),
			("failedFlags", "nokia_runtime_failed_cpsr_value"),
			("failedBadAddress", "nokia_runtime_failed_bad_address_value"),
			("failedYieldPc", "nokia_runtime_failed_yield_pc_value"),
			("failedYieldReason", "nokia_runtime_failed_yield_reason_value"),
			("failedEntry", "nokia_runtime_last_entry_value"),
			("failedStage", "nokia_runtime_last_stage_value"),
			("finalLastPc", "nokia_frontend_last_pc_value"),
			("finalBadAddress", "nokia_frontend_bad_address_value"),
			("finalYieldPc", "nokia_frontend_yield_pc_value"),
			("finalYieldReason", "nokia_frontend_yield_reason_value"),
		):
			function = getattr(self._dll, export, None)
			if function:
				function.argtypes = []
				function.restype = ctypes.c_uint32
				self._diagnosticFunctions[label] = function

	def _registerConfigBlobs(self):
		count = 0
		for path in sorted((self._root / "data" / "config").glob("srsf_*_*.bin")):
			match = re.fullmatch(r"srsf_(\d+)_(\d+)\.bin", path.name, re.IGNORECASE)
			if not match:
				continue
			data = path.read_bytes()
			buffer = ctypes.create_string_buffer(data)
			if not self._dll.nokia_register_config_blob(
				int(match.group(1)),
				int(match.group(2)),
				buffer,
				len(data),
			):
				raise RuntimeError(f"Could not register Nokia configuration {path.name}")
			count += 1
		if not count:
			raise RuntimeError("No Nokia srsf configuration blobs were packaged")

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
		self._dll.nokia_clear_config_blobs()

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
				klattDiagnostics = [
					f"klattFailure=0x{self._dll.nokia_runtime_klatt_failure(runtime):08x}",
					*(
						f"klattR{label}=0x{self._dll.nokia_runtime_klatt_reg(runtime, index):08x}"
						for index, label in enumerate(("0", "1", "2", "3", "Sp"))
					),
					f"klattCount=0x{self._dll.nokia_runtime_klatt_count(runtime):08x}",
					f"klattGain=0x{self._dll.nokia_runtime_klatt_gain(runtime):08x}",
				]
				diagnostics = ", ".join([
					f"runtimeArch={self._arch}",
					f"runtimeDll={self._dllPath.name}",
					*klattDiagnostics,
					*(
						f"{label}=0x{function():08x}"
						for label, function in self._diagnosticFunctions.items()
					),
				])
				raise RuntimeError(
					f"Native runtime error {error}"
					+ (f"; {diagnostics}" if diagnostics else "")
				)
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
