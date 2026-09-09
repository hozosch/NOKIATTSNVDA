#!/usr/bin/env python3
"""Build-time support for the Nokia E65's ROFS speech modules.

The E65 keeps ``nssdevtts.dll`` and ``asrsnlphwdevice.dll`` outside its XIP
ROM.  The preserved Python reference harness predates that profile, so this
module supplies the very small E32 loader needed while collecting traces and
snapshots.  Loaded code is placed directly after the ROM image.  An augmented
ROM written after construction therefore contains the bound modules at the
same virtual addresses and can be translated into the native-only AOT.

Nothing in this module is shipped in the NVDA add-on; it is a migration tool.
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path


E32_UID_DLL = 0x10000079
E32_SIGNATURE = 0x434F5045  # "EPOC", little-endian
COMP_NONE = 0
COMP_DEFLATE = 0x101F7AFC

HUFFMAN_MAX_CODELENGTH = 27
HUFFMAN_METACODE = HUFFMAN_MAX_CODELENGTH + 1
DEFLATE_LENGTH_MAG = 8
DEFLATE_DIST_MAG = 12
DEFLATE_MIN_LENGTH = 3
DEFLATE_DIST_CODE_BASE = 0x200
ENCODING_LITERALS = 256
ENCODING_LENGTHS = (DEFLATE_LENGTH_MAG - 1) * 4
ENCODING_SPECIALS = 1
ENCODING_DISTS = (DEFLATE_DIST_MAG - 1) * 4
ENCODING_LITERAL_LEN = ENCODING_LITERALS + ENCODING_LENGTHS + ENCODING_SPECIALS
ENCODING_EOS = ENCODING_LITERALS + ENCODING_LENGTHS
DEFLATE_CODES = ENCODING_LITERAL_LEN + ENCODING_DISTS

HUFFMAN_META = (
    0x0004006C, 0x00040064, 0x0004005C, 0x00040050, 0x00040044,
    0x0004003C, 0x00040034, 0x00040021, 0x00040023, 0x00040025,
    0x00040027, 0x00040029, 0x00040014, 0x0004000C, 0x00040035,
    0x00390037, 0x00330031, 0x0004002B, 0x002F002D, 0x001F001D,
    0x001B0019, 0x00040013, 0x00170015, 0x0004000D, 0x0011000F,
    0x000B0009, 0x00070003, 0x00050001,
)


def _u32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


class E32LoadError(RuntimeError):
    pass


class _BitInput:
    """MSB-first reader matching Symbian's E32 inflater."""

    def __init__(self, data: bytes):
        self.data = data
        bitlen = len(data) * 8
        if not bitlen:
            self.bits = 0
            self.count = 0
            self.remain = 0
            self.wordpos = 4
            return
        self.bits = self._word(0)
        have = 32
        bitlen -= have
        if bitlen < 0:
            have += bitlen
        self.count = have
        self.remain = bitlen
        self.wordpos = 4

    def _word(self, pos: int) -> int:
        value = 0
        for index in range(4):
            byte = self.data[pos + index] if pos + index < len(self.data) else 0
            value |= byte << (24 - index * 8)
        return value

    def read1(self) -> int:
        current = self.bits
        new_count = self.count - 1
        if new_count < 0:
            return self.read(1)
        self.count = new_count
        self.bits = (current << 1) & 0xFFFFFFFF
        return (current >> 31) & 1

    def read(self, size: int) -> int:
        if not size:
            return 0
        value = 0
        current = self.bits
        self.count -= size
        while self.count < 0:
            if self.count + size:
                value |= (current >> (32 - (self.count + size))) << (-self.count)
            size = -self.count
            if self.remain <= 0:
                raise E32LoadError("compressed E32 bitstream ended early")
            if self.remain >= 32:
                current = self._word(self.wordpos)
            else:
                valid = (self.remain + 7) // 8
                current = 0
                for index in range(valid):
                    if self.wordpos + index < len(self.data):
                        current |= self.data[self.wordpos + index] << (24 - index * 8)
            self.wordpos += 4
            self.count += 32
            self.remain -= 32
            if self.remain < 0:
                self.count += self.remain
        self.bits = 0 if size == 32 else (current << size) & 0xFFFFFFFF
        return value | (current >> (32 - size))

    def meta(self) -> int:
        index = 0
        huffman = 0
        while True:
            index += (huffman >> 16) // 4
            if not 0 <= index < len(HUFFMAN_META):
                raise E32LoadError("invalid E32 meta-Huffman stream")
            huffman = HUFFMAN_META[index]
            if self.read1() == 0:
                huffman = (huffman << 16) & 0xFFFFFFFF
            if huffman & 0x10000:
                return huffman >> 17


