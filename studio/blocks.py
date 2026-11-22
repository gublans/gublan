"""blocks: every line of a program shown as a coloured block with labelled boxes for its values.

blocks and code are the same program. editing a block rewrites the code (one undo step each) and
anything blocks can't show nicely stays as a plain "code" block, so nothing is ever lost.
"""

import re
import tkinter as tk
from dataclasses import dataclass, field

from gublancore import BLOCK_MIDDLES, BLOCK_OPENERS, COLORS, COMMAND_SPECS, parse_line

from . import meta, theme
from .theme import (
    BORDER, CATEGORY_COLORS, DIM, ERROR, HOVER, MOSS, MOSS_DARK, MOSS_LIGHT, MUTED, PANEL, PANEL_ALT, SELECT,
    SELECT_TEXT, SYNTAX, TEXT, BracketButton, ScrollFrame, Tooltip, flat_entry, icon, icon_font, lower, mono_font,
    plural, px, show_menu, ui_font,
)

MAX_BLOCKS = 700
_ASSIGN_RE = re.compile(r"^([A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\[[^\]]*\])*)\s*(\+=|-=|\*=|/=|=)(?!=)\s*(.*)$")
_SET_RE = re.compile(r"^set\s+(\S+?)\s*=(?!=)\s*(.*)$")
_FOR_RANGE = re.compile(r"^([A-Za-z_]\w*)\s*=\s*(.+?)\s+to\s+(.+?)(?:\s+step\s+(.+))?$")
_FOR_IN = re.compile(r"^([A-Za-z_]\w*)\s+in\s+(.+)$")
EXPRESSION_FIELDS = {"if": "condition", "elseif": "condition", "while": "condition", "return": "value",
                     "print": "values", "popup": "message", "title": "text", "loop": "times", "wait": "seconds",
                     "until": "condition", "assert": "condition", "match": "value", "case": "values",
                     "throw": "message", "catch": "variable", "test": "name", "use": "module"}
TEXT_FIELDS = ("print", "popup", "title", "throw", "catch", "test", "use")
NEEDS_END = set(BLOCK_OPENERS)
MIDDLES = tuple(BLOCK_MIDDLES)
CLOSERS = ("end",) + MIDDLES


@dataclass
class Field:
    name: str
    optional: bool = False
    rest: bool = False
    choices: tuple = ()
    literal: str = ""
    expression: bool = False


@dataclass
class Block:
    kind: str                      # command, assign, code, comment, blank, for
    command: str = ""
    values: list = field(default_factory=list)
    raw: str = ""
    spelling: str = ""             # "else if" or "elif" when the code was written that way

    @property
    def category(self):
        if self.kind == "comment":
            return "comments"
        if self.kind in ("code", "blank"):
            return "code"
        if self.kind == "assign":
            return "basics"
        return meta.category(self.command)


def raw_tokens(text):
    """split like the language does, but keep each token exactly as written (quotes and braces too)."""
    tokens = []
    index, length = 0, len(text)
    while index < length:
        if text[index].isspace():
            index += 1
            continue
        start = index
        while index < length and not text[index].isspace():
            char = text[index]
            if char == '"' or (char == "'" and index == start):
                closing = text.find(char, index + 1)
                index = closing + 1 if closing >= 0 else index + 1
            elif char == "{":
                depth, scan, quote = 0, index, None
                while scan < length:
                    current = text[scan]
                    if quote:
                        if current == quote:
                            quote = None
                    elif current in "\"'":
                        quote = current
                    elif current == "{":
                        depth += 1
                    elif current == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    scan += 1
                index = scan + 1 if scan < length else index + 1
            else:
                index += 1
        tokens.append(text[start:index])
    return tokens


def _rest_after(text, count):
    """the raw text after the first count tokens."""
    remaining = text
    for _ in range(count):
        remaining = remaining.lstrip()
        token = raw_tokens(remaining)[:1]
        if not token:
            return ""
        remaining = remaining[len(token[0]):]
    return remaining.strip()


