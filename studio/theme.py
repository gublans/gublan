"""look and feel for gublan studio.

three rules hold everywhere in the studio:
  - no rounded corners: every window asks windows 11 not to round it, and every widget is square
  - no capitals: every label, title and message is lowercase
  - the soft green and soft black palette below, nothing else
"""

import ctypes
import json
import math
import os
import re
import sys
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# ----- palette ---------------------------------------------------------------
BG = "#141414"
PANEL = "#1c1c1c"
PANEL_ALT = "#262626"
EDITOR_BG = "#171717"
TEXT = "#e5e5e5"
MUTED = "#aaaaaa"
DIM = "#6f6f6f"
MOSS = "#647f4a"
MOSS_LIGHT = "#94b66c"
MOSS_DARK = "#3c4c2d"
NUMBER = "#d7bd75"
ERROR = "#e16b6b"
ACTIVE_LINE = "#1f251d"
ERROR_LINE = "#332222"
DEBUG_LINE = "#293328"
BORDER = "#2c2c2c"
HOVER = "#232323"
SELECT = "#2f3d27"
SELECT_TEXT = "#f0f5ea"

SYNTAX = {
    "command": MOSS_LIGHT,
    "flow": "#b9cf8f",
    "string": "#a8c49a",
    "number": NUMBER,
    "comment": "#6b7266",
    "brace": "#8fb3a0",
    "function": "#cfe0b0",
    "keyword": "#c2c79a",
    "color": "#b0c48a",
    "operator": "#9aa596",
}

# block and category colours: all greens and olives so the palette stays soft green and black
CATEGORY_COLORS = {
    "basics": "#94b66c",
    "control": "#b9cf8f",
    "functions": "#7fa36a",
    "lists and maps": "#6f9a7d",
    "display": "#a3b08a",
    "2d": "#8fb08a",
    "3d": "#7a9a8f",
    "objects": "#9db07a",
    "input": "#c2c79a",
    "sound": "#88a878",
    "web": "#8a9a80",
    "saving": "#a8b27c",
    "files": "#9fb59a",
    "discord": "#8f9cc4",
    "testing": "#b8a878",
    "ui": "#9cbf9a",
    "plugins": "#a89cc4",
    "comments": "#6b7266",
    "code": "#7d8a74",
}

# smaller shades the widgets use
FIELD_BG = "#1f1f1f"
CODE_BG = "#202020"
INACTIVE_SELECT = "#252d21"
MATCH = "#34422a"
THUMB = "#333333"
THUMB_HOVER = "#4a4a4a"
BUTTON_HOVER = "#2e2e2e"
ACCENT_TEXT = "#10140c"
DARK = True
THEME_NAME = "moss"

# ----- themes ------------------------------------------------------------------
# a theme changes the names above. json themes in the themes folder use the lowercase names, for example
#   {"name": "night sea", "base": "midnight", "colors": {"bg": "#0d1117", "accent": "#3b82f6"},
#    "syntax": {"string": "#9ecbff"}}
# "accent", "accent_light" and "accent_dark" are friendlier names for moss, moss_light and moss_dark.
COLOR_NAMES = ("BG", "PANEL", "PANEL_ALT", "EDITOR_BG", "TEXT", "MUTED", "DIM", "MOSS", "MOSS_LIGHT", "MOSS_DARK",
               "NUMBER", "ERROR", "ACTIVE_LINE", "ERROR_LINE", "DEBUG_LINE", "BORDER", "HOVER", "SELECT",
               "SELECT_TEXT", "FIELD_BG", "CODE_BG", "INACTIVE_SELECT", "MATCH", "THUMB", "THUMB_HOVER",
               "BUTTON_HOVER", "ACCENT_TEXT")
COLOR_ALIASES = {"accent": "MOSS", "accent_light": "MOSS_LIGHT", "accent_dark": "MOSS_DARK"}
DEFAULT_THEME = "moss"
_MOSS_COLORS = {name: globals()[name] for name in COLOR_NAMES}
_MOSS_SYNTAX = dict(SYNTAX)
_MOSS_CATEGORIES = dict(CATEGORY_COLORS)

