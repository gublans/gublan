"""language facts the studio needs: highlighting words, completions, hints and line explanations.

everything comes from gublancore so the editor can never disagree with the language.
"""

import re

from gublancore import (
    BLOCK_OPENERS, CATEGORY_ORDER, COLORS, COMMAND_SPECS, EXPRESSION_FUNCTIONS, EXPRESSION_KEYWORDS,
    GUBLANCOMMANDS, KEY_ALIASES, parse_line, split_command,
)

FLOW_WORDS = {"if", "elseif", "elif", "else", "then", "end", "loop", "forever", "while", "for", "break", "continue",
              "function", "return", "kill", "wait", "include"}
KEY_NAMES = sorted({"left", "right", "up", "down", "space", "return", "escape", "tab", "backspace", "left shift",
                    "right shift", "left ctrl", "a", "d", "s", "w", "f1"} | set(KEY_ALIASES))
EXPRESSION_WORDS = {"and", "or", "not", "in", "to", "step", "true", "false", "none", "pi", "dt", "all"} | set(
    EXPRESSION_KEYWORDS)
INDENT_OPENERS = set(BLOCK_OPENERS) | {"elseif", "else"}
DEDENT_WORDS = {"end", "else", "elseif", "elif"}

CATEGORY_ABOUT = {
    "basics": "printing, variables and math",
    "control": "choices, loops and timing",
    "functions": "reusable named blocks of code",
    "lists and maps": "collections of values",
    "display": "the window, colours and frames",
    "2d": "flat shapes, text, pictures and buttons",
    "3d": "cubes, spheres and the camera",
    "objects": "moving, hiding and checking shapes",
    "input": "keyboard, mouse and questions",
    "sound": "sound effects and music",
    "web": "reading text from the internet",
}


def commands_by_category():
    groups = {category: [] for category in CATEGORY_ORDER}
    for name, spec in COMMAND_SPECS.items():
        groups.setdefault(spec[0], []).append(name)
    return groups


def usage(command):
    spec = COMMAND_SPECS.get(command)
    return spec[1] if spec else ""


def summary(command):
    spec = COMMAND_SPECS.get(command)
    return spec[3] if spec else ""


def example(command):
    spec = COMMAND_SPECS.get(command)
    return spec[4] if spec else ""


def category(command):
    spec = COMMAND_SPECS.get(command)
    return spec[0] if spec else "code"


# ----- symbols in the user's program --------------------------------------------------
_FUNCTION_RE = re.compile(r"^\s*function\s+([A-Za-z_]\w*)(.*)$", re.MULTILINE)
_ASSIGN_RE = re.compile(r"^\s*(?:set\s+)?([A-Za-z_]\w*)\s*(?:=|\+=|-=|\*=|/=)(?!=)", re.MULTILINE)
_CREATES_VARIABLE = {
    "random": 1, "time": 1, "calc": 1, "list": 1, "map": 1, "item": 3, "length": 2, "lookup": 3, "has": 3,
    "key": 1, "keypressed": 1, "mousebutton": 1, "input": 1, "touching": 1, "button": 1, "vec2": 1, "vec3": 1,
    "get": 2, "for": 1,
}
_CREATES_OBJECT = {"box": 1, "circle": 1, "line": 1, "text": 1, "image": 1, "sprite": 1, "cube": 1, "sphere": 1}


def collect_symbols(source):
    """functions (with parameters and line), variables and objects defined in a program."""
    functions = {}
    variables = {}
    objects = {}
    for number, raw in enumerate(source.split("\n"), start=1):
        text = raw.strip()
        if not text or text.startswith("//"):
            continue
        match = _FUNCTION_RE.match(raw)
        if match:
            params = match.group(2).split()
            functions.setdefault(match.group(1), {"line": number, "params": params})
            for param in params:
                variables.setdefault(param, number)
            continue
        assignment = _ASSIGN_RE.match(raw)
        if assignment and assignment.group(1) not in GUBLANCOMMANDS:
            variables.setdefault(assignment.group(1), number)
            continue
        words = text.split()
        command = words[0]
        if command == "set" and len(words) > 1:
            variables.setdefault(words[1], number)
        elif command in _CREATES_VARIABLE and len(words) > _CREATES_VARIABLE[command]:
            name = words[_CREATES_VARIABLE[command]]
            if command == "for":
                name = re.split(r"[=\s]", text[4:].strip(), 1)[0]
            if re.fullmatch(r"[A-Za-z_]\w*", name):
                variables.setdefault(name, number)
            if command == "mouse" and len(words) > 2:
                variables.setdefault(words[2], number)
        elif command == "mouse" and len(words) > 2:
            variables.setdefault(words[1], number)
            variables.setdefault(words[2], number)
        elif command in _CREATES_OBJECT and len(words) > 1 and "{" not in words[1]:
            objects.setdefault(words[1], number)
    return {"functions": functions, "variables": variables, "objects": objects}


