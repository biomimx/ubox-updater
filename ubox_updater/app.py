"""uBox Updater - Tkinter GUI."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import sources, updater
from .version import APP_VERSION

PAD = 10


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"uBox Updater {APP_VERSION}")
        self.resizable(False, False)
        self.q: queue.Queue = queue.Queue()
        self.ubox = None
        self.entries: list[sources.FirmwareEntry] = []
        self.busy = False
        self._build()
        self.after(100, self._poll)
        self.after(200, self.refresh)
        self.after(600, self.check_online)

    # ---------------------------------------------------------------- UI
    def _build(self):
        f = ttk.Frame(self, padding=PAD)
        f.grid(sticky="nsew")

        ttk.Label(f, text="uBox Pro firmware update", font=("", 15, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")

        # device
        box = ttk.LabelFrame(f, text="uBox", padding=PAD)
        box.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(PAD, 0))
        self.dev_var = tk.StringVar(value="Searching...")
        ttk.Label(box, textvariable=self.dev_var, width=60).grid(row=0, column=0, sticky="w")
        self.btn_refresh = ttk.Button(box, text="Refresh", command=self.refresh)
        self.btn_refresh.grid(row=0, column=1, padx=(PAD, 0))

        # firmware
        fw = ttk.LabelFrame(f, text="Firmware", padding=PAD)
        fw.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(PAD, 0))
        self.fw_var = tk.StringVar()
        self.fw_combo = ttk.Combobox(fw, textvariable=self.fw_var, state="readonly", width=48)
        self.fw_combo.grid(row=0, column=0, sticky="w")
        ttk.Button(fw, text="Open file...", command=self.open_file).grid(row=0, column=1, padx=(PAD, 0))
        self.online_var = tk.StringVar(value="")
        ttk.Label(fw, textvariable=self.online_var, foreground="#666").grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(fw, text="I know the variant of this uBox (needed only for firmware older than v8.4)",
                        variable=self.force_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # action
        self.btn_update = ttk.Button(f, text="Update", command=self.start_update, state="disabled")
        self.btn_update.grid(row=3, column=0, sticky="w", pady=(PAD, 0))
        self.progress = ttk.Progressbar(f, length=420, mode="determinate", maximum=1000)
        self.progress.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(PAD, 0), pady=(PAD, 0))

        # log
        self.log_box = tk.Text(f, height=12, width=78, state="disabled", wrap="word", font=("Menlo", 10) if self.tk.call("tk", "windowingsystem") == "aqua" else ("Consolas", 9))
        self.log_box.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(PAD, 0))

        ttk.Label(f, text="BiomimX Srl - keep the USB cable connected and the uBox powered during the update.",
                  foreground="#666").grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))

    def log(self, msg: str):
        self.q.put(("log", msg))

    def set_progress(self, v: float):
        self.q.put(("progress", v))

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.log_box.configure(state="normal")
                    self.log_box.insert("end", val + "\n")
                    self.log_box.see("end")
                    self.log_box.configure(state="disabled")
                elif kind == "progress":
                    self.progress["value"] = int(val * 1000)
                elif kind == "device":
                    self.ubox = val
                    self._update_device_label()
                elif kind == "entries":
                    self._merge_entries(val)
                elif kind == "online":
                    self.online_var.set(val)
                elif kind == "done":
                    self.busy = False
                    self._set_buttons()
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _set_buttons(self):
        st = "disabled" if self.busy else "normal"
        self.btn_refresh.configure(state=st)
        self.btn_update.configure(state="normal" if (not self.busy and self.ubox and self.entries) else "disabled")

    def _update_device_label(self):
        u = self.ubox
        if u is None:
            self.dev_var.set("No uBox found. Connect the USB cable (switch the uBox on) and press Refresh.")
        elif u.port == "bootloader":
            self.dev_var.set("uBox in programming mode (variant unknown): tick 'I know the variant' to update.")
        elif u.version:
            self.dev_var.set(f"Connected on {u.port}: firmware v{u.version} {u.variant}")
        else:
            self.dev_var.set(f"Connected on {u.port}: firmware older than v8.4 (cannot report version/variant)")
        self._select_default()
        self._set_buttons()

    def _merge_entries(self, new):
        self.entries = sources.merge(self.entries + new)
        self.fw_combo["values"] = [e.label for e in self.entries]
        self._select_default()
        self._set_buttons()

    def _select_default(self):
        if not self.entries:
            return
        variant = self.ubox.variant if self.ubox else None
        pick = next((e for e in self.entries if variant is None or e.variant == variant), self.entries[0])
        self.fw_combo.current(self.entries.index(pick))

    def _selected(self) -> sources.FirmwareEntry | None:
        i = self.fw_combo.current()
        return self.entries[i] if 0 <= i < len(self.entries) else None

    # ---------------------------------------------------------------- actions
    def refresh(self):
        if self.busy:
            return
        self.busy = True
        self._set_buttons()
        self.dev_var.set("Searching...")
        if not self.entries:
            self.q.put(("entries", sources.bundled_firmware()))

        def work():
            try:
                u = updater.detect(self.log)
                if u is None:
                    self.log("No uBox found on USB.")
                self.q.put(("device", u))
            except Exception as e:
                self.log(f"Error while looking for the uBox: {e}")
                self.q.put(("device", None))
            finally:
                self.q.put(("done", None))
        threading.Thread(target=work, daemon=True).start()

    def check_online(self):
        def work():
            try:
                ent = sources.online_firmware()
                self.q.put(("entries", ent))
                self.q.put(("online", f"Online: {len(ent)} firmware file(s) available from BiomimX." if ent else "Online: no firmware published."))
            except Exception:
                self.q.put(("online", "Online check not available (no connection). Included firmware can still be used."))
        threading.Thread(target=work, daemon=True).start()

    def open_file(self):
        path = filedialog.askopenfilename(title="Choose a uBox firmware file", filetypes=[("Firmware", "*.hex"), ("All files", "*.*")])
        if not path:
            return
        try:
            e = sources.file_firmware(path)
        except Exception as ex:
            messagebox.showerror("uBox Updater", f"Cannot use this file:\n{ex}")
            return
        self._merge_entries([e])
        self.fw_combo.current(self.entries.index(next(x for x in self.entries if x.version == e.version and x.variant == e.variant)))
        self.log(f"Loaded {path}: {e.label}")

    def start_update(self):
        e = self._selected()
        if not e or self.busy:
            return
        u = self.ubox
        if u and u.version and e.version == u.version and e.variant == u.variant:
            if not messagebox.askyesno("uBox Updater", f"The uBox already runs v{u.version} {u.variant}. Write it again?"):
                return
        if u and u.variant and u.variant != e.variant:
            messagebox.showerror("uBox Updater", f"This uBox is {u.variant}: choose the {u.variant} firmware.")
            return
        if not messagebox.askokcancel("uBox Updater", f"Write {e.label} to the uBox?\n\nThe uBox will restart. Settings, patterns and counters are preserved."):
            return
        self.busy = True
        self._set_buttons()
        self.progress["value"] = 0

        def work():
            try:
                info = updater.run_update(e, u, self.log, self.set_progress, force_variant=self.force_var.get())
                self.q.put(("device", info if info else None))
                if info and info.version == e.version:
                    self.q.put(("log", "Done."))
            except Exception as ex:
                self.log(f"ERROR: {ex}")
                self.q.put(("log", "If the uBox shows 'Programming mode', unplug USB, remove power for 5 s, power on, and retry."))
            finally:
                self.q.put(("done", None))
        threading.Thread(target=work, daemon=True).start()


def main():
    App().mainloop()
