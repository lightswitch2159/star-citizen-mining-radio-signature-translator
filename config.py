"""
Persist a handful of user settings (region, hotkey, capture mode) between
launches, in a small JSON file in the standard per-OS config location.
"""

import json
import os
import sys

APP_NAME = "sc_rs_scanner"

DEFAULTS = {
    "region": None,      # [left, top, width, height] or None
    "hotkey": "F9",
    "mode": "hotkey",    # "hotkey" or "live"
}


def _config_dir() -> str:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP_NAME)
    if sys.platform == "darwin":
        return os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
    # Linux and other Unix-likes: follow XDG
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, APP_NAME)


def _config_path() -> str:
    return os.path.join(_config_dir(), "config.json")


def load_config() -> dict:
    """Return saved settings merged over defaults. Never raises."""
    cfg = dict(DEFAULTS)
    try:
        with open(_config_path(), "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            cfg.update({k: v for k, v in saved.items() if k in DEFAULTS})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return cfg


def save_config(**updates) -> None:
    """
    Merge `updates` into the saved config and write it out. Silently does
    nothing on failure -- losing saved settings isn't worth crashing over.
    """
    cfg = load_config()
    cfg.update(updates)
    try:
        os.makedirs(_config_dir(), exist_ok=True)
        tmp_path = _config_path() + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp_path, _config_path())
    except OSError:
        pass
