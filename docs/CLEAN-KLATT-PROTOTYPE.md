# Independent S60 Klatt prototype

`s60Klatt-0.3.0-clean-test3-probe1` is a deliberately separate NVDA add-on. Its
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
male and female. Public reference recordings are used for listening and broad
measurements only. They are not copied into source constants, linked into the
runtime or packaged with the add-on. The measurement record and reproducible
comparison command are in
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
- common digraphs and clusters including `sch`, `ch`, `ng`, `pf`, `sp`,
  `st`, `ei`, `au`, `eu` and `ie`;
- digit spelling and basic sentence pauses;
- deterministic output for repeatable regression tests.

## Deliberate limitations of test 3 probe 1

The test 2 acoustic core is deliberately retained only as an instrumented
candidate while the output-only measurement boundary is established. It is
not a recognizable 5320 reproduction. Probe 1 applies the first directly
observed behavioral result—common punctuation produces no additional pause or
question contour—but does not yet claim corrected phone inventories, stress,
coarticulation or voice quality. Listening during ordinary NVDA navigation
remains the decisive test after later probes replace the acoustic core.

Pure ARM64 is compiled and checked in CI but is not packaged because current
NVDA processes on Windows ARM load the ARM64EC DLL. The add-on packages x86,
x64 and ARM64EC.
