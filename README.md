# SC Mining RS Scanner

Reads the Resource Signature (RS) number off your screen while mining in
Star Citizen and tells you which mineral it corresponds to, using the
community RS reference table.

## Setup

### 1. Install Tesseract OCR (one-time, separate from Python)

- **Windows**: download and run the installer from the
  [UB-Mannheim Tesseract build](https://github.com/UB-Mannheim/tesseract/wiki).
  Default install path is `C:\Program Files\Tesseract-OCR` — the app looks
  there automatically, so you don't need to touch your PATH.
- **macOS**: `brew install tesseract`
- **Linux**: `sudo apt install tesseract-ocr` (or your distro's equivalent)

If you installed it somewhere non-standard, set an environment variable
`TESSERACT_CMD` to the full path of the `tesseract`/`tesseract.exe` binary
before running the app.

### 1b. Wayland only: install a screenshot tool

On X11 this app captures the screen directly and needs nothing extra. On
Wayland, compositors block that kind of direct capture for security, so the
app shells out to a session screenshot tool instead — it's auto-detected,
no configuration needed:

- **KDE Plasma**: uses `spectacle`, which ships with Plasma by default. If
  it's somehow missing: `sudo apt install spectacle` (or your distro's
  equivalent package name).
- **Sway / Hyprland / other wlroots compositors**: uses `grim` —
  `sudo apt install grim` or `sudo pacman -S grim`.
- **GNOME on Wayland**: not yet supported by this app (GNOME doesn't expose
  a scriptable non-interactive screenshot tool the way KDE/wlroots do —
  it's portal-only, which prompts on every capture). If this is you, let's
  talk about adding portal-based capture instead.

The status bar in the app tells you which capture backend it picked.

### 2. Install Python dependencies

```
pip install -r requirements.txt
```

Requires Python 3.9+.

### 3. Run it

```
python main.py
```

## Using it

1. **Select Region** — drag a box tightly around where the RS number
   appears on screen (works best in windowed/borderless mode, or with the
   game on your primary monitor). Esc cancels.
2. Pick a **capture mode**:
   - **Hotkey** — tap the configured key (default `F9`) any time you want
     a single reading. Change the key in the box and click Apply — supports
     things like `F9`, `F5`, or combos like `ctrl+shift+r`.
   - **Live** — click "Start Live Watch" and it polls the region a few
     times a second, updating automatically whenever the number changes.
     Click again to stop.
3. The result panel shows the identified mineral. If the reading falls
   very close to two minerals' values (a handful of pairs on the reference
   sheet — e.g. Borase/Gold/Bexalite — genuinely sit only ~15 apart), you'll
   get both candidates flagged as uncertain rather than a guess. Anything
   that doesn't land near any known value shows as **Unknown**.

Your region, hotkey, and hotkey/live mode selection are saved automatically
and restored the next time you launch the app — no need to reconfigure each
session. (Saved to a small `config.json` in the standard per-OS config
location — `~/.config/sc_rs_scanner/` on Linux, `~/Library/Application
Support/sc_rs_scanner/` on macOS, `%APPDATA%\sc_rs_scanner\` on Windows.)

## Notes / limitations

- OCR accuracy depends a lot on font size, contrast, and UI scale in-game —
  if you're getting a lot of "Unknown" results, try tightening the region
  box to just the digits, or nudging in-game HUD scale/opacity up.
- Region selection spans your full multi-monitor desktop, so you can select
  a region on a different monitor than the one this app's window is on —
  just drag over to it. (If it still only lets you select on one monitor,
  that's a sign your desktop layout isn't a simple side-by-side arrangement;
  let's take a look at your setup specifically.)
- **Wayland + fractional/HiDPI scaling**: the app auto-corrects for scaling
  by comparing the screenshot tool's pixel dimensions against what Tk
  reports, but if your region ends up capturing the wrong spot, it's almost
  always a scaling mismatch — try setting your display to 100% scaling, or
  re-select a slightly larger region as a margin of error.
- **Wayland live mode is slower to react** than on X11 — each capture spawns
  `spectacle`/`grim` as a separate process (there's no lightweight
  "grab this rectangle" API under Wayland), so live mode polls every ~2s
  instead of ~0.75s. Hotkey mode isn't affected by this at all.
- The reference table is the "multiple 1–7" values from the community RS
  sheet; it doesn't account for any values the community hasn't documented
  yet, in which case you'll correctly get "Unknown" rather than a wrong
  guess.

## Distributing to other Windows users

Want to hand this to other players without them installing Python or
Tesseract themselves? See `packaging/windows/README.md` for building a
one-click `SCRSScannerSetup.exe` installer that bundles everything.