BUILTIN_THEMES = {
    "moss": {"about": "soft green and soft black. the gublan look.", "dark": True, "colors": {}},
    "midnight": {
        "about": "deep blue and slate.", "dark": True,
        "colors": {"bg": "#11141a", "panel": "#181c24", "panel_alt": "#222834", "editor_bg": "#141820",
                   "text": "#e3e7ee", "muted": "#a3abba", "dim": "#687082", "moss": "#4f6f9f",
                   "moss_light": "#8fb0e0", "moss_dark": "#2c3d5a", "number": "#e0c27a", "error": "#e57373",
                   "active_line": "#1a2030", "error_line": "#352228", "debug_line": "#1f2c3a", "border": "#2a303c",
                   "hover": "#1f2430", "select": "#2a3a55", "select_text": "#eef3fb", "field_bg": "#1b2029",
                   "code_bg": "#1d222c", "inactive_select": "#232c3c", "match": "#2e4366", "thumb": "#303644",
                   "thumb_hover": "#465066", "button_hover": "#2a3140", "accent_text": "#0c111a"},
        "syntax": {"command": "#8fb0e0", "flow": "#b3c8f0", "string": "#9fc9b0", "number": "#e0c27a",
                   "comment": "#687386", "brace": "#9ab8c8", "function": "#c9d8f5", "keyword": "#c3b8e8",
                   "color": "#a9c0e0", "operator": "#98a2b3"},
    },
    "ember": {
        "about": "warm browns and orange.", "dark": True,
        "colors": {"bg": "#161312", "panel": "#1e1a18", "panel_alt": "#29231f", "editor_bg": "#181513",
                   "text": "#ece4dc", "muted": "#b3a69a", "dim": "#75695e", "moss": "#a0623a",
                   "moss_light": "#e0a070", "moss_dark": "#5a3622", "number": "#e8c46c", "error": "#e86b6b",
                   "active_line": "#241d19", "error_line": "#3a2222", "debug_line": "#2e2a1f", "border": "#322b26",
                   "hover": "#261f1b", "select": "#4a2f20", "select_text": "#fbf1e8", "field_bg": "#211c19",
                   "code_bg": "#231e1b", "inactive_select": "#33251c", "match": "#553624", "thumb": "#3a322c",
                   "thumb_hover": "#54483f", "button_hover": "#332a25", "accent_text": "#1a0f08"},
        "syntax": {"command": "#e0a070", "flow": "#f0c090", "string": "#c8c08a", "number": "#e8c46c",
                   "comment": "#7a6e64", "brace": "#d0a890", "function": "#f2d0a8", "keyword": "#e8b8a0",
                   "color": "#d8b080", "operator": "#b0a294"},
    },
    "paper": {
        "about": "a light theme for bright rooms.", "dark": False,
        "colors": {"bg": "#f3f1ec", "panel": "#e9e6df", "panel_alt": "#dedad1", "editor_bg": "#fbfaf7",
                   "text": "#22251f", "muted": "#5c6157", "dim": "#8c9087", "moss": "#5a7a3e",
                   "moss_light": "#3f6a1f", "moss_dark": "#c9d8b4", "number": "#9a6a00", "error": "#c03a3a",
                   "active_line": "#eef2e6", "error_line": "#f6dede", "debug_line": "#e2ecd6", "border": "#cfcbc2",
                   "hover": "#e0ddd5", "select": "#cddcb8", "select_text": "#1a1f14", "field_bg": "#f6f5f1",
                   "code_bg": "#eceae4", "inactive_select": "#dfe6d4", "match": "#d8e6c0", "thumb": "#c8c4bb",
                   "thumb_hover": "#aaa59b", "button_hover": "#d6d2c9", "accent_text": "#ffffff"},
        "syntax": {"command": "#3f6a1f", "flow": "#5a7a1a", "string": "#2f7a4a", "number": "#9a6a00",
                   "comment": "#8a9084", "brace": "#3a6a6a", "function": "#2f5a20", "keyword": "#6a6a1a",
                   "color": "#5a7a2a", "operator": "#5a6257"},
    },
    "contrast": {
        "about": "pure black, bright text and strong edges.", "dark": True,
        "colors": {"bg": "#000000", "panel": "#0a0a0a", "panel_alt": "#161616", "editor_bg": "#000000",
                   "text": "#ffffff", "muted": "#d6d6d6", "dim": "#a0a0a0", "moss": "#7fbf3f",
                   "moss_light": "#b6f070", "moss_dark": "#3f6a1f", "number": "#ffd75e", "error": "#ff6b6b",
                   "active_line": "#141c0c", "error_line": "#3a1010", "debug_line": "#1c2c10", "border": "#5a5a5a",
                   "hover": "#1e1e1e", "select": "#3f6a1f", "select_text": "#ffffff", "field_bg": "#0f0f0f",
                   "code_bg": "#121212", "inactive_select": "#2a3a1a", "match": "#4a6a22", "thumb": "#4a4a4a",
                   "thumb_hover": "#707070", "button_hover": "#2a2a2a", "accent_text": "#000000"},
        "syntax": {"command": "#b6f070", "flow": "#d8f5a0", "string": "#a0e8b0", "number": "#ffd75e",
                   "comment": "#9a9a9a", "brace": "#a0e0e0", "function": "#e0ffc0", "keyword": "#f0f0a0",
                   "color": "#c8e890", "operator": "#d0d0d0"},
    },
    "fern": {
        "about": "brighter spring greens on a green-black.", "dark": True,
        "colors": {"bg": "#121612", "panel": "#182018", "panel_alt": "#212b21", "editor_bg": "#141a14",
                   "text": "#e6efe3", "muted": "#a8b8a3", "dim": "#6c7d68", "moss": "#5f9a48",
                   "moss_light": "#9edb7c", "moss_dark": "#2f4f24", "number": "#dcc27a", "error": "#e46c6c",
                   "active_line": "#1a2419", "error_line": "#332222", "debug_line": "#20321d", "border": "#283426",
                   "hover": "#1d261c", "select": "#2d4a24", "select_text": "#f0faea", "field_bg": "#1b221a",
                   "code_bg": "#1d251c", "inactive_select": "#233522", "match": "#36582a", "thumb": "#2f3a2d",
                   "thumb_hover": "#465744", "button_hover": "#263124", "accent_text": "#0b1408"},
        "syntax": {"command": "#9edb7c", "flow": "#c4ec9a", "string": "#b0d8a0", "number": "#dcc27a",
                   "comment": "#6c7d68", "brace": "#98c8a8", "function": "#d4f0bc", "keyword": "#cfd89a",
                   "color": "#b0d88a", "operator": "#a0ad9b"},
    },
    "dusk": {
        "about": "violet evening light.", "dark": True,
        "colors": {"bg": "#15131a", "panel": "#1c1924", "panel_alt": "#26222f", "editor_bg": "#17151d",
                   "text": "#e8e4ef", "muted": "#aaa3b8", "dim": "#6f6880", "moss": "#7a5fa8",
                   "moss_light": "#b49ae6", "moss_dark": "#3e3157", "number": "#e6c27a", "error": "#e87070",
                   "active_line": "#1f1b28", "error_line": "#352229", "debug_line": "#262036", "border": "#2d2838",
                   "hover": "#221e2b", "select": "#3a2f52", "select_text": "#f3effa", "field_bg": "#1f1c27",
                   "code_bg": "#211d29", "inactive_select": "#2a2338", "match": "#47386a", "thumb": "#353042",
                   "thumb_hover": "#4c4560", "button_hover": "#2c2738", "accent_text": "#120d1a"},
        "syntax": {"command": "#b49ae6", "flow": "#d0b8f5", "string": "#a8d0b8", "number": "#e6c27a",
                   "comment": "#6f6880", "brace": "#b8a8d8", "function": "#dccff5", "keyword": "#e0b0d0",
                   "color": "#c0a8e8", "operator": "#a59fb3"},
    },
    "glacier": {
        "about": "cold teal and ice.", "dark": True,
        "colors": {"bg": "#101518", "panel": "#161c20", "panel_alt": "#1f272c", "editor_bg": "#12181b",
                   "text": "#e2ecef", "muted": "#9fb2b8", "dim": "#64777d", "moss": "#3f8a99",
                   "moss_light": "#7fd0dc", "moss_dark": "#234a52", "number": "#e3c77e", "error": "#e57373",
                   "active_line": "#172126", "error_line": "#33232a", "debug_line": "#1a2c30", "border": "#263137",
                   "hover": "#1b2429", "select": "#24464f", "select_text": "#ecf8fa", "field_bg": "#192125",
                   "code_bg": "#1b2328", "inactive_select": "#1f343a", "match": "#2b5a64", "thumb": "#2e3a40",
                   "thumb_hover": "#455860", "button_hover": "#233036", "accent_text": "#071215"},
        "syntax": {"command": "#7fd0dc", "flow": "#a8e4ec", "string": "#a8d8b0", "number": "#e3c77e",
                   "comment": "#64777d", "brace": "#98c8d8", "function": "#c8eef4", "keyword": "#b8c8f0",
                   "color": "#90d0d8", "operator": "#98aab0"},
    },
    "rosewood": {
        "about": "deep red wood and soft pink.", "dark": True,
        "colors": {"bg": "#171213", "panel": "#1f1819", "panel_alt": "#2a2022", "editor_bg": "#191314",
                   "text": "#efe4e5", "muted": "#b8a3a6", "dim": "#7d6669", "moss": "#a8505f",
                   "moss_light": "#ec95a3", "moss_dark": "#5a2a33", "number": "#e8c47a", "error": "#ff7a7a",
                   "active_line": "#241a1c", "error_line": "#3a2020", "debug_line": "#2c2224", "border": "#33282a",
                   "hover": "#261d1f", "select": "#4d2a31", "select_text": "#fbf0f1", "field_bg": "#221a1c",
                   "code_bg": "#241c1e", "inactive_select": "#36242a", "match": "#5e313b", "thumb": "#3a2e30",
                   "thumb_hover": "#554446", "button_hover": "#31262a", "accent_text": "#1a0a0d"},
        "syntax": {"command": "#ec95a3", "flow": "#f5b8c2", "string": "#c8c08a", "number": "#e8c47a",
                   "comment": "#7d6669", "brace": "#d8a8b0", "function": "#f8d0d6", "keyword": "#e8b8a0",
                   "color": "#e0a0b0", "operator": "#b0a0a2"},
    },
    "terminal": {
        "about": "green glow on black, like an old screen.", "dark": True,
        "colors": {"bg": "#050805", "panel": "#0a0f0a", "panel_alt": "#111a11", "editor_bg": "#060a06",
                   "text": "#b8f5b0", "muted": "#7cc074", "dim": "#4a7a44", "moss": "#2f8f2a",
                   "moss_light": "#5cff5c", "moss_dark": "#164a14", "number": "#e8e85c", "error": "#ff5c5c",
                   "active_line": "#0c160c", "error_line": "#2a0e0e", "debug_line": "#10240f", "border": "#1c331a",
                   "hover": "#0f1a0f", "select": "#1c4a1a", "select_text": "#e0ffe0", "field_bg": "#0a120a",
                   "code_bg": "#0c140c", "inactive_select": "#133313", "match": "#236b20", "thumb": "#1c331a",
                   "thumb_hover": "#2e5a2a", "button_hover": "#142614", "accent_text": "#021002"},
        "syntax": {"command": "#5cff5c", "flow": "#a0ffa0", "string": "#c8f070", "number": "#e8e85c",
                   "comment": "#4a7a44", "brace": "#80e0c0", "function": "#c0ffc0", "keyword": "#9af0d0",
                   "color": "#90f090", "operator": "#7cc074"},
    },
    "latte": {
        "about": "a warm light theme: cream and coffee.", "dark": False,
        "colors": {"bg": "#f4efe8", "panel": "#ebe4da", "panel_alt": "#e0d7ca", "editor_bg": "#faf7f2",
                   "text": "#2b2520", "muted": "#65594e", "dim": "#958879", "moss": "#8a5a34",
                   "moss_light": "#6e4220", "moss_dark": "#e0ccb4", "number": "#8a6200", "error": "#b8382e",
                   "active_line": "#f2ebe0", "error_line": "#f5dcd8", "debug_line": "#ebe0cc", "border": "#d4c9ba",
                   "hover": "#e4dccf", "select": "#e6d2b8", "select_text": "#1e1812", "field_bg": "#f7f3ed",
                   "code_bg": "#efe8de", "inactive_select": "#ece0ce", "match": "#e8d4b4", "thumb": "#cdc1b1",
                   "thumb_hover": "#ae9f8c", "button_hover": "#dbd1c3", "accent_text": "#ffffff"},
        "syntax": {"command": "#6e4220", "flow": "#8a4a1a", "string": "#3f7040", "number": "#8a6200",
                   "comment": "#958879", "brace": "#5a6a6a", "function": "#5a3418", "keyword": "#7a5a1a",
                   "color": "#8a5a2a", "operator": "#65594e"},
    },
}

