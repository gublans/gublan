"""gublan's mcp server: lets ai helpers (claude, copilot, cursor and others) work on a gublan project.

    py gublancli.py mcp [project folder]
    GublanStudio.exe --mcp [project folder]

it speaks the model context protocol over stdin and stdout (one json-rpc message per line). its tools can list,
read, write and edit files in the project folder (and nowhere else), check code for problems, run programs (with
keys held, clicks and typing), run test blocks, take screenshots of the game window, look up commands and functions,
and turn code into gublan or gublan into python, javascript or lua.
"""

import base64
import inspect
import io
import json
import os
import re
import sys
import time
import traceback

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

SERVER_NAME = "gublan"
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_PROTOCOL = "2025-06-18"
SKIPPED_FOLDERS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".idea", ".vscode", "build", "dist"}
TEXT_EXTENSIONS = {".gubl", ".txt", ".md", ".json", ".csv", ".py", ".js", ".lua", ".html", ".css", ".toml", ".ini",
                   ".cfg", ".xml", ".svg", ".yml", ".yaml", ".log"}
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
               ".webp": "image/webp", ".bmp": "image/bmp"}
MAX_OUTPUT_CHARS = 20000
MAX_READ_BYTES = 2_000_000

INSTRUCTIONS = """gublan is a small programming language for beginners and games. one command per line, blocks close
with `end`, expressions go in {braces} inside text (print score is {score}). use command_help to look up a command
or function before guessing (command_help with no topic lists them all). after changing a .gubl file, call
check_code, then run_tests if the program has test blocks, run_program to see what it prints, and screenshot to see
the window. all paths are relative to the project folder."""


def _version():
    try:
        from studio.version import VERSION
        return VERSION
    except Exception:  # noqa: BLE001 - the server works without the studio package
        return "1.0.5"


class ToolError(Exception):
    """a problem the ai helper can fix (a bad path, a missing argument). shown as the tool's answer."""


def _clip(text, limit=MAX_OUTPUT_CHARS):
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... ({len(text) - limit} more characters cut)"


def _function_parts(text):
    """'clamp(x, low, high) keep x between low and high' -> ('clamp(x, low, high)', 'keep x between ...')"""
    match = re.match(r"^\s*(\w+\([^)]*\))\s*(.*)$", text, re.DOTALL)
    if match:
        return match.group(1), match.group(2)
    signature, _space, about = text.partition(" ")
    return signature, about


def _plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


# ----- the project folder ----------------------------------------------------------------------------------------
class Project:
    def __init__(self, folder):
        self.root = os.path.realpath(os.path.abspath(folder))

    def path(self, relative, must_exist=False, folder=False):
        if not isinstance(relative, str) or not relative.strip():
            raise ToolError("give a path inside the project folder, like game.gubl")
        full = os.path.realpath(os.path.join(self.root, relative.strip()))
        try:
            inside = os.path.commonpath([full, self.root]) == self.root
        except ValueError:  # another drive on windows
            inside = False
        if not inside:
            raise ToolError(f"'{relative}' is outside the project folder ({self.root}). only files inside it can be "
                            "used")
        if must_exist and folder and not os.path.isdir(full):
            raise ToolError(f"there is no folder called '{relative}' in the project")
        if must_exist and not folder and not os.path.isfile(full):
            hint = ""
            matches = self.find(os.path.basename(relative))
            if matches:
                hint = f". did you mean {', '.join(matches[:3])}?"
            raise ToolError(f"there is no file called '{relative}' in the project{hint}")
        return full

    def relative(self, full):
        return os.path.relpath(full, self.root).replace(os.sep, "/")

    def walk(self, start=None, limit=600):
        found = []
        for folder, folders, files in os.walk(start or self.root):
            folders[:] = sorted(name for name in folders if name not in SKIPPED_FOLDERS and not name.startswith("."))
            for name in sorted(files):
                found.append(os.path.join(folder, name))
                if len(found) >= limit:
                    return found
        return found

    def find(self, name):
        name = name.lower()
        return [self.relative(path) for path in self.walk() if os.path.basename(path).lower() == name]


# ----- running programs -------------------------------------------------------------------------------------------
_RUNTIME_CLASS = None


def _runtime_class():
    """a GublanRuntime that can hand each finished frame to the server (for screenshots)."""
    global _RUNTIME_CLASS
    if _RUNTIME_CLASS is None:
        import pygame
        from gublancore import GublanRuntime

        class WatchedRuntime(GublanRuntime):
            onframe = None

            def render(self):
                if not self.screen or self.mode not in ("2d", "3d"):
                    return
                if self.mode == "2d":
                    self._render_2d()
                else:
                    self._render_3d()
                if self.onframe:
                    self.onframe(self)
                pygame.display.flip()

        _RUNTIME_CLASS = WatchedRuntime
    return _RUNTIME_CLASS


def _grab(runtime):
    """the picture in the game window right now, as a pygame surface."""
    import pygame
    if runtime.mode == "2d":
        return runtime.screen.copy()
    from OpenGL.GL import GL_PACK_ALIGNMENT, GL_RGB, GL_UNSIGNED_BYTE, glPixelStorei, glReadPixels
    width, height = runtime.screen.get_size()
    glPixelStorei(GL_PACK_ALIGNMENT, 1)
    data = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE)
    make = getattr(pygame.image, "frombytes", None) or pygame.image.fromstring
    return make(bytes(data), (width, height), "RGB", True)


