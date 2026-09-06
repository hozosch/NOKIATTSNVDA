#!/usr/bin/env python3
"""Build-time smoke test for the standalone 5320 DLL.

Python is only the test harness here. The DLL itself must not import Python or
Unicorn and must synthesize PCM from its native snapshot/AOT path.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import re
import struct
from pathlib import Path

from build_config_pack import read as read_config_pack


class Callbacks(ctypes.Structure):
    pass

PCM = ctypes.CFUNCTYPE(None, ctypes.c_void_p,
                       ctypes.POINTER(ctypes.c_int16), ctypes.c_uint32,
                       ctypes.c_uint32)
INDEX = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint32)
Callbacks._fields_ = [('pcm', PCM), ('index', INDEX), ('user', ctypes.c_void_p)]


def blob_arg(data: bytes):
    array = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
    return array, ctypes.cast(array, ctypes.POINTER(ctypes.c_uint8))


def optional_u32(dll, name):
    fn = getattr(dll, name, None)
    if fn is None:
        return None
    fn.argtypes = []
    fn.restype = ctypes.c_uint32
    return fn


def optional_u64(dll, name):
    fn = getattr(dll, name, None)
    if fn is None:
        return None
    fn.argtypes = []
    fn.restype = ctypes.c_uint64
    return fn


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('dll', type=Path)
    ap.add_argument('rom', type=Path)
    ap.add_argument('snapshot', type=Path)
    ap.add_argument('data_dir', type=Path)
    ap.add_argument('--rom-trace', type=Path)
    args = ap.parse_args()

    dll = ctypes.CDLL(str(args.dll.resolve()))
    dll.nokia_register_config_blob.argtypes = [ctypes.c_uint32, ctypes.c_uint32,
                                                ctypes.c_void_p, ctypes.c_uint32]
    dll.nokia_register_config_blob.restype = ctypes.c_int
    dll.nokia_runtime_create_5320_snapshot.argtypes = [
        ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
    dll.nokia_runtime_create_5320_snapshot.restype = ctypes.c_void_p
    dll.nokia_runtime_speak_utf16.argtypes = [ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint16), ctypes.c_uint32,
        ctypes.POINTER(Callbacks)]
    dll.nokia_runtime_speak_utf16.restype = ctypes.c_int
    dll.nokia_runtime_set_rate.argtypes = [ctypes.c_void_p, ctypes.c_double]
    dll.nokia_runtime_set_rate.restype = ctypes.c_int
    dll.nokia_runtime_last_error.argtypes = [ctypes.c_void_p]
    dll.nokia_runtime_last_error.restype = ctypes.c_int
    dll.nokia_runtime_destroy.argtypes = [ctypes.c_void_p]
    dll.nokia_runtime_text_chunks.argtypes = [ctypes.c_void_p]
    dll.nokia_runtime_text_chunks.restype = ctypes.c_uint32
    dll.nokia_runtime_seam_trimmed_samples.argtypes = [ctypes.c_void_p]
    dll.nokia_runtime_seam_trimmed_samples.restype = ctypes.c_uint32
    dll.nokia_runtime_first_pcm_ticks.argtypes = [ctypes.c_void_p]
    dll.nokia_runtime_first_pcm_ticks.restype = ctypes.c_uint64
    dll.nokia_runtime_rom_trace_reset.argtypes = []
    dll.nokia_runtime_rom_trace_reset.restype = None
    dll.nokia_runtime_rom_trace_page_size.argtypes = []
    dll.nokia_runtime_rom_trace_page_size.restype = ctypes.c_uint32
    dll.nokia_runtime_rom_trace_page_used.argtypes = [ctypes.c_uint32]
    dll.nokia_runtime_rom_trace_page_used.restype = ctypes.c_uint32
    dll.nokia_runtime_rom_trace_touched_pages.argtypes = []
    dll.nokia_runtime_rom_trace_touched_pages.restype = ctypes.c_uint32

    first_unsupported = optional_u32(dll, 'nokia_frontend_first_unsupported_pc_value')
    last_pc = optional_u32(dll, 'nokia_frontend_last_pc_value')
    bad_address = optional_u32(dll, 'nokia_frontend_bad_address_value')
    yield_pc = optional_u32(dll, 'nokia_frontend_yield_pc_value')
    yield_reason = optional_u32(dll, 'nokia_frontend_yield_reason_value')
    yield_count = optional_u64(dll, 'nokia_frontend_yield_count_value')
    debug_values = []
    for label in ('r0','r1','r2','r3','r4','r5','r6','r7','sp',
                  's0','s2','s4','pc'):
        fn = optional_u32(dll, f'nokia_frontend_debug_{label}_value')
        if fn:
            debug_values.append((label, fn))
    klatt_debug_values = []
    for label, export in (
        ('klattLastPc', 'nokia_klatt_last_pc'),
        ('klattLastR0', 'nokia_klatt_last_r0'),
        ('klattLastR7', 'nokia_klatt_last_r7'),
        ('klattBadAddress', 'nokia_klatt_last_bad_address'),
    ):
        fn = optional_u32(dll, export)
        if fn:
            klatt_debug_values.append((label, fn))

    held = []
    if args.data_dir.is_file():
        config_blobs = [
            (type_id, data_id, data, f'srsf_{type_id}_{data_id}.bin')
            for type_id, data_id, data in read_config_pack(args.data_dir)
        ]
    else:
        config_blobs = []
        for path in sorted(args.data_dir.glob('srsf_*_*.bin')):
            match = re.fullmatch(r'srsf_(\d+)_(\d+)\.bin', path.name, re.I)
            if match:
                config_blobs.append((
                    int(match.group(1)), int(match.group(2)),
                    path.read_bytes(), path.name,
                ))
    for type_id, data_id, data, name in config_blobs:
        buf = ctypes.create_string_buffer(data)
        held.append(buf)
        if not dll.nokia_register_config_blob(type_id, data_id,
                                               buf, len(data)):
            raise SystemExit(f'failed registering {name}')
    print('registered config blobs:', len(held))

    rom_data = args.rom.read_bytes()
    snapshot_data = args.snapshot.read_bytes()
    rom_buf, rom_ptr = blob_arg(rom_data)
    snap_buf, snap_ptr = blob_arg(snapshot_data)
    dll.nokia_runtime_rom_trace_reset()

    def create_runtime():
        runtime = dll.nokia_runtime_create_5320_snapshot(
            rom_ptr, len(rom_data), snap_ptr, len(snapshot_data))
        if not runtime:
            raise SystemExit('native snapshot constructor failed')
        return runtime

    samples = [0]
    calls = [0]
    measure_pcm = [False]
    pcm_previous = [0]
    pcm_have_previous = [False]
    pcm_max_delta = [0]
    pcm_max_absolute = [0]
    pcm_clipped = [0]
    pcm_final = [0]
    pcm_position = [0]
    pcm_large_jumps = [0]
    pcm_max_transition = [0, 0, 0]
    pcm_recent = []
    pcm_jump_windows = []
    last_metrics = {}
    @PCM
    def on_pcm(_user, _samples, count, rate):
        if rate != 16000:
            raise RuntimeError(f'unexpected sample rate {rate}')
        if measure_pcm[0]:
            for i in range(count):
                current = int(_samples[i])
                for window in pcm_jump_windows:
                    if len(window[1]) < 17:
                        window[1].append(current)
                pcm_max_absolute[0] = max(pcm_max_absolute[0], abs(current))
                if abs(current) >= 32760:
                    pcm_clipped[0] += 1
                if pcm_have_previous[0]:
                    delta = abs(current - pcm_previous[0])
                    if delta > pcm_max_delta[0]:
                        pcm_max_delta[0] = delta
                        pcm_max_transition[:] = [
                            pcm_position[0], pcm_previous[0], current
                        ]
                    if delta > 32768:
                        pcm_large_jumps[0] += 1
                        pcm_jump_windows.append(
                            (pcm_position[0], list(pcm_recent) + [current])
                        )
                pcm_previous[0] = current
                pcm_have_previous[0] = True
                pcm_final[0] = current
                pcm_position[0] += 1
                pcm_recent.append(current)
                del pcm_recent[:-8]
        samples[0] += int(count)
        calls[0] += 1
    @INDEX
    def on_index(_user, _index):
        pass
    callbacks = Callbacks(on_pcm, on_index, None)

    def speak_case(label: str, value: str, runtime=None,
                   rate: float = 1.0, measure: bool = False) -> int:
        owned_runtime = runtime is None
        if owned_runtime:
            runtime = create_runtime()
        encoded = value.encode('utf-16-le')
        words = (ctypes.c_uint16 * (len(encoded) // 2)).from_buffer_copy(encoded)
        samples_before = samples[0]
        calls_before = calls[0]
        measure_pcm[0] = measure
        pcm_previous[0] = 0
        pcm_have_previous[0] = False
        pcm_max_delta[0] = pcm_max_absolute[0] = pcm_clipped[0] = 0
        pcm_final[0] = 0
        pcm_position[0] = pcm_large_jumps[0] = 0
        pcm_max_transition[:] = [0, 0, 0]
        pcm_recent.clear()
        pcm_jump_windows.clear()
        try:
            if not dll.nokia_runtime_set_rate(runtime, rate):
                raise SystemExit(
                    f'native runtime rejected rate {rate} for {label!r}'
                )
            ok = dll.nokia_runtime_speak_utf16(
                runtime, words, len(words), ctypes.byref(callbacks))
            error = dll.nokia_runtime_last_error(runtime)
            produced = samples[0] - samples_before
            print(
                f'native case {label!r}: result={ok} error={error} '
                f'pcm callbacks={calls[0] - calls_before} samples={produced}'
                + (
                    f' maxDelta={pcm_max_delta[0]} '
                    f'maxAbs={pcm_max_absolute[0]} '
                    f'clipped={pcm_clipped[0]} final={pcm_final[0]} '
                    f'largeJumps={pcm_large_jumps[0]} '
                    f'maxAt={pcm_max_transition[0]} '
                    f'maxPair={pcm_max_transition[1]}:{pcm_max_transition[2]}'
                    if measure else ''
                )
            )
            if not ok or produced <= 0:
                details = ', '.join(
                    f'{name}={fn():#x}' for name, fn in klatt_debug_values
                )
                raise SystemExit(
                    f'native synthesis failed for {label!r}: '
                    f'error={error}, samples={produced}'
                    + (f', {details}' if details else '')
                )
            if measure:
                if pcm_jump_windows:
                    print(f'  wrap windows: {pcm_jump_windows}')
                last_metrics.clear()
                last_metrics.update(
                    max_delta=pcm_max_delta[0],
                    max_absolute=pcm_max_absolute[0],
                    clipped=pcm_clipped[0],
                    final=pcm_final[0],
                    large_jumps=pcm_large_jumps[0],
                )
            return produced
        finally:
            measure_pcm[0] = False
            if owned_runtime:
                dll.nokia_runtime_destroy(runtime)

    # Exercise the letter-name path one character at a time. Embedding the
    # alphabet in a sentence does not use the same Nokia frontend branch and
    # therefore failed to reveal missing compact-ROM pages needed by "H".
    for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ':
        speak_case(f'isolated letter {letter}', letter)
    speak_case('known crash word', 'Einstellungen')
    neutral_rate = speak_case('native rate reference', 'Hallo')
    fast_rate = speak_case('native rate at 2x', 'Hallo', rate=2.0)
    slow_rate = speak_case('native rate at 0.5x', 'Hallo', rate=0.5)
    if not fast_rate < neutral_rate * 0.8:
        raise SystemExit(
            f'native 2x rate did not shorten PCM: neutral={neutral_rate}, '
            f'fast={fast_rate}'
        )
    if not slow_rate > neutral_rate * 1.5:
        raise SystemExit(
            f'native 0.5x rate did not lengthen PCM: neutral={neutral_rate}, '
            f'slow={slow_rate}'
        )
    for click_text in ('egal', 'Egel', 'legen', 'Regen', 'Begegnung', 'e g'):
        speak_case(
            f'high-rate click regression {click_text}', click_text,
            rate=4.0, measure=True,
        )
        if last_metrics['large_jumps']:
            raise SystemExit(
                f'high-rate PCM still contains a signed wrap for {click_text!r}'
            )
        if last_metrics['final'] != 0:
            raise SystemExit(
                f'high-rate PCM does not end at zero for {click_text!r}: '
                f'{last_metrics["final"]}'
            )
    text = (
        'Dies ist der erste Satz und er prueft die schnelle Analyse. '
        'Der zweite Satz muss eine eigene, saubere Intonationskurve erhalten. '
        'Auch der dritte Satz wird innerhalb derselben nativen Engine erzeugt. '
        'Ein vierter Satz macht den Block lang genug fuer die inkrementelle Verarbeitung. '
        'Zum Abschluss prueft dieser Satz, ob die Ausgabe vollstaendig bleibt. '
        'Einstellungen, Geschwindigkeit, Tonhoehe, Sprache, Woerterbuch und Aussprache. '
        'Abfahrt Bahnhof Computer Datei E-Mail Fenster GitHub Hilfe Internet Kalender '
        'Lautstaerke Menue Nokia Optionen Pruefung Quelle Runtime Synthesizer Telefon '
        'Unicode Verbindung Windows Xylophon Ypsilon Zuerich. '
        'Null eins zwei drei vier fuenf sechs sieben acht neun zehn hundert tausend '
        'Komma Punkt Doppelpunkt Bindestrich Klammer Fragezeichen Ausrufezeichen. '
        'Grossbuchstaben ABCDEFGHIJKLMNOPQRSTUVWXYZ und Umlaute Ä Ö Ü ä ö ü ß.'
    )
    # NVDA rate 65 maps to this native factor.  It previously exercised the
    # missing signed-saturation edge at 0x830fa214 in the traced Klatt AOT.
    nvda_rate_65 = 2.0 ** ((65.0 - 50.0) / 25.0)
    speak_case('NVDA rate 65 regression', text, rate=nvda_rate_65)
    speak_case('maximum native rate regression', text, rate=4.0, measure=True)
    if last_metrics['large_jumps'] or last_metrics['final'] != 0:
        raise SystemExit(
            'maximum-rate corpus failed native PCM continuity checks: '
            f'{last_metrics}'
        )
    runtime = create_runtime()
    try:
        speak_case('long German block', text, runtime)
        ok = 1
        error = dll.nokia_runtime_last_error(runtime)
        diagnostics = []
        if first_unsupported:
            diagnostics.append(f'firstUnsupported={first_unsupported():#x}')
        if last_pc:
            diagnostics.append(f'lastPc={last_pc():#x}')
        if bad_address:
            diagnostics.append(f'badAddress={bad_address():#x}')
        if yield_pc:
            diagnostics.append(f'yieldPc={yield_pc():#x}')
        if yield_reason:
            diagnostics.append(f'yieldReason={yield_reason()}')
        if yield_count:
            diagnostics.append(f'yields={yield_count()}')
        for label, fn in debug_values:
            diagnostics.append(f'{label}={fn():#x}')
        chunks = dll.nokia_runtime_text_chunks(runtime)
        seam_trimmed = dll.nokia_runtime_seam_trimmed_samples(runtime)
        first_pcm_ticks = dll.nokia_runtime_first_pcm_ticks(runtime)
        page_size = dll.nokia_runtime_rom_trace_page_size()
        virtual_size = (
            struct.unpack_from('<I', rom_data, 16)[0]
            if len(rom_data) >= 24 and rom_data[:8] == b'NKROMP1\0'
            else len(rom_data)
        )
        total_pages = (virtual_size + page_size - 1) // page_size
        used_pages = [
            page for page in range(total_pages)
            if dll.nokia_runtime_rom_trace_page_used(page)
        ]
        touched_pages = dll.nokia_runtime_rom_trace_touched_pages()
        print('native speak result:', ok, 'error:', error,
              'pcm callbacks:', calls[0], 'samples:', samples[0],
              'text chunks:', chunks,
              'seam samples removed:', seam_trimmed,
              'first PCM ticks:', first_pcm_ticks,
              'ROM pages:', touched_pages, '/', total_pages,
              'ROM bytes:', touched_pages * page_size,
              ' '.join(diagnostics))
        if not ok or samples[0] <= 0:
            raise SystemExit(
                f'native synthesis failed: error={error}, samples={samples[0]}, '
                + ', '.join(diagnostics))
        if chunks < 2:
            raise SystemExit(
                f'long-text synthesis did not segment internally: chunks={chunks}'
            )
        if seam_trimmed == 0:
            raise SystemExit(
                'long-text synthesis removed no silence at internal chunk joins'
            )
        if touched_pages != len(used_pages):
            raise SystemExit(
                f'ROM trace count mismatch: export={touched_pages}, '
                f'enumerated={len(used_pages)}'
            )
        if args.rom_trace:
            ranges = []
            for page in used_pages:
                if ranges and page == ranges[-1][1] + 1:
                    ranges[-1][1] = page
                else:
                    ranges.append([page, page])
            args.rom_trace.parent.mkdir(parents=True, exist_ok=True)
            args.rom_trace.write_text(json.dumps({
                'format': 'nokia-rom-pages-v1',
                'pageSize': page_size,
                'virtualSize': virtual_size,
                'usedPageCount': len(used_pages),
                'usedPages': used_pages,
                'usedRanges': ranges,
            }, indent=2) + '\n', encoding='utf-8')
            print('wrote ROM trace:', args.rom_trace)
    finally:
        dll.nokia_runtime_destroy(runtime)


if __name__ == '__main__':
    main()