# the "accent_color" setting: any #rrggbb here replaces the theme's own accent (and the shades made from it)
ACCENT = ""
# the "ui_scale" setting as a fraction: 1.25 makes every button, label and gap a quarter bigger
UI_ZOOM = 1.0


def themes_folder():
    from . import config
    return os.path.join(config.settings_folder(), "themes")


def _is_color(value):
    return isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) is not None


def _theme_file_name(path):
    return os.path.splitext(os.path.basename(path))[0].lower()


def theme_files():
    """{name: path} for each .json theme in the themes folder."""
    found = {}
    try:
        entries = sorted(os.listdir(themes_folder()))
    except OSError:
        return found
    for entry in entries:
        if entry.lower().endswith(".json"):
            path = os.path.join(themes_folder(), entry)
            spec = _read_theme_file(path)
            if spec is not None:
                found[str(spec.get("name") or _theme_file_name(path)).lower()] = path
    return found


def _read_theme_file(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            spec = json.load(handle)
    except (OSError, ValueError):
        return None
    return spec if isinstance(spec, dict) else None


def theme_names():
    """every theme you can pick: the built-in ones first, then your own."""
    return list(BUILTIN_THEMES) + [name for name in theme_files() if name not in BUILTIN_THEMES]


def theme_spec(name, _seen=None):
    """the theme with its base filled in: {"dark", "about", "colors", "syntax", "categories"}, or None."""
    name = str(name or "").lower()
    _seen = _seen or set()
    if name in _seen:
        return None
    _seen.add(name)
    spec = BUILTIN_THEMES.get(name)
    if spec is None:
        path = theme_files().get(name)
        spec = _read_theme_file(path) if path else None
    if spec is None:
        return None
    base_name = str(spec.get("base") or ("moss" if name != "moss" else "")).lower()
    base = theme_spec(base_name, _seen) if base_name and base_name != name else None
    result = {"dark": True, "about": "", "colors": {}, "syntax": {}, "categories": {}}
    if base:
        for key in ("colors", "syntax", "categories"):
            result[key].update(base[key])
        result["dark"] = base["dark"]
    for key in ("colors", "syntax", "categories"):
        values = spec.get(key)
        if isinstance(values, dict):
            for item, value in values.items():
                if _is_color(value):
                    result[key][str(item).lower()] = value
    if isinstance(spec.get("dark"), bool):
        result["dark"] = spec["dark"]
    result["about"] = str(spec.get("about", "") or "")
    return result


def _mix(color, other, amount):
    """blend two #rrggbb colours: amount 0 is color, 1 is other."""
    first = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    second = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(a + (b - a) * amount):02x}" for a, b in zip(first, second))


def apply_theme(name):
    """switch the palette. widgets read it when they are made, so the studio restarts to show it."""
    global DARK, THEME_NAME
    spec = theme_spec(name)
    if spec is None:
        return False
    values = dict(_MOSS_COLORS)
    for key, value in spec["colors"].items():
        target = COLOR_ALIASES.get(key, key.upper())
        if target in values:
            values[target] = value
    DARK = spec["dark"]
    accented = _apply_accent(values)
    globals().update(values)
    SYNTAX.clear()
    SYNTAX.update(_MOSS_SYNTAX)
    if not DARK and not spec["syntax"]:
        SYNTAX.update({key: _mix(value, "#000000", 0.45) for key, value in _MOSS_SYNTAX.items()})
    SYNTAX.update({key: value for key, value in spec["syntax"].items() if key in SYNTAX})
    if accented:
        SYNTAX["command"] = values["MOSS_LIGHT"]
        SYNTAX["function"] = _mix(values["MOSS_LIGHT"], values["TEXT"], 0.45)
    CATEGORY_COLORS.clear()
    CATEGORY_COLORS.update(_MOSS_CATEGORIES if DARK else
                           {key: _mix(value, "#000000", 0.45) for key, value in _MOSS_CATEGORIES.items()})
    CATEGORY_COLORS.update({key: value for key, value in spec["categories"].items() if key in CATEGORY_COLORS})
    THEME_NAME = str(name).lower()
    return True


def _apply_accent(values):
    """swap the accent shades in values for ones made from ACCENT. gives back True when it did."""
    if not _is_color(ACCENT):
        return False
    base = ACCENT.lower()
    values["MOSS"] = base
    values["MOSS_LIGHT"] = _mix(base, "#ffffff", 0.32) if DARK else _mix(base, "#000000", 0.28)
    values["MOSS_DARK"] = _mix(base, values["BG"], 0.55)
    values["SELECT"] = _mix(base, values["EDITOR_BG"], 0.7)
    values["INACTIVE_SELECT"] = _mix(base, values["EDITOR_BG"], 0.82)
    values["MATCH"] = _mix(base, values["EDITOR_BG"], 0.6)
    values["ACTIVE_LINE"] = _mix(base, values["EDITOR_BG"], 0.93)
    values["DEBUG_LINE"] = _mix(base, values["EDITOR_BG"], 0.84)
    brightness = sum(int(base[i:i + 2], 16) for i in (1, 3, 5)) / 3
    values["ACCENT_TEXT"] = "#0d0d0d" if brightness > 140 else "#ffffff"
    return True


def accent_choices():
    """(name, colour) pairs offered in settings next to "theme colour"."""
    return (("theme", ""), ("moss", "#647f4a"), ("sky", "#4a86c8"), ("violet", "#8a63c9"), ("rose", "#c45a78"),
            ("amber", "#c98a2e"), ("teal", "#2f9a8a"), ("coral", "#d0664e"), ("slate", "#6a7a8c"))


def write_example_theme():
    """make the themes folder with an example theme in it, and give back the folder."""
    folder = themes_folder()
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "my theme.json")
    if not os.path.exists(path):
        example = {"name": "my theme", "base": "midnight", "about": "copy this file to make your own theme.",
                   "dark": True,
                   "colors": {"bg": "#0f1115", "accent": "#5b8def", "accent_light": "#9cc0ff"},
                   "syntax": {"string": "#a5d6a7", "comment": "#6b7280"}}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(example, handle, indent=2)
    return folder


def _stored_settings():
    try:
        from . import config
        with open(config.settings_path(), "r", encoding="utf-8") as handle:
            stored = json.load(handle)
        return stored if isinstance(stored, dict) else {}
    except (OSError, ValueError, ImportError):
        return {}


def _theme_from_settings():
    return str(_stored_settings().get("theme") or DEFAULT_THEME)


def _startup_look():
    """the settings that must be known before the first widget is made."""
    global ACCENT, UI_ZOOM, SPEED
    stored = _stored_settings()
    accent = stored.get("accent_color")
    ACCENT = accent if _is_color(accent) else ""
    try:
        UI_ZOOM = max(0.8, min(1.6, int(stored.get("ui_scale", 100)) / 100.0))
    except (TypeError, ValueError):
        UI_ZOOM = 1.0
    SPEED = SPEEDS.get(str(stored.get("animation_speed", "normal")), 1.0)


