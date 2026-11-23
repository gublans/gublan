"""the code editor: highlighting, gutter, completion, hover help, hints, find and replace.

the text widget's tcl command is wrapped by a small tcl proc, so every insert, delete and cursor
move is seen (including the ones tk's own key bindings make) without breaking tk's error handling.
"""

import bisect
import re
import tkinter as tk
from tkinter import font as tkfont

from gublancore import BLOCK_OPENERS, COLORS, COMMAND_SPECS, EXPRESSION_FUNCTIONS

from . import meta, sounds
from .caret import SmoothCaret, SmoothScroll, TypingEffects
from .theme import (
    BORDER, DEBUG_LINE, DIM, EDITOR_BG, ERROR, ERROR_LINE, MOSS, MOSS_DARK, MOSS_LIGHT, MUTED, NUMBER,
    PANEL, PANEL_ALT, SELECT, SELECT_TEXT, SYNTAX, TEXT, ACTIVE_LINE, BracketButton, flat_entry, icon,
    icon_font, lower, mono_font, popup_window, px, scrollbar, ui_font,
)
from . import theme

SYNTAX_TAGS = ("command", "flow", "string", "number", "comment", "brace", "function", "keyword", "color",
               "operator")
BRACKET_TAGS = ("bracket0", "bracket1", "bracket2")
_OPENING, _CLOSING = "([", ")]"


def bracket_depths(text):
    """(column, depth) for each ( ) [ ] outside text and comments: rainbow brackets colour them by depth."""
    skip = set()
    for tag, a, b in line_tokens(text):
        if tag in ("string", "comment"):
            skip.update(range(a, b))
    found, depth = [], 0
    for column, char in enumerate(text):
        if column in skip:
            continue
        if char in _OPENING:
            found.append((column, depth))
            depth += 1
        elif char in _CLOSING:
            depth = max(0, depth - 1)
            found.append((column, depth))
    return found

_ASSIGN_START = re.compile(r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\[[^\]]*\])*)\s*(\+=|-=|\*=|/=|=)(?!=)")
_EXPR_TOKEN = re.compile(
    r"""(?P<string>"[^"]*"?|'[^']*'?)"""
    r"""|(?P<hex>\#[0-9a-fA-F]{6}\b|\#[0-9a-fA-F]{3}\b)"""
    r"""|(?P<number>(?<![\w.])\d+(?:\.\d+)?)"""
    r"""|(?P<word>[A-Za-z_]\w*)"""
    r"""|(?P<op>==|!=|>=|<=|\+=|-=|\*=|/=|&&|\|\||[-+*/%<>=!^])"""
    r"""|(?P<brace>[{}])"""
)
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_HEX = re.compile(r"#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}")
_WORD_BEFORE = re.compile(r"[A-Za-z_]\w*$")
EXPRESSION_LINES = {"if", "elseif", "elif", "while", "return", "set", "for", "call", "calc"}
PAIRS = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}
CLOSERS = {")", "]", "}"}


# ----- highlighting (pure functions, easy to test) -----------------------------------
def _match_brace(text, index):
    depth, quote = 0, None
    for scan in range(index, len(text)):
        char = text[scan]
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return scan
    return -1


def _expression(text, start, end, out):
    for match in _EXPR_TOKEN.finditer(text, start, end):
        kind = match.lastgroup
        a, b = match.span()
        if kind == "word":
            word = match.group("word")
            rest = text[b:end].lstrip()
            if rest.startswith("("):
                out.append(("function", a, b))
            elif word in meta.EXPRESSION_WORDS:
                out.append(("keyword", a, b))
        elif kind == "hex":
            out.append(("color", a, b))
        elif kind == "op":
            out.append(("operator", a, b))
        else:
            out.append((kind, a, b))


def _plain(text, start, out, colours=False):
    index, length = start, len(text)
    while index < length:
        if text[index].isspace():
            index += 1
            continue
        token_start = index
        simple = True
        while index < length and not text[index].isspace():
            char = text[index]
            if char == '"' or (char == "'" and index == token_start):
                closing = text.find(char, index + 1)
                if closing < 0:
                    index += 1
                    continue
                out.append(("string", index, closing + 1))
                index = closing + 1
                simple = False
            elif char == "{":
                closing = _match_brace(text, index)
                if closing < 0:
                    index += 1
                    continue
                out.append(("brace", index, index + 1))
                out.append(("brace", closing, closing + 1))
                _expression(text, index + 1, closing, out)
                index = closing + 1
                simple = False
            else:
                index += 1
        if simple:
            word = text[token_start:index]
            if _NUMBER.fullmatch(word):
                out.append(("number", token_start, index))
            elif _HEX.fullmatch(word):
                out.append(("color", token_start, index))
            elif colours and word in COLORS:
                out.append(("color", token_start, index))


def line_tokens(text):
    """(tag, start column, end column) for one line of gublan."""
    out = []
    stripped = text.lstrip()
    if not stripped:
        return out
    offset = len(text) - len(stripped)
    if stripped.startswith("//"):
        return [("comment", offset, len(text))]
    match = re.match(r"[A-Za-z_]\w*", stripped)
    first = match.group(0) if match else ""
    after = offset + len(first)
    if first in COMMAND_SPECS or first == "elif":
        if first not in COMMAND_SPECS or not _ASSIGN_START.match(stripped) or first in ("set", "for"):
            out.append(("flow" if first in meta.FLOW_WORDS else "command", offset, after))
            if first == "else" and re.match(r"\s+if\b", text[after:]):
                extra = re.match(r"\s+if\b", text[after:])
                out.append(("flow", after + extra.end() - 2, after + extra.end()))
                _expression(text, after + extra.end(), len(text), out)
            elif first in EXPRESSION_LINES:
                _expression(text, after, len(text), out)
            elif first == "function":
                name = re.match(r"\s+([A-Za-z_]\w*)", text[after:])
                if name:
                    out.append(("function", after + name.start(1), after + name.end(1)))
            else:
                _plain(text, after, out, colours=first in ("color", "paint", "background"))
            return out
    if _ASSIGN_START.match(stripped):
        _expression(text, offset, len(text), out)
        return out
    if first and text[after:].lstrip().startswith("("):
        out.append(("function", offset, after))
        _expression(text, after, len(text), out)
        return out
    _plain(text, offset, out)
    return out


def leading(text):
    return text[:len(text) - len(text.lstrip(" \t"))]


def first_word(text):
    match = re.match(r"\s*([A-Za-z_]\w*)", text)
    return match.group(1) if match else ""


