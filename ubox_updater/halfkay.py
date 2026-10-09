"""HalfKay bootloader client for Teensy 4.1 over HID (same protocol as PJRC's teensy_loader_cli).

Device: VID 0x16C0, PID 0x0478. Each write is an output report (ID 0) of 64 header bytes +
1024 data bytes: header[0..2] = address (little endian, 24 bit), rest zero. The first blocks
can take a long time because they trigger the flash erase, so they are retried for up to 45 s.
A block with header FF FF FF reboots the Teensy into the freshly written program.
"""
from __future__ import annotations

import time
from typing import Callable

import hid  # package "hidapi"

from .ihex import FirmwareImage, TEENSY41_BLOCK_SIZE

HALFKAY_VID = 0x16C0
HALFKAY_PID = 0x0478
WRITE_SIZE = TEENSY41_BLOCK_SIZE + 64


class HalfKayError(RuntimeError):
    pass


def find_bootloader() -> dict | None:
    for d in hid.enumerate(HALFKAY_VID, HALFKAY_PID):
        return d
    return None


def wait_for_bootloader(timeout_s: float, poll_s: float = 0.25) -> dict:
    t0 = time.monotonic()
    while True:
        d = find_bootloader()
        if d:
            return d
        if time.monotonic() - t0 > timeout_s:
            raise HalfKayError("Teensy bootloader not found on USB")
        time.sleep(poll_s)


class HalfKay:
    def __init__(self, info: dict | None = None):
        self.info = info or find_bootloader()
        if not self.info:
            raise HalfKayError("Teensy bootloader not found on USB")
        self.dev = hid.device()
        self.dev.open_path(self.info["path"])

    def close(self):
        try:
            self.dev.close()
        except Exception:
            pass

    def _write(self, buf: bytes, timeout_s: float) -> None:
        assert len(buf) == WRITE_SIZE
        report = b"\x00" + buf                     # report ID 0
        t0 = time.monotonic()
        last_err = None
        while True:
            try:
                n = self.dev.write(report)
                if n == len(report) or n == WRITE_SIZE:
                    return
                last_err = f"short write ({n})"
            except Exception as e:                # hidapi raises while the device is busy erasing
                last_err = str(e)
            if time.monotonic() - t0 > timeout_s:
                raise HalfKayError(f"USB write failed: {last_err}")
            time.sleep(0.01)

    def program(self, img: FirmwareImage, progress: Callable[[int, int], None] | None = None) -> None:
        total = img.block_count()
        done = 0
        for addr, chunk in img.blocks():
            hdr = bytes([addr & 0xFF, (addr >> 8) & 0xFF, (addr >> 16) & 0xFF]) + bytes(61)
            self._write(hdr + chunk, 45.0 if done < 5 else 0.5)
            done += 1
            if progress:
                progress(done, total)

    def reboot(self) -> None:
        buf = bytes([0xFF, 0xFF, 0xFF]) + bytes(WRITE_SIZE - 3)
        self._write(buf, 0.5)
