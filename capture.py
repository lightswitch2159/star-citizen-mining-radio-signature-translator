"""
Screen region selection (click-drag overlay) and grabbing that region as a
PIL Image.

Capture backend is chosen automatically:
  - X11 sessions: mss (fast, direct pixel grab).
  - Wayland sessions: mss can't see compositor surfaces at all (it silently
    returns a black frame rather than erroring), so we shell out to a
    session screenshot tool instead:
      * KDE Plasma  -> `spectacle` (bundled with Plasma)
      * wlroots (Sway/Hyprland) -> `grim`
    These tools grab the *whole* screen (no non-interactive way to ask for
    an arbitrary rectangle without a permission prompt), so we crop to the
    selected region ourselves after the fact.
"""

import os
import subprocess
import tempfile
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageEnhance, ImageTk

try:
    import mss
except ImportError:
    mss = None

_tk_root = None  # set by select_region(), used to scale Tk logical coords
                  # to the physical pixels a full-screen tool captures


def _session_type() -> str:
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or os.environ.get(
        "WAYLAND_DISPLAY"
    ):
        return "wayland"
    return "x11"


def _is_kde() -> bool:
    desktop = (os.environ.get("XDG_CURRENT_DESKTOP", "") + os.environ.get("DESKTOP_SESSION", "")).lower()
    return "kde" in desktop or "plasma" in desktop


def _backend_order():
    if _session_type() == "wayland":
        return ["spectacle", "grim"] if _is_kde() else ["grim", "spectacle"]
    return ["mss"]


def select_region(root: tk.Tk):
    """
    Show the desktop (dimmed, as a real screenshot) spanning the full
    multi-monitor virtual desktop, let the user drag a rectangle over the
    RS readout, and return (left, top, width, height) in Tk's logical
    screen coordinates. Returns None if cancelled (Esc) or if the initial
    screenshot fails.

    Displays an actual screenshot rather than a translucent window: under
    KWin/Wayland, WM-level alpha compositing isn't reliably applied to
    override-redirect windows (which we need in order to span multiple
    monitors -- see the geometry comment below), so a "-alpha" overlay can
    render fully opaque black instead of see-through. Painting a real,
    slightly-dimmed screenshot as the background sidesteps that entirely.
    """
    global _tk_root
    _tk_root = root

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()

    try:
        snapshot = grab_fullscreen()
    except Exception as e:
        messagebox.showerror(
            "Capture failed",
            f"Couldn't take a screenshot to build the region-select overlay:\n{e}",
        )
        return None

    preview = snapshot.resize((screen_w, screen_h), Image.LANCZOS)
    preview = ImageEnhance.Brightness(preview).enhance(0.55)

    result = {}

    overlay = tk.Toplevel(root)
    overlay.overrideredirect(True)
    overlay.geometry(f"{screen_w}x{screen_h}+0+0")
    overlay.attributes("-topmost", True)
    overlay.config(cursor="crosshair")

    canvas = tk.Canvas(overlay, width=screen_w, height=screen_h, highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)

    photo = ImageTk.PhotoImage(preview, master=overlay)
    overlay.bg_photo = photo  # keep a reference so it isn't garbage-collected
    canvas.create_image(0, 0, image=photo, anchor="nw")

    canvas.create_text(
        screen_w // 2,
        40,
        text="Click and drag over the RS number, then release. Esc to cancel.",
        fill="white",
        font=("Segoe UI", 16, "bold"),
    )

    state = {"start": None, "rect": None}

    def on_press(event):
        state["start"] = (event.x_root, event.y_root)
        state["rect"] = canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="#00ffb0", width=2
        )

    def on_drag(event):
        if state["rect"] is None:
            return
        x0, y0 = state["start"]
        wx0, wy0 = x0 - overlay.winfo_rootx(), y0 - overlay.winfo_rooty()
        canvas.coords(state["rect"], wx0, wy0, event.x, event.y)

    def on_release(event):
        if state["start"] is None:
            overlay.destroy()
            return
        x0, y0 = state["start"]
        x1, y1 = event.x_root, event.y_root
        left, right = sorted((x0, x1))
        top, bottom = sorted((y0, y1))
        width, height = right - left, bottom - top
        if width > 3 and height > 3:
            result["bbox"] = (left, top, width, height)
        overlay.destroy()

    def on_cancel(_event=None):
        overlay.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    overlay.bind("<Escape>", on_cancel)

    overlay.grab_set()
    overlay.focus_force()
    root.wait_window(overlay)

    return result.get("bbox")


