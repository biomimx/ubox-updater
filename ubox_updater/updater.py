"""The update sequence, independent of the GUI (runs in a worker thread).

  1. find the uBox serial port, send 'V'  -> version / variant (None for firmware < v8.4)
  2. check the chosen image against the uBox (variant must match unless forced)
  3. reboot into the bootloader (134 baud) and wait for the HalfKay HID device
  4. program every block, then reboot
  5. wait for the uBox serial port to come back and read 'V' again
"""
from __future__ import annotations

import time
from typing import Callable

from . import halfkay, ubox_serial
from .ihex import FirmwareImage
from .sources import FirmwareEntry

Log = Callable[[str], None]
Progress = Callable[[float], None]       # 0..1


class UpdateError(RuntimeError):
    pass


def detect(log: Log) -> ubox_serial.UBoxInfo | None:
    """Return the connected uBox (serial) or None. Also recognises a uBox already in bootloader mode."""
    ports = ubox_serial.list_ubox_ports()
    if ports:
        info = ubox_serial.identify(ports[0])
        if info.version:
            log(f"uBox Pro found on {info.port}: firmware v{info.version} {info.variant}")
        else:
            log(f"uBox Pro found on {info.port}: firmware older than v8.4 (version unknown)")
        return info
    if halfkay.find_bootloader():
        log("Teensy in programming mode found (uBox already rebooted into the bootloader)")
        return ubox_serial.UBoxInfo("bootloader", None, None, "")
    return None


def run_update(entry: FirmwareEntry, ubox: ubox_serial.UBoxInfo | None, log: Log, progress: Progress,
               force_variant: bool = False) -> ubox_serial.UBoxInfo | None:
    img: FirmwareImage = entry.load()
    log(f"Firmware image: {img.label}, {img.block_count()} blocks of 1 kB, sha256 {img.sha256[:12]}...")

    if ubox is None:
        raise UpdateError("No uBox connected. Connect the USB cable and press Refresh.")

    if ubox.variant and ubox.variant != img.variant and not force_variant:
        raise UpdateError(f"Variant mismatch: the uBox is {ubox.variant}, the file is {img.variant}. "
                          f"Choose the {ubox.variant} firmware.")
    if not ubox.variant and ubox.port != "bootloader" and not force_variant:
        raise UpdateError("This uBox runs a firmware older than v8.4 and cannot report its variant. "
                          "Tick 'I know the variant' only if you are sure which file applies (PHOENIX = uNMC/uLung "
                          "version with uHeart 0.25 bar; STANDARD = all others).")

    # 1. into the bootloader
    if ubox.port != "bootloader":
        log("Rebooting the uBox into programming mode...")
        progress(0.02)
        ubox_serial.enter_bootloader(ubox.port)
    log("Waiting for the Teensy bootloader...")
    try:
        info = halfkay.wait_for_bootloader(15.0)
    except halfkay.HalfKayError:
        raise UpdateError("The uBox did not enter programming mode. On the uBox go to Settings -> Firmware update -> GO "
                          "(firmware v8.4 or later), then press Update again.")
    progress(0.05)

    # 2. program
    hk = halfkay.HalfKay(info)
    try:
        log("Programming (the first blocks erase the flash and can take up to a minute)...")
        t0 = time.monotonic()

        def on_block(done, total):
            progress(0.05 + 0.90 * done / total)

        hk.program(img, on_block)
        log(f"Programming done in {time.monotonic() - t0:.1f} s. Rebooting the uBox...")
        hk.reboot()
    finally:
        hk.close()
    progress(0.96)

    # 3. verify
    try:
        port = ubox_serial.wait_for_ubox(20.0)
        time.sleep(1.5)                       # let the firmware finish booting (EEPROM, display)
        info2 = ubox_serial.identify(port)
    except TimeoutError:
        log("The uBox did not reappear on USB within 20 s: check it on the display (Settings shows the version).")
        progress(1.0)
        return None
    if info2.version:
        ok = (info2.version == img.version and info2.variant == img.variant)
        log(f"uBox reports firmware v{info2.version} {info2.variant}" + (" - update successful." if ok else " - UNEXPECTED, please retry."))
        if not ok:
            raise UpdateError("The uBox reports a different firmware than the one written.")
    else:
        log("uBox back on USB but it did not answer the version request.")
    progress(1.0)
    return info2
