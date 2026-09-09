#!/usr/bin/env python3
"""Smoke-test every packaged Nokia 5320 language and named voice."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import re
from pathlib import Path

from build_config_pack import read as read_config_pack


SAMPLES = {
    1: "Hello world",
    2: "Bonjour le monde",
    3: "Hallo Welt",
    4: "Hola mundo",
    5: "Ciao mondo",
    6: "Hej världen",
    7: "Hej verden",
    8: "Hei verden",
    9: "Hei maailma",
    13: "Olá mundo",
    14: "Merhaba dünya",
    15: "Halló heimur",
    16: "Привет мир",
    17: "Helló világ",
    18: "Hallo wereld",
    25: "Ahoj světe",
    26: "Ahoj svet",
    27: "Witaj świecie",
    28: "Pozdravljen svet",
    37: "مرحبا بالعالم",
    42: "Здравей свят",
    44: "Hola món",
    45: "Pozdrav svijete",
    49: "Tere maailm",
    54: "Γεια σου κόσμε",
    57: "שלום עולם",
    67: "Sveika pasaule",
    68: "Labas pasauli",
    78: "Salut lume",
    79: "Здраво свете",
    93: "Привіт світе",
    401: "Kaixo mundua",
    402: "Ola mundo",
}
GENDERS = ("male", "female")
REGRESSION_SAMPLES = {
    (3, "male"): ("Gegen", "Google", "Hallo 你好，世界 Test"),
    (3, "female"): (
        "Zwölf Boxkämpfer jagen Viktor quer über den großen Sylter Deich.",
    ),
    (5, "male"): ("Braille",),
    (5, "female"): ("Braille",),
    (8, "male"): ("abcdefghijklmnopqrstuvwxyz æøå 0123456789",),
    (8, "female"): ("abcdefghijklmnopqrstuvwxyz æøå 0123456789",),
    (18, "female"): ("Pa's wijze lynx bezag vroom het fikse aquaduct.",),
    (54, "male"): ("εισαγωγικά", "εισαγωγικά λέξη"),
    (54, "female"): ("εισαγωγικά", "εισαγωγικά λέξη"),
}
REGRESSION_SHA256 = {
    (3, "male", 1): (
        "92cecc0850a31f57ca1a52f714545cea0bfdd44808657b20bba58bc8f8b0c0b4"
    ),
    (3, "male", 2): (
        "8254bc71b3ae1dffa540882fbbf221413ebc1e1b4718154bf0f9ef1bfe74351c"
    ),
    (3, "female", 1): (
        "4904603323b210266e78e9758747d8fd527d133c5341569b587f744536ac61e6"
    ),
    (5, "male", 1): (
        "89851f72aaff955d334cdb16120dbb75966ab365e6a6ea45f024deee37db855e"
    ),
    (5, "female", 1): (
        "a3bc2b5e308979409eab011c16cba7f4a0c05eb980d99eb88f30c8f7e187fbf2"
    ),
    (8, "male", 1): (
        "c25b1b0f7ab2e7c1e95e582df5900b7c6c1ac921661d483ea64fbffb4028f233"
    ),
    (8, "female", 1): (
        "bf22320590d55b9718e7032cfbb3d3748048d4b12a1bc3448c397dd7907edb1f"
    ),
    (18, "female", 1): (
        "9c50f6748fc60ad113a3abaa332d008bc7777398fb76c2efaecf395f13417f41"
    ),
    (54, "male", 1): (
        "8db00776c0cb8d7b761141001f6c276f8ea63af02f095f798b385a3477de5109"
    ),
    (54, "male", 2): (
        "847be3072aebe159377b74a8dc21ca9a2541b13a738a411a33318a699dcb212c"
    ),
    (54, "female", 1): (
        "3fb59cb0047f55b15ce5f6856160b8b47507634e076b9ad7e1c26ab68fe68131"
    ),
    (54, "female", 2): (
        "5f3af17114da8ef96a6b81bac248623324fce6782126cdd217eb371c87718281"
    ),
}
GERMAN_MALE_SHA256 = (
    "3f3e908c133f7eb26c6bb990886f3bde06a5d31e93a65dbed2bc091f6cd738ee"
)


PCM = ctypes.CFUNCTYPE(
    None,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int16),
    ctypes.c_uint32,
    ctypes.c_uint32,
)
INDEX = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint32)


class Callbacks(ctypes.Structure):
    _fields_ = [("pcm", PCM), ("index", INDEX), ("user", ctypes.c_void_p)]


def byte_array(path: Path):
    data = path.read_bytes()
    return data, (ctypes.c_uint8 * len(data)).from_buffer_copy(data)


def config_blobs(path: Path):
    if path.is_file():
        yield from read_config_pack(path)
        return
    for item in sorted(path.glob("srsf_*_*.bin")):
        match = re.fullmatch(r"srsf_(\d+)_(\d+)\.bin", item.name, re.I)
        if match:
            yield int(match.group(1)), int(match.group(2)), item.read_bytes()


def bind(dll):
    dll.nokia_register_config_blob.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    dll.nokia_register_config_blob.restype = ctypes.c_int
    dll.nokia_runtime_create_5320_snapshot.argtypes = [
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_size_t,
    ]
    dll.nokia_runtime_create_5320_snapshot.restype = ctypes.c_void_p
    dll.nokia_runtime_speak_utf16.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint16),
        ctypes.c_uint32,
        ctypes.POINTER(Callbacks),
    ]
    dll.nokia_runtime_speak_utf16.restype = ctypes.c_int
    dll.nokia_runtime_last_error.argtypes = [ctypes.c_void_p]
    dll.nokia_runtime_last_error.restype = ctypes.c_int
    dll.nokia_runtime_destroy.argtypes = [ctypes.c_void_p]


def synthesize(
    dll, rom, rom_size, snapshot_path: Path, text: str, *, allow_silence=False
):
    snapshot_data, snapshot = byte_array(snapshot_path)
    runtime = dll.nokia_runtime_create_5320_snapshot(
        rom,
        rom_size,
        snapshot,
        len(snapshot_data),
    )
    if not runtime:
        raise RuntimeError("snapshot restore failed")
    pcm = []
    callback_error = []

    @PCM
    def on_pcm(_user, samples, count, sample_rate):
        if sample_rate != 16000:
            callback_error.append(f"unexpected sample rate {sample_rate}")
            return
        pcm.append(ctypes.string_at(samples, count * 2))

    @INDEX
    def on_index(_user, _index):
        pass

    callbacks = Callbacks(on_pcm, on_index, None)
    encoded = text.encode("utf-16-le")
    units = (ctypes.c_uint16 * (len(encoded) // 2)).from_buffer_copy(encoded)
    try:
        ok = dll.nokia_runtime_speak_utf16(
            runtime,
            units,
            len(units),
            ctypes.byref(callbacks),
        )
        error = dll.nokia_runtime_last_error(runtime)
        audio = b"".join(pcm)
        if callback_error:
            raise RuntimeError(callback_error[0])
        if not ok or error or (
            not allow_silence and (not audio or not any(audio))
        ):
            raise RuntimeError(
                f"synthesis result={ok}, error={error}, pcm_bytes={len(audio)}"
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
    parser.add_argument(
        "--skip-reference-hash",
        action="store_true",
        help="do not require bit-identical Test43 German male output",
    )
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
    hashes = {}
    for language_id, text in SAMPLES.items():
        for gender in GENDERS:
            label = f"{language_id}-{gender}"
            snapshot = args.snapshot_dir / f"5320-{label}.snapshot"
            if not snapshot.is_file():
                failures.append(f"{label}: snapshot missing")
                continue
            try:
                audio = synthesize(dll, rom, len(rom_data), snapshot, text)
            except Exception as error:
                failures.append(f"{label}: {error}")
                continue
            digest = hashlib.sha256(audio).hexdigest()
            hashes[label] = digest
            print(f"{label}: pcm_bytes={len(audio)} sha256={digest}")
            try:
                cjk_audio = synthesize(
                    dll,
                    rom,
                    len(rom_data),
                    snapshot,
                    "你好，世界",
                    allow_silence=True,
                )
            except Exception as error:
                failures.append(f"{label}-CJK: {error}")
            else:
                print(f"{label}-CJK: handled, pcm_bytes={len(cjk_audio)}")

    for language_id in SAMPLES:
        male = hashes.get(f"{language_id}-male")
        female = hashes.get(f"{language_id}-female")
        if male is not None and male == female:
            failures.append(f"{language_id}: male and female PCM are identical")

    for (language_id, gender), samples in REGRESSION_SAMPLES.items():
        label = f"{language_id}-{gender}"
        snapshot = args.snapshot_dir / f"5320-{label}.snapshot"
        if not snapshot.is_file():
            continue
        for number, sample in enumerate(samples, 1):
            regression_label = f"{label}-regression-{number}"
            try:
                audio = synthesize(
                    dll, rom, len(rom_data), snapshot, sample
                )
            except Exception as error:
                failures.append(f"{regression_label}: {error}")
                continue
            digest = hashlib.sha256(audio).hexdigest()
            print(
                f"{regression_label}: pcm_bytes={len(audio)} sha256={digest}"
            )
            expected = REGRESSION_SHA256.get(
                (language_id, gender, number)
            )
            if expected is not None and digest != expected:
                failures.append(
                    f"{regression_label}: Unicorn reference changed: "
                    f"expected {expected}, got {digest}"
                )

    if not args.skip_reference_hash:
        actual = hashes.get("3-male")
        if actual is not None and actual != GERMAN_MALE_SHA256:
            failures.append(
                "3-male: Test43 reference changed: "
                f"expected {GERMAN_MALE_SHA256}, got {actual}"
            )

    print(f"validated voices: {len(hashes)}; failures: {len(failures)}")
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
