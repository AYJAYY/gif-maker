"""Settings persistence: %APPDATA%/Framezy/config.json (or ~/.config/Framezy on non-Windows)."""
import json
import os
import sys
from pathlib import Path

DEFAULTS = {
    "fps": 20,
    "output_width": 480,
    "quality_mode": "quality",  # "quality" (ffmpeg palette) or "fast" (Pillow)
    "save_folder": str(Path.home() / "Videos"),
    "overlay_border_color": "#26c6da",  # matches theme.ACCENT
    "loop_count": 0,  # 0 = infinite
    "playback_speed": 1.0,
    "hotkeys": {
        "start_stop": "F9",
    },
}

# Bump alongside DEFAULTS changes and add an entry to _MIGRATIONS below so
# existing users' config.json picks up new defaults. A migration only
# overwrites a saved value when it still matches the *old* default, so a
# value the user deliberately changed is never touched.
CONFIG_VERSION = 3

# Each entry: (version this migration upgrades *to*, key, old_default, new_default).
_MIGRATIONS = [
    (2, "fps", 15, 20),
    (3, "overlay_border_color", "#FFCA38", "#26c6da"),
]


def _config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", str(Path.home()))
        return Path(base) / "Framezy"
    return Path.home() / ".config" / "Framezy"


def _config_path() -> Path:
    return _config_dir() / "config.json"


def load() -> dict:
    path = _config_path()
    settings = DEFAULTS.copy()
    if not path.exists():
        settings["_config_version"] = CONFIG_VERSION
        return settings

    try:
        with open(path, "r", encoding="utf-8") as f:
            saved = json.load(f)
    except (json.JSONDecodeError, OSError):
        settings["_config_version"] = CONFIG_VERSION
        return settings

    settings.update(saved)
    saved_version = saved.get("_config_version", 1)
    migrated = False
    for target_version, key, old_default, new_default in _MIGRATIONS:
        if saved_version < target_version and saved.get(key) == old_default:
            settings[key] = new_default
            migrated = True

    if saved_version < CONFIG_VERSION or migrated:
        settings["_config_version"] = CONFIG_VERSION
        save(settings)
    return settings


def save(settings: dict) -> None:
    config_dir = _config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    with open(_config_path(), "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
