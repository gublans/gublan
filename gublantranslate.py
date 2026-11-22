"""turn a gublan program into python, javascript or lua (the other way round from gublanconvert).

    from gublantranslate import translate
    result = translate(source, "python", name="game")
    result.files    {"game.py": "...", "gublan_runtime.py": "..."}

the new program keeps the shape of the gublan one: the same names, loops, functions and comments.
everything gublan does for you (windows, shapes, keys, sound, saving, its built-in functions) lives in a
small runtime library that is written next to it, so the translated code itself stays short and readable.

    python      game.py + gublan_runtime.py              py game.py  (windows and sound need pygame-ce)
    javascript  game.js + gublan_runtime.js + index.html open index.html in a browser, or: node game.js
    lua         main.lua + gublan.lua                    a love2d game folder (love .), or plain lua
"""

import ast
import json
import keyword
import os
import re
import sys

from gublancore import (
    BLOCK_MIDDLES, BLOCK_OPENERS, EXPRESSION_FUNCTIONS, GublanRuntime, QuotedText, analyze_source,
    parse_expression, parse_line, split_command,
)
from gublancore import (  # the same rules the runtime uses, so a translated program reads its lines the same way
    _BRACE_RE, _FOR_IN_RE, _FOR_RANGE_RE, _NUMBER_RE, _SET_RE, _condition_is_simple, _normalize_condition,
    _split_top_level_commas,
)

try:
    from studio.version import VERSION
except ImportError:  # pragma: no cover - only when gublantranslate is copied somewhere on its own
    VERSION = ""

RUNTIME_FOLDER = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "runtimes")

LANGUAGES = {
    "python": {"label": "python", "extension": ".py", "runtime": "gublan_runtime.py",
               "how": "run it with: py {main}   (windows, shapes and sound need: py -m pip install pygame-ce)"},
    "javascript": {"label": "javascript (web page)", "extension": ".js", "runtime": "gublan_runtime.js",
                   "how": "open index.html in a web browser, or run text programs with: node {main}"},
    "lua": {"label": "lua (love2d)", "extension": ".lua", "runtime": "gublan.lua",
            "how": "run the folder with love2d (love .), or text programs with: lua {main}"},
}
ALIASES = {"py": "python", "js": "javascript", "web": "javascript", "html": "javascript", "love": "lua",
           "love2d": "lua"}

# commands that only make sense in 3d (not translated yet: they become todo comments)
THREE_D = {"cube", "sphere", "camera"}
# commands that open a window
WINDOW_COMMANDS = {"mode", "window", "box", "circle", "line", "text", "image", "sprite", "button", "ui", "textbox",
                   "slider", "checkbox", "background", "frame"}
# commands that store into a variable: command -> positions in the line that are variable names
STORES = {
    "add": (1,), "sub": (1,), "mul": (1,), "div": (1,), "calc": (1,), "random": (1,), "time": (1,),
    "list": (1,), "map": (1,), "item": (3,), "length": (2,), "lookup": (3,), "has": (3,), "touching": (1,),
    "key": (1,), "keypressed": (1,), "mouse": (1, 2), "mousebutton": (1,), "input": (1,), "load": (2,),
    "vec2": (1,), "vec3": (1,), "get": (2,),
}
LOOPS = {"loop", "forever", "while", "until", "for"}
# builtins whose answer is always true or false (no truthiness wrapper needed in javascript and lua)
BOOLEAN_FUNCTIONS = {"contains", "keydown", "keypressed", "mousedown", "mousepressed", "touching", "exists",
                     "chance", "startswith", "endswith", "isnumber", "overlap", "saved", "any", "every"}
TEXT_FUNCTIONS = {"str", "string", "upper", "lower", "trim", "join", "replace", "pad", "decimals", "capitalize",
                  "char", "tojson", "date", "clock", "type"}
NUMBER_FUNCTIONS = {"abs", "min", "max", "round", "floor", "ceil", "sqrt", "sin", "cos", "tan", "atan2", "rad",
                    "deg", "clamp", "lerp", "sign", "dist", "len", "num", "number", "int", "random", "mousex",
                    "mousey", "time", "mag", "pow", "asin", "acos", "atan", "sum", "indexof", "count", "average",
                    "wrap", "remap", "approach", "angleto", "now", "code", "textwidth", "log", "exp", "noise",
                    "randint"}
LIST_FUNCTIONS = {"range", "sort", "reverse", "keys", "values", "split", "shuffle", "unique", "map", "filter", "sortby",
                  "zip", "flat", "lines", "words"}
# commands that have to wait for the screen in javascript (so they are awaited, and so is anything calling them)
JS_WAITS = {"frame", "wait", "input", "popup", "animate", "get"}


class TranslateError(ValueError):
    """the program could not be translated (it has errors, or the language is unknown)."""


class TranslateResult:
    def __init__(self, language, files, main, todos, notes, source_lines):
        self.language = language
        self.files = files
        self.main = main
        self.todos = todos
        self.notes = notes
        self.source_lines = source_lines

    @property
    def text(self):
        return self.files[self.main]

    @property
    def output_lines(self):
        return self.text.count("\n") + 1


def language_of(name):
    key = str(name).strip().lower().lstrip(".")
    key = ALIASES.get(key, key)
    if key not in LANGUAGES:
        raise TranslateError(f"gublan can be turned into {', '.join(LANGUAGES)}, not '{name}'")
    return key


def runtime_source(language):
    with open(os.path.join(RUNTIME_FOLDER, LANGUAGES[language]["runtime"]), "r", encoding="utf-8") as handle:
        return handle.read()


def translate(source, language, name="program", base_dir=None, check=True):
    """turn gublan source into another language. raises TranslateError when the program has errors."""
    language = language_of(language)
    if check:
        errors = [item for item in analyze_source(source) if item.get("severity", "error") == "error"]
        if errors:
            first = errors[0]
            where = f"line {first['line']}: " if first.get("line") else ""
            raise TranslateError(f"fix the errors first. {where}{first['message']}")
    try:
        entries = GublanRuntime(onlog=lambda *_: None)._expand_includes_mapped(source, os.path.abspath(
            base_dir or os.getcwd()))
    except ValueError as err:
        raise TranslateError(str(err)) from err
    writer = {"python": _Python, "javascript": _JavaScript, "lua": _Lua}[language](entries, _safe_name(name))
    main_text = writer.program()
    files = {writer.main_file: main_text, LANGUAGES[language]["runtime"]: runtime_source(language)}
    if language == "javascript":
        files["index.html"] = _web_page(name, writer.main_file)
    if language == "lua":
        files["conf.lua"] = _LOVE_CONF.replace("{title}", name.replace('"', "").replace("\\", "")).replace(
            "{console}", "false" if writer.uses_window else "true")
    return TranslateResult(language, files, writer.main_file, writer.todos, sorted(writer.notes),
                           source.count("\n") + 1)


def write_files(result, folder):
    """save every file of a translation into a folder. returns the paths written."""
    os.makedirs(folder, exist_ok=True)
    written = []
    for file_name, text in result.files.items():
        path = os.path.join(folder, file_name)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        written.append(path)
    return written


def _safe_name(name):
    base = os.path.splitext(os.path.basename(str(name or "program")))[0]
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", base).strip("_").lower() or "program"
    return "program_" + cleaned if cleaned[0].isdigit() else cleaned


def _web_page(name, script):
    title = re.sub(r"[<>&\"]", "", str(name))
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ margin: 0; background: #101010; color: #e5e5e5; font: 15px/1.5 Consolas, monospace; }}
  #gublan-stage {{ display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 16px; }}
  canvas {{ max-width: 100%; outline: none; }}
  #gublan-log {{ white-space: pre-wrap; margin: 0; max-width: 100%; }}
</style>
</head>
<body>
<div id="gublan-stage"><pre id="gublan-log"></pre></div>
<script src="gublan_runtime.js"></script>
<script src="{script}"></script>
</body>
</html>
"""


_LOVE_CONF = """-- love2d settings for this program. the window opens when the program first draws something,
-- at the size the program asks for.
function love.conf(t)
    t.window = false
    t.console = {console}
    t.identity = "gublan_{title}"
