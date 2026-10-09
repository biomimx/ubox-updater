# uBox Updater

Desktop application (Windows, macOS) that updates the firmware of the **BiomimX uBox Pro** over USB,
without Arduino IDE or Teensy Loader.

## For customers

1. Download the latest release for your system from the
   [Releases](https://github.com/biomimx/ubox-updater/releases/latest) page and unzip it.
   - Windows: run `uBox Updater.exe` (SmartScreen may ask to confirm: *More info → Run anyway*).
   - macOS: move `uBox Updater.app` to Applications; first launch with right-click → *Open*.
2. Switch the uBox on and connect it to the computer with the USB cable.
3. The app shows the connected uBox and its firmware version, and proposes the newest firmware for its
   variant (PHOENIX / STANDARD). Press **Update**. The uBox restarts by itself; settings, patterns and
   counters are preserved.

The app contains the firmware files of its release and, when online, also offers newer files published
here. *Open file...* lets you use a `.hex` file received from BiomimX.

## How it works

- The uBox answers `V` on its USB serial port with `uBox Pro firmware v8.5 STANDARD` (firmware ≥ v8.4).
- The `.hex` file contains the same string: the app reads it from the file and refuses a variant mismatch.
- Opening the serial port at 134 baud makes the Teensy 4.1 reboot into its HalfKay bootloader (this is
  what Arduino IDE does), so it also works with firmware older than v8.4 (variant to be confirmed by the user).
- The bootloader is programmed over HID with the same protocol as PJRC's `teensy_loader_cli`
  (`ubox_updater/halfkay.py`), then rebooted; the app reads `V` again to confirm.

## Releasing a new firmware

1. Copy the new `uBox_Teensy_v<ver>_PHOENIX.hex` and `..._STANDARD.hex` into `firmware/`
   (the version string inside the file is what counts, not the file name).
2. Bump `APP_VERSION` in `ubox_updater/version.py` if the app changed.
3. Commit, tag (`git tag v1.1.0 && git push --tags`). GitHub Actions builds the Windows and macOS apps and
   publishes a Release with the apps, the `.hex` files and `manifest.json`; the app on customers' PCs sees
   the new files on its next start.

## Development

```
pip install -r requirements.txt
python run_updater.py
```
Local packaging: `build_local.sh` / `build_local.bat`.
