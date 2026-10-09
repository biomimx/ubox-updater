"""Where firmware images come from: bundled with the app, downloaded from the BiomimX
GitHub release, or a file chosen by the user.

Online manifest (attached to every release by the build workflow):
  https://github.com/<REPO>/releases/latest/download/manifest.json
  {"generated": "...", "firmware": [{"file": "...hex", "version": "8.5", "variant": "STANDARD",
                                     "sha256": "...", "url": "https://github.com/.../releases/download/v1.0.0/...hex"}]}
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
import urllib.request
from dataclasses import dataclass, field

from .ihex import FirmwareImage, load_hex, parse_hex_text, version_tuple

REPO = "biomimx/ubox-updater"
MANIFEST_URL = f"https://github.com/{REPO}/releases/latest/download/manifest.json"
USER_AGENT = "uBox-Updater"


@dataclass
class FirmwareEntry:
    version: str
    variant: str
    origin: str                      # "bundled" | "online" | "file"
    path: str | None = None          # local .hex (bundled / file)
    url: str | None = None           # online
    sha256: str | None = None
    image: FirmwareImage | None = field(default=None, repr=False)

    @property
    def label(self) -> str:
        tag = {"bundled": "included", "online": "online", "file": "file"}[self.origin]
        desc = "uNMC / uLung, uHeart 0.25 bar" if self.variant == "PHOENIX" else "uHeart 0.35 bar"
        return f"v{self.version} {self.variant} - {desc}  ({tag})"

    def load(self, progress=None) -> FirmwareImage:
        if self.image:
            return self.image
        if self.path:
            self.image = load_hex(self.path)
        elif self.url:
            req = urllib.request.Request(self.url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
            if self.sha256 and hashlib.sha256(raw).hexdigest() != self.sha256:
                raise ValueError("Downloaded file is corrupted (checksum mismatch)")
            self.image = parse_hex_text(raw.decode("ascii"), source=self.url)
        else:
            raise ValueError("No source for this firmware")
        if self.image.version != self.version or self.image.variant != self.variant:
            raise ValueError(f"File content ({self.image.label}) does not match its name ({self.label})")
        return self.image


def bundled_dir() -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "firmware")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "firmware")


def bundled_firmware() -> list[FirmwareEntry]:
    out = []
    for path in sorted(glob.glob(os.path.join(bundled_dir(), "*.hex"))):
        try:
            img = load_hex(path)
        except Exception:
            continue
        if img.version and img.variant:
            out.append(FirmwareEntry(img.version, img.variant, "bundled", path=path, sha256=img.sha256, image=img))
    return out


def online_firmware(timeout_s: float = 8.0) -> list[FirmwareEntry]:
    req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout_s) as r:
        manifest = json.loads(r.read().decode("utf-8"))
    out = []
    for fw in manifest.get("firmware", []):
        out.append(FirmwareEntry(fw["version"], fw["variant"], "online", url=fw["url"], sha256=fw.get("sha256")))
    return out


def file_firmware(path: str) -> FirmwareEntry:
    img = load_hex(path)
    if not (img.version and img.variant):
        raise ValueError("This .hex file is not a uBox Pro firmware (no version string found)")
    return FirmwareEntry(img.version, img.variant, "file", path=path, sha256=img.sha256, image=img)


def merge(entries: list[FirmwareEntry]) -> list[FirmwareEntry]:
    """One entry per (version, variant); local copies win over online ones. Newest first."""
    best: dict[tuple, FirmwareEntry] = {}
    rank = {"file": 0, "bundled": 1, "online": 2}
    for e in entries:
        k = (e.version, e.variant)
        if k not in best or rank[e.origin] < rank[best[k].origin]:
            best[k] = e
    return sorted(best.values(), key=lambda e: (version_tuple(e.version), e.variant), reverse=True)
