# Output-only S60 black-box measurements

Test 2 showed that similar whole-utterance duration, F0 and spectral-band
figures do not establish a recognizable historical S60 voice. Test 3 therefore
starts with a reproducible, language-separated measurement boundary before any
new synthesis parameters are fitted.

## Boundary

The historical renderer is treated as a separate process with exactly three
observable elements:

1. self-authored input text;
2. success or failure;
3. 16 kHz mono PCM output.

The capture tool does not import reference implementation code, inspect its
memory, request internal phoneme or Klatt frames, or copy parameter tables. It
does not make the legal provenance of a particular reference installation
lawful by itself; the person running it still needs to be entitled to use that
installation.

German Copyright Act sections
[`69a(2)`](https://www.gesetze-im-internet.de/urhg/__69a.html) and
[`69d(3)`](https://www.gesetze-im-internet.de/urhg/__69d.html) distinguish a
program's protected expression from underlying ideas and permit a person
entitled to use a program copy to observe, study or test its functioning while
performing authorized acts. This record is an engineering boundary, not legal
advice. It deliberately does not rely on the narrower decompilation rule in
[`69e`](https://www.gesetze-im-internet.de/urhg/__69e.html).

Reference WAVs are transient measurement inputs. The local wrapper creates
them below an operating-system temporary directory and erases them after the
aggregate report has been written. No reference PCM, firmware, snapshot or
reference executable is placed in the independent add-on.

## Language separation

Finnish is useful because its mature historical frontend and comparatively
regular orthography make controlled contrasts easier. It is not treated as a
universal phonetic model. German, British English, French and Italian are
probed separately because their historical S60 frontends use different phone
inventories, contextual realizations and stress behavior.

The corpus contains 175 cases across those five languages. It includes:

- punctuation versus plain spaces, plus punctuation without surrounding space;
- vowel inventories and length contrasts;
- isolated German stops, fricatives and sonorants plus liquid contexts,
  including `l` in several positions;
- weak endings, diphthongs and consonant length where applicable;
- German `ch`, `sch`, `sp`/`st`, affricate, `ng`, final-devoicing, vocalic-`r`
  and weak-vowel rules;
- compounds, stress probes and short as well as longer intonation phrases;
- German digit behavior.

The acoustic and prosody subset separates short vowel carriers, `l` in
multiple vowel contexts, one-word contours, growing phrases and short
sentences. These are intentionally measured per language; Finnish remains a
control rather than a template for German, English, French or Italian.

All corpus text in `tools/s60_blackbox_corpus.json` was written for this test;
it is not extracted from firmware resources or dictionaries.

## Running an authorized external reference locally

The public GitHub workflow validates only the newly written tools. It does not
download a ROM, historical executable, emulator or third-party reference
package. Reference comparison is an explicit local operation. The wrapper
requires the operator to confirm that the supplied installation may be used:

```console
python tools/run_s60_blackbox_local.py \
  --reference-renderer C:\path\to\nk_render.exe \
  --rom C:\path\to\5320\SYM.ROM \
  --data-tree C:\path\to\5320\files \
  --candidate-dll C:\path\to\classic_klatt_x64.dll \
  --output s60-blackbox-5320-male.json \
  --phone-profile-output s60-phones-5320-de-male.json \
  --confirm-authorized-reference
```

On Linux, an already installed Python reference package can be kept behind the
same process boundary with the small adapter below. It contains and copies no
reference implementation; the named directory and its Unicorn dependency stay
outside the independent project:

```console
export S60_REFERENCE_DRIVER_DIR=/path/to/installed/addon/synthDrivers
python tools/run_s60_blackbox_local.py \
  --reference-renderer tools/render_authorized_s60_reference.py \
  --rom /path/to/5320/SYM.ROM \
  --data-tree /path/to/5320/files \
  --candidate-dll ./libclassic_klatt.so \
  --output s60-blackbox-5320-male.json \
  --phone-profile-output s60-phones-5320-de-male.json \
  --confirm-authorized-reference
```

`--language de-DE` is the default. A previous aggregate report becomes a
release baseline with `--baseline-report old-report.json --enforce-gate`.
The optional phone profile contains only aggregate output-derived measurements
for the 28 labelled German vowel, stop, fricative, sonorant and liquid probes.
It stores no PCM or internal reference state and is intended as the target for
a later independently authored data-driven renderer.

On Linux, an already installed and authorized Python reference package can be
placed behind the same separate-process interface without copying it into this
repository. Set `S60_REFERENCE_DRIVER_DIR` to the directory containing its
`_nokia` package, then supply `tools/render_authorized_s60_reference.py` as the
reference renderer. The helper contains no emulator, ROM or speech data.

Once the aggregate profile exists, fitting no longer invokes the historical
renderer or needs its WAV output:

```console
python tools/fit_clean_klatt_phone_profile.py \
  s60-phones-5320-de-male.json \
  --output clean-klatt-phone-fit.json
```

Each trial compiles only the independent core and renders the 28 self-authored
probe strings. Stored spectrum, cepstrum, source-mixture, periodicity, pulse
shape, F0 and duration targets rank candidates before the full release gate.

Candidates improving the phone-weighted non-punctuation score by less than 15
percent are rejected before listening. Even when the combined score improves,
the gate remains closed unless the isolated-phone score improves by the same
threshold. Clearing the gate only makes a build eligible for a short listening
check; it does not establish perceptual identity.

For a single already captured and authorized output-only WAV, the independent
core can be searched without invoking any historical runtime:

```console
python tools/fit_clean_klatt_profile.py reference.wav \
  "Guten Tag, ich bin die Nokia Klatt Sprachausgabe und ich spreche Deutsch." \
  --confirm-authorized-reference --baseline-score 71.354 \
  --output clean-klatt-fit.json
```

The fitter compiles only `native/clean/classic_klatt.c`, varies newly authored
acoustic constants, renders transient candidate PCM and deletes its temporary
libraries and audio buffers. It accepts neither firmware nor a runtime binary.
Its JSON records the reference PCM hash, deterministic seed, exact candidate
constants and known limitations; it never embeds reference PCM or local frame
features. A one-utterance result must still be checked against the wider corpus
and by listening.

## Current analysis

`tools/analyze_s60_blackbox.py` measures utterance length, active boundaries,
internal quiet intervals, RMS, peak level and zero-crossing density. It now
also derives a 24-point F0 contour, F0 range and periodicity, a 25 Hz-spaced
spectral envelope through 5 kHz, spectral tilt, coarse spectral bands and
three regional resonance peaks. A second, transient analysis aligns 30 ms
frames with dynamic time warping after discarding only leading and trailing
padding. It measures framewise spectral shape, spectral transitions, voicing
decisions, F0 in cents, periodicity, unvoiced high-band energy, spectral flux
and regional resonance trajectories. The JSON report deliberately omits PCM
hashes, raw sample envelopes, frame feature sequences and all audio.

The reference renderer's roughly 60–80 ms output padding is recorded as a
measurement artifact, not reproduced by the independent runtime. Preserving
immediate first audio for screen-reader use takes priority over matching file
boundaries that do not change phonemes, spectral character or intonation.

Metric version 2 also derives an eight-coefficient cepstral description of the
spectral envelope plus crest factor and first-difference energy for the source
pulse. Controlled phone probes are compared in their phone-bearing window,
with a separate penalty for confusing quiet, periodic and aperiodic source
mixtures. These measures address the failure mode where whole-word duration,
pitch and energy looked closer while the perceived phones and timbre did not.

The objective gate excludes punctuation because matching it can conceal badly
wrong phones. It is designed to spare the listener from small, unpromising
iterations. Reports made with earlier metric versions cannot be used as a
baseline; both baseline and candidate must be regenerated. Separate language
frontends must still be fitted against controlled contrasts rather than against
rules for linguistically ideal pronunciation.
