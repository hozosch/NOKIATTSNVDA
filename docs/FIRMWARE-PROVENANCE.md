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

## Future source profiles

DJ Graco's repository also documents reconstructed Nokia E65 RM-208 firmware
4.0633.74.00 and Nokia N95 8GB RM-320 firmware 31.0.015. These model engines
are not part of Test 29. They require their own compact extraction, native
validation and provenance inventory before inclusion.

The more detailed source record is available in DJ Graco's
[`ROM-PROVENANCE.md`](https://github.com/djgraco/nokiaKlatt/blob/main/docs/ROM-PROVENANCE.md)
and
[`BINARY-AUDIT.md`](https://github.com/djgraco/nokiaKlatt/blob/main/docs/BINARY-AUDIT.md).
