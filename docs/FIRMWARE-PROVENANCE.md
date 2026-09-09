# Firmware and speech-data provenance

Provenance and redistribution permission are separate questions. Identifying
the firmware from which a file came does not itself grant redistribution
rights. Nokia firmware-derived materials are not covered by this project's
GPL-2.0-or-later code license and remain third-party material.

## Nokia 5320 XpressMusic

The compact 5320 code pack used by NOKIATTSNVDA was derived from the ROM
shipped with Guillem Leon's original nokiaKlatt 0.5.0. DJ Graco independently
records that inherited ROM as 69,947,392 bytes with SHA-256
`89c2d9fbbdaa94fca5d8bf49eb512cc82abdc17c97372bca77d700f02bb0d490`.
The exact source firmware of that ROM image has not been proven.

The expanded Test-29 regional speech-data set comes from Nokia 5320
XpressMusic RM-409 firmware 05.16, using native regional variants v01 through
v09. DJ Graco assembled, tested and documented this set in
[`nokiaKlatt 0.5.1`](https://github.com/djgraco/nokiaKlatt). This statement
establishes the origin of the regional speech data, not a claim that the
inherited 0.5.0 ROM was extracted from RM-409 05.16.

## Nokia E65

The Test-66 E65 inputs come from the reconstructed Nokia E65 RM-208 firmware
4.0633.74.00 packaged by
[`joshknnd1982/nokiaklatt-sapi5`](https://github.com/joshknnd1982/nokiaklatt-sapi5)
and documented by DJ Graco. The original 19,013,632-byte `SYM.ROM` has SHA-256
`bee819fd6b20f0d9522f1efe3c994f1d563106f738237a1ac21c4e45d2b520ec`.
The E65 speech device and hardware DLLs reside in ROFS; the build-time tooling
binds them into the traced address space before translating the frontend. The
add-on stores only the observed address-preserving pages and does not contain
that complete firmware image.

## Future source profiles

DJ Graco's repository also documents reconstructed Nokia N95 8GB RM-320
firmware 31.0.015. That model engine requires its own compact extraction,
native validation and provenance inventory before inclusion.

The more detailed source record is available in DJ Graco's
[`ROM-PROVENANCE.md`](https://github.com/djgraco/nokiaKlatt/blob/main/docs/ROM-PROVENANCE.md)
and
[`BINARY-AUDIT.md`](https://github.com/djgraco/nokiaKlatt/blob/main/docs/BINARY-AUDIT.md).
