#!/usr/bin/env python3
"""Verify all 30 packaged Nokia E65 languages against reference PCM."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import string
from pathlib import Path

from smoke_native_5500_voices import (
    ARABIC_LATIN_RUNTIME_ERROR_FIRST_HALF_REGRESSION,
    ARABIC_LATIN_RUNTIME_ERROR_REGRESSION,
    Callbacks,
    DIAGNOSTICS,
    GERMAN_SETTINGS_REGRESSION,
    INDEX,
    LONG_RUNTIME_ERROR_REGRESSION,
    PCM,
    byte_array,
    config_blobs,
    write_rom_trace,
)


SAMPLES = {
    1: "Hello, this is the Nokia Klatt speech synthesizer speaking British English.",
    2: "Bonjour, je suis le synthetiseur vocal Nokia Klatt et je parle francais.",
    3: "Guten Tag, ich bin die Nokia Klatt Sprachausgabe und ich spreche Deutsch.",
    4: "Hola, soy el sintetizador de voz Nokia Klatt y hablo espanol.",
    5: "Buongiorno, sono il sintetizzatore vocale Nokia Klatt e parlo italiano.",
    6: "Hej, jag ar Nokia Klatt talsyntes och jag talar svenska.",
    7: "Goddag, jeg er Nokia Klatt talesyntese, og jeg taler dansk.",
    8: "God dag, jeg er Nokia Klatt talesyntese, og jeg snakker norsk.",
    9: "Hei, mina olen Nokia Klatt puhesyntetisaattori ja puhun suomea.",
    13: "Ola, sou o sintetizador de voz Nokia Klatt e falo portugues.",
    14: "Merhaba, ben Nokia Klatt konusma sentezleyicisiyim ve Turkce konusuyorum.",
    15: "Godan dag, eg er Nokia Klatt talgervill og eg tala islensku.",
    16: "Здравствуйте, я синтезатор речи Нокиа Клатт, и я говорю по-русски.",
    17: "Jo napot, en vagyok a Nokia Klatt beszedszintetizator es magyarul beszelek.",
    18: "Goedendag, ik ben de Nokia Klatt spraaksynthese en ik spreek Nederlands.",
    25: "Dobry den, jsem hlasovy syntezator Nokia Klatt a mluvim cesky.",
    26: "Dobry den, som hlasovy syntetizator Nokia Klatt a hovorim po slovensky.",
    27: "Dzien dobry, jestem syntezatorem mowy Nokia Klatt i mowie po polsku.",
    28: "Dober dan, sem govorni sintetizator Nokia Klatt in govorim slovensko.",
    37: "مرحبا، أنا مركب الكلام نوكيا وأتكلم العربية.",
    42: "Здравейте, аз съм гласовият синтезатор Нокиа и говоря български.",
    45: "Dobar dan, ja sam govorni sintetizator Nokia Klatt i govorim hrvatski.",
    49: "Tere, ma olen Nokia Klatt konesyntesaator ja ma raagin eesti keelt.",
    54: "Γεια σας, είμαι ο συνθετής φωνής Νοκια και μιλάω ελληνικά.",
    57: "שלום, אני מסנתז הדיבור של נוקיה ואני מדבר עברית.",
    67: "Sveiki, es esmu Nokia Klatt runas sintezators un es runaju latviski.",
    68: "Sveiki, as esu Nokia Klatt kalbos sintezatorius ir kalbu lietuviskai.",
    78: "Buna ziua, sunt sintetizatorul de voce Nokia Klatt si vorbesc romaneste.",
    79: "Добар дан, ја сам говорни синтетизатор Нокиа и говорим српски.",
    93: "Доброго дня, я синтезатор мовлення Нокіа і я говорю українською.",
}

EXPECTED_SHA256 = {
    1: "06b6c1c5d72a8e44d4d56f9d59d5f3b1a47133ee4e8c44ccc8c3ee16cf49e570",
    2: "877d6ba5c1c461783a1befd5a3b1d639c5420b0b1063131d3452633e81217da7",
    3: "36f8ad4660a7f6dde9a5c878d1cfb63e098bd60b09d95c11c81e3486e63c942c",
    4: "426ef616df181c54fc6a7c94252d7c134a0ca0504b9b26e5d9eaa20f9100c460",
    5: "190c58c25edf7ae4fb1066f930ae1d4ffcc003871300f0d7e45258801467267d",
    6: "211096e7f6ca65a8983896ac30319aa83156d2e1204b9b80d540a07bac29d081",
    7: "3363fb2eee6908a11345a4daf2a043da10086e59517f04492165dd2f542393b9",
    8: "061e04104f11259641e5d77a36e6a3c166c017c5046188c8bd966479fea1da9b",
    9: "db331a7bea2414d2f713b52d593b35dcf6fff90d65a7336cde7eef6e7622f6bd",
    13: "b88ea661be1ee12391daf018ae0cf75779e153621666fbedebc11042313f2174",
    14: "dd511c08d4e442a90e1da9561d180776a148ca8ab9cda55193f6ce644fed0b79",
    15: "83e8db6253b117d709d772b879cfda37b79686d65de9b3f62143bbcd8a96a7bf",
    16: "96e153afebc061d7f4dc671ee0f283d692c5319ba0671b21fc1174a76b01a5cc",
    17: "6d9343a58914abae87d8119125f23c9f4c969b1bfd6a4de5cf487a4a8aacc494",
    18: "2890c3ab77495511f8f3473cbbe316744d225a54bf39ac4013afdfe2e09415be",
    25: "998b6d95fd5c23710eee4fb2a2454ecb8d6f60785c103e77f8e27b43c9d43f58",
    26: "2baa9a14533886970a29c29a23a2b72dd5cb39bb0a89dec3e34c45ee14727d47",
    27: "41ba02d66150197f9c5d170e19ca7540b5331a1e137c0bc624aac73e7bea4767",
    28: "4438ef404a870c09e070356dd44ac99aaacf542c3e7993770fa007bc4a78e488",
    37: "d2f65d7117f955603ced07d4070518cab13917d5dc89406046b228e78c6ef5a0",
    42: "ab7bb7540aec087f66c5ce6c4a3004eabc57018caed8535646be28d4d6681cd6",
    45: "d7fda2fa3df2af5200ffa7339d41f398ed479dec396784d17b22cb6fa33d098d",
    49: "36ff45c087aa93af57833cc9a85e0048e1654d3e2a5408f73fedd3a63d3f7fa2",
    54: "7d3eab74a043db415b1faaffaa9298a1a1a0b3c707a9ed5e2a493347642032cd",
    57: "88695feccaf3149d15887677c178e6587847bee5ff0c02f6ad59606f8390ebe1",
    67: "bfce4bd30f2fe6272891a21dc531879c1bf68dfb393b7f345b9963af6889bc4f",
    68: "68b9d7d76051e58b51656e1653a86a788e062462111aadb12f8444e28ae25804",
    78: "53750c7f13335ef37e73b5ad39e056beed66420a6b19b4582bab6bb6f82fdd8a",
    79: "15a764c48a5964f00baea37b39487aceaa06905329a9fbc7745fbef0edbe2160",
    93: "1a72e2ca084e9e60ef8d237266396b5aa9ba5999caa8062645ff36cc38b8f6bd",
}

GERMAN_REGRESSIONS = (
    "NVDA Menü",
    "Optionen Untermenü",
    "Werkzeuge Untermenü",
    GERMAN_SETTINGS_REGRESSION,
    LONG_RUNTIME_ERROR_REGRESSION,
)
LANGUAGE_REGRESSIONS = {
    3: GERMAN_REGRESSIONS,
    37: (
        "Hello world",
        ARABIC_LATIN_RUNTIME_ERROR_FIRST_HALF_REGRESSION,
        ARABIC_LATIN_RUNTIME_ERROR_REGRESSION,
    ),
}

# These exact one-character utterances are rejected by the original E65
# engine itself and therefore are not native-AOT coverage failures.
REFERENCE_REJECTED_LETTERS = {1: frozenset("r")}


def bind(dll) -> None:
    dll.nokia_register_config_blob.argtypes = [
        ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32,
    ]
    dll.nokia_register_config_blob.restype = ctypes.c_int
    dll.nokia_runtime_create_e65_snapshot.argtypes = [
        ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
    ]
    dll.nokia_runtime_create_e65_snapshot.restype = ctypes.c_void_p
    dll.nokia_runtime_speak_utf16.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint16), ctypes.c_uint32,
        ctypes.POINTER(Callbacks),
    ]
    dll.nokia_runtime_speak_utf16.restype = ctypes.c_int
    dll.nokia_runtime_set_rate.argtypes = [ctypes.c_void_p, ctypes.c_double]
    dll.nokia_runtime_set_rate.restype = ctypes.c_int
    dll.nokia_runtime_set_pitch.argtypes = [ctypes.c_void_p, ctypes.c_double]
    dll.nokia_runtime_set_pitch.restype = ctypes.c_int
    dll.nokia_runtime_last_error.argtypes = [ctypes.c_void_p]
    dll.nokia_runtime_last_error.restype = ctypes.c_int
    dll.nokia_runtime_destroy.argtypes = [ctypes.c_void_p]
    dll.nokia_runtime_rom_trace_page_size.restype = ctypes.c_uint32
    dll.nokia_runtime_rom_trace_page_used.argtypes = [ctypes.c_uint32]
    dll.nokia_runtime_rom_trace_page_used.restype = ctypes.c_int
    for _label, export in DIAGNOSTICS:
        function = getattr(dll, export, None)
        if function:
            function.argtypes = []
            function.restype = ctypes.c_uint32


def synthesize(
    dll, rom, rom_size, snapshot_path: Path, text: str,
    rate=1.0, pitch=1.0,
):
    snapshot_data, snapshot = byte_array(snapshot_path)
    runtime = dll.nokia_runtime_create_e65_snapshot(
        rom, rom_size, snapshot, len(snapshot_data)
    )
    if not runtime:
        raise RuntimeError("snapshot restore failed")
    if not dll.nokia_runtime_set_rate(runtime, rate):
        dll.nokia_runtime_destroy(runtime)
        raise RuntimeError(f"setting rate {rate} failed")
    if not dll.nokia_runtime_set_pitch(runtime, pitch):
        dll.nokia_runtime_destroy(runtime)
        raise RuntimeError(f"setting pitch {pitch} failed")
    pcm = []

    @PCM
    def on_pcm(_user, samples, count, sample_rate):
        if sample_rate != 16000:
            raise RuntimeError(f"unexpected sample rate {sample_rate}")
        pcm.append(ctypes.string_at(samples, count * 2))

    @INDEX
    def on_index(_user, _index):
        pass

    callbacks = Callbacks(on_pcm, on_index, None)
    encoded = text.encode("utf-16-le")
    units = (ctypes.c_uint16 * (len(encoded) // 2)).from_buffer_copy(encoded)
    try:
        ok = dll.nokia_runtime_speak_utf16(
            runtime, units, len(units), ctypes.byref(callbacks)
        )
        audio = b"".join(pcm)
        if not ok or not audio or not any(audio):
            error = dll.nokia_runtime_last_error(runtime)
            diagnostics = ", ".join(
                f"{label}=0x{function():08x}"
                for label, export in DIAGNOSTICS
                if (function := getattr(dll, export, None))
            )
            raise RuntimeError(
                f"synthesis result={ok}, error={error}, pcm_bytes={len(audio)}"
                + (f", {diagnostics}" if diagnostics else "")
            )
        return audio
    finally:
        dll.nokia_runtime_destroy(runtime)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dll", type=Path)
    parser.add_argument("rom", type=Path)
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("config", type=Path)
    parser.add_argument("--quick", action="store_true",
                        help="skip isolated-letter and high-rate coverage")
    parser.add_argument("--rom-trace", type=Path)
    args = parser.parse_args()

    dll = ctypes.CDLL(str(args.dll.resolve()))
    bind(dll)
    held = []
    for type_id, data_id, data in config_blobs(args.config):
        buffer = ctypes.create_string_buffer(data)
        held.append(buffer)
        if not dll.nokia_register_config_blob(type_id, data_id, buffer, len(data)):
            raise SystemExit(f"failed registering srsf_{type_id}_{data_id}.bin")
    if not held:
        raise SystemExit("no configuration blobs found")

    rom_data, rom = byte_array(args.rom)
    failures = []
    validated = 0
    letters_passed = 0
    high_rate_passed = 0
    for language_id, sample in SAMPLES.items():
        snapshot = args.snapshot_dir / f"e65-{language_id}.snapshot"
        try:
            audio = synthesize(dll, rom, len(rom_data), snapshot, sample)
        except Exception as error:
            failures.append(f"{language_id}: {error}")
            continue
        digest = hashlib.sha256(audio).hexdigest()
        print(f"{language_id}: pcm_bytes={len(audio)} sha256={digest}")
        if digest != EXPECTED_SHA256[language_id]:
            failures.append(
                f"{language_id}: expected {EXPECTED_SHA256[language_id]}, got {digest}"
            )
        else:
            validated += 1
        # Keep these before the quick-test exit: they guard the ARM64EC path
        # used by the NVDA driver, including its explicit pitch setup.
        for regression_text in LANGUAGE_REGRESSIONS.get(language_id, ()):
            try:
                regression_audio = synthesize(
                    dll, rom, len(rom_data), snapshot, regression_text
                )
            except Exception as error:
                failures.append(
                    f"{language_id} {regression_text!r}: {error}"
                )
            else:
                print(
                    f"{language_id} {regression_text!r}: "
                    f"pcm_bytes={len(regression_audio)}"
                )
        if args.quick:
            continue
        for value in string.ascii_letters:
            if value in REFERENCE_REJECTED_LETTERS.get(language_id, ()):
                continue
            try:
                synthesize(dll, rom, len(rom_data), snapshot, value)
            except Exception as error:
                failures.append(f"{language_id} {value!r}: {error}")
            else:
                letters_passed += 1
        try:
            synthesize(dll, rom, len(rom_data), snapshot, sample, rate=4.0)
        except Exception as error:
            failures.append(f"{language_id} high-rate: {error}")
        else:
            high_rate_passed += 1

    if args.rom_trace:
        write_rom_trace(dll, rom_data, args.rom_trace)
        print("wrote ROM trace:", args.rom_trace)
    print(f"validated voices: {validated}/{len(SAMPLES)}; failures: {len(failures)}")
    if not args.quick:
        expected_letters = len(SAMPLES) * 52 - sum(
            len(values) for values in REFERENCE_REJECTED_LETTERS.values()
        )
        print(f"isolated letters passed: {letters_passed}/{expected_letters}")
        print(f"high-rate utterances passed: {high_rate_passed}/{len(SAMPLES)}")
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
