#!/usr/bin/env python3
"""Record every ROM instruction used by one complete Nokia utterance.

This is a build-time migration tool. It intentionally runs the known-good
Unicorn implementation once in CI so the resulting instruction corpus can be
translated ahead of time and Unicorn can disappear from the shipped add-on.
The hook is installed immediately after Epoc creates/maps Unicorn, before
CDevTTS construction and speech work execute. The historical filename is kept
because existing 5320 workflows call it, but ``--profile`` also supports later
ports such as the Nokia 5500.
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
    parser.add_argument("--text-file", type=Path,
                        help="read utterance text from UTF-8 file")
    parser.add_argument("--language", type=int, default=3)
    parser.add_argument("--voice", default="DefaultMale")
    parser.add_argument("--profile", default="5320",
                        help="ROM profile directory below addon/roms")
    args = parser.parse_args()
    if args.text_file is not None:
        args.text = args.text_file.read_text(encoding="utf-8")

    addon = args.upstream / "addon"
    sys.path.insert(0, str(addon / "synthDrivers"))

    # Importing the harness package first is intentional: its __init__ adds the
    # vendored Unicorn bindings/native DLL directory to sys.path/environment.
    import _nokia.harness  # noqa: F401
    from unicorn import UC_HOOK_CODE
    from unicorn.arm_const import (
        UC_ARM_REG_CPSR,
        UC_ARM_REG_LR,
        UC_ARM_REG_PC,
        UC_ARM_REG_R12,
    )
    from _nokia.harness import epoc as epoc_module

    executed: dict[tuple[int, bool], int] = {}
    addresses_seen: set[int] = set()
    phase = {"name": "epoc"}
    first_phase: dict[tuple[int, bool], str] = {}
    executive_calls: dict[tuple[bool, int, int, bool], dict] = {}
    executive_phases: dict[tuple[bool, int, int, bool], set[str]] = {}
    original_init = epoc_module.Epoc.__init__

    def install_trace(self, *a, **kw):
        original_init(self, *a, **kw)

        def on_code(uc, address, size, _user):
            # Only guest ROM code belongs in the AOT corpus. Host traps,
            # synthetic heap and stack are represented by native runtime data.
            if not (self.rom_base <= address < self.rom_base + len(self.blob)):
                return
            address = int(address) & ~1
            if address in addresses_seen:
                return
            addresses_seen.add(address)
            cpsr = int(uc.reg_read(UC_ARM_REG_CPSR))
            thumb = bool(cpsr & (1 << 5))
            key = (address, thumb)
            executed[key] = int(size)
            first_phase[key] = phase["name"]

        self._full_lifecycle_trace_hook = self.uc.hook_add(
            UC_HOOK_CODE, on_code, None,
            self.rom_base, self.rom_base + len(self.blob) - 1)

        original_exec_call = self.exec_call

        def on_exec_call(number, fast, uc):
            cpsr = int(uc.reg_read(UC_ARM_REG_CPSR))
            thumb = bool(cpsr & (1 << 5))
            pc_after_svc = int(uc.reg_read(UC_ARM_REG_PC)) & 0xffffffff
            svc_address = (pc_after_svc - (2 if thumb else 4)) & 0xffffffff
            returns_to_lr = bool(self._stub_returns_to_lr(uc, pc_after_svc))
            key = (bool(fast), int(number), svc_address, returns_to_lr)
            item = executive_calls.setdefault(key, {
                "fast": bool(fast),
                "number": int(number),
                "svc_address": svc_address,
                "thumb": thumb,
                "returns_to_lr": returns_to_lr,
                "first_phase": phase["name"],
                "sample_lr": int(uc.reg_read(UC_ARM_REG_LR)) & 0xffffffff,
                "sample_ip": int(uc.reg_read(UC_ARM_REG_R12)) & 0xffffffff,
                "count": 0,
            })
            executive_phases.setdefault(key, set()).add(phase["name"])
            item["count"] += 1
            return original_exec_call(number, fast, uc)

        self.exec_call = on_exec_call

    epoc_module.Epoc.__init__ = install_trace

    from _nokia import romdir
    from _nokia.engine import Engine

    profile_dir = addon / "roms" / args.profile
    rom_name = romdir.find_rom_image(str(profile_dir))
    tree_name = romdir.data_tree(str(profile_dir), args.profile)
    if not rom_name or not tree_name:
        raise SystemExit(
            f"profile {args.profile!r} does not contain a usable ROM and "
            "speech-data tree"
        )
    rom = Path(rom_name)
    tree = Path(tree_name)
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
        "profile": args.profile,
        "language": args.language,
        "voice": args.voice,
        "text": args.text,
        "audio_bytes": total,
        "instruction_count": len(instructions),
        "phase_counts": counts,
        "executive_calls": [
            dict(
                executive_calls[key],
                phases=sorted(executive_phases[key]),
            )
            for key in sorted(executive_calls)
        ],
        "instructions": instructions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n",
                           encoding="utf-8")
    print(f"{args.profile} full lifecycle: "
          f"{len(instructions)} unique ROM instructions")
    print("phase counts:", counts)
    print("audio bytes:", total)


if __name__ == "__main__":
    main()
