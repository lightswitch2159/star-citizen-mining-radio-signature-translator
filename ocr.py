"""
OCR handling: takes a screenshot (PIL Image) of the RS readout and returns
the digits it finds, using Tesseract via pytesseract.

The RS readout is just a number, so we preprocess aggressively (upscale,
threshold, try both polarities) and constrain Tesseract to digits only.
"""

import os
import re
import shutil
import sys

from PIL import Image, ImageOps

try:
    import pytesseract
except ImportError:
    pytesseract = None

_TESSERACT_READY = False
_TESSERACT_ERROR = None


def _bundled_tesseract_dir():
    """
    When running as a frozen PyInstaller build with a Tesseract copy bundled
    alongside it (see packaging/windows/), return that folder. Returns None
    for a normal `python main.py` run, or if no bundle is present.
    """
    if not getattr(sys, "frozen", False):
        return None
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
    candidate = os.path.join(base, "tesseract_bundle")
    return candidate if os.path.isdir(candidate) else None


def _find_windows_tesseract():
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def _find_tessdata_dir():
    """Search common install locations for eng.traineddata and return the
    directory containing it, or None."""
    import glob

    candidates = [
        "/usr/share/tessdata",
        "/usr/local/share/tessdata",
        "/usr/share/tesseract-ocr/*/tessdata",
        "/usr/share/tesseract-ocr/tessdata",
        "/opt/homebrew/share/tessdata",  # macOS (Apple Silicon Homebrew)
        "/usr/local/opt/tesseract/share/tessdata",  # macOS (Intel Homebrew)
    ]
    for pattern in candidates:
        for path in glob.glob(pattern):
            if os.path.isfile(os.path.join(path, "eng.traineddata")):
                return path
    return None


def ensure_tesseract():
    """
    Locate the tesseract binary and its English language data.
    Returns (ok: bool, message: str).
    """
    global _TESSERACT_READY, _TESSERACT_ERROR

    if pytesseract is None:
        _TESSERACT_ERROR = "pytesseract is not installed (pip install -r requirements.txt)"
        return False, _TESSERACT_ERROR

    binary_ok = False
    binary_msg = ""

    # A bundled copy (packaged Windows build) always wins -- it's the whole
    # point of bundling, and avoids depending on anything installed system-wide.
    bundled_dir = _bundled_tesseract_dir()
    if bundled_dir:
        exe_name = "tesseract.exe" if sys.platform.startswith("win") else "tesseract"
        bundled_exe = os.path.join(bundled_dir, exe_name)
        bundled_tessdata = os.path.join(bundled_dir, "tessdata")
        if os.path.isfile(bundled_exe) and os.path.isfile(
            os.path.join(bundled_tessdata, "eng.traineddata")
        ):
            pytesseract.pytesseract.tesseract_cmd = bundled_exe
            os.environ["TESSDATA_PREFIX"] = bundled_tessdata
            _TESSERACT_READY = True
            return True, f"bundled copy at {bundled_exe}"

    if shutil.which("tesseract"):
        binary_ok = True
        binary_msg = "found on PATH"
    elif sys.platform.startswith("win"):
        found = _find_windows_tesseract()
        if found:
            pytesseract.pytesseract.tesseract_cmd = found
            binary_ok = True
            binary_msg = f"found at {found}"
    else:
        env_path = os.environ.get("TESSERACT_CMD")
        if env_path and os.path.isfile(env_path):
            pytesseract.pytesseract.tesseract_cmd = env_path
            binary_ok = True
            binary_msg = f"found at {env_path}"

    if not binary_ok:
        _TESSERACT_ERROR = (
            "Tesseract binary not found. Install it "
            "(https://github.com/UB-Mannheim/tesseract/wiki on Windows, "
            "'brew install tesseract' on macOS, 'sudo apt install tesseract-ocr' "
            "on Linux), or set TESSERACT_CMD to its full path."
        )
        return False, _TESSERACT_ERROR

    # Binary found -- now make sure the English language data is reachable.
    tessdata_dir = os.environ.get("TESSDATA_PREFIX")
    if not tessdata_dir:
        tessdata_dir = _find_tessdata_dir()
        if tessdata_dir:
            os.environ["TESSDATA_PREFIX"] = tessdata_dir

    if not tessdata_dir or not os.path.isfile(os.path.join(tessdata_dir, "eng.traineddata")):
        _TESSERACT_ERROR = (
            "Tesseract binary found, but its English language data "
            "(eng.traineddata) could not be located. Install the language "
            "pack (e.g. 'sudo apt install tesseract-ocr-eng' on Debian/Ubuntu, "
            "'sudo dnf install tesseract-langpack-eng' on Fedora), or find it "
            "yourself with `find / -iname eng.traineddata` and set "
            "TESSDATA_PREFIX to the directory it's in."
        )
        return False, _TESSERACT_ERROR

    _TESSERACT_READY = True
    return True, binary_msg


