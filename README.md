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

## Current status: compact transition build

The current 0.9 test build is **not yet a native reimplementation of the Nokia
speech engine**.

| Component | Current implementation | Intended final implementation |
|---|---|---|
| NVDA driver and audio streaming | Native NVDA/Python host code | Native NVDA integration |
| Complete phone ROMs | Removed | Not required |
| TTS code and data | Compact address-preserving TTS packs | Data-only voice packages |
| Text analysis and pronunciation | Nokia ARM32 code through Unicorn | Portable native frontend |
| Prosody generation | Nokia ARM32 code through Unicorn | Portable native frontend |
| Klatt/DSP signal generation | Mostly Nokia ARM32 code through Unicorn | Portable C/C++ core |
| Resampling | One hot routine replaced on ARM64 | Portable x64/ARM64 implementation |
| Windows ARM host | Native ARM64 helper process | Native ARM64 library/process |
| Intel/AMD host | In-process x64 Unicorn | Native x64 library/process |

Five full phone ROMs have already been replaced by small `TTS.PAK` files.
These contain only the address-preserving code pages reached by TTS, together
with the external speech-resource files that the engines actually open. This
reduces the add-on from well over 100 MB to roughly 12–17 MB, depending on the
included host runtimes.

### Why version 0.9 is not faster yet

The compact packages remove unrelated phone software, but they do not change
the instructions executed while speaking. Text processing, prosody and most
of the Klatt/DSP work are still ARM32 Symbian machine code executed by
Unicorn.

The ARM64 helper removes an unnecessary x64-to-ARM64 translation layer and
fixes ABI problems, but measurements and listening tests have so far shown no
meaningful improvement in reaction time. That is expected at this stage: the
dominant synthesis workload itself has not yet been ported.

Profiling the Nokia 5320 attributes roughly **85.5% of guest basic-block
executions** for a sentence to one DSP image (UID `0x101f8ca5`). This module
is the main target for native replacement.

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

1. Trace the frame/parameter boundary between Nokia text/prosody processing
   and the hot DSP code.
2. Record parameter frames and reference PCM for automated comparison.
3. Reproduce the 5320 DSP output in portable C or C++.
4. Build the same core for Windows x64 and ARM64.
5. Adapt compatible formats used by the 5500, 6650, 6220, N85 and later C5.
6. Decode or replace the remaining text, phoneme and prosody frontend.
7. Replace `TTS.PAK`, Unicorn and the embedded Python runtime with data-only
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
infrastructure. The next substantial performance milestone is the native
Klatt/DSP core, not another buffering or ROM-compression change.

## Attribution

- Original NVDA experiment: Guillem Leon, `nokiaKlatt 0.5.0`
- Continued porting and packaging: the NOKIATTSNVDA project
- CPU emulation used by transition builds:
  [Unicorn Engine](https://github.com/unicorn-engine/unicorn)

Nokia and Symbian are trademarks of their respective owners.
