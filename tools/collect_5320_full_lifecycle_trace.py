#!/usr/bin/env python3
"""Record every ROM instruction used by one complete Nokia 5320 utterance.

This is a build-time migration tool.  It intentionally runs the known-good
Unicorn implementation once in CI so the resulting instruction corpus can be
translated ahead of time and Unicorn can disappear from the shipped add-on.
The hook is installed immediately after Epoc creates/maps Unicorn, before
CDevTTS construction and runtime bootstrap execute.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream", type=Path,
                        help="checkout of djgraco/nokiaKlatt")
    parser.add_argument("output", type=Path)
    parser.add_argument("--text", default="Hallo Welt 123")
    parser.add_argument("--language", type=int, default=3)
    parser.add_argument("--voice", default="DefaultMale")
    args = parser.parse_args()

    addon = args.upstream / "addon"
    sys.path.insert(0, str(addon / "synthDrivers"))

    from unicorn import UC_HOOK_CODE
    from unicorn.arm_const import UC_ARM_REG_CPSR
    from _nokia.harness import epoc as epoc_module

    executed: dict[tuple[int, bool], int] = {}
    phase = {"name": "epoc"}
    first_phase: dict[tuple[int, bool], str] = {}
    original_init = epoc_module.Epoc.__init__

    def install_trace(self, *a, **kw):
        original_init(self, *a, **kw)

        def on_code(uc, address, size, _user):
            # Only guest ROM code belongs in the AOT corpus. Host traps,
            # synthetic heap and stack are represented by native runtime data.
            if not (self.rom_base <= address < self.rom_base + len(self.blob)):
                return
            # CPSR is read only the first time an address is encountered. This
            # keeps the one-time migration trace affordable even in tight loops.
            known_modes = [key for key in executed if key[0] == address]
            if known_modes:
                return
            cpsr = int(uc.reg_read(UC_ARM_REG_CPSR))
            thumb = bool(cpsr & (1 << 5))
            key = (int(address) & ~1, thumb)
            executed[key] = int(size)
            first_phase[key] = phase["name"]

        self._full_lifecycle_trace_hook = self.uc.hook_add(
            UC_HOOK_CODE, on_code, None,
            self.rom_base, self.rom_base + len(self.blob) - 1)

    epoc_module.Epoc.__init__ = install_trace

    from _nokia.engine import Engine

    rom = addon / "roms" / "5320" / "SYM.ROM"
    tree = addon / "roms" / "5320" / "files"
    engine = None
    total = 0
    try:
        phase["name"] = "construct"
        engine = Engine(str(rom), str(tree), args.language, args.voice)
        phase["name"] = "speak"
        total = engine.speak(args.text, lambda _pcm: None)
        phase["name"] = "stop"
        engine.cancel()
    finally:
        phase["name"] = "close"
        if engine is not None:
            engine.close()
        epoc_module.Epoc.__init__ = original_init

    instructions = [
        {"address": address, "size": size, "thumb": thumb,
         "phase": first_phase[(address, thumb)]}
        for (address, thumb), size in sorted(executed.items())
    ]
    counts: dict[str, int] = {}
    for item in instructions:
        counts[item["phase"]] = counts.get(item["phase"], 0) + 1
    payload = {
        "profile": "5320",
        "language": args.language,
        "voice": args.voice,
        "text": args.text,
        "audio_bytes": total,
        "instruction_count": len(instructions),
        "phase_counts": counts,
        "instructions": instructions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n",
                           encoding="utf-8")
    print(f"full lifecycle: {len(instructions)} unique ROM instructions")
    print("phase counts:", counts)
    print("audio bytes:", total)


if __name__ == "__main__":
    main()