# ----- completion -----------------------------------------------------------------------
def completions(prefix, line_before, symbols):
    """suggestions for the word being typed. returns (label, insert, kind, detail) tuples."""
    stripped = line_before.lstrip()
    in_braces = line_before.count("{") > line_before.count("}")
    first_word = not stripped or (" " not in stripped and not in_braces)
    items = []
    lowered = prefix.lower()

    def add(label, kind, detail, insert=None):
        if label.lower().startswith(lowered) and label != prefix:
            items.append((label, insert or label, kind, detail))

    if first_word:
        for name, spec in COMMAND_SPECS.items():
            add(name, spec[0], spec[3])
        for name, info in symbols["functions"].items():
            add(name, "function", f"call your function {name} {' '.join(info['params'])}".strip(),
                insert=f"{name}()")
        for name in symbols["variables"]:
            add(name, "variable", "change this variable")
        items.sort(key=lambda item: (item[2] not in ("function", "variable"), len(item[0]) > 0 and item[0]))
        return _rank(items, lowered)

    words = split_command(stripped) if stripped else []
    command = words[0] if words else ""
    if not in_braces and command in ("color", "paint", "background"):
        for name in COLORS:
            add(name, "colour", f"the colour {name}")
    if not in_braces and command in ("key", "keypressed"):
        for name in KEY_NAMES:
            if " " not in name:
                add(name, "key", f"the {name} key")
    if not in_braces and command == "mode":
        add("2d", "mode", "a flat window with x and y in pixels")
        add("3d", "mode", "a 3d window with cubes, spheres and a camera")
    if not in_braces and command == "call":
        for name, info in symbols["functions"].items():
            add(name, "function", " ".join(info["params"]))
    if command in ("move", "place", "resize", "hide", "show", "spin", "animate", "paint", "delete") or in_braces:
        for name in symbols["objects"]:
            add(name, "object", "a shape in your program")
    for name in symbols["variables"]:
        add(name, "variable", "a variable in your program")
    if in_braces or command in ("set", "if", "elseif", "while", "for", "return", "calc") or "=" in stripped:
        for name, help_text in EXPRESSION_FUNCTIONS.items():
            add(name, "math", help_text, insert=f"{name}(")
        for name, info in symbols["functions"].items():
            add(name, "function", " ".join(info["params"]), insert=f"{name}(")
        for word in ("and", "or", "not", "true", "false", "none", "pi", "dt"):
            add(word, "word", "")
    return _rank(items, lowered)


def _rank(items, prefix):
    seen = set()
    unique = []
    for item in items:
        if item[0] not in seen:
            seen.add(item[0])
            unique.append(item)
    unique.sort(key=lambda item: (not item[0].lower().startswith(prefix), len(item[0])))
    return unique[:60]


# ----- parameter hints ---------------------------------------------------------------------
def parameter_hint(line_before):
    """for 'box player 10' returns ('box', ['<name>', '<x>', ...], index of the argument being typed)."""
    stripped = line_before.lstrip()
    if not stripped or stripped.startswith("//"):
        return None
    words = split_command(stripped)
    if not words:
        return None
    command = words[0]
    spec = COMMAND_SPECS.get(command)
    if not spec:
        return None
    form = spec[1].split(" | ")[0]
    params = form.split()[1:]
    typed = len(words) - 1
    if not stripped.endswith(" "):
        typed -= 1
    index = max(0, typed)
    if params and params[-1].endswith("...>") and index >= len(params):
        index = len(params) - 1
    return command, params, index, spec[1]


# ----- explain the current line ------------------------------------------------------------
def explain_line(raw):
    """a short plain-language explanation of one line, for beginners."""
    text = raw.strip()
    if not text:
        return ""
    if text.startswith("//"):
        return "a comment: a note for people. the computer skips it."
    parsed = parse_line(text)
    if parsed is None:
        return ""
    if parsed.error:
        return parsed.error.lower()
    command = parsed.cmd
    parts = parsed.parts
    if command == "set" and len(parts) >= 3 and text.split(None, 1)[0] != "set":
        target = parts[1]
        value = text.split("=", 1)[1].strip() if "=" in text else ""
        return f"store {value} in {target}. a short way to write: set {target} = {value}"
    if command in ("add", "sub", "mul", "div") and text.split(None, 1)[0] != command:
        verbs = {"add": "add {v} to {t}", "sub": "take {v} away from {t}", "mul": "multiply {t} by {v}",
                 "div": "divide {t} by {v}"}
        amount = " ".join(str(part) for part in parts[2:])
        return verbs[command].format(v=amount, t=parts[1]) + "."
    if command == "call" and parsed.call_source:
        name = parsed.call_source.split("(", 1)[0]
        return f"run your function {name}. its answer goes into result."
    if command == "elseif" and text.startswith(("elif", "else if")):
        return f"{summary('elseif')} (another way to write elseif)"
    spec = COMMAND_SPECS.get(command)
    if not spec:
        return f"'{command}' is not a gublan command."
    explanation = spec[3]
    if command in ("if", "elseif", "while") and len(parts) > 1:
        condition = text.split(None, 1)[1]
        explanation = f"{explanation} here the condition is: {condition}"
    if command == "for":
        rest = text[3:].strip()
        match = re.match(r"([A-Za-z_]\w*)\s*=\s*(.+?)\s+to\s+(.+?)(?:\s+step\s+(.+))?$", rest)
        if match:
            name, start, stop, step = match.groups()
            explanation = f"count {name} from {start} to {stop}" + (f" in steps of {step}" if step else "") + \
                ", running the lines inside each time."
        elif " in " in rest:
            name, values = rest.split(" in ", 1)
            explanation = f"go through every item in {values.strip()}, calling it {name.strip()} each time."
    if "{" in text and command not in ("for",):
        explanation += " parts in {braces} are worked out first."
    return explanation
