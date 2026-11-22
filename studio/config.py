"""settings: defaults, the beginner / standard / expert presets, and loading and saving them."""

import json
import os
import sys

DEFAULTS = {
    "level": "beginner",
    "font_size": 11,
    "indent": 4,
    "wrap": False,
    "line_numbers": True,
    "highlight_line": True,
    "block_cursor": False,
    "auto_indent": True,
    "auto_end": True,
    "auto_pair": True,
    "autocomplete": True,
    "complete_after": 1,
    "enter_accepts": False,
    "hover": True,
    "hint_bar": True,
    "explain": True,
    "warnings": True,
    "toolbar_labels": True,
    "clear_output": True,
    "check_before_run": True,
    "show_variables_on_run": True,
    "focus_window_on_run": True,
    "autosave": False,
    "restore_session": True,
    "show_welcome": True,
    "side_panel": "files",
    "side_width": 250,
    "bottom_height": 210,
    "bottom_panel": "output",
    "show_side": True,
    "show_bottom": True,
    "export_onefile": True,
    "export_console": "auto",
    "export_include_folder": True,
    "export_folder": "",
    "check_updates": True,
    "skipped_update": "",
    "update_pending": "",
    "discord_presence": True,
    "discord_details": "{action} {file}",
    "discord_state": "line {line} of {lines}",
    "discord_idle": "thinking about what to make",
    "discord_show_file": True,
    "discord_show_time": True,
    "discord_programs": True,
    "discord_activity": "playing",
    "discord_image": "",
    "discord_image_text": "gublan studio {version}",
    "discord_small_image": "",
    "discord_button_label": "get gublan studio",
    "discord_button_url": "https://github.com/gublans/gublan",
    "discord_app_id": "",
    "recent": [],
    "session": [],
    "session_active": 0,
    "folder": "",
    "window": "",
    "translate_language": "python",
    "mcp_app": "claude code",
    "theme": "moss",
    "animations": True,
    "plugins": False,
    "disabled_plugins": [],
    "live_name": "",
    "live_port": 47800,
    "live_address": "",
}

PRESETS = {
    "beginner": {
        "explain": True, "hint_bar": True, "autocomplete": True, "complete_after": 1, "enter_accepts": False,
        "warnings": True, "toolbar_labels": True, "auto_end": True, "auto_pair": True, "hover": True,
        "show_variables_on_run": True, "check_before_run": True,
    },
    "standard": {
        "explain": False, "hint_bar": True, "autocomplete": True, "complete_after": 1, "enter_accepts": True,
        "warnings": True, "toolbar_labels": True, "auto_end": True, "auto_pair": True, "hover": True,
        "show_variables_on_run": False, "check_before_run": True,
    },
    "expert": {
        "explain": False, "hint_bar": True, "autocomplete": True, "complete_after": 2, "enter_accepts": True,
        "warnings": True, "toolbar_labels": False, "auto_end": True, "auto_pair": True, "hover": True,
        "show_variables_on_run": False, "check_before_run": True,
    },
}

LEVEL_ABOUT = {
    "beginner": "every line is explained as you type, ideas pop up early and the variables panel opens when "
                "you run.",
    "standard": "hints for each command, no explanations. enter accepts suggestions.",
    "expert": "a quieter screen: icon-only toolbar and suggestions after two letters. everything stays "
              "available.",
}


def settings_folder():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "GublanStudio")


def settings_path():
    return os.path.join(settings_folder(), "settings.json")


def load():
    settings = dict(DEFAULTS)
    try:
        with open(settings_path(), "r", encoding="utf-8") as handle:
            stored = json.load(handle)
        if isinstance(stored, dict):
            for key, value in stored.items():
                if key in DEFAULTS and isinstance(value, type(DEFAULTS[key])):
                    settings[key] = value
                elif key in DEFAULTS and isinstance(DEFAULTS[key], int) and isinstance(value, (int, float)):
                    settings[key] = int(value)
    except (OSError, ValueError):
        pass
    return settings


def save(settings):
    try:
        os.makedirs(settings_folder(), exist_ok=True)
        temporary = settings_path() + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2)
        os.replace(temporary, settings_path())
    except OSError:
        pass


def apply_level(settings, level):
    settings["level"] = level
    settings.update(PRESETS.get(level, {}))
    return settings


def add_recent(settings, path):
    path = os.path.abspath(path)
    recent = [item for item in settings.get("recent", []) if os.path.normcase(item) != os.path.normcase(path)]
    recent.insert(0, path)
    settings["recent"] = recent[:12]
