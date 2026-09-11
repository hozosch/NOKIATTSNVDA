# Independent S60 Klatt prototype

`s60Klatt-0.5.0-clean-test5` is a deliberately separate NVDA add-on. Its
package name, driver name and user-facing product name are **S60 Klatt**.
Its explicit goal is to recreate the pronunciation behaviour, prosody and
acoustic character of the historical Nokia S60 TTS systems through newly
authored code and independently measured voice profiles. Those systems are
listening and behaviour references, not a claim of origin, endorsement or
binary compatibility.

## Source boundary

The prototype contains only newly written source/filter synthesis and German
pronunciation code. Its build reads only:

- `native/clean/classic_klatt.c` and `.h`;
- `addonClean/manifest.ini`;
- `addonClean/synthDrivers/s60Klatt.py`.

It does not read or package a firmware image, compact ROM page pack, generated
AOT source, extracted configuration blob, voice snapshot or original speech
data. CI rejects those file types if they appear inside `addonClean` or the
staged add-on.

The prototype currently offers two independent German 5320-targeted voices:
male and female. Output from a separately and lawfully operated reference may
be used for local black-box measurements only. It is not copied into source
constants, linked into the runtime or packaged with the add-on. Public CI does
not fetch a historical renderer, firmware or reference audio. The measurement
record and reproducible local comparison command are in
[`CLEAN-ROOM-REFERENCE.md`](CLEAN-ROOM-REFERENCE.md).

## Implemented behaviour

- 16 kHz mono streaming PCM;
- synchronous native C synthesis behind NVDA's worker thread;
- cancellation between short PCM blocks;
- NVDA rate, pitch and voice settings;
- separate 5320-targeted male and female F0, duration, formant and spectral
  profiles;
- five resonators with continuous envelopes across adjacent voiced phonemes;
- German letter spelling and uppercase acronym spelling;
- German short and long vowels, umlauts, final devoicing and vocalic `r`;
- common punctuation does not add pauses or a question contour, matching the
  first output-only 5320 probes;
- a mostly level multiword F0 plateau followed by a late phrase-final fall,
  fitted to authorized German 5320 male output; the female contour remains
  separate until it has an equally strong output-only fit;
- a vowel-specific parallel-filter balance fitted to output-only spectral
  measurements without adding the reference renderer's start padding;
- common digraphs and clusters including `sch`, `ch`, `ng`, `pf`, `sp`,
  `st`, `ei`, `au`, `eu` and `ie`;
- digit spelling and punctuation-neutral word separation;
- deterministic output for repeatable regression tests.

## Test 5 source-character experiment

Listening showed that test 4's lower feature score did not correspond to a
recognizable historical voice: its voiced excitation was too sharp and its
unvoiced consonants sounded like broad, steady noise. Test 5 therefore changes
the synthesis mechanism rather than refitting the same whole-utterance score.
It blends the abrupt glottal return with a continuously closing synthetic flow
pulse, applies a small one-pole source tilt, narrows only unvoiced formant
bandwidths and makes deterministic frication more pulse-like.

An LPC residual diagnostic on the fixed German sentence changes median source
kurtosis from about 88 in test 4 to about 35, versus about 39 in the authorized
reference. Median residual crest factor changes from about 13.5 to 10.4,
versus about 9.8 in the reference. Median unvoiced-frame level moves from about
-24.8 dB relative to the utterance maximum to about -20.0 dB, matching the
reference's approximately -20.0 dB while using less broadband excitation.

The existing local feature score becomes worse (59.817 to about 61.8), even
though F0 error and regional resonance deltas improve. This is intentionally a
listening candidate, not a numeric fidelity claim; test 4 demonstrated that
the old aggregate score underweights the voice-source character.

DECtalk was considered because its formant-synthesis timbre is perceptually
relevant. The publicly visible DECtalk 4.63 source repository has no open-source
license, and its vocal-tract source labels itself confidential and proprietary,
so none of that code or its data is used here. A generic cascade path was also
tested locally but rejected because making it audible increased the measured
distance. Test 5 remains newly authored source/filter code under the existing
clean boundary.

## Test 4 measurement result and limitations

Test 4 replaces word-local pitch resets with a measured German 5320 male phrase
plateau and late final fall. Its glottal timing, formant scaling, vowel,
sonorant and noise balance, transitions and stop release were searched against
time-local features from an authorized output-only recording. On the fixed
German sentence, the local feature score falls from 71.354 to 59.817: a 16.2%
improvement, clearing the predeclared 15% gate for a listening candidate.

Across 31 previously measured German probes, whole-utterance spectral distance
falls by about 9.7%, spectral-centroid error by about 45%, and absolute duration
error by about 40%. The coarse 24-bin F0 error across those probes is about 9%
worse, while time-aligned F0 error on the fixed sentence improves. This mixed
result is why test 4 is a listening candidate rather than a fidelity claim.
Pronunciation rules, individual phones, stress, coarticulation and female voice
quality remain incomplete.

Pure ARM64 is compiled and checked in CI but is not packaged because current
NVDA processes on Windows ARM load the ARM64EC DLL. The add-on packages x86,
x64 and ARM64EC.
