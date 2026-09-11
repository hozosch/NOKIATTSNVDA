# Independent Classic Klatt prototype

`classicKlatt-0.1.0-clean-test1` is a deliberately separate NVDA add-on. Its
package name, driver name and user-facing product name are **Classic Klatt**.
Historical Nokia S60 speech is a listening and behaviour reference, not a
claim of origin, endorsement or binary compatibility.

## Source boundary

The prototype contains only newly written source/filter synthesis and German
pronunciation code. Its build reads only:

- `native/clean/classic_klatt.c` and `.h`;
- `addonClean/manifest.ini`;
- `addonClean/synthDrivers/classicKlatt.py`.

It does not read or package a firmware image, compact ROM page pack, generated
AOT source, extracted configuration blob, voice snapshot or original speech
data. CI rejects those file types if they appear inside `addonClean` or the
staged add-on.

The prototype currently offers two independent German voices: male and
female. They are initial generic classic-phone formant profiles, not yet a
validated reproduction of a particular historical model.

## Implemented behaviour

- 16 kHz mono streaming PCM;
- synchronous native C synthesis behind NVDA's worker thread;
- cancellation between short PCM blocks;
- NVDA rate, pitch and voice settings;
- German letter spelling and uppercase acronym spelling;
- German vowels and umlauts;
- common digraphs and clusters including `sch`, `ch`, `ng`, `pf`, `sp`,
  `st`, `ei`, `au`, `eu` and `ie`;
- digit spelling and basic sentence pauses;
- deterministic output for repeatable regression tests.

## Deliberate limitations of test 1

This is an audible architecture test, not yet a Nokia-model replacement.
Stress, compound analysis, loanwords, number expansion, punctuation naming,
coarticulation and consonant quality remain deliberately small. The first
listening task is to determine whether the source, formant filtering and
male/female pitch ranges are a useful foundation before the German rule set
and model profiles are expanded.

Pure ARM64 is compiled and checked in CI but is not packaged because current
NVDA processes on Windows ARM load the ARM64EC DLL. The add-on packages x86,
x64 and ARM64EC.