def _png(surface):
    import pygame
    buffer = io.BytesIO()
    pygame.image.save(surface, buffer, "shot.png")
    return buffer.getvalue()


def _clean_actions(actions):
    cleaned = []
    for number, action in enumerate(actions or [], start=1):
        if not isinstance(action, dict):
            raise ToolError(f"action {number} should be an object like {{\"at\": 0.5, \"key\": \"space\"}}")
        at = action.get("at", 0)
        if not isinstance(at, (int, float)) or at < 0:
            raise ToolError(f"action {number}: 'at' is the number of seconds after the start (0 or more)")
        kinds = [kind for kind in ("key", "click", "move", "type") if kind in action]
        if len(kinds) != 1:
            raise ToolError(f"action {number} needs exactly one of key, click, move or type")
        if kinds[0] in ("click", "move"):
            point = action[kinds[0]]
            if (not isinstance(point, (list, tuple)) or len(point) != 2
                    or not all(isinstance(value, (int, float)) for value in point)):
                raise ToolError(f"action {number}: {kinds[0]} takes a position like [120, 80]")
        hold = action.get("hold", 0.1)
        if not isinstance(hold, (int, float)) or hold < 0:
            raise ToolError(f"action {number}: 'hold' is how many seconds the key or button stays down")
        cleaned.append(dict(action, at=float(at), hold=float(hold)))
    return sorted(cleaned, key=lambda item: item["at"])


class _Session:
    """one run of a program: fake keys and mouse, the time limit, the output and the last picture."""

    def __init__(self, seconds, inputs, hold, actions, screenshot, show_window):
        import pygame
        self.pygame = pygame
        self.seconds = seconds
        self.answers = [str(value) for value in inputs or []]
        self.hold_names = [str(name) for name in hold or []]
        self.actions = _clean_actions(actions)
        self.screenshot = screenshot
        self.show_window = show_window
        self.output = []
        self.shot = None
        self.shot_at = None
        self.stopped_for_shot = False
        self.last_grab = 0.0
        self.latest = None
        self.frames = 0
        self.timed_out = False
        self.held_keys = {}  # keycode -> time it is let go
        self.releases = []  # (time, event) for keys and mouse buttons let go later
        self.mouse = None
        self.mouse_down_until = 0.0
        self.runtime = None
        self.started = time.perf_counter()
        self._saved = []

    # the runtime's callbacks
    def log(self, *parts):
        self.output.append(" ".join(str(part) for part in parts))

    def ask(self, prompt):
        answer = self.answers.pop(0) if self.answers else ""
        self.output.append(f"(asked: {prompt}) -> {answer!r}")
        return answer

    def popup(self, text):
        self.output.append(f"(popup) {text}")

    def elapsed(self):
        return time.perf_counter() - self.started

    def should_stop(self):
        now = self.elapsed()
        if self.runtime is not None and self.runtime.screen is not None:
            while self.actions and self.actions[0]["at"] <= now:
                self._fire(self.actions.pop(0), now)
            if self.releases:
                due = [event for at, event in self.releases if at <= now]
                self.releases = [(at, event) for at, event in self.releases if at > now]
                for event in due:
                    self.pygame.event.post(event)
        if self.screenshot and self.shot is not None:
            self.stopped_for_shot = True
            return True
        limit = self.seconds + (1.0 if self.screenshot else 0.0)
        if now >= limit:
            self.timed_out = True
            return True
        return False

    def on_frame(self, runtime):
        self.frames += 1
        now = self.elapsed()
        if self.screenshot and self.shot is None and now >= self.seconds:
            self.shot, self.shot_at = _grab(runtime), now
        elif now - self.last_grab >= 0.1:
            self.last_grab = now
            self.latest = (_grab(runtime), now)

    # fake input
    def _fire(self, action, now):
        pygame, runtime = self.pygame, self.runtime
        try:
            if "key" in action:
                code = runtime._keycode(action["key"])
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=code, mod=0, unicode="", scancode=0))
                self.held_keys[code] = now + action["hold"]
                self.releases.append((now + action["hold"],
                                      pygame.event.Event(pygame.KEYUP, key=code, mod=0, unicode="", scancode=0)))
            elif "type" in action:
                pygame.event.post(pygame.event.Event(pygame.TEXTINPUT, text=str(action["type"])))
            elif "move" in action:
                self.mouse = tuple(int(value) for value in action["move"])
                pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=self.mouse, rel=(0, 0), buttons=(0, 0, 0)))
            elif "click" in action:
                self.mouse = tuple(int(value) for value in action["click"])
                self.mouse_down_until = now + action["hold"]
                pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=self.mouse, button=1))
                self.releases.append((self.mouse_down_until,
                                      pygame.event.Event(pygame.MOUSEBUTTONUP, pos=self.mouse, button=1)))
        except (ValueError, pygame.error) as err:
            self.output.append(f"(could not do the action {json.dumps(action)}: {err})")

    def __enter__(self):
        pygame, session = self.pygame, self
        real_set_mode = pygame.display.set_mode
        real_key_pressed = pygame.key.get_pressed
        real_mouse_pressed = pygame.mouse.get_pressed
        real_mouse_pos = pygame.mouse.get_pos

        def set_mode(size=(0, 0), flags=0, *args, **kwargs):
            if not session.show_window:
                flags |= getattr(pygame, "HIDDEN", 0)
            surface = real_set_mode(size, flags, *args, **kwargs)
            for name in session.hold_names:
                try:
                    session.held_keys[session.runtime._keycode(name)] = float("inf")
                except (ValueError, pygame.error) as err:
                    session.output.append(f"(could not hold the key '{name}': {err})")
            return surface

        class Pressed:
            def __init__(self, real):
                self.real = real

            def __getitem__(self, code):
                until = session.held_keys.get(code)
                if until is not None and session.elapsed() < until:
                    return True
                return self.real[code]

            def __len__(self):
                return len(self.real)

        def key_pressed():
            return Pressed(real_key_pressed())

        def mouse_pressed(num_buttons=3, *args, **kwargs):
            real = list(real_mouse_pressed(num_buttons, *args, **kwargs))
            if session.elapsed() < session.mouse_down_until:
                real[0] = True
            return tuple(real)

        def mouse_pos():
            return session.mouse if session.mouse is not None else real_mouse_pos()

        for owner, name, value in ((pygame.display, "set_mode", set_mode), (pygame.key, "get_pressed", key_pressed),
                                   (pygame.mouse, "get_pressed", mouse_pressed), (pygame.mouse, "get_pos", mouse_pos)):
            self._saved.append((owner, name, getattr(owner, name)))
            setattr(owner, name, value)
        return self

    def __exit__(self, *_):
        for owner, name, value in reversed(self._saved):
            setattr(owner, name, value)
        self._saved.clear()