def fields_for(command):
    if command in EXPRESSION_FIELDS:
        return [Field(EXPRESSION_FIELDS[command], rest=True, expression=command not in TEXT_FIELDS)]
    if command == "calc":
        return [Field("variable"), Field("expression", rest=True, expression=True)]
    if command == "function":
        return [Field("name"), Field("parameters", optional=True, rest=True)]
    if command == "call":
        return [Field("name"), Field("arguments", optional=True, rest=True)]
    if command == "color":
        return [Field("colour", rest=True, choices=tuple(COLORS))]
    if command == "background":
        return [Field("colour", rest=True, choices=tuple(COLORS))]
    form = COMMAND_SPECS[command][1].split(" | ")[0]
    result = []
    for word in form.split()[1:]:
        if word.startswith(("<", "[")):
            optional = word.startswith("[")
            name = word.strip("<>[]")
            rest = name.endswith("...")
            name = name.rstrip(".")
            choices = ()
            if name in ("color", "colour"):
                choices = tuple(COLORS)
            elif name == "key-name":
                choices = tuple(name for name in meta.KEY_NAMES if " " not in name)
            elif "|" in name:
                choices = tuple(part for part in name.split("|") if part != "object")
                name = name.split("|")[0]
            result.append(Field(name, optional=optional, rest=rest, choices=choices))
        elif "|" in word:
            choices = tuple(word.split("|"))
            result.append(Field("choice", choices=choices))
        else:
            result.append(Field(word, literal=word))
    if result and not result[-1].rest:
        result[-1].rest = True  # anything extra stays with the last box so no text is lost
    return result


def parse_block(raw):
    stripped = raw.strip()
    if not stripped:
        return Block("blank")
    if stripped.startswith("//"):
        return Block("comment", values=[stripped[2:].strip()])
    try:
        parsed = parse_line(stripped)
    except (ValueError, IndexError):
        parsed = None
    if parsed is None or parsed.error:
        return Block("code", raw=stripped)
    word = raw_tokens(stripped)[0]
    if parsed.cmd == "elseif" and word != "elseif":
        return Block("command", "elseif", [parsed.rest], spelling=_elseif_spelling(stripped))
    if word not in COMMAND_SPECS or parsed.cmd in ("add", "sub", "mul", "div", "set") and word != parsed.cmd:
        match = _ASSIGN_RE.match(stripped)
        if match and word not in COMMAND_SPECS:
            target, operator, value = match.groups()
            return Block("assign", values=[target, operator, value])
        if parsed.cmd == "elseif":
            return Block("command", "elseif", [parsed.rest], raw=stripped, spelling=_elseif_spelling(stripped))
        return Block("code", raw=stripped)
    command = word
    if command == "set":
        match = _SET_RE.match(stripped)
        if match:
            return Block("assign", "set", [match.group(1), "=", match.group(2)])
        return Block("code", raw=stripped)
    if command == "for":
        rest = stripped[3:].strip()
        match = _FOR_RANGE.match(rest)
        if match:
            name, start, stop, step = match.groups()
            return Block("for", "for", [name, start, stop, step or ""])
        match = _FOR_IN.match(rest)
        if match:
            return Block("for", "for-in", [match.group(1), match.group(2)])
        return Block("code", raw=stripped)
    fields = fields_for(command)
    values = []
    position = 1
    tokens = raw_tokens(stripped)
    for number, item in enumerate(fields):
        if item.literal:
            if position < len(tokens) and tokens[position] == item.literal:
                position += 1
            values.append(item.literal)
            continue
        if item.rest or number == len(fields) - 1:
            values.append(_rest_after(stripped, position))
            position = len(tokens)
        else:
            values.append(tokens[position] if position < len(tokens) else "")
            position += 1
    return Block("command", command, values)


def _elseif_spelling(text):
    if text.startswith("elif"):
        return "elif"
    return "else if" if re.match(r"else\s+if\b", text) else ""


def parse_blocks(source):
    return [parse_block(line) for line in source.splitlines()]


def block_line(block):
    if block.kind == "blank":
        return ""
    if block.kind == "comment":
        return ("// " + block.values[0]).rstrip() if block.values and block.values[0] else "//"
    if block.kind == "code":
        return block.raw
    if block.kind == "assign":
        target, operator, value = (block.values + ["", "", ""])[:3]
        prefix = "set " if block.command == "set" else ""
        return f"{prefix}{target.strip() or 'value'} {operator} {value.strip()}".rstrip()
    if block.kind == "for":
        if block.command == "for-in":
            name, items = (block.values + ["", ""])[:2]
            return f"for {name.strip() or 'item'} in {items.strip()}".rstrip()
        name, start, stop, step = (block.values + ["", "", "", ""])[:4]
        line = f"for {name.strip() or 'i'} = {start.strip() or '1'} to {stop.strip() or '10'}"
        return line + (f" step {step.strip()}" if step.strip() else "")
    parts = [block.spelling or block.command] + [value.strip() for value in block.values if value and value.strip()]
    return " ".join(parts)


