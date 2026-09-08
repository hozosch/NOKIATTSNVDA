"""Experimental in-process NVDA driver for the native-only Nokia 5320 runtime."""

from __future__ import annotations

import ctypes
import os
import queue
import re
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
_IndexCallback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint32)


# Languages present in the Nokia 5320 EMEA/Hispania configuration set.
# The numeric values are Symbian TLanguage identifiers and also form part of
# the stable voice IDs stored by NVDA.
_LANGUAGES = (
	(1, "English (UK)", "en_GB"),
	(2, "French", "fr_FR"),
	(3, "German", "de_DE"),
	(4, "Spanish", "es_ES"),
	(5, "Italian", "it_IT"),
	(6, "Swedish", "sv_SE"),
	(7, "Danish", "da_DK"),
	(8, "Norwegian", "nb_NO"),
	(9, "Finnish", "fi_FI"),
	(13, "Portuguese", "pt_PT"),
	(14, "Turkish", "tr_TR"),
	(15, "Icelandic", "is_IS"),
	(16, "Russian", "ru_RU"),
	(17, "Hungarian", "hu_HU"),
	(18, "Dutch", "nl_NL"),
	(25, "Czech", "cs_CZ"),
	(26, "Slovak", "sk_SK"),
	(27, "Polish", "pl_PL"),
	(28, "Slovenian", "sl_SI"),
	(37, "Arabic", "ar"),
	(42, "Bulgarian", "bg_BG"),
	(44, "Catalan", "ca_ES"),
	(45, "Croatian", "hr_HR"),
	(49, "Estonian", "et_EE"),
	(54, "Greek", "el_GR"),
	(57, "Hebrew", "he_IL"),
	(67, "Latvian", "lv_LV"),
	(68, "Lithuanian", "lt_LT"),
	(78, "Romanian", "ro_RO"),
	(79, "Serbian", "sr_RS"),
	(93, "Ukrainian", "uk_UA"),
	(401, "Basque", "eu_ES"),
	(402, "Galician", "gl_ES"),
)
_GENDERS = ("male", "female")
_DEFAULT_VOICE = "5320:3-male"


def _voiceId(languageId, gender):
	return f"5320:{languageId}-{gender}"


class _Callbacks(ctypes.Structure):
	_fields_ = [
		("pcm", _PcmCallback),
		("index", _IndexCallback),
		("user", ctypes.c_void_p),
	]


