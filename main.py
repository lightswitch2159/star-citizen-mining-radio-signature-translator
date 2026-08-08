"""
Star Citizen Mining RS Scanner
-------------------------------
Select a screen region over the in-game Resource Signature (RS) readout,
then either:
  - Hotkey mode: press a key to grab a single reading, or
  - Live mode: continuously watch the region and update automatically.

The captured number is OCR'd with Tesseract and matched against the
community RS reference table to tell you which mineral it is.
"""

import os
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import capture
import config
import ocr
from mineral_data import lookup_rs

try:
    from pynput import keyboard as pynput_keyboard
except ImportError:
    pynput_keyboard = None

DEFAULT_HOTKEY = "<f9>"
LIVE_INTERVAL_SEC = 0.75  # used for the mss (X11) backend
LIVE_INTERVAL_SEC_SLOW = 2.0  # used for spectacle/grim (Wayland) — each
                               # capture spawns an external process
TRIGGER_FILE = os.path.join(tempfile.gettempdir(), "sc_rs_scanner_trigger")
TRIGGER_POLL_SEC = 0.15


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SC Mining RS Scanner")
        self.root.geometry("480x560")
        self.root.minsize(420, 480)

        self.saved_config = config.load_config()

        saved_region = self.saved_config.get("region")
        self.region = tuple(saved_region) if saved_region else None
        self.mode = tk.StringVar(value=self.saved_config.get("mode", "hotkey"))
        self.hotkey_str = tk.StringVar(value=self.saved_config.get("hotkey", "F9"))
        self.status_text = tk.StringVar(value="Select a screen region to begin.")

        self._live_thread = None
        self._live_stop = threading.Event()
        self._hotkey_listener = None
        self._last_digits = None

        self._trigger_stop = threading.Event()
        self._trigger_thread = None
        if sys.platform.startswith("linux"):
            # Only relevant on Linux: this is the workaround for Wayland
            # blocking real global hotkeys (see _trigger_watch_loop).
            # Windows/macOS get real global hotkeys from pynput directly.
            self._trigger_thread = threading.Thread(target=self._trigger_watch_loop, daemon=True)
            self._trigger_thread.start()

        self._build_ui()
        self._restore_region_label()
        self._check_tesseract()
        self._apply_hotkey()
        self._report_capture_backend()

    def _restore_region_label(self):
        if self.region:
            l, t, w, h = self.region
            self.region_label.config(text=f"{w}x{h} at ({l},{t}) — restored")

    def _report_capture_backend(self):
        backend = capture._backend_order()[0]
        names = {"mss": "mss (X11)", "spectacle": "KDE Spectacle (Wayland)", "grim": "grim (Wayland)"}
        self.live_interval = LIVE_INTERVAL_SEC if backend == "mss" else LIVE_INTERVAL_SEC_SLOW
        current = self.status_text.get()
        self.status_text.set(f"{current}  |  Capture: {names.get(backend, backend)}")

    # ---------- UI ----------

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        region_frame = ttk.LabelFrame(self.root, text="1. Region")
        region_frame.pack(fill="x", **pad)
        ttk.Button(region_frame, text="Select Region", command=self.on_select_region).pack(
            side="left", padx=8, pady=8
        )
        self.region_label = ttk.Label(region_frame, text="No region selected")
        self.region_label.pack(side="left", padx=8)
        ttk.Button(region_frame, text="Save Debug Capture", command=self.on_debug_capture).pack(
            side="right", padx=8
        )

        mode_frame = ttk.LabelFrame(self.root, text="2. Capture mode")
        mode_frame.pack(fill="x", **pad)

        rb_row = ttk.Frame(mode_frame)
        rb_row.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Radiobutton(
            rb_row, text="Hotkey (press to capture once)", value="hotkey",
            variable=self.mode, command=self.on_mode_change
        ).pack(side="left")
        ttk.Radiobutton(
            rb_row, text="Live (auto-watch)", value="live",
            variable=self.mode, command=self.on_mode_change
        ).pack(side="left", padx=(16, 0))

        hk_row = ttk.Frame(mode_frame)
        hk_row.pack(fill="x", padx=8, pady=4)
        is_linux = sys.platform.startswith("linux")
        ttk.Label(hk_row, text="Hotkey:" if not is_linux else "In-app hotkey:").pack(side="left")
        self.hotkey_entry = ttk.Entry(hk_row, textvariable=self.hotkey_str, width=10)
        self.hotkey_entry.pack(side="left", padx=6)
        ttk.Button(hk_row, text="Apply", command=self._apply_hotkey).pack(side="left", padx=6)
        hk_caveat = (
            "(only fires while this window is focused — see Global Hotkey below for in-game use)"
            if is_linux else
            "(fires globally, including while Star Citizen is focused)"
        )
        ttk.Label(
            hk_row, text=hk_caveat,
            font=("Segoe UI", 8), foreground="#666"
        ).pack(side="left", padx=(6, 0))

        if is_linux:
            global_frame = ttk.LabelFrame(
                mode_frame, text="Global hotkey — Linux only (fires while Star Citizen is focused)"
            )
            global_frame.pack(fill="x", padx=8, pady=(4, 8))
            ttk.Label(
                global_frame,
                text=(
                    "Linux/Wayland blocks apps from listening for keypresses in "
                    "other windows, so the hotkey above won't fire while the game "
                    "has focus. Use KDE's own global shortcuts instead: bind a key "
                    "to run this command, and this app will react to it. "
                    "(Not needed on Windows/macOS — the hotkey above already works "
                    "globally there.)"
                ),
                wraplength=420, justify="left",
            ).pack(padx=6, pady=(6, 4), anchor="w")

            cmd_row = ttk.Frame(global_frame)
            cmd_row.pack(fill="x", padx=6, pady=(0, 6))
            self.trigger_cmd_str = f"touch '{TRIGGER_FILE}'"
            cmd_entry = ttk.Entry(cmd_row)
            cmd_entry.insert(0, self.trigger_cmd_str)
            cmd_entry.config(state="readonly")
            cmd_entry.pack(side="left", fill="x", expand=True)
            ttk.Button(cmd_row, text="Copy", command=self._copy_trigger_cmd).pack(side="left", padx=6)
            ttk.Button(cmd_row, text="Setup Steps", command=self._show_kde_setup).pack(side="left")

        self.live_toggle_btn = ttk.Button(
            mode_frame, text="Start Live Watch", command=self.on_toggle_live
        )
        self.live_toggle_btn.pack(padx=8, pady=(2, 8), anchor="w")

        result_frame = ttk.LabelFrame(self.root, text="3. Result")
        result_frame.pack(fill="x", **pad)

        self.mineral_label = ttk.Label(
            result_frame, text="--", font=("Segoe UI", 26, "bold")
        )
        self.mineral_label.pack(padx=10, pady=(10, 0))

        self.detail_label = ttk.Label(result_frame, text="", font=("Segoe UI", 10))
        self.detail_label.pack(padx=10, pady=(0, 4))

        self.hint_label = ttk.Label(
            result_frame, text="", font=("Segoe UI", 9, "italic"), foreground="#a65a00"
        )
        self.hint_label.pack(padx=10, pady=(0, 10))

        history_frame = ttk.LabelFrame(self.root, text="History")
        history_frame.pack(fill="both", expand=True, **pad)
        self.history = tk.Text(history_frame, height=10, state="disabled", wrap="none")
        self.history.pack(fill="both", expand=True, padx=6, pady=6)

        self.status_bar = ttk.Label(self.root, textvariable=self.status_text, relief="sunken", anchor="w")
        self.status_bar.pack(fill="x", side="bottom")

        self.on_mode_change()

    def _check_tesseract(self):
        ok, msg = ocr.ensure_tesseract()
        if not ok:
            self.status_text.set(f"Tesseract not ready: {msg}")
            messagebox.showwarning("Tesseract not found", msg)
        else:
            self.status_text.set(f"Tesseract ready ({msg}). Select a region to begin.")

    # ---------- Region selection ----------

    def on_select_region(self):
        bbox = capture.select_region(self.root)
        if bbox:
            self.region = bbox
            self.region_label.config(text=f"{bbox[2]}x{bbox[3]} at ({bbox[0]},{bbox[1]})")
            self.status_text.set("Region set.")
            config.save_config(region=list(bbox))
        else:
            self.status_text.set("Region selection cancelled.")

    def on_debug_capture(self):
        if not self.region:
            messagebox.showinfo("No region", "Select a screen region first.")
            return
        try:
            img = capture.grab(self.region)
        except Exception as e:
            messagebox.showerror("Capture failed", str(e))
            return

        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_captures")
        results = ocr.debug_capture(img, out_dir)
        lines = "\n".join(f"{name}: {text}" for name, text in results)
        self._log(f"Debug capture saved to {out_dir}")
        messagebox.showinfo(
            "Debug capture saved",
            f"Saved to:\n{out_dir}\n\nOpen 00_raw_crop.png first — that's exactly "
            f"what the region grab captured. If it's blank, black, or the wrong "
            f"part of the screen, that's a capture/region issue, not OCR.\n\n"
            f"Tesseract output per variant:\n{lines}",
        )

    # ---------- Mode handling ----------

    def on_mode_change(self):
        live = self.mode.get() == "live"
        self.live_toggle_btn.config(state="normal" if live else "disabled")
        if not live:
            self._stop_live()
        config.save_config(mode=self.mode.get())

    def on_toggle_live(self):
        if self._live_thread and self._live_thread.is_alive():
            self._stop_live()
        else:
            self._start_live()

    def _start_live(self):
        if not self.region:
            messagebox.showinfo("No region", "Select a screen region first.")
            return
        self._live_stop.clear()
        self._live_thread = threading.Thread(target=self._live_loop, daemon=True)
        self._live_thread.start()
        self.live_toggle_btn.config(text="Stop Live Watch")
        self.status_text.set("Live watch running...")

    def _stop_live(self):
        self._live_stop.set()
        self.live_toggle_btn.config(text="Start Live Watch")
        if self.mode.get() == "live":
            self.status_text.set("Live watch stopped.")

    def _live_loop(self):
        interval = getattr(self, "live_interval", LIVE_INTERVAL_SEC)
        while not self._live_stop.is_set():
            self.do_scan(from_live=True)
            self._live_stop.wait(interval)

    # ---------- Hotkey handling ----------

    def _apply_hotkey(self):
        if pynput_keyboard is None:
            self.status_text.set("pynput not installed; hotkey mode unavailable.")
            return

        if self._hotkey_listener:
            self._hotkey_listener.stop()
            self._hotkey_listener = None

        combo = self.hotkey_str.get().strip().lower()
        if not combo:
            return
        # allow bare function keys like "F9" without requiring <f9> syntax
        if combo.startswith("f") and combo[1:].isdigit():
            combo = f"<{combo}>"

        try:
            self._hotkey_listener = pynput_keyboard.GlobalHotKeys(
                {combo: self._on_hotkey_pressed}
            )
            self._hotkey_listener.start()
            self.status_text.set(f"Hotkey set to {self.hotkey_str.get()}.")
            config.save_config(hotkey=self.hotkey_str.get())
        except Exception as e:
            self.status_text.set(f"Invalid hotkey: {e}")

    def _on_hotkey_pressed(self):
        if self.mode.get() != "hotkey":
            return
        if not self.region:
            self.root.after(0, lambda: self.status_text.set("Set a region before using the hotkey."))
            return
        self.do_scan(from_live=False)

    # ---------- Global trigger (works even while Star Citizen has focus) ----------

    def _trigger_watch_loop(self):
        """
        Wayland blocks apps from listening for keypresses in other windows,
        so pynput's "global" hotkey above only actually fires while this
        app's own window is focused. To get a real global trigger, we watch
        for a small marker file instead -- bind a KDE Custom Shortcut to
        `touch` that file (see _show_kde_setup), and this loop reacts to it.
        """
        while not self._trigger_stop.is_set():
            try:
                if os.path.exists(TRIGGER_FILE):
                    os.remove(TRIGGER_FILE)
                    if self.mode.get() == "hotkey":
                        self.do_scan(from_live=False)
            except OSError:
                pass
            self._trigger_stop.wait(TRIGGER_POLL_SEC)

    def _copy_trigger_cmd(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.trigger_cmd_str)
        self.status_text.set("Command copied — paste it into the KDE shortcut's Action field.")

    def _show_kde_setup(self):
        steps = (
            "Wayland doesn't let apps listen for keypresses while another "
            "window (like Star Citizen) has focus, so we use KDE's own "
            "Global Shortcuts to trigger a capture instead:\n\n"
            "1. Open System Settings → Shortcuts → Custom Shortcuts.\n"
            "2. Right-click the list → New → Global Shortcut → Command/URL.\n"
            "3. Name it, e.g. 'SC RS Scanner Capture'.\n"
            "4. In the Trigger tab, set whatever key you want (e.g. F9) — "
            "this is now a real global shortcut, so it'll fire even while "
            "the game is focused.\n"
            f"5. In the Action tab, paste this command:\n   {self.trigger_cmd_str}\n"
            "6. Click Apply.\n\n"
            "With this app running and set to Hotkey mode, pressing that key "
            "anywhere (including in-game) will trigger a capture."
        )
        messagebox.showinfo("KDE global shortcut setup", steps)

    # ---------- Scan / OCR / lookup ----------

    def do_scan(self, from_live: bool):
        if not self.region:
            return
        try:
            img = capture.grab(self.region)
        except Exception as e:
            self.root.after(0, lambda: self.status_text.set(f"Capture error: {e}"))
            return

        digits = ocr.read_digits(img)

        if from_live and digits == self._last_digits:
            return  # nothing changed, skip UI churn
        self._last_digits = digits

        if not digits:
            self.root.after(0, lambda: self._show_result(None, "unknown", []))
            return

        value = int(digits)
        result = lookup_rs(value)
        self.root.after(0, lambda: self._show_result(digits, result.status, result.candidates))

    def _show_result(self, digits, status, candidates):
        if status == "match" and candidates:
            c = candidates[0]
            self.mineral_label.config(text=c.mineral, foreground="#0a7d2c")
            self.detail_label.config(text=f"RS {c.value} (x{c.multiple})  |  read: {digits}")
            # Informational, not a caution -- this is just what else the
            # sheet says commonly comes from the same rock.
            hint = f"Rock may also contain: {c.co_occurs_with}" if c.co_occurs_with else ""
            self.hint_label.config(text=hint, foreground="#3a6ea5")
            self._log(f"{digits} -> {c.mineral} (RS {c.value})")

        elif status == "ambiguous" and candidates:
            names = " / ".join(c.mineral for c in candidates)
            self.mineral_label.config(text=names, foreground="#a65a00")
            self.detail_label.config(text=f"Uncertain match  |  read: {digits}")
            self.hint_label.config(text="Close readings — check mass/resistance to confirm.", foreground="#a65a00")
            self._log(f"{digits} -> uncertain: {names}")

        else:
            self.mineral_label.config(text="Unknown", foreground="#a30000")
            shown = digits if digits else "(no digits read)"
            self.detail_label.config(text=f"read: {shown}")
            self.hint_label.config(text="Not on the reference sheet, or OCR misread it.", foreground="#a65a00")
            self._log(f"{shown} -> unknown")

    def _log(self, line):
        ts = time.strftime("%H:%M:%S")
        self.history.config(state="normal")
        self.history.insert("end", f"[{ts}] {line}\n")
        self.history.see("end")
        self.history.config(state="disabled")

    def on_close(self):
        self._stop_live()
        self._trigger_stop.set()
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
