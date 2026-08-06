# Project History

Chronological record of how this project was built, kept for context that
doesn't fit in `CLAUDE.md`'s quick-reference format. Read this when you need
the *why* behind a decision, not just the *what*.

## Origin

Built for a Star Citizen player who wanted the in-game mining Resource
Signature (RS) number automatically identified as a mineral, rather than
manually cross-referencing a spreadsheet every time. The reference data
came from a community Google Sheet listing each mineral's base RS value
(at "multiple 1") and a "secondaries" column.

## Round 1 — initial build

Elicited two design choices up front before writing code:
- OCR engine: **Tesseract** (via `pytesseract`) over EasyOCR — smaller,
  faster, one-time install vs. a ~500MB self-contained download.
- Capture trigger: **both** hotkey and live-watch, as a toggle, rather than
  picking one.

Built the initial four modules (`main.py`, `capture.py`, `ocr.py`,
`mineral_data.py`), matching logic with tight/loose relative-error
tolerance tiers, and a first cut of the region-select overlay using
`-fullscreen` + `-alpha` (both later found to be wrong for this user's
setup — see below).

## Round 2 — Wayland capture

User reported the value simply wasn't being read. Root cause: the user
runs KDE Plasma under Wayland, and `mss` (the original capture library)
can't see Wayland compositor surfaces — it returns a black frame instead of
raising an error, so the failure was silent.

Fix: auto-detect session type (`XDG_SESSION_TYPE`/`WAYLAND_DISPLAY`) and
desktop (`XDG_CURRENT_DESKTOP`), and shell out to `spectacle` (KDE) or
`grim` (wlroots) on Wayland instead, capturing full-screen and cropping
locally since neither tool offers a non-interactive arbitrary-rectangle
capture. Added HiDPI scale correction by comparing the tool's pixel
dimensions against Tk's logical screen size.

## Round 3 — file distribution

User hit `ModuleNotFoundError` because they'd only downloaded `main.py`,
not its sibling modules (they were being shared as individual file
attachments). Fixed by switching to a single zip containing the whole
project — used for every delivery from this point forward.

## Round 4 — Tesseract language data

Debug capture confirmed the screen crop was perfect (crisp "15,600"), but
OCR still failed with `Error opening data file .../eng.traineddata`.
Diagnosis: Tesseract's binary was installed and on PATH, but the English
language data file wasn't where the binary expected it (a common gap when
a distro splits the binary package from the language-data package).

This is also when the **debug capture feature** was added to `ocr.py` /
`main.py` (a button that saves the raw crop plus every preprocessing
variant to disk, with each variant's raw Tesseract output) — it became the
primary diagnostic tool for the rest of the Linux/Wayland debugging that
followed, since there's no way to test this locally without the user's
actual environment.

Fix: `ensure_tesseract()` now searches common `tessdata` install locations
per-OS and sets `TESSDATA_PREFIX` automatically, with a specific error
message when the language data genuinely can't be found (distinct from the
binary-not-found case).

## Round 5 — salvage signatures

User explained that salvage/scrap nodes read as any multiple of 2000,
independent of the mineral table, and asked for overlaps to display as
`"Salvage/{mineral}"`. Implemented as an independent check alongside the
mineral lookup (not a replacement for it) — a reading can be a salvage
multiple, a mineral match, both (real overlaps found: Savrilium×5=16000,
Bexalite×5=18000), or neither. Added `MAX_SALVAGE_MULTIPLE` after
discovering the naive version would accept wildly OCR-garbled numbers
(e.g. `9999999`) as valid "Salvage" matches by rounding to a huge multiple.

## Round 6 — global hotkey crash

User hit `AttributeError: 'App' object has no attribute '_trigger_watch_loop'`.
Investigation revealed `main.py` already contained UI code and constants
(`TRIGGER_FILE`, `TRIGGER_POLL_SEC`) for a KDE-global-shortcut-based hotkey
workaround, but the actual methods implementing it had never been written
— a half-finished feature, presumably sketched out in response to the
underlying problem (pynput's "global" hotkey only works while this app's
own window has focus, under Wayland) but left incomplete.

