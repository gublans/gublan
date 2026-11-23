"""turn a gublan script into a stand-alone windows program.

what the old exporter got wrong, and what this one does instead:
  - pyinstaller's --add-data takes "source;folder". the old code passed the file's own name as
    the folder, so assets/pixel.png ended up at assets/pixel.png/pixel.png and the game could
    not find it. assets now go to their folder, with the platform separator (os.pathsep).
  - media outside the script folder used to stop the export. it is now copied into
    assets/external/ in the bundle and the script is rewritten to point at the copy.
  - paths were only found after image, sprite, sound and music. any word or "quoted text" that
    names a media file is found now, including inside {expressions}, and the whole assets/
    folder can be bundled for paths built while the game runs.
  - the generated program called GublanRuntime().run(source, folder) and, with no console,
    errors vanished. it now calls run_standalone, which keeps the window open at the end and
    shows errors in a message box (or the console for text programs).
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

from gublancore import analyze_source, split_command

MEDIA_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tga", ".wav", ".ogg", ".mp3", ".flac", ".opus",
    ".mod", ".xm", ".ttf", ".otf", ".txt", ".json", ".csv",
}
MEDIA_ARGUMENT = {"image": 2, "sprite": 2, "sound": 1, "music": 1}
WINDOW_COMMANDS = {
    "mode", "window", "box", "circle", "image", "sprite", "text", "button", "ui", "cube", "sphere", "line",
    "frame", "background", "camera",
}
_QUOTED_IN_BRACES = re.compile(r"\"([^\"]+)\"|'([^']+)'")
MAX_FOLDER_FILES = 4000


class ExportError(ValueError):
    pass


@dataclass
class Asset:
    bundle_path: str
    source_path: str
    line: int = 0
    external: bool = False


@dataclass
class ExportPlan:
    source: str
    assets: dict = field(default_factory=dict)
    missing: list = field(default_factory=list)
    console: bool = False
    notes: list = field(default_factory=list)

    @property
    def external(self):
        return [asset for asset in self.assets.values() if asset.external]


def _is_media(text):
    return os.path.splitext(text.strip().lower())[1] in MEDIA_EXTENSIONS


def _inside(folder, path):
    try:
        return os.path.commonpath((os.path.realpath(folder), os.path.realpath(path))) == os.path.realpath(folder)
    except ValueError:
        return False


def uses_window(source):
    for raw in source.splitlines():
        text = raw.strip()
        if not text or text.startswith("//"):
            continue
        first = text.split(None, 1)[0]
        if first in WINDOW_COMMANDS:
            return True
    return False


def _candidates(line_text):
    """yield (text as written, path) pairs for every word on a line that could be a media file."""
    tokens = split_command(line_text)
    if not tokens:
        return
    command = tokens[0]
    position = MEDIA_ARGUMENT.get(command)
    seen = set()
    if position is not None and len(tokens) > position:
        if command in ("sound", "music"):
            path = " ".join(str(token) for token in tokens[1:])
        else:
            path = str(tokens[position])
        if not path.startswith("{"):
            seen.add(path)
            yield path, True
    for token in tokens[1:]:
        text = str(token)
        if text.startswith("{") and text.endswith("}"):
            for match in _QUOTED_IN_BRACES.finditer(text):
                inner = match.group(1) or match.group(2)
                if _is_media(inner) and inner not in seen:
                    seen.add(inner)
                    yield inner, False
        elif _is_media(text) and text not in seen:
            seen.add(text)
            yield text, position is not None


def plan_export(source, base_dir, include_folder=True, folder_name="assets"):
    """find every media file a script uses and work out where it goes in the bundle."""
    base_dir = os.path.abspath(base_dir)
    plan = ExportPlan(source=source)
    lines = source.split("\n")
    for index, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped or stripped.startswith("//"):
            continue
        new_line = raw
        for written, required in _candidates(stripped):
            path = written.strip()
            full = os.path.normpath(path if os.path.isabs(path) else os.path.join(base_dir, path))
            if not os.path.isfile(full):
                if required or os.path.isabs(path):
                    plan.missing.append((index + 1, path))
                continue
            if _inside(base_dir, full):
                bundle = os.path.relpath(full, base_dir).replace(os.sep, "/")
                plan.assets.setdefault(bundle, Asset(bundle, full, index + 1))
                if bundle != path.replace("\\", "/") and os.path.isabs(path):
                    new_line = _replace_path(new_line, written, bundle)
                continue
            existing = next((asset for asset in plan.assets.values() if asset.source_path == full), None)
            if existing:
                bundle = existing.bundle_path
            else:
                name = os.path.basename(full)
                stem, extension = os.path.splitext(name)
                bundle = f"{folder_name}/external/{name}"
                number = 2
                while bundle in plan.assets:
                    bundle = f"{folder_name}/external/{stem}_{number}{extension}"
                    number += 1
                plan.assets[bundle] = Asset(bundle, full, index + 1, external=True)
            new_line = _replace_path(new_line, written, bundle)
        lines[index] = new_line
    plan.source = "\n".join(lines)
    if include_folder:
        folder = os.path.join(base_dir, folder_name)
        if os.path.isdir(folder):
            count = 0
            for directory, _dirs, files in os.walk(folder):
                for name in files:
                    if name.startswith(".") or name.lower().endswith((".gubl.bak", ".tmp")):
                        continue
                    full = os.path.join(directory, name)
                    bundle = os.path.relpath(full, base_dir).replace(os.sep, "/")
                    plan.assets.setdefault(bundle, Asset(bundle, full, 0))
                    count += 1
                    if count >= MAX_FOLDER_FILES:
                        plan.notes.append(f"only the first {MAX_FOLDER_FILES} files of {folder_name}/ were added")
                        break
                if count >= MAX_FOLDER_FILES:
                    break
    plan.console = not uses_window(plan.source)
    if plan.external:
        one = len(plan.external) == 1
        plan.notes.append(f"{len(plan.external)} {'file' if one else 'files'} from outside the script folder "
                          f"{'is' if one else 'are'} copied into the game")
    return plan


def _replace_path(line, written, bundle):
    quoted_forms = (f'"{written}"', f"'{written}'")
    for form in quoted_forms:
        if form in line:
            return line.replace(form, f'"{bundle}"', 1)
    replacement = f'"{bundle}"' if " " in bundle else bundle
    return line.replace(written, replacement, 1)


PROGRAM_TEMPLATE = '''import os
import sys

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from gublancore import run_standalone

SOURCE = {source!r}
TITLE = {title!r}
STYLE = {style!r}
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.argv[0])))

if __name__ == "__main__":
    sys.exit(run_standalone(SOURCE, BASE_DIR, title=TITLE, console={console!r}, style=STYLE))
'''


def program_text(source, title, console, style=None):
    """the python file pyinstaller builds. style is the studio's game window and popup look."""
    return PROGRAM_TEMPLATE.format(source=source, title=title, console=bool(console),
                                   style=dict(style) if isinstance(style, dict) and style else None)


