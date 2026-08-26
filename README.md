# NOKIATTSNVDA

NOKIATTSNVDA is an experimental NVDA synthesizer project based on Guillem
Leon's **nokiaKlatt 0.5.0** add-on, originally announced as
["Nokia TTS on NVDA"](https://dragonscave.space/@guilevi/117146263625498595)
and distributed from
[guilevi.me](https://guilevi.me/nokiaKlatt-0.5.0.nvda-addon).

That project demonstrated that the ARM32 speech engines from Nokia S60 phones
can be driven by NVDA through a small Symbian compatibility harness. This
repository continues that work. It is an independent preservation and
porting experiment and is not an official Nokia project.

## Project goal

The goal is not to ship a complete phone emulator. The intended result is a
small, responsive NVDA synthesizer that:

- preserves the characteristic Nokia pronunciation, prosody and formant voices;
- executes the time-critical Klatt/DSP synthesis path as native Windows code;
- supports both Intel/AMD x64 and Windows ARM64;
- eventually needs no Symbian ROM, ARM32 emulation, Unicorn or embedded Python;
- starts producing audio with screen-reader-friendly latency;
- cancels reliably during rapid navigation;
- loads languages and voices from separate, manifest-driven data packages;
- permits compatible language data and independently defined voices to be
  added without rebuilding the complete add-on.

Faithful output matters: replacing the engine with an unrelated generic Klatt
synthesizer would be fast, but would not necessarily retain the Nokia sound.
The emulated engine is therefore kept as a reference while the native
implementation is developed and compared against its parameters and PCM.

## Current status: accelerated hybrid build

Version 0.12 is the first accelerated hybrid build. It is **not yet a fully
native reimplementation of the Nokia speech engine**.

| Component | Current implementation | Intended final implementation |
|---|---|---|
| NVDA driver and audio streaming | Native NVDA/Python host code | Native NVDA integration |
| Complete phone ROMs | Removed | Not required |
| TTS code and data | Compact address-preserving TTS packs | Data-only voice packages |
| Text analysis and pronunciation | Nokia ARM32 code through Unicorn | Portable native frontend |
| Prosody generation | Nokia ARM32 code through Unicorn | Portable native frontend |
| Klatt waveform generation | Bit-exact native x64/ARM64 code for all five bundled families | Portable native core |
| Resampling and rate conversion | Native x64/ARM64; rate remains pitch-preserving post-processing | Native parameter timing |
| Windows ARM host | Native ARM64 helper process | Native ARM64 library/process |
| Intel/AMD host | In-process x64 Unicorn | Native x64 library/process |

Five full phone ROMs have already been replaced by small `TTS.PAK` files.
These contain only the address-preserving code pages reached by TTS, together
with the external speech-resource files that the engines actually open. This
reduces the add-on from well over 100 MB to roughly 12–17 MB, depending on the
included host runtimes.

### First native performance milestone

The complete shared Klatt waveform-generator frame routine has now been
reconstructed as portable C and built as native Windows x64 and ARM64 code for
the 5320, 5500, 6650, 6220 and N85 families. End-to-end reference tests remain
PCM-identical and report no ARM fallback. The full 5320 reference sentence is
about 1.4 times faster locally.

Nokia text analysis, pronunciation and prosody preparation still execute as
ARM32 code through Unicorn. Because most preparation for a short utterance
happens before its first synthesis frame, some first-audio latency remains.
That frontend is the next major performance target.

Speaking-rate conversion now executes inside the same native library rather
than Python. It preserves pitch and is deliberately described as native audio
processing, not as a reconstructed Nokia prosody control: the frontend still
creates frames at its natural durations.

Profiling the Nokia 5320 attributes roughly **85.5% of guest basic-block
executions** for a sentence to one DSP image (UID `0x101f8ca5`). This module
is the main target for native replacement.

## DSP trace and frame-capture builds

Version 0.10 adds an explicit profiler for locating the boundary that the
native Klatt/DSP implementation must replace. It is completely disabled during
ordinary speech and therefore adds no runtime hook overhead unless requested.

Open NVDA's Python console with NVDA+Control+Z and run:

```python
from synthDrivers._nokia import bench
bench.trace()
```

The trace records:

- executed ARM basic blocks by ROM image;
- likely DSP function calls and their ARM argument registers;
- DSP activity observed before each PCM buffer reaches NVDA;
- whether the existing native resampler accelerator is active.

A much slower memory-write trace is available when needed:

```python
bench.trace(deep=True)
```

The summary is printed and written to NVDA's log. The complete structured
report is saved as `nokiaTTS-dsp-trace.json` in NVDA's configuration
directory. All profiling hooks are removed immediately after the test
utterance.

The trace is a diagnostic milestone, not a performance improvement by itself.
Its purpose is to identify stable parameters and hot routines that can be
reimplemented and tested as native x64/ARM64 code. Version 0.11 added the
complete parameter/state/PCM frame capture; version 0.12 is the first build to
use the resulting native generator.

## Voices and languages

The current compact build combines five working engine families:

- Nokia 5320
- Nokia 5500
- Nokia 6650
- Nokia 6220
- Nokia N85

Together they provide 27 model/language variants covering 23 distinct
languages. Italian and Turkish were present in the available speech data but
were missing from the earlier profile list; both have now been verified on
the Nokia 5320 and Nokia 6220 with male and female voices.

Other variants, such as French from the Nokia C5 family, require matching C5
TTS data before they can be analysed and packaged. Data from a different
phone is not silently substituted, because engine and resource versions may
not be compatible.

## Native-port roadmap

1. Keep native generator output bit-exact across all supported voices.
2. Port the preparation path responsible for latency before the first frame.
3. Decode or replace the remaining text, phoneme and prosody frontend.
4. Add compatible formats used by later families such as the C5 when matching
   TTS data is available.
5. Replace `TTS.PAK`, Unicorn and the embedded Python runtime with data-only
   voice packages once the native implementation matches the reference.

A release should only be described as fully native once the ARM32 guest path
is no longer required for normal synthesis. The emulator must not remain a
silent fallback in a release advertised as ROM-independent.

## Planned voice-package format

The intended layout is model-independent and manifest-driven:

```text
voices/<package-id>/
  manifest.json
  text-rules.bin
  voice-data.bin
  prosody.bin
```

During the transition, Nokia-compatible packages may additionally require a
compact code pack. In the final architecture, voice packages should contain
speech data only.

## Repository scope

At present this repository contains experimental build and porting work,
including native Windows ARM/x64 dependencies and the transition add-on
infrastructure. The native Klatt frame generator is now implemented; the next
substantial performance milestone is the pre-frame text/prosody path, not
another buffering or ROM-compression change.

## Attribution

- Original NVDA experiment: Guillem Leon, `nokiaKlatt 0.5.0`
- Continued porting and packaging: the NOKIATTSNVDA project
- CPU emulation used by transition builds:
  [Unicorn Engine](https://github.com/unicorn-engine/unicorn)

Nokia and Symbian are trademarks of their respective owners.