# ---------- capture backends ----------
# Each backend function takes bbox=None to return the full, uncropped
# screenshot, or a (left, top, width, height) tuple (in Tk logical screen
# coordinates) to return just that region.


def _grab_mss(bbox) -> Image.Image:
    if mss is None:
        raise RuntimeError("mss is not installed")
    with mss.mss() as sct:
        if bbox is None:
            monitor = sct.monitors[0]  # bounding box of all monitors combined
        else:
            left, top, width, height = bbox
            monitor = {"left": left, "top": top, "width": width, "height": height}
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def _crop_fullshot_to_bbox(full: Image.Image, bbox) -> Image.Image:
    """
    Full-screen capture tools return native/physical pixels, but our bbox
    is in Tk's logical screen coordinates (which differ under HiDPI/
    fractional scaling). Scale the crop box proportionally.
    """
    left, top, width, height = bbox
    if _tk_root is not None:
        logical_w = _tk_root.winfo_screenwidth()
        logical_h = _tk_root.winfo_screenheight()
    else:
        logical_w, logical_h = full.width, full.height

    scale_x = full.width / logical_w if logical_w else 1
    scale_y = full.height / logical_h if logical_h else 1

    box = (
        int(left * scale_x),
        int(top * scale_y),
        int((left + width) * scale_x),
        int((top + height) * scale_y),
    )
    return full.crop(box)


def _grab_spectacle(bbox) -> Image.Image:
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "shot.png")
        try:
            proc = subprocess.run(
                ["spectacle", "-b", "-n", "-f", "-o", out_path],
                capture_output=True,
                timeout=8,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "spectacle not found. It normally ships with KDE Plasma; "
                "install the 'spectacle' package if it's missing."
            )
        if proc.returncode != 0 or not os.path.isfile(out_path):
            raise RuntimeError(
                f"spectacle failed (exit {proc.returncode}): {proc.stderr.decode(errors='ignore')}"
            )
        full = Image.open(out_path).convert("RGB")
        full.load()  # force read before the temp file is removed
        return full if bbox is None else _crop_fullshot_to_bbox(full, bbox)


def _grab_grim(bbox) -> Image.Image:
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "shot.png")
        try:
            proc = subprocess.run(
                ["grim", out_path], capture_output=True, timeout=8
            )
        except FileNotFoundError:
            raise RuntimeError(
                "grim not found. Install it (e.g. 'sudo pacman -S grim' / "
                "'sudo apt install grim') for Wayland screen capture on "
                "wlroots-based compositors (Sway, Hyprland)."
            )
        if proc.returncode != 0 or not os.path.isfile(out_path):
            raise RuntimeError(
                f"grim failed (exit {proc.returncode}): {proc.stderr.decode(errors='ignore')}"
            )
        full = Image.open(out_path).convert("RGB")
        full.load()
        return full if bbox is None else _crop_fullshot_to_bbox(full, bbox)


_BACKENDS = {
    "mss": _grab_mss,
    "spectacle": _grab_spectacle,
    "grim": _grab_grim,
}

_working_backend = None  # cached once one succeeds, to avoid retrying dead ones


def _dispatch(bbox) -> Image.Image:
    global _working_backend

    order = [_working_backend] if _working_backend else []
    order += [b for b in _backend_order() if b not in order]

    errors = []
    for name in order:
        fn = _BACKENDS.get(name)
        if fn is None:
            continue
        try:
            img = fn(bbox)
        except Exception as e:
            errors.append(f"{name}: {e}")
            continue

        # mss on Wayland silently returns a black frame instead of raising --
        # detect that and fall through to the next backend rather than
        # reporting a bogus "Unknown" result.
        if name == "mss" and img.getextrema() == ((0, 0), (0, 0), (0, 0)):
            errors.append("mss: returned a black frame (likely Wayland)")
            continue

        _working_backend = name
        return img

    raise RuntimeError(
        "All screen capture backends failed:\n" + "\n".join(errors)
    )


def grab(bbox) -> Image.Image:
    """Grab just the given (left, top, width, height) region."""
    return _dispatch(bbox)


def grab_fullscreen() -> Image.Image:
    """Grab the entire virtual desktop, uncropped."""
    return _dispatch(None)
