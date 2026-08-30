#!/usr/bin/env python3
"""Capture the known-good Unicorn state at the 5320 Prime loop."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

TARGET = 0x830DBA0E


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('upstream', type=Path)
    ap.add_argument('--text', default='Hallo Welt')
    args = ap.parse_args()

    addon = args.upstream / 'addon'
    sys.path.insert(0, str(addon / 'synthDrivers'))
    import _nokia.harness  # noqa: F401
    from unicorn import UC_HOOK_CODE
    from unicorn.arm_const import (
        UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
        UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
        UC_ARM_REG_SP,
    )
    from _nokia.harness import epoc as epoc_module

    regs_const = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                  UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7]
    first_samples = []
    around_samples = []
    tail_samples = []
    hits = [0]
    original_init = epoc_module.Epoc.__init__

    def capture_row(uc):
        regs = [int(uc.reg_read(c)) & 0xffffffff for c in regs_const]
        sp = int(uc.reg_read(UC_ARM_REG_SP)) & 0xffffffff
        r4 = regs[4]
        try:
            raw = bytes(uc.mem_read(r4, 8))
            s0 = int.from_bytes(raw[0:2], 'little')
            s2 = int.from_bytes(raw[2:4], 'little')
            s4 = int.from_bytes(raw[4:8], 'little')
        except Exception:
            s0 = s2 = s4 = 0xffffffff
        return (hits[0], *regs, sp, s0, s2, s4)

    def install_probe(self, *a, **kw):
        original_init(self, *a, **kw)
        def on_code(uc, address, _size, _user):
            if (int(address) & ~1) != TARGET:
                return
            hits[0] += 1
            row = capture_row(uc)
            if hits[0] <= 8:
                first_samples.append(row)
            if 724 <= hits[0] <= 736:
                around_samples.append(row)
            tail_samples.append(row)
            if len(tail_samples) > 12:
                del tail_samples[0]
        self._prime_probe_hook = self.uc.hook_add(UC_HOOK_CODE, on_code)

    epoc_module.Epoc.__init__ = install_probe
    from _nokia.engine import Engine
    engine = None
    try:
        engine = Engine(str(addon / 'roms' / '5320' / 'SYM.ROM'),
                        str(addon / 'roms' / '5320' / 'files'),
                        3, 'DefaultMale')
        audio = engine.speak(args.text, lambda _pcm: None)
        print('known-good audio bytes:', audio)
        print('target hits:', hits[0])
        names = ['r0','r1','r2','r3','r4','r5','r6','r7','sp','s0','s2','s4']
        for label, rows in [('first', first_samples), ('around730', around_samples), ('tail', tail_samples)]:
            print(label + ':')
            for row in rows:
                hit, *v = row
                print('hit', hit, ' '.join(f'{n}={x:#x}' for n, x in zip(names, v)))
    finally:
        if engine is not None:
            engine.close()
        epoc_module.Epoc.__init__ = original_init


if __name__ == '__main__':
    main()