def run_gublan(source, base_dir, name="program", seconds=3.0, inputs=(), hold=(), actions=(), screenshot=False,
               show_window=False):
    """run gublan source with a time limit. gives back (session, runtime)."""
    session = _Session(seconds, inputs, hold, actions, screenshot, show_window)
    runtime_class = _runtime_class()
    runtime = runtime_class(onlog=session.log, base_dir=base_dir, oninput=session.ask, onpopup=session.popup,
                            onpresence=lambda *_: None, shouldstop=session.should_stop, hold_window=screenshot,
                            save_name=f"{name}_mcp")
    runtime.onframe = session.on_frame
    session.runtime = runtime
    with session:
        session.started = time.perf_counter()
        runtime.run(source, base_dir)
    if screenshot and session.shot is None and session.latest is not None:
        session.shot, session.shot_at = session.latest
    return session, runtime


# ----- the server ---------------------------------------------------------------------------------------------------
def _schema(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


_SOURCE = {
    "path": {"type": "string", "description": "a .gubl file in the project, like game.gubl"},
    "code": {"type": "string", "description": "gublan code to use instead of a file (includes are found in the "
                                              "project folder)"},
}
_RUN_OPTIONS = {
    "seconds": {"type": "number", "description": "how long to let it run before stopping it (default 3, at most 60)"},
    "inputs": {"type": "array", "items": {"type": "string"},
               "description": "answers given to ask, one after another"},
    "hold": {"type": "array", "items": {"type": "string"},
             "description": "keys held down for the whole run, like [\"right\", \"space\"]"},
    "actions": {"type": "array", "items": {"type": "object"},
                "description": "things to do while it runs, each with 'at' (seconds after the start) and one of: "
                               "key (a key name, tapped; 'hold' seconds keeps it down), click ([x, y] in the "
                               "window), move ([x, y]), type (text typed into the focused textbox). "
                               "example: [{\"at\": 0.5, \"click\": [100, 60]}, {\"at\": 0.8, \"type\": \"sam\"}, "
                               "{\"at\": 1, \"key\": \"return\"}]"},
    "show_window": {"type": "boolean", "description": "show the window on the screen while it runs (default false)"},
}

TOOLS = [
    {"name": "project_info", "title": "about this project",
     "description": "the project folder, its gublan programs and the gublan version. a good first call.",
     "inputSchema": _schema({}), "annotations": {"readOnlyHint": True}},
    {"name": "list_files", "title": "list files",
     "description": "list the files in the project folder (or a folder inside it) with their sizes.",
     "inputSchema": _schema({"folder": {"type": "string", "description": "a folder inside the project (default: "
                                                                         "the whole project)"}}),
     "annotations": {"readOnlyHint": True}},
    {"name": "read_file", "title": "read a file",
     "description": "read a file in the project. pictures come back as images. line_numbers adds a number to each "
                    "line (leave them out when copying text into edit_file).",
     "inputSchema": _schema({"path": {"type": "string"},
                             "start_line": {"type": "integer", "description": "first line to read (from 1)"},
                             "end_line": {"type": "integer", "description": "last line to read"},
                             "line_numbers": {"type": "boolean"}}, ["path"]),
     "annotations": {"readOnlyHint": True}},
    {"name": "write_file", "title": "write a file",
     "description": "create or replace a file in the project with new text. folders are made when needed. for "
                    ".gubl files the answer lists any problems in the new code.",
     "inputSchema": _schema({"path": {"type": "string"}, "text": {"type": "string"}}, ["path", "text"]),
     "annotations": {"destructiveHint": True, "idempotentHint": True}},
    {"name": "edit_file", "title": "edit a file",
     "description": "replace exact text in a file. old_text must be found once (or set replace_all). for .gubl "
                    "files the answer lists any problems after the change.",
     "inputSchema": _schema({"path": {"type": "string"}, "old_text": {"type": "string"},
                             "new_text": {"type": "string"}, "replace_all": {"type": "boolean"}},
                            ["path", "old_text", "new_text"]),
     "annotations": {"destructiveHint": True}},
    {"name": "check_code", "title": "check for problems",
     "description": "find errors and warnings in gublan code without running it.",
     "inputSchema": _schema(_SOURCE), "annotations": {"readOnlyHint": True}},
    {"name": "run_program", "title": "run a program",
     "description": "run a gublan program for a few seconds and give back what it printed, the error it hit (if "
                    "any) and the variables at the end. windows are hidden unless show_window is true. keys, "
                    "clicks and typing can be faked with hold and actions.",
     "inputSchema": _schema({**_SOURCE, **_RUN_OPTIONS}), "annotations": {"readOnlyHint": True}},
    {"name": "run_tests", "title": "run tests",
     "description": "run the program's test blocks (or one of them) and say which passed.",
     "inputSchema": _schema({**_SOURCE, "name": {"type": "string", "description": "only run the test with this "
                                                                                 "name"}}),
     "annotations": {"readOnlyHint": True}},
    {"name": "screenshot", "title": "screenshot the game",
     "description": "run a program that opens a window, wait some seconds (default 1), and give back a picture of "
                    "the window. hold and actions can press keys and click first.",
     "inputSchema": _schema({**_SOURCE, **_RUN_OPTIONS,
                             "save_as": {"type": "string", "description": "also save the picture in the project, "
                                                                         "like shots/title.png"}}),
     "annotations": {"readOnlyHint": False}},
    {"name": "command_help", "title": "look up commands",
     "description": "how a gublan command or function works, with an example. give a word to search for, or "
                    "nothing to list every command and function.",
     "inputSchema": _schema({"topic": {"type": "string", "description": "a command (textbox), function (clamp) "
                                                                         "or word to search for (collision)"}}),
     "annotations": {"readOnlyHint": True}},
    {"name": "convert_code", "title": "turn code into gublan",
     "description": "turn python, javascript or lua into gublan. lines that could not be turned are marked todo.",
     "inputSchema": _schema({"code": {"type": "string"},
                             "path": {"type": "string", "description": "a .py, .js or .lua file in the project"},
                             "language": {"type": "string", "enum": ["python", "javascript", "lua"]},
                             "save_as": {"type": "string", "description": "save the gublan in the project, like "
                                                                         "game.gubl"}}),
     "annotations": {"readOnlyHint": False}},
    {"name": "translate_code", "title": "turn gublan into another language",
     "description": "turn a gublan program into python (pygame), javascript (web page) or lua (love2d), with the "
                    "small runtime file it needs. with folder, the files are saved in the project.",
     "inputSchema": _schema({**_SOURCE, "language": {"type": "string", "enum": ["python", "javascript", "lua"]},
                             "folder": {"type": "string", "description": "a folder in the project to save into"}},
                            ["language"]),
     "annotations": {"readOnlyHint": False}},
]


class Server:
    def __init__(self, folder):
        self.project = Project(folder)
        self.protocol = DEFAULT_PROTOCOL
        self.handlers = {tool["name"]: getattr(self, "tool_" + tool["name"]) for tool in TOOLS}

    # json-rpc
    def handle(self, message):
        """answer one message. gives back the reply, or None for notifications."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "not a json-rpc 2.0 message"}}
        method = message.get("method")
        if "id" not in message:
            return None  # notifications (initialized, cancelled) need no answer
        ident = message["id"]
        params = message.get("params") or {}
        try:
            if method == "initialize":
                result = self.initialize(params)
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                result = self.call_tool(params.get("name"), params.get("arguments") or {})
            elif method == "resources/list":
                result = {"resources": self.resources()}
            elif method == "resources/templates/list":
                result = {"resourceTemplates": []}
            elif method == "resources/read":
                result = {"contents": [self.read_resource(params.get("uri", ""))]}
            elif method == "prompts/list":
                result = {"prompts": []}
            else:
                return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": f"no method {method}"}}
        except ToolError as err:
            return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32602, "message": str(err)}}
        except Exception as err:  # noqa: BLE001 - one bad request must not stop the server
            traceback.print_exc(file=sys.stderr)
            return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32603, "message": f"{type(err).__name__}: {err}"}}
        return {"jsonrpc": "2.0", "id": ident, "result": result}

    def initialize(self, params):
        wanted = params.get("protocolVersion")
        self.protocol = wanted if wanted in PROTOCOL_VERSIONS else DEFAULT_PROTOCOL
        return {"protocolVersion": self.protocol,
                "capabilities": {"tools": {"listChanged": False}, "resources": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "title": "gublan studio", "version": _version()},
                "instructions": INSTRUCTIONS + f"\nthe project folder is {self.project.root}"}

    def call_tool(self, name, arguments):
        handler = self.handlers.get(name)
        if handler is None:
            raise ToolError(f"there is no tool called {name}")
        if not isinstance(arguments, dict):
            raise ToolError("the arguments should be an object")
        try:
            inspect.signature(handler).bind(**arguments)
        except TypeError as err:
            return {"content": [{"type": "text", "text": f"wrong arguments for {name}: {err}"}], "isError": True}
        try:
            content = handler(**arguments)
        except ToolError as err:
            return {"content": [{"type": "text", "text": str(err)}], "isError": True}
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        return {"content": content, "isError": False}

    # helpers
    def _source(self, path=None, code=None):
        """(source, base folder, program name, relative path or None)"""
        if code is not None and path:
            raise ToolError("give either path or code, not both")
        if code is not None:
            return code, self.project.root, "snippet", None
        if not path:
            raise ToolError("give the path of a .gubl file, or some gublan code")
        full = self.project.path(path, must_exist=True)
        with open(full, "r", encoding="utf-8-sig") as handle:
            source = handle.read()
        return source, os.path.dirname(full), os.path.splitext(os.path.basename(full))[0], self.project.relative(full)

    @staticmethod
    def _problems_text(source, limit=40):
        from gublancore import analyze_source
        problems = analyze_source(source, warnings=True)
        if not problems:
            return "no problems found.", 0
        errors = sum(1 for item in problems if item.get("severity", "error") == "error")
        lines = [f"{_plural(errors, 'error')}, {_plural(len(problems) - errors, 'warning')}:"]
        for item in problems[:limit]:
            where = f"line {item['line']}" if item.get("line") else "file"
            lines.append(f"  {where}: {item.get('severity', 'error')}: {item['message']}")
        if len(problems) > limit:
            lines.append(f"  ... and {len(problems) - limit} more")
        return "\n".join(lines), errors

    @staticmethod
    def _seconds(seconds, default):
        if seconds is None:
            return default
        if not isinstance(seconds, (int, float)) or seconds <= 0:
            raise ToolError("seconds should be a number above 0")
        return min(float(seconds), 60.0)

    # tools
    def tool_project_info(self):
        programs = [path for path in self.project.walk() if path.endswith(".gubl")]
        lines = [f"gublan {_version()}", f"project folder: {self.project.root}", ""]
        if programs:
            lines.append(f"{_plural(len(programs), 'program')}:")
            for path in programs[:80]:
                try:
                    with open(path, "r", encoding="utf-8-sig") as handle:
                        text = handle.read()
                except OSError:
                    continue
                tests = sum(1 for line in text.splitlines() if line.strip().startswith("test "))
                extra = f", {_plural(tests, 'test')}" if tests else ""
                lines.append(f"  {self.project.relative(path)} ({_plural(text.count(chr(10)) + 1, 'line')}{extra})")
        else:
            lines.append("no .gubl programs yet. write_file can make one, like game.gubl.")
        lines.append("")
        lines.append("command_help lists every command. docs/COMMANDS.md in the gublan folder has the full guide.")
        return "\n".join(lines)

    def tool_list_files(self, folder=None):
        start = self.project.path(folder, must_exist=True, folder=True) if folder else self.project.root
        files = self.project.walk(start)
        if not files:
            return "this folder is empty."
        lines = []
        for path in files:
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            lines.append(f"{self.project.relative(path)}  ({size:,} bytes)")
        if len(files) >= 600:
            lines.append("... (only the first 600 files are listed)")
        return "\n".join(lines)

    def tool_read_file(self, path, start_line=None, end_line=None, line_numbers=False):
        full = self.project.path(path, must_exist=True)
        extension = os.path.splitext(full)[1].lower()
        size = os.path.getsize(full)
        if extension in IMAGE_TYPES:
            if size > 5_000_000:
                raise ToolError("that picture is too big to send (over 5 mb)")
            with open(full, "rb") as handle:
                data = base64.b64encode(handle.read()).decode("ascii")
            return [{"type": "image", "data": data, "mimeType": IMAGE_TYPES[extension]},
                    {"type": "text", "text": f"{self.project.relative(full)} ({size:,} bytes)"}]
        if size > MAX_READ_BYTES:
            raise ToolError(f"that file is {size:,} bytes, too big to read here")
        with open(full, "rb") as handle:
            raw = handle.read()
        if b"\0" in raw[:4096] and extension not in TEXT_EXTENSIONS:
            return f"{self.project.relative(full)} is not a text file ({size:,} bytes)"
        text = raw.decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
        lines = text.split("\n")
        first = max(1, int(start_line or 1))
        last = min(len(lines), int(end_line or len(lines)))
        chosen = lines[first - 1:last]
        if line_numbers:
            width = len(str(last))
            chosen = [f"{number:>{width}}| {line}" for number, line in enumerate(chosen, start=first)]
        body = "\n".join(chosen)
        header = f"{self.project.relative(full)} ({_plural(len(lines), 'line')}"
        header += f", showing {first}-{last})" if (first, last) != (1, len(lines)) else ")"
        return header + "\n" + _clip(body, 200_000)

    def _after_write(self, full, text, did):
        message = f"{did} {self.project.relative(full)} ({_plural(text.count(chr(10)) + 1, 'line')})."
        if full.endswith(".gubl"):
            problems, _errors = self._problems_text(text)
            message += "\n" + problems
        return message

    def tool_write_file(self, path, text):
        full = self.project.path(path)
        if os.path.isdir(full):
            raise ToolError(f"'{path}' is a folder")
        existed = os.path.isfile(full)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        return self._after_write(full, text, "replaced" if existed else "made")

    def tool_edit_file(self, path, old_text, new_text, replace_all=False):
        full = self.project.path(path, must_exist=True)
        with open(full, "r", encoding="utf-8-sig") as handle:
            text = handle.read().replace("\r\n", "\n")
        old_text, new_text = old_text.replace("\r\n", "\n"), new_text.replace("\r\n", "\n")
        if not old_text:
            raise ToolError("old_text is empty. use write_file to replace a whole file")
        count = text.count(old_text)
        if count == 0:
            stripped = "\n".join(line.strip() for line in old_text.split("\n"))
            near = stripped in "\n".join(line.strip() for line in text.split("\n"))
            raise ToolError("old_text was not found in the file" + (
                " (it is there with different spaces at the start of the lines; copy them exactly)" if near else
                ". read_file shows the current text"))
        if count > 1 and not replace_all:
            raise ToolError(f"old_text is in the file {count} times. add more lines around it so it is found "
                            "once, or set replace_all")
        text = text.replace(old_text, new_text) if replace_all else text.replace(old_text, new_text, 1)
        with open(full, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        return self._after_write(full, text, f"changed {_plural(count if replace_all else 1, 'place')} in")

    def tool_check_code(self, path=None, code=None):
        source, _base, _name, label = self._source(path, code)
        problems, _errors = self._problems_text(source, limit=200)
        return f"{label or 'the code'}: {problems}"

    def _run_report(self, session, runtime, label, seconds):
        lines = [f"ran {label or 'the code'}"]
        if session.output:
            lines.append("printed:")
            lines.extend("  " + line for line in _clip("\n".join(session.output)).split("\n"))
        else:
            lines.append("printed nothing.")
        error = getattr(runtime, "last_error", None)
        if error:
            where = f"{error['file']} line {error['line']}" if error.get("file") else (
                f"line {error['line']}" if error.get("line") else "while loading")
            lines.append(f"stopped with an error on {where}: {error['message']}")
        elif session.stopped_for_shot:
            lines.append(f"it was stopped once the picture was taken ({session.shot_at:.1f} seconds in).")
        elif session.timed_out:
            lines.append(f"it was still running after {seconds:g} seconds, so it was stopped (that is normal for "
                         "games).")
        else:
            lines.append(f"it finished in {session.elapsed():.2f} seconds.")
        if session.frames:
            lines.append(f"{_plural(session.frames, 'frame')} were drawn in a {runtime.mode} window.")
        variables = {name: value for name, value in sorted(runtime.vars.items()) if not name.startswith("_")}
        if variables:
            from gublancore import format_value
            shown = []
            for name, value in list(variables.items())[:60]:
                text = format_value(value)
                shown.append(f"  {name} = {text if len(text) < 120 else text[:117] + '...'}")
            lines.append("variables at the end:")
            lines.extend(shown)
        if runtime.objects:
            names = sorted(runtime.objects)
            lines.append(f"objects: {', '.join(names[:50])}{' ...' if len(names) > 50 else ''}")
        return "\n".join(lines)

    def tool_run_program(self, path=None, code=None, seconds=None, inputs=None, hold=None, actions=None,
                         show_window=False):
        source, base, name, label = self._source(path, code)
        seconds = self._seconds(seconds, 3.0)
        session, runtime = run_gublan(source, base, name, seconds=seconds, inputs=inputs, hold=hold,
                                      actions=actions, show_window=bool(show_window))
        return self._run_report(session, runtime, label, seconds)

    def tool_run_tests(self, path=None, code=None, name=None):
        source, base, program, label = self._source(path, code)
        from gublancore import GublanRuntime
        deadline = time.perf_counter() + 60
        runtime = GublanRuntime(onlog=lambda *_: None, base_dir=base, oninput=lambda _prompt: "",
                                onpopup=lambda _text: None, onpresence=lambda *_: None,
                                shouldstop=lambda: time.perf_counter() > deadline, save_name=program + "_tests")
        results = runtime.run_tests(source, base, only=name or None)
        if not results:
            if name:
                return f"there is no test called '{name}' in {label or 'the code'}."
            return (f"{label or 'the code'} has no test blocks. a test looks like:\n"
                    "test adding works\n    assert 1 + 1 == 2\nend")
        lines = []
        for result in results:
            if result["passed"]:
                lines.append(f"pass: {result['name']} ({result['seconds']:.2f}s)")
            else:
                where = f" ({result['file'] + ' ' if result.get('file') else ''}line {result['line']})" \
                    if result.get("line") else ""
                lines.append(f"fail: {result['name']}{where}: {result['message']}")
        failed = sum(1 for result in results if not result["passed"])
        lines.append(f"{len(results) - failed} passed, {failed} failed")
        return "\n".join(lines)

    def tool_screenshot(self, path=None, code=None, seconds=None, inputs=None, hold=None, actions=None,
                        show_window=False, save_as=None):
        source, base, name, label = self._source(path, code)
        seconds = self._seconds(seconds, 1.0)
        target = self.project.path(save_as) if save_as else None
        session, runtime = run_gublan(source, base, name, seconds=seconds, inputs=inputs, hold=hold,
                                      actions=actions, screenshot=True, show_window=bool(show_window))
        report = self._run_report(session, runtime, label, seconds)
        if session.shot is None:
            return report + "\nno picture: the program never drew a window. it needs a mode 2d or mode 3d line."
        png = _png(session.shot)
        if target:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as handle:
                handle.write(png)
            report += f"\nsaved the picture as {self.project.relative(target)}."
        width, height = session.shot.get_size()
        report = f"the window after {session.shot_at:.1f} seconds ({width}x{height}).\n" + report
        return [{"type": "image", "data": base64.b64encode(png).decode("ascii"), "mimeType": "image/png"},
                {"type": "text", "text": report}]

    def tool_command_help(self, topic=None):
        from gublancore import CATEGORY_ORDER, COMMAND_SPECS, EXPRESSION_FUNCTIONS
        if not topic or not topic.strip():
            lines = ["commands (one per line, the first word):"]
            by_category = {}
            for command, spec in COMMAND_SPECS.items():
                by_category.setdefault(spec[0], []).append(command)
            for category in list(CATEGORY_ORDER) + sorted(set(by_category) - set(CATEGORY_ORDER)):
                if category in by_category:
                    lines.append(f"  {category}: {', '.join(by_category[category])}")
            lines.append("functions (inside expressions and {braces}): " + ", ".join(EXPRESSION_FUNCTIONS))
            lines.append("give a topic to see how one works.")
            return "\n".join(lines)
        word = topic.strip().lower()
        if word in COMMAND_SPECS:
            category, usage, _minimum, summary, example = COMMAND_SPECS[word]
            return f"{usage}\n  {summary}\n  example: {example}\n  category: {category}"
        if word.rstrip("()") in EXPRESSION_FUNCTIONS:
            signature, about = _function_parts(EXPRESSION_FUNCTIONS[word.rstrip("()")])
            return f"{signature}\n  {about}\n  a function: use it in an expression, like print {{{signature}}}"
        found = [f"{spec[1]}  -  {spec[3]}" for command, spec in COMMAND_SPECS.items()
                 if word in command or word in spec[3].lower() or word in spec[1].lower()]
        found += ["  -  ".join(_function_parts(text)) for function, text in EXPRESSION_FUNCTIONS.items()
                  if word in function or word in text.lower()]
        if not found:
            return f"nothing about '{topic}'. call command_help with no topic to list everything."
        return f"{_plural(len(found), 'match')} for '{topic}':\n" + "\n".join("  " + line for line in found[:40])

    def tool_convert_code(self, code=None, path=None, language=None, save_as=None):
        import gublanconvert
        if (code is None) == (not path):
            raise ToolError("give either code or the path of a .py, .js or .lua file")
        filename = None
        if path:
            full = self.project.path(path, must_exist=True)
            with open(full, "r", encoding="utf-8-sig") as handle:
                code = handle.read()
            filename = full
        try:
            result = gublanconvert.convert(code, language=language, filename=filename)
        except gublanconvert.Unsupported as err:
            raise ToolError(f"could not convert it: {err}") from err
        summary = (f"{result.language} -> gublan: {result.source_lines} lines in, {result.output_lines} out, "
                   f"{_plural(result.todos, 'todo')}.")
        if result.notes:
            summary += "\nnotes:\n" + "\n".join("  " + note for note in result.notes)
        if save_as:
            target = self.project.path(save_as)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(result.text)
            summary += f"\nsaved as {self.project.relative(target)}."
        return summary + "\n\n" + _clip(result.text, 100_000)

    def tool_translate_code(self, language, path=None, code=None, folder=None):
        import gublantranslate
        source, base, name, label = self._source(path, code)
        try:
            result = gublantranslate.translate(source, language, name=name, base_dir=base)
        except gublantranslate.TranslateError as err:
            raise ToolError(f"could not translate: {err}") from err
        language = result.language
        lines = [f"{label or 'the code'} -> {language}: {result.source_lines} gublan lines, {result.output_lines} "
                 f"{language} lines, {_plural(result.todos, 'todo')}."]
        lines.extend("note: " + note for note in result.notes)
        lines.append(gublantranslate.LANGUAGES[language]["how"].format(main=result.main))
        if folder:
            target = self.project.path(folder)
            written = gublantranslate.write_files(result, target)
            lines.append("saved: " + ", ".join(self.project.relative(item) for item in written))
        else:
            others = [file_name for file_name in result.files if file_name != result.main]
            lines.append(f"files: {result.main} (below), {', '.join(others)} (give folder to save them all)")
            lines.append("")
            lines.append(_clip(result.files[result.main], 100_000))
        return "\n".join(lines)

    # resources: the command guide and the project's programs
    def resources(self):
        items = [{"uri": "gublan://docs/commands", "name": "commands", "title": "every gublan command",
                  "description": "the full command and function guide", "mimeType": "text/markdown"}]
        for path in self.project.walk(limit=300):
            if path.endswith(".gubl"):
                relative = self.project.relative(path)
                items.append({"uri": "gublan://project/" + relative, "name": relative, "mimeType": "text/x-gublan"})
        return items

    def read_resource(self, uri):
        if uri == "gublan://docs/commands":
            from studio import docsgen
            return {"uri": uri, "mimeType": "text/markdown", "text": docsgen.commands_markdown()}
        if uri.startswith("gublan://project/"):
            full = self.project.path(uri[len("gublan://project/"):], must_exist=True)
            with open(full, "r", encoding="utf-8-sig") as handle:
                return {"uri": uri, "mimeType": "text/x-gublan", "text": handle.read()}
        raise ToolError(f"no resource {uri}")


# ----- stdio ---------------------------------------------------------------------------------------------------------
def _std_streams():
    """the binary stdin and stdout. a windowed exe has no sys.stdin, so open the handles it was given."""
    stdin = getattr(sys.stdin, "buffer", None)
    stdout = getattr(sys.stdout, "buffer", None)
    if (stdin is None or stdout is None) and os.name == "nt":
        import ctypes
        import msvcrt
        kernel = ctypes.windll.kernel32
        kernel.GetStdHandle.restype = ctypes.c_void_p
        streams = []
        for number, mode in ((-10, "rb"), (-11, "wb")):
            handle = kernel.GetStdHandle(number)
            if not handle or handle == ctypes.c_void_p(-1).value:
                raise OSError("this program was not started with stdin and stdout to talk over")
            streams.append(os.fdopen(msvcrt.open_osfhandle(handle, 0), mode, buffering=0))
        stdin, stdout = streams
    if stdin is None or stdout is None:
        raise OSError("this program was not started with stdin and stdout to talk over")
    return stdin, stdout


def serve(folder=None):
    """read json-rpc messages from stdin, one per line, and answer on stdout until stdin closes."""
    folder = os.path.abspath(folder or os.getcwd())
    if not os.path.isdir(folder):
        print(f"there is no folder {folder}", file=sys.stderr)
        return 1
    stdin, stdout = _std_streams()
    # everything else (print, pygame's hello, gublan's own output) goes to stderr so stdout stays clean
    sys.stdout = sys.stderr if sys.stderr is not None else open(os.devnull, "w", encoding="utf-8")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:  # plugins switched on in gublan studio add their commands here too
        from studio import plugins
        for info in plugins.load_plugins():
            if info.status != "off":
                print(f"plugin {info.describe()}", file=sys.stderr)
    except ImportError:
        pass
    server = Server(folder)
    print(f"gublan mcp server {_version()} for {server.project.root}", file=sys.stderr)

    def send(reply):
        stdout.write((json.dumps(reply, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
        stdout.flush()

    for raw in stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw.decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError) as err:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"could not read that: {err}"}})
            continue
        if isinstance(message, list):  # a batch (older protocol versions)
            replies = [reply for reply in (server.handle(item) for item in message) if reply is not None]
            if replies:
                send(replies)
            continue
        reply = server.handle(message)
        if reply is not None:
            send(reply)
    return 0


def client_config(folder, frozen=None):
    """the json an ai app needs to start this server for a project (shown in the studio)."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if frozen:
        command, args = sys.executable, ["--mcp", folder]
    else:
        command = sys.executable
        args = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "gublancli.py"), "mcp", folder]
    return {"mcpServers": {"gublan": {"command": command, "args": args}}}