end
"""


# ----- reading the program ---------------------------------------------------------------------------------------
class _Line:
    __slots__ = ("cmd", "parts", "rest", "call_source", "file", "number", "text")

    def __init__(self, parsed, file, number, text):
        self.cmd, self.parts, self.rest = parsed.cmd, parsed.parts, parsed.rest
        self.call_source = parsed.call_source
        self.file, self.number, self.text = file, number, text


class _Block:
    __slots__ = ("line", "body", "branches", "comments")

    def __init__(self, line):
        self.line = line
        self.body = []
        self.branches = []  # [(middle line, body)] for elseif, else, case and catch
        self.comments = []


class _Comment:
    __slots__ = ("text",)

    def __init__(self, text):
        self.text = text


_BLANK = "blank"


def _build(entries):
    root, stack, body = [], [], None
    body = root
    for raw, file, number in entries:
        stripped = raw.strip()
        if not stripped:
            if body and body[-1] is not _BLANK:
                body.append(_BLANK)
            continue
        if stripped.startswith("//"):
            body.append(_Comment(stripped[2:].strip()))
            continue
        parsed = parse_line(raw)
        if parsed is None:
            continue
        line = _Line(parsed, file, number, stripped)
        if parsed.cmd in BLOCK_OPENERS:
            block = _Block(line)
            body.append(block)
            stack.append(block)
            body = block.body
        elif parsed.cmd in BLOCK_MIDDLES and stack:
            branch = []
            stack[-1].branches.append((line, branch))
            body = branch
        elif parsed.cmd == "end" and stack:
            stack.pop()
            if not stack:
                body = root
            else:
                parent = stack[-1]
                body = parent.branches[-1][1] if parent.branches else parent.body
        else:
            body.append(line)
    return root


def _walk(nodes):
    """every line inside some nodes, including inside blocks."""
    for node in nodes:
        if isinstance(node, _Line):
            yield node
        elif isinstance(node, _Block):
            yield node.line
            yield from _walk(node.body)
            for middle, branch in node.branches:
                yield middle
                yield from _walk(branch)


def _stored_names(line):
    """plain variable names a line gives a value to."""
    cmd, parts = line.cmd, line.parts
    names = []
    if cmd in ("set", "const"):
        match = _SET_RE.match(line.rest)
        if match:
            names.append(match.group(1))
    elif cmd == "for":
        match = _FOR_RANGE_RE.match(line.rest) or _FOR_IN_RE.match(line.rest)
        if match:
            names.append(match.group(1))
    elif cmd == "catch":
        names.append(str(parts[1]) if len(parts) > 1 else "error")
    elif cmd in STORES:
        names.extend(str(parts[index]) for index in STORES[cmd] if index < len(parts))
    return [name for name in names if re.fullmatch(r"[A-Za-z_]\w*", name)]


def _has_continue(nodes, word="continue"):
    """does this loop body continue (or break) itself, not just an inner loop?"""
    for node in nodes:
        if isinstance(node, _Line) and node.cmd == word:
            return True
        if isinstance(node, _Block) and node.line.cmd not in LOOPS | {"function", "test"}:
            if _has_continue(node.body, word) or any(_has_continue(branch, word) for _, branch in node.branches):
                return True
    return False


def _slug(text):
    cleaned = re.sub(r"\W+", "_", str(text).strip().lower()).strip("_")
    return cleaned or "unnamed"


def _joined(values):
    """a JoinedStr node from text pieces and expression nodes (merging neighbouring text)."""
    merged = []
    for value in values:
        if isinstance(value, str):
            if not value:
                continue
            if merged and isinstance(merged[-1], ast.Constant):
                merged[-1] = ast.Constant(merged[-1].value + value)
            else:
                merged.append(ast.Constant(value))
        else:
            merged.append(ast.FormattedValue(value=value, conversion=-1, format_spec=None))
    if not merged:
        return ast.Constant("")
    if len(merged) == 1 and isinstance(merged[0], ast.Constant):
        return merged[0]
    return ast.JoinedStr(values=merged)


def _number_text(value):
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return repr(value)


# ----- the shared part of every language --------------------------------------------------------------------------
class _Writer:
    UNIT = "    "
    COMMENT = "#"
    RESERVED = set()
    main_file = ""

    def __init__(self, entries, name):
        self.program_name = name
        self.tree = _build(entries)
        self.out = []
        self.depth = 0
        self.todos = 0
        self.notes = set()
        self.scopes = []          # stack of sets of local names (function parameters, little-function names)
        self.counter = 0
        self.functions = {}       # name -> parameters
        self.tests = []
        self.variables = set()
        self.buttons = set()
        self.objects_3d = set()
        self.kinds = {}           # variable -> "list", "map" or "text" when it is obvious
        self.uses_ui_button = False
        self.uses_window = False
        self.function_bodies = {}
        self._scan()

    # ----- looking at the program first --------------------------------------------------------------
    def _scan(self):
        for node in self.tree:
            if isinstance(node, _Block) and node.line.cmd == "function" and len(node.line.parts) > 1:
                self.functions[str(node.line.parts[1])] = [str(part) for part in node.line.parts[2:]]
                self.function_bodies[str(node.line.parts[1])] = node.body
        for line in _walk(self.tree):
            for stored in _stored_names(line):
                self.variables.add(stored)
            cmd, parts = line.cmd, line.parts
            if cmd == "button" and len(parts) > 1:
                self.buttons.add(str(parts[1]))
            elif cmd == "ui":
                self.uses_ui_button = True
            if cmd in WINDOW_COMMANDS:
                self.uses_window = True
            elif cmd in THREE_D and len(parts) > 1:
                self.objects_3d.add(str(parts[1]))
            if cmd == "list":
                self.kinds.setdefault(str(parts[1]), "list")
            elif cmd == "map":
                self.kinds.setdefault(str(parts[1]), "map")
            elif cmd == "set":
                match = _SET_RE.match(line.rest)
                if match and re.fullmatch(r"[A-Za-z_]\w*", match.group(1)):
                    value = match.group(2).strip()
                    kind = ("list" if value.startswith("[") else "map" if value.startswith("{") and ":" in value
                            else "text" if value[:1] in "\"'" else
                            "vector" if re.match(r"vec[23]\s*\(", value) else None)
                    if kind:
                        self.kinds.setdefault(match.group(1), kind)
        self.variables -= self.buttons

    # ----- names ---------------------------------------------------------------------------------------------
    def ident(self, name):
        name = str(name)
        return name + "_" if name in self.RESERVED else name

    def is_local(self, name):
        return any(name in scope for scope in self.scopes)

    def is_variable(self, name):
        return (self.is_local(name) or name in self.variables or name in self.buttons
                or name in ("dt", "screen_width", "screen_height") or (name == "ui" and self.uses_ui_button))

    def name_code(self, name):
        """how a variable is read (and written) in the new language."""
        if self.is_local(name):
            return self.ident(name)
        if name in self.buttons:
            return self.runtime_field("buttons", name)
        if name in ("dt", "screen_width", "screen_height") and name not in self.variables:
            return f"G.{name}"
        if name == "ui" and self.uses_ui_button:
            return "G.ui"
        return self.ident(name)

    def runtime_field(self, table, key):
        return f"G.{table}[{json.dumps(key)}]"

    # ----- gublan values -> expression trees (the same rules as the runtime) --------------------------------
    def val(self, token):
        if isinstance(token, QuotedText):
            return self.interp(str(token))
        text = str(token)
        if self.is_variable(text) or text in self.functions:
            return ast.Name(text)
        if text == "true":
            return ast.Constant(True)
        if text == "false":
            return ast.Constant(False)
        if text in ("none", "nil", "null"):
            return ast.Constant(None)
        if _NUMBER_RE.match(text):
            return ast.Constant(float(text) if "." in text else int(text))
        if text.startswith("{") and text.endswith("}") and len(text) > 2:
            try:
                return self.expression(text[1:-1])
            except (SyntaxError, ValueError):
                pass
        try:
            node = parse_expression(text)
        except (SyntaxError, ValueError):
            return self.interp(text)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                return self.interp(node.value)
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return node
            return ast.Constant(text)
        if isinstance(node, ast.Name):
            return node if self.is_variable(node.id) or node.id in self.functions else ast.Constant(text)
        if isinstance(node, (ast.List, ast.Dict)) and not text.startswith(("[", "{")):
            return ast.Constant(text)
        return node

    def interp(self, text):
        """text with {expressions} inside -> a JoinedStr (or plain text)."""
        if "{" not in text:
            return ast.Constant(text)
        values, last = [], 0
        for match in _BRACE_RE.finditer(text):
            inner = match.group(1).strip()
            if not inner:
                continue
            try:
                node = parse_expression(inner)
            except (SyntaxError, ValueError):
                continue
            values.append(text[last:match.start()])
            values.append(node)
            last = match.end()
        values.append(text[last:])
        return _joined(values)

    def text_of(self, tokens):
        """print, text, popup and input words (see GublanRuntime._text)."""
        if any("{" in token and not isinstance(token, QuotedText) for token in tokens):
            pieces = []
            for index, token in enumerate(tokens):
                if index:
                    pieces.append(" ")
                part = self.interp(str(token))
                pieces.extend(self._pieces(part))
            return _joined(pieces)
        pieces = []
        for index, token in enumerate(tokens):
            if index:
                pieces.append(" ")
            node = self.val(token)
            if isinstance(node, ast.Constant):
                value = node.value
                pieces.append("true" if value is True else "false" if value is False else "none" if value is None
                              else _number_text(value) if isinstance(value, (int, float)) else str(value))
            else:
                pieces.extend(self._pieces(node))
        return _joined(pieces)

    @staticmethod
    def _pieces(node):
        if isinstance(node, ast.Constant):
            return [str(node.value)]
        if isinstance(node, ast.JoinedStr):
            return [value.value if isinstance(value, ast.Constant) else value.value for value in node.values]
        return [node]

    def label(self, tokens):
        return self.interp(" ".join(str(token) for token in tokens))

    def eval_value(self, raw, tokens):
        raw = raw.strip()
        if len(tokens) == 1:
            return self.val(tokens[0])
        if not tokens:
            return ast.Constant(None)
        try:
            return self.expression(raw)
        except (SyntaxError, ValueError):
            return self.interp(" ".join(str(token) for token in tokens))

    def value_from(self, tokens):
        return self.val(tokens[0]) if len(tokens) == 1 else self.interp(" ".join(str(token) for token in tokens))

    def expression(self, text):
        return parse_expression(_normalize_condition(text) if ("&&" in text or "||" in text) else text)

    def condition(self, line):
        tokens = line.parts[1:]
        if _condition_is_simple(tokens):
            operator = {"=": ast.Eq(), "==": ast.Eq(), "!=": ast.NotEq(), ">": ast.Gt(), "<": ast.Lt(),
                        ">=": ast.GtE(), "<=": ast.LtE()}[tokens[1]]
            return ast.Compare(left=self.val(tokens[0]), ops=[operator], comparators=[self.val(tokens[2])])
        if len(tokens) == 1:
            return self.val(tokens[0])
        return parse_expression(_normalize_condition(line.rest))

    def object_name(self, token):
        return self.interp(str(token))

    def color_args(self, tokens):
        if len(tokens) == 3:
            return [self.val(token) for token in tokens]
        token = tokens[0]
        text = str(token)
        if not isinstance(token, QuotedText) and (self.is_variable(text) or (text.startswith("{") and text.endswith("}"))):
            return [self.val(token)]
        return [ast.Constant(text)]

    def target(self, text):
        """the left side of an assignment as an expression tree (a name, a.field or a[index])."""
        try:
            node = parse_expression(text)
        except (SyntaxError, ValueError):
            return ast.Name(text)
        return node

    # ----- output ----------------------------------------------------------------------------------------------
    def emit(self, text=""):
        self.out.append((self.UNIT * self.depth + text) if text else "")

    def comment(self, text):
        self.emit(f"{self.COMMENT} {text}" if text else self.COMMENT)

    def todo(self, line, why):
        self.todos += 1
        self.comment(f"todo: {line.text}   ({why})")

    def fresh(self, stem):
        self.counter += 1
        return f"{stem}{self.counter}"

    def blank(self):
        if self.out and self.out[-1] != "":
            self.out.append("")

    def program(self):
        hoisted, main, pending = [], [], []
        for node in self.tree:
            if isinstance(node, _Comment) or node is _BLANK:
                pending.append(node)
                continue
            if isinstance(node, _Block) and node.line.cmd in ("function", "test"):
                node.comments = [item for item in pending if isinstance(item, _Comment)]
                hoisted.append(node)
            else:
                main.extend(pending)
                main.append(node)
            pending = []
        main.extend(item for item in pending if isinstance(item, _Comment))
        while main and main[0] is _BLANK:
            main.pop(0)
        while main and main[-1] is _BLANK:
            main.pop()
        self.header()
        for node in hoisted:
            self.blank()
            for item in node.comments:
                self.comment(item.text)
            if node.line.cmd == "function":
                self.function(node)
            else:
                self.test(node)
        self.blank()
        self.main(main)
        self.footer()
        while self.out and self.out[-1] == "":
            self.out.pop()
        self.tidy()
        return "\n".join(self.out) + "\n"

    def tidy(self):
        """a last look over the finished lines."""

    def header_lines(self):
        made = f"made from {self.program_name}.gubl by gublan studio{(' ' + VERSION) if VERSION else ''}."
        how = LANGUAGES[self.LANGUAGE]["how"].format(main=self.main_file)
        return [made, how]

    def body(self, nodes):
        for node in nodes:
            if node is _BLANK:
                self.blank()
            elif isinstance(node, _Comment):
                self.comment(node.text)
            elif isinstance(node, _Block):
                self.block(node)
            else:
                self.statement(node)

    def block(self, node):
        cmd = node.line.cmd
        handler = getattr(self, "b_" + cmd, None)
        if handler is None or cmd in ("function", "test"):
            self.todo(node.line, f"a {cmd} block can only be at the top of the program")
            return
        handler(node)

    def statement(self, line):
        cmd = line.cmd
        if cmd in THREE_D or (cmd == "mode" and len(line.parts) > 1 and line.parts[1] == "3d") or (
                cmd == "spin" and len(line.parts) > 1 and str(line.parts[1]) in self.objects_3d):
            self.notes.add("3d scenes are not translated yet. those lines are left as todo comments.")
            self.todo(line, "3d is not translated yet")
            return
        if cmd == "presence":
            self.comment(f"{line.text}   (the discord status only works inside gublan)")
            return
        handler = getattr(self, "c_" + cmd, None)
        if handler is None:
            self.todo(line, f"'{cmd}' can't be translated")
            return
        try:
            handler(line)
        except (SyntaxError, ValueError, IndexError) as err:
            self.todo(line, str(err).lower() or "this line could not be read")

    # ----- commands that work the same way in every language -------------------------------------------------
    def call(self, function, *args):
        """a statement that calls the runtime library."""
        self.line_code(self.runtime_call(function, list(args)))

    def runtime_call(self, function, args):
        return f"G.{function}({', '.join(self.expr(arg) for arg in args)})"

    def c_print(self, line):
        arguments = _split_top_level_commas(line.rest)
        if len(arguments) > 1:
            values = [self.eval_value(argument, split_command(argument)) for argument in arguments]
            pieces = []
            for index, value in enumerate(values):
                if index:
                    pieces.append(" ")
                pieces.extend(self._pieces(value) if isinstance(value, (ast.Constant, ast.JoinedStr)) else [value])
            self.print_text(_joined(pieces))
            return
        self.print_text(self.text_of(line.parts[1:]))

    def c_set(self, line):
        match = _SET_RE.match(line.rest)
        target, raw = match.groups()
        self.store(self.target(target), self.eval_value(raw, split_command(raw)))

    c_const = c_set

    def c_calc(self, line):
        self.store(self.target(str(line.parts[1])), self.expression(line.rest.split(None, 1)[1]))

    def arithmetic(self, line, operator):
        name = str(line.parts[1])
        raw = line.rest.split(None, 1)[1] if len(line.rest.split(None, 1)) > 1 else ""
        amount = self.eval_value(raw, line.parts[2:])
        target = self.target(name)
        kind = self.kinds.get(name)
        if isinstance(operator, ast.Add) and kind == "list":
            self.append_to(target, amount)
            return
        if isinstance(operator, ast.Add) and kind == "text":
            amount = self.as_text(amount)
        self.store(target, ast.BinOp(left=target, op=operator, right=amount), compound=operator)

    def c_add(self, line):
        self.arithmetic(line, ast.Add())

    def c_sub(self, line):
        self.arithmetic(line, ast.Sub())

    def c_mul(self, line):
        self.arithmetic(line, ast.Mult())

    def c_div(self, line):
        self.arithmetic(line, ast.Div())

    def c_random(self, line):
        self.store(ast.Name(str(line.parts[1])), self.builtin("random", self.val(line.parts[2]),
                                                              self.val(line.parts[3])))

    def c_time(self, line):
        self.store(ast.Name(str(line.parts[1])), self.builtin("time"))

    def builtin(self, name, *args):
        return ast.Call(func=ast.Name(name), args=list(args), keywords=[])

    def as_text(self, node):
        return node if self.is_text(node) else self.builtin("str", node)

    def c_call(self, line):
        if line.call_source:
            self.line_code(self.expr(parse_expression(line.call_source)))
            return
        name = str(line.parts[1])
        self.line_code(self.expr(ast.Call(func=ast.Name(name), args=[self.val(arg) for arg in line.parts[2:]],
                                          keywords=[])))

    def c_list(self, line):
        self.store(ast.Name(str(line.parts[1])), ast.List(elts=[self.val(token) for token in line.parts[2:]]))

    def c_append(self, line):
        self.append_to(ast.Name(str(line.parts[1])), self.value_from(line.parts[2:]))

    def c_item(self, line):
        self.store(ast.Name(str(line.parts[3])), ast.Subscript(value=ast.Name(str(line.parts[1])),
                                                               slice=self.val(line.parts[2])))

    def c_length(self, line):
        self.store(ast.Name(str(line.parts[2])), self.builtin("len", self.val(line.parts[1])))

    def c_map(self, line):
        self.store(ast.Name(str(line.parts[1])), ast.Dict(keys=[], values=[]))

    def c_put(self, line):
        self.store(ast.Subscript(value=ast.Name(str(line.parts[1])), slice=ast.Constant(str(line.parts[2]))),
                   self.value_from(line.parts[3:]))

    def c_lookup(self, line):
        self.store(ast.Name(str(line.parts[3])), ast.Subscript(value=ast.Name(str(line.parts[1])),
                                                               slice=ast.Constant(str(line.parts[2]))))

    def c_has(self, line):
        self.store(ast.Name(str(line.parts[3])), ast.Compare(left=ast.Constant(str(line.parts[2])), ops=[ast.In()],
                                                             comparators=[ast.Name(str(line.parts[1]))]))

    def c_delete(self, line):
        name = str(line.parts[1])
        if len(line.parts) == 2:
            if self.is_variable(name) and name not in self.buttons:
                self.store(ast.Name(name), ast.Constant(None))
            else:
                self.call("delete", self.object_name(line.parts[1]))
            return
        self.call("remove_at", ast.Name(name), self.val(line.parts[2]) if self.kinds.get(name) != "map"
                  else ast.Constant(str(line.parts[2])))

    def c_insert(self, line):
        self.call("insert", ast.Name(str(line.parts[1])), self.val(line.parts[2]), self.value_from(line.parts[3:]))

    def c_remove(self, line):
        self.call("remove", ast.Name(str(line.parts[1])), self.value_from(line.parts[2:]))

    def c_shuffle(self, line):
        self.call("shuffle_list", ast.Name(str(line.parts[1])))

    def c_sort(self, line):
        self.call("sort_list", ast.Name(str(line.parts[1])), ast.Constant(len(line.parts) > 2))

    def c_wait(self, line):
        self.call("wait", self.val(line.parts[1]))

    def c_kill(self, line):
        self.call("kill")

    def c_then(self, line):
        self.call("kill")

    def c_throw(self, line):
        self.throw(self.label(line.parts[1:]))

    def c_assert(self, line):
        source = line.rest
        self.call("check", self.condition(line), ast.Constant(source))

    # display and objects
    def c_mode(self, line):
        self.call("mode", ast.Constant(str(line.parts[1])))

    def c_window(self, line):
        args = [self.val(line.parts[1]), self.val(line.parts[2])]
        if len(line.parts) > 3:
            args.append(self.label(line.parts[3:]))
        self.call("window", *args)

    def c_title(self, line):
        self.call("title", self.label(line.parts[1:]))

    def c_background(self, line):
        self.call("background", *self.color_args(line.parts[1:]))

    def c_color(self, line):
        self.call("color", *self.color_args(line.parts[1:]))

    def c_paint(self, line):
        self.call("paint", self.object_name(line.parts[1]), *self.color_args(line.parts[2:]))

    def c_clear(self, line):
        self.call("clear")

    def c_frame(self, line):
        self.call("frame")

    def c_fps(self, line):
        self.call("fps", self.val(line.parts[1]))

    def c_textsize(self, line):
        self.call("textsize", self.val(line.parts[1]))

    def shape(self, line, function, count):
        parts = line.parts
        self.call(function, self.object_name(parts[1]), *[self.val(token) for token in parts[2:2 + count]])

    def c_box(self, line):
        self.shape(line, "box", 4)

    def c_circle(self, line):
        self.shape(line, "circle", 3)

    def c_line(self, line):
        self.shape(line, "line", 5)

    def c_text(self, line):
        parts = line.parts
        self.call("text", self.object_name(parts[1]), self.val(parts[2]), self.val(parts[3]), self.text_of(parts[4:]))

    def c_image(self, line):
        parts = line.parts
        self.call("image", self.object_name(parts[1]), ast.Constant(str(parts[2])), self.val(parts[3]),
                  self.val(parts[4]))

    def c_sprite(self, line):
        parts = line.parts
        self.call("sprite", self.object_name(parts[1]), ast.Constant(str(parts[2])),
                  *[self.val(token) for token in parts[3:7]])

    def c_spin(self, line):
        self.call("spin", self.object_name(line.parts[1]), self.val(line.parts[2]))

    def c_vec2(self, line):
        self.store(ast.Name(str(line.parts[1])), self.builtin("vec2", *[self.val(t) for t in line.parts[2:4]]))

    def c_vec3(self, line):
        self.store(ast.Name(str(line.parts[1])), self.builtin("vec3", *[self.val(t) for t in line.parts[2:5]]))

    def c_button(self, line):
        parts = line.parts
        self.call("button", ast.Constant(str(parts[1])), *[self.val(token) for token in parts[2:6]],
                  self.label(parts[6:]))

    def c_ui(self, line):
        self.call("ui_button", self.label(line.parts[2:]))

    def c_textbox(self, line):
        parts = line.parts
        self.call("textbox", self.object_name(parts[1]), *[self.val(token) for token in parts[2:5]],
                  self.label(parts[5:]))

    def c_slider(self, line):
        parts = line.parts
        args = [self.object_name(parts[1])] + [self.val(token) for token in parts[2:8]]
        self.call("slider", *args)

    def c_checkbox(self, line):
        parts = line.parts
        self.call("checkbox", self.object_name(parts[1]), self.val(parts[2]), self.val(parts[3]),
                  self.label(parts[4:]))

    def c_focus(self, line):
        name = str(line.parts[1])
        self.call("focus", ast.Constant(None) if name == "none" else self.object_name(line.parts[1]))

    def c_move(self, line):
        parts = line.parts
        self.call("move", self.object_name(parts[1]), *[self.val(token) for token in parts[2:5]])

    def c_place(self, line):
        parts = line.parts
        self.call("place", self.object_name(parts[1]), *[self.val(token) for token in parts[2:5]])

    def c_resize(self, line):
        parts = line.parts
        self.call("resize", self.object_name(parts[1]), *[self.val(token) for token in parts[2:4]])

    def c_hide(self, line):
        self.call("hide", self.object_name(line.parts[1]))

    def c_show(self, line):
        self.call("show", self.object_name(line.parts[1]))

    def c_animate(self, line):
        parts = line.parts
        self.call("animate", self.object_name(parts[1]), *[self.val(token) for token in parts[2:]])

    def c_touching(self, line):
        self.store(ast.Name(str(line.parts[1])), self.flag(self.builtin(
            "touching", self.object_name(line.parts[2]), self.object_name(line.parts[3]))))

    def c_key(self, line):
        self.store(ast.Name(str(line.parts[1])), self.flag(self.builtin("keydown", self.val(line.parts[2]))))

    def c_keypressed(self, line):
        self.store(ast.Name(str(line.parts[1])), self.flag(self.builtin("keypressed", self.val(line.parts[2]))))

    def c_mouse(self, line):
        self.store(ast.Name(str(line.parts[1])), self.builtin("mousex"))
        self.store(ast.Name(str(line.parts[2])), self.builtin("mousey"))

    def c_mousebutton(self, line):
        self.store(ast.Name(str(line.parts[1])), self.builtin("mousedown", ast.Constant(str(line.parts[2]))))

    def flag(self, node):
        """true/false -> 1/0, like the key, keypressed and touching commands give."""
        return ast.Call(func=ast.Name("__flag__"), args=[node], keywords=[])

    def c_input(self, line):
        self.store(ast.Name(str(line.parts[1])), ast.Call(func=ast.Name("__ask__"),
                                                          args=[self.text_of(line.parts[2:])], keywords=[]))

    def c_popup(self, line):
        self.call("popup", self.text_of(line.parts[1:]))

    def c_cursor(self, line):
        self.call("cursor", ast.Constant(str(line.parts[1]) == "show"))

    def c_sound(self, line):
        self.call("sound", ast.Constant(" ".join(str(part) for part in line.parts[1:])))

    def c_music(self, line):
        self.call("music", ast.Constant(" ".join(str(part) for part in line.parts[1:])))

    def c_stopmusic(self, line):
        self.call("stopmusic")

    def c_stopsounds(self, line):
        self.call("stopsounds")

    def c_volume(self, line):
        self.call("volume", self.val(line.parts[1]))

    def c_get(self, line):
        self.store(ast.Name(str(line.parts[2])), ast.Call(func=ast.Name("__fetch__"), args=[self.val(line.parts[1])],
                                                          keywords=[]))

    def c_save(self, line):
        self.call("save", self.object_name(line.parts[1]), self.value_from(line.parts[2:]))

    def c_load(self, line):
        default = self.value_from(line.parts[3:]) if len(line.parts) > 3 else ast.Constant(0)
        self.store(self.target(str(line.parts[2])), self.builtin("load", self.object_name(line.parts[1]), default))

    def c_forget(self, line):
        self.call("forget", self.object_name(line.parts[1]))

    # ----- facts about expressions ----------------------------------------------------------------------------
    def is_text(self, node):
        if isinstance(node, ast.Constant):
            return isinstance(node.value, str)
        if isinstance(node, ast.JoinedStr):
            return True
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self.is_text(node.left) or self.is_text(node.right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return node.func.id in TEXT_FUNCTIONS and node.func.id not in self.functions
        if isinstance(node, ast.Name):
            return self.kinds.get(node.id) == "text"
        return False

    def plain_text(self, node):
        """True when a value is surely text already (so it needs no G.str around it in a template)."""
        if isinstance(node, ast.Constant):
            return isinstance(node.value, str)
        if isinstance(node, ast.JoinedStr):
            return True
        return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in TEXT_FUNCTIONS \
            and node.func.id not in self.functions

    def single_value(self, node):
        """the value of a template that is only {value}, or None."""
        if isinstance(node, ast.JoinedStr) and len(node.values) == 1 and isinstance(node.values[0], ast.FormattedValue):
            return node.values[0].value
        return None

    @staticmethod
    def nonzero(node):
        """True when a divisor is a number that can never be zero, so the division needs no check."""
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            node = node.operand
        return (isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
                and not isinstance(node.value, bool) and node.value != 0)

    def is_number(self, node):
        if isinstance(node, ast.Constant):
            return isinstance(node.value, (int, float)) and not isinstance(node.value, bool)
        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Add):
                return self.is_number(node.left) and self.is_number(node.right)
            return not isinstance(node.op, ast.Mult) or (self.is_number(node.left) and self.is_number(node.right))
        if isinstance(node, ast.UnaryOp):
            return isinstance(node.op, (ast.USub, ast.UAdd, ast.Invert))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return node.func.id in NUMBER_FUNCTIONS and node.func.id not in self.functions
        if isinstance(node, ast.Name):
            return node.id in ("dt", "screen_width", "screen_height", "pi")
        return False

    def is_list(self, node):
        if isinstance(node, (ast.List, ast.ListComp)):
            return True
        if isinstance(node, ast.Name):
            return self.kinds.get(node.id) == "list"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return node.func.id in LIST_FUNCTIONS and node.func.id not in self.functions
        return False

    def is_vector(self, node):
        if isinstance(node, ast.Name):
            return self.kinds.get(node.id) == "vector"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return node.func.id in ("vec2", "vec3") and node.func.id not in self.functions
        if isinstance(node, ast.BinOp):
            return self.is_vector(node.left) or self.is_vector(node.right)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return self.is_vector(node.operand)
        return False

    def is_boolean(self, node):
        if isinstance(node, ast.Compare):
            return True
        if isinstance(node, ast.Constant):
            return isinstance(node.value, bool)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return True
        if isinstance(node, ast.BoolOp):
            return all(self.is_boolean(value) for value in node.values)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return node.func.id in BOOLEAN_FUNCTIONS and node.func.id not in self.functions
        return False

    def is_literal(self, node):
        return isinstance(node, ast.Constant) or isinstance(node, ast.JoinedStr)

    # ----- assigned names per function (python needs them for 'global') --------------------------------------
    def stored_in(self, nodes):
        names = []
        for line in _walk(nodes):
            for name in _stored_names(line):
                if name not in names and name not in self.buttons:
                    names.append(name)
        return names


# ----- expressions shared by the printers --------------------------------------------------------------------------
_BIN = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**",
        ast.BitAnd: "&", ast.BitOr: "|", ast.BitXor: "^", ast.LShift: "<<", ast.RShift: ">>"}
_CMP = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}

_PY_RESERVED = set(keyword.kwlist) | {"G", "main", "print", "int", "range", "len", "str", "Exception", "list", "dict",
                                       "math"}
_JS_RESERVED = {
    "break", "case", "catch", "class", "const", "continue", "debugger", "default", "delete", "do", "else", "enum",
    "export", "extends", "false", "finally", "for", "function", "if", "import", "in", "instanceof", "new", "null",
    "return", "super", "switch", "this", "throw", "true", "try", "typeof", "var", "void", "while", "with", "yield",
    "let", "static", "implements", "interface", "package", "private", "protected", "public", "await", "async",
    "arguments", "eval", "undefined", "NaN", "Infinity", "G", "main", "console", "Math", "Object", "Number",
    "String", "Array", "JSON", "document", "window", "Promise", "Error", "Symbol", "Map", "Set", "of", "require",
    "module", "globalThis",
}
_LUA_RESERVED = {
    "and", "break", "do", "else", "elseif", "end", "false", "for", "function", "goto", "if", "in", "local", "nil",
    "not", "or", "repeat", "return", "then", "true", "until", "while", "G", "main", "print", "error", "type",
    "table", "string", "math", "os", "io", "pairs", "ipairs", "select", "tostring", "tonumber", "require", "love",
    "coroutine", "pcall", "xpcall", "next", "unpack", "setmetatable", "getmetatable", "rawget", "rawset",
    "rawequal", "bit", "arg", "self", "_G", "_ENV", "assert", "load", "loadstring", "dofile", "collectgarbage",
    "module", "package", "jit",
}


class _Python(_Writer):
    LANGUAGE = "python"
    COMMENT = "#"
    RESERVED = _PY_RESERVED
    PREC = {"lambda": 1, "if": 2, "or": 3, "and": 4, "not": 5, "cmp": 6, "|": 7, "^": 8, "&": 9, "<<": 10,
            ">>": 10, "+": 11, "-": 11, "*": 12, "/": 12, "//": 12, "%": 12, "unary": 13, "**": 14, "call": 16,
            "atom": 17}

    def __init__(self, entries, name):
        super().__init__(entries, name)
        self.main_file = name + ".py"
        self.quote = '"'
        self.opened = []

    def ident(self, name):
        name = str(name)
        return name + "_" if name in _PY_RESERVED else name

    # ----- printing expressions -------------------------------------------------------------------------------
    def expr(self, node):
        return self.x(node)[0]

    def wrap(self, node, least):
        code, prec = self.x(node)
        return f"({code})" if prec < least else code

    def runtime_field(self, table, key):
        return f"G.{table}[{self.string(key)}]"

    def string(self, text):
        quote = self.quote
        body = json.dumps(text, ensure_ascii=False)[1:-1]
        if quote == "'":
            body = body.replace('\\"', '"').replace("'", "\\'")
        return quote + body + quote

    def x(self, node):
        P = self.PREC
        kind = type(node)
        if kind is ast.Constant:
            value = node.value
            if isinstance(value, str):
                return self.string(value), P["atom"]
            if value is None or isinstance(value, bool):
                return repr(value), P["atom"]
            return repr(value), (P["atom"] if value >= 0 else P["unary"])
        if kind is ast.Name:
            return self.name(node.id), P["atom"]
        if kind is ast.JoinedStr:
            return self.fstring(node), P["atom"]
        if kind is ast.FormattedValue:
            return self.x(self.builtin("str", node.value))
        if kind in (ast.List, ast.Tuple):
            return "[" + ", ".join(self.expr(item) for item in node.elts) + "]", P["atom"]
        if kind is ast.Dict:
            return "{" + ", ".join(f"{self.key(k)}: {self.expr(v)}" for k, v in zip(node.keys, node.values)) + "}", \
                P["atom"]
        if kind is ast.BinOp:
            symbol = _BIN[type(node.op)]
            left, right = node.left, node.right
            if symbol == "+" and self.is_text(left) != self.is_text(right):
                left, right = self.as_text(left), self.as_text(right)
            p = P[symbol]
            if symbol == "**":
                return f"{self.wrap(left, p + 1)} ** {self.wrap(right, P['unary'])}", p
            return f"{self.wrap(left, p)} {symbol} {self.wrap(right, p + 1)}", p
        if kind is ast.UnaryOp:
            if isinstance(node.op, ast.Not):
                return "not " + self.wrap(node.operand, P["not"]), P["not"]
            symbol = {ast.USub: "-", ast.UAdd: "+", ast.Invert: "~"}[type(node.op)]
            return symbol + self.wrap(node.operand, P["unary"]), P["unary"]
        if kind is ast.BoolOp:
            word = "and" if isinstance(node.op, ast.And) else "or"
            return f" {word} ".join(self.wrap(value, P[word] + 1) for value in node.values), P[word]
        if kind is ast.Compare:
            pieces = [self.wrap(node.left, P["cmp"] + 1)]
            for operator, right in zip(node.ops, node.comparators):
                symbol = {ast.In: "in", ast.NotIn: "not in"}.get(type(operator)) or _CMP[type(operator)]
                pieces.append(f"{symbol} {self.wrap(right, P['cmp'] + 1)}")
            return " ".join(pieces), P["cmp"]
        if kind is ast.IfExp:
            return (f"{self.wrap(node.body, P['if'] + 1)} if {self.wrap(node.test, P['if'] + 1)} else "
                    f"{self.wrap(node.orelse, P['if'])}"), P["if"]
        if kind is ast.Lambda:
            names = [arg.arg for arg in node.args.args]
            self.scopes.append(set(names))
            try:
                body = self.wrap(node.body, P["lambda"])
            finally:
                self.scopes.pop()
            return f"lambda {', '.join(self.ident(n) for n in names)}: {body}" if names else f"lambda: {body}", \
                P["lambda"]
        if kind in (ast.ListComp, ast.DictComp):
            return self.comprehension(node), P["atom"]
        if kind is ast.Subscript:
            index = node.slice
            if isinstance(index, ast.Slice):
                inside = ":".join("" if part is None else self.expr(part) for part in (index.lower, index.upper)) + (
                    ":" + self.expr(index.step) if index.step is not None else "")
            else:
                inside = self.expr(index)
            return f"{self.subject(node.value)}[{inside}]", P["call"]
        if kind is ast.Attribute:
            return f"G.field({self.subject_value(node.value)}, {self.string(node.attr)})", P["call"]
        if kind is ast.Call:
            return self.call_code(node), P["call"]
        raise ValueError(f"'{kind.__name__.lower()}' can't be translated")

    def subject(self, node):
        return self.wrap(node, self.PREC["call"])

    def subject_value(self, node):
        """the left side of a.field: a variable, or an object's name."""
        if isinstance(node, ast.Name) and not self.is_variable(node.id) and node.id not in self.functions:
            return self.string(node.id)
        return self.expr(node)

    def key(self, node):
        if isinstance(node, ast.Name) and not self.is_variable(node.id):
            return self.string(node.id)
        return self.expr(node)

    def name(self, name):
        if self.is_variable(name):
            return self.name_code(name)
        if name in self.functions:
            return self.ident(name)
        if name == "true":
            return "True"
        if name == "false":
            return "False"
        if name in ("none", "nil", "null"):
            return "None"
        if name == "pi":
            return "G.pi"
        if name in EXPRESSION_FUNCTIONS:
            return f"G.{name}"
        return self.string(name)  # gublan reads an unknown word as that word

    def fstring(self, node):
        if len(node.values) == 1 and isinstance(node.values[0], ast.FormattedValue):
            value = node.values[0].value
            return self.expr(value if self.plain_text(value) else self.builtin("str", value))
        outer, self.quote = self.quote, ("'" if self.quote == '"' else '"')
        try:
            pieces = []
            for value in node.values:
                if isinstance(value, ast.Constant):
                    text = json.dumps(value.value, ensure_ascii=False)[1:-1]
                    if outer == "'":
                        text = text.replace('\\"', '"').replace("'", "\\'")
                    pieces.append(text.replace("{", "{{").replace("}", "}}"))
                else:
                    inner = value.value if self.plain_text(value.value) else self.builtin("str", value.value)
                    pieces.append("{" + self.expr(inner) + "}")
        finally:
            self.quote = outer
        return f"f{outer}{''.join(pieces)}{outer}"

    def comprehension(self, node):
        names = set()
        for generator in node.generators:
            names.update(target.id for target in ast.walk(generator.target) if isinstance(target, ast.Name))
        self.scopes.append(names)
        try:
            parts = []
            for generator in node.generators:
                parts.append(f"for {self.target_code(generator.target)} in G.each({self.expr(generator.iter)})")
                parts.extend(f"if {self.wrap(test, self.PREC['if'] + 1)}" for test in generator.ifs)
            if isinstance(node, ast.ListComp):
                return f"[{self.expr(node.elt)} {' '.join(parts)}]"
            return f"{{{self.key(node.key)}: {self.expr(node.value)} {' '.join(parts)}}}"
        finally:
            self.scopes.pop()

    def target_code(self, node):
        if isinstance(node, ast.Name):
            return self.ident(node.id)
        return ", ".join(self.target_code(item) for item in node.elts)

    def call_code(self, node):
        func, args = node.func, [self.expr(arg) for arg in node.args]
        if isinstance(func, ast.Name):
            name = func.id
            if name == "__flag__":
                return f"int({args[0]})"
            if name == "__ask__":
                return f"G.ask({args[0]})"
            if name == "__fetch__":
                return f"G.fetch({args[0]})"
            if self.is_variable(name) or name in self.functions:
                return f"{self.name_code(name) if self.is_variable(name) else self.ident(name)}({', '.join(args)})"
            if name in EXPRESSION_FUNCTIONS:
                return f"G.{name}({', '.join(args)})"
            self.notes.add(f"'{name}' is not a gublan function (maybe it came from a plugin). it is left as a call "
                           "to G.missing.")
            return f"G.missing({self.string(name)})({', '.join(args)})"
        if isinstance(func, ast.Attribute):
            method = func.attr
            subject = self.subject_value(func.value)
            if method in self.functions:
                return f"{self.ident(method)}({', '.join([subject] + args)})"
            if method in EXPRESSION_FUNCTIONS:
                return f"G.{method}({', '.join([subject] + args)})"
            return f"G.field({subject}, {self.string(method)})({', '.join(args)})"
        return f"{self.subject(func)}({', '.join(args)})"

    # ----- statements -------------------------------------------------------------------------------------------
    def line_code(self, code):
        self.emit(code)

    def open(self, header):
        self.emit(header + ":")
        self.depth += 1
        self.opened.append(len(self.out))

    def close(self):
        start = self.opened.pop()
        if not any(line.strip() and not line.strip().startswith("#") for line in self.out[start:]):
            self.emit("pass")
        self.depth -= 1

    def middle(self, header):
        self.close()
        self.open(header)

    def store(self, target, value, compound=None):
        code = self.expr(value)
        if isinstance(target, ast.Name):
            name = self.name_code(target.id)
            if compound is not None:
                right = value.right
                if isinstance(compound, ast.Add) and self.is_text(value.left) and not self.is_text(right):
                    right = self.as_text(right)
                self.emit(f"{name} {_BIN[type(compound)]}= {self.expr(right)}")
                return
            self.emit(f"{name} = {code}")
        elif isinstance(target, ast.Attribute):
            self.emit(f"G.set_field({self.subject_value(target.value)}, {self.string(target.attr)}, {code})")
        elif isinstance(target, ast.Subscript):
            self.emit(f"{self.expr(target)} = {code}")
        else:
            raise ValueError("this can't be given a value")

    def append_to(self, target, value):
        self.emit(f"{self.expr(target)}.append({self.expr(value)})")

    def print_text(self, node):
        value = self.single_value(node)
        if value is not None and self.plain_text(value):
            node = value
        self.emit(f"print({self.expr(node)})")

    def throw(self, message):
        self.emit(f"raise G.GublanError({self.expr(message)})")

    def cond(self, node):
        return self.expr(node)

    def header(self):
        for text in self.header_lines():
            self.comment(text)
        self.emit("import gublan_runtime as G")
        self.blank()

    def globals_line(self, nodes, params=()):
        names = [self.ident(name) for name in self.stored_in(nodes) if name not in params
                 and name not in ("dt", "screen_width", "screen_height")]
        if names:
            self.emit("global " + ", ".join(names))

    def function(self, node):
        name = str(node.line.parts[1])
        params = self.functions.get(name, [])
        self.blank()
        self.open(f"def {self.ident(name)}({', '.join(self.ident(p) for p in params)})")
        self.globals_line(node.body, params)
        self.scopes.append(set(params))
        try:
            self.body(node.body)
        finally:
            self.scopes.pop()
        self.close()
        self.blank()

    def test(self, node):
        name = "test_" + _slug(" ".join(str(part) for part in node.line.parts[1:]))
        while name in self.tests:
            name += "_"
        self.tests.append(name)
        self.blank()
        self.open(f"def {name}()")
        self.emit(f'"""{node.line.text}"""')
        self.globals_line(node.body)
        self.body(node.body)
        self.close()
        self.blank()

    def main(self, nodes):
        self.blank()
        self.open("def main()")
        self.globals_line(nodes)
        self.body(nodes)
        self.close()

    def footer(self):
        self.blank()
        self.blank()
        self.open('if __name__ == "__main__"')
        self.emit(f"G.start(main, {self.string(self.program_name)})")
        self.close()

    # blocks
    def b_if(self, node):
        self.open(f"if {self.cond(self.condition(node.line))}")
        self.body(node.body)
        for middle, branch in node.branches:
            if middle.cmd == "elseif":
                self.middle(f"elif {self.cond(self.condition(middle))}")
            else:
                self.middle("else")
            self.body(branch)
        self.close()

    def b_loop(self, node):
        count = self.val(node.line.parts[1])
        whole = isinstance(count, ast.Constant) and isinstance(count.value, int) and not isinstance(count.value, bool)
        self.open(f"for _ in range({self.expr(count)})" if whole else f"for _ in range(int({self.expr(count)}))")
        self.body(node.body)
        self.close()

    def b_forever(self, node):
        self.open("while True")
        self.body(node.body)
        self.close()

    def b_while(self, node):
        self.open(f"while {self.cond(self.condition(node.line))}")
        self.body(node.body)
        self.close()

    def b_until(self, node):
        self.open(f"while not {self.wrap(self.condition(node.line), self.PREC['not'])}")
        self.body(node.body)
        self.close()

    def b_for(self, node):
        line = node.line
        match = _FOR_RANGE_RE.match(line.rest)
        if match:
            name, start, end, step = match.groups()
            start, end = parse_expression(start), parse_expression(end)
            step = parse_expression(step) if step else None
            simple = all(isinstance(n, ast.Constant) and type(n.value) is int for n in (start, end)) and (
                step is None or (isinstance(step, ast.Constant) and type(step.value) is int and step.value > 0))
            if simple:
                stop = end.value + 1
                head = f"range({start.value}, {stop}" + (f", {step.value})" if step is not None else ")")
            else:
                head = f"G.steps({self.expr(start)}, {self.expr(end)}" + (
                    f", {self.expr(step)})" if step is not None else ")")
        else:
            match = _FOR_IN_RE.match(line.rest)
            name = match.group(1)
            head = f"G.each({self.expr(parse_expression(match.group(2)))})"
        self.open(f"for {self.name_code(name)} in {head}")
        self.body(node.body)
        self.close()

    def b_match(self, node):
        temp = self.fresh("_match")
        self.emit(f"{temp} = {self.expr(self.val(node.line.parts[1]) if len(node.line.parts) == 2 else self.expression(node.line.rest))}")
        first = True
        if node.body and any(not isinstance(item, _Comment) and item is not _BLANK for item in node.body):
            self.todo(node.line, "lines between match and the first case are skipped")
        for middle, branch in node.branches:
            if middle.cmd == "case":
                values = [self.eval_value(part, split_command(part)) for part in _split_top_level_commas(middle.rest)]
                test = " or ".join(f"{temp} == {self.wrap(value, self.PREC['cmp'] + 1)}" for value in values)
                if first:
                    self.open(f"if {test}")
                else:
                    self.middle(f"elif {test}")
            else:
                if first:
                    self.open("if True")
                else:
                    self.middle("else")
            first = False
            self.body(branch)
        if not first:
            self.close()

    def b_try(self, node):
        self.open("try")
        self.body(node.body)
        catches = [(middle, branch) for middle, branch in node.branches if middle.cmd == "catch"]
        if catches:
            middle, branch = catches[0]
            name = str(middle.parts[1]) if len(middle.parts) > 1 else "error"
            self.middle("except Exception as problem_")
            self.emit(f"{self.name_code(name)} = G.message(problem_)")
            self.body(branch)
        else:
            self.middle("except Exception")
        self.close()

    def c_break(self, line):
        self.emit("break")

    def c_continue(self, line):
        self.emit("continue")

    def c_return(self, line):
        if len(line.parts) > 1:
            self.emit(f"return {self.expr(self.eval_value(line.rest, line.parts[1:]))}")
        else:
            self.emit("return")