def _valid_lengths(lengths: list[int]) -> bool:
    remain = 1 << HUFFMAN_MAX_CODELENGTH
    total = 0
    for length in reversed(lengths):
        if length <= 0:
            continue
        total += length
        if length > HUFFMAN_MAX_CODELENGTH:
            return False
        cell = 1 << (HUFFMAN_MAX_CODELENGTH - length)
        if cell > remain:
            return False
        remain -= cell
    return remain == 0 or total <= 1


def _read_lengths(bits: _BitInput, count: int) -> list[int]:
    move_to_front = list(range(HUFFMAN_METACODE))
    last = 0
    output: list[int] = []
    run = 0
    while len(output) + run < count:
        code = bits.meta()
        if code < 2:
            run += run + code + 1
            continue
        while run:
            output.append(last)
            run -= 1
            if len(output) > count:
                raise E32LoadError("E32 Huffman length table overflow")
        index = code - 1
        if index >= len(move_to_front):
            raise E32LoadError("invalid E32 Huffman MTF index")
        move_to_front[0] = last
        last = move_to_front[index]
        for position in range(index, 0, -1):
            move_to_front[position] = move_to_front[position - 1]
        output.append(last)
    output.extend([last] * run)
    if len(output) != count:
        raise E32LoadError("wrong E32 Huffman length table size")
    return output


def _decoder(lengths: list[int]) -> tuple[list[dict[int, int]], int]:
    maximum = max(lengths, default=0)
    if not maximum:
        return [], 0
    counts = [0] * maximum
    for length in lengths:
        if length:
            counts[length - 1] += 1
    next_code = [0] * maximum
    code = 0
    for index in range(maximum):
        code <<= 1
        next_code[index] = code
        code += counts[index]
    maps: list[dict[int, int]] = [{} for _ in range(maximum + 1)]
    for symbol, length in enumerate(lengths):
        if not length:
            continue
        maps[length][next_code[length - 1]] = symbol
        next_code[length - 1] += 1
    return maps, maximum


def _decode_symbol(bits: _BitInput,
                   decoder: tuple[list[dict[int, int]], int]) -> int:
    maps, maximum = decoder
    code = 0
    for length in range(1, maximum + 1):
        code = (code << 1) | bits.read1()
        if code in maps[length]:
            return maps[length][code]
    raise E32LoadError("invalid E32 Huffman code")