def core_folder():
    """the folder that holds gublancore.py (and gublanpresence.py next to it), for pyinstaller's --paths."""
    if getattr(sys, "frozen", False):
        bundled = getattr(sys, "_MEIPASS", "")
        if os.path.isfile(os.path.join(bundled, "gublancore.py")):
            return bundled
    import gublancore
    return os.path.dirname(os.path.abspath(gublancore.__file__))


def find_python():
    if getattr(sys, "frozen", False):
        return shutil.which("python") or shutil.which("py")
    return sys.executable


def pyinstaller_status(python):
    """(version, None) when pyinstaller works, (None, None) when it isn't installed and (None, reason) when it is
    installed but fails to start, for example because one of its own packages is missing."""
    try:
        result = subprocess.run([python, "-m", "PyInstaller", "--version"], capture_output=True, text=True,
                                timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as err:
        return None, str(err)
    if result.returncode == 0:
        return (result.stdout or "").strip() or "unknown", None
    errors = [line.strip() for line in (result.stderr or "").splitlines() if line.strip()]
    last = errors[-1] if errors else ""
    if not last or "No module named PyInstaller" in last or "No module named 'PyInstaller'" in last:
        return None, None
    return None, last


def pyinstaller_available(python):
    return pyinstaller_status(python)[0]


def pyinstaller_command(python, name, script_path, build_dir, plan, console, onefile=True, icon_path=None):
    staged = os.path.join(build_dir, "dist")
    command = [
        python, "-m", "PyInstaller", "--noconfirm", "--onefile" if onefile else "--onedir",
        "--console" if console else "--noconsole",
        "--name", name, "--distpath", staged, "--workpath", os.path.join(build_dir, "work"),
        "--specpath", build_dir, "--paths", core_folder(), "--hidden-import", "gublancore",
        "--hidden-import", "gublanpresence", "--collect-all", "OpenGL",
    ]
    for module in ("tkinter", "numpy", "PIL", "matplotlib", "IPython", "pytest", "studio", "gublanconvert"):
        command.extend(["--exclude-module", module])
    if icon_path:
        command.extend(["--icon", icon_path])
    for bundle, asset in sorted(plan.assets.items()):
        folder = os.path.dirname(bundle) or "."
        command.extend(["--add-data", f"{asset.source_path}{os.pathsep}{folder}"])
    command.append(script_path)
    return command, staged


def safe_name(text):
    name = re.sub(r"[^\w\- ]+", "", text).strip() or "gublan game"
    return name[:60]


def build(source, output, python, base_dir, expand_includes, progress=None, include_folder=True,
          onefile=True, console=None, icon_path=None, title=None, style=None):
    """build the program. raises ExportError with a lowercase message when something is wrong."""
    report = progress or (lambda _status: None)
    report("checking the script and its media...")
    base_dir = os.path.abspath(base_dir or os.getcwd())
    try:
        expanded = expand_includes(source, base_dir)
    except ValueError as err:
        raise ExportError(f"include error: {err}") from err
    problems = [item for item in analyze_source(expanded) if item.get("severity", "error") == "error"]
    if problems:
        first = problems[0]
        raise ExportError(f"fix line {first['line']} first: {first['message']}")
    plan = plan_export(expanded, base_dir, include_folder=include_folder)
    if plan.missing:
        line, path = plan.missing[0]
        raise ExportError(f"line {line}: the media file '{path}' was not found")
    if console is None:
        console = plan.console
    name = safe_name(os.path.splitext(os.path.basename(output))[0])
    with tempfile.TemporaryDirectory(prefix="gublan-export-") as build_dir:
        script_path = os.path.join(build_dir, "gublan_program.py")
        with open(script_path, "w", encoding="utf-8") as handle:
            handle.write(program_text(plan.source, (title or name).lower(), console, style))
        command, staged = pyinstaller_command(python, name, script_path, build_dir, plan, console, onefile,
                                              icon_path)
        media = f"{len(plan.assets)} media {'file' if len(plan.assets) == 1 else 'files'}"
        report(f"building with pyinstaller ({media})...")
        try:
            subprocess.run(command, cwd=build_dir, capture_output=True, text=True, check=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except FileNotFoundError as err:
            raise ExportError("python was not found, so the program can't be built") from err
        except subprocess.CalledProcessError as err:
            details = (err.stderr or err.stdout or str(err))[-2500:]
            if "No module named PyInstaller" in details:
                raise ExportError("pyinstaller is not installed. install it with: py -m pip install pyinstaller") \
                    from err
            raise ExportError("pyinstaller failed:\n" + details.lower()) from err
        report("finishing...")
        if onefile:
            built = os.path.join(staged, name + ".exe")
            if not os.path.isfile(built) or os.path.getsize(built) == 0:
                raise ExportError("pyinstaller finished but did not make the program")
            os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
            if os.path.exists(output):
                os.remove(output)
            shutil.move(built, output)
            return output
        built_dir = os.path.join(staged, name)
        if not os.path.isdir(built_dir):
            raise ExportError("pyinstaller finished but did not make the program folder")
        target_dir = os.path.join(os.path.dirname(os.path.abspath(output)), name)
        if os.path.isdir(target_dir):
            shutil.rmtree(target_dir)
        shutil.move(built_dir, target_dir)
        return os.path.join(target_dir, name + ".exe")
