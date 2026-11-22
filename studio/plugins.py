"""studio plugins: python files in the plugins folder that add commands, functions and menu items.

a plugin is a .py file (or a folder with an __init__.py) in the plugins folder. it can have a PLUGIN dict that
names it, and a setup(api) function that adds things:

    PLUGIN = {"name": "hello", "about": "adds a shout command", "version": "1.0"}

    def setup(api):
        api.command("shout", lambda context: context.print(context.text.upper() + "!"),
                    usage="shout <text>", summary="prints the text loudly.", example="shout hello")
        api.function("twice", lambda value: value * 2, "twice(x) x times two")
        api.menu("say hello", lambda: api.log("hello from a plugin"))

plugins are python code that runs with your permissions, so they only load when "load plugins" is on in
settings, and only the ones you have not switched off.
"""

import importlib.util
import os
import sys
import traceback

from . import config

API_VERSION = 1
EXAMPLE_NAME = "hello.py"
EXAMPLE = '''"""an example gublan studio plugin. switch plugins on in settings, then restart gublan studio."""

PLUGIN = {"name": "hello", "about": "adds a shout command, a twice() function and a menu item", "version": "1.0"}


def setup(api):
    def shout(context):
        # context.text is the rest of the line with {braces} filled in
        context.print(context.text.upper() + "!")

    api.command("shout", shout, usage="shout <text>", summary="prints the text loudly.", example="shout hello")
    api.function("twice", lambda value: value * 2, "twice(x) x times two")
    api.menu("say hello", lambda: api.log("hello from the hello plugin"))
'''


def plugins_folder():
    return os.path.join(config.settings_folder(), "plugins")


def write_example():
    """make the plugins folder with an example plugin in it, and give back the folder."""
    folder = plugins_folder()
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, EXAMPLE_NAME)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(EXAMPLE)
    return folder


class PluginInfo:
    def __init__(self, key, path):
        self.key = key  # the file name without .py: what settings use to switch it off
        self.path = path
        self.name = key
        self.about = ""
        self.version = ""
        self.status = "off"  # off, loaded or error
        self.error = ""
        self.commands = []
        self.functions = []
        self.menu_items = []  # (label, action)

    def describe(self):
        parts = [self.name]
        if self.version:
            parts.append(self.version)
        added = self.commands + [name + "()" for name in self.functions]
        text = " ".join(parts)
        if self.status == "error":
            return f"{text}: did not load ({self.error})"
        if self.status == "off":
            return f"{text}: switched off"
        return f"{text}: adds {', '.join(added)}" if added else f"{text}: loaded"


class PluginAPI:
    """what setup(api) gets."""

    version = API_VERSION

    def __init__(self, info, app=None):
        self._info = info
        self._app = app

    @property
    def studio_version(self):
        from .version import VERSION
        return VERSION

    @property
    def folder(self):
        """the plugin's own folder (for files it ships with)."""
        return os.path.dirname(self._info.path)

    def command(self, name, run, usage=None, summary="", example=None, min_parts=1, category="plugins"):
        """add a gublan command. run(context) gets a CommandContext: context.words, context.values, context.text,
        context.get(name), context.set(name, value) and context.print(...)."""
        import gublancore
        gublancore.register_command(name, run, usage=usage, summary=summary, example=example, category=category,
                                    min_parts=min_parts)
        self._info.commands.append(name)

    def function(self, name, function, description=""):
        """add a function for expressions: name(a, b) calls function(a, b)."""
        import gublancore
        gublancore.register_function(name, function, description)
        self._info.functions.append(name)

    def menu(self, label, action):
        """add an item to tools > plugins. action() runs when it is picked."""
        if not callable(action):
            raise ValueError("a menu action must be a function")
        self._info.menu_items.append((str(label).lower(), action))

    def log(self, text):
        """write a line in the output panel."""
        if self._app is not None and hasattr(self._app, "output"):
            self._app.output.write(f"[{self._info.name}] {text}", "moss")
        else:
            print(f"[{self._info.name}] {text}", file=sys.stderr)

    def message(self, text):
        """show a short message at the bottom of the window."""
        if self._app is not None and hasattr(self._app, "flash"):
            self._app.flash(str(text))
        else:
            self.log(text)

    def code(self):
        """the text of the program you are looking at ("" when nothing is open)."""
        doc = getattr(self._app, "current", None)
        return doc.editor.get() if doc is not None else ""

    def insert(self, text):
        """type text into the program at the cursor."""
        if self._app is not None and hasattr(self._app, "insert_code"):
            self._app.insert_code(text)

    def file(self):
        """the path of the program you are looking at, or None."""
        doc = getattr(self._app, "current", None)
        return getattr(doc, "path", None)


def find_plugins():
    """[PluginInfo] for each plugin file in the plugins folder, sorted by name."""
    found = []
    folder = plugins_folder()
    try:
        entries = sorted(os.listdir(folder))
    except OSError:
        return found
    for entry in entries:
        path = os.path.join(folder, entry)
        if entry.startswith(("_", ".")):
            continue
        if entry.lower().endswith(".py") and os.path.isfile(path):
            found.append(PluginInfo(entry[:-3].lower(), path))
        elif os.path.isfile(os.path.join(path, "__init__.py")):
            found.append(PluginInfo(entry.lower(), os.path.join(path, "__init__.py")))
    return found


def _load_one(info, app):
    module_name = "gublan_plugin_" + "".join(ch if ch.isalnum() else "_" for ch in info.key)
    spec = importlib.util.spec_from_file_location(module_name, info.path)
    if spec is None or spec.loader is None:
        raise ImportError("not a python file")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    details = getattr(module, "PLUGIN", None)
    if isinstance(details, dict):
        info.name = str(details.get("name") or info.key).lower()
        info.about = str(details.get("about") or "").lower()
        info.version = str(details.get("version") or "")
    setup = getattr(module, "setup", None)
    if callable(setup):
        setup(PluginAPI(info, app))
    return module


def load_plugins(settings=None, app=None):
    """load every plugin that is switched on. a broken plugin is reported, never fatal.
    gives back [PluginInfo] for all plugins found (loaded, off or broken)."""
    settings = settings if settings is not None else config.load()
    plugins = find_plugins()
    if not settings.get("plugins"):
        return plugins
    disabled = {str(name).lower() for name in settings.get("disabled_plugins", [])}
    for info in plugins:
        if info.key in disabled:
            continue
        try:
            _load_one(info, app)
            info.status = "loaded"
        except Exception as err:  # noqa: BLE001 - a plugin can fail in any way; studio must keep going
            info.status = "error"
            last = traceback.extract_tb(err.__traceback__)
            where = f" (line {last[-1].lineno})" if last and last[-1].filename == info.path else ""
            info.error = f"{type(err).__name__}: {err}{where}".lower()
    return plugins
