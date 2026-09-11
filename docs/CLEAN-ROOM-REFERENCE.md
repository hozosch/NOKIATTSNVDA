# Independent reference measurement record

This document records the external observations used for S60 Klatt clean test
2. It is an engineering provenance record, not a legal conclusion.

## Reference boundary

The active measurement path accepts only output from a separately operated
reference installation that the operator is entitled to use. No particular
internet copy, ROM download or third-party redistribution is endorsed as a
lawful source. Public CI does not obtain or run a historical renderer.

The fixed German comparison text is:

> Guten Tag, ich bin die Nokia Klatt Sprachausgabe und ich spreche Deutsch.

Reference WAVs are created in a temporary local directory, are not committed
or packaged, and are erased immediately after aggregate analysis.

## Legacy measurements used in test 2

These figures document why the broad test-2 method was inadequate. They are not
an active fitting input and do not establish that the historical source from
which they were once measured was licensed for redistribution.

Measurements were taken from 16 kHz mono output. RMS covers the complete
utterance. F0 is the median detected fundamental over voiced frames. The band
columns are percentages of spectral energy from a 1024-sample Welch estimate
with 50% overlap.

| Output | Duration | Peak | RMS | 0–500 Hz | 500–1000 Hz | 1–2 kHz | 2–4 kHz | 4–8 kHz | Median F0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Historical 5320 male output | 4.400 s | −6.2 dBFS | −22.3 dBFS | 63.3% | 25.3% | 8.0% | 3.2% | 0.2% | 115.9 Hz |
| Clean test 2 male | 4.396 s | −5.2 dBFS | −22.2 dBFS | 66.9% | 24.5% | 6.9% | 1.4% | 0.3% | 116.8 Hz |
| Historical 5320 female output | 4.650 s | −7.9 dBFS | −21.3 dBFS | 52.2% | 40.5% | 6.3% | 0.9% | 0.1% | 205.1 Hz |
| Clean test 2 female | 4.646 s | −6.9 dBFS | −22.2 dBFS | 59.1% | 33.9% | 5.8% | 1.0% | 0.2% | 205.1 Hz |

The figures guided high-level choices such as pitch range, duration scale,
formant emphasis and source balance. They are not copied engine parameters and
do not prove a perceptual match. In particular, the female 500–1000 Hz balance
and both voices' 2–4 kHz energy still differ from the references.

For this one German sentence, the observed N95 8GB WAV was byte-identical to
the observed 5320 male WAV. This does not establish that the two
models share an engine or behave identically on other text, languages or
voices.

## Reproducing a clean-core render

After compiling `native/clean/classic_klatt.c` as a shared library, render the
same text without NVDA using:

```console
python tools/render_clean_klatt_wav.py ./libclassic_klatt.so output.wav \
  "Guten Tag, ich bin die Nokia Klatt Sprachausgabe und ich spreche Deutsch."
```

Use `--voice female` for the female profile. The renderer calls only the public
clean-core API and writes 16-bit, 16 kHz mono PCM.