def client_snippets(folder):
    """ready-to-paste setup for the common ai apps: {label: (where it goes, text)}"""
    server = client_config(folder)["mcpServers"]["gublan"]
    command, args = server["command"], server["args"]
    quoted = " ".join(f'"{part}"' if " " in part else part for part in [command] + args)
    return {
        "claude code": ("run this in a terminal (or save the project file below)",
                        f"claude mcp add gublan -- {quoted}"),
        "claude desktop / cursor": ("add this to claude_desktop_config.json or .cursor/mcp.json",
                                    json.dumps({"mcpServers": {"gublan": server}}, indent=2)),
        "vs code": ("save this as .vscode/mcp.json in the project",
                    json.dumps({"servers": {"gublan": {"type": "stdio", "command": command, "args": args}}},
                               indent=2)),
    }


def self_test(folder, timeout=30):
    """start the server like an ai app would and ask for its tools. gives back the tool names."""
    import subprocess
    server = client_config(folder)["mcpServers"]["gublan"]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen([server["command"]] + server["args"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, creationflags=flags)
    try:
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": DEFAULT_PROTOCOL, "capabilities": {},
                                "clientInfo": {"name": "gublan self test", "version": _version()}}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
        data = "".join(json.dumps(message) + "\n" for message in messages).encode("utf-8")
        output, _errors = process.communicate(data, timeout=timeout)
    except Exception:
        process.kill()
        raise
    replies = {}
    for line in output.decode("utf-8", errors="replace").splitlines():
        try:
            reply = json.loads(line)
        except ValueError:
            raise OSError(f"the server wrote something that is not json: {line[:80]}") from None
        replies[reply.get("id")] = reply
    if 2 not in replies or "result" not in replies[2]:
        raise OSError("the server did not answer")
    return [tool["name"] for tool in replies[2]["result"]["tools"]]


if __name__ == "__main__":
    sys.exit(serve(sys.argv[1] if len(sys.argv) > 1 else None))
