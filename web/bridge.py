"""the python half of the web playground. it runs inside pyodide, in the browser.

the playground only needs gublan's checker and its javascript translator. gublancore imports pygame and
pyopengl for the desktop window, which a browser can't load, so those are replaced with empty stand-ins
before gublancore is imported. nothing here draws: the translated program runs with gublan_runtime.js.
"""
import json
import sys
import types


class _Placeholder(types.ModuleType):
    """a module whose every name is a harmless placeholder (only used by the desktop window code)."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return 0


for _name in ("pygame", "pygame.locals", "OpenGL", "OpenGL.GL", "OpenGL.GLU"):
    sys.modules.setdefault(_name, _Placeholder(_name))

for _name in ("ssl",):  # some pyodide versions ship ssl as a separate download; gublan only needs the name
    try:
        __import__(_name)
    except ImportError:
        sys.modules[_name] = _Placeholder(_name)

import gublancore  # noqa: E402
import gublantranslate  # noqa: E402


def check(source):
    """problems in a program, as json: [{line, severity, message}]."""
    return json.dumps(gublancore.analyze_source(source, warnings=True))


def translate(source, name="program"):
    """turn a program into javascript, as json: {ok, code, notes, todos} or {ok: false, error}."""
    try:
        result = gublantranslate.translate(source, "javascript", name=name, base_dir="/gublan/project")
    except gublantranslate.TranslateError as err:
        return json.dumps({"ok": False, "error": str(err)})
    except Exception as err:  # the playground should report anything, never hang
        return json.dumps({"ok": False, "error": f"{type(err).__name__}: {err}"})
    return json.dumps({"ok": True, "code": result.text, "notes": list(result.notes), "todos": result.todos})


PROJECT = "/gublan/project"


def _split_usage(text):
    """'abs(x) the distance of x from zero' -> ('abs(x)', 'the distance of x from zero')."""
    usage, _, summary = str(text).partition(") ")
    if not summary:
        return str(text), ""
    return usage + ")", summary


def reference():
    """every command, function and colour name, as json, for the playground's reference panel and suggestions."""
    commands = [{"name": name, "category": spec[0], "usage": spec[1], "summary": spec[3], "example": spec[4]}
                for name, spec in sorted(gublancore.COMMAND_SPECS.items())]
    functions = []
    for name, text in sorted(gublancore.EXPRESSION_FUNCTIONS.items()):
        usage, summary = _split_usage(text)
        functions.append({"name": name, "usage": usage, "summary": summary})
    colors = {name: list(value[:3]) for name, value in sorted(gublancore.COLORS.items())}
    words = {"openers": sorted(gublancore.BLOCK_OPENERS), "middles": sorted(gublancore.BLOCK_MIDDLES),
             "keywords": sorted(getattr(gublancore, "EXPRESSION_KEYWORDS", ()))}
    return json.dumps({"commands": commands, "functions": functions, "colors": colors, "words": words})


def set_files(files_json, folder=PROJECT):
    """write the playground's other project files where include can find them. files_json is {name: text}."""
    import os
    files = json.loads(files_json)
    os.makedirs(folder, exist_ok=True)
    for old in os.listdir(folder):
        if old.endswith(".gubl") and old not in files:
            os.remove(os.path.join(folder, old))
    for name, text in files.items():
        name = os.path.basename(str(name))
        if not name.endswith(".gubl") or name.startswith("."):
            continue
        with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
            handle.write(str(text))
    return len(files)
