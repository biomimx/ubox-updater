"""Talk to a running uBox Pro over its USB serial port (Teensy USB Serial, VID 0x16C0 PID 0x0483).

- identify(): sends 'V' and parses "uBox Pro firmware v8.5 STANDARD" (firmware >= v8.4).
- enter_bootloader(): opens the port at 134 baud, which the Teensy core treats as the request
  to reboot into the HalfKay bootloader (this is what Arduino IDE does before every upload and
  works with any uBox firmware, v8.1 included).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

import serial
from serial.tools import list_ports

TEENSY_SERIAL_VID = 0x16C0
TEENSY_SERIAL_PIDS = {0x0483, 0x0489, 0x048B, 0x04D0, 0x04D1}   # Serial, Serial+MIDI, Serial+MIDI+Audio, ...

_V_RE = re.compile(r"uBox Pro firmware v(\d+(?:\.\d+)*) (PHOENIX|STANDARD)")


@dataclass
class UBoxInfo:
    port: str
    version: str | None
    variant: str | None
    raw: str


def list_ubox_ports() -> list[str]:
    ports = []
    for p in list_ports.comports():
        if p.vid == TEENSY_SERIAL_VID and (p.pid in TEENSY_SERIAL_PIDS or p.pid is None):
            ports.append(p.device)
    return sorted(ports)


def identify(port: str, timeout_s: float = 2.5) -> UBoxInfo:
    """Send 'V' and collect the reply. Older firmware (< v8.4) ignores 'V': version stays None."""
    with serial.Serial(port, 115200, timeout=0.2, write_timeout=1.0) as s:
        time.sleep(0.3)                      # let the port settle (and the firmware notice DTR)
        s.reset_input_buffer()
        s.write(b"V")
        s.flush()
        buf = b""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout_s:
            buf += s.read(256)
            m = _V_RE.search(buf.decode("ascii", "replace"))
            if m:
                return UBoxInfo(port, m.group(1), m.group(2), buf.decode("ascii", "replace"))
    return UBoxInfo(port, None, None, buf.decode("ascii", "replace"))


def enter_bootloader(port: str) -> None:
    """Reboot the uBox into the HalfKay bootloader by opening the port at 134 baud."""
    try:
        s = serial.Serial()
        s.port = port
        s.baudrate = 134
        s.timeout = 0.5
        s.open()
        time.sleep(0.3)
        s.close()
    except serial.SerialException as e:
        # The device often disappears while the port is still open: that is the reboot happening.
        msg = str(e).lower()
        if "device" in msg or "disconnected" in msg or "not configured" in msg or "input/output" in msg:
            return
        raise


def wait_for_ubox(timeout_s: float, poll_s: float = 0.5) -> str:
    """Wait for a uBox serial port to (re)appear after programming."""
    t0 = time.monotonic()
    while True:
        ports = list_ubox_ports()
        if ports:
            return ports[0]
        if time.monotonic() - t0 > timeout_s:
            raise TimeoutError("uBox did not reappear on USB")
        time.sleep(poll_s)
