# NOKIATTSNVDA

NOKIATTSNVDA is the current working name of an experimental, cross-interface
Nokia TTS preservation and native-porting project. NVDA is the first supported
interface; SAPI5 and Android integrations are planned on top of the same core.
The project is based on Guillem Leon's **nokiaKlatt 0.5.0** add-on, originally announced as
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
- supports Windows x86, x64 and ARM64EC in the NVDA add-on;
- needs no complete Symbian ROM, ARM32 emulator, Unicorn or embedded Python at runtime;
- starts producing audio with screen-reader-friendly latency;
- cancels reliably during rapid navigation;
- loads languages and voices from separate, manifest-driven data packages;
- permits compatible language data and independently defined voices to be
  added without rebuilding the complete add-on.

Faithful output matters: replacing the engine with an unrelated generic Klatt
synthesizer would be fast, but would not necessarily retain the Nokia sound.
The emulated engine is therefore kept as a reference while the native
implementation is developed and compared against its parameters and PCM.

## Current status: native-only Test 75 candidate

Normal synthesis now runs entirely in compiled Windows DLLs. Unicorn remains a
development-time reference for capturing and validating new phone profiles,
but it is not shipped and is never used as a runtime fallback.

| Component | Current implementation | Next target |
|---|---|---|
| Interfaces | NVDA synth driver | SAPI5 and Android on the shared core |
| Complete phone ROMs | Removed | Remain unnecessary |
| Runtime TTS code | Small address-preserving code-page packs | Eventually data-only voice packages |
| Text analysis and pronunciation | Original Nokia logic lifted to portable C | Optimise verified hot loops, then progressively decode it |
| Prosody and Klatt synthesis | Native duration/F0 control and bit-exact portable C | Preserve exact output across every added model |
| Architectures | Packaged x86, x64 and ARM64EC DLLs; pure ARM64 remains CI-tested | Add pure ARM64 when NVDA can load it directly |
| Volume | Not yet exposed | Compare streaming PCM gain with any usable native control |

Rate is applied to Nokia's phoneme durations and prosody timelines before
waveform generation; pitch scales the per-frame F0 parameter. Neither control
post-processes completed audio. The reverse-engineering evidence is recorded
in [`docs/NATIVE-PROSODY-CONTROLS.md`](docs/NATIVE-PROSODY-CONTROLS.md).

Test 70 reduced 5320 first-audio latency by replacing three fully verified
Prime/iterator loops with direct C while retaining byte-identical PCM. Further
long-text work will follow the same rule: optimise measured frontend hot loops,
without lowering the existing very-long-text chunk threshold or introducing
extra buffering.

## Voices and languages

The source tree preserves native Klatt waveform cores labelled for six engine
families:

- Nokia 5320
- Nokia 5500
- Nokia E65
- Nokia 6650
- Nokia 6220 Classic
- Nokia N85

The Test 75 candidate exposes the 5320, 5500, E65, 6650 and N85 end to end.
The native tree currently has only the 6220 Klatt core. Guillem Leon's original
0.5.0 reference package identifies the matching profile as Nokia 6220 Classic
and contains its `6220c.rom` image and speech data; its frontend, compact
runtime pack and snapshots still need to be captured for the native add-on.

The expanded SAPI5 reference repository provides most of the following device
inventory. The 5500 and 6220 Classic come from the original NVDA collection
instead because that SAPI5 package does not contain them.

| Model | Languages | Voices | Native NVDA status |
|---|---:|---:|---|
| Nokia 5320 XpressMusic | 33 | 66 | complete |
| Nokia 5500 | 5 | 5 | complete |
| Nokia E65 | 30 | 30 | complete |
| Nokia 6650 Fold | 4 | 8 | Test 75 candidate; broad text corpus passes |
| Nokia 6220 Classic | 5 | 10 | original reference recovered; native port pending |
| Nokia N85 | 2 | 4 | Test 75 candidate; broad text corpus passes |
| Nokia N95 8GB | 30 | 30 | planned; separate engine build |

