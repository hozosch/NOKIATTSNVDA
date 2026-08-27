# Native Nokia prosody controls

This note records the evidence behind the Test 30 rate and pitch controls. It
distinguishes parameter-domain control from the PCM time scaling used by
earlier transition builds.

## Klatt frame pitch

The shared waveform generator receives a 122-byte parameter frame. The signed
16-bit field at offset `0x18` is F0 in tenths of a hertz:

- German `DefaultMale`: approximately 950–1320 (95–132 Hz)
- German `DefaultFemale`: approximately 1720–2290 (172–229 Hz)

Scaling this field before the native Klatt generator changes measured pitch
without changing the number of frames or output samples. A sustained German
test produced approximately 54/105/213 Hz for male factors 0.5/1/2 and
95/188/377 Hz for female factors 0.5/1/2. This is excitation-frequency
control, not PCM resampling.

The female voice is not merely the male voice with a larger F0. Nokia also
selects different timbre constants, formant trajectories and durations. The
pitch setting intentionally scales the chosen voice's own F0 trajectory rather
than attempting to interpolate the complete male and female voice definitions.

## PrimeSynthesisL duration object

After `PrimeSynthesisL`, one guest object describes phoneme durations and two
prosody control curves. The relevant fields are:

| Offset | Type | Meaning |
|---:|---|---|
| `0x00` | `uint16` | phoneme/duration count |
| `0x02` | `uint16` | pitch point count |
| `0x04` | `uint16` | amplitude point count |
| `0x08` | pointer | phoneme identifiers |
| `0x0c` | pointer | signed 16-bit phoneme durations |
| `0x10` | pointer | signed 16-bit F0 control values |
| `0x14` | pointer | signed 16-bit F0 time positions |
| `0x1c` | pointer | signed 16-bit amplitude control values |
| `0x20` | pointer | signed 16-bit amplitude time positions |

The two previously reconstructed helpers at guest addresses corresponding to
`0x830ffaa2` and `0x830ffafe` update the same time-position arrays. The native
rate control runs once after Prime and scales the duration array plus both time
axes by the inverse rate factor. It leaves the F0 and amplitude values alone.
Monotonic control points remain monotonic after integer rounding.

For short utterances that do not call either helper, the bridge locates the
same validated object in the active guest heap by its counts, six in-range
array pointers, positive duration values, plausible F0 data and monotonic time
axes.

## Validation

At neutral rate and pitch, the Test 30 candidate matched the ARM reference PCM
byte-for-byte on the 5320, 5500, 6650, 6220 and N85 families. Changing rate,
pitch and then returning both to neutral restored the original PCM hash on
both German 5320 named voices.

Examples from local end-to-end tests:

| Input | Rate 0.5 | Rate 1 | Rate 2 | Rate 4 |
|---|---:|---:|---:|---:|
| German 5320, `Hallo` | 0.90 s | 0.45 s | 0.25 s | 0.15 s |
| German 5320 reference sentence | 5.90 s | 3.00 s | 1.50 s | 0.80 s |

The fixed start/end material and minimum one-unit phoneme durations explain
why very short text does not scale perfectly linearly at the highest rates.

These controls do not make the complete engine native. Text normalization,
pronunciation, most prosody planning and scheduler control still use the
ARM32 reference through Unicorn until their AOT/native ports are complete.
