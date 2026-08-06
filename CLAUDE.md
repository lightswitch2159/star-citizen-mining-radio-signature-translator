# CLAUDE.md

Context for Claude Code picking up this project. Read `docs/PROJECT_HISTORY.md`
for the detailed chronological log of what's been built and why — this file
is the quick-reference version.

## What this is

A desktop app that OCRs the Resource Signature (RS) number off the mining
HUD in Star Citizen and identifies which mineral it corresponds to, using a
community reference table. Python + Tkinter GUI. Developed for a Linux
(KDE Plasma, Wayland) user; packaged for distribution to Windows players
(the majority of the SC playerbase).

## Commands

```
pip install -r requirements.txt   # deps (see also: platform-specific system
                                   # packages noted in README.md — Tesseract,
                                   # spectacle/grim on Linux)
python main.py                    # run the app
python mineral_data.py            # quick sanity check of the lookup table
python -m py_compile *.py         # syntax check all modules (no GUI needed)
```

Building the Windows installer: see `packaging/windows/README.md`.
Requires an actual Windows machine. Built and verified end-to-end on
2026-08-06 (PyInstaller app folder launched correctly; Inno Setup installer
compiled cleanly) — see `packaging/windows/README.md` for the steps.

## Architecture

| File | Responsibility |
|---|---|
| `main.py` | Tkinter GUI: region select, hotkey/live mode toggle, result display, history log, config load/save wiring |
| `capture.py` | Screen capture backend selection (mss/spectacle/grim), region-select overlay |
| `ocr.py` | Tesseract discovery (binary + tessdata), image preprocessing, digit extraction |
| `mineral_data.py` | RS reference table, matching/lookup logic (pure functions, no I/O) |
| `config.py` | Persists region/hotkey/mode to JSON in the standard per-OS config dir |
| `packaging/windows/` | PyInstaller spec + build script + Inno Setup script for a one-click Windows installer |

## Critical gotchas — read before touching capture.py

These were each a real, debugged-live bug. Don't reintroduce them.

1. **`mss` silently returns a black frame on Wayland instead of erroring.**
   Never trust an `mss` capture without the black-frame check already in
   `capture.py` (`img.getextrema() == ((0,0),(0,0),(0,0))`). This is why
   Wayland sessions use `spectacle`/`grim` instead.

2. **Tk's `-fullscreen` attribute is per-*monitor* under Wayland's window
   management protocol.** It cannot span a multi-monitor desktop, no matter
   what geometry the window would otherwise want. The region-select overlay
   instead sets explicit `geometry()` to the full virtual desktop size at
   `+0+0`, combined with `overrideredirect(True)` to bypass WM placement
   entirely. Do not go back to `-fullscreen` for anything meant to span
   multiple monitors.

3. **`-alpha` transparency is not reliably composited on `overrideredirect`
   windows under KWin.** (Needed `overrideredirect` for #2 above, which then
   broke transparency — found out the hard way.) The overlay now displays
   an actual dimmed screenshot as its background instead of relying on any
   window-manager compositing trick. If you're tempted to "simplify" this
   back to a translucent window, don't — it was tested and rendered solid
   black.

4. **Tesseract binary-found ≠ Tesseract working.** The binary can be on
   PATH while `TESSDATA_PREFIX` (or the equivalent bundled path) still
   isn't set, producing an opaque "Error opening data file eng.traineddata"
   failure. `ocr.py`'s `ensure_tesseract()` checks both independently and
   returns a specific, actionable message for each failure mode. Preserve
   that separation if you touch this function.

5. **Global hotkeys don't work while another window has focus, under
   Wayland.** `pynput`'s `GlobalHotKeys` only actually fires globally on
   Windows/macOS; on Linux/Wayland it's effectively scoped to this app's
   own window. The Linux-only workaround (KDE Custom Shortcut → `touch` a
   trigger file → app polls for it) lives in `main.py`'s
   `_trigger_watch_loop` / `_show_kde_setup` / `_copy_trigger_cmd`, and the
   whole "Global hotkey" UI section is hidden on non-Linux platforms via
   `sys.platform.startswith("linux")` checks — keep that platform gate
   intact; it's not dead code, it's correctness.

## Data semantics — read before touching mineral_data.py

- `Candidate.co_occurs_with` is **informational**, not a confusability
  signal: it's another mineral commonly found in the *same rock*, sourced
  directly from the reference sheet's "secondaries" column. It has **no
  role** in matching/scoring and should be shown on every match (not gated
  on exactness) — this was wrong earlier in development (was called
  `secondary`, treated as "look-alike RS signature," and only shown on
  inexact matches) and was corrected after the person who owns the
  reference sheet clarified its actual meaning. Don't reintroduce the old
  interpretation.
- Ambiguous matches (`status == "ambiguous"`) come from two *different*
  minerals' RS values genuinely sitting close together numerically (e.g.
  Borase/Gold/Bexalite are only ~15 apart) — this is computed fresh from
  the numbers each lookup, unrelated to `co_occurs_with`.
- Salvage nodes read as any multiple of 2000, checked independently of the
  mineral table. Two real overlaps exist in the current data (Savrilium×5 =
  16000, Bexalite×5 = 18000) — these should report as `"Salvage/Savrilium"`
  / `"Salvage/Bexalite"`, not silently pick one. `MAX_SALVAGE_MULTIPLE`
  caps how far a reading can round to a salvage multiple, to stop OCR
  garbage (stray extra digit) from being accepted as a huge, bogus salvage
  match — don't remove that cap.

## Platform matrix

| Platform | Capture backend | Global hotkey |
|---|---|---|
| Windows | `mss` | Real (`pynput`) |
| macOS | `mss` | Real (`pynput`) |
| Linux, X11 | `mss` | Real (`pynput`) |
| Linux, Wayland + KDE | `spectacle` | KDE Custom Shortcut + trigger file |
| Linux, Wayland + wlroots (Sway/Hyprland) | `grim` | Not implemented (no equivalent built yet) |
| Linux, Wayland + GNOME | **Unsupported** — no scriptable non-interactive screenshot tool available the way KDE/wlroots have one | — |

## Testing approach (no real device access in this environment)

There's no live Windows/Wayland/game environment available for direct
testing here. What's actually been used to verify correctness:
- `python -m py_compile` on every module after any change.
- An AST-based check that every `self.method`-shaped reference in `main.py`
  resolves to an actual defined method — this exact class of bug
  (`AttributeError` on a half-wired feature) has happened once already.
- `mineral_data.py`'s `if __name__ == "__main__"` block as a quick sanity
  suite for the lookup logic — extend this when adding new matching
  behavior rather than only testing by hand in the running app.
- Everything Wayland/KDE-specific has been debugged *with* the user
  live — screenshots, error messages, and a purpose-built "Save Debug
  Capture" feature in the app (dumps the raw crop + every OCR preprocessing
  variant to disk) were the actual diagnostic tools, not local testing.
  Lean on that debug feature (or extend it) rather than guessing when
  something Linux/Wayland-specific breaks again.

## Known unfinished / untested

- wlroots (Sway/Hyprland) users have no global-hotkey workaround yet —
  only the capture backend (`grim`) is implemented for them; the KDE Custom
  Shortcut approach is KDE-specific.
- GNOME Wayland is explicitly unsupported.
