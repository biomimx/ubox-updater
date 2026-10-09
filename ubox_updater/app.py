"""uBox Updater - Tkinter GUI."""
from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import sources, updater
from .version import APP_VERSION

# palette
NAVY = "#1f3864"
ACCENT = "#2e5597"
BG = "#f4f5f7"
CARD = "#ffffff"
BORDER = "#d9dde3"
TEXT = "#222222"
MUTED = "#6b7280"
GREEN = "#2e7d32"
ORANGE = "#d97706"
RED = "#bd1724"

IS_MAC = sys.platform == "darwin"
FONT = "Helvetica Neue" if IS_MAC else "Segoe UI"
MONO = "Menlo" if IS_MAC else "Consolas"
if IS_MAC:
    # Aqua ttk widgets paint their own frame with the window background: use it for the cards so
    # buttons and menus do not sit in a differently coloured rectangle.
    CARD = "systemWindowBackgroundColor"
    BG = "#e3e5e9"


class Card(tk.Frame):
    """White panel with a numbered title and a status dot."""

    def __init__(self, master, number: str, title: str):
        super().__init__(master, bg=CARD, highlightbackground=BORDER, highlightthickness=1, padx=16, pady=12)
        head = tk.Frame(self, bg=CARD)
        head.pack(fill="x")
        self.dot = tk.Canvas(head, width=14, height=14, bg=CARD, highlightthickness=0)
        self.dot.pack(side="left", padx=(0, 8))
        self._dot = self.dot.create_oval(2, 2, 12, 12, fill=BORDER, outline="")
        tk.Label(head, text=number, bg=CARD, fg=ACCENT, font=(FONT, 11, "bold")).pack(side="left")
        tk.Label(head, text=title, bg=CARD, fg=TEXT, font=(FONT, 13, "bold")).pack(side="left", padx=(6, 0))
        self.body = tk.Frame(self, bg=CARD)
        self.body.pack(fill="x", pady=(8, 0))

    def set_state(self, color: str):
        self.dot.itemconfigure(self._dot, fill=color)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"uBox Updater {APP_VERSION}")
        if IS_MAC:
            try:   # always light appearance, whatever the system setting (dark widgets on light cards look broken)
                self.tk.call("::tk::unsupported::MacWindowStyle", "appearance", self._w, "aqua")
            except tk.TclError:
                pass
        self.configure(bg=BG)
        self.resizable(False, False)
        self.q: queue.Queue = queue.Queue()
        self.ubox = None
        self.entries: list[sources.FirmwareEntry] = []
        self.busy = False
        self._style()
        self._build()
        self.after(100, self._poll)
        self.after(200, self.refresh)
        self.after(600, self.check_online)

    # ---------------------------------------------------------------- UI
    def _style(self):
        st = ttk.Style(self)
        if not IS_MAC:
            try:
                st.theme_use("vista" if sys.platform.startswith("win") else "clam")
            except tk.TclError:
                pass
        st.configure("TButton", font=(FONT, 11), padding=(12, 4))
        st.configure("Primary.TButton", font=(FONT, 13, "bold"), padding=(22, 8))
        st.configure("TCombobox", font=(FONT, 11))
        st.configure("Horizontal.TProgressbar", troughcolor=BORDER, background=ACCENT, thickness=14)
        st.configure("TCheckbutton", background=CARD, font=(FONT, 10))

    def _build(self):
        # header band
        hdr = tk.Frame(self, bg=NAVY, padx=24, pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text="uBox Updater", bg=NAVY, fg="white", font=(FONT, 20, "bold")).pack(side="left")
        tk.Label(hdr, text="uBox Pro firmware update  ·  BiomimX", bg=NAVY, fg="#b8c4dc", font=(FONT, 11)).pack(side="left", padx=(14, 0), pady=(6, 0))
        tk.Label(hdr, text=f"v{APP_VERSION}", bg=NAVY, fg="#b8c4dc", font=(FONT, 10)).pack(side="right", pady=(6, 0))

        body = tk.Frame(self, bg=BG, padx=24, pady=18)
        body.pack(fill="both", expand=True)

        # card 1: device
        self.c1 = Card(body, "1", "Connect the uBox")
        self.c1.pack(fill="x")
        self.dev_var = tk.StringVar(value="Searching...")
        tk.Label(self.c1.body, textvariable=self.dev_var, bg=CARD, fg=TEXT, font=(FONT, 11), anchor="w", justify="left", wraplength=520).pack(side="left", fill="x", expand=True)
        self.btn_refresh = ttk.Button(self.c1.body, text="Refresh", command=self.refresh)
        self.btn_refresh.pack(side="right", padx=(12, 0))

        # card 2: firmware
        self.c2 = Card(body, "2", "Choose the firmware")
        self.c2.pack(fill="x", pady=(12, 0))
        row = tk.Frame(self.c2.body, bg=CARD)
        row.pack(fill="x")
        self.fw_var = tk.StringVar()
        self.fw_combo = ttk.Combobox(row, textvariable=self.fw_var, state="readonly", width=40, font=(FONT, 11))
        self.fw_combo.pack(side="left")
        ttk.Button(row, text="Open file...", command=self.open_file).pack(side="left", padx=(10, 0))
        self.online_var = tk.StringVar(value="Checking for firmware published online...")
        tk.Label(self.c2.body, textvariable=self.online_var, bg=CARD, fg=MUTED, font=(FONT, 10), anchor="w").pack(fill="x", pady=(6, 0))
        self.force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.c2.body, text="I know the variant of this uBox (needed only for firmware older than v8.4)",
                        variable=self.force_var).pack(anchor="w", pady=(4, 0))

        # card 3: update
        self.c3 = Card(body, "3", "Update")
        self.c3.pack(fill="x", pady=(12, 0))
        row3 = tk.Frame(self.c3.body, bg=CARD)
        row3.pack(fill="x")
        self.btn_update = ttk.Button(row3, text="Update", style="Primary.TButton", command=self.start_update, state="disabled")
        self.btn_update.pack(side="left")
        self.progress = ttk.Progressbar(row3, length=380, mode="determinate", maximum=1000)
        self.progress.pack(side="left", padx=(16, 0), fill="x", expand=True)
        self.status_var = tk.StringVar(value="")
        tk.Label(self.c3.body, textvariable=self.status_var, bg=CARD, fg=TEXT, font=(FONT, 11, "bold"), anchor="w").pack(fill="x", pady=(8, 0))
        self.log_box = tk.Text(self.c3.body, height=7, width=78, state="disabled", wrap="word", font=(MONO, 10),
                               bg="#fafafa", fg="#333333", relief="flat", highlightbackground=BORDER, highlightthickness=1, padx=8, pady=6)
        self.log_box.pack(fill="x", pady=(8, 0))

        tk.Label(body, text="Keep the USB cable connected and the uBox powered during the update. Settings, patterns and counters are preserved.",
                 bg=BG, fg=MUTED, font=(FONT, 10), wraplength=640, justify="left").pack(anchor="w", pady=(12, 0))

    def log(self, msg: str):
        self.q.put(("log", msg))

    def set_progress(self, v: float):
        self.q.put(("progress", v))

    def _status(self, text: str, color: str = TEXT):
        self.status_var.set(text)
        self.c3.body.winfo_children()[1].configure(fg=color)

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
                elif kind == "status":
                    self._status(*val)
                elif kind == "done":
                    self.busy = False
                    self._set_buttons()
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _set_buttons(self):
        st = "disabled" if self.busy else "normal"
        self.btn_refresh.configure(state=st)
        ready = (not self.busy and self.ubox is not None and bool(self.entries))
        self.btn_update.configure(state="normal" if ready else "disabled")
        self.c3.set_state(ACCENT if ready else BORDER)

    def _update_device_label(self):
        u = self.ubox
        if u is None:
            self.dev_var.set("No uBox found. Switch the uBox on, connect the USB cable and press Refresh.")
            self.c1.set_state(RED)
        elif u.port == "bootloader":
            self.dev_var.set("uBox in programming mode (variant unknown): tick 'I know the variant' and choose the file.")
            self.c1.set_state(ORANGE)
        elif u.version:
            self.dev_var.set(f"Connected on {u.port}  ·  firmware v{u.version} {u.variant}")
            self.c1.set_state(GREEN)
        else:
            self.dev_var.set(f"Connected on {u.port}  ·  firmware older than v8.4 (cannot report version and variant)")
            self.c1.set_state(ORANGE)
        self._select_default()
        self._set_buttons()

    def _merge_entries(self, new):
        self.entries = sources.merge(self.entries + new)
        self.fw_combo["values"] = [e.label for e in self.entries]
        self._select_default()
        self._set_buttons()

    def _select_default(self):
        if not self.entries:
            self.c2.set_state(BORDER)
            return
        variant = self.ubox.variant if self.ubox else None
        pick = next((e for e in self.entries if variant is None or e.variant == variant), self.entries[0])
        self.fw_combo.current(self.entries.index(pick))
        self.c2.set_state(GREEN)

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
        self.c1.set_state(BORDER)
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
                self.q.put(("online", f"Online: {len(ent)} firmware file(s) published by BiomimX." if ent else "Online: no firmware published."))
            except Exception:
                self.q.put(("online", "Online check not available (no connection). The included firmware can still be used."))
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
        self._status("Updating... do not disconnect the uBox.", ORANGE)

        def work():
            try:
                info = updater.run_update(e, u, self.log, self.set_progress, force_variant=self.force_var.get())
                self.q.put(("device", info if info else None))
                if info and info.version == e.version:
                    self.q.put(("status", (f"Update completed: the uBox now runs v{info.version} {info.variant}.", GREEN)))
                else:
                    self.q.put(("status", ("Programming finished. Check the version on the uBox display (Settings).", ORANGE)))
            except Exception as ex:
                self.log(f"ERROR: {ex}")
                self.q.put(("log", "If the uBox shows 'Programming mode': unplug USB, remove power for 5 s, power on, and retry."))
                self.q.put(("status", ("Update failed - see the messages above.", RED)))
            finally:
                self.q.put(("done", None))
        threading.Thread(target=work, daemon=True).start()


def main():
    App().mainloop()
