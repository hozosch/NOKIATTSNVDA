# Nokia model native-port roadmap

This document keeps the Unicorn-removal work model-independent.  The 5320 is
the first standalone-native frontend target because it already has the largest
AOT corpus, but the runtime boundaries should be reusable by the other Nokia
Klatt engine generations preserved by DJ Graco.

## Current and upstream profiles

| Profile | Phone / platform | Upstream status | Native-port implication |
|---|---|---|---|
| `5320` | Nokia 5320 XpressMusic, Symbian 9.3 FP2 | 33 verified languages, male/female | Primary frontend-AOT target. Existing 14k+ instruction corpus and native Klatt core. |
| `6650` | Nokia 6650 Fold, Symbian 9.3 FP2 | 4 verified languages, male/female | Closest runtime generation to 5320. Reuse host ABI, allocator, executive and observer work; generate a profile-specific frontend corpus. |
| `n85` | Nokia N85, Symbian 9.3 FP2 | Tagalog/Vietnamese verified, male/female | Same broad EKA2 generation as 5320. Good second/third frontend-AOT target after 6650. |
| `e65` | Nokia E65, Symbian 9.1 | 30 verified languages, unnamed/default voice | Speech DLLs live in ROFS and are loaded by the harness' minimal E32 loader. Standalone runtime needs a native E32/ROFS image loader boundary and the older EKA2 executive ABI. |
| `n958gb` | Nokia N95 8GB RM-320, Symbian 9.2 FP1 | 30 verified languages, unnamed/default voice | Uses a reconstructed XIP image and VFP/DFPAEABI on the English path. AOT tooling must preserve VFP helper semantics or replace those helpers natively. |
| `n95` | Nokia N95 Chinese-market build | Test harness speaks; NVDA path unreliable | Keep as an experimental validation target. A standalone native runtime may remove the current harness/NVDA discrepancy. |
| `e5` | Nokia E5-00, Symbian 9.3 | Does not start in current harness | Speech devices are ECOM plugins. Requires a minimal native ECOM resolver/loader before frontend porting is useful. |
| `5800` | Nokia 5800 XpressMusic, Symbian 9.4 | Does not start in current harness | Different euser/executive surface hangs during construction. A standalone host ABI should avoid copying 9.3-specific euser assumptions. |

The upstream profile facts above are taken from `djgraco/nokiaKlatt` 0.5.1.
Firmware-derived binaries remain third-party preservation material and are not
relicensed by this project's GPL code.

## Runtime layers to make reusable

The native implementation should not hard-code the 5320 wherever the phone
family only changes data or addresses.  The following boundaries should become
profile descriptors or callbacks:

1. ROM / compact-code-pack base and image table.
2. EUser / executive ABI generation (9.1, 9.2, 9.3/9.4).
3. Heap and cleanup-stack bootstrap.
4. File/resource lookup for SRSF/TTP/TTS/prosody packages.
5. DevTTS observer callbacks: configuration data, events and PCM buffers.
6. Frontend entry points and AOT corpus.
7. Klatt frame entry and profile-specific bit-exact native generator.
8. Optional VFP/DFPAEABI helpers (notably N95 8GB).
9. Optional E32/ROFS and ECOM image loading.

## Suggested order

1. **5320:** remove every normal-synthesis Unicorn yield and add a standalone
   native frontend host. Keep Unicorn only as an explicit reference/debug mode.
2. **6650 + N85:** generate frontend traces/AOT using the same host ABI. Their
   existing native Klatt cores make them the lowest-risk proof that the runtime
   is truly model-independent.
3. **E65:** implement the Symbian 9.1/E32-loader differences and port its
   frontend. Its 30-language set makes this high value.
4. **N95 8GB:** add the 9.2/VFP helper layer and port its frontend. This adds a
   second 30-language engine generation with a distinct sound.
5. Revisit **N95**, then implement the missing **E5 ECOM** and **5800 9.4 euser**
   boundaries.

## Definition of "Unicorn-free"

A profile is Unicorn-free only when normal NVDA synthesis can initialize the
engine, normalize/parse text, prime prosody, generate PCM, service observer
callbacks, change rate/pitch, cancel between native work units and shut down
without creating or executing a Unicorn CPU instance.  Unicorn may remain as
an optional reference verifier during development, but must not be a silent
fallback in a build advertised as native.
