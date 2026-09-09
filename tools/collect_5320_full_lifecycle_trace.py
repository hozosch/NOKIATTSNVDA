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
    parser.add_argument("--augmented-rom-output", type=Path,
                        help="write an E65 ROM with its bound ROFS modules")
    parser.add_argument("--klatt-entry", type=lambda value: int(value, 0),
                        help="also record the instructions used inside Klatt")
    parser.add_argument("--block-trace", action="store_true",
                        help="decode executed basic blocks instead of hooking "
                             "every instruction")
    args = parser.parse_args()
    if args.text_file is not None:
        args.text = args.text_file.read_text(encoding="utf-8")

    addon = args.upstream / "addon"
    sys.path.insert(0, str(addon / "synthDrivers"))

    # Importing the harness package first is intentional: its __init__ adds the
    # vendored Unicorn bindings/native DLL directory to sys.path/environment.
    import _nokia.harness  # noqa: F401
    from unicorn import UC_HOOK_BLOCK, UC_HOOK_CODE
    from unicorn.arm_const import (
        UC_ARM_REG_CPSR,
        UC_ARM_REG_LR,
        UC_ARM_REG_PC,
        UC_ARM_REG_R12,
    )
    from _nokia.harness import epoc as epoc_module

    executed: dict[tuple[int, bool], int] = {}
    klatt_executed: dict[tuple[int, bool], int] = {}
    klatt_active = {"value": False, "return": 0}
    klatt_entry = (
        args.klatt_entry & ~1 if args.klatt_entry is not None else None
    )
    addresses_seen: set[int] = set()
    phase = {"name": "epoc"}
    first_phase: dict[tuple[int, bool], str] = {}
    executive_calls: dict[tuple[bool, int, int, bool], dict] = {}
    executive_phases: dict[tuple[bool, int, int, bool], set[str]] = {}
    original_init = epoc_module.Epoc.__init__
    executed_blocks: dict[tuple[int, int, bool], str] = {}
    klatt_blocks: set[tuple[int, int, bool]] = set()

    def install_trace(self, *a, **kw):
        original_init(self, *a, **kw)

        def on_code(uc, address, size, _user):
            # Only guest ROM code belongs in the AOT corpus. Host traps,
            # synthetic heap and stack are represented by native runtime data.
            in_rom = self.rom_base <= address < self.rom_base + len(self.blob)
            in_external = any(
                image.code_addr <= address < image.code_addr + image.code_size
                for image in getattr(self, "_e65_external_images", ())
            )
            if not (in_rom or in_external):
                return
            address = int(address) & ~1
            cpsr = int(uc.reg_read(UC_ARM_REG_CPSR))
            thumb = bool(cpsr & (1 << 5))
            key = (address, thumb)
            if klatt_entry is not None:
                if not klatt_active["value"] and address == klatt_entry:
                    klatt_active["value"] = True
                    klatt_active["return"] = (
                        int(uc.reg_read(UC_ARM_REG_LR)) & ~1
                    )
                elif (
                    klatt_active["value"]
                    and address == klatt_active["return"]
                ):
                    klatt_active["value"] = False
                if klatt_active["value"]:
                    klatt_executed[key] = int(size)
            if address in addresses_seen:
                return
            addresses_seen.add(address)
            executed[key] = int(size)
            first_phase[key] = phase["name"]

        def on_block(uc, address, size, _user):
            in_rom = self.rom_base <= address < self.rom_base + len(self.blob)
            in_external = any(
                image.code_addr <= address < image.code_addr + image.code_size
                for image in getattr(self, "_e65_external_images", ())
            )
            if not (in_rom or in_external):
                return
            address = int(address) & ~1
            cpsr = int(uc.reg_read(UC_ARM_REG_CPSR))
            thumb = bool(cpsr & (1 << 5))
            if klatt_entry is not None:
                if not klatt_active["value"] and address == klatt_entry:
                    klatt_active["value"] = True
                    klatt_active["return"] = (
                        int(uc.reg_read(UC_ARM_REG_LR)) & ~1
                    )
                elif (
                    klatt_active["value"]
                    and address == klatt_active["return"]
                ):
                    klatt_active["value"] = False
            block_key = (address, int(size), thumb)
            executed_blocks.setdefault(block_key, phase["name"])
            if klatt_active["value"]:
                klatt_blocks.add(block_key)

        self._full_lifecycle_trace_hook = self.uc.hook_add(
            UC_HOOK_BLOCK if args.block_trace else UC_HOOK_CODE,
            on_block if args.block_trace else on_code,
            None,
        )

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

    if args.profile == "e65":
        from e65_reference_support import install_e65_reference_support
        install_e65_reference_support()

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
        if args.augmented_rom_output is not None:
            from e65_reference_support import write_augmented_rom
            write_augmented_rom(engine.tts.epoc, args.augmented_rom_output)
        phase["name"] = "speak"
        total = engine.speak(args.text, lambda _pcm: None)
        phase["name"] = "stop"
        engine.cancel()
        if args.block_trace:
            import pypcode
            contexts = {
                False: pypcode.Context("ARM:LE:32:v8"),
                True: pypcode.Context("ARM:LE:32:v8T"),
            }
            decoded_blocks = {}
            for (address, size, thumb), block_phase in executed_blocks.items():
                raw = bytes(engine.tts.epoc.uc.mem_read(address, size))
                listing = contexts[thumb].disassemble(
                    raw,
                    base_address=address,
                    max_instructions=max(1, (size + 1) // 2),
                )
                decoded = [
                    (int(item.addr.offset) & ~1, int(item.length), thumb)
                    for item in listing.instructions
                ]
                if sum(item[1] for item in decoded) != size:
                    raise RuntimeError(
                        f"could not decode complete block at 0x{address:08x}: "
                        f"decoded {sum(item[1] for item in decoded)} of {size} bytes"
                    )
                decoded_blocks[(address, size, thumb)] = decoded
                for instruction_address, instruction_size, instruction_thumb in decoded:
                    key = (instruction_address, instruction_thumb)
                    if key not in executed:
                        executed[key] = instruction_size
                        first_phase[key] = block_phase
            for block_key in klatt_blocks:
                for instruction_address, instruction_size, instruction_thumb in decoded_blocks[block_key]:
                    klatt_executed[
                        (instruction_address, instruction_thumb)
                    ] = instruction_size
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
    if klatt_entry is not None:
        payload["klatt_entry"] = klatt_entry
        payload["klatt_instruction_count"] = len(klatt_executed)
        payload["klatt_instructions"] = [
            {
                "address": address,
                "size": size,
                "thumb": thumb,
                "phase": "klatt",
            }
            for (address, thumb), size in sorted(klatt_executed.items())
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n",
                           encoding="utf-8")
    print(f"{args.profile} full lifecycle: "
          f"{len(instructions)} unique ROM instructions")
    print("phase counts:", counts)
    print("audio bytes:", total)


if __name__ == "__main__":
    main()
