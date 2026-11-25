"""rename a variable, function or object everywhere in a program, and find text in every file of a project.

rename never changes what a program prints or shows: in commands that take free text (print, popup, text...) only
the {braces} change, and "quoted strings" and // comments never do. a field after a dot (player.x) is a field, not
the variable x. nothing here touches tk, so the tests use it directly.
"""

import os
import re

from gublancore import COMMAND_SPECS

# commands whose words from this position on are text, not names (word 0 is the command)
TEXT_FROM = {
    "print": 1, "popup": 1, "title": 1, "throw": 1, "test": 1, "input": 2, "writefile": 2, "appendfile": 2,
    "append": 2, "remove": 2, "save": 2, "list": 2, "presence": 2, "insert": 3, "put": 3, "load": 3, "window": 3,
    "text": 4, "checkbox": 4, "textbox": 5, "button": 6,
}
EXPRESSION_LINES = {"if", "elseif", "elif", "while", "return", "set", "for", "call", "calc"}
KEYWORDS = {"and", "or", "not", "true", "false", "in", "to", "step", "end", "else", "then", "nothing"}
NAME = re.compile(r"[A-Za-z_]\w*$")
_ASSIGN_START = re.compile(r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\[[^\]]*\])*)\s*(\+=|-=|\*=|/=|=)(?!=)")
_EXPRESSION_TOKEN = re.compile(r'"[^"]*"?|\'[^\']*\'?|[A-Za-z_]\w*|\s+|.', re.S)
SEARCHED = (".gubl", ".txt", ".csv", ".tsv", ".json", ".md", ".log", ".dat")
SKIPPED_FOLDERS = {".git", "__pycache__", "node_modules", "export", "build", "dist", ".venv", "venv"}


def check_new_name(new):
    """None when new can be a name, otherwise why not."""
    if not NAME.match(new or ""):
        return "a name is letters, numbers and _, and it can't start with a number"
    if new in COMMAND_SPECS or new in KEYWORDS:
        return f"'{new}' is part of gublan, so it can't be a name"
    return None


def _expression(segment, old, new):
    out = []
    previous = ""
    for match in _EXPRESSION_TOKEN.finditer(segment):
        token = match.group(0)
        if token == old and previous != ".":
            token = new
        out.append(token)
        if not token.isspace():
            previous = token
    return "".join(out)


def _closing_brace(line, start):
    depth = 0
    index = start
    while index < len(line):
        char = line[index]
        if char == '"':
            end = line.find('"', index + 1)
            index = len(line) if end < 0 else end
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def _plain(line, start, old, new, text_from):
    """words outside braces change only before text_from; {braces} always do; "strings" never."""
    out = [line[:start]]
    word_pattern = re.compile(r"(?<![\w.])" + re.escape(old) + r"(?!\w)")
    index, position, length = start, 1, len(line)
    while index < length:
        if line[index].isspace():
            out.append(line[index])
            index += 1
            continue
        while index < length and not line[index].isspace():
            char = line[index]
            if char == "{":
                close = _closing_brace(line, index)
                if close < 0:
                    out.append(line[index:])
                    index = length
                    break
                out.append("{" + _expression(line[index + 1:close], old, new) + "}")
                index = close + 1
            elif char == '"':
                close = line.find('"', index + 1)
                close = length - 1 if close < 0 else close
                out.append(line[index:close + 1])
                index = close + 1
            else:
                end = index
                while end < length and not line[end].isspace() and line[end] not in '{"':
                    end += 1
                piece = line[index:end]
                if position < text_from:
                    piece = word_pattern.sub(new, piece)
                out.append(piece)
                index = end
        position += 1
    return "".join(out)


def rename_line(line, old, new):
    stripped = line.lstrip()
    if not stripped or stripped.startswith("//") or not re.search(r"(?<!\w)" + re.escape(old) + r"(?!\w)", line):
        return line
    offset = len(line) - len(stripped)
    match = re.match(r"[A-Za-z_]\w*", stripped)
    first = match.group(0) if match else ""
    after = offset + len(first)
    if first in COMMAND_SPECS or first == "elif":
        if first not in COMMAND_SPECS or not _ASSIGN_START.match(stripped) or first in ("set", "for"):
            if first in EXPRESSION_LINES:
                return line[:after] + _expression(line[after:], old, new)
            return _plain(line, after, old, new, TEXT_FROM.get(first, 10 ** 6))
    if _ASSIGN_START.match(stripped) or (first and line[after:].lstrip().startswith("(")):
        return line[:offset] + _expression(line[offset:], old, new)
    return _plain(line, offset, old, new, 10 ** 6)


def rename(source, old, new):
    """(new source, [changed line numbers]) with old renamed to new wherever it's a name."""
    lines = source.split("\n")
    changed = []
    for number, line in enumerate(lines, start=1):
        renamed = rename_line(line, old, new)
        if renamed != line:
            lines[number - 1] = renamed
            changed.append(number)
    return "\n".join(lines), changed


# ----- find in files -------------------------------------------------------------------------------------------
def find_in_files(folder, needle, match_case=False, whole_word=False, limit=2000):
    """[(path, line number, column, line text)] for every match in the project's text files."""
    if not folder or not needle or not os.path.isdir(folder):
        return []
    flags = 0 if match_case else re.I
    pattern = re.escape(needle)
    if whole_word:
        pattern = r"(?<!\w)" + pattern + r"(?!\w)"
    finder = re.compile(pattern, flags)
    found = []
    for here, folders, files in os.walk(folder):
        folders[:] = sorted(name for name in folders if name not in SKIPPED_FOLDERS and not name.startswith("."))
        for name in sorted(files):
            if not name.lower().endswith(SEARCHED):
                continue
            path = os.path.join(here, name)
            try:
                if os.path.getsize(path) > 2_000_000:
                    continue
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    for number, line in enumerate(handle, start=1):
                        for match in finder.finditer(line):
                            found.append((path, number, match.start(), line.rstrip("\r\n")))
                            if len(found) >= limit:
                                return found
            except OSError:
                continue
    return found