SPEEDS = {"slow": 1.7, "normal": 1.0, "fast": 0.55}
SPEED = 1.0  # the "animation_speed" setting: every animation's time is multiplied by this
_startup_look()
if not apply_theme(_theme_from_settings()):
    apply_theme(DEFAULT_THEME)


# ----- motion --------------------------------------------------------------------
MOTION = True  # the "animations" setting; when it is off every animation jumps straight to its end


def ease_out(progress):
    return 1 - (1 - progress) ** 3


def ease_in_out(progress):
    if progress < 0.5:
        return 4 * progress ** 3
    return 1 - (-2 * progress + 2) ** 3 / 2


def ease_back(progress):
    """overshoots a little, then settles: good for things that pop in."""
    c = 1.70158
    return 1 + (c + 1) * (progress - 1) ** 3 + c * (progress - 1) ** 2


def ease_spring(progress):
    """a soft wobble that settles on 1."""
    return 1 - math.cos(progress * math.pi * 2.5) * math.exp(-5.5 * progress)


def animate(widget, duration, step, done=None, ease=ease_out):
    """call step(progress from 0 to 1) about 60 times a second for duration milliseconds.
    gives back a function that stops it early."""
    state = {"job": None}

    def finish():
        try:
            step(1.0)
        except tk.TclError:
            return
        if done:
            done()

    duration = duration * SPEED
    if not MOTION or duration <= 0:
        finish()
        return lambda: None
    start = time.perf_counter()

    def tick():
        state["job"] = None
        try:
            if not widget.winfo_exists():
                return
        except tk.TclError:
            return
        progress = min(1.0, (time.perf_counter() - start) * 1000.0 / duration)
        if progress >= 1.0:
            finish()
            return
        try:
            step(ease(progress))
            state["job"] = widget.after(16, tick)
        except tk.TclError:
            return

    def cancel():
        if state["job"]:
            try:
                widget.after_cancel(state["job"])
            except tk.TclError:
                pass
            state["job"] = None

    tick()
    return cancel


def mix(color, other, amount):
    """blend two colours for animations: amount 0 gives color, 1 gives other. names that are not #rrggbb
    switch over halfway."""
    if _is_color(color) and _is_color(other):
        return _mix(color, other, max(0.0, min(1.0, amount)))
    return other if amount >= 0.5 else color


def fade_in(window, duration=130):
    """fade a window in from see-through. does nothing where windows can't be see-through."""
    if not MOTION:
        return
    try:
        window.attributes("-alpha", 0.0)
    except tk.TclError:
        return

    def step(progress):
        window.attributes("-alpha", progress)

    animate(window, duration, step)


def slide_in(window, x, y, width, height, dx=0, dy=-6, duration=140):
    """show a window by sliding it a few pixels into place while it fades in."""
    if not MOTION:
        window.geometry(f"{width}x{height}+{x}+{y}")
        return lambda: None
    try:
        window.attributes("-alpha", 0.0)
    except tk.TclError:
        pass
    dx, dy = px(dx), px(dy)

    def step(progress):
        window.geometry(f"{width}x{height}+{round(x + dx * (1 - progress))}+{round(y + dy * (1 - progress))}")
        try:
            window.attributes("-alpha", progress)
        except tk.TclError:
            pass

    step(0.0)
    return animate(window, duration, step)


def pulse(widget, option, low, high, period=1300, widgets=None):
    """slowly breathe a colour option between low and high until the returned function is called."""
    state = {"job": None, "on": True}
    targets = widgets or [widget]
    start = time.perf_counter()

    def tick():
        state["job"] = None
        if not state["on"]:
            return
        try:
            if not widget.winfo_exists():
                return
        except tk.TclError:
            return
        if MOTION:
            phase = (time.perf_counter() - start) * 1000.0 / max(200.0, period * SPEED)
            amount = 0.5 - 0.5 * math.cos(phase * 2 * math.pi)
        else:
            amount = 1.0
        color = mix(low, high, amount)
        for target in targets:
            try:
                target.configure(**{option: color})
            except tk.TclError:
                pass
        if MOTION:
            state["job"] = widget.after(40, tick)

    def stop():
        state["on"] = False
        if state["job"]:
            try:
                widget.after_cancel(state["job"])
            except tk.TclError:
                pass
        for target in targets:
            try:
                target.configure(**{option: low})
            except tk.TclError:
                pass

    tick()
    return stop


def flash(widgets, option, rest, bright, duration=650):
    """light a colour option up to bright, then let it fade back to rest."""
    def step(progress):
        color = mix(bright, rest, progress)
        for widget in widgets:
            try:
                widget.configure(**{option: color})
            except tk.TclError:
                pass

    if not widgets:
        return lambda: None
    return animate(widgets[0], duration, step, ease=ease_in_out)


def type_in(label, text, duration=260):
    """reveal a label's text letter by letter (status messages use it)."""
    text = str(text)
    if not MOTION or len(text) < 2:
        label.configure(text=text)
        return lambda: None

    def step(progress):
        label.configure(text=text[:max(1, round(len(text) * progress))])

    return animate(label, duration, step)


def tween_colors(widgets, option, start, end, duration=220):
    """fade a colour option (like bg) on several widgets from start to end."""
    def step(progress):
        color = mix(start, end, progress)
        for widget in widgets:
            try:
                widget.configure(**{option: color})
            except tk.TclError:
                pass

    if not widgets:
        return lambda: None
    return animate(widgets[0], duration, step)


class Toast:
    """a short message that slides up in the bottom right corner of a window, then slides away."""

    shown = []

    def __init__(self, window, text, kind="info", seconds=3.5, margin=None):
        self.window = window.winfo_toplevel()
        self.margin = px(34) if margin is None else margin
        accent = {"error": ERROR, "warning": NUMBER}.get(kind, MOSS_LIGHT)
        self.frame = tk.Frame(self.window, bg=PANEL_ALT, highlightthickness=1, highlightbackground=MOSS_DARK)
        tk.Frame(self.frame, bg=accent, width=px(3)).pack(side="left", fill="y")
        self.label = tk.Label(self.frame, text=lower(text), bg=PANEL_ALT, fg=PANEL_ALT, font=ui_font(10),
                              justify="left", wraplength=px(380), padx=px(12), pady=px(8))
        self.label.pack(side="left")
        self.label.bind("<Button-1>", lambda _e: self.hide())
        self.offset = 0
        self.closing = False
        _sound("error" if kind == "error" else "warning" if kind == "warning" else "notify")
        Toast.shown.append(self)
        self._place(0.0)
        self.cancel = animate(self.frame, 200, self._place)
        self.frame.after(int(seconds * 1000), self.hide)

    def _stack_y(self):
        y = self.margin
        for toast in Toast.shown:
            if toast is self:
                break
            try:
                y += toast.frame.winfo_reqheight() + px(8)
            except tk.TclError:
                pass
        return y

    def _place(self, progress):
        drop = px(18) * (1 - progress)
        self.frame.place(relx=1.0, rely=1.0, x=-px(16), y=-(self._stack_y() - drop), anchor="se")
        self.label.configure(fg=mix(PANEL_ALT, TEXT, progress))
        self.frame.lift()

    def hide(self):
        if self.closing:
            return
        self.closing = True

        def step(progress):
            self._place(1.0 - progress)

        def gone():
            if self in Toast.shown:
                Toast.shown.remove(self)
            try:
                self.frame.destroy()
            except tk.TclError:
                pass
            for toast in Toast.shown:
                try:
                    toast._place(1.0)
                except tk.TclError:
                    pass

        try:
            self.cancel()
            animate(self.frame, 160, step, done=gone)
        except tk.TclError:
            gone()


def _sound(name):
    """play one of the studio's soft sounds (studio/sounds.py), when sounds are on."""
    try:
        from . import sounds
        sounds.play(name)
    except Exception:  # noqa: BLE001 - a missing sound must never break the window
        pass


def toast(window, text, kind="info", seconds=3.5):
    try:
        return Toast(window, text, kind, seconds)
    except tk.TclError:
        return None