def inflate_e32(data: bytes, expected: int) -> bytes:
    bits = _BitInput(data)
    lengths = _read_lengths(bits, DEFLATE_CODES)
    literal_lengths = lengths[:ENCODING_LITERAL_LEN]
    distance_lengths = lengths[ENCODING_LITERAL_LEN:]
    if not _valid_lengths(literal_lengths) or not _valid_lengths(distance_lengths):
        raise E32LoadError("invalid E32 Huffman tables")
    literals = _decoder(literal_lengths)
    distances = _decoder(distance_lengths)
    output = bytearray()
    while True:
        symbol = _decode_symbol(bits, literals)
        if symbol < ENCODING_LITERALS:
            output.append(symbol)
        elif symbol == ENCODING_EOS:
            break
        else:
            code = (symbol - ENCODING_LITERALS) & 0xFF
            if code >= 8:
                extra = (code >> 2) - 1
                code -= extra << 2
                code = (code << extra) | bits.read(extra)
            length = code + DEFLATE_MIN_LENGTH
            distance_symbol = _decode_symbol(bits, distances) + DEFLATE_DIST_CODE_BASE
            distance_code = (distance_symbol - ENCODING_LITERALS) & 0xFF
            if distance_code >= 8:
                extra = (distance_code >> 2) - 1
                distance_code -= extra << 2
                distance_code = (distance_code << extra) | bits.read(extra)
            distance = distance_code + 1
            if distance > len(output):
                raise E32LoadError("invalid E32 back-reference")
            for _ in range(length):
                output.append(output[-distance])
        if expected and len(output) > expected:
            raise E32LoadError("E32 stream expanded beyond advertised size")
    if expected and len(output) != expected:
        raise E32LoadError("E32 stream size disagrees with the header")
    return bytes(output)


@dataclass
class _Header:
    uid3: int
    compression: int
    code_size: int
    data_size: int
    bss_size: int
    code_base: int
    data_base: int
    dll_count: int
    export_offset: int
    export_count: int
    code_offset: int
    import_offset: int
    code_reloc_offset: int
    header_format: int
    uncompressed_size: int

    @classmethod
    def read(cls, raw: bytes) -> "_Header":
        if len(raw) < 124:
            raise E32LoadError("E32 image is too small")
        uid1 = _u32(raw, 0)
        signature = _u32(raw, 16)
        flags = _u32(raw, 44)
        header_format = (flags >> 24) & 0xF
        header = cls(
            uid3=_u32(raw, 8), compression=_u32(raw, 28),
            code_size=_u32(raw, 48), data_size=_u32(raw, 52),
            bss_size=_u32(raw, 68), code_base=_u32(raw, 76),
            data_base=_u32(raw, 80), dll_count=_u32(raw, 84),
            export_offset=_u32(raw, 88), export_count=_u32(raw, 92),
            code_offset=_u32(raw, 100), import_offset=_u32(raw, 108),
            code_reloc_offset=_u32(raw, 112), header_format=header_format,
            uncompressed_size=(
                _u32(raw, 124) if header_format and len(raw) >= 128
                else len(raw) - _u32(raw, 100)
            ),
        )
        if uid1 != E32_UID_DLL or signature != E32_SIGNATURE:
            raise E32LoadError("not an EKA2 DLL E32Image")
        if not 0 < header.code_size <= 0x400000:
            raise E32LoadError("implausible E32 code size")
        return header


def _expanded_image(raw: bytes, header: _Header) -> bytes:
    if header.compression == COMP_NONE:
        return raw
    if header.compression != COMP_DEFLATE:
        raise E32LoadError("unsupported E32 compression")
    errors = []
    for start in (header.code_offset, header.code_offset + 4):
        if start >= len(raw):
            continue
        try:
            decompressed = inflate_e32(raw[start:], header.uncompressed_size)
            return raw[:header.code_offset] + decompressed
        except E32LoadError as error:
            errors.append(str(error))
    raise E32LoadError("could not decompress E32 image: " + "; ".join(errors))


def _real_dll_name(name: str) -> str:
    cut = len(name)
    for marker in "{[":
        position = name.find(marker)
        if position >= 0:
            cut = min(cut, position)
    base = name[:cut].lower()
    if not base.endswith((".dll", ".exe", ".ldd", ".pdd", ".csy")):
        base += ".dll"
    return base


def _uid_from_import(name: str) -> int:
    opening = name.find("[")
    if opening < 0 or opening + 9 >= len(name) or name[opening + 9] != "]":
        return 0
    try:
        return int(name[opening + 1:opening + 9], 16)
    except ValueError:
        return 0