# ----- the editor ---------------------------------------------------------------------
class CodeEditor(tk.Frame):
    def __init__(self, parent, settings, hooks=None):
        super().__init__(parent, bg=EDITOR_BG)
        self.settings = settings
        self.hooks = hooks or {}
        self.breakpoints = set()
        self.diagnostics = []
        self.diag_by_line = {}
        self.debug_line = None
        self.symbols = {"functions": {}, "variables": {}, "objects": {}}
        self.version = 0
        self.saved_version = 0
        self._jobs = {}
        self._pending = []
        self._structure = (None, {})
        self.completion = None
        self.hover = None
        self._hover_word = None
        self.find_bar = None
        self.matches = []
        self.match_index = -1
        self.collab_listener = None  # live sessions: called soon after the text changes
        self.collab_cursor = None  # live sessions: called soon after the cursor moves
        self.peers = []  # live sessions: other people's cursors (key, name, color, position)
        self.peer_flags = {}
        self.live_applying = False  # true while someone else's edit is being put in

        size = settings.get("font_size", 11)
        self.font = tkfont.Font(family=theme.MONO_FAMILY, size=size)
        self.italic = tkfont.Font(family=theme.MONO_FAMILY, size=size, slant="italic")
        self.bold = tkfont.Font(family=theme.MONO_FAMILY, size=size, weight="bold")

        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self.gutter = tk.Canvas(self, bg=EDITOR_BG, highlightthickness=0, bd=0, width=px(48), cursor="hand2")
        self.gutter.grid(row=1, column=0, sticky="ns")
        self.text = tk.Text(
            self, undo=True, autoseparators=True, maxundo=-1, wrap="word" if settings.get("wrap") else "none",
            font=self.font, bg=EDITOR_BG, fg=TEXT, insertbackground=MOSS_LIGHT, insertwidth=px(2),
            insertofftime=420, insertontime=640, selectbackground=SELECT, inactiveselectbackground=theme.INACTIVE_SELECT,
            relief="flat", borderwidth=0, highlightthickness=0, padx=px(10), pady=px(6), spacing1=px(1),
            spacing3=px(1), exportselection=True,
        )
        self.text.grid(row=1, column=1, sticky="nsew")
        self.vbar = scrollbar(self, "vertical", self.text.yview)
        self.vbar.grid(row=1, column=2, sticky="ns")
        self.hbar = scrollbar(self, "horizontal", self.text.xview)
        self.hbar.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.hbar.grid_remove()
        self.text.configure(yscrollcommand=self._yscroll, xscrollcommand=self._xscroll)
        self.hintbar = tk.Text(self, height=1, bg=PANEL, fg=MUTED, relief="flat", borderwidth=0,
                               highlightthickness=0, font=ui_font(9), padx=px(10), pady=px(4), cursor="arrow",
                               wrap="none", takefocus=0)
        self.hintbar.grid(row=3, column=0, columnspan=3, sticky="ew")
        for tag, color in (("param", MOSS_LIGHT), ("current", SELECT_TEXT), ("dim", DIM), ("error", ERROR),
                           ("warning", NUMBER), ("explain", MUTED), ("head", MOSS_LIGHT)):
            self.hintbar.tag_configure(tag, foreground=color)
        self.hintbar.tag_configure("mono", font=mono_font(9))
        self.hintbar.tag_configure("currentparam", foreground=SELECT_TEXT, background=MOSS_DARK, font=mono_font(9))
        self.hintbar.configure(state="disabled")
        if not settings.get("hint_bar", True):
            self.hintbar.grid_remove()

        self._configure_tags()
        self._install_proxy()
        self._bind_keys()
        self._typing = False
        self._rainbow = None
        self.caret = SmoothCaret(self)
        self.effects = TypingEffects(self)
        self.smooth_scroll = SmoothScroll(self)
        self.text.bind("<<Paste>>", self._before_paste, add="+")
        self.apply_settings(settings)
        self.gutter.bind("<Button-1>", self._gutter_click)
        self.gutter.bind("<MouseWheel>", lambda e: self.text.yview_scroll(int(-e.delta / 40), "units"))
        self.text.bind("<Configure>", lambda _e: self._schedule("gutter", 0, self.draw_gutter), add="+")

    # ----- setup ---------------------------------------------------------------------
    def theme_changed(self):
        """the theme changed while the studio is open (see theme.switch_theme)."""
        self._configure_tags()
        self._schedule("gutter", 0, self.draw_gutter)

    def _configure_tags(self):
        text = self.text
        text.tag_configure("currentline", background=ACTIVE_LINE)
        text.tag_configure("errorline", background=ERROR_LINE)
        text.tag_configure("debugline", background=DEBUG_LINE)
        text.tag_configure("found", background=MOSS_DARK)
        text.tag_configure("foundcurrent", background=MOSS, foreground=SELECT_TEXT)
        text.tag_configure("match", background=theme.MATCH, foreground=SELECT_TEXT)
        for tag in SYNTAX_TAGS:
            text.tag_configure(tag, foreground=SYNTAX[tag])
        text.tag_configure("comment", font=self.italic)
        text.tag_configure("command", font=self.font)
        text.tag_configure("error", underline=True, underlinefg=ERROR)
        text.tag_configure("warning", underline=True, underlinefg=NUMBER)
        text.tag_configure("sel", foreground="")
        for tag in ("errorline", "debugline", "found", "foundcurrent", "match"):
            text.tag_raise(tag, "currentline")
        for tag, color in zip(BRACKET_TAGS, (SYNTAX["number"], SYNTAX["keyword"], SYNTAX["brace"])):
            text.tag_configure(tag, foreground=color)
        text.tag_raise("sel")

    def _install_proxy(self):
        widget = str(self.text)
        original = widget + "_orig"
        callback = self.register(self._changed)
        self.tk.call("rename", widget, original)
        script = """
proc {W} {{args}} {{
    set op [lindex $args 0]
    if {{$op eq "insert" || $op eq "delete" || $op eq "replace"}} {{
        set a [{O} index [lindex $args 1]]
        if {{[{O} compare $a >= end]}} {{ set a [{O} index "end - 1 chars"] }}
        if {{$op ne "insert" && [llength $args] > 2}} {{
            set b [{O} index [lindex $args 2]]
        }} else {{
            set b $a
        }}
        set n 0
        if {{$op eq "insert"}} {{ set n [string length [lindex $args 2]] }}
        set before [lindex [split [{O} index end] .] 0]
        set result [{O} {{*}}$args]
        set after [lindex [split [{O} index end] .] 0]
        {C} $op $a $b [expr {{$after - $before}}] $n
        return $result
    }}
    if {{$op eq "mark" && [lindex $args 1] eq "set" && [lindex $args 2] eq "insert"}} {{
        set result [{O} {{*}}$args]
        {C} cursor 0 0 0 0
        return $result
    }}
    return [{O} {{*}}$args]
}}
""".format(W=widget, O=original, C=callback)
        self.tk.eval(script)
        self._proxy_names = (widget, original)
        self.text.bind("<Destroy>", self._remove_proxy, add="+")

    def _remove_proxy(self, _event=None):
        try:
            self.tk.call("rename", self._proxy_names[0], "")
        except tk.TclError:
            pass

    def apply_settings(self, settings):
        self.settings = settings
        size = int(settings.get("font_size", 11))
        family = theme.editor_family(settings, self)
        for item in (self.font, self.italic, self.bold):
            item.configure(family=family, size=size)
        tab = self.font.measure(" " * self.indent_size())
        try:
            extra = max(0, min(8, int(settings.get("line_spacing", 1))))
        except (TypeError, ValueError):
            extra = 1
        self.text.configure(tabs=(tab,), wrap="word" if settings.get("wrap") else "none",
                            spacing1=px(extra), spacing3=px(extra))
        if settings.get("hint_bar", True):
            self.hintbar.grid()
        else:
            self.hintbar.grid_remove()
        self.caret.apply(settings)
        self.effects.apply(settings)
        self.smooth_scroll.apply(settings)
        rainbow = bool(settings.get("rainbow_brackets", True))
        if rainbow != self._rainbow:
            changed = self._rainbow is not None
            self._rainbow = rainbow
            if changed:
                self.highlight_all()
        self._schedule("gutter", 0, self.draw_gutter)

    def indent_size(self):
        return int(self.settings.get("indent", 4))

    def unit(self):
        return " " * self.indent_size()

    # ----- content -------------------------------------------------------------------------
    def get(self):
        return self.text.get("1.0", "end-1c")

    def set_text(self, value, keep_undo=False):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        if not keep_undo:
            self.text.edit_reset()
        self.text.mark_set("insert", "1.0")
        self.text.see("insert")
        self.saved_version = self.version
        self.refresh_symbols()
        self.highlight_all()

    def replace_all_text(self, value):
        """replace everything as one undoable step, keeping the scroll position."""
        top = self.text.yview()[0]
        cursor = self.text.index("insert")
        self.text.edit_separator()
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self.text.edit_separator()
        self.text.mark_set("insert", cursor)
        self.text.yview_moveto(top)
        self.highlight_all()

    @property
    def dirty(self):
        return self.version != self.saved_version

    def mark_saved(self):
        self.saved_version = self.version

    def cursor(self):
        line, column = self.text.index("insert").split(".")
        return int(line), int(column)

    def current_line_text(self):
        return self.text.get("insert linestart", "insert lineend")

    def line_count(self):
        return int(self.text.index("end-1c").split(".")[0])

    def focus_editor(self):
        self.text.focus_set()

    # ----- change tracking -------------------------------------------------------------------
    def _changed(self, op, start, end, delta, count=0):
        if op == "insert" and self._typing and not self.live_applying:
            try:
                length = int(count)
            except ValueError:
                length = 0
            if 0 < length <= 8:
                self.effects.typed(start, f"{start}+{length}c")
        if op == "cursor":
            self._schedule("cursor", 0, self._cursor_moved)
            if self.collab_cursor:
                self._schedule("collab_cursor", 90, self.collab_cursor)
            return
        try:
            start_line, start_col = (int(part) for part in start.split("."))
            end_line = int(end.split(".")[0])
            delta = int(delta)
        except ValueError:
            return
        self.version += 1
        if delta:
            self._shift_lines(start_line, start_col, end_line, delta, op == "insert")
        first = min(start_line, end_line)
        last = max(start_line, end_line + delta, first)
        self._mark_dirty(first, last)
        self._schedule("cursor", 0, self._cursor_moved)
        self._schedule("gutter", 0, self.draw_gutter)
        self._schedule("symbols", 450, self.refresh_symbols)
        callback = self.hooks.get("changed")
        if callback:
            self._schedule("changed", 30, callback)
        if self.collab_listener and not self.live_applying:
            # right away, so each edit goes out on its own: merged edits would carry unchanged text with them
            self.collab_listener()
        if self.matches:
            self._schedule("research", 200, self._research)

    def _shift_lines(self, start_line, start_col, end_line, delta, inserting):
        def moved(line):
            if delta > 0:
                if line > start_line or (inserting and start_col == 0 and line == start_line):
                    return line + delta
                return line
            if start_line < line <= end_line:
                return None
            if line > end_line:
                return line + delta
            return line

        new_points = set()
        for line in self.breakpoints:
            target = moved(line)
            if target is not None:
                new_points.add(target)
        if new_points != self.breakpoints:
            self.breakpoints = new_points
            callback = self.hooks.get("breakpoints")
            if callback:
                callback()
        shifted = {}
        for line, items in self.diag_by_line.items():
            target = moved(line)
            if target is not None:
                shifted[target] = items
        self.diag_by_line = shifted
        if self.debug_line:
            self.debug_line = moved(self.debug_line)
        self._pending = [(moved(a) or a, moved(b) or b) for a, b in self._pending]

    def _mark_dirty(self, first, last):
        self._pending.append((first, last))
        if "highlight" not in self._jobs:
            self._jobs["highlight"] = self.after_idle(self._process_pending)

    def highlight_all(self):
        self._pending = [(1, self.line_count())]
        self._process_pending()

    def _process_pending(self):
        self._jobs.pop("highlight", None)
        if not self._pending:
            return
        top = int(self.text.index("@0,0").split(".")[0])
        bottom = int(self.text.index(f"@0,{self.text.winfo_height()}").split(".")[0]) + 1
        budget = 400
        remaining = []
        # visible lines first so what you see is always coloured
        for first, last in self._pending:
            a, b = max(first, top), min(last, bottom)
            if a <= b:
                self.highlight_lines(a, b)
                if first < a:
                    remaining.append((first, a - 1))
                if b < last:
                    remaining.append((b + 1, last))
            else:
                remaining.append((first, last))
        later = []
        for first, last in remaining:
            if budget <= 0:
                later.append((first, last))
                continue
            stop = min(last, first + budget - 1)
            self.highlight_lines(first, stop)
            budget -= stop - first + 1
            if stop < last:
                later.append((stop + 1, last))
        self._pending = later
        if later:
            self._jobs["highlight"] = self.after(5, self._process_pending)

    def highlight_lines(self, first, last):
        total = self.line_count()
        first, last = max(1, first), min(last, total)
        if first > last:
            return
        text = self.text
        start, end = f"{first}.0", f"{last}.end"
        for tag in SYNTAX_TAGS + BRACKET_TAGS:
            text.tag_remove(tag, start, end)
        ranges = {tag: [] for tag in SYNTAX_TAGS + BRACKET_TAGS}
        rainbow = self.settings.get("rainbow_brackets", True)
        for offset, line in enumerate(text.get(start, end).split("\n")):
            number = first + offset
            if len(line) > 3000:
                line = line[:3000]
            for tag, a, b in line_tokens(line):
                if b > a:
                    ranges[tag].append(f"{number}.{a}")
                    ranges[tag].append(f"{number}.{b}")
            if rainbow and ("(" in line or "[" in line):
                for column, depth in bracket_depths(line):
                    tag = BRACKET_TAGS[depth % len(BRACKET_TAGS)]
                    ranges[tag].append(f"{number}.{column}")
                    ranges[tag].append(f"{number}.{column + 1}")
        for tag, indices in ranges.items():
            for chunk in range(0, len(indices), 2000):
                part = indices[chunk:chunk + 2000]
                if part:
                    text.tag_add(tag, *part)

    def refresh_symbols(self):
        self._jobs.pop("symbols", None)
        self.symbols = meta.collect_symbols(self.get())
        callback = self.hooks.get("symbols")
        if callback:
            callback()

    def _schedule(self, name, delay, callback):
        job = self._jobs.pop(name, None)
        if job:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass

        def run():
            self._jobs.pop(name, None)
            callback()

        self._jobs[name] = self.after(delay, run) if delay else self.after_idle(run)

    # ----- scrolling and the gutter -------------------------------------------------------------
    def _yscroll(self, first, last):
        self.vbar.set(first, last)
        self.caret.update(animate=False)
        self._schedule("gutter", 0, self.draw_gutter)
        if self.peers:
            self._schedule("peers", 0, self.place_peer_flags)
        if self._pending:
            self._schedule("visible", 30, self._process_pending)
        if getattr(self, "_last_view", None) not in (None, (first, last)):
            self._hide_hover()
        self._last_view = (first, last)

    def _xscroll(self, first, last):
        self.hbar.set(first, last)
        self.caret.update(animate=False)
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.hbar.grid_remove()
        else:
            self.hbar.grid()

    def draw_gutter(self):
        canvas = self.gutter
        canvas.delete("all")
        if not self.settings.get("line_numbers", True):
            canvas.configure(width=px(20))
        digits = max(2, len(str(self.line_count())))
        number_font = self.font
        width = number_font.measure("0" * digits) + px(26)
        if self.settings.get("line_numbers", True) and int(canvas["width"]) != width:
            canvas.configure(width=width)
        width = int(canvas["width"])
        current = self.cursor()[0]
        index = self.text.index("@0,0")
        height = self.text.winfo_height()
        mark = px(8)
        while True:
            info = self.text.dlineinfo(index)
            if info is None:
                break
            y, line_height = info[1], info[3]
            number = int(index.split(".")[0])
            middle = y + line_height / 2
            severity = None
            for item in self.diag_by_line.get(number, ()):
                if item.get("severity", "error") == "error":
                    severity = "error"
                elif severity is None:
                    severity = "warning"
            if self.settings.get("line_numbers", True):
                color = ERROR if severity == "error" else NUMBER if severity == "warning" else (
                    TEXT if number == current else DIM)
                canvas.create_text(width - px(8), middle, text=str(number), anchor="e", font=number_font,
                                   fill=color)
            if number in self.breakpoints:
                canvas.create_rectangle(px(5), middle - mark / 2, px(5) + mark, middle + mark / 2, fill=ERROR,
                                        outline=ERROR)
            if number == self.debug_line:
                canvas.create_polygon(px(4), middle - px(6), px(4) + px(9), middle, px(4), middle + px(6),
                                      fill=MOSS_LIGHT, outline=MOSS_LIGHT)
            following = self.text.index(f"{index}+1line")
            if following == index or y > height:
                break
            index = following

    def _gutter_click(self, event):
        index = self.text.index(f"@0,{event.y}")
        line = int(index.split(".")[0])
        self.toggle_breakpoint(line)

    def toggle_breakpoint(self, line=None):
        line = line or self.cursor()[0]
        if line in self.breakpoints:
            self.breakpoints.discard(line)
        else:
            self.breakpoints.add(line)
        self.draw_gutter()
        callback = self.hooks.get("breakpoints")
        if callback:
            callback()

    # ----- markers from outside --------------------------------------------------------------
    def set_diagnostics(self, items):
        self.diagnostics = list(items)
        self.diag_by_line = {}
        for item in self.diagnostics:
            line = item.get("line")
            if line:
                self.diag_by_line.setdefault(int(line), []).append(item)
        text = self.text
        for tag in ("error", "warning", "errorline"):
            text.tag_remove(tag, "1.0", "end")
        total = self.line_count()
        for line, line_items in self.diag_by_line.items():
            if line > total:
                continue
            raw = text.get(f"{line}.0", f"{line}.end")
            start = len(raw) - len(raw.lstrip())
            severe = any(item.get("severity", "error") == "error" for item in line_items)
            tag = "error" if severe else "warning"
            if raw.strip():
                text.tag_add(tag, f"{line}.{start}", f"{line}.end")
            if severe:
                text.tag_add("errorline", f"{line}.0", f"{line}.0+1line")
        self.draw_gutter()
        self._schedule("cursor", 0, self._cursor_moved)

    def set_debug_line(self, line, scroll=True):
        self.text.tag_remove("debugline", "1.0", "end")
        self.debug_line = line
        if line:
            self.text.tag_add("debugline", f"{line}.0", f"{line}.0+1line")
            if scroll:
                self.text.see(f"{line}.0")
        self.draw_gutter()

    def goto_line(self, line, column=0, select_line=False):
        line = max(1, min(int(line), self.line_count()))
        self.text.mark_set("insert", f"{line}.{column}")
        self.text.tag_remove("sel", "1.0", "end")
        if select_line:
            raw = self.text.get(f"{line}.0", f"{line}.end")
            start = len(raw) - len(raw.lstrip())
            self.text.tag_add("sel", f"{line}.{start}", f"{line}.end")
        self.text.see(f"{line}.0")
        self.text.focus_set()
        self.flash_line(line)

    def flash_line(self, line, kind="jump"):
        """a soft glow over a line that fades out, so the eye finds it (jumps, errors)."""
        color = theme.mix(theme.ERROR, theme.EDITOR_BG, 0.55) if kind == "error" else theme.MOSS_DARK
        self.effects.flash_line(line, color=color, duration=1.1 if kind == "error" else 0.8)

    # ----- cursor, matching and the hint bar -------------------------------------------------------
    def _cursor_moved(self):
        text = self.text
        text.tag_remove("currentline", "1.0", "end")
        if self.settings.get("highlight_line", True) and not text.tag_ranges("sel"):
            text.tag_add("currentline", "insert linestart", "insert linestart+1line")
        self.caret.update()
        self.draw_gutter()
        self._show_matches()
        self._update_hint()
        line, column = self.cursor()
        callback = self.hooks.get("cursor")
        if callback:
            callback(line, column)

    def block_structure(self):
        """line -> list of partner lines for if/else/end style blocks (cached per edit)."""
        if self._structure[0] == self.version:
            return self._structure[1]
        partners = {}
        stack = []
        for number, raw in enumerate(self.get().split("\n"), start=1):
            word = first_word(raw)
            if raw.lstrip().startswith("//"):
                continue
            if word in BLOCK_OPENERS and not _ASSIGN_START.match(raw.strip()):
                stack.append([number])
            elif word in meta.MIDDLE_WORDS and stack:
                stack[-1].append(number)
            elif word == "end" and stack:
                group = stack.pop() + [number]
                for member in group:
                    partners[member] = group
        self._structure = (self.version, partners)
        return partners

    def _show_matches(self):
        text = self.text
        text.tag_remove("match", "1.0", "end")
        line, column = self.cursor()
        raw = self.current_line_text()
        word = first_word(raw)
        if word in BLOCK_OPENERS or word in meta.DEDENT_WORDS:
            group = self.block_structure().get(line)
            if group and len(group) > 1:
                for member in group:
                    member_text = text.get(f"{member}.0", f"{member}.end")
                    start = len(member_text) - len(member_text.lstrip())
                    member_word = first_word(member_text)
                    text.tag_add("match", f"{member}.{start}", f"{member}.{start + len(member_word)}")
        # brackets on the same line
        for position in (column - 1, column):
            if 0 <= position < len(raw) and raw[position] in "()[]{}":
                partner = self._bracket_partner(raw, position)
                if partner is not None:
                    text.tag_add("match", f"{line}.{position}", f"{line}.{position + 1}")
                    text.tag_add("match", f"{line}.{partner}", f"{line}.{partner + 1}")
                break

    @staticmethod
    def _bracket_partner(raw, position):
        opening = {"(": ")", "[": "]", "{": "}"}
        char = raw[position]
        if char in opening:
            depth = 0
            for scan in range(position, len(raw)):
                if raw[scan] == char:
                    depth += 1
                elif raw[scan] == opening[char]:
                    depth -= 1
                    if depth == 0:
                        return scan
        else:
            mirror = {value: key for key, value in opening.items()}[char]
            depth = 0
            for scan in range(position, -1, -1):
                if raw[scan] == char:
                    depth += 1
                elif raw[scan] == mirror:
                    depth -= 1
                    if depth == 0:
                        return scan
        return None

    def _update_hint(self):
        if not self.settings.get("hint_bar", True):
            return
        bar = self.hintbar
        bar.configure(state="normal")
        bar.delete("1.0", "end")
        line, column = self.cursor()
        raw = self.current_line_text()
        problems = self.diag_by_line.get(line)
        if problems:
            item = problems[0]
            severity = item.get("severity", "error")
            bar.insert("end", f"{icon('error' if severity == 'error' else 'warning', '!')}  ", ("error"
                       if severity == "error" else "warning",))
            bar.tag_configure("iconfont", font=icon_font(9))
            bar.tag_add("iconfont", "1.0", "1.1")
            bar.insert("end", lower(item["message"]), (severity if severity == "error" else "warning",))
        else:
            before = raw[:column]
            hint = meta.parameter_hint(before if before.strip() else raw)
            if hint and raw.strip():
                command, params, index, full = hint
                bar.insert("end", command, ("head", "mono"))
                for number, param in enumerate(params):
                    bar.insert("end", " ", ("mono",))
                    tag = "currentparam" if number == index and before.strip() != command and len(
                        before.split()) > 0 else "param"
                    bar.insert("end", param, (tag, "mono") if tag == "param" else (tag,))
                if " | " in full:
                    others = [form.strip() for form in full.split(" | ")[1:] if form.strip()]
                    bar.insert("end", "   or  " + "  or  ".join(others), ("dim", "mono"))
                explanation = meta.explain_line(raw) if self.settings.get("explain", True) else meta.summary(
                    command)
                if explanation:
                    bar.insert("end", "    " + explanation, ("explain",))
            elif raw.strip() and self.settings.get("explain", True):
                explanation = meta.explain_line(raw)
                if explanation:
                    bar.insert("end", explanation, ("explain",))
            elif not raw.strip():
                bar.insert("end", "type a command, or press ctrl+space for ideas", ("dim",))
        bar.configure(state="disabled")

    # ----- keys ------------------------------------------------------------------------
    def _bind_keys(self):
        text = self.text
        tags = list(text.bindtags())
        if "GublanKeys" not in tags:
            tags.insert(1, "GublanKeys")
            text.bindtags(tuple(tags))
        bindings = {
            "<Return>": self._on_return,
            "<KP_Enter>": self._on_return,
            "<Tab>": self._on_tab,
            "<Shift-Tab>": self._on_shift_tab,
            "<ISO_Left_Tab>": self._on_shift_tab,
            "<BackSpace>": self._on_backspace,
            "<Home>": self._on_home,
            "<Escape>": self._on_escape,
            "<Up>": lambda e: self._completion_key(e, -1),
            "<Down>": lambda e: self._completion_key(e, 1),
            "<Prior>": lambda e: self._completion_key(e, -8),
            "<Next>": lambda e: self._completion_key(e, 8),
            "<Control-space>": self._manual_completion,
            "<Control-slash>": lambda _e: self._run(self.toggle_comment),
            "<Control-d>": lambda _e: self._run(self.duplicate_line),
            "<Control-D>": lambda _e: self._run(self.duplicate_line),
            "<Alt-Up>": lambda _e: self._run(lambda: self.move_lines(-1)),
            "<Alt-Down>": lambda _e: self._run(lambda: self.move_lines(1)),
            "<Control-K>": lambda _e: self._run(self.delete_line),
            "<Control-Return>": lambda _e: self._run(lambda: self.open_line(below=True)),
            "<Control-Shift-Return>": lambda _e: self._run(lambda: self.open_line(below=False)),
            "<Control-bracketright>": lambda _e: self._run(lambda: self.indent_lines(1)),
            "<Control-bracketleft>": lambda _e: self._run(lambda: self.indent_lines(-1)),
            "<Control-l>": lambda _e: self._run(self.select_line),
            "<Control-a>": lambda _e: self._run(self.select_all),
            "<<Undo>>": lambda _e: self._run(self.undo),
            "<<Redo>>": lambda _e: self._run(self.redo),
            "<<Copy>>": self._on_copy,
            "<<Cut>>": self._on_cut,
            "<F12>": lambda _e: self._run(self.goto_definition),
            "<Control-Button-1>": self._on_ctrl_click,
            "<Motion>": self._on_motion,
            "<Leave>": lambda _e: self._hide_hover(),
            "<KeyRelease>": self._on_key_release,
            "<KeyPress>": self._on_key_press,
            "<FocusOut>": lambda _e: self.after(150, self._focus_lost),
            "<Button-1>": lambda _e: (self.close_completion(), self._hide_hover()),
            "<Control-MouseWheel>": self._on_zoom_wheel,
            "<MouseWheel>": lambda _e: (self.close_completion(), None)[1],
        }
        for sequence, handler in bindings.items():
            text.bind(sequence, handler, add="+" if sequence in ("<Button-1>", "<MouseWheel>") else "")

    def _run(self, action):
        action()
        return "break"

    def _focus_lost(self):
        focused = self.focus_get()
        if self.completion and focused is not None and str(focused).startswith(str(self.completion.window)):
            return
        self.close_completion()

    def _on_zoom_wheel(self, event):
        callback = self.hooks.get("zoom")
        if callback:
            callback(1 if event.delta > 0 else -1)
        return "break"

    def _on_escape(self, _event):
        if self.completion:
            self.close_completion()
            return "break"
        if self.find_bar and self.find_bar.winfo_ismapped():
            self.hide_find()
            return "break"
        self._hide_hover()
        return None

    def _selection_lines(self):
        ranges = self.text.tag_ranges("sel")
        if not ranges:
            line = self.cursor()[0]
            return line, line
        first = int(self.text.index(ranges[0]).split(".")[0])
        last_index = self.text.index(ranges[1])
        last = int(last_index.split(".")[0])
        if last_index.endswith(".0") and last > first:
            last -= 1
        return first, last

    def _on_return(self, event):
        if self.completion and self.completion.wants_return():
            self.completion.accept()
            return "break"
        self.close_completion()
        text = self.text
        if not self.settings.get("auto_indent", True):
            return None
        text.edit_separator()
        if text.tag_ranges("sel"):
            text.delete("sel.first", "sel.last")
        line = self.cursor()[0]
        self._dedent_closer(line)
        before = text.get("insert linestart", "insert")
        after = text.get("insert", "insert lineend")
        stripped = before.strip()
        indent = leading(before)
        word = first_word(before)
        opens = (word in meta.INDENT_OPENERS and not stripped.startswith("//")
                 and not _ASSIGN_START.match(stripped) and not after.strip())
        if not stripped:
            # leaving a line that only has spaces: keep the indent for the new line, drop it here
            text.delete("insert linestart", "insert")
            indent = before
        spaces_after = len(after) - len(after.lstrip(" \t"))
        if spaces_after:
            text.delete("insert", f"insert+{spaces_after}c")
        text.insert("insert", "\n" + indent + (self.unit() if opens else ""))
        if opens and word in BLOCK_OPENERS and self.settings.get("auto_end", True) and self._needs_end(line):
            text.insert("insert", "\n" + indent + "end")
            text.mark_set("insert", f"insert-{len(indent) + 4}c")
        text.edit_separator()
        text.see("insert")
        return "break"

    def _needs_end(self, opener_line):
        lines = self.get().split("\n")
        opener = lines[opener_line - 1]
        depth = len(leading(opener).expandtabs(self.indent_size()))
        for raw in lines[opener_line:]:
            if not raw.strip() or raw.lstrip().startswith("//"):
                continue
            level = len(leading(raw).expandtabs(self.indent_size()))
            if level > depth:
                continue
            if level < depth:
                return True
            word = first_word(raw)
            if word == "end":
                return False
            if word in meta.MIDDLE_WORDS and first_word(opener) in meta.middle_owners(word):
                continue
            return True
        return True

    def expected_indent(self, line):
        """the indentation a closing word (end, else, elseif, case, catch) on this line should have."""
        lines = self.get().split("\n")
        word = first_word(lines[line - 1])
        depth = 0
        for raw in reversed(lines[:line - 1]):
            if not raw.strip() or raw.lstrip().startswith("//"):
                continue
            current = first_word(raw)
            if current == "end":
                depth += 1
            elif current in BLOCK_OPENERS and not _ASSIGN_START.match(raw.strip()):
                if depth == 0:
                    return leading(raw)
                depth -= 1
            elif current in meta.MIDDLE_WORDS and depth == 0 and word != "end":
                return leading(raw)
        return None

    def _dedent_closer(self, line):
        raw = self.text.get(f"{line}.0", f"{line}.end")
        word = first_word(raw)
        if word not in meta.DEDENT_WORDS:
            return
        if word == "end" and raw.strip() != "end":
            return
        wanted = self.expected_indent(line)
        current = leading(raw)
        if wanted is not None and wanted != current:
            self.text.delete(f"{line}.0", f"{line}.{len(current)}")
            self.text.insert(f"{line}.0", wanted)

    def _on_tab(self, _event):
        if self.completion:
            self.completion.accept()
            return "break"
        text = self.text
        if text.tag_ranges("sel") and self._selection_lines()[0] != self._selection_lines()[1]:
            self.indent_lines(1)
            return "break"
        column = self.cursor()[1]
        size = self.indent_size()
        text.insert("insert", " " * (size - column % size))
        return "break"

    def _on_shift_tab(self, _event):
        self.indent_lines(-1)
        return "break"

    def _on_backspace(self, _event):
        text = self.text
        if text.tag_ranges("sel"):
            return None
        before = text.get("insert linestart", "insert")
        following = text.get("insert", "insert+1c")
        if before and following and before[-1] in PAIRS and PAIRS[before[-1]] == following and \
                self.settings.get("auto_pair", True):
            text.delete("insert-1c", "insert+1c")
            return "break"
        if before and not before.strip(" ") and len(before) > 0:
            size = self.indent_size()
            remove = len(before) % size or size
            text.delete(f"insert-{min(remove, len(before))}c", "insert")
            return "break"
        return None

    def _on_home(self, event):
        if event.state & 0x1:
            return None
        raw = self.current_line_text()
        column = self.cursor()[1]
        start = len(raw) - len(raw.lstrip())
        target = 0 if column == start else start
        self.text.mark_set("insert", f"insert linestart+{target}c")
        self.text.tag_remove("sel", "1.0", "end")
        self.text.see("insert")
        return "break"

    def _before_paste(self, _event):
        try:
            ranges = self.text.tag_ranges("sel")
            start = self.text.index(ranges[0] if ranges else "insert")
        except tk.TclError:
            return None
        mark = "fxpastestart"
        self.text.mark_set(mark, start)
        self.text.mark_gravity(mark, "left")

        def glow():
            try:
                if self.text.compare(mark, "<", "insert"):
                    self.effects.flash_range(mark, "insert")
                self.text.mark_unset(mark)
            except tk.TclError:
                pass

        self.after_idle(glow)
        return None

    def _typed_done(self):
        self._typing = False

    def _on_key_press(self, event):
        char = event.char
        if not char or event.state & 0x4 or event.state & 0x20000:
            return None
        if char.isprintable():
            self._typing = True
            self.after_idle(self._typed_done)
            sounds.play("type")
        text = self.text
        if char in PAIRS and self.settings.get("auto_pair", True):
            ranges = text.tag_ranges("sel")
            if ranges and char in "([{\"'":
                selected = text.get(ranges[0], ranges[1])
                text.edit_separator()
                text.delete(ranges[0], ranges[1])
                text.insert("insert", char + selected + PAIRS[char])
                return "break"
            following = text.get("insert", "insert+1c")
            previous = text.get("insert-1c", "insert") if text.compare("insert", ">", "insert linestart") else ""
            if char in ("\"", "'") and following == char:
                text.mark_set("insert", "insert+1c")
                return "break"
            if char in ("\"", "'"):
                if previous and (previous.isalnum() or previous == "_"):
                    return None
                if following and not (following.isspace() or following in ")]},"):
                    return None
            elif following and not (following.isspace() or following in ")]},"):
                return None
            text.insert("insert", char + PAIRS[char])
            text.mark_set("insert", "insert-1c")
            return "break"
        if char in CLOSERS and self.settings.get("auto_pair", True):
            if text.get("insert", "insert+1c") == char:
                text.mark_set("insert", "insert+1c")
                return "break"
        if char == " ":
            line = self.cursor()[0]
            raw = text.get(f"{line}.0", "insert")
            if raw.strip() in meta.MIDDLE_WORDS or raw.strip() == "else if":
                self._dedent_closer(line)
        return None

    def _on_key_release(self, event):
        keysym = event.keysym
        if keysym in ("Up", "Down", "Prior", "Next", "Return", "Tab", "Escape", "KP_Enter", "Shift_L",
                      "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"):
            return
        if event.state & 0x4:
            return
        if keysym in ("Left", "Right", "Home", "End"):
            self.close_completion()
            return
        if not self.settings.get("autocomplete", True):
            return
        char = event.char
        if char and (char.isalnum() or char == "_"):
            self.update_completion(auto=True)
        elif keysym == "BackSpace" and self.completion:
            self.update_completion(auto=True)
        elif char:
            self.close_completion()

    # ----- line actions ----------------------------------------------------------------------------
    def toggle_comment(self):
        first, last = self._selection_lines()
        text = self.text
        lines = [text.get(f"{n}.0", f"{n}.end") for n in range(first, last + 1)]
        code = [line for line in lines if line.strip()]
        uncomment = bool(code) and all(line.lstrip().startswith("//") for line in code)
        column = min((len(leading(line)) for line in code), default=0)
        text.edit_separator()
        for offset, line in enumerate(lines):
            number = first + offset
            if not line.strip():
                continue
            if uncomment:
                start = line.index("//")
                length = 3 if line[start:start + 3] == "// " else 2
                text.delete(f"{number}.{start}", f"{number}.{start + length}")
            else:
                text.insert(f"{number}.{column}", "// ")
        text.edit_separator()

    def duplicate_line(self):
        first, last = self._selection_lines()
        text = self.text
        block = text.get(f"{first}.0", f"{last}.end")
        line, column = self.cursor()
        text.edit_separator()
        text.insert(f"{last}.end", "\n" + block)
        text.mark_set("insert", f"{line + (last - first + 1)}.{column}")
        text.tag_remove("sel", "1.0", "end")
        text.see("insert")
        text.edit_separator()

    def move_lines(self, direction):
        first, last = self._selection_lines()
        total = self.line_count()
        if (direction < 0 and first == 1) or (direction > 0 and last >= total):
            return
        text = self.text
        line, column = self.cursor()
        block = text.get(f"{first}.0", f"{last}.end")
        text.edit_separator()
        if direction < 0:
            above = text.get(f"{first - 1}.0", f"{first - 1}.end")
            text.delete(f"{first - 1}.0", f"{last}.end")
            text.insert(f"{first - 1}.0", block + "\n" + above)
        else:
            below = text.get(f"{last + 1}.0", f"{last + 1}.end")
            text.delete(f"{first}.0", f"{last + 1}.end")
            text.insert(f"{first}.0", below + "\n" + block)
        had_selection = bool(text.tag_ranges("sel"))
        text.mark_set("insert", f"{line + direction}.{column}")
        if had_selection or first != last:
            text.tag_remove("sel", "1.0", "end")
            text.tag_add("sel", f"{first + direction}.0", f"{last + direction}.end")
        text.see("insert")
        text.edit_separator()

    def delete_line(self):
        first, last = self._selection_lines()
        text = self.text
        text.edit_separator()
        if last >= self.line_count():
            start = f"{first - 1}.end" if first > 1 else "1.0"
            text.delete(start, "end-1c")
        else:
            text.delete(f"{first}.0", f"{last + 1}.0")
        text.edit_separator()

    def open_line(self, below=True):
        text = self.text
        raw = self.current_line_text()
        indent = leading(raw)
        if below and first_word(raw) in meta.INDENT_OPENERS:
            indent += self.unit()
        if below:
            text.mark_set("insert", "insert lineend")
            text.insert("insert", "\n" + indent)
        else:
            text.mark_set("insert", "insert linestart")
            text.insert("insert", indent + "\n")
            text.mark_set("insert", "insert-1c")
        text.see("insert")

    def indent_lines(self, direction):
        first, last = self._selection_lines()
        text = self.text
        size = self.indent_size()
        text.edit_separator()
        for number in range(first, last + 1):
            raw = text.get(f"{number}.0", f"{number}.end")
            if direction > 0:
                if raw.strip():
                    text.insert(f"{number}.0", " " * size)
            else:
                spaces = len(leading(raw).expandtabs(size))
                remove = min(len(leading(raw)), spaces % size or size)
                if remove:
                    text.delete(f"{number}.0", f"{number}.{remove}")
        text.edit_separator()
        if first != last:
            text.tag_remove("sel", "1.0", "end")
            text.tag_add("sel", f"{first}.0", f"{last}.end")

    def select_line(self):
        first, last = self._selection_lines()
        self.text.tag_remove("sel", "1.0", "end")
        self.text.tag_add("sel", f"{first}.0", f"{last + 1}.0")
        self.text.mark_set("insert", f"{last + 1}.0")

    def select_all(self):
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.mark_set("insert", "end-1c")

    def undo(self):
        try:
            self.text.edit_undo()
        except tk.TclError:
            return
        self._after_bulk_change()

    def redo(self):
        try:
            self.text.edit_redo()
        except tk.TclError:
            return
        self._after_bulk_change()

    def _after_bulk_change(self):
        self.version += 1
        self._mark_dirty(1, self.line_count())
        self._schedule("gutter", 0, self.draw_gutter)
        self._schedule("symbols", 300, self.refresh_symbols)
        callback = self.hooks.get("changed")
        if callback:
            self._schedule("changed", 30, callback)
        if self.collab_listener and not self.live_applying:
            self.collab_listener()

    # ----- live sessions -------------------------------------------------------------------------------------
    def _index_of(self, text, offset):
        """a character offset in text as a tk index."""
        offset = max(0, min(offset, len(text)))
        line = text.count("\n", 0, offset) + 1
        column = offset - (text.rfind("\n", 0, offset) + 1)
        return f"{line}.{column}"

    def live_apply(self, start, end, insert):
        """put someone else's edit in, keeping your cursor and scroll where they were."""
        text = self.get()
        first, last = self._index_of(text, start), self._index_of(text, end)
        top = self.text.yview()[0]
        self.live_applying = True
        try:
            if end > start:
                self.text.delete(first, last)
            if insert:
                self.text.insert(first, insert)
        finally:
            self.live_applying = False
        self.text.yview_moveto(top)
        self._schedule("peers", 0, self.place_peer_flags)

    def live_replace_all(self, value):
        if value != self.get():
            self.live_applying = True
            try:
                self.replace_all_text(value)
            finally:
                self.live_applying = False

    def show_peers(self, peers):
        """draw other people's cursors: [(key, name, color, offset)]."""
        self.peers = list(peers)
        self.place_peer_flags()

    def place_peer_flags(self):
        """a thin caret in each person's colour, with their name in a small flag above it."""
        shown = set()
        text = self.get() if self.peers else ""
        line_height = self.font.metrics("linespace")
        for key, name, color, offset in self.peers:
            parts = self.peer_flags.get(key)
            if parts is None:
                caret = tk.Frame(self.text, bg=color, width=max(2, px(2)), height=line_height)
                flag = tk.Label(self.text, text=name, bg=color, fg=EDITOR_BG, font=theme.ui_font(7), padx=px(3),
                                pady=0, bd=0)
                parts = self.peer_flags[key] = (caret, flag)
            caret, flag = parts
            caret.configure(bg=color)
            flag.configure(text=name, bg=color)
            box = self.text.bbox(self._index_of(text, offset))
            if box is None:
                caret.place_forget()
                flag.place_forget()
                continue
            caret.configure(height=box[3])
            caret.place(x=box[0], y=box[1])
            height = flag.winfo_reqheight()
            y = box[1] - height if box[1] - height >= 0 else box[1] + box[3]
            flag.place(x=box[0], y=y)
            shown.add(key)
        current = {peer[0] for peer in self.peers}
        for key in list(self.peer_flags):
            if key not in current:
                for widget in self.peer_flags.pop(key):
                    widget.destroy()
            elif key not in shown:
                for widget in self.peer_flags[key]:
                    widget.place_forget()

    def _on_copy(self, _event):
        if self.text.tag_ranges("sel"):
            return None
        self.clipboard_clear()
        self.clipboard_append(self.current_line_text() + "\n")
        return "break"

    def _on_cut(self, _event):
        if self.text.tag_ranges("sel"):
            return None
        self.clipboard_clear()
        self.clipboard_append(self.current_line_text() + "\n")
        self.delete_line()
        return "break"

    def insert_lines(self, snippet):
        """insert code as whole lines below the cursor, matching the current indentation."""
        text = self.text
        raw = self.current_line_text()
        indent = leading(raw)
        if first_word(raw) in meta.INDENT_OPENERS:
            indent += self.unit()
        lines = snippet.rstrip("\n").split("\n")
        body = "\n".join(indent + line if line.strip() else line for line in lines)
        text.edit_separator()
        if raw.strip():
            text.mark_set("insert", "insert lineend")
            text.insert("insert", "\n" + body)
        else:
            text.delete("insert linestart", "insert lineend")
            text.insert("insert", body)
        text.edit_separator()
        text.see("insert")
        text.focus_set()

    # ----- go to definition -------------------------------------------------------------------------
    def word_at(self, index):
        text = self.text
        start = text.index(f"{index} wordstart")
        end = text.index(f"{index} wordend")
        word = text.get(start, end)
        if re.fullmatch(r"[A-Za-z_]\w*", word or ""):
            return word, start
        return None, None

    def goto_definition(self, word=None):
        if word is None:
            word, _ = self.word_at("insert")
        if not word:
            return False
        self.refresh_symbols()
        for kind in ("functions", "objects", "variables"):
            found = self.symbols[kind].get(word)
            if found:
                line = found["line"] if isinstance(found, dict) else found
                self.goto_line(line, select_line=True)
                return True
        callback = self.hooks.get("define_elsewhere")
        return bool(callback and callback(word))

    def _on_ctrl_click(self, event):
        index = self.text.index(f"@{event.x},{event.y}")
        word, _ = self.word_at(index)
        if word:
            self.after(10, lambda: self.goto_definition(word))
        return "break"

    # ----- completion -------------------------------------------------------------------------------
    def _manual_completion(self, _event=None):
        self.update_completion(auto=False)
        return "break"

    def update_completion(self, auto=True):
        text = self.text
        before = text.get("insert linestart", "insert")
        if before.lstrip().startswith("//"):
            self.close_completion()
            return
        match = _WORD_BEFORE.search(before)
        prefix = match.group(0) if match else ""
        if auto and len(prefix) < int(self.settings.get("complete_after", 1)):
            self.close_completion()
            return
        items = meta.completions(prefix, before, self.symbols)
        if not items:
            self.close_completion()
            return
        if not self.completion:
            self.completion = CompletionPopup(self)
        self.completion.show(items, prefix)

    def close_completion(self):
        if self.completion:
            self.completion.close()
            self.completion = None

    def _completion_key(self, _event, step):
        if self.completion:
            self.completion.move(step)
            return "break"
        return None

    def apply_completion(self, item, prefix):
        label, insert, kind, _detail = item
        text = self.text
        text.edit_separator()
        if prefix:
            text.delete(f"insert-{len(prefix)}c", "insert")
        before = text.get("insert linestart", "insert")
        spec = COMMAND_SPECS.get(label)
        first = not before.strip()
        if first and spec and kind == spec[0]:
            needs_args = len(spec[1].split(" | ")[0].split()) > 1
            text.insert("insert", insert + (" " if needs_args else ""))
        elif insert.endswith("()"):
            params = self.symbols["functions"].get(label, {}).get("params", [])
            text.insert("insert", insert)
            if params:
                text.mark_set("insert", "insert-1c")
        else:
            text.insert("insert", insert)
        text.edit_separator()
        self.close_completion()
        self._schedule("cursor", 0, self._cursor_moved)

    # ----- hover help ---------------------------------------------------------------------------------
    def _on_motion(self, event):
        if not self.settings.get("hover", True):
            return
        index = self.text.index(f"@{event.x},{event.y}")
        box = self.text.bbox(index)
        if not box or not (box[0] - 2 <= event.x <= box[0] + box[2] + 2 and box[1] <= event.y <= box[1] + box[3]):
            self._hide_hover()
            return
        word, start = self.word_at(index)
        key = (word, start)
        if key == self._hover_word and (self.hover or "hover" in self._jobs):
            return
        self._hide_hover()
        if not word:
            return
        self._hover_word = key
        x, y = event.x_root, event.y_root
        self._schedule("hover", 600, lambda: self._show_hover(word, start, x, y))

    def hover_info(self, word, index):
        line = int(index.split(".")[0])
        raw = self.text.get(f"{line}.0", f"{line}.end")
        is_first = first_word(raw) == word and raw.strip().startswith(word)
        is_call = self.text.get(f"{index}+{len(word)}c", f"{index}+{len(word) + 1}c") == "("
        if is_first and word in COMMAND_SPECS:
            spec = COMMAND_SPECS[word]
            return {"title": spec[1], "body": spec[3], "example": spec[4], "kind": spec[0]}
        functions = self.symbols["functions"]
        if word in functions:
            info = functions[word]
            params = " ".join(info["params"])
            return {"title": f"function {word} {params}".strip(),
                    "body": f"your function, made on line {info['line']}. ctrl+click to go there.", "kind": "function"}
        if is_call and word in EXPRESSION_FUNCTIONS:
            return {"title": f"{word}(...)", "body": EXPRESSION_FUNCTIONS[word], "kind": "math"}
        info = None
        if word in self.symbols["objects"]:
            info = {"title": word, "body": f"a shape made on line {self.symbols['objects'][word]}.",
                    "kind": "object"}
        elif word in self.symbols["variables"]:
            info = {"title": word, "body": f"a variable, first set on line {self.symbols['variables'][word]}.",
                    "kind": "variable"}
        elif word in COLORS:
            info = {"title": word, "body": "a colour name. use it with color, paint or background.", "kind": "colour"}
        elif word in meta.EXPRESSION_WORDS:
            words = {"and": "true when both sides are true.", "or": "true when either side is true.",
                     "not": "flips true and false.", "dt": "seconds since the last frame. multiply speeds by it.",
                     "pi": "3.14159..., half a turn in radians.", "true": "yes.", "false": "no.",
                     "none": "no value.", "to": "used in for loops: for i = 1 to 10",
                     "step": "used in for loops: for i = 0 to 100 step 5", "in": "used in for loops: for x in items"}
            if word in words:
                info = {"title": word, "body": words[word], "kind": "word"}
        value_of = self.hooks.get("value_of")
        if value_of:
            value = value_of(word)
            if value is not None:
                info = info or {"title": word, "body": "", "kind": "variable"}
                info["value"] = value
        return info

    def _show_hover(self, word, index, x, y):
        info = self.hover_info(word, index)
        problems = self.diag_by_line.get(int(index.split(".")[0]))
        if not info and not problems:
            return
        self.hover = popup_window(self)
        frame = tk.Frame(self.hover, bg=PANEL_ALT, highlightthickness=1, highlightbackground=MOSS_DARK)
        frame.pack()
        wrap = px(420)
        if info:
            top = tk.Frame(frame, bg=PANEL_ALT)
            top.pack(fill="x", padx=px(10), pady=(px(8), px(2)))
            tk.Label(top, text=info["title"], bg=PANEL_ALT, fg=MOSS_LIGHT, font=mono_font(10), justify="left",
                     wraplength=wrap, anchor="w").pack(side="left")
            if info.get("kind"):
                tk.Label(top, text=lower(info["kind"]), bg=PANEL_ALT, fg=DIM, font=ui_font(8)).pack(
                    side="right", padx=(px(12), 0))
            if info.get("body"):
                tk.Label(frame, text=info["body"], bg=PANEL_ALT, fg=TEXT, font=ui_font(9), justify="left",
                         wraplength=wrap, anchor="w").pack(fill="x", padx=px(10), pady=(0, px(4)))
            if info.get("example"):
                tk.Label(frame, text=info["example"], bg=theme.CODE_BG, fg=MUTED, font=mono_font(9), justify="left",
                         anchor="w", padx=px(6), pady=px(3)).pack(fill="x", padx=px(10), pady=(0, px(6)))
            if "value" in info:
                tk.Label(frame, text=f"now: {info['value']}", bg=PANEL_ALT, fg=NUMBER, font=mono_font(9),
                         justify="left", wraplength=wrap, anchor="w").pack(fill="x", padx=px(10), pady=(0, px(6)))
        for item in problems or ():
            color = ERROR if item.get("severity", "error") == "error" else NUMBER
            tk.Label(frame, text=lower(item["message"]), bg=PANEL_ALT, fg=color, font=ui_font(9), justify="left",
                     wraplength=wrap, anchor="w").pack(fill="x", padx=px(10), pady=(px(4), px(6)))
        self.hover.update_idletasks()
        width = self.hover.winfo_reqwidth()
        screen = self.winfo_screenwidth()
        self.hover.geometry(f"+{min(x + px(8), screen - width - 8)}+{y + px(18)}")
        self.hover.deiconify()

    def _hide_hover(self):
        job = self._jobs.pop("hover", None)
        if job:
            self.after_cancel(job)
        if self.hover:
            self.hover.destroy()
            self.hover = None
        self._hover_word = None

    # ----- find and replace ---------------------------------------------------------------------------
    def show_find(self, replace=False):
        if not self.find_bar:
            self.find_bar = FindBar(self)
        self.find_bar.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.find_bar.show_replace(replace)
        ranges = self.text.tag_ranges("sel")
        if ranges:
            selected = self.text.get(ranges[0], ranges[1])
            if "\n" not in selected and selected:
                self.find_bar.find_var.set(selected)
        self.find_bar.focus_find()
        self._research()

    def hide_find(self):
        if self.find_bar:
            self.find_bar.grid_remove()
        self.matches = []
        self.text.tag_remove("found", "1.0", "end")
        self.text.tag_remove("foundcurrent", "1.0", "end")
        self.text.focus_set()

    def _pattern(self):
        bar = self.find_bar
        needle = bar.find_var.get() if bar else ""
        if not needle:
            return None
        body = needle if bar.regex.get() else re.escape(needle)
        if bar.whole.get():
            body = rf"\b(?:{body})\b"
        try:
            return re.compile(body, 0 if bar.case.get() else re.IGNORECASE)
        except re.error:
            return None

    def _research(self):
        self._jobs.pop("research", None)
        text = self.text
        text.tag_remove("found", "1.0", "end")
        text.tag_remove("foundcurrent", "1.0", "end")
        self.matches = []
        if not self.find_bar or not self.find_bar.winfo_ismapped():
            return
        pattern = self._pattern()
        if pattern is None:
            self.find_bar.set_count(None if self.find_bar.find_var.get() and self.find_bar.regex.get() else 0, 0,
                                    bad=bool(self.find_bar.find_var.get()))
            return
        source = self.get()
        starts = [0]
        for match in re.finditer("\n", source):
            starts.append(match.end())

        def to_index(offset):
            line = bisect.bisect_right(starts, offset) - 1
            return f"{line + 1}.{offset - starts[line]}"

        indices = []
        for match in pattern.finditer(source):
            if match.end() == match.start():
                continue
            self.matches.append((to_index(match.start()), to_index(match.end()), match))
            if len(self.matches) >= 10000:
                break
        for start, end, _match in self.matches:
            indices.extend((start, end))
        for chunk in range(0, len(indices), 2000):
            text.tag_add("found", *indices[chunk:chunk + 2000])
        self.match_index = -1
        cursor = text.index("insert")
        for number, (start, _end, _match) in enumerate(self.matches):
            if text.compare(start, ">=", cursor):
                self.match_index = number
                break
        if self.matches and self.match_index < 0:
            self.match_index = 0
        self._mark_current(scroll=False)

    def _mark_current(self, scroll=True):
        text = self.text
        text.tag_remove("foundcurrent", "1.0", "end")
        if self.matches and 0 <= self.match_index < len(self.matches):
            start, end, _ = self.matches[self.match_index]
            text.tag_add("foundcurrent", start, end)
            if scroll:
                text.see(start)
                text.mark_set("insert", end)
        if self.find_bar:
            self.find_bar.set_count(self.match_index + 1 if self.matches else 0, len(self.matches))

    def find_step(self, step):
        if not self.matches:
            self._research()
            if not self.matches:
                return
        self.match_index = (self.match_index + step) % len(self.matches)
        self._mark_current()

    def replace_one(self):
        if not self.matches or not (0 <= self.match_index < len(self.matches)):
            self.find_step(1)
            return
        start, end, match = self.matches[self.match_index]
        replacement = self._replacement(match)
        text = self.text
        text.edit_separator()
        text.delete(start, end)
        text.insert(start, replacement)
        text.edit_separator()
        text.mark_set("insert", f"{start}+{len(replacement)}c")
        keep = self.match_index
        self._research()
        if self.matches:
            self.match_index = min(keep, len(self.matches) - 1)
            self._mark_current()

    def replace_all(self):
        if not self.matches:
            self._research()
        if not self.matches:
            return 0
        text = self.text
        count = len(self.matches)
        text.configure(autoseparators=False)
        text.edit_separator()
        for start, end, match in reversed(self.matches):
            text.delete(start, end)
            text.insert(start, self._replacement(match))
        text.edit_separator()
        text.configure(autoseparators=True)
        self._research()
        return count

    def _replacement(self, match):
        value = self.find_bar.replace_var.get()
        if self.find_bar.regex.get():
            try:
                return match.expand(value)
            except (re.error, IndexError):
                return value
        return value