class SynthDriver(BaseSynthDriver):
	name = "nokiaNative5320"
	description = "Nokia 5320 Native (experimental)"
	# The Nokia engine leaves useful silence around short utterances.  Keeping
	# those utterances in one WavePlayer feed avoids opening or refilling the
	# output stream in the middle of a word-initial plosive.
	UTTERANCE_OVERHEAD = 0.35
	CHARS_PER_SECOND = 20.0
	WHOLE_BUFFER_MAX_NORMAL_SECONDS = 0.85
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
			data = root / "data"
			return (
				(data / "5320-3-male.snapshot").is_file()
				or (data / "5320-de-male.snapshot").is_file()
			) and (
				(root / "data" / "5320-core.nrp").is_file()
				or (root / "data" / "SYM.ROM").is_file()
			)
		except Exception:
			return False

	def __init__(self):
		self._rate = 50
		self._pitch = 50
		self._root = Path(__file__).resolve().parent.parent
		self._voiceSnapshots = self._findVoiceSnapshots()
		if not self._voiceSnapshots:
			raise RuntimeError("No Nokia 5320 native voice snapshots were packaged")
		self._voices = self._buildVoiceList()
		self._voice = (
			_DEFAULT_VOICE
			if _DEFAULT_VOICE in self._voices
			else next(iter(self._voices))
		)
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
		romPath = self._root / "data" / "5320-core.nrp"
		if not romPath.is_file():
			romPath = self._root / "data" / "SYM.ROM"
		self._romBytes = romPath.read_bytes()
		self._rom = (ctypes.c_uint8 * len(self._romBytes)).from_buffer_copy(self._romBytes)
		# Voice snapshots are about 2 MiB each. Cache only the selected one;
		# loading all 66 would need roughly 140 MiB for almost no latency gain.
		self._snapshotVoice = None
		self._snapshotBytes = None
		self._snapshot = None
		# Preserve Test43's first-utterance behaviour: prepare the default voice
		# during driver startup, while later voice changes remain lazy.
		self._loadSnapshot(self._voice)
		self._player = self._makePlayer()
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

	def _makePlayer(self):
		player = nvwave.WavePlayer(
			channels=1,
			samplesPerSec=16000,
			bitsPerSample=16,
			outputDevice=config.conf["audio"]["outputDevice"],
		)
		# Nokia already supplies roughly 80 ms of leading silence.  NVDA's
		# default trimming can otherwise wake the device on the first consonant,
		# which is heard intermittently as a click even though the PCM is clean.
		try:
			player.enableTrimmingLeadingSilence(False)
		except Exception:
			log.error(
				"Could not preserve Nokia leading silence",
				exc_info=True,
			)
		return player

	@classmethod
	def _wholeBufferUtterance(cls, runs):
		normalSeconds = sum(
			cls.UTTERANCE_OVERHEAD + len(text) / cls.CHARS_PER_SECOND
			for text, _pitchFactor in runs
		)
		return normalSeconds <= cls.WHOLE_BUFFER_MAX_NORMAL_SECONDS

	def _findVoiceSnapshots(self):
		data = self._root / "data"
		paths = {}
		for languageId, _name, _locale in _LANGUAGES:
			for gender in _GENDERS:
				voiceId = _voiceId(languageId, gender)
				path = data / f"5320-{languageId}-{gender}.snapshot"
				# Accept Test43's original filename as a compatibility fallback.
				if languageId == 3 and gender == "male" and not path.is_file():
					path = data / "5320-de-male.snapshot"
				if path.is_file():
					paths[voiceId] = path
		return paths

	def _buildVoiceList(self):
		voices = OrderedDict()
		self._voiceLocales = {}
		for languageId, name, locale in sorted(_LANGUAGES, key=lambda row: row[1]):
			for gender in _GENDERS:
				voiceId = _voiceId(languageId, gender)
				if voiceId in self._voiceSnapshots:
					self._voiceLocales[voiceId] = locale
					voices[voiceId] = VoiceInfo(
						voiceId,
						f"{name} {gender} (Nokia 5320)",
						locale,
					)
		return voices

	def _loadSnapshot(self, voiceId):
		if voiceId != self._snapshotVoice:
			path = self._voiceSnapshots.get(voiceId)
			if path is None:
				raise RuntimeError(f"Nokia 5320 voice snapshot is unavailable: {voiceId}")
			self._snapshotBytes = path.read_bytes()
			self._snapshot = (
				ctypes.c_uint8 * len(self._snapshotBytes)
			).from_buffer_copy(self._snapshotBytes)
			self._snapshotVoice = voiceId
		return self._snapshot, len(self._snapshotBytes)

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
		self._dll.nokia_runtime_set_rate.argtypes = [ctypes.c_void_p, ctypes.c_double]
		self._dll.nokia_runtime_set_rate.restype = ctypes.c_int
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
		for typeId, dataId, data, name in self._iterConfigBlobs():
			buffer = ctypes.create_string_buffer(data)
			if not self._dll.nokia_register_config_blob(
				typeId,
				dataId,
				buffer,
				len(data),
			):
				raise RuntimeError(f"Could not register Nokia configuration {name}")
			count += 1
		if not count:
			raise RuntimeError("No Nokia srsf configuration blobs were packaged")

	def _iterConfigBlobs(self):
		packPath = self._root / "data" / "5320-config.ncf"
		if not packPath.is_file():
			for path in sorted((self._root / "data" / "config").glob("srsf_*_*.bin")):
				match = re.fullmatch(r"srsf_(\d+)_(\d+)\.bin", path.name, re.IGNORECASE)
				if match:
					yield int(match.group(1)), int(match.group(2)), path.read_bytes(), path.name
			return
		raw = packPath.read_bytes()
		header = struct.Struct("<8sIIII")
		entry = struct.Struct("<III")
		blob = struct.Struct("<II")
		if len(raw) < header.size:
			raise RuntimeError("Nokia configuration pack is truncated")
		magic, version, entryCount, blobCount, payloadOffset = header.unpack_from(raw)
		tableEnd = header.size + entryCount * entry.size + blobCount * blob.size
		if magic != b"NKCFGP1\0" or version != 1 or payloadOffset != tableEnd or tableEnd > len(raw):
			raise RuntimeError("Nokia configuration pack is invalid")
		blobs = [
			blob.unpack_from(raw, header.size + entryCount * entry.size + index * blob.size)
			for index in range(blobCount)
		]
		for index in range(entryCount):
			typeId, dataId, blobIndex = entry.unpack_from(raw, header.size + index * entry.size)
			if blobIndex >= blobCount:
				raise RuntimeError("Nokia configuration pack contains an invalid reference")
			offset, size = blobs[blobIndex]
			start = payloadOffset + offset
			end = start + size
			if start < payloadOffset or end > len(raw):
				raise RuntimeError("Nokia configuration pack contains an invalid payload")
			yield typeId, dataId, raw[start:end], f"srsf_{typeId}_{dataId}.bin"

	def _get_pitch(self):
		return self._pitch

	def _set_pitch(self, value):
		self._pitch = max(0, min(100, int(value)))

	def _get_rate(self):
		return self._rate

	def _set_rate(self, value):
		self._rate = max(0, min(100, int(value)))

	def _get_availableVoices(self):
		return self._voices

	def _get_voice(self):
		return self._voice

	def _set_voice(self, value):
		if value in self._voices:
			self._voice = value

	def _get_language(self):
		return self._voiceLocales.get(self._voice)

	@staticmethod
	def _rateFactor(value):
		# Match the useful range of the former hybrid driver: every 25 slider
		# points doubles or halves duration, capped at 0.4x..4x.
		return max(0.4, min(4.0, 2.0 ** ((value - 50) / 25.0)))

	@staticmethod
	def _pitchFactor(value):
		# 0..100 maps exponentially to the runtime's native 0.5x..2x range.
		return 2.0 ** ((value - 50) / 50.0)

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
				runs.append((text, self._pitchFactor(currentPitch)))

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
			voiceId = self._voice
			self._requests.put((
				generation,
				voiceId,
				tuple(runs),
				tuple(indexes),
				self._rateFactor(self._rate),
			))

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
			generation, voiceId, runs, indexes, rateFactor = request
			with self._lock:
				if generation != self._generation:
					continue
			try:
				self._runUtterance(
					generation,
					voiceId,
					runs,
					indexes,
					rateFactor,
				)
			except Exception:
				log.error("Native Nokia 5320 synthesis failed", exc_info=True)

	def _runUtterance(self, generation, voiceId, runs, indexes, rateFactor):
		snapshot, snapshotSize = self._loadSnapshot(voiceId)
		runtime = self._dll.nokia_runtime_create_5320_snapshot(
			self._rom,
			len(self._romBytes),
			snapshot,
			snapshotSize,
		)
		if not runtime:
			raise RuntimeError("Could not restore the Nokia 5320 native snapshot")
		with self._lock:
			if generation != self._generation:
				self._dll.nokia_runtime_destroy(runtime)
				return
			self._activeRuntime = runtime

		# Short words are produced quickly and fit comfortably in memory.  Feed
		# each of them as one continuous block, matching the proven Unicorn
		# driver's playback path without touching Nokia's waveform.
		bufferedPcm = bytearray() if self._wholeBufferUtterance(runs) else None

		def onPcm(_user, samples, sampleCount, sampleRate):
			if sampleRate != 16000 or generation != self._generation:
				return
			pcm = ctypes.string_at(samples, sampleCount * 2)
			if bufferedPcm is not None:
				bufferedPcm.extend(pcm)
			else:
				self._player.feed(pcm)

		def onIndex(_user, index):
			if generation == self._generation:
				synthIndexReached.notify(synth=self, index=index)

		pcmCallback = _PcmCallback(onPcm)
		indexCallback = _IndexCallback(onIndex)
		callbacks = _Callbacks(pcmCallback, indexCallback, None)
		try:
			if not self._dll.nokia_runtime_set_rate(runtime, rateFactor):
				raise RuntimeError("Native runtime rejected rate change")
			for text, pitchFactor in runs:
				if generation != self._generation:
					return
				encoded = text.encode("utf-16-le")
				units = len(encoded) // 2
				textBuffer = (ctypes.c_uint16 * units).from_buffer_copy(encoded)
				if not self._dll.nokia_runtime_set_pitch(runtime, pitchFactor):
					raise RuntimeError("Native runtime rejected pitch change")
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
				if bufferedPcm:
					self._player.feed(bytes(bufferedPcm))
				for index in indexes:
					synthIndexReached.notify(synth=self, index=index)
				self._player.idle()
				synthDoneSpeaking.notify(synth=self)
		finally:
			with self._lock:
				if self._activeRuntime == runtime:
					self._activeRuntime = None
			self._dll.nokia_runtime_destroy(runtime)