Completed the implementation: `_trigger_watch_loop` (polls for a marker
file and triggers a capture when it appears), `_copy_trigger_cmd`
(clipboard helper), `_show_kde_setup` (walks the user through binding a
KDE Custom Shortcut to `touch` that file). Added a static AST-based check
(every `self.method`-shaped reference in the class must resolve to an
actual defined method) to `main.py`'s verification process after this,
specifically to catch this class of bug before shipping again.

## Round 7 — platform-gating the hotkey UI

Follow-up: the Global Hotkey section made no sense on Windows (where
`pynput`'s hotkey genuinely is global) and would confuse Windows users.
Hidden entirely behind `sys.platform.startswith("linux")`, and the in-app
hotkey's caveat label corrected to not claim "only fires while focused" on
platforms where that isn't true.

## Round 8 — region selection, multi-monitor

User reported: could now select a region, but only on the monitor the app
itself was on, and dragging over the correct (other) monitor just showed
black. Root cause, confirmed via a two-question check (multi-monitor
setup? exclusive vs. windowed fullscreen?): Tk's `-fullscreen` attribute is
a per-output request under Wayland's window management protocol — it
cannot span multiple monitors, full stop, regardless of the window's
declared size.

Fix: stopped asking the window manager for fullscreen. The overlay now
sets explicit `geometry()` to the full virtual desktop's bounding box at
`+0+0`, combined with `overrideredirect(True)` to bypass window-manager
placement/output-scoping entirely.

## Round 9 — overlay still black

That fix solved the monitor-confinement, but the overlay was still
opaque black rather than see-through. Root cause: `overrideredirect`
windows aren't reliably alpha-composited by KWin the way normal managed
windows are — the transparency trick that (presumably) would have worked
with a normal fullscreen window doesn't survive combination with the
override-redirect approach needed for round 8's fix.

Fix: stopped relying on window-manager compositing entirely. The overlay
now takes an actual screenshot first (`grab_fullscreen()`, added to
`capture.py` by making every backend function accept `bbox=None` for an
uncropped capture), dims it via `PIL.ImageEnhance`, and displays that as a
static image background via `ImageTk.PhotoImage`. This is the same
technique tools like Flameshot or Spectacle's own rectangular-region picker
use — sidesteps compositor behavior entirely since nothing needs to be
see-through anymore. Tradeoff: it's a snapshot at selection time, not a
live view (fine for framing a region, not for reading a live-changing
number while selecting).

## Round 10 — co_occurs_with semantics

User asked how the sheet's "secondaries" column was being used. It had
been interpreted (without being explicitly asked) as "commonly confused
RS signature" — displayed as a caution ("Look-alike signature: X — not an
exact match") only on inexact matches. The user corrected this: it's
actually just other minerals commonly found in the *same rock*, unrelated
to signature confusion.

Fix: renamed the field `secondary` → `co_occurs_with` throughout, changed
the displayed message to informational framing ("Rock may also contain:
X"), changed its color from caution-orange to informational-blue, and
removed the exact-match gate — it's now shown on every match where present,
since it was never actually about read confidence.

## Round 11 — packaging

Scoped to Windows-only after asking (Windows being the majority SC
platform; the user's own dev environment is Linux). Built a PyInstaller
spec + build script + Inno Setup script under `packaging/windows/`,
including a change to `ocr.py` so the app looks for a bundled Tesseract
copy first (via `sys.frozen`/`sys._MEIPASS`) before falling back to system
detection — the whole point of bundling is that end users install nothing
separately.

Explicitly could not test this end-to-end: no Windows machine, no network
access in the build sandbox to download Tesseract's Windows binaries, no
Inno Setup available. Wrote the scripts carefully with defensive error
messages for the person actually running them on real Windows hardware,
and documented that limitation directly in the packaging README rather
than implying it was tested.

User then hit a `Failed to load Python DLL` error — turned out to be
running the `.exe` from PyInstaller's intermediate `build\` scratch folder
instead of the actual output in `dist\SC RS Scanner\`. Not a bug in the
build itself, just folder confusion; clarified which folder is which.
