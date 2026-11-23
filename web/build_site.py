"""build the online playground into a folder (default: _site) ready for github pages.

    python web/build_site.py            # writes _site/
    python web/build_site.py out        # writes out/
    python -m http.server -d _site      # then open http://localhost:8000 to try it

the page itself lives in web/. this copies it together with the real gublan files it needs (the checker,
the javascript translator, the javascript runtime, the modules and the examples), so the website always
runs the same language as the studio. nothing in this folder is used by the windows app or the installer.
"""
import ast
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")

PAGE_FILES = ["index.html", "playground.css", "playground.js", "bridge.py"]
PYTHON_FILES = ["gublancore.py", "gublantranslate.py", "studio/__init__.py", "studio/version.py"]
OTHER_FILES = ["runtimes/gublan_runtime.js", "logo.png", "logo.ico"]

# examples offered in the picker, in this order (anything else in examples/ is added after them)
FIRST_EXAMPLES = ["hello.gubl", "examples/responsive_2d.gubl", "examples/maps_and_vectors.gubl"]


def _copy(relative, out, target=None):
    source = os.path.join(ROOT, relative)
    destination = os.path.join(out, target or relative)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    shutil.copyfile(source, destination)


def _title(path):
    """an example's name for the picker: its first comment ('// pong: ...' -> 'pong'), else the file name."""
    with open(os.path.join(ROOT, path), "r", encoding="utf-8") as handle:
        first = handle.readline().strip()
    match = re.match(r"//\s*([^:]+)", first)
    if match:
        return match.group(1).strip()
    return os.path.splitext(os.path.basename(path))[0].replace("_", " ")


def _uses_3d(path):
    with open(os.path.join(ROOT, path), "r", encoding="utf-8") as handle:
        return any(re.match(r"\s*mode\s+3d\b", line) for line in handle)


def _constants(relative):
    """the top-level names of a python file whose values can be read without running it."""
    with open(os.path.join(ROOT, relative), "r", encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    found = {}

    def value(node):
        if isinstance(node, ast.Name) and node.id in found:
            return found[node.id]
        if isinstance(node, ast.Dict):
            return {value(k): value(v) for k, v in zip(node.keys, node.values)}
        if isinstance(node, (ast.Tuple, ast.List)):
            return [value(item) for item in node.elts]
        return ast.literal_eval(node)

    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                found[node.targets[0].id] = value(node.value)
            except (ValueError, TypeError, SyntaxError):
                continue
        elif isinstance(node, ast.FunctionDef) and node.name == "accent_choices":
            for inner in ast.walk(node):
                if isinstance(inner, ast.Return):
                    found["ACCENTS"] = value(inner.value)
    return found


def _looks():
    """gublan studio's themes, accent colours and game window presets, so the playground can offer the same ones."""
    try:
        theme = _constants("studio/theme.py")
        moss_colors = {name.lower(): theme[name] for name in theme["COLOR_NAMES"]}
        themes = {}
        for name, info in theme["BUILTIN_THEMES"].items():
            themes[name] = {"about": info.get("about", ""), "dark": bool(info.get("dark", True)),
                            "colors": dict(moss_colors, **info.get("colors", {})),
                            "syntax": dict(theme["SYNTAX"], **info.get("syntax", {}))}
        accents = [{"name": name, "color": color} for name, color in theme.get("ACCENTS", [])]
    except (OSError, KeyError, TypeError, ValueError, SyntaxError):
        themes, accents = {}, []
    try:
        core = _constants("gublancore.py")
        dialogs = _constants("studio/dialogs.py")
        game = {"defaults": core["GAME_STYLE"], "positions": core["DIALOG_POSITIONS"],
                "animations": core["DIALOG_ANIMATIONS"], "looks": dialogs["POPUP_LOOKS"],
                "sizes": dialogs["WINDOW_SIZES"], "demo": dialogs["STYLE_DEMO"]}
    except (OSError, KeyError, TypeError, ValueError, SyntaxError):
        game = {}
    return themes, accents, game


def build(out):
    out = os.path.abspath(out)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)

    for name in PAGE_FILES:
        _copy(os.path.join("web", name), out, name)
    for relative in PYTHON_FILES:
        _copy(relative, out, os.path.join("gublan", relative))
    for relative in OTHER_FILES:
        _copy(relative, out, os.path.join("gublan", relative) if relative.startswith("runtimes") else relative)

    modules = sorted(name for name in os.listdir(os.path.join(ROOT, "modules")) if name.endswith(".gubl"))
    for name in modules:
        _copy(os.path.join("modules", name), out, os.path.join("gublan", "modules", name))

    found = sorted("examples/" + name for name in os.listdir(os.path.join(ROOT, "examples")) if name.endswith(".gubl"))
    ordered = [path for path in FIRST_EXAMPLES if os.path.isfile(os.path.join(ROOT, path))]
    ordered += [path for path in found if path not in ordered]
    examples = []
    for path in ordered:
        _copy(path, out, os.path.join("examples", os.path.basename(path)))
        examples.append({"file": "examples/" + os.path.basename(path), "title": _title(path),
                         "web": not _uses_3d(path)})

    with open(os.path.join(ROOT, "studio", "version.py"), "r", encoding="utf-8") as handle:
        version = re.search(r'VERSION\s*=\s*"([^"]+)"', handle.read()).group(1)

    themes, accents, game = _looks()
    manifest = {
        "version": version,
        "python": PYTHON_FILES + ["runtimes/gublan_runtime.js"] + ["modules/" + name for name in modules],
        "examples": examples,
        "themes": themes,
        "accents": accents,
        "game": game,
    }
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2)
    # github pages would otherwise run jekyll, which hides files and folders that start with an underscore
    open(os.path.join(out, ".nojekyll"), "w").close()
    return out, manifest


if __name__ == "__main__":
    folder, info = build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "_site"))
    print(f"built the gublan {info['version']} playground in {folder} ({len(info['examples'])} examples)")
