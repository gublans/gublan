"""build the online playground into a folder (default: _site) ready for github pages.

    python web/build_site.py            # writes _site/
    python web/build_site.py out        # writes out/
    python -m http.server -d _site      # then open http://localhost:8000 to try it

the page itself lives in web/. this copies it together with the real gublan files it needs (the checker,
the javascript translator, the javascript runtime, the modules and the examples), so the website always
runs the same language as the studio. nothing in this folder is used by the windows app or the installer.
"""
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

    manifest = {
        "version": version,
        "python": PYTHON_FILES + ["runtimes/gublan_runtime.js"] + ["modules/" + name for name in modules],
        "examples": examples,
    }
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2)
    # github pages would otherwise run jekyll, which hides files and folders that start with an underscore
    open(os.path.join(out, ".nojekyll"), "w").close()
    return out, manifest


if __name__ == "__main__":
    folder, info = build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "_site"))
    print(f"built the gublan {info['version']} playground in {folder} ({len(info['examples'])} examples)")