class CompletionPopup:
    """the list of suggestions under the cursor."""

    ROWS = 9

    def __init__(self, editor):
        self.editor = editor
        self.window = popup_window(editor)
        self.frame = tk.Frame(self.window, bg=PANEL_ALT, highlightthickness=1, highlightbackground=MOSS_DARK)
        self.frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(self.frame, bg=PANEL_ALT, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.detail = tk.Label(self.frame, bg=theme.CODE_BG, fg=MUTED, font=ui_font(9), anchor="w", justify="left",
                               padx=px(8), pady=px(4))
        self.detail.pack(fill="x")
        self.items = []
        self.prefix = ""
        self.index = 0
        self.offset = 0
        self.navigated = False
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Double-Button-1>", lambda _e: self.accept())
        self.canvas.bind("<MouseWheel>", self._wheel)

    def show(self, items, prefix):
        changed_prefix = prefix != self.prefix
        self.items = items
        self.prefix = prefix
        if changed_prefix:
            self.index = 0
            self.offset = 0
            self.navigated = False
        self.index = min(self.index, len(items) - 1)
        self.draw()
        text = self.editor.text
        box = text.bbox("insert")
        if not box:
            self.close()
            return
        font = self.editor.font
        x = text.winfo_rootx() + box[0] - font.measure(prefix) - px(8)
        y = text.winfo_rooty() + box[1] + box[3] + px(3)
        self.window.update_idletasks()
        height = self.window.winfo_reqheight()
        width = self.window.winfo_reqwidth()
        if y + height > self.window.winfo_screenheight() - 40:
            y = text.winfo_rooty() + box[1] - height - px(3)
        x = min(x, self.window.winfo_screenwidth() - width - 8)
        self.window.geometry(f"+{max(0, x)}+{y}")
        self.window.deiconify()
        self.window.lift()

    def draw(self):
        canvas = self.canvas
        canvas.delete("all")
        row_height = px(24)
        label_font = mono_font(10)
        measure = tkfont.Font(font=label_font)
        kind_font = ui_font(8)
        visible = self.items[self.offset:self.offset + self.ROWS]
        widest = max((measure.measure(item[0]) for item in self.items[:60]), default=80)
        width = max(px(260), widest + px(120))
        canvas.configure(width=width, height=row_height * len(visible))
        for row, item in enumerate(visible):
            number = self.offset + row
            top = row * row_height
            selected = number == self.index
            if selected:
                canvas.create_rectangle(0, top, width, top + row_height, fill=SELECT, outline=SELECT)
                canvas.create_rectangle(0, top, px(2), top + row_height, fill=MOSS_LIGHT, outline=MOSS_LIGHT)
            label_text = item[0]
            matched = len(self.prefix) if label_text.lower().startswith(self.prefix.lower()) else 0
            x = px(10)
            if matched:
                canvas.create_text(x, top + row_height / 2, text=label_text[:matched], anchor="w", font=label_font,
                                   fill=MOSS_LIGHT)
                x += measure.measure(label_text[:matched])
            canvas.create_text(x, top + row_height / 2, text=label_text[matched:], anchor="w", font=label_font,
                               fill=SELECT_TEXT if selected else TEXT)
            canvas.create_text(width - px(10), top + row_height / 2, text=lower(item[2]), anchor="e",
                               font=kind_font, fill=MOSS_LIGHT if selected else DIM)
        if self.items:
            item = self.items[self.index]
            usage = COMMAND_SPECS[item[0]][1] if item[0] in COMMAND_SPECS and item[2] == COMMAND_SPECS[item[0]][0] \
                else ""
            detail = (usage + "\n" if usage else "") + lower(item[3] or "")
            self.detail.configure(text=detail.strip() or " ", wraplength=width - px(16))
        more = len(self.items) - self.ROWS
        if more > 0:
            bar_height = max(px(10), row_height * self.ROWS * self.ROWS / len(self.items))
            top = (row_height * self.ROWS - bar_height) * self.offset / max(1, more)
            canvas.create_rectangle(width - px(3), top, width, top + bar_height, fill=theme.THUMB_HOVER, outline="")

    def move(self, step):
        if not self.items:
            return
        self.navigated = True
        self.index = max(0, min(len(self.items) - 1, self.index + step))
        if self.index < self.offset:
            self.offset = self.index
        elif self.index >= self.offset + self.ROWS:
            self.offset = self.index - self.ROWS + 1
        self.draw()

    def _wheel(self, event):
        more = len(self.items) - self.ROWS
        if more > 0:
            self.offset = max(0, min(more, self.offset + (-1 if event.delta > 0 else 1)))
            self.draw()
        return "break"

    def _click(self, event):
        row = int(event.y // px(24))
        number = self.offset + row
        if 0 <= number < len(self.items):
            self.index = number
            self.navigated = True
            self.draw()
        self.editor.text.focus_set()

    def wants_return(self):
        if not self.items:
            return False
        if self.navigated:
            return True
        complete = self.prefix in COMMAND_SPECS or self.prefix in self.editor.symbols["variables"] or \
            self.prefix in meta.EXPRESSION_WORDS
        return not complete and self.editor.settings.get("enter_accepts", True)

    def accept(self):
        if self.items:
            self.editor.apply_completion(self.items[self.index], self.prefix)
        else:
            self.editor.close_completion()

    def close(self):
        try:
            self.window.destroy()
        except tk.TclError:
            pass


class FindBar(tk.Frame):
    """find and replace, shown above the code."""

    def __init__(self, editor):
        super().__init__(editor, bg=PANEL, highlightthickness=0)
        self.editor = editor
        self.find_var = tk.StringVar()
        self.replace_var = tk.StringVar()
        self.case = tk.BooleanVar(value=False)
        self.whole = tk.BooleanVar(value=False)
        self.regex = tk.BooleanVar(value=False)
        top = tk.Frame(self, bg=PANEL)
        top.pack(fill="x", padx=px(8), pady=(px(6), px(3)))
        tk.Label(top, text=icon("search", "?"), bg=PANEL, fg=DIM, font=icon_font(10), width=2).pack(side="left")
        self.find_entry = flat_entry(top, self.find_var, width=30, mono=True)
        self.find_entry.pack(side="left", fill="x", expand=True, padx=(px(4), px(6)))
        self.toggles = {}
        for key, label_text, variable, tip in (("case", "aa", self.case, "match upper and lower case"),
                                               ("whole", "ab", self.whole, "whole words only"),
                                               ("regex", ".*", self.regex, "use a regular expression")):
            button = BracketButton(top, label_text, kind="ghost", size=9, pad_x=6, pad_y=3, tooltip=tip,
                                   command=lambda v=variable, k=key: self._flip(v, k))
            button.pack(side="left", padx=(0, px(2)))
            self.toggles[key] = (button, variable)
        self.count = tk.Label(top, text="", bg=PANEL, fg=MUTED, font=ui_font(9), width=11)
        self.count.pack(side="left", padx=px(6))
        BracketButton(top, icon_name="up", kind="ghost", size=9, pad_x=6, pad_y=3, tooltip="previous (shift+enter)",
                      command=lambda: editor.find_step(-1)).pack(side="left")
        BracketButton(top, icon_name="down", kind="ghost", size=9, pad_x=6, pad_y=3, tooltip="next (enter)",
                      command=lambda: editor.find_step(1)).pack(side="left")
        BracketButton(top, icon_name="close", kind="ghost", size=9, pad_x=6, pad_y=3, tooltip="close (escape)",
                      command=editor.hide_find).pack(side="left", padx=(px(4), 0))
        self.replace_row = tk.Frame(self, bg=PANEL)
        tk.Label(self.replace_row, text=icon("refresh", ">"), bg=PANEL, fg=DIM, font=icon_font(10), width=2).pack(
            side="left")
        self.replace_entry = flat_entry(self.replace_row, self.replace_var, width=30, mono=True)
        self.replace_entry.pack(side="left", fill="x", expand=True, padx=(px(4), px(6)))
        BracketButton(self.replace_row, "replace", size=9, pad_x=8, pad_y=3, command=editor.replace_one).pack(
            side="left", padx=(0, px(4)))
        BracketButton(self.replace_row, "replace all", size=9, pad_x=8, pad_y=3, command=self._replace_all).pack(
            side="left")
        tk.Frame(self, bg=BORDER, height=1).pack(side="bottom", fill="x")
        self.find_var.trace_add("write", lambda *_: editor._schedule("research", 120, editor._research))
        for entry in (self.find_entry, self.replace_entry):
            entry.bind("<Escape>", lambda _e: (editor.hide_find(), "break")[1])
        self.find_entry.bind("<Return>", lambda _e: (editor.find_step(1), "break")[1])
        self.find_entry.bind("<Shift-Return>", lambda _e: (editor.find_step(-1), "break")[1])
        self.replace_entry.bind("<Return>", lambda _e: (editor.replace_one(), "break")[1])
        self.replace_entry.bind("<Control-Return>", lambda _e: (self._replace_all(), "break")[1])

    def _flip(self, variable, key):
        variable.set(not variable.get())
        self.toggles[key][0].set_checked(variable.get())
        self.editor._research()

    def _replace_all(self):
        count = self.editor.replace_all()
        self.count.configure(text=f"{count} replaced")

    def show_replace(self, show):
        if show:
            self.replace_row.pack(fill="x", padx=px(8), pady=(0, px(6)), before=self.winfo_children()[-1])
        else:
            self.replace_row.pack_forget()

    def focus_find(self):
        self.find_entry.focus_set()
        self.find_entry.select_range(0, "end")

    def set_count(self, current, total, bad=False):
        if bad:
            self.count.configure(text="bad pattern", fg=ERROR)
        elif not self.find_var.get():
            self.count.configure(text="", fg=MUTED)
        elif total == 0:
            self.count.configure(text="no results", fg=ERROR)
        else:
            self.count.configure(text=f"{current} of {total}", fg=MUTED)