_DIGIT_CONFIG = "--psm 7 -c tessedit_char_whitelist=0123456789"

# Common OCR misreads for a digits-only readout, applied as a fallback
# if the raw pass returns non-digit noise mixed with numbers.
_SUBSTITUTIONS = str.maketrans({
    "O": "0", "o": "0", "D": "0",
    "l": "1", "I": "1", "|": "1",
    "Z": "2", "z": "2",
    "S": "5", "s": "5",
    "B": "8",
    "G": "6",
    "T": "7",
})


def _preprocess_variants(img: Image.Image):
    """Yield (name, image) pairs of preprocessed versions of the crop to
    try OCR against."""
    gray = img.convert("L")

    # Upscale — small HUD text benefits a lot from this
    scale = 4
    big = gray.resize((gray.width * scale, gray.height * scale), Image.LANCZOS)

    # Plain upscaled grayscale
    yield "grayscale_upscaled", big

    # Thresholded (light text on dark background is common in game HUDs)
    thresh = big.point(lambda p: 255 if p > 140 else 0)
    yield "threshold_140", thresh

    # Inverted, in case it's dark text on a light background
    yield "threshold_140_inverted", ImageOps.invert(thresh.convert("L"))


def read_digits(img: Image.Image) -> str:
    """
    Run OCR on a cropped screenshot and return the best digit string found.
    Returns "" if nothing usable was recognized.
    """
    if not _TESSERACT_READY:
        ok, _ = ensure_tesseract()
        if not ok:
            return ""

    best = ""
    for _name, variant in _preprocess_variants(img):
        try:
            raw = pytesseract.image_to_string(variant, config=_DIGIT_CONFIG)
        except Exception:
            continue
        digits = re.sub(r"[^\d]", "", raw)
        if not digits:
            # try correcting common letter/digit confusions and retry cleanup
            corrected = re.sub(r"[^\d]", "", raw.translate(_SUBSTITUTIONS))
            digits = corrected
        if len(digits) > len(best):
            best = digits

    return best


def debug_capture(img: Image.Image, out_dir: str) -> list:
    """
    Save the raw crop plus every preprocessed variant to out_dir, along with
    what Tesseract reads off each one. Returns a list of
    (filename, raw_ocr_text) for display/logging.
    """
    os.makedirs(out_dir, exist_ok=True)
    results = []

    raw_path = os.path.join(out_dir, "00_raw_crop.png")
    img.save(raw_path)
    results.append(("00_raw_crop.png", "(unprocessed crop — this is what the region grab actually captured)"))

    if not _TESSERACT_READY:
        ok, msg = ensure_tesseract()
        if not ok:
            results.append(("(tesseract)", f"NOT READY: {msg}"))
            return results

    for i, (name, variant) in enumerate(_preprocess_variants(img), start=1):
        fname = f"{i:02d}_{name}.png"
        variant.save(os.path.join(out_dir, fname))
        try:
            raw_text = pytesseract.image_to_string(variant, config=_DIGIT_CONFIG)
        except Exception as e:
            raw_text = f"(tesseract error: {e})"
        results.append((fname, repr(raw_text)))

    return results


def last_error() -> str:
    return _TESSERACT_ERROR or ""
