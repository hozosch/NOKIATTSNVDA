#!/usr/bin/env python3
"""Capture only instructions executed inside a Nokia Klatt entry call."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--entry", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--language", type=int, required=True)
    parser.add_argument("--voice", default="")
    parser.add_argument("--text", required=True)
    args = parser.parse_args()

    addon = args.upstream / "addon"
    sys.path.insert(0, str(addon / "synthDrivers"))
    import _nokia.harness  # noqa: F401
    from unicorn import UC_HOOK_CODE
    from unicorn.arm_const import UC_ARM_REG_CPSR, UC_ARM_REG_LR
    from _nokia.harness import epoc as epoc_module

    entry = args.entry & ~1
    executed: dict[tuple[int, bool], int] = {}
    active = {"value": False, "return": 0}
    original_init = epoc_module.Epoc.__init__

    def install_trace(self, *a, **kw):
        original_init(self, *a, **kw)

        def on_code(uc, address, size, _user):
            address = int(address) & ~1
            if not active["value"]:
                if address != entry:
                    return
                active["value"] = True
                active["return"] = int(uc.reg_read(UC_ARM_REG_LR)) & ~1
            elif address == active["return"]:
                active["value"] = False
                return
            if not (self.rom_base <= address < self.rom_base + len(self.blob)):
                return
            cpsr = int(uc.reg_read(UC_ARM_REG_CPSR))
            executed[(address, bool(cpsr & (1 << 5)))] = int(size)

        self._native_klatt_trace_hook = self.uc.hook_add(
            UC_HOOK_CODE, on_code, None,
            self.rom_base, self.rom_base + len(self.blob) - 1,
        )

    epoc_module.Epoc.__init__ = install_trace
    from _nokia import romdir
    from _nokia.engine import Engine

    profile_dir = addon / "roms" / args.profile
    rom_name = romdir.find_rom_image(str(profile_dir))
    tree_name = romdir.data_tree(str(profile_dir), args.profile)
    if not rom_name or not tree_name:
        raise SystemExit(f"profile {args.profile!r} is incomplete")
    engine = None
    try:
        engine = Engine(rom_name, tree_name, args.language, args.voice)
        total = engine.speak(args.text, lambda _pcm: None)
    finally:
        if engine is not None:
            engine.close()
        epoc_module.Epoc.__init__ = original_init

    instructions = [
        {"address": address, "size": size, "thumb": thumb, "phase": "klatt"}
        for (address, thumb), size in sorted(executed.items())
    ]
    payload = {
        "profile": args.profile,
        "kind": "native-klatt",
        "entry": entry,
        "language": args.language,
        "voice": args.voice,
        "text": args.text,
        "audio_bytes": total,
        "instruction_count": len(instructions),
        "instructions": instructions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"{args.profile} language {args.language}: "
        f"{len(instructions)} Klatt instructions, {total} audio bytes"
    )


if __name__ == "__main__":
    main()