def blocks_source(blocks, unit="    "):
    lines = []
    depth = 0
    for block in blocks:
        command = block.command if block.kind in ("command", "for") else ""
        if block.kind == "for":
            command = "for"
        if command in CLOSERS:
            depth = max(0, depth - 1)
        text = block_line(block)
        lines.append(unit * depth + text if text else "")
        if command in NEEDS_END or command in MIDDLES:
            depth += 1
    return "\n".join(lines) + "\n"


def block_ranges(blocks):
    """index of each opener's end (so a whole if ... end can be moved or deleted together)."""
    ends = {}
    stack = []
    for index, block in enumerate(blocks):
        command = "for" if block.kind == "for" else block.command if block.kind == "command" else ""
        if command in NEEDS_END:
            stack.append(index)
        elif command == "end" and stack:
            ends[stack.pop()] = index
    return ends


def new_block(command):
    """a fresh block (and its end, for blocks that hold other blocks) built from the command's example."""
    example = COMMAND_SPECS[command][4].split("\n")[0] if command in COMMAND_SPECS else command
    if command in ("end", "else", "forever", "break", "continue", "clear", "frame", "kill", "stopmusic",
                   "stopsounds", "try"):
        example = command
    block = parse_block(example)
    if block.kind == "code" or (block.command != command and block.kind == "command"):
        block = parse_block(command)
    blocks = [block]
    if command in NEEDS_END:
        blocks.append(Block("command", "end", []))
    return blocks


