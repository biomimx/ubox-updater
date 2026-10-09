"""Intel HEX parsing for Teensy 4.1 images (IMXRT1062, flash mapped at 0x60000000).

Mirrors the behaviour of PJRC's teensy_loader_cli: extended linear addresses in the
0x60000000 window are rebased to 0, the image is held in a flat bytearray filled with
0xFF, and blocks that are entirely 0xFF are skipped when programming (except the first).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

TEENSY41_CODE_SIZE = 8126464
TEENSY41_BLOCK_SIZE = 1024
FLASH_BASE = 0x60000000

_FW_RE = re.compile(rb"uBox Pro firmware v(\d+(?:\.\d+)*) (PHOENIX|STANDARD)")


class HexError(ValueError):
    pass


@dataclass
class FirmwareImage:
    data: bytearray            # flat image, len == TEENSY41_CODE_SIZE, unused = 0xFF
    used_end: int              # highest used address + 1
    version: str | None        # "8.5"
    variant: str | None        # "PHOENIX" | "STANDARD"
    sha256: str
    source: str                # file path or label

    @property
    def label(self) -> str:
        if self.version and self.variant:
            return f"v{self.version} {self.variant}"
        return "unknown firmware"

    def blocks(self):
        """Yield (addr, bytes) for every block to program (first block always, blank blocks skipped)."""
        bs = TEENSY41_BLOCK_SIZE
        blank = b"\xff" * bs
        for addr in range(0, self.used_end, bs):
            chunk = bytes(self.data[addr:addr + bs])
            if addr != 0 and chunk == blank:
                continue
            yield addr, chunk

    def block_count(self) -> int:
        return sum(1 for _ in self.blocks())


def parse_hex_text(text: str, source: str = "<memory>") -> FirmwareImage:
    data = bytearray(b"\xff" * TEENSY41_CODE_SIZE)
    ext = 0
    used_end = 0
    any_data = False
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line[0] != ":":
            raise HexError(f"{source}: line {lineno}: missing ':'")
        try:
            rec = bytes.fromhex(line[1:])
        except ValueError:
            raise HexError(f"{source}: line {lineno}: bad hex characters")
        if len(rec) < 5:
            raise HexError(f"{source}: line {lineno}: record too short")
        n, addr_lo, rtype = rec[0], (rec[1] << 8) | rec[2], rec[3]
        payload, chk = rec[4:4 + n], rec[4 + n]
        if len(payload) != n or (sum(rec[:4 + n]) + chk) & 0xFF != 0:
            raise HexError(f"{source}: line {lineno}: checksum error")
        if rtype == 0x00:
            addr = ext + addr_lo
            if addr + n > TEENSY41_CODE_SIZE:
                raise HexError(f"{source}: line {lineno}: address 0x{addr:08X} outside Teensy 4.1 flash")
            data[addr:addr + n] = payload
            used_end = max(used_end, addr + n)
            any_data = True
        elif rtype == 0x01:
            break
        elif rtype == 0x02:
            ext = ((payload[0] << 8) | payload[1]) << 4
        elif rtype == 0x04:
            ext = ((payload[0] << 8) | payload[1]) << 16
            if FLASH_BASE <= ext < FLASH_BASE + TEENSY41_CODE_SIZE:
                ext -= FLASH_BASE
        elif rtype in (0x03, 0x05):
            continue
        else:
            raise HexError(f"{source}: line {lineno}: unknown record type {rtype}")
    if not any_data:
        raise HexError(f"{source}: no data records")
    # Teensy 4.x images start with the FlexSPI configuration block ("FCFB") at address 0.
    if data[0:4] != b"FCFB":
        raise HexError(f"{source}: not a Teensy 4.x image (no FCFB header)")
    m = _FW_RE.search(bytes(data[:used_end]))
    version = m.group(1).decode() if m else None
    variant = m.group(2).decode() if m else None
    sha = hashlib.sha256(bytes(data[:used_end])).hexdigest()
    return FirmwareImage(data, used_end, version, variant, sha, source)


def load_hex(path: str) -> FirmwareImage:
    with open(path, "r", encoding="ascii", errors="strict") as f:
        return parse_hex_text(f.read(), source=path)


def version_tuple(v: str) -> tuple:
    return tuple(int(x) for x in v.split("."))
