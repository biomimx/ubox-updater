#!/usr/bin/env python3
"""Build manifest.json for a release from the .hex files in firmware/.

usage: make_manifest.py <tag> <out.json> [firmware_dir]
The download URL of each file is https://github.com/<REPO>/releases/download/<tag>/<file>.
"""
import datetime, hashlib, json, os, sys, glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ubox_updater.ihex import load_hex, version_tuple
from ubox_updater.sources import REPO

tag, out = sys.argv[1], sys.argv[2]
fw_dir = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(__file__), "..", "firmware")
items = []
for path in sorted(glob.glob(os.path.join(fw_dir, "*.hex"))):
    img = load_hex(path)
    if not (img.version and img.variant):
        print("skip (no version string):", path); continue
    with open(path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    name = os.path.basename(path)
    items.append({"file": name, "version": img.version, "variant": img.variant, "sha256": sha,
                  "url": f"https://github.com/{REPO}/releases/download/{tag}/{name}"})
items.sort(key=lambda x: (version_tuple(x["version"]), x["variant"]), reverse=True)
json.dump({"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "tag": tag, "firmware": items}, open(out, "w"), indent=2)
print(f"{out}: {len(items)} firmware files")
