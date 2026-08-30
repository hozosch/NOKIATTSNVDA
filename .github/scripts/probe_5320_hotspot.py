#!/usr/bin/env python3
from __future__ import annotations
import argparse, sys
from collections import deque
from pathlib import Path

TARGET = 0x830E1952


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('upstream', type=Path)
    ap.add_argument('--text', default='Hallo Welt')
    args=ap.parse_args()
    addon=args.upstream/'addon'
    sys.path.insert(0,str(addon/'synthDrivers'))
    import _nokia.harness  # noqa
    from unicorn import UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_SP)
    from _nokia.harness import epoc as epoc_module
    regs_const=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7]
    hits=[0]; first=[]; periodic=[]; tail=deque(maxlen=12)
    original=epoc_module.Epoc.__init__
    def install(self,*a,**kw):
        original(self,*a,**kw)
        def on_code(uc,address,_size,_user):
            if (int(address)&~1)!=TARGET: return
            hits[0]+=1
            regs=[int(uc.reg_read(c))&0xffffffff for c in regs_const]
            sp=int(uc.reg_read(UC_ARM_REG_SP))&0xffffffff
            r4=regs[4]
            try:
                raw=bytes(uc.mem_read(r4,8)); s0=int.from_bytes(raw[:2],'little'); s2=int.from_bytes(raw[2:4],'little'); s4=int.from_bytes(raw[4:8],'little')
            except Exception:
                s0=s2=s4=0xffffffff
            row=(hits[0],*regs,sp,s0,s2,s4)
            if len(first)<8: first.append(row)
            if hits[0]%500==0: periodic.append(row)
            tail.append(row)
        self._hotspot_probe=self.uc.hook_add(UC_HOOK_CODE,on_code)
    epoc_module.Epoc.__init__=install
    from _nokia.engine import Engine
    e=None
    try:
        e=Engine(str(addon/'roms'/'5320'/'SYM.ROM'),str(addon/'roms'/'5320'/'files'),3,'DefaultMale')
        audio=e.speak(args.text,lambda _pcm:None)
        print('known-good audio bytes:',audio); print('target:',hex(TARGET),'hits:',hits[0])
        names=['r0','r1','r2','r3','r4','r5','r6','r7','sp','s0','s2','s4']
        def show(tag, rows):
            print(tag+':')
            for row in rows:
                hit,*v=row; print('hit',hit,' '.join(f'{n}={x:#x}' for n,x in zip(names,v)))
        show('first',first); show('periodic',periodic); show('tail',list(tail))
    finally:
        if e is not None: e.close()
        epoc_module.Epoc.__init__=original
if __name__=='__main__': main()