# ----- the view ---------------------------------------------------------------------------
class BlocksView(tk.Frame):
    def __init__(self, parent, on_change, settings, hooks=None):
        super().__init__(parent, bg=PANEL)
        self.on_change = on_change
        self.settings = settings
        self.hooks = hooks or {}
        self.blocks = []
        self.rows = []
        self.selected = None
        self.last_source = None
        self.category = "basics"
        self.drag = None
        self._push_job = None
        self.objects = []

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_palette()
        self.palette_line = tk.Frame(self, bg=BORDER, width=1)
        self.palette_line.grid(row=0, column=0, sticky="nse")
        right = tk.Frame(self, bg=PANEL)
        right.grid(row=0, column=1, sticky="nsew")
        head = tk.Frame(right, bg=PANEL)
        head.pack(fill="x", padx=px(12), pady=(px(8), px(4)))
        self.add_button = BracketButton(head, "add a block", icon_name="add", size=9, command=self._add_from_button,
                                        bg=PANEL)
        self.head_hint = tk.Label(head, text="", bg=PANEL, fg=DIM, font=ui_font(9), anchor="w")
        self.head_hint.pack(side="left", fill="x", expand=True)
        self.count_label = tk.Label(head, text="", bg=PANEL, fg=DIM, font=ui_font(9))
        self.count_label.pack(side="right")
        # when the view is narrow (split view) the palette folds away into the 'add a block' button
        self.compact = None
        self._set_compact(False)
        self.bind("<Configure>", self._on_resize, add="+")
        self.scroll = ScrollFrame(right, bg=PANEL)
        self.scroll.pack(fill="both", expand=True)
        self.list = self.scroll.inner
        self.indicator = tk.Frame(self.list, bg=MOSS_LIGHT, height=px(2))
        self.bind_all_keys()

    # ----- palette ----------------------------------------------------------------------
    def _on_resize(self, event):
        if event.widget is self:
            self._set_compact(event.width < px(640))

    def _set_compact(self, compact):
        if compact == self.compact:
            return
        self.compact = compact
        if compact:
            self.palette.grid_remove()
            self.palette_line.grid_remove()
            self.add_button.pack(side="left", padx=(0, px(10)), before=self.head_hint)
            self.head_hint.configure(text="adds below the selected line")
        else:
            self.palette.grid()
            self.palette_line.grid()
            self.add_button.pack_forget()
            self.head_hint.configure(text="click a block on the left to add it below the selected one, or drag it "
                                          "into place.")

    def _add_from_button(self):
        self._add_menu(self.add_button)

    def _build_palette(self):
        palette = self.palette = tk.Frame(self, bg=PANEL, width=px(230))
        palette.grid(row=0, column=0, sticky="nsw")
        palette.grid_propagate(False)
        palette.pack_propagate(False)
        self.search_var = tk.StringVar()
        search = flat_entry(palette, self.search_var, width=18)
        search.pack(fill="x", padx=px(10), pady=(px(10), px(6)))
        self._placeholder(search, "search blocks")
        self.search_var.trace_add("write", lambda *_: self._fill_palette())
        cats = tk.Frame(palette, bg=PANEL)
        cats.pack(fill="x", padx=px(10))
        self.category_buttons = {}
        groups = meta.commands_by_category()
        for number, name in enumerate(groups):
            button = tk.Label(cats, text=lower(name), bg=PANEL, fg=MUTED, font=ui_font(9), anchor="w", padx=px(6),
                              pady=px(2), cursor="hand2")
            button.grid(row=number // 2, column=number % 2, sticky="ew", padx=(0, px(2)), pady=px(1))
            button.bind("<Button-1>", lambda _e, n=name: self.choose_category(n))
            self.category_buttons[name] = button
        cats.columnconfigure(0, weight=1)
        cats.columnconfigure(1, weight=1)
        tk.Frame(palette, bg=BORDER, height=1).pack(fill="x", padx=px(10), pady=px(8))
        self.palette_about = tk.Label(palette, text="", bg=PANEL, fg=DIM, font=ui_font(9), anchor="w",
                                      justify="left", wraplength=px(205))
        self.palette_about.pack(fill="x", padx=px(10))
        self.palette_scroll = ScrollFrame(palette, bg=PANEL)
        self.palette_scroll.pack(fill="both", expand=True, pady=(px(4), 0))
        self.choose_category("basics")

    def _placeholder(self, entry, text):
        def show(_event=None):
            if not entry.get():
                entry.insert(0, text)
                entry.configure(fg=DIM)

        def hide(_event=None):
            if entry.cget("fg") == DIM:
                entry.delete(0, "end")
                entry.configure(fg=TEXT)

        entry.bind("<FocusIn>", hide)
        entry.bind("<FocusOut>", show)
        self._placeholder_text = text
        show()

    def choose_category(self, name):
        self.category = name
        for key, button in self.category_buttons.items():
            on = key == name
            color = CATEGORY_COLORS.get(key, MOSS_LIGHT)
            button.configure(bg=SELECT if on else PANEL, fg=color if on else MUTED)
        self._fill_palette()

    def _fill_palette(self):
        inner = self.palette_scroll.inner
        for child in inner.winfo_children():
            child.destroy()
        query = self.search_var.get().strip().lower()
        if query == getattr(self, "_placeholder_text", None):
            query = ""
        groups = meta.commands_by_category()
        if query:
            names = [name for name, spec in COMMAND_SPECS.items()
                     if query in name or query in spec[3].lower()]
            self.palette_about.configure(text=f"{plural(len(names), 'block')} matching '{query}'")
        else:
            names = groups.get(self.category, [])
            self.palette_about.configure(text=meta.CATEGORY_ABOUT.get(self.category, ""))
        for name in names:
            color = CATEGORY_COLORS.get(meta.category(name), MOSS_LIGHT)
            chip = tk.Frame(inner, bg=PANEL_ALT, cursor="hand2")
            chip.pack(fill="x", padx=(px(10), px(6)), pady=px(2))
            tk.Frame(chip, bg=color, width=px(4)).pack(side="left", fill="y")
            title = tk.Label(chip, text=name, bg=PANEL_ALT, fg=color, font=mono_font(10, "bold"), anchor="w")
            title.pack(side="top", fill="x", padx=px(8), pady=(px(4), 0))
            about = tk.Label(chip, text=meta.summary(name), bg=PANEL_ALT, fg=DIM, font=ui_font(8), anchor="w",
                             justify="left", wraplength=px(180))
            about.pack(side="top", fill="x", padx=px(8), pady=(0, px(4)))
            Tooltip(chip, meta.usage(name))
            for widget in (chip, title, about):
                widget.bind("<ButtonPress-1>", lambda e, n=name: self._palette_press(e, n))
                widget.bind("<B1-Motion>", self._drag_motion)
                widget.bind("<ButtonRelease-1>", self._drag_release)
                widget.bind("<Enter>", lambda _e, c=chip: self._chip_hover(c, True))
                widget.bind("<Leave>", lambda _e, c=chip: self._chip_hover(c, False))
        self.palette_scroll.bind_tree(inner)
        self.palette_scroll.to_top()

    @staticmethod
    def _chip_hover(chip, on):
        for widget in [chip] + chip.winfo_children():
            if isinstance(widget, tk.Label) or widget is chip:
                widget.configure(bg=HOVER if on else PANEL_ALT)

    # ----- loading and saving ---------------------------------------------------------------
    def load(self, source, force=False):
        if not force and source == self.last_source:
            return
        self.last_source = source
        self.blocks = parse_blocks(source)
        self.objects = list(meta.collect_symbols(source)["objects"])
        self.render()

    def source(self):
        return blocks_source(self.blocks, " " * int(self.settings.get("indent", 4)))

    def push(self, now=False):
        if self._push_job:
            self.after_cancel(self._push_job)
            self._push_job = None
        if not now:
            self._push_job = self.after(350, lambda: self.push(True))
            return
        source = self.source()
        self.last_source = source
        self.on_change(source)

    # ----- rendering ------------------------------------------------------------------------
    def render(self):
        top = self.scroll.canvas.yview()[0]
        for child in self.list.winfo_children():
            if child is not self.indicator:
                child.destroy()
        self.rows = []
        shown = self.blocks[:MAX_BLOCKS]
        depth = 0
        for index, block in enumerate(shown):
            command = "for" if block.kind == "for" else block.command if block.kind == "command" else ""
            if command in CLOSERS:
                depth = max(0, depth - 1)
            self.rows.append(self._make_row(index, block, depth))
            if command in NEEDS_END or command in MIDDLES:
                depth += 1
        if len(self.blocks) > MAX_BLOCKS:
            tk.Label(self.list, text=f"only the first {MAX_BLOCKS} of {len(self.blocks)} lines are shown as blocks. "
                     "use the code view for the rest.", bg=PANEL, fg=MUTED, font=ui_font(9)).pack(
                anchor="w", padx=px(14), pady=px(8))
        if not self.blocks:
            tk.Label(self.list, text="no blocks yet. add one to start.", bg=PANEL, fg=DIM,
                     font=ui_font(10)).pack(anchor="w", padx=px(14), pady=px(20))
        add = BracketButton(self.list, "add a block", icon_name="add", kind="ghost", size=9)
        add.command = lambda: self._add_menu(add)
        add.pack(anchor="w", padx=px(14), pady=px(10))
        self.count_label.configure(text=plural(len(self.blocks), 'line'))
        self.scroll.bind_tree(self.list)
        self.update_idletasks()
        self.scroll.canvas.yview_moveto(top)
        if self.selected is not None and self.selected < len(self.rows):
            self._paint_selection()

    def _make_row(self, index, block, depth):
        category = block.category
        color = CATEGORY_COLORS.get(category, MOSS_LIGHT)
        body_bg = PANEL if block.kind in ("blank", "comment") else PANEL_ALT
        row = tk.Frame(self.list, bg=PANEL)
        row.pack(fill="x", padx=(px(12), px(12)), pady=px(1))
        if depth:
            guide = tk.Canvas(row, width=depth * px(22), height=1, bg=PANEL, highlightthickness=0)
            guide.pack(side="left", fill="y")
            guide.bind("<Configure>", lambda e, c=guide, d=depth: self._draw_guides(c, d, e.height))
        body = tk.Frame(row, bg=body_bg)
        body.pack(side="left", fill="x", expand=block.kind in ("code", "comment", "blank"))
        row.body = body
        row.index = index
        tk.Frame(body, bg=color if block.kind != "blank" else PANEL, width=px(4)).pack(side="left", fill="y")
        handle = tk.Label(body, text=icon("more", "::"), bg=body_bg, fg=DIM, font=icon_font(9), cursor="fleur",
                          padx=px(4))
        handle.pack(side="left")
        handle.bind("<ButtonPress-1>", lambda e, i=index: self._row_press(e, i))
        handle.bind("<B1-Motion>", self._drag_motion)
        handle.bind("<ButtonRelease-1>", self._drag_release)
        for widget in (row, body):
            widget.bind("<Button-1>", lambda _e, i=index: self.select(i), add="+")
        if block.kind == "blank":
            spacer = tk.Label(body, text="", bg=body_bg, font=ui_font(4), width=40)
            spacer.pack(side="left")
            spacer.bind("<Button-1>", lambda _e, i=index: self.select(i))
        elif block.kind == "comment":
            self._entry(body, block, 0, "note", width=60, color=SYNTAX["comment"], prefix="//", fill=True)
        elif block.kind == "code":
            tk.Label(body, text="code", bg=body_bg, fg=color, font=mono_font(10, "bold")).pack(side="left",
                                                                                                padx=(px(2), px(6)))
            self._entry(body, block, None, "", width=60, mono=True, fill=True)
        elif block.kind == "assign":
            if block.command == "set":
                self._word(body, "set", color, body_bg)
            self._entry(body, block, 0, "variable", width=10)
            operator = block.values[1] if len(block.values) > 1 else "="
            names = {"=": "=", "+=": "+=", "-=": "-=", "*=": "*=", "/=": "/="}
            op = tk.Label(body, text=names.get(operator, operator), bg=body_bg, fg=SYNTAX["operator"],
                          font=mono_font(10), cursor="hand2", padx=px(4))
            op.pack(side="left")
            op.bind("<Button-1>", lambda _e, b=block, w=op: self._choose_operator(b, w))
            self._entry(body, block, 2, "value", width=18, mono=True)
        elif block.kind == "for":
            self._word(body, "for", color, body_bg)
            if block.command == "for-in":
                self._entry(body, block, 0, "item", width=6)
                self._word(body, "in", DIM, body_bg, small=True)
                self._entry(body, block, 1, "list", width=14, mono=True)
            else:
                self._entry(body, block, 0, "name", width=4)
                self._word(body, "from", DIM, body_bg, small=True)
                self._entry(body, block, 1, "start", width=4, mono=True)
                self._word(body, "to", DIM, body_bg, small=True)
                self._entry(body, block, 2, "end", width=6, mono=True)
                self._word(body, "step", DIM, body_bg, small=True)
                self._entry(body, block, 3, "1", width=3, mono=True)
        else:
            self._word(body, block.command, color, body_bg)
            for number, item in enumerate(fields_for(block.command) if block.command in COMMAND_SPECS else []):
                if item.literal:
                    self._word(body, item.literal, DIM, body_bg, small=True)
                    continue
                value = block.values[number] if number < len(block.values) else ""
                self._word(body, item.name, DIM, body_bg, small=True)
                width = max(4, min(34, len(value) + 2))
                if item.rest:
                    width = max(width, 12)
                self._entry(body, block, number, item.name, width=width, mono=item.expression or item.rest,
                            choices=self._choices(item), path=item.name == "path")
        remove = tk.Label(body, text=icon("close", "x"), bg=body_bg, fg=DIM, font=icon_font(8), cursor="hand2",
                          padx=px(6))
        remove.pack(side="right")
        remove.bind("<Button-1>", lambda _e, i=index: self.remove(i))
        remove.bind("<Enter>", lambda _e, w=remove: w.configure(fg=ERROR))
        if block.kind == "blank":
            # empty lines stay quiet: their remove button only shows while the pointer is on the row
            remove.configure(fg=body_bg)
            remove.bind("<Leave>", lambda _e, w=remove: w.configure(fg=body_bg))
            row.bind("<Enter>", lambda _e, w=remove: w.configure(fg=DIM), add="+")
            row.bind("<Leave>", lambda _e, w=remove: w.configure(fg=body_bg), add="+")
        else:
            remove.bind("<Leave>", lambda _e, w=remove: w.configure(fg=DIM))
        return row

    def _choices(self, item):
        if item.choices:
            return item.choices
        if item.name in ("object", "object-a", "object-b"):
            return tuple(self.objects) + (("all",) if item.name == "object" else ())
        return ()

    @staticmethod
    def _draw_guides(canvas, depth, height):
        canvas.delete("all")
        for level in range(depth):
            x = level * px(22) + px(10)
            canvas.create_line(x, 0, x, height, fill=BORDER)

    @staticmethod
    def _word(parent, text, color, bg, small=False):
        label = tk.Label(parent, text=text, bg=bg, fg=color, font=ui_font(8) if small else mono_font(10, "bold"),
                         padx=px(3) if small else px(4))
        label.pack(side="left", pady=px(4))
        return label

    def _entry(self, parent, block, index, hint, width=10, mono=False, color=TEXT, prefix=None, fill=False,
               choices=(), path=False):
        if prefix:
            tk.Label(parent, text=prefix, bg=parent.cget("bg"), fg=color, font=mono_font(10)).pack(side="left")
        variable = tk.StringVar(value=block.raw if index is None else (
            block.values[index] if index < len(block.values) else ""))
        entry = tk.Entry(parent, textvariable=variable, width=width, bg=theme.FIELD_BG, fg=color, insertbackground=TEXT,
                         relief="flat", highlightthickness=1, highlightbackground=BORDER, highlightcolor=MOSS,
                         selectbackground=SELECT, selectforeground=SELECT_TEXT, bd=px(2),
                         font=mono_font(10) if mono else ui_font(10))
        entry.pack(side="left", padx=(0, px(4)), pady=px(4), fill="x" if fill else None, expand=fill)
        if hint:
            Tooltip(entry, hint)

        def changed(*_):
            value = variable.get()
            if index is None:
                block.raw = value
            else:
                while len(block.values) <= index:
                    block.values.append("")
                block.values[index] = value
            if not fill:
                entry.configure(width=max(width if len(value) < width else 3, min(40, len(value) + 2)))
            self.push()

        variable.trace_add("write", changed)
        entry.bind("<FocusIn>", lambda _e, i=block: self.select(self.blocks.index(i) if i in self.blocks else None,
                                                                    focus=False))
        if choices:
            arrow = tk.Label(parent, text=icon("down", "v"), bg=parent.cget("bg"), fg=MUTED, font=icon_font(7),
                             cursor="hand2", padx=px(2))
            arrow.pack(side="left", padx=(0, px(6)))
            arrow.bind("<Button-1>", lambda _e, v=variable, w=entry, c=choices: show_menu(
                w, [(choice, lambda x=choice, var=v: var.set(x)) for choice in c[:40]]))
        if path and self.hooks.get("pick_asset"):
            folder = tk.Label(parent, text=icon("folder", "..."), bg=parent.cget("bg"), fg=MUTED, font=icon_font(9),
                              cursor="hand2", padx=px(2))
            folder.pack(side="left", padx=(0, px(6)))
            Tooltip(folder, "choose a file")

            def pick(_event=None, v=variable):
                chosen = self.hooks["pick_asset"]()
                if chosen:
                    v.set(f'"{chosen}"' if " " in chosen else chosen)

            folder.bind("<Button-1>", pick)
        return entry

    def _choose_operator(self, block, widget):
        options = [("=  set to", "="), ("+=  add", "+="), ("-=  take away", "-="), ("*=  multiply", "*="),
                   ("/=  divide", "/=")]

        def choose(value):
            block.values[1] = value
            widget.configure(text=value)
            self.push(True)

        show_menu(widget, [(label_text, lambda v=value: choose(v)) for label_text, value in options])

    # ----- selection and editing ----------------------------------------------------------------
    def select(self, index, focus=True):
        self.selected = index
        self._paint_selection()
        if focus:
            self.focus_set()

    def _paint_selection(self):
        for row in self.rows:
            on = row.index == self.selected
            try:
                row.configure(bg=MOSS_DARK if on else PANEL)
                row.configure(highlightthickness=0)
                row.pack_configure(pady=px(1))
            except tk.TclError:
                pass

    def bind_all_keys(self):
        self.bind("<Delete>", lambda _e: self.selected is not None and self.remove(self.selected))
        self.bind("<Up>", lambda _e: self._move_selection(-1))
        self.bind("<Down>", lambda _e: self._move_selection(1))
        self.bind("<Control-Up>", lambda _e: self.selected is not None and self.move_block(self.selected, -1))
        self.bind("<Control-Down>", lambda _e: self.selected is not None and self.move_block(self.selected, 1))

    def _move_selection(self, step):
        if not self.rows:
            return
        current = self.selected if self.selected is not None else -1
        self.select(max(0, min(len(self.rows) - 1, current + step)))

    def _span(self, index):
        ends = block_ranges(self.blocks)
        return index, ends.get(index, index)

    def insert_blocks(self, items, at=None):
        if at is None:
            at = len(self.blocks) if self.selected is None else self.selected + 1
        at = max(0, min(at, len(self.blocks)))
        self.blocks[at:at] = items
        self.selected = at
        self.push(True)
        self.render()
        self._focus_first_entry(at)

    def _focus_first_entry(self, index):
        if index >= len(self.rows):
            return
        for widget in self.rows[index].body.winfo_children():
            if isinstance(widget, tk.Entry):
                widget.focus_set()
                widget.select_range(0, "end")
                break

    def add_command(self, command, at=None):
        self.insert_blocks(new_block(command), at)

    def remove(self, index):
        if index is None or index >= len(self.blocks):
            return
        start, end = self._span(index)
        block = self.blocks[index]
        if block.kind == "command" and block.command in ("end",):
            return
        del self.blocks[start:end + 1]
        self.selected = min(start, len(self.blocks) - 1) if self.blocks else None
        self.push(True)
        self.render()

    def move_block(self, index, step):
        start, end = self._span(index)
        if step < 0 and start == 0 or step > 0 and end >= len(self.blocks) - 1:
            return
        chunk = self.blocks[start:end + 1]
        del self.blocks[start:end + 1]
        target = start - 1 if step < 0 else start + 1
        self.blocks[target:target] = chunk
        self.selected = target
        self.push(True)
        self.render()

    def _add_menu(self, anchor=None):
        groups = meta.commands_by_category()
        items = [(name, [(command, lambda c=command: self.add_command(c)) for command in commands])
                 for name, commands in groups.items()]
        show_menu(anchor or (self.rows[-1] if self.rows else self.list), items)

    # ----- drag and drop --------------------------------------------------------------------------
    def _row_press(self, event, index):
        block = self.blocks[index]
        self.select(index, focus=True)
        if block.kind == "command" and block.command in CLOSERS:
            self.drag = None
            return
        self.drag = {"kind": "row", "index": index, "x": event.x_root, "y": event.y_root, "moved": False}

    def _palette_press(self, event, command):
        self.drag = {"kind": "palette", "command": command, "x": event.x_root, "y": event.y_root, "moved": False}

    def _gap_at(self, y_root):
        for row in self.rows:
            top = row.winfo_rooty()
            if y_root < top + row.winfo_height() / 2:
                return row.index
        return len(self.rows)

    def _drag_motion(self, event):
        if not self.drag:
            return
        if abs(event.y_root - self.drag["y"]) + abs(event.x_root - self.drag["x"]) > 6:
            self.drag["moved"] = True
        if not self.drag["moved"]:
            return
        list_x = self.scroll.winfo_rootx()
        inside = list_x <= event.x_root <= list_x + self.scroll.winfo_width()
        if not inside:
            self.indicator.place_forget()
            return
        gap = self._gap_at(event.y_root)
        if gap < len(self.rows):
            y = self.rows[gap].winfo_y() - px(1)
        elif self.rows:
            last = self.rows[-1]
            y = last.winfo_y() + last.winfo_height()
        else:
            y = px(4)
        self.indicator.place(x=px(10), y=y, relwidth=1.0, width=-px(20), height=px(2))
        self.indicator.lift()
        # scroll when dragging near the edges
        canvas = self.scroll.canvas
        top = canvas.winfo_rooty()
        if event.y_root < top + px(30):
            canvas.yview_scroll(-1, "units")
        elif event.y_root > top + canvas.winfo_height() - px(30):
            canvas.yview_scroll(1, "units")

    def _drag_release(self, event):
        drag, self.drag = self.drag, None
        self.indicator.place_forget()
        if not drag:
            return
        if not drag["moved"]:
            if drag["kind"] == "palette":
                self.add_command(drag["command"])
            return
        list_x = self.scroll.winfo_rootx()
        if not list_x <= event.x_root <= list_x + self.scroll.winfo_width():
            return
        gap = self._gap_at(event.y_root)
        if drag["kind"] == "palette":
            self.add_command(drag["command"], at=gap)
            return
        start, end = self._span(drag["index"])
        if start <= gap <= end + 1:
            return
        chunk = self.blocks[start:end + 1]
        del self.blocks[start:end + 1]
        if gap > end:
            gap -= len(chunk)
        self.blocks[gap:gap] = chunk
        self.selected = gap
        self.push(True)
        self.render()


def parseblocksource(source):
    """blocks for a program: one per line. lines blocks can't show stay as code blocks."""
    return parse_blocks(source)