# ----- fonts -------------------------------------------------------------------
UI_FAMILY = "Segoe UI"
MONO_FAMILY = "Consolas"
ICON_FAMILY = "Segoe MDL2 Assets"
_SCALE = 1.0

ICONS = {
    "run": "", "stop": "", "pause": "", "step": "", "save": "",
    "open": "", "new": "", "export": "", "convert": "", "blocks": "",
    "code": "", "settings": "", "help": "", "files": "", "outline": "",
    "assets": "", "search": "", "close": "", "check": "", "warning": "",
    "error": "", "info": "", "play": "", "folder": "", "file": "",
    "image": "", "sound": "", "chevron": "", "down": "", "up": "",
    "brush": "", "trash": "", "add": "", "copy": "", "palette": "",
    "bug": "", "learn": "", "game": "", "dot": "", "refresh": "",
    "menu": "", "more": "", "back": "", "breakpoint": "",
}


def pick_fonts(root):
    """choose the best fonts installed on this computer."""
    global UI_FAMILY, MONO_FAMILY, ICON_FAMILY, _SCALE
    families = set(tkfont.families(root))
    for name in ("Segoe UI Variable Text", "Segoe UI", "Tahoma", "DejaVu Sans"):
        if name in families:
            UI_FAMILY = name
            break
    for name in ("Cascadia Mono", "Cascadia Code", "JetBrains Mono", "Consolas", "Courier New"):
        if name in families:
            MONO_FAMILY = name
            break
    for name in ("Segoe Fluent Icons", "Segoe MDL2 Assets"):
        if name in families:
            ICON_FAMILY = name
            break
    else:
        ICON_FAMILY = ""
    try:
        _SCALE = max(1.0, root.winfo_fpixels("1i") / 96.0)
    except tk.TclError:
        _SCALE = 1.0


def px(value):
    """scale a pixel size for high dpi screens (and the ui scale setting)."""
    return int(round(value * _SCALE * UI_ZOOM))


def _zoomed(size):
    return max(6, int(round(size * UI_ZOOM)))


def ui_font(size=10, weight="normal"):
    return (UI_FAMILY, _zoomed(size), weight)


def mono_font(size=11, weight="normal"):
    return (MONO_FAMILY, _zoomed(size), weight)


def icon_font(size=11):
    return (ICON_FAMILY or UI_FAMILY, _zoomed(size))


# fonts the editor can use, best first. only the ones installed on this computer are offered.
EDITOR_FONTS = ("Cascadia Mono", "Cascadia Code", "JetBrains Mono", "Fira Code", "Source Code Pro", "Consolas",
                "Lucida Console", "Courier New", "DejaVu Sans Mono", "Menlo", "Monaco")


def editor_fonts(root):
    """the editor fonts installed here, as (shown name, family) pairs."""
    try:
        installed = {name.lower(): name for name in tkfont.families(root)}
    except tk.TclError:
        installed = {}
    return [(family.lower(), installed[family.lower()]) for family in EDITOR_FONTS if family.lower() in installed]


def editor_family(settings, root=None):
    """the font family the code editor should use: the editor_font setting when it is installed."""
    wanted = str(settings.get("editor_font") or "").lower()
    if wanted and root is not None:
        for shown, family in editor_fonts(root):
            if shown == wanted:
                return family
    return MONO_FAMILY


def icon(name, fallback=""):
    if not ICON_FAMILY:
        return fallback
    return ICONS.get(name, fallback)


# ----- windows -------------------------------------------------------------------
def enable_dpi_awareness():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _colorref(hex_color):
    hex_color = hex_color.lstrip("#")
    red, green, blue = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return blue << 16 | green << 8 | red


def square_window(window, caption=BG, border=MOSS_DARK, text=TEXT):
    """ask windows 11 for square corners and a soft black title bar."""
    if sys.platform != "win32":
        return
    try:
        window.update_idletasks()
        handle = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        dwm = ctypes.windll.dwmapi

        def setattr_(attribute, value):
            data = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(handle, attribute, ctypes.byref(data), ctypes.sizeof(data))

        setattr_(20, 1 if DARK else 0)  # dark mode title bar
        setattr_(33, 1)  # DWMWCP_DONOTROUND: square corners
        setattr_(34, _colorref(border))
        setattr_(35, _colorref(caption))
        setattr_(36, _colorref(text))
    except (AttributeError, OSError, tk.TclError):
        pass


def lower(text):
    return str(text).lower()


def plural(count, word, many=None):
    """'1 file', '3 files'."""
    return f"{count} {word if count == 1 else (many or word + 's')}"