def _imports(full: bytes, header: _Header) -> list[tuple[str, list[int]]]:
    if not header.import_offset or not header.dll_count:
        return []
    if header.import_offset + 4 > len(full):
        raise E32LoadError("E32 import table is outside image")
    output = []
    position = header.import_offset + 4
    for _ in range(header.dll_count):
        if position + 8 > len(full):
            raise E32LoadError("truncated E32 import block")
        name_offset = _u32(full, position)
        count = struct.unpack_from("<i", full, position + 4)[0]
        position += 8
        if not 0 <= count <= 10000:
            raise E32LoadError("invalid E32 import count")
        name_position = header.import_offset + name_offset
        if name_position >= len(full):
            raise E32LoadError("invalid E32 import name offset")
        name_end = full.find(b"\0", name_position)
        if name_end < 0:
            raise E32LoadError("unterminated E32 import name")
        need = count * 4
        if position + need > len(full):
            raise E32LoadError("truncated E32 import offsets")
        offsets = list(struct.unpack_from(f"<{count}I", full, position))
        position += need
        output.append((full[name_position:name_end].decode("latin1"), offsets))
    return output


def _relocations(full: bytes, offset: int) -> list[tuple[int, int]]:
    if not offset:
        return []
    if offset + 8 > len(full):
        raise E32LoadError("E32 relocation section outside image")
    blocks_size = _u32(full, offset)
    declared = _u32(full, offset + 4)
    if not blocks_size:
        if declared:
            raise E32LoadError("empty E32 relocation section has relocs")
        return []
    end = offset + 8 + blocks_size
    if end > len(full):
        raise E32LoadError("truncated E32 relocation section")
    output = []
    position = offset + 8
    while position < end:
        if position + 8 > end:
            raise E32LoadError("truncated E32 relocation block header")
        page = _u32(full, position)
        block_size = _u32(full, position + 4)
        if page & 0xFFF:
            raise E32LoadError("E32 relocation page is not 4K aligned")
        if block_size < 8 or block_size & 3 or position + block_size > end:
            raise E32LoadError("invalid E32 relocation block")
        for index in range((block_size - 8) // 2):
            relocation = struct.unpack_from("<H", full, position + 8 + index * 2)[0]
            if not relocation:
                continue
            kind = relocation & 0xF000
            if kind not in (0x1000, 0x2000, 0x3000):
                raise E32LoadError("unknown E32 relocation type")
            output.append((page + (relocation & 0x0FFF), kind))
        position += block_size
    if position != end or len(output) != declared:
        raise E32LoadError("E32 relocation count disagrees with the header")
    return output


@dataclass
class ExternalImage:
    name: str
    uid3: int
    code_addr: int
    code_size: int
    exports: list[int]


def _external_images(epoc) -> list[ExternalImage]:
    if not hasattr(epoc, "_e65_external_images"):
        epoc._e65_external_images = []
    return epoc._e65_external_images


def _external_by_name(epoc, name: str) -> ExternalImage | None:
    return next((item for item in _external_images(epoc) if item.name == name), None)


def _external_by_uid3(epoc, uid3: int) -> ExternalImage | None:
    return next((item for item in _external_images(epoc) if item.uid3 == uid3), None)


def _external_alloc(epoc, size: int) -> int:
    if not hasattr(epoc, "_e65_external_next"):
        epoc._e65_external_next = _align(epoc.rom_base + len(epoc.blob), 0x1000)
    run = _align(epoc._e65_external_next, 0x1000)
    end = run + _align(size, 0x1000)
    mapped_end = epoc.rom_base + _align(len(epoc.blob), 0x100000)
    if end > mapped_end:
        raise E32LoadError("E65 external E32 code exceeds ROM padding")
    epoc._e65_external_next = end
    return run


def _rom_images_by_name(epoc) -> dict[str, object]:
    """Index ``Z:\\sys\\bin`` entries from the E65 ROM directory."""
    cached = getattr(epoc, "_e65_rom_images_by_name", None)
    if cached is not None:
        return cached
    from _nokia.harness.romrun import RomImage

    blob = epoc.blob
    base = epoc.rom_base
    output: dict[str, object] = {}
    epoc._e65_rom_images_by_name = output
    if len(blob) < 0x98:
        return output
    root_address = _u32(blob, 0x94)
    if root_address < base:
        return output
    root_offset = root_address - base
    if root_offset + 4 > len(blob):
        return output
    count = _u32(blob, root_offset)
    if not 0 < count <= 32:
        return output
    roots = []
    for index in range(count):
        position = root_offset + 4 + 8 * index
        if position + 8 > len(blob):
            return output
        roots.append(_u32(blob, position + 4))

    stack = [(address, "") for address in roots]
    seen = set()
    while stack:
        address, prefix = stack.pop()
        if address < base:
            continue
        offset = address - base
        if offset in seen or offset + 4 > len(blob):
            continue
        seen.add(offset)
        directory_size = _u32(blob, offset)
        if directory_size < 4 or offset + directory_size > len(blob):
            continue
        position, end = offset + 4, offset + directory_size
        while position + 10 <= end:
            entry_address = _u32(blob, position + 4)
            attributes = blob[position + 8]
            name_length = blob[position + 9]
            position += 10
            if name_length > 127 or position + name_length * 2 > end:
                break
            raw_name = bytes(blob[position:position + name_length * 2])
            decoded = raw_name.decode("utf-16-le", errors="replace")
            name = "".join(c.lower() if ord(c) < 128 else "?" for c in decoded)
            position = _align(position + name_length * 2, 4)
            path = prefix + name
            if attributes & 0x10:
                stack.append((entry_address, path + "\\"))
            elif path.startswith("sys\\bin\\") and entry_address >= base:
                try:
                    output[name] = RomImage(blob, entry_address - base)
                except (IndexError, struct.error):
                    pass
    return output


def load_e32(epoc, path: os.PathLike[str] | str,
             lower_name: str) -> ExternalImage:
    lower_name = lower_name.lower()
    existing = _external_by_name(epoc, lower_name)
    if existing:
        return existing
    raw = Path(path).read_bytes()
    header = _Header.read(raw)
    if header.data_size or header.bss_size:
        raise E32LoadError(
            f"{lower_name}: writable data/BSS is not supported")
    full = _expanded_image(raw, header)
    if header.code_offset + header.code_size > len(full):
        raise E32LoadError(f"{lower_name}: code extends past the E32 image")
    code = bytearray(full[header.code_offset:header.code_offset + header.code_size])
    run = _external_alloc(epoc, header.code_size)

    for import_name, offsets in _imports(full, header):
        real_name = _real_dll_name(import_name)
        dependency = _external_by_name(epoc, real_name)
        exports = dependency.exports if dependency else []
        uid = _uid_from_import(import_name)
        if not exports and uid:
            dependency = _external_by_uid3(epoc, uid)
            if dependency:
                exports = dependency.exports
            else:
                candidates = [image for image in epoc.images
                              if image.uid3 == uid]
                image = max(candidates, key=lambda item: item.export_count,
                            default=None)
                if image:
                    exports = image.exports(epoc.blob, epoc.rom_base)
        if not exports:
            image = _rom_images_by_name(epoc).get(real_name)
            if image:
                exports = image.exports(epoc.blob, epoc.rom_base)
        if not exports:
            raise E32LoadError(
                f"missing import dependency {import_name} ({real_name})")
        for offset in offsets:
            if offset + 4 > len(code):
                raise E32LoadError(f"{lower_name}: import offset outside code")
            info = _u32(code, offset)
            ordinal = info & 0xFFFF
            adjustment = info >> 16
            if not 0 < ordinal <= len(exports) or not exports[ordinal - 1]:
                raise E32LoadError(
                    f"{lower_name}: invalid ordinal {ordinal} in {import_name}")
            struct.pack_into(
                "<I", code, offset,
                (exports[ordinal - 1] + adjustment) & 0xFFFFFFFF)

    code_delta = (run - header.code_base) & 0xFFFFFFFF
    data_delta = (-header.data_base) & 0xFFFFFFFF
    for offset, kind in _relocations(full, header.code_reloc_offset):
        if offset + 4 > len(code):
            raise E32LoadError(f"{lower_name}: relocation outside code")
        value = _u32(code, offset)
        if kind == 0x1000:
            delta = code_delta
        elif kind == 0x2000:
            delta = data_delta
        elif header.code_base <= value <= header.code_base + header.code_size:
            delta = code_delta
        elif header.data_base <= value <= header.data_base + header.data_size + header.bss_size:
            delta = data_delta
        else:
            raise E32LoadError(f"{lower_name}: cannot infer a relocation base")
        struct.pack_into("<I", code, offset, (value + delta) & 0xFFFFFFFF)

    epoc.uc.mem_write(run, bytes(code))
    exports = []
    if header.export_count:
        need = header.export_offset + header.export_count * 4
        if need > len(full):
            raise E32LoadError(f"{lower_name}: export table outside image")
        for index in range(header.export_count):
            address = _u32(full, header.export_offset + index * 4)
            exports.append(
                (run + address - header.code_base) & 0xFFFFFFFF if address else 0)
    image = ExternalImage(lower_name, header.uid3, run, header.code_size, exports)
    _external_images(epoc).append(image)
    return image


def load_e65_speech_modules(epoc, file_server) -> ExternalImage:
    nlp = file_server.resolve("\\sys\\bin\\asrsnlphwdevice.dll")
    dev = file_server.resolve("\\sys\\bin\\nssdevtts.dll")
    if not nlp or not dev:
        raise E32LoadError(
            "E65 speech DLLs are missing from files\\sys\\bin")
    load_e32(epoc, nlp, "asrsnlphwdevice.dll")
    return load_e32(epoc, dev, "nssdevtts.dll")


def install_e65_reference_support() -> None:
    """Teach the preserved Python ``DevTts`` class about ROFS speech DLLs."""
    from _nokia.harness import devtts as module
    from _nokia.harness.epoc import Epoc
    from _nokia.harness.f32 import FileServer

    if getattr(module.DevTts, "_e65_reference_support", False):
        return

    def patched_init(self, rom, tree, verbose=False):
        self.epoc = Epoc(rom, verbose=verbose)
        self.epoc.fs = FileServer(tree, verbose=verbose)
        self.epoc.bootstrap()
        self.uc = self.epoc.uc
        image = self.epoc.image_by_uid3(module.UID_DEVTTS)
        if image:
            self.eps = image.exports(self.epoc.blob, self.epoc.rom_base)
        else:
            self.eps = load_e65_speech_modules(
                self.epoc, self.epoc.fs).exports
        common = self.epoc.image_by_uid3(module.UID_TTSCOMMON)
        if not common:
            raise E32LoadError("ROM has no nssttscommon.dll")
        self.common_eps = common.exports(self.epoc.blob, self.epoc.rom_base)
        self.pcm = bytearray()
        self.events = []
        self.pending = []
        self.done = False
        self.dev = None
        self.observer = self._observer()

    patched_init._e65_reference_support = True
    module.DevTts.__init__ = patched_init
    module.DevTts._e65_reference_support = True


def augmented_rom_bytes(epoc) -> bytes:
    """Return the XIP ROM plus bound E65 modules at their run addresses."""
    end = epoc.rom_base + len(epoc.blob)
    for image in _external_images(epoc):
        end = max(end, image.code_addr + image.code_size)
    size = end - epoc.rom_base
    return bytes(epoc.uc.mem_read(epoc.rom_base, size))


def write_augmented_rom(epoc, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(augmented_rom_bytes(epoc))