The recovered [`nokiaKlatt 0.5.0`](https://guilevi.me/nokiaKlatt-0.5.0.nvda-addon)
profile labels the source consistently as Nokia 6220 Classic and supplies
Swedish, Danish, Norwegian, Finnish and Icelandic with male and female styles.
Its complete British-English package faults the original emulated engine and
is deliberately not offered. The precise RM variant and firmware version are
not yet established from an internal version record, so those narrower claims
remain open even though the source profile is no longer missing.

The 5320 and E65 language lists already match the SAPI5 inventory exactly.
The packaged 5500 resources also confirm that its five-language set—British
English, French, German, Spanish and Arabic—is complete; no hidden 5500
language was omitted.

The N85 data tree also contains a complete language-ID 1 (British English)
package, but the SAPI5 reference deliberately blocks it because it faults the
original emulated engine. It is therefore not counted as an available N85
language and is not exposed as a voice.

Test 29 expanded the Nokia 5320 from 9 to 33 verified languages using the
native RM-409 05.16 regional data preserved and documented by DJ Graco in
[`djgraco/nokiaKlatt`](https://github.com/djgraco/nokiaKlatt). The set includes
Dutch, Portuguese, Czech, Slovak, Polish, Slovenian, Croatian, Estonian,
Greek, Hebrew, Latvian, Lithuanian, Serbian, Catalan, Basque and Galician in
addition to the previously bundled 5320 languages. All 33 have been verified
with complete synthesis, non-zero PCM and both distinct Nokia voice variants.

The native-only Test 66 build exposed that complete set directly through NVDA:
33 Nokia 5320 languages with `DefaultMale` and `DefaultFemale`, plus the Nokia
5500's single standard voice in British English, French, German, Spanish and
Arabic, and the E65's single standard voice in 30 languages. This gives 101
selectable voices across 33 languages. NVDA groups voices by language and then
by model, so the Nokia 5500 and E65 variants follow the two Nokia 5320 variants
for shared languages. Voice
snapshots are loaded on demand and only the active one remains in memory.
The verified frontend AOT, Klatt AOT and snapshots for all three models are frozen;
ordinary add-on builds compile them directly rather than recapturing the
expensive AOT corpora.

Test 63 adds the bounded Nokia 5500 frontend paths required for isolated-letter
synthesis, including distinct uppercase and lowercase routes, and uncommon
lookup/initialization outcomes such as the reported yield at `0xF8451E9A`. It
also restores a two-instruction Klatt fallthrough used by accented Spanish
words. The established 5320 and high-rate PCM paths remain unchanged.

Test 64 closes the reported Nokia 5500 Thumb fallthroughs at `0xF844FCB6` and
`0xF8450FAC`. It also maps only whitespace-delimited French `Ä`, `Ö` and `Ü`
tokens to the lowercase spellings accepted by the original 5500 frontend;
ordinary mixed-case words remain unchanged. The regression suite exercises
embedded underscores and the isolated French and Arabic letter combinations.

Test 65 matches the original Nokia engine's text boundary by removing only
leading and trailing whitespace before native synthesis. Interior spacing and
the complete one-call utterance are preserved. This closes the reported Nokia
5500 ARM64EC yield at `0xF8453C0C`; regression coverage includes spaces,
tabs and line endings in all five 5500 languages. It also adds the missing
German frontend continuation at `0xF844F330`, verified with the complete
reported `Administrator_berechtigungen` sentence.

Test 66 adds the missing Nokia 5500 German frontend instruction at
`0xF8451E3E`, closing the reported `$SysReset` folder-name path without changing
the input text. It also adds the Nokia E65 engine from the reconstructed
[`nokiaklatt-sapi5`](https://github.com/joshknnd1982/nokiaklatt-sapi5)
profile: all 30 available languages, one standard male-labelled voice per
language, and native x86, x64, ARM64 and ARM64EC runtimes. Reference sentences
are PCM-identical for all 30 voices; 1,559 reference-accepted isolated ASCII
letters and all 30 high-rate cases also pass. The 19 MB source firmware is not
packaged: its observed TTS pages are stored in an address-preserving core of
about 373 KB.

Test 67 closes the reported E65 ARM64EC continuation at `0xF840064C` and the
additional frontend and Klatt paths exercised by the long saved-settings and
runtime-error messages. The same long runtime-error regression is covered on
the Nokia 5500. Because the Nokia 5320 set has no CJK voice, unsupported CJK
spans are now removed before they reach its original frontend: surrounding
supported text is still spoken, while an all-CJK utterance succeeds silently.
This behavior is verified with every one of the 66 packaged 5320 snapshots.

Test 68 adds the original Arabic frontend branches used when Latin text is
submitted to the Nokia 5500 or E65 voice. It includes the reported E65
ARM64EC instruction at `0xF83FEC32`; no text substitution or language-specific
runtime shortcut is used. Both Arabic voices are tested with Latin words and
the complete reported runtime-error message.

Test 69 stores all 101 packaged voice snapshots as deterministic gzip streams
and decompresses only the selected voice into the existing runtime buffer.
Uncompressed snapshot data fall from 219,727,056 to 398,770 installed bytes;
the complete local add-on footprint falls from about 273 MB to about 54 MB.
The driver still accepts unpacked snapshots for compatibility.

Test 70 reduces Nokia 5320 time to first audio by collapsing two verified
Prime iterator loops and a fixed-stride helper into direct C. In local x64
A/B measurements, the median first PCM callback for the reported German menu
phrase falls from about 40.6 ms to 31.0 ms; a longer German settings sentence
falls from 70.6 ms to 54.0 ms. The complete PCM output remains bit-identical,
and all 66 multilingual 5320 voices plus their regression samples pass.

Test 71 adds the Nokia 6650 Fold in US English, Canadian French, Brazilian
Portuguese and Latin American Spanish, with distinct `DefaultMale` and
`DefaultFemale` voices. All eight snapshots pass two consecutive calls on one
runtime with PCM hashes identical to the reference. All eight also pass a third
call on that same runtime after changing rate and pitch; this covers the Klatt
pitch-clamp branch not reached by neutral reference frames. Its 47,448,064-byte
ROM is represented by a 377,224-byte compact page pack. Together, the NVDA
add-on now offers 109 voices across 37 languages.

Test 72 adds the Nokia N85 in Tagalog and Vietnamese, again with distinct
`DefaultMale` and `DefaultFemale` voices. All four snapshots pass two
consecutive calls on one runtime with reference-identical PCM, followed by a
third call with changed rate and pitch. The lifted single-threaded
`LDREX`/`STREX` helper is represented as a deterministic successful store,
closing the only loop that could otherwise wait forever without an emulated
exclusive monitor. The original 43,237,376-byte ROM is reduced to a 352,624-byte
address-preserving page pack. The add-on now offers 113 voices across 39
languages.

No complete firmware ROM is added. The expanded build uses compact,
address-preserving code packs for the 5320, 5500, E65, 6650 and N85 and adds
only the required speech data.
The SAPI5 reference also contains a working Nokia N95 8GB profile with 30
languages. It uses another distinct Nokia engine build and therefore still
requires separate compact-pack and native-port validation rather than being
silently substituted as 5320 or E65 data.

Test 73 closes the missing original frontend paths exposed when German NVDA
interface labels are sent to the 6650 or N85 voices. All eight 6650 and all
four N85 voices now synthesize the three separate `NVDA Menü`,
`Optionen Untermenü` and `Werkzeuge Untermenü` regression utterances in
addition to retaining their reference-identical PCM hashes. The NVDA package
no longer duplicates the five
model runtimes as pure ARM64 DLLs: ARM64EC is the runtime selected by the NVDA
processes targeted on Windows ARM. Pure ARM64 builds and smoke tests remain in
CI for future native-ARM64 NVDA support.

Test 74 replaces that narrow three-phrase check with 48 practical utterances
per voice: NVDA and Windows interface labels, role announcements, letters,
numbers, punctuation, paths, identifiers, long settings text, a runtime-error
message and native-language sentences with diacritics. Against the Test 73
sources this found 278 failing cases on the eight 6650 voices and 162 on the
four N85 voices. The missing original-ROM frontend and Klatt paths are now
included; all 576 broad-corpus syntheses pass on x64 locally, and the existing
repeated-call PCM hashes remain byte-identical. CI repeats the complete corpus
on x64, ARM64EC and pure ARM64.

Test 75 adds the two complete 736/738-character runtime-error reports to the
regression corpus and closes the newly exposed original frontend paths at
`0x82A5B454` on the 6650 and `0x82047EB0` on the N85. It also restores the
N85 slow-executive default and the saved `Dll::Tls` locale object used by the
original engine. All eight 6650 voices retain their reference PCM hashes, and
the complete corpus passes in US English, Canadian French, Brazilian
Portuguese and Latin American Spanish. All four N85 voices likewise retain
their hashes and pass in Tagalog and Vietnamese. The Vietnamese analyser has a
smaller native token workspace for dense diagnostic strings, so only text with
repeated assignment fields or hexadecimal values uses a conservative
128-unit boundary; ordinary long prose keeps the existing 384-unit chunk
limit. The compact 6650 and N85 ROM packs remain byte-identical to Test 74.

Other variants, such as French from the Nokia C5 family, require matching C5
TTS data before they can be analysed and packaged. Data from a different
phone is not silently substituted, because engine and resource versions may
not be compatible.

## Native-port roadmap

1. Finish and stabilize every verified phone profile, next N95 8GB, while
   retaining exact reference PCM; then port the recovered 6220 Classic
   reference with its five working Nordic languages.
2. Profile longer ordinary utterances and replace only verified hot frontend
   loops. Do not use smaller text chunks as a latency shortcut.
3. Add volume control after comparing streaming PCM gain against any usable
   engine-native path. The SAPI5 investigation found that the public Symbian
   `iVolume` style field rejects values other than 100, so incremental PCM gain
   is currently the more promising design and need not buffer whole utterances.
4. Separate the reusable synthesis core from the NVDA adapter, then add SAPI5
   and Android interfaces.
5. Progressively decode or replace the remaining instruction-shaped text,
   phoneme and prosody frontend and move toward data-only voice packages.

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

At present this repository contains the reusable native runtime, reference and
regression tooling, Windows builds, compact model data and the first NVDA
adapter. The repository will be renamed once a final interface-neutral project
name is chosen; changing the GitHub name before that decision would only create
avoidable churn. NVDA remains the first supported frontend after the rename.

## Attribution

- Original NVDA experiment and recovered Nokia 6220 Classic reference:
  Guillem Leon,
  [`nokiaKlatt 0.5.0`](https://guilevi.me/nokiaKlatt-0.5.0.nvda-addon)
- Expanded RM-409 language collection, E65/N95 8GB reconstruction and detailed
  firmware provenance: DJ Graco,
  [`nokiaKlatt 0.5.1`](https://github.com/djgraco/nokiaKlatt). Many thanks for
  preserving, testing and documenting these difficult-to-find Nokia speech
  resources.
- SAPI5 packaging used for the expanded five-phone model/language inventory
  and as the E65, 6650, N85 and N95 8GB reference source:
  [`joshknnd1982/nokiaklatt-sapi5`](https://github.com/joshknnd1982/nokiaklatt-sapi5)
- Continued porting and packaging: the NOKIATTSNVDA project
- CPU emulation used by transition builds:
  [Unicorn Engine](https://github.com/unicorn-engine/unicorn)

Project code and documentation are GPL-2.0-or-later unless stated otherwise.
Nokia firmware-derived speech data are not relicensed by that GPL and remain
third-party material. Known origin and confidence boundaries are documented in
[`docs/FIRMWARE-PROVENANCE.md`](docs/FIRMWARE-PROVENANCE.md).

Nokia and Symbian are trademarks of their respective owners. This project is
not affiliated with or endorsed by Nokia, HMD Global or NV Access.
