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
lawful by itself; the person running it still needs a lawful basis to use that
installation.

Reference WAVs are transient measurement inputs. `reference-output/` is
ignored by Git, and CI removes all captured WAVs before publishing its report.
No reference PCM, firmware, snapshot or reference executable is placed in the
independent add-on.

## Language separation

Finnish is useful because its mature historical frontend and comparatively
regular orthography make controlled contrasts easier. It is not treated as a
universal phonetic model. German, British English, French and Italian are
probed separately because their historical S60 frontends use different phone
inventories, contextual realizations and stress behavior.

The corpus contains 147 cases across those five languages. It includes:

- punctuation versus plain spaces, plus punctuation without surrounding space;
- vowel inventories and length contrasts;
- consonant and liquid contexts, including `l` in several positions;
- weak endings, diphthongs and consonant length where applicable;
- compounds, stress probes and a short sentence;
- German digit behavior.

The acoustic and prosody subset separates short vowel carriers, `l` in
multiple vowel contexts, one-word contours, growing phrases and short
sentences. These are intentionally measured per language; Finnish remains a
control rather than a template for German, English, French or Italian.

All corpus text in `tools/s60_blackbox_corpus.json` was written for this test;
it is not extracted from firmware resources or dictionaries.

## Capturing the external reference

The current adapter drives the public command-line boundary of `nk_render`:

```console
python tools/capture_s60_blackbox.py \
  --backend nk-render \
  --renderer C:\path\to\nk_render.exe \
  --rom C:\path\to\5320\SYM.ROM \
  --data-tree C:\path\to\5320\files \
  --voice male \
  --output-dir reference-output\5320-male \
  --jobs 4
```

`--language de-DE` can restrict a capture to one frontend. The corresponding
independent German candidate is captured through its public DLL API:

```console
python tools/capture_s60_blackbox.py \
  --backend clean-core \
  --renderer C:\path\to\classic_klatt_x64.dll \
  --language de-DE \
  --voice male \
  --output-dir reference-output\candidate-de
```

Existing output is never overwritten unless `--force` is supplied.

## Current analysis

`tools/analyze_s60_blackbox.py` measures utterance length, active boundaries,
internal quiet intervals, RMS, peak level and zero-crossing density. It now
also derives a 24-point F0 contour, F0 range and periodicity, a 25 Hz-spaced
spectral envelope through 5 kHz, spectral tilt, coarse spectral bands and
three regional resonance peaks. Candidate comparisons summarize the duration,
F0-contour and spectrum errors by probe group. Explicit contrast pairs also
report whether their PCM is identical. The JSON report deliberately omits PCM
hashes, raw sample envelopes and all audio.

This first stage is sufficient to establish behavior such as whether a comma
or period changes the waveform or inserts a pause. It does not yet identify a
phone sequence. Subsequent stages will add time-local formant, excitation and
noise measurements and will fit separate language frontends against controlled
contrasts rather than against rules for linguistically ideal pronunciation.
