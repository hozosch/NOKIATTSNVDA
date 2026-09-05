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
    dll.nokia_runtime_last_error.argtypes = [ctypes.c_void_p]
    dll.nokia_runtime_last_error.restype = ctypes.c_int
    dll.nokia_runtime_destroy.argtypes = [ctypes.c_void_p]
    dll.nokia_runtime_text_chunks.argtypes = [ctypes.c_void_p]
    dll.nokia_runtime_text_chunks.restype = ctypes.c_uint32
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

    held = []
    for path in sorted(args.data_dir.glob('srsf_*_*.bin')):
        match = re.fullmatch(r'srsf_(\d+)_(\d+)\.bin', path.name, re.I)
        if not match:
            continue
        data = path.read_bytes()
        buf = ctypes.create_string_buffer(data)
        held.append(buf)
        if not dll.nokia_register_config_blob(int(match.group(1)),
                                               int(match.group(2)),
                                               buf, len(data)):
            raise SystemExit(f'failed registering {path.name}')
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
    @PCM
    def on_pcm(_user, _samples, count, rate):
        if rate != 16000:
            raise RuntimeError(f'unexpected sample rate {rate}')
        samples[0] += int(count)
        calls[0] += 1
    @INDEX
    def on_index(_user, _index):
        pass
    callbacks = Callbacks(on_pcm, on_index, None)

    def speak_case(label: str, value: str, runtime=None) -> None:
        owned_runtime = runtime is None
        if owned_runtime:
            runtime = create_runtime()
        encoded = value.encode('utf-16-le')
        words = (ctypes.c_uint16 * (len(encoded) // 2)).from_buffer_copy(encoded)
        samples_before = samples[0]
        calls_before = calls[0]
        try:
            ok = dll.nokia_runtime_speak_utf16(
                runtime, words, len(words), ctypes.byref(callbacks))
            error = dll.nokia_runtime_last_error(runtime)
            produced = samples[0] - samples_before
            print(
                f'native case {label!r}: result={ok} error={error} '
                f'pcm callbacks={calls[0] - calls_before} samples={produced}'
            )
            if not ok or produced <= 0:
                raise SystemExit(
                    f'native synthesis failed for {label!r}: '
                    f'error={error}, samples={produced}'
                )
        finally:
            if owned_runtime:
                dll.nokia_runtime_destroy(runtime)

    # Exercise the letter-name path one character at a time. Embedding the
    # alphabet in a sentence does not use the same Nokia frontend branch and
    # therefore failed to reveal missing compact-ROM pages needed by "H".
    for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ':
        speak_case(f'isolated letter {letter}', letter)
    speak_case('known crash word', 'Einstellungen')

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
              'text chunks:', chunks, 'first PCM ticks:', first_pcm_ticks,
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