class _JavaScript(_Writer):
    LANGUAGE = "javascript"
    COMMENT = "//"
    RESERVED = _JS_RESERVED
    PREC = {"arrow": 1, "?": 2, "||": 3, "&&": 4, "|": 5, "^": 6, "&": 7, "==": 8, "cmp": 9, "<<": 10, ">>": 10,
            "+": 11, "-": 11, "*": 12, "/": 12, "%": 12, "**": 13, "unary": 14, "call": 17, "atom": 18}

    def __init__(self, entries, name):
        super().__init__(entries, name)
        self.main_file = name + ".js"
        self.awaited = False
        self.waiting = self._waiting_functions()
        self.in_function = None

    def _waiting_functions(self):
        """functions that have to be awaited: they wait for the screen, or call one that does."""
        waiting = set()
        changed = True
        while changed:
            changed = False
            for name, body in self.function_bodies.items():
                if name in waiting:
                    continue
                for line in _walk(body):
                    if line.cmd in JS_WAITS or any(re.search(rf"\b{re.escape(other)}\b", line.text)
                                                   for other in waiting):
                        waiting.add(name)
                        changed = True
                        break
        return waiting

    def runtime_field(self, table, key):
        return f"G.{table}[{json.dumps(key)}]"

    def runtime_call(self, function, args):
        code = f"G.{function}({', '.join(self.expr(arg) for arg in args)})"
        return ("await " + code) if function in JS_WAITS | {"ask", "fetch"} else code

    # ----- expressions ------------------------------------------------------------------------------------------
    def expr(self, node):
        return self.x(node)[0]

    def wrap(self, node, least):
        code, prec = self.x(node)
        return f"({code})" if prec < least else code

    @staticmethod
    def string(text):
        return json.dumps(text, ensure_ascii=False)

    def truthy(self, node):
        if self.is_boolean(node):
            if isinstance(node, ast.BoolOp):
                word = "&&" if isinstance(node.op, ast.And) else "||"
                return f" {word} ".join(self.wrap_code(self.truthy(v), v, self.PREC[word] + 1) for v in node.values)
            return self.expr(node)
        if isinstance(node, ast.BoolOp):
            word = "&&" if isinstance(node.op, ast.And) else "||"
            return f" {word} ".join(self.wrap_code(self.truthy(v), v, self.PREC[word] + 1) for v in node.values)
        return f"G.truthy({self.expr(node)})"

    def wrap_code(self, code, node, least):
        if code.startswith("G.truthy("):
            return code
        prec = self.x(node)[1]
        return f"({code})" if prec < least else code

    def x(self, node):
        P = self.PREC
        kind = type(node)
        if kind is ast.Constant:
            value = node.value
            if isinstance(value, str):
                return self.string(value), P["atom"]
            if value is None:
                return "null", P["atom"]
            if isinstance(value, bool):
                return ("true" if value else "false"), P["atom"]
            return repr(value), (P["atom"] if value >= 0 else P["unary"])
        if kind is ast.Name:
            return self.name(node.id), P["atom"]
        if kind is ast.JoinedStr:
            if len(node.values) == 1 and isinstance(node.values[0], ast.FormattedValue):
                value = node.values[0].value
                return (self.x(value) if self.plain_text(value) else (f"G.str({self.expr(value)})", P["call"]))
            pieces = []
            for value in node.values:
                if isinstance(value, ast.Constant):
                    pieces.append(value.value.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${"))
                elif self.plain_text(value.value):
                    pieces.append("${" + self.expr(value.value) + "}")
                else:
                    pieces.append("${G.str(" + self.expr(value.value) + ")}")
            return "`" + "".join(pieces) + "`", P["atom"]
        if kind in (ast.List, ast.Tuple):
            return "[" + ", ".join(self.expr(item) for item in node.elts) + "]", P["atom"]
        if kind is ast.Dict:
            items = []
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    items.append(f"{self.string(key.value)}: {self.expr(value)}")
                elif isinstance(key, ast.Name) and not self.is_variable(key.id):
                    items.append(f"{self.string(key.id)}: {self.expr(value)}")
                else:
                    items.append(f"[{self.expr(key)}]: {self.expr(value)}")
            return "{" + ", ".join(items) + "}", P["atom"]
        if kind is ast.BinOp:
            symbol = _BIN[type(node.op)]
            left, right = node.left, node.right
            if symbol in ("+", "-", "*", "/") and (self.is_vector(left) or self.is_vector(right)):
                function = {"+": "add", "-": "sub", "*": "mul", "/": "div"}[symbol]
                return f"G.{function}({self.expr(left)}, {self.expr(right)})", P["call"]
            if symbol == "+" and (self.is_list(left) or self.is_list(right)):
                return f"G.add({self.expr(left)}, {self.expr(right)})", P["call"]
            if symbol == "*" and any(self.is_text(side) or self.is_list(side) for side in (left, right)):
                return f"G.mul({self.expr(left)}, {self.expr(right)})", P["call"]
            if symbol in ("/", "//") and not self.nonzero(right):
                function = "div" if symbol == "/" else "idiv"
                return f"G.{function}({self.expr(left)}, {self.expr(right)})", P["call"]
            if symbol == "//":
                return f"Math.floor({self.expr(left)} / {self.wrap(right, P['/'] + 1)})", P["call"]
            if symbol == "%":
                return f"G.mod({self.expr(left)}, {self.expr(right)})", P["call"]
            p = P[symbol]
            if symbol == "**":
                return f"{self.wrap(left, P['unary'] + 1)} ** {self.wrap(right, p)}", p
            return f"{self.wrap(left, p)} {symbol} {self.wrap(right, p + 1)}", p
        if kind is ast.UnaryOp:
            if isinstance(node.op, ast.Not):
                if self.is_boolean(node.operand):
                    return "!" + self.wrap(node.operand, P["unary"]), P["unary"]
                return f"!G.truthy({self.expr(node.operand)})", P["unary"]
            symbol = {ast.USub: "-", ast.UAdd: "+", ast.Invert: "~"}[type(node.op)]
            if symbol == "-" and self.is_vector(node.operand):
                return f"G.sub(0, {self.expr(node.operand)})", P["call"]
            inner = self.wrap(node.operand, P["unary"])
            return symbol + (" " + inner if inner.startswith(symbol) else inner), P["unary"]
        if kind is ast.BoolOp:
            word = "&&" if isinstance(node.op, ast.And) else "||"
            return f" {word} ".join(self.wrap(value, P[word] + 1) for value in node.values), P[word]
        if kind is ast.Compare:
            pieces = []
            left = node.left
            for operator, right in zip(node.ops, node.comparators):
                pieces.append(self.compare(left, operator, right))
                left = right
            if len(pieces) == 1:
                return pieces[0]
            return " && ".join(code if prec > P["&&"] else f"({code})" for code, prec in pieces), P["&&"]
        if kind is ast.IfExp:
            test = self.truthy(node.test)
            if " " in test and not test.startswith("G.truthy("):
                test = f"({test})"
            return f"{test} ? {self.wrap(node.body, P['?'] + 1)} : {self.wrap(node.orelse, P['?'])}", P["?"]
        if kind is ast.Lambda:
            names = [arg.arg for arg in node.args.args]
            self.scopes.append(set(names))
            before, self.awaited = self.awaited, False
            try:
                body = self.wrap(node.body, P["?"])
                if body.startswith("{"):
                    body = f"({body})"
                waits = self.awaited
            finally:
                self.scopes.pop()
                self.awaited = before or self.awaited
            if waits:
                self.notes.add("a little function calls something that waits for the screen, so it gives back a "
                               "promise in javascript.")
            return f"{'async ' if waits else ''}({', '.join(self.ident(n) for n in names)}) => {body}", P["arrow"]
        if kind is ast.ListComp:
            return self.comprehension(node.generators, lambda: self.expr(node.elt)), P["call"]
        if kind is ast.DictComp:
            code = self.comprehension(node.generators, lambda: f"[{self.key(node.key)}, {self.expr(node.value)}]")
            return f"Object.fromEntries({code})", P["call"]
        if kind is ast.Subscript:
            index = node.slice
            if isinstance(index, ast.Slice):
                args = [self.expr(node.value)] + ["null" if part is None else self.expr(part)
                                                  for part in (index.lower, index.upper)]
                return f"G.slice({', '.join(args)})", P["call"]
            # G.at counts from the end for negative numbers and stops with a message when nothing is there
            return f"G.at({self.expr(node.value)}, {self.expr(index)})", P["call"]
        if kind is ast.Attribute:
            return f"G.field({self.subject_value(node.value)}, {self.string(node.attr)})", P["call"]
        if kind is ast.Call:
            code, waits = self.call_code(node)
            if waits:
                self.awaited = True
            return (f"await {code}", P["unary"]) if waits else (code, P["call"])
        raise ValueError(f"'{kind.__name__.lower()}' can't be translated")

    def compare(self, left, operator, right):
        P = self.PREC
        if isinstance(operator, (ast.In, ast.NotIn)):
            code = f"G.contains({self.expr(right)}, {self.expr(left)})"
            return (code, P["call"]) if isinstance(operator, ast.In) else ("!" + code, P["unary"])
        if isinstance(operator, (ast.Eq, ast.NotEq)):
            simple = any(isinstance(side, ast.Constant) or self.is_number(side) for side in (left, right))
            if not simple:
                code = f"G.eq({self.expr(left)}, {self.expr(right)})"
                return (code, P["call"]) if isinstance(operator, ast.Eq) else ("!" + code, P["unary"])
            symbol = "===" if isinstance(operator, ast.Eq) else "!=="
            return f"{self.wrap(left, P['==']+1)} {symbol} {self.wrap(right, P['==']+1)}", P["=="]
        symbol = _CMP[type(operator)]
        return f"{self.wrap(left, P['cmp'] + 1)} {symbol} {self.wrap(right, P['cmp'] + 1)}", P["cmp"]

    def comprehension(self, generators, element):
        names = set()
        for generator in generators:
            names.update(t.id for t in ast.walk(generator.target) if isinstance(t, ast.Name))
        self.scopes.append(names)
        try:
            def level(index):
                generator = generators[index]
                param = self.param(generator.target)
                code = f"G.each({self.expr(generator.iter)})"
                for test in generator.ifs:
                    code += f".filter(({param}) => {self.truthy(test)})"
                if index == len(generators) - 1:
                    return code + f".map(({param}) => {element()})"
                return code + f".flatMap(({param}) => {level(index + 1)})"
            return level(0)
        finally:
            self.scopes.pop()

    def param(self, target):
        if isinstance(target, ast.Name):
            return self.ident(target.id)
        return "[" + ", ".join(self.param(item) for item in target.elts) + "]"

    def subject_value(self, node):
        if isinstance(node, ast.Name) and not self.is_variable(node.id) and node.id not in self.functions:
            return self.string(node.id)
        return self.expr(node)

    def key(self, node):
        if isinstance(node, ast.Name) and not self.is_variable(node.id):
            return self.string(node.id)
        return self.expr(node)

    def name(self, name):
        if self.is_variable(name):
            return self.name_code(name)
        if name in self.functions:
            return self.ident(name)
        if name == "true":
            return "true"
        if name == "false":
            return "false"
        if name in ("none", "nil", "null"):
            return "null"
        if name == "pi":
            return "Math.PI"
        if name in EXPRESSION_FUNCTIONS:
            return f"G.{name}"
        return self.string(name)

    def call_code(self, node):
        """(code, has to be awaited)"""
        func, args = node.func, [self.expr(arg) for arg in node.args]
        if isinstance(func, ast.Name):
            name = func.id
            if name == "__flag__":
                return f"({args[0]} ? 1 : 0)", False
            if name == "__ask__":
                return f"G.ask({args[0]})", True
            if name == "__fetch__":
                return f"G.fetch({args[0]})", True
            if self.is_variable(name):
                return f"{self.name_code(name)}({', '.join(args)})", False
            if name in self.functions:
                return f"{self.ident(name)}({', '.join(args)})", name in self.waiting
            if name in EXPRESSION_FUNCTIONS:
                return f"G.{name}({', '.join(args)})", False
            self.notes.add(f"'{name}' is not a gublan function (maybe it came from a plugin). it is left as a call "
                           "to G.missing.")
            return f"G.missing({self.string(name)})({', '.join(args)})", False
        if isinstance(func, ast.Attribute):
            method = func.attr
            subject = self.subject_value(func.value)
            if method in self.functions:
                return f"{self.ident(method)}({', '.join([subject] + args)})", method in self.waiting
            if method in EXPRESSION_FUNCTIONS:
                return f"G.{method}({', '.join([subject] + args)})", False
            return f"G.field({subject}, {self.string(method)})({', '.join(args)})", False
        return f"{self.wrap(func, self.PREC['call'])}({', '.join(args)})", False

    # ----- statements -------------------------------------------------------------------------------------------
    def line_code(self, code):
        self.emit(code + ";")

    def open(self, header):
        self.emit(header + " {")
        self.depth += 1

    def close(self):
        self.depth -= 1
        self.emit("}")

    def middle(self, header):
        self.depth -= 1
        self.emit("} " + header + " {")
        self.depth += 1

    def store(self, target, value, compound=None):
        code = self.expr(value)
        if isinstance(target, ast.Name):
            name = self.name_code(target.id)
            if compound is not None and not code.startswith(("G.", "Math.", "await ")):
                self.emit(f"{name} {_BIN[type(compound)]}= {self.expr(value.right)};")
                return
            self.emit(f"{name} = {code};")
        elif isinstance(target, ast.Attribute):
            self.emit(f"G.set_field({self.subject_value(target.value)}, {self.string(target.attr)}, {code});")
        elif isinstance(target, ast.Subscript):
            if isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
                self.emit(f"{self.wrap(target.value, self.PREC['call'])}[{self.expr(target.slice)}] = {code};")
            else:
                self.emit(f"G.put({self.expr(target.value)}, {self.expr(target.slice)}, {code});")
        else:
            raise ValueError("this can't be given a value")

    def append_to(self, target, value):
        self.emit(f"{self.expr(target)}.push({self.expr(value)});")

    def print_text(self, node):
        value = self.single_value(node)
        self.emit(f"G.print({self.expr(node if value is None else value)});")

    def throw(self, message):
        self.emit(f"throw new G.GublanError({self.expr(message)});")

    def cond(self, node):
        return self.truthy(node)

    def header(self):
        for text in self.header_lines():
            self.comment(text)
        self.emit('const G = globalThis.G || require("./gublan_runtime.js");')
        names = sorted(self.ident(name) for name in self.variables
                       if name not in ("dt", "screen_width", "screen_height"))
        if names:
            self.blank()
            self.comment("gublan variables can be used anywhere in the program")
            line = "let "
            for index, name in enumerate(names):
                piece = name + (", " if index < len(names) - 1 else ";")
                if len(line) + len(piece) > 110:
                    self.emit(line.rstrip())
                    line = "    "
                line += piece
            self.emit(line)
        self.blank()

    def function(self, node):
        name = str(node.line.parts[1])
        params = self.functions.get(name, [])
        self.blank()
        prefix = "async " if name in self.waiting else ""
        self.open(f"{prefix}function {self.ident(name)}({', '.join(self.ident(p) for p in params)})")
        self.scopes.append(set(params))
        try:
            self.body(node.body)
        finally:
            self.scopes.pop()
        self.close()
        self.blank()

    def test(self, node):
        name = "test_" + _slug(" ".join(str(part) for part in node.line.parts[1:]))
        while name in self.tests:
            name += "_"
        self.tests.append(name)
        self.blank()
        self.comment(node.line.text)
        self.open(f"async function {name}()")
        self.body(node.body)
        self.close()
        self.blank()

    def main(self, nodes):
        self.blank()
        self.open("async function main()")
        self.body(nodes)
        self.close()

    def footer(self):
        self.blank()
        if self.tests:
            self.emit(f"G.tests = {{{', '.join(f'{self.string(n)}: {n}' for n in self.tests)}}};")
        self.emit(f"G.start(main, {self.string(self.program_name)});")

    def b_if(self, node):
        self.open(f"if ({self.cond(self.condition(node.line))})")
        self.body(node.body)
        for middle, branch in node.branches:
            if middle.cmd == "elseif":
                self.middle(f"else if ({self.cond(self.condition(middle))})")
            else:
                self.middle("else")
            self.body(branch)
        self.close()

    def b_loop(self, node):
        counter = self.fresh("_n")
        self.open(f"for (let {counter} = 0; {counter} < {self.wrap(self.val(node.line.parts[1]), self.PREC['cmp'] + 1)}; {counter}++)")
        self.body(node.body)
        self.close()

    def b_forever(self, node):
        self.open("while (true)")
        self.body(node.body)
        self.close()

    def b_while(self, node):
        self.open(f"while ({self.cond(self.condition(node.line))})")
        self.body(node.body)
        self.close()

    def b_until(self, node):
        test = self.cond(self.condition(node.line))
        self.open(f"while (!({test}))" if not test.startswith("G.") else f"while (!{test})")
        self.body(node.body)
        self.close()

    def b_for(self, node):
        line = node.line
        match = _FOR_RANGE_RE.match(line.rest)
        if match:
            name, start, end, step = match.groups()
            start, end = parse_expression(start), parse_expression(end)
            step = parse_expression(step) if step else None
            variable = self.name_code(name)
            positive = step is None or (isinstance(step, ast.Constant) and isinstance(step.value, (int, float))
                                        and step.value > 0)
            negative = isinstance(step, ast.UnaryOp) and isinstance(step.op, ast.USub) and \
                isinstance(step.operand, ast.Constant)
            if positive or negative:
                change = f"{variable}++" if step is None or (isinstance(step, ast.Constant) and step.value == 1) \
                    else f"{variable} += {self.expr(step)}" if positive else f"{variable} -= {self.expr(step.operand)}"
                last = self.expr(end)
                if not isinstance(end, (ast.Constant, ast.Name)):
                    temp = self.fresh("_last")
                    self.emit(f"const {temp} = {last};")
                    last = temp
                self.open(f"for ({variable} = {self.expr(start)}; {variable} {'<=' if positive else '>='} {last}; "
                          f"{change})")
            else:
                self.open(f"for ({variable} of G.steps({self.expr(start)}, {self.expr(end)}, {self.expr(step)}))")
        else:
            match = _FOR_IN_RE.match(line.rest)
            self.open(f"for ({self.name_code(match.group(1))} of G.each({self.expr(parse_expression(match.group(2)))}))")
        self.body(node.body)
        self.close()

    def b_match(self, node):
        temp = self.fresh("_match")
        value = self.val(node.line.parts[1]) if len(node.line.parts) == 2 else self.expression(node.line.rest)
        self.emit(f"const {temp} = {self.expr(value)};")
        if node.body and any(not isinstance(item, _Comment) and item is not _BLANK for item in node.body):
            self.todo(node.line, "lines between match and the first case are skipped")
        first = True
        for middle, branch in node.branches:
            if middle.cmd == "case":
                values = [self.eval_value(part, split_command(part)) for part in _split_top_level_commas(middle.rest)]
                test = " || ".join(f"G.eq({temp}, {self.expr(value)})" for value in values)
                self.open(f"if ({test})") if first else self.middle(f"else if ({test})")
            else:
                self.open("if (true)") if first else self.middle("else")
            first = False
            self.body(branch)
        if not first:
            self.close()

    def b_try(self, node):
        self.open("try")
        self.body(node.body)
        problem = self.fresh("_problem")
        catches = [(middle, branch) for middle, branch in node.branches if middle.cmd == "catch"]
        self.middle(f"catch ({problem})")
        if catches:
            middle, branch = catches[0]
            name = str(middle.parts[1]) if len(middle.parts) > 1 else "error"
            self.emit(f"{self.name_code(name)} = G.message({problem});")
            self.body(branch)
        else:
            self.emit(f"G.message({problem});")
        self.close()

    def c_break(self, line):
        self.emit("break;")

    def c_continue(self, line):
        self.emit("continue;")

    def c_return(self, line):
        if len(line.parts) > 1:
            self.emit(f"return {self.expr(self.eval_value(line.rest, line.parts[1:]))};")
        else:
            self.emit("return;")


class _Lua(_Writer):
    LANGUAGE = "lua"
    COMMENT = "--"
    RESERVED = _LUA_RESERVED
    PREC = {"or": 1, "and": 2, "cmp": 3, "..": 5, "+": 6, "-": 6, "*": 7, "/": 7, "%": 7, "unary": 8, "^": 10,
            "call": 11, "atom": 12}

    def __init__(self, entries, name):
        super().__init__(entries, name)
        self.main_file = "main.lua"
        self.context = []  # what we are inside: ["loop", label] / ["try", flags] / ["function"]

    def runtime_field(self, table, key):
        return f"G.{table}[{self.string(key)}]" if not re.fullmatch(r"[A-Za-z_]\w*", key) or key in _LUA_RESERVED \
            else f"G.{table}.{key}"

    # ----- expressions ------------------------------------------------------------------------------------------
    def expr(self, node):
        return self.x(node)[0]

    def wrap(self, node, least):
        code, prec = self.x(node)
        return f"({code})" if prec < least else code

    @staticmethod
    def string(text):
        out = []
        for char in text:
            if char == "\\":
                out.append("\\\\")
            elif char == '"':
                out.append('\\"')
            elif char == "\n":
                out.append("\\n")
            elif char == "\r":
                out.append("\\r")
            elif char == "\t":
                out.append("\\t")
            elif ord(char) < 32:
                out.append(f"\\{ord(char):03d}")
            else:
                out.append(char)
        return '"' + "".join(out) + '"'

    def truthy(self, node):
        if isinstance(node, ast.BoolOp):
            word = "and" if isinstance(node.op, ast.And) else "or"
            pieces = []
            for value in node.values:
                code = self.truthy(value)
                pieces.append(code if code.startswith("G.") or self.x(value)[1] > self.PREC[word] or
                              not self.is_boolean(value) else f"({code})")
            return f" {word} ".join(pieces)
        if self.is_boolean(node):
            return self.expr(node)
        return f"G.truthy({self.expr(node)})"

    def x(self, node):
        P = self.PREC
        kind = type(node)
        if kind is ast.Constant:
            value = node.value
            if isinstance(value, str):
                return self.string(value), P["atom"]
            if value is None:
                return "nil", P["atom"]
            if isinstance(value, bool):
                return ("true" if value else "false"), P["atom"]
            return repr(value), (P["atom"] if value >= 0 else P["unary"])
        if kind is ast.Name:
            return self.name(node.id), P["atom"]
        if kind is ast.JoinedStr:
            if len(node.values) == 1 and isinstance(node.values[0], ast.FormattedValue):
                value = node.values[0].value
                return (self.x(value) if self.plain_text(value) else (f"G.str({self.expr(value)})", P["call"]))
            pieces = [self.string(value.value) if isinstance(value, ast.Constant) else
                      self.wrap(value.value, P[".."] + 1) if self.plain_text(value.value) else
                      f"G.str({self.expr(value.value)})" for value in node.values]
            return " .. ".join(pieces), P[".."]
        if kind in (ast.List, ast.Tuple):
            return "{" + ", ".join(self.expr(item) for item in node.elts) + "}", P["atom"]
        if kind is ast.Dict:
            # G.dict(key, value, key, value...) keeps the keys in order, like gublan maps
            items = []
            for key, value in zip(node.keys, node.values):
                items.append(f"{self.key(key)}, {self.expr(value)}")
            return "G.dict(" + ", ".join(items) + ")", P["call"]
        if kind is ast.BinOp:
            symbol = _BIN[type(node.op)]
            left, right = node.left, node.right
            if symbol == "+":
                if self.is_text(left) or self.is_text(right):
                    return (f"{self.text_piece(left)} .. {self.text_piece(right)}"), P[".."]
                if self.is_list(left) or self.is_list(right):
                    return f"G.add({self.expr(left)}, {self.expr(right)})", P["call"]
            if symbol == "*" and any(self.is_text(side) or self.is_list(side) for side in (left, right)):
                return f"G.mul({self.expr(left)}, {self.expr(right)})", P["call"]
            if symbol in ("/", "//", "%") and not self.nonzero(right):
                function = {"/": "div", "//": "idiv", "%": "mod"}[symbol]
                return f"G.{function}({self.expr(left)}, {self.expr(right)})", P["call"]
            if symbol == "//":
                return f"math.floor({self.expr(left)} / {self.wrap(right, P['/'] + 1)})", P["call"]
            if symbol in ("&", "|", "^", "<<", ">>"):
                function = {"&": "band", "|": "bor", "^": "bxor", "<<": "shl", ">>": "shr"}[symbol]
                return f"G.{function}({self.expr(left)}, {self.expr(right)})", P["call"]
            if symbol == "**":
                return f"{self.wrap(left, P['^'] + 1)} ^ {self.wrap(right, P['unary'])}", P["^"]
            p = P[symbol]
            return f"{self.wrap(left, p)} {symbol} {self.wrap(right, p + 1)}", p
        if kind is ast.UnaryOp:
            if isinstance(node.op, ast.Not):
                if self.is_boolean(node.operand):
                    return "not " + self.wrap(node.operand, P["unary"]), P["unary"]
                return f"not G.truthy({self.expr(node.operand)})", P["unary"]
            if isinstance(node.op, ast.Invert):
                return f"G.bnot({self.expr(node.operand)})", P["call"]
            inner = self.wrap(node.operand, P["unary"])
            if isinstance(node.op, ast.UAdd):
                return inner, P["unary"]
            return "-" + (f"({inner})" if inner.startswith("-") else inner), P["unary"]
        if kind is ast.BoolOp:
            word = "and" if isinstance(node.op, ast.And) else "or"
            return f" {word} ".join(self.wrap(value, P[word] + 1) for value in node.values), P[word]
        if kind is ast.Compare:
            pieces = []
            left = node.left
            for operator, right in zip(node.ops, node.comparators):
                pieces.append(self.compare(left, operator, right))
                left = right
            if len(pieces) == 1:
                return pieces[0]
            return " and ".join(code if prec > P["and"] else f"({code})" for code, prec in pieces), P["and"]
        if kind is ast.IfExp:
            return (f"G.pick({self.truthy(node.test)}, function() return {self.expr(node.body)} end, "
                    f"function() return {self.expr(node.orelse)} end)"), P["call"]
        if kind is ast.Lambda:
            names = [arg.arg for arg in node.args.args]
            self.scopes.append(set(names))
            try:
                body = self.expr(node.body)
            finally:
                self.scopes.pop()
            return f"function({', '.join(self.ident(n) for n in names)}) return {body} end", P["atom"]
        if kind is ast.ListComp:
            return self.comprehension(node.generators, lambda: self.expr(node.elt), "G.comp"), P["call"]
        if kind is ast.DictComp:
            return self.comprehension(node.generators, lambda: f"{self.key(node.key)}, {self.expr(node.value)}",
                                      "G.dcomp"), P["call"]
        if kind is ast.Subscript:
            index = node.slice
            if isinstance(index, ast.Slice):
                args = [self.expr(node.value)] + ["nil" if part is None else self.expr(part)
                                                  for part in (index.lower, index.upper)]
                return f"G.slice({', '.join(args)})", P["call"]
            return f"G.at({self.expr(node.value)}, {self.expr(index)})", P["call"]
        if kind is ast.Attribute:
            return f"G.field({self.subject_value(node.value)}, {self.string(node.attr)})", P["call"]
        if kind is ast.Call:
            return self.call_code(node), P["call"]
        raise ValueError(f"'{kind.__name__.lower()}' can't be translated")

    def text_piece(self, node):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) and (self.is_text(node.left)
                                                                             or self.is_text(node.right)):
            return self.expr(node)
        if self.is_text(node) and not isinstance(node, ast.Name):
            return self.wrap(node, self.PREC[".."] + 1)
        return f"G.str({self.expr(node)})"

    def compare(self, left, operator, right):
        P = self.PREC
        if isinstance(operator, (ast.In, ast.NotIn)):
            code = f"G.contains({self.expr(right)}, {self.expr(left)})"
            return (code, P["call"]) if isinstance(operator, ast.In) else ("not " + code, P["unary"])
        if isinstance(operator, (ast.Eq, ast.NotEq)):
            simple = any(isinstance(side, ast.Constant) or self.is_number(side) for side in (left, right))
            if not simple:
                code = f"G.eq({self.expr(left)}, {self.expr(right)})"
                return (code, P["call"]) if isinstance(operator, ast.Eq) else ("not " + code, P["unary"])
            symbol = "==" if isinstance(operator, ast.Eq) else "~="
            return f"{self.wrap(left, P['cmp'] + 1)} {symbol} {self.wrap(right, P['cmp'] + 1)}", P["cmp"]
        symbol = _CMP[type(operator)]
        return f"{self.wrap(left, P['cmp'] + 1)} {symbol} {self.wrap(right, P['cmp'] + 1)}", P["cmp"]

    def comprehension(self, generators, element, helper):
        names = set()
        for generator in generators:
            names.update(t.id for t in ast.walk(generator.target) if isinstance(t, ast.Name))
        self.scopes.append(names)
        try:
            def level(index):
                generator = generators[index]
                param, unpack = self.param(generator.target)
                tests = " and ".join(self.truthy(test) for test in generator.ifs)
                keep = f", function({param}) {unpack}return {tests} end" if tests else ""
                if index == len(generators) - 1:
                    return f"{helper}(G.each({self.expr(generator.iter)}), function({param}) {unpack}return " \
                           f"{element()} end{keep})"
                return f"G.flat(G.comp(G.each({self.expr(generator.iter)}), function({param}) {unpack}return " \
                       f"{level(index + 1)} end{keep}))"
            return level(0)
        finally:
            self.scopes.pop()

    def param(self, target):
        if isinstance(target, ast.Name):
            return self.ident(target.id), ""
        names = [self.ident(item.id) for item in target.elts if isinstance(item, ast.Name)]
        return "_pair", f"local {', '.join(names)} = G.unpack(_pair) "

    def subject_value(self, node):
        if isinstance(node, ast.Name) and not self.is_variable(node.id) and node.id not in self.functions:
            return self.string(node.id)
        return self.expr(node)

    def key(self, node):
        if isinstance(node, ast.Name) and not self.is_variable(node.id):
            return self.string(node.id)
        return self.expr(node)

    def name(self, name):
        if self.is_variable(name):
            return self.name_code(name)
        if name in self.functions:
            return self.ident(name)
        if name == "true":
            return "true"
        if name == "false":
            return "false"
        if name in ("none", "nil", "null"):
            return "nil"
        if name == "pi":
            return "math.pi"
        if name in EXPRESSION_FUNCTIONS:
            return f"G.{self.function_name(name)}"
        return self.string(name)

    @staticmethod
    def function_name(name):
        return name + "_" if name in _LUA_RESERVED else name

    def call_code(self, node):
        func, args = node.func, [self.expr(arg) for arg in node.args]
        if isinstance(func, ast.Name):
            name = func.id
            if name == "__flag__":
                return f"G.flag({args[0]})"
            if name == "__ask__":
                return f"G.ask({args[0]})"
            if name == "__fetch__":
                return f"G.fetch({args[0]})"
            if self.is_variable(name):
                return f"{self.name_code(name)}({', '.join(args)})"
            if name in self.functions:
                return f"{self.ident(name)}({', '.join(args)})"
            if name in EXPRESSION_FUNCTIONS:
                return f"G.{self.function_name(name)}({', '.join(args)})"
            self.notes.add(f"'{name}' is not a gublan function (maybe it came from a plugin). it is left as a call "
                           "to G.missing.")
            return f"G.missing({self.string(name)})({', '.join(args)})"
        if isinstance(func, ast.Attribute):
            method = func.attr
            subject = self.subject_value(func.value)
            if method in self.functions:
                return f"{self.ident(method)}({', '.join([subject] + args)})"
            if method in EXPRESSION_FUNCTIONS:
                return f"G.{self.function_name(method)}({', '.join([subject] + args)})"
            return f"G.field({subject}, {self.string(method)})({', '.join(args)})"
        return f"{self.wrap(func, self.PREC['call'])}({', '.join(args)})"

    # ----- statements -------------------------------------------------------------------------------------------
    def line_code(self, code):
        if not re.search(r"\)\s*$", code) or code.startswith("("):
            code = f"local _ = {code}"
        self.emit(code)

    def tidy(self):
        """'do return x end' becomes 'return x' when it is the last line of its block (lua needs the do...end only
        when more lines follow)."""
        for index, line in enumerate(self.out):
            match = re.fullmatch(r"(\s*)do (return(?: .*)?|break) end", line)
            if not match:
                continue
            indent = len(match.group(1))
            following = next((later for later in self.out[index + 1:]
                              if later.strip() and not later.strip().startswith("--")), None)
            if following is None or len(following) - len(following.lstrip()) < indent:
                self.out[index] = match.group(1) + match.group(2)

    def open(self, header):
        self.emit(header)
        self.depth += 1

    def close(self, word="end"):
        self.depth -= 1
        self.emit(word)

    def middle(self, header):
        self.depth -= 1
        self.emit(header)
        self.depth += 1

    def store(self, target, value, compound=None):
        code = self.expr(value)
        if isinstance(target, ast.Name):
            self.emit(f"{self.name_code(target.id)} = {code}")
        elif isinstance(target, ast.Attribute):
            self.emit(f"G.set_field({self.subject_value(target.value)}, {self.string(target.attr)}, {code})")
        elif isinstance(target, ast.Subscript):
            self.emit(f"G.put({self.expr(target.value)}, {self.expr(target.slice)}, {code})")
        else:
            raise ValueError("this can't be given a value")

    def append_to(self, target, value):
        self.emit(f"G.append({self.expr(target)}, {self.expr(value)})")

    def print_text(self, node):
        value = self.single_value(node)
        self.emit(f"G.print({self.expr(node if value is None else value)})")

    def throw(self, message):
        self.emit(f"G.throw({self.expr(message)})")

    def cond(self, node):
        return self.truthy(node)

    def header(self):
        for text in self.header_lines():
            self.comment(text)
        self.emit('local G = require("gublan")')
        self.blank()

    def function(self, node):
        name = str(node.line.parts[1])
        params = self.functions.get(name, [])
        self.blank()
        self.open(f"function {self.ident(name)}({', '.join(self.ident(p) for p in params)})")
        self.scopes.append(set(params))
        self.context.append(["function"])
        try:
            self.body(node.body)
        finally:
            self.scopes.pop()
            self.context.pop()
        self.close()
        self.blank()

    def test(self, node):
        name = "test_" + _slug(" ".join(str(part) for part in node.line.parts[1:]))
        while name in self.tests:
            name += "_"
        self.tests.append(name)
        self.blank()
        self.comment(node.line.text)
        self.open(f"function {name}()")
        self.context.append(["function"])
        try:
            self.body(node.body)
        finally:
            self.context.pop()
        self.close()
        self.blank()

    def main(self, nodes):
        self.blank()
        self.open("function main()")
        self.context.append(["function"])
        try:
            self.body(nodes)
        finally:
            self.context.pop()
        self.close()

    def footer(self):
        self.blank()
        if self.tests:
            self.emit(f"G.tests = {{{', '.join(f'{{{self.string(n)}, {n}}}' for n in self.tests)}}}")
        self.emit(f"G.start(main, {self.string(self.program_name)})")

    def b_if(self, node):
        self.open(f"if {self.cond(self.condition(node.line))} then")
        self.body(node.body)
        for middle, branch in node.branches:
            if middle.cmd == "elseif":
                self.middle(f"elseif {self.cond(self.condition(middle))} then")
            else:
                self.middle("else")
            self.body(branch)
        self.close()

    def loop_body(self, node, header):
        """lua has no continue: a loop that uses it jumps to a label at the end of the loop."""
        label = self.fresh("continue") if _has_continue(node.body) else None
        self.open(header)
        self.context.append(["loop", label])
        try:
            if label:
                self.open("do")
                self.body(node.body)
                self.close()
                self.emit(f"::{label}::")
            else:
                self.body(node.body)
        finally:
            self.context.pop()
        self.close()

    def b_loop(self, node):
        self.loop_body(node, f"for _ = 1, {self.expr(self.val(node.line.parts[1]))} do")

    def b_forever(self, node):
        self.loop_body(node, "while true do")

    def b_while(self, node):
        self.loop_body(node, f"while {self.cond(self.condition(node.line))} do")

    def b_until(self, node):
        test = self.cond(self.condition(node.line))
        self.loop_body(node, f"while not ({test}) do" if " " in test and not test.startswith("G.")
                       else f"while not {test} do")

    def b_for(self, node):
        line = node.line
        match = _FOR_RANGE_RE.match(line.rest)
        if match:
            name, start, end, step = match.groups()
            pieces = [self.expr(parse_expression(start)), self.expr(parse_expression(end))]
            if step:
                pieces.append(self.expr(parse_expression(step)))
            self.loop_body(node, f"for {self.name_code(name)} = {', '.join(pieces)} do")
        else:
            match = _FOR_IN_RE.match(line.rest)
            self.loop_body(node, f"for _, {self.name_code(match.group(1))} in "
                                 f"ipairs(G.each({self.expr(parse_expression(match.group(2)))})) do")

    def b_match(self, node):
        temp = self.fresh("_match")
        value = self.val(node.line.parts[1]) if len(node.line.parts) == 2 else self.expression(node.line.rest)
        self.emit(f"local {temp} = {self.expr(value)}")
        if node.body and any(not isinstance(item, _Comment) and item is not _BLANK for item in node.body):
            self.todo(node.line, "lines between match and the first case are skipped")
        first = True
        for middle, branch in node.branches:
            if middle.cmd == "case":
                values = [self.eval_value(part, split_command(part)) for part in _split_top_level_commas(middle.rest)]
                test = " or ".join(f"G.eq({temp}, {self.expr(value)})" for value in values)
                self.open(f"if {test} then") if first else self.middle(f"elseif {test} then")
            else:
                self.open("if true then") if first else self.middle("else")
            first = False
            self.body(branch)
        if not first:
            self.close()

    def b_try(self, node):
        ok, result, value = self.fresh("_ok"), self.fresh("_result"), self.fresh("_value")
        flags = {"return": False, "break": False, "continue": False}
        self.emit(f"local {ok}, {result}, {value} = pcall(function()")
        self.depth += 1
        self.context.append(["try", flags])
        try:
            self.body(node.body)
        finally:
            self.context.pop()
        self.depth -= 1
        self.emit("end)")
        catches = [(middle, branch) for middle, branch in node.branches if middle.cmd == "catch"]
        self.open(f"if not {ok} then")
        if catches:
            middle, branch = catches[0]
            name = str(middle.parts[1]) if len(middle.parts) > 1 else "error"
            self.emit(f"{self.name_code(name)} = G.message({result})")
            self.body(branch)
        else:
            self.emit(f"G.message({result})")
        for word, marker in (("return", "G.RETURN"), ("break", "G.BREAK"), ("continue", "G.CONTINUE")):
            if flags[word]:
                self.middle(f"elseif {result} == {marker} then")
                self.leave(word, value)
        self.close()

    def leave(self, word, value=None):
        """return, break or continue: inside a try they have to pass through pcall first."""
        for entry in reversed(self.context):
            if entry[0] == "try":
                entry[1][word] = True
                marker = {"return": "G.RETURN", "break": "G.BREAK", "continue": "G.CONTINUE"}[word]
                self.emit(f"do return {marker}{', ' + value if value else ''} end")
                return
            if entry[0] == "loop" and word in ("break", "continue"):
                if word == "break":
                    self.emit("do break end")
                else:
                    self.emit(f"goto {entry[1]}")
                return
            if entry[0] == "function" and word == "return":
                self.emit(f"do return {value} end" if value else "do return end")
                return
        self.emit(f"do return {value} end" if value else "do return end")

    def c_break(self, line):
        self.leave("break")

    def c_continue(self, line):
        self.leave("continue")

    def c_return(self, line):
        value = self.expr(self.eval_value(line.rest, line.parts[1:])) if len(line.parts) > 1 else None
        self.leave("return", value)