# ----- ttk styles ----------------------------------------------------------------
def setup_styles(root):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(".", background=PANEL, foreground=TEXT, fieldbackground=PANEL_ALT, bordercolor=BORDER,
                    lightcolor=PANEL, darkcolor=PANEL, troughcolor=PANEL, focuscolor=MOSS,
                    selectbackground=SELECT, selectforeground=SELECT_TEXT, font=ui_font(10), relief="flat")
    for orient in ("Vertical", "Horizontal"):
        name = f"Flat.{orient}.TScrollbar"
        style.layout(name, [(f"{orient}.Scrollbar.trough", {"sticky": "nswe", "children": [
            (f"{orient}.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
        style.configure(name, background=THUMB, troughcolor=PANEL, bordercolor=PANEL, lightcolor=THUMB,
                        darkcolor=THUMB, arrowsize=px(10), gripcount=0, relief="flat", borderwidth=0)
        style.map(name, background=[("active", THUMB_HOVER), ("pressed", MOSS)],
                  lightcolor=[("active", THUMB_HOVER)], darkcolor=[("active", THUMB_HOVER)])
    style.configure("Flat.Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, borderwidth=0,
                    rowheight=px(24), font=ui_font(10), relief="flat")
    style.map("Flat.Treeview", background=[("selected", SELECT)], foreground=[("selected", SELECT_TEXT)])
    style.configure("Flat.Treeview.Heading", background=PANEL_ALT, foreground=MUTED, relief="flat",
                    borderwidth=0, font=ui_font(9))
    style.map("Flat.Treeview.Heading", background=[("active", HOVER)])
    style.layout("Flat.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure("Flat.Horizontal.TProgressbar", troughcolor=PANEL_ALT, background=MOSS_LIGHT,
                    bordercolor=PANEL_ALT, lightcolor=MOSS_LIGHT, darkcolor=MOSS, thickness=px(6))
    style.configure("Flat.TCombobox", fieldbackground=PANEL_ALT, background=PANEL_ALT, foreground=TEXT,
                    arrowcolor=MUTED, bordercolor=BORDER, lightcolor=PANEL_ALT, darkcolor=PANEL_ALT)
    root.option_add("*TCombobox*Listbox.background", PANEL_ALT)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", SELECT)
    root.option_add("*Font", ui_font(10))
    return style


def scrollbar(parent, orient="vertical", command=None):
    name = "Flat.Vertical.TScrollbar" if orient == "vertical" else "Flat.Horizontal.TScrollbar"
    return ttk.Scrollbar(parent, orient=orient, command=command, style=name)


# ----- widgets ---------------------------------------------------------------------
class BracketButton(tk.Canvas):
    """a flat square button with the moss corner-bracket accent.

    kinds: "normal", "accent" (filled moss), "ghost" (no background), "danger".
    """

    def __init__(self, parent, text="", command=None, icon_name=None, kind="normal", size=10, width=None,
                 tooltip=None, pad_x=12, pad_y=6, bg=None):
        self.parent_bg = bg or _bg_of(parent)
        super().__init__(parent, highlightthickness=0, bd=0, bg=self.parent_bg, cursor="hand2",
                         takefocus=1)
        self.command = command
        self.kind = kind
        self.text = lower(text)
        self.icon_text = icon(icon_name) if icon_name else ""
        self.font = ui_font(size)
        self.icon_font = icon_font(size + 1)
        self.pad_x, self.pad_y = px(pad_x), px(pad_y)
        self.fixed_width = px(width) if width else None
        self.hover = False
        self.glow = 0.0  # 0 resting, 1 fully hovered; animated between the two
        self._glow_stop = None
        self.pressed = False
        self.enabled = True
        self.checked = False
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<KeyPress-space>", lambda _e: self.invoke())
        self.bind("<KeyPress-Return>", lambda _e: self.invoke())
        self.bind("<FocusIn>", lambda _e: self.draw())
        self.bind("<FocusOut>", lambda _e: self.draw())
        if tooltip:
            Tooltip(self, tooltip)
        self._measure()
        self.draw()

    def _measure(self):
        measure = tkfont.Font(font=self.font)
        width = measure.measure(self.text) if self.text else 0
        if self.icon_text:
            width += tkfont.Font(font=self.icon_font).measure(self.icon_text) + (px(7) if self.text else 0)
        height = measure.metrics("linespace")
        self.configure(width=self.fixed_width or width + self.pad_x * 2, height=height + self.pad_y * 2)

    def configure_text(self, text=None, icon_name=None):
        if text is not None:
            self.text = lower(text)
        if icon_name is not None:
            self.icon_text = icon(icon_name)
        self._measure()
        self.draw()

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        self.configure(cursor="hand2" if self.enabled else "arrow")
        self.draw()

    def set_checked(self, checked):
        self.checked = bool(checked)
        self.draw()

    def colors(self):
        if 0.0 < self.glow < 1.0 and self.enabled:
            hovered = self.hover
            self.hover = False
            rest = self._colors()
            self.hover = True
            lit = self._colors()
            self.hover = hovered
            return tuple(mix(a, b, self.glow) for a, b in zip(rest, lit))
        return self._colors()

    def _colors(self):
        if not self.enabled:
            return (PANEL if self.kind != "ghost" else self.parent_bg), DIM, BORDER
        if self.kind == "accent":
            fill = MOSS_LIGHT if self.hover else MOSS
            return fill, ACCENT_TEXT if self.hover else SELECT_TEXT, MOSS_LIGHT
        if self.kind == "danger":
            fill = ERROR_LINE if self.hover else PANEL_ALT
            return fill, ERROR if self.hover else TEXT, ERROR
        if self.kind == "ghost":
            fill = HOVER if self.hover or self.checked else self.parent_bg
            return fill, (MOSS_LIGHT if self.checked else TEXT if self.hover else MUTED), MOSS
        fill = BUTTON_HOVER if self.hover else PANEL_ALT
        if self.checked:
            fill = SELECT
        return fill, TEXT, MOSS_LIGHT if self.hover or self.checked else MOSS

    def draw(self):
        self.delete("all")
        width, height = int(self["width"]), int(self["height"])
        fill, foreground, accent = self.colors()
        if self.pressed and self.enabled:
            fill = MOSS_DARK if self.kind != "accent" else MOSS
        self.create_rectangle(0, 0, width, height, fill=fill, outline=fill)
        if self.kind != "ghost" or self.hover or self.checked or self.focus_get() is self:
            arm = px(5)
            line = px(1) if self.kind != "accent" else 0
            if line:
                for x, y, dx, dy in ((0, 0, 1, 1), (width - 1, 0, -1, 1), (0, height - 1, 1, -1),
                                     (width - 1, height - 1, -1, -1)):
                    self.create_line(x, y, x + dx * arm, y, fill=accent, width=line)
                    self.create_line(x, y, x, y + dy * arm, fill=accent, width=line)
        cursor_x = width / 2
        if self.icon_text and self.text:
            icon_width = tkfont.Font(font=self.icon_font).measure(self.icon_text)
            text_width = tkfont.Font(font=self.font).measure(self.text)
            start = (width - icon_width - text_width - px(7)) / 2
            self.create_text(start, height / 2 + px(1), text=self.icon_text, font=self.icon_font, fill=foreground,
                             anchor="w")
            self.create_text(start + icon_width + px(7), height / 2, text=self.text, font=self.font,
                             fill=foreground, anchor="w")
        elif self.icon_text:
            self.create_text(cursor_x, height / 2 + px(1), text=self.icon_text, font=self.icon_font,
                             fill=foreground)
        else:
            self.create_text(cursor_x, height / 2, text=self.text, font=self.font, fill=foreground)

    def _glow_to(self, target, duration):
        if self._glow_stop:
            self._glow_stop()
        start = self.glow

        def step(progress):
            self.glow = start + (target - start) * progress
            self.draw()

        self._glow_stop = animate(self, duration, step)

    def _enter(self, _event):
        self.hover = True
        self._glow_to(1.0, 90)

    def _leave(self, _event):
        self.hover = False
        self.pressed = False
        self._glow_to(0.0, 180)

    def _press(self, _event):
        if self.enabled:
            self.pressed = True
            self.draw()

    def _release(self, event):
        was_pressed = self.pressed
        self.pressed = False
        self.draw()
        inside = 0 <= event.x <= int(self["width"]) and 0 <= event.y <= int(self["height"])
        if was_pressed and inside:
            self.invoke()

    def invoke(self):
        if self.enabled and self.command:
            self.command()


class Toggle(tk.Frame):
    """a square checkbox with a lowercase label."""

    def __init__(self, parent, text, variable=None, command=None, bg=None):
        bg = bg or _bg_of(parent)
        super().__init__(parent, bg=bg)
        self.variable = variable or tk.BooleanVar(value=False)
        self.command = command
        self.box = tk.Canvas(self, width=px(16), height=px(16), bg=bg, highlightthickness=0, cursor="hand2")
        self.box.pack(side="left")
        self.label = tk.Label(self, text=lower(text), bg=bg, fg=TEXT, font=ui_font(10), cursor="hand2")
        self.label.pack(side="left", padx=(px(8), 0))
        for widget in (self, self.box, self.label):
            widget.bind("<Button-1>", self.flip)
        self.fill = 1.0 if self.variable.get() else 0.0
        self._fill_stop = None
        self.variable.trace_add("write", lambda *_: self._animate_to())
        self.draw()

    def _animate_to(self):
        target = 1.0 if self.variable.get() else 0.0
        if self._fill_stop:
            self._fill_stop()
        start = self.fill

        def step(progress):
            self.fill = start + (target - start) * progress
            self.draw()

        self._fill_stop = animate(self, 140, step)

    def flip(self, _event=None):
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()

    def draw(self):
        self.box.delete("all")
        size = px(16)
        fill = getattr(self, "fill", 1.0 if self.variable.get() else 0.0)
        self.box.create_rectangle(1, 1, size - 1, size - 1, outline=mix(THUMB_HOVER, MOSS_LIGHT, fill),
                                  fill=mix(PANEL_ALT, MOSS, fill))
        if fill > 0.35:
            self.box.create_line(px(4), px(8), px(7), px(11), px(12), px(5), fill=mix(MOSS, SELECT_TEXT, fill),
                                 width=px(2))


class Segmented(tk.Frame):
    """square toggle buttons standing in for radio buttons."""

    def __init__(self, parent, options, variable, command=None, bg=None, size=10):
        bg = bg or _bg_of(parent)
        super().__init__(parent, bg=bg)
        self.variable = variable
        self.command = command
        self.buttons = {}
        for value, label in options:
            button = BracketButton(self, label, command=lambda v=value: self.choose(v), kind="normal", size=size,
                                   bg=bg, pad_x=10, pad_y=5)
            button.pack(side="left", padx=(0, px(4)))
            self.buttons[value] = button
        self._trace = self.variable.trace_add("write", lambda *_: self.refresh())
        self.bind("<Destroy>", self._forget_variable, add="+")
        self.refresh()

    def _forget_variable(self, event):
        # a segmented row can be rebuilt over the same variable; the old one must stop listening
        if event.widget is self and self._trace:
            try:
                self.variable.trace_remove("write", self._trace)
            except tk.TclError:
                pass
            self._trace = None

    def choose(self, value):
        self.variable.set(value)
        if self.command:
            self.command(value)

    def refresh(self):
        current = self.variable.get()
        for value, button in self.buttons.items():
            button.set_checked(value == current)


def flat_entry(parent, textvariable=None, width=20, mono=False, bg=PANEL_ALT):
    entry = tk.Entry(parent, textvariable=textvariable, width=width, bg=bg, fg=TEXT, insertbackground=TEXT,
                     relief="flat", highlightthickness=1, highlightbackground=BORDER, highlightcolor=MOSS,
                     selectbackground=SELECT, selectforeground=SELECT_TEXT, bd=px(4),
                     font=mono_font(10) if mono else ui_font(10))
    return entry


def label(parent, text, size=10, color=TEXT, weight="normal", bg=None, **kwargs):
    return tk.Label(parent, text=lower(text), bg=bg or _bg_of(parent), fg=color, font=ui_font(size, weight),
                    **kwargs)


def _bg_of(widget):
    try:
        return widget.cget("bg")
    except tk.TclError:
        return PANEL


class Tooltip:
    """a small square hint that appears when the pointer rests on a widget."""

    def __init__(self, widget, text, delay=550):
        self.widget = widget
        self.text = lower(text)
        self.delay = delay
        self.window = None
        self.job = None
        widget.bind("<Enter>", self.schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def schedule(self, _event=None):
        self.cancel()
        self.job = self.widget.after(self.delay, self.show)

    def cancel(self):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None

    def show(self):
        if self.window or not self.text:
            return
        x = self.widget.winfo_rootx() + px(4)
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + px(6)
        self.window = popup_window(self.widget)
        frame = tk.Frame(self.window, bg=PANEL_ALT, highlightthickness=1, highlightbackground=MOSS_DARK)
        frame.pack()
        tk.Label(frame, text=self.text, bg=PANEL_ALT, fg=TEXT, font=ui_font(9), justify="left",
                 wraplength=px(360)).pack(padx=px(8), pady=px(5))
        self.window.update_idletasks()
        self.window.deiconify()
        slide_in(self.window, x, y, self.window.winfo_reqwidth(), self.window.winfo_reqheight(), dy=-3,
                 duration=110)

    def hide(self, _event=None):
        self.cancel()
        if self.window:
            self.window.destroy()
            self.window = None


def popup_window(master):
    window = tk.Toplevel(master)
    window.withdraw()
    window.overrideredirect(True)
    window.configure(bg=PANEL_ALT)
    try:
        window.attributes("-topmost", True)
    except tk.TclError:
        pass
    square_window(window, border=MOSS_DARK)
    return window


class PopupMenu:
    """a square, lowercase replacement for native menus (which windows 11 rounds).

    items: (label, command), (label, command, shortcut), {"label", "command", "shortcut", "checked",
    "enabled"}, "-" for a separator, or (label, [items]) for a submenu.
    """

    active = None

    def __init__(self, master, items, on_close=None):
        self.master = master
        self.items = [self._normalise(item) for item in items]
        self.on_close = on_close
        self.window = None
        self.rows = []
        self.index = -1
        self.child = None
        self.child_index = -1
        self.parent_menu = None
        self._global = None

    @staticmethod
    def _normalise(item):
        if item == "-" or item is None:
            return None
        if isinstance(item, dict):
            return item
        if len(item) == 2 and isinstance(item[1], list):
            return {"label": item[0], "submenu": item[1]}
        return {"label": item[0], "command": item[1], "shortcut": item[2] if len(item) > 2 else ""}

    def post(self, x, y):
        if PopupMenu.active and self.parent_menu is None:
            PopupMenu.active.close()
        if self.parent_menu is None:
            PopupMenu.active = self
        self.window = popup_window(self.master)
        frame = tk.Frame(self.window, bg=PANEL_ALT, highlightthickness=1, highlightbackground=MOSS_DARK)
        frame.pack(fill="both", expand=True)
        for item in self.items:
            if item is None:
                tk.Frame(frame, bg=BORDER, height=1).pack(fill="x", padx=px(8), pady=px(4))
                continue
            row = tk.Frame(frame, bg=PANEL_ALT, cursor="hand2")
            row.pack(fill="x")
            enabled = item.get("enabled", True)
            mark = icon("check", "x") if item.get("checked") else ""
            check = tk.Label(row, text=mark, width=2, bg=PANEL_ALT, fg=MOSS_LIGHT, font=icon_font(9))
            check.pack(side="left", padx=(px(6), 0))
            name = tk.Label(row, text=lower(item["label"]), bg=PANEL_ALT, fg=TEXT if enabled else DIM,
                            font=ui_font(10), anchor="w")
            name.pack(side="left", fill="x", expand=True, padx=(px(2), px(24)), pady=px(5))
            hint_text = lower(item.get("shortcut", "")) if "submenu" not in item else icon("chevron", ">")
            hint = tk.Label(row, text=hint_text, bg=PANEL_ALT, fg=DIM,
                            font=ui_font(9) if "submenu" not in item else icon_font(8))
            hint.pack(side="right", padx=(0, px(12)))
            entry = (row, (row, check, name, hint), item)
            self.rows.append(entry)
            for widget in entry[1]:
                widget.bind("<Enter>", lambda _e, i=len(self.rows) - 1: self.highlight(i))
                widget.bind("<ButtonRelease-1>", lambda _e, i=len(self.rows) - 1: self.activate(i))
        self.window.update_idletasks()
        width = max(self.window.winfo_reqwidth(), px(200))
        height = self.window.winfo_reqheight()
        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()
        x = min(x, screen_w - width - 4)
        y = min(y, screen_h - height - 4)
        self.window.deiconify()
        slide_in(self.window, x, y, width, height, dx=-6 if self.parent_menu else 0,
                 dy=0 if self.parent_menu else -6, duration=120)
        self.window.lift()
        if self.parent_menu is None:
            _sound("click")
            self.window.focus_force()
            self.window.bind("<FocusOut>", self._focus_out)
            self.window.bind("<Escape>", lambda _e: self.close())
            self.window.bind("<Down>", lambda _e: self.move(1))
            self.window.bind("<Up>", lambda _e: self.move(-1))
            self.window.bind("<Return>", lambda _e: (self.child or self).activate((self.child or self).index))
            self.window.bind("<Right>", lambda _e: self.open_child())
            self.window.bind("<Left>", lambda _e: self.close_child())
            self._global = None
            # bind later so the click that opened the menu doesn't close it straight away
            self.window.after(80, self._bind_outside_click)
        return self

    def _bind_outside_click(self):
        if self.window:
            self._global = self.master.winfo_toplevel().bind("<Button-1>", lambda _e: self.close(), add="+")

    def _focus_out(self, _event):
        self.window.after(60, self._check_focus)

    def _check_focus(self):
        if not self.window:
            return
        focused = self.window.focus_get()
        menus = [self]
        child = self.child
        while child:
            menus.append(child)
            child = child.child
        if focused is None or not any(menu.window and str(focused).startswith(str(menu.window)) for menu in menus):
            self.close()

    def highlight(self, index):
        if not self.rows:
            return
        self.index = index % len(self.rows)
        for number, (row, widgets, item) in enumerate(self.rows):
            on = number == self.index and item.get("enabled", True)
            for widget in widgets:
                widget.configure(bg=SELECT if on else PANEL_ALT)
        item = self.rows[self.index][2]
        if self.child and self.child_index != self.index:
            self.close_child()
        if "submenu" in item and not self.child:
            self.window.after(180, lambda i=self.index: self.index == i and self.open_child())

    def move(self, step):
        target = self.child if self.child else self
        if target.rows:
            target.highlight(target.index + step if target.index >= 0 else 0)

    def open_child(self):
        if self.index < 0 or self.child:
            return
        item = self.rows[self.index][2]
        if "submenu" not in item:
            return
        row = self.rows[self.index][0]
        self.child = PopupMenu(self.master, item["submenu"])
        self.child.parent_menu = self
        self.child_index = self.index
        self.child.post(row.winfo_rootx() + row.winfo_width(), row.winfo_rooty() - px(1))

    def close_child(self):
        if self.child:
            self.child.close()
            self.child = None

    def activate(self, index):
        if index < 0 or index >= len(self.rows):
            return
        item = self.rows[index][2]
        if not item.get("enabled", True):
            return
        if "submenu" in item:
            self.open_child()
            return
        command = item.get("command")
        root = self
        while root.parent_menu:
            root = root.parent_menu
        root.close()
        if command:
            self.master.after(10, command)

    def close(self):
        self.close_child()
        if self.window:
            try:
                if self.parent_menu is None and self._global:
                    self.master.winfo_toplevel().unbind("<Button-1>", self._global)
            except (tk.TclError, AttributeError):
                pass
            self.window.destroy()
            self.window = None
        if PopupMenu.active is self:
            PopupMenu.active = None
            if self.on_close:
                self.on_close()


def show_menu(widget, items, x=None, y=None, on_close=None):
    if x is None:
        x = widget.winfo_rootx()
        y = widget.winfo_rooty() + widget.winfo_height()
    return PopupMenu(widget, items, on_close=on_close).post(x, y)


class ScrollFrame(tk.Frame):
    """a frame whose contents scroll vertically with the mouse wheel."""

    def __init__(self, parent, bg=PANEL):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.bar = scrollbar(self, "vertical", self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.window = self.canvas.create_window(0, 0, anchor="nw", window=self.inner)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.bind_wheel(self.canvas)
        self.bind_wheel(self.inner)

    def bind_wheel(self, widget):
        widget.bind("<MouseWheel>", self._wheel, add="+")

    def bind_tree(self, widget):
        self.bind_wheel(widget)
        for child in widget.winfo_children():
            self.bind_tree(child)

    def _wheel(self, event):
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(int(-event.delta / 120) * 3, "units")
        return "break"

    def to_top(self):
        self.canvas.yview_moveto(0)


# ----- switching themes while the studio is open ------------------------------------------------------------------
_FG_FIRST = ("TEXT", "MUTED", "DIM", "MOSS_LIGHT", "MOSS", "SELECT_TEXT", "ACCENT_TEXT", "NUMBER", "ERROR")
_BG_FIRST = ("BG", "PANEL", "PANEL_ALT", "EDITOR_BG", "FIELD_BG", "CODE_BG", "HOVER", "BORDER", "SELECT")
_FG_OPTIONS = ("foreground", "activeforeground", "selectforeground", "disabledforeground", "insertbackground")
_BG_OPTIONS = ("background", "activebackground", "highlightbackground", "highlightcolor", "selectbackground",
               "troughcolor", "readonlybackground", "inactiveselectbackground", "selectcolor", "disabledbackground")
_ITEM_OPTIONS = ("fill", "outline", "activefill", "activeoutline", "disabledfill", "disabledoutline")
_TAG_OPTIONS = ("foreground", "background", "selectbackground", "selectforeground", "underlinefg", "overstrikefg")


def _palette():
    values = {name: str(globals()[name]).lower() for name in COLOR_NAMES}
    values.update({f"syntax:{key}": str(value).lower() for key, value in SYNTAX.items()})
    values.update({f"category:{key}": str(value).lower() for key, value in CATEGORY_COLORS.items()})
    return values


def _color_map(old, new, first):
    """old colour -> new colour. when two names shared a colour, the names in `first` win."""
    mapping = {}
    for name in list(first) + [name for name in old if name not in first]:
        if name in old and old[name] not in mapping:
            mapping[old[name]] = new[name]
    return {key: value for key, value in mapping.items() if key != value}


def switch_theme(root, name, modules=None):
    """change the theme without restarting: swap every widget's old palette colours for the new ones.

    returns False when there is no theme with that name. anything that mixes its own shades keeps the old
    ones until it is drawn again; a restart always gives the cleanest result.
    """
    old = _palette()
    if not apply_theme(name):
        return False
    new = _palette()
    general = _color_map(old, new, ())
    if not general:
        return True
    maps = {"fg": _color_map(old, new, _FG_FIRST), "bg": _color_map(old, new, _BG_FIRST), "any": general}
    _update_names(old, new, modules)
    setup_styles(root)
    _recolor_tree(root, maps)
    square_window(root, caption=BG)
    return True


def _update_names(old, new, modules=None):
    """modules that did `from .theme import BG, ...` hold their own copies of the colours, and so do default
    arguments (flat_entry's bg=PANEL_ALT). bring both up to date so new widgets get the new look."""
    lookup = {old[name]: new[name] for name in COLOR_NAMES}
    targets = modules if modules is not None else [module for key, module in list(sys.modules.items())
                                                   if module is not None and (key == "studio" or
                                                                              key.startswith("studio."))]
    for module in targets:
        space = vars(module)
        for name in COLOR_NAMES:
            if isinstance(space.get(name), str) and module is not sys.modules[__name__]:
                space[name] = new[name]
        for value in list(space.values()):
            functions = [value]
            if isinstance(value, type) and getattr(value, "__module__", "") == module.__name__:
                functions = [item for item in vars(value).values() if callable(item)]
            for function in functions:
                _fix_defaults(function, lookup)


def _fix_defaults(function, lookup):
    code_owner = getattr(function, "__func__", function)
    defaults = getattr(code_owner, "__defaults__", None)
    if defaults and any(isinstance(item, str) and item.lower() in lookup for item in defaults):
        try:
            code_owner.__defaults__ = tuple(lookup.get(item.lower(), item) if isinstance(item, str) else item
                                            for item in defaults)
        except (AttributeError, TypeError):
            pass
    keywords = getattr(code_owner, "__kwdefaults__", None)
    if keywords:
        for key, item in list(keywords.items()):
            if isinstance(item, str) and item.lower() in lookup:
                keywords[key] = lookup[item.lower()]


def _swap(value, mapping):
    if not isinstance(value, str) or not value.startswith("#"):
        return None
    return mapping.get(value.lower())


def _recolor_tree(widget, maps):
    stack = [widget]
    while stack:
        current = stack.pop()
        try:
            _recolor(current, maps)
            stack.extend(current.winfo_children())
        except tk.TclError:
            continue


def _recolor(widget, maps):
    changes = {}
    for option in _FG_OPTIONS + _BG_OPTIONS:
        try:
            value = widget.cget(option)
        except (tk.TclError, ValueError):
            continue
        swapped = _swap(str(value), maps["fg" if option in _FG_OPTIONS else "bg"])
        if swapped:
            changes[option] = swapped
    if changes:
        try:
            widget.configure(**changes)
        except tk.TclError:
            pass
    for attribute in ("parent_bg", "bg_color", "base_bg", "rest_bg"):
        value = getattr(widget, attribute, None)
        swapped = _swap(value, maps["bg"])
        if swapped:
            setattr(widget, attribute, swapped)
    if isinstance(widget, tk.Toplevel):
        try:
            if not widget.wm_overrideredirect():
                square_window(widget)
        except tk.TclError:
            pass
    if isinstance(widget, tk.Canvas):
        _recolor_canvas(widget, maps["any"])
    elif isinstance(widget, tk.Text):
        _recolor_tags(widget, maps["any"])
    hook = getattr(widget, "theme_changed", None)
    if callable(hook):
        try:
            hook()
        except Exception:  # noqa: BLE001 - one widget must not stop the rest
            pass
    elif isinstance(widget, (BracketButton, Toggle)):
        try:
            widget.draw()
        except tk.TclError:
            pass


def _recolor_canvas(canvas, mapping):
    for item in canvas.find_all():
        changes = {}
        for option in _ITEM_OPTIONS:
            try:
                swapped = _swap(canvas.itemcget(item, option), mapping)
            except tk.TclError:
                continue
            if swapped:
                changes[option] = swapped
        if changes:
            try:
                canvas.itemconfigure(item, **changes)
            except tk.TclError:
                pass


def _recolor_tags(text, mapping):
    for tag in text.tag_names():
        changes = {}
        for option in _TAG_OPTIONS:
            try:
                swapped = _swap(str(text.tag_cget(tag, option)), mapping)
            except tk.TclError:
                continue
            if swapped:
                changes[option] = swapped
        if changes:
            try:
                text.tag_configure(tag, **changes)
            except tk.TclError:
                pass
