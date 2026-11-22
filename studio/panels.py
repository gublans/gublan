"""the side and bottom panels: output, problems, variables, help, files, outline and assets."""

import os
import re
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import ttk

from gublancore import COMMAND_SPECS, EXPRESSION_FUNCTIONS, format_value, kind_of

from . import meta, theme
from .guides import GUIDES
from .theme import (
    BORDER, DIM, EDITOR_BG, ERROR, MOSS_LIGHT, MUTED, NUMBER, PANEL,
    PANEL_ALT, SELECT, TEXT, BracketButton, Tooltip, flat_entry, lower,
    mono_font, plural, px, scrollbar, show_menu, ui_font,
)

MEDIA_IMAGES = (".png", ".gif", ".jpg", ".jpeg", ".bmp", ".webp")
MEDIA_SOUNDS = (".wav", ".ogg", ".mp3", ".flac")


def panel_header(parent, title, actions=()):
    bar = tk.Frame(parent, bg=PANEL)
    bar.pack(fill="x")
    tk.Label(bar, text=lower(title), bg=PANEL, fg=MUTED, font=ui_font(9, "bold"), anchor="w").pack(
        side="left", padx=px(12), pady=px(6))
    for icon_name, tip, command in reversed(actions):
        BracketButton(bar, icon_name=icon_name, kind="ghost", size=9, pad_x=5, pad_y=3, tooltip=tip,
                      command=command).pack(side="right", padx=(0, px(4)))
    return bar


def tree(parent, columns, headings=None, show="tree headings"):
    frame = tk.Frame(parent, bg=PANEL)
    widget = ttk.Treeview(frame, columns=columns, style="Flat.Treeview", show=show, selectmode="browse")
    bar = scrollbar(frame, "vertical", widget.yview)
    widget.configure(yscrollcommand=bar.set)
    widget.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")
    for column, heading in zip(columns, headings or columns):
        widget.heading(column, text=lower(heading), anchor="w")
    widget.tag_configure("error", foreground=ERROR)
    widget.tag_configure("warning", foreground=NUMBER)
    widget.tag_configure("dim", foreground=DIM)
    widget.tag_configure("moss", foreground=MOSS_LIGHT)
    widget.tag_configure("changed", foreground=NUMBER)
    return frame, widget


# ----- output --------------------------------------------------------------------------------
class OutputPanel(tk.Frame):
    """what programs print, their questions and a quick console."""

    def __init__(self, parent, on_console=None):
        super().__init__(parent, bg=EDITOR_BG)
        self.on_console = on_console
        self.answer_callback = None
        self.history = []
        self.history_index = 0
        self.text = tk.Text(self, bg=EDITOR_BG, fg=TEXT, relief="flat", borderwidth=0, highlightthickness=0,
                            font=mono_font(10), wrap="word", padx=px(12), pady=px(8), state="disabled",
                            selectbackground=SELECT, inactiveselectbackground=SELECT, cursor="xterm")
        bar = scrollbar(self, "vertical", self.text.yview)
        self.text.configure(yscrollcommand=bar.set)
        for tag, color in (("error", ERROR), ("info", DIM), ("answer", MOSS_LIGHT), ("question", TEXT),
                           ("system", MUTED), ("good", MOSS_LIGHT), ("console", NUMBER)):
            self.text.tag_configure(tag, foreground=color)
        self.text.tag_configure("link", foreground=MOSS_LIGHT, underline=True)
        self.text.tag_bind("link", "<Enter>", lambda _e: self.text.configure(cursor="hand2"))
        self.text.tag_bind("link", "<Leave>", lambda _e: self.text.configure(cursor="xterm"))
        self.text.tag_bind("link", "<Button-1>", self._link_click)
        self.on_link = None
        self.input_row = tk.Frame(self, bg=PANEL)
        self.prompt = tk.Label(self.input_row, text="", bg=PANEL, fg=TEXT, font=mono_font(10), anchor="w")
        self.prompt.pack(side="left", padx=(px(12), px(6)))
        self.answer = flat_entry(self.input_row, width=40, mono=True)
        self.answer.pack(side="left", fill="x", expand=True, pady=px(6))
        self.answer.bind("<Return>", self._submit)
        BracketButton(self.input_row, "answer", kind="accent", size=9, pad_x=10, pad_y=3,
                      command=self._submit).pack(side="left", padx=px(8))
        self.console_row = tk.Frame(self, bg=PANEL)
        tk.Label(self.console_row, text=">", bg=PANEL, fg=MOSS_LIGHT, font=mono_font(10)).pack(
            side="left", padx=(px(12), px(6)))
        self.console = tk.Entry(self.console_row, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat",
                                highlightthickness=0, font=mono_font(10), bd=0)
        self.console.pack(side="left", fill="x", expand=True, pady=px(6))
        self.console_hint = tk.Label(self.console_row, text="quick console: type a line of gublan or a sum",
                                     bg=PANEL, fg=DIM, font=ui_font(8))
        self.console_hint.pack(side="right", padx=px(10))
        self.console.bind("<Return>", self._console_submit)
        self.console.bind("<Up>", lambda _e: self._history(-1))
        self.console.bind("<Down>", lambda _e: self._history(1))
        self.console.bind("<FocusIn>", lambda _e: self.console_hint.configure(text="enter runs it. up and down "
                                                                                   "go through history"))
        tk.Frame(self, bg=BORDER, height=1).pack(side="bottom", fill="x")
        self.console_row.pack(side="bottom", fill="x")
        tk.Frame(self, bg=BORDER, height=1).pack(side="bottom", fill="x")
        bar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.line_count = 0

    def write(self, message, tag=None):
        text = self.text
        at_end = text.yview()[1] >= 0.999
        text.configure(state="normal")
        message = str(message)
        if tag == "error":
            match = re.match(r"^((?:([\w .\/:-]+\.gubl) )?line (\d+)):", message)
            if match:
                text.insert("end", match.group(1), ("error", "link", f"line:{match.group(3)}:{match.group(2) or ''}"))
                text.insert("end", message[len(match.group(1)):] + "\n", ("error",))
            else:
                text.insert("end", message + "\n", ("error",))
        else:
            text.insert("end", message + "\n", (tag,) if tag else ())
        self.line_count += 1 + message.count("\n")
        if self.line_count > 6000:
            text.delete("1.0", "1500.0")
            self.line_count = int(text.index("end-1c").split(".")[0])
        text.configure(state="disabled")
        if at_end:
            text.see("end")

    def _link_click(self, event):
        index = self.text.index(f"@{event.x},{event.y}")
        for tag in self.text.tag_names(index):
            if tag.startswith("line:") and self.on_link:
                number, _sep, file = tag[5:].partition(":")
                self.on_link(int(number), file or None)

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self.line_count = 0

    def copy_all(self):
        self.clipboard_clear()
        self.clipboard_append(self.text.get("1.0", "end-1c"))

    def ask(self, question, callback):
        self.answer_callback = callback
        self.write(question, "question")
        self.prompt.configure(text=(question[:60] + "...") if len(question) > 60 else question)
        self.input_row.pack(side="bottom", fill="x", before=self.console_row)
        self.answer.delete(0, "end")
        self.answer.focus_set()

    def cancel_question(self):
        self.answer_callback = None
        self.input_row.pack_forget()

    def _submit(self, _event=None):
        if not self.answer_callback:
            return
        value = self.answer.get()
        callback, self.answer_callback = self.answer_callback, None
        self.input_row.pack_forget()
        self.write(f"  {value}", "answer")
        callback(value)

    def _console_submit(self, _event=None):
        line = self.console.get()
        if not line.strip():
            return
        self.history.append(line)
        self.history_index = len(self.history)
        self.console.delete(0, "end")
        self.write(f"> {line}", "console")
        if self.on_console:
            self.on_console(line)

    def _history(self, step):
        if not self.history:
            return
        self.history_index = max(0, min(len(self.history), self.history_index + step))
        self.console.delete(0, "end")
        if self.history_index < len(self.history):
            self.console.insert(0, self.history[self.history_index])


# ----- problems ----------------------------------------------------------------------------------
class ProblemsPanel(tk.Frame):
    def __init__(self, parent, on_open):
        super().__init__(parent, bg=PANEL)
        self.on_open = on_open
        frame, self.tree = tree(self, ("line", "message"), ("line", "problem"), show="headings")
        self.tree.column("line", width=px(70), stretch=False, anchor="w")
        self.tree.column("message", width=px(600), anchor="w")
        frame.pack(fill="both", expand=True)
        self.empty = tk.Label(self, text="no problems found. nice work!", bg=PANEL, fg=DIM, font=ui_font(10))
        self.tree.bind("<Double-1>", self._open)
        self.tree.bind("<Return>", self._open)
        self.items = {}

    def show(self, diagnostics):
        self.tree.delete(*self.tree.get_children())
        self.items = {}
        for item in diagnostics:
            severity = item.get("severity", "error")
            where = f"{item.get('line') or '-'}"
            node = self.tree.insert("", "end", values=(where, lower(item["message"])),
                                    tags=("error" if severity == "error" else "warning",))
            self.items[node] = item
        if diagnostics:
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.45, anchor="center")

    def _open(self, _event=None):
        selection = self.tree.selection()
        if selection and selection[0] in self.items:
            self.on_open(self.items[selection[0]])


# ----- variables -----------------------------------------------------------------------------------
class VariablesPanel(tk.Frame):
    """live values while a program runs, and watches for experts."""

    def __init__(self, parent, evaluate=None):
        super().__init__(parent, bg=PANEL)
        self.evaluate = evaluate
        self.watches = []
        self.previous = {}
        top = tk.Frame(self, bg=PANEL)
        top.pack(fill="x", padx=px(10), pady=(px(6), px(4)))
        self.state = tk.Label(top, text="run a program to see its variables here", bg=PANEL, fg=DIM,
                              font=ui_font(9), anchor="w")
        self.state.pack(side="left")
        self.watch_entry = flat_entry(top, width=22, mono=True)
        self.watch_entry.pack(side="right")
        self.watch_entry.bind("<Return>", self._add_watch)
        tk.Label(top, text="watch", bg=PANEL, fg=DIM, font=ui_font(9)).pack(side="right", padx=px(6))
        Tooltip(self.watch_entry, "type an expression like score * 2 or player.x and press enter")
        frame, self.tree = tree(self, ("value", "kind"), ("value", "type"))
        self.tree.heading("#0", text="name", anchor="w")
        self.tree.column("#0", width=px(180), stretch=False)
        self.tree.column("value", width=px(420))
        self.tree.column("kind", width=px(90), stretch=False)
        frame.pack(fill="both", expand=True)
        self.tree.bind("<Delete>", self._remove_watch)
        self.open_nodes = set()
        self.tree.bind("<<TreeviewOpen>>", lambda _e: self._remember_open(True))
        self.tree.bind("<<TreeviewClose>>", lambda _e: self._remember_open(False))
        self.sections = {}

    def _remember_open(self, opened):
        node = self.tree.focus()
        if opened:
            self.open_nodes.add(node)
        else:
            self.open_nodes.discard(node)

    def _add_watch(self, _event=None):
        text = self.watch_entry.get().strip()
        if text and text not in self.watches:
            self.watches.append(text)
        self.watch_entry.delete(0, "end")
        self.refresh(self._last or ({}, {}, ""))

    def _remove_watch(self, _event=None):
        node = self.tree.focus()
        if node.startswith("watch:"):
            expression = node[6:]
            if expression in self.watches:
                self.watches.remove(expression)
            self.refresh(self._last or ({}, {}, ""))

    _last = None

    def set_state(self, text, color=DIM):
        self.state.configure(text=lower(text), fg=color)

    def refresh(self, snapshot):
        self._last = snapshot
        variables, objects, where = snapshot
        tree_widget = self.tree
        keep = tree_widget.yview()[0]
        tree_widget.delete(*tree_widget.get_children())
        if self.watches:
            parent = tree_widget.insert("", "end", "section:watch", text="watches", open=True, tags=("moss",))
            for expression in self.watches:
                value = self.evaluate(expression, variables, objects) if self.evaluate else "?"
                tree_widget.insert(parent, "end", f"watch:{expression}", text=expression,
                                   values=(value, ""), tags=())
        parent = tree_widget.insert("", "end", "section:vars", text=f"variables ({len(variables)})", open=True,
                                    tags=("moss",))
        for name in sorted(variables, key=str.lower):
            self._insert_value(parent, f"var:{name}", name, variables[name], depth=0)
        if objects:
            parent = tree_widget.insert("", "end", "section:objects", text=f"shapes ({len(objects)})",
                                        open="section:objects" in self.open_nodes or len(objects) < 12,
                                        tags=("moss",))
            for name in sorted(objects, key=str.lower)[:400]:
                info = objects[name]
                if isinstance(info, dict):
                    kind = info.get("type", "")
                    summary = ", ".join(f"{key} {format_value(info[key])}" for key in ("x", "y", "z", "w", "h", "r")
                                        if key in info and isinstance(info[key], (int, float)))
                    hidden = " (hidden)" if info.get("hidden") else ""
                    tree_widget.insert(parent, "end", f"obj:{name}", text=name, values=(summary + hidden, kind))
        tree_widget.yview_moveto(keep)

    def _insert_value(self, parent, node, name, value, depth):
        changed = node in self.previous and self.previous[node] != repr(value)[:200]
        self.previous[node] = repr(value)[:200]
        try:
            shown = format_value(value)
        except Exception:  # noqa: BLE001 - never let a strange value break the panel
            shown = repr(value)
        if len(shown) > 300:
            shown = shown[:300] + "..."
        try:
            kind = kind_of(value)
        except Exception:  # noqa: BLE001
            kind = type(value).__name__
        item = self.tree.insert(parent, "end", node, text=name, values=(shown, kind),
                                open=node in self.open_nodes, tags=("changed",) if changed else ())
        if depth < 3:
            if isinstance(value, list):
                for index, child in enumerate(value[:200]):
                    self._insert_value(item, f"{node}[{index}]", f"[{index}]", child, depth + 1)
            elif isinstance(value, dict):
                for index, key in enumerate(list(value)[:200]):
                    self._insert_value(item, f"{node}.{key}", str(key), value[key], depth + 1)


# ----- help ------------------------------------------------------------------------------------------
class HelpPanel(tk.Frame):
    """guides and every command with examples you can insert."""

    def __init__(self, parent, on_insert):
        super().__init__(parent, bg=PANEL)
        self.on_insert = on_insert
        self.search_var = tk.StringVar()
        top = tk.Frame(self, bg=PANEL)
        top.pack(fill="x", padx=px(10), pady=(px(8), px(4)))
        entry = flat_entry(top, self.search_var, width=20)
        entry.pack(fill="x")
        Tooltip(entry, "search commands, functions and guides")
        self.search_var.trace_add("write", lambda *_: self.after_idle(self.render))
        self.text = tk.Text(self, bg=PANEL, fg=TEXT, relief="flat", borderwidth=0, highlightthickness=0,
                            wrap="word", padx=px(12), pady=px(6), cursor="arrow", font=ui_font(10),
                            spacing1=px(1), spacing3=px(2))
        bar = scrollbar(self, "vertical", self.text.yview)
        self.text.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)
        text = self.text
        text.tag_configure("h1", font=ui_font(12, "bold"), foreground=MOSS_LIGHT, spacing1=px(10), spacing3=px(4))
        text.tag_configure("h2", font=ui_font(10, "bold"), foreground=TEXT, spacing1=px(8))
        text.tag_configure("usage", font=mono_font(10), foreground=MOSS_LIGHT)
        text.tag_configure("body", foreground=MUTED)
        text.tag_configure("code", font=mono_font(9), foreground=TEXT, background=theme.CODE_BG, lmargin1=px(8),
                           lmargin2=px(8))
        text.tag_configure("insert", foreground=MOSS_LIGHT, font=ui_font(8), underline=True)
        text.tag_configure("topic", foreground=MOSS_LIGHT, font=ui_font(10), underline=False)
        text.tag_bind("insert", "<Enter>", lambda _e: text.configure(cursor="hand2"))
        text.tag_bind("insert", "<Leave>", lambda _e: text.configure(cursor="arrow"))
        text.tag_bind("topic", "<Enter>", lambda _e: text.configure(cursor="hand2"))
        text.tag_bind("topic", "<Leave>", lambda _e: text.configure(cursor="arrow"))
        self.topic = None
        self.render()

    def show_topic(self, name):
        self.topic = name
        self.search_var.set("")
        self.render()

    def render(self):
        text = self.text
        text.configure(state="normal")
        text.delete("1.0", "end")
        for tag in text.tag_names():
            if tag.startswith(("ins:", "top:")):
                text.tag_delete(tag)
        query = self.search_var.get().strip().lower()
        if self.topic and not query:
            for title, body in GUIDES:
                if title == self.topic:
                    self._link("< all help", "top:", "")
                    text.insert("end", "\n" + title + "\n", ("h1",))
                    self._render_guide(body)
                    break
            text.configure(state="disabled")
            return
        if not query:
            text.insert("end", "guides\n", ("h1",))
            for title, _body in GUIDES:
                self._link(title, f"top:{title}", title)
                text.insert("end", "\n")
        matches = [(title, body) for title, body in GUIDES if query and (query in title or query in body.lower())]
        if matches:
            text.insert("end", "guides\n", ("h1",))
            for title, _body in matches:
                self._link(title, f"top:{title}", title)
                text.insert("end", "\n")
        groups = meta.commands_by_category()
        for category, names in groups.items():
            shown = [name for name in names if not query or query in name or query in COMMAND_SPECS[name][3].lower()
                     or query in category]
            if not shown:
                continue
            text.insert("end", category + "\n", ("h1",))
            for name in shown:
                spec = COMMAND_SPECS[name]
                text.insert("end", spec[1] + "\n", ("usage",))
                text.insert("end", spec[3] + "\n", ("body",))
                text.insert("end", spec[4] + "\n", ("code",))
                tag = f"ins:{name}"
                text.insert("end", "insert this", ("insert", tag))
                text.tag_bind(tag, "<Button-1>", lambda _e, example=spec[4]: self.on_insert(example))
                text.insert("end", "\n")
        functions = [(name, about) for name, about in EXPRESSION_FUNCTIONS.items()
                     if not query or query in name or query in about.lower()]
        if functions:
            text.insert("end", "functions for {braces} and maths\n", ("h1",))
            for name, about in functions:
                text.insert("end", f"{name}()", ("usage",))
                text.insert("end", f"  {about}\n", ("body",))
        text.configure(state="disabled")
        text.yview_moveto(0)

    def _link(self, label_text, tag, topic):
        self.text.insert("end", label_text, ("topic", tag))
        self.text.tag_bind(tag, "<Button-1>", lambda _e, t=topic: self.show_topic(t or None))

    def _render_guide(self, body):
        text = self.text
        paragraph = []
        code = []

        def flush():
            if paragraph:
                text.insert("end", " ".join(paragraph) + "\n\n", ("body",))
                paragraph.clear()
            if code:
                snippet = "\n".join(code)
                text.insert("end", snippet + "\n", ("code",))
                tag = f"ins:{len(text.tag_names())}"
                text.insert("end", "insert this", ("insert", tag))
                text.tag_bind(tag, "<Button-1>", lambda _e, s=snippet: self.on_insert(s))
                text.insert("end", "\n\n")
                code.clear()

        for line in body.split("\n"):
            if line.startswith("    "):
                if paragraph:
                    flush()
                code.append(line[4:])
            elif not line.strip():
                if code and not paragraph:
                    continue
                flush()
            else:
                if code:
                    flush()
                paragraph.append(line.strip())
        flush()


# ----- outline -------------------------------------------------------------------------------------------
class OutlinePanel(tk.Frame):
    def __init__(self, parent, on_open):
        super().__init__(parent, bg=PANEL)
        self.on_open = on_open
        panel_header(self, "outline")
        frame, self.tree = tree(self, ("line",), ("line",), show="tree")
        self.tree.column("#0", width=px(180))
        self.tree.column("line", width=px(50), stretch=False, anchor="e")
        frame.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._open)
        self.lines = {}
        self.closed = set()
        self.tree.bind("<<TreeviewClose>>", lambda _e: self.closed.add(self.tree.focus()))
        self.tree.bind("<<TreeviewOpen>>", lambda _e: self.closed.discard(self.tree.focus()))

    def show(self, symbols):
        tree_widget = self.tree
        tree_widget.delete(*tree_widget.get_children())
        self.lines = {}
        for key, title in (("functions", "functions"), ("objects", "shapes"), ("variables", "variables")):
            items = symbols.get(key, {})
            if not items:
                continue
            node = tree_widget.insert("", "end", key, text=f"{title} ({len(items)})", open=key not in self.closed,
                                      tags=("moss",))
            for name, info in sorted(items.items(), key=lambda pair: pair[1]["line"] if isinstance(pair[1], dict)
                                     else pair[1]):
                line = info["line"] if isinstance(info, dict) else info
                label_text = name + (" " + " ".join(info["params"]) if isinstance(info, dict) and info["params"]
                                     else "")
                child = tree_widget.insert(node, "end", text=label_text, values=(line,))
                self.lines[child] = line
        if not tree_widget.get_children():
            tree_widget.insert("", "end", text="functions, shapes and variables appear here", tags=("dim",))

    def _open(self, _event=None):
        selection = self.tree.selection()
        if selection and selection[0] in self.lines:
            self.on_open(self.lines[selection[0]])


# ----- files ------------------------------------------------------------------------------------------------
class FilesPanel(tk.Frame):
    def __init__(self, parent, on_open, on_choose_folder, on_message):
        super().__init__(parent, bg=PANEL)
        self.on_open = on_open
        self.on_message = on_message
        self.folder = None
        panel_header(self, "files", [("folder", "open a folder", on_choose_folder),
                                     ("add", "new program here", self.new_file),
                                     ("refresh", "refresh", self.refresh)])
        self.place_label = tk.Label(self, text="", bg=PANEL, fg=DIM, font=ui_font(8), anchor="w")
        self.place_label.pack(fill="x", padx=px(12))
        frame, self.tree = tree(self, (), (), show="tree")
        frame.pack(fill="both", expand=True, pady=(px(4), 0))
        self.tree.bind("<Double-1>", self._activate)
        self.tree.bind("<Return>", self._activate)
        self.tree.bind("<<TreeviewOpen>>", self._expand)
        self.tree.bind("<Button-3>", self._context)
        self.paths = {}
        self.place_tip = Tooltip(self.place_label, "")
        self.refresh()

    def set_folder(self, folder):
        self.folder = folder
        self.refresh()

    def refresh(self):
        tree_widget = self.tree
        tree_widget.delete(*tree_widget.get_children())
        self.paths = {}
        if not self.folder or not os.path.isdir(self.folder):
            self.place_label.configure(text="open a program or folder to see its files")
            self.place_tip.text = ""
            return
        # the panel is narrow, so show the end of the path and keep the whole path in the tooltip
        parts = os.path.normpath(self.folder).split(os.sep)
        shown = self.folder if len(parts) <= 2 else "..." + os.sep + os.sep.join(parts[-2:])
        self.place_label.configure(text=shown)
        self.place_tip.text = self.folder
        self._fill("", self.folder)

    def _fill(self, parent, folder):
        try:
            names = sorted(os.listdir(folder), key=lambda n: (not os.path.isdir(os.path.join(folder, n)), n.lower()))
        except OSError:
            return
        for name in names[:800]:
            if name.startswith(".") or name in ("__pycache__", "build", "dist") or name.endswith(".pyc"):
                continue
            path = os.path.join(folder, name)
            is_dir = os.path.isdir(path)
            extension = os.path.splitext(name)[1].lower()
            tags = ()
            if not is_dir and extension not in (".gubl",) + MEDIA_IMAGES + MEDIA_SOUNDS:
                tags = ("dim",)
            elif extension == ".gubl":
                tags = ("moss",)
            node = self.tree.insert(parent, "end", text=("  " if not is_dir else "") + name, tags=tags)
            self.paths[node] = path
            if is_dir:
                self.tree.insert(node, "end", text="...", tags=("dim",))

    def _expand(self, _event=None):
        node = self.tree.focus()
        path = self.paths.get(node)
        if path and os.path.isdir(path):
            children = self.tree.get_children(node)
            if len(children) == 1 and children[0] not in self.paths:
                self.tree.delete(children[0])
                self._fill(node, path)

    def _activate(self, _event=None):
        node = self.tree.focus()
        path = self.paths.get(node)
        if path and os.path.isfile(path):
            self.on_open(path)

    def selected_path(self):
        return self.paths.get(self.tree.focus())

    def new_file(self):
        if not self.folder:
            self.on_message("open a folder first")
            return
        from .dialogs import ask
        name = ask(self, "new program", "name for the new program", "my program")
        if not name:
            return
        if not name.endswith(".gubl"):
            name += ".gubl"
        path = os.path.join(self.folder, name)
        if os.path.exists(path):
            self.on_message(f"{name} already exists")
            return
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("// " + name[:-5] + "\n\nprint hello\n")
        self.refresh()
        self.on_open(path)

    def _context(self, event):
        node = self.tree.identify_row(event.y)
        if node:
            self.tree.selection_set(node)
            self.tree.focus(node)
        path = self.paths.get(node)
        items = []
        if path and os.path.isfile(path):
            items.append(("open", lambda: self.on_open(path)))
        items.append(("new program here", self.new_file))
        if path:
            items.append(("rename", lambda: self._rename(path)))
            items.append(("copy path", lambda: (self.clipboard_clear(), self.clipboard_append(path))))
            items.append(("show in explorer", lambda: reveal(path)))
            items.append("-")
            items.append({"label": "delete", "command": lambda: self._delete(path)})
        items.append("-")
        items.append(("refresh", self.refresh))
        show_menu(self.tree, items, event.x_root, event.y_root)

    def _rename(self, path):
        from .dialogs import ask
        name = ask(self, "rename", "new name", os.path.basename(path))
        if not name or name == os.path.basename(path):
            return
        target = os.path.join(os.path.dirname(path), name)
        if os.path.exists(target):
            self.on_message(f"{name} already exists")
            return
        try:
            os.rename(path, target)
        except OSError as err:
            self.on_message(f"could not rename: {str(err).lower()}")
        self.refresh()

    def _delete(self, path):
        from .dialogs import confirm
        if not confirm(self, "delete", f"delete {os.path.basename(path)}? this can't be undone.", yes="delete"):
            return
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except OSError as err:
            self.on_message(f"could not delete: {str(err).lower()}")
        self.refresh()


def reveal(path):
    if sys.platform == "win32":
        if os.path.isdir(path):
            os.startfile(path)  # noqa: S606 - opening a folder the user chose
        else:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


# ----- assets --------------------------------------------------------------------------------------------------
class AssetsPanel(tk.Frame):
    """pictures and sounds in the project's assets folder, with previews and code to use them."""

    def __init__(self, parent, hooks):
        super().__init__(parent, bg=PANEL)
        self.hooks = hooks
        self.folder = None
        self.preview_image = None
        panel_header(self, "assets", [("add", "import pictures or sounds", self.import_files),
                                      ("brush", "paint a new sprite", lambda: hooks["sprite_editor"](None)),
                                      ("folder", "open the assets folder", self.open_folder),
                                      ("refresh", "refresh", self.refresh)])
        self.place_label = tk.Label(self, text="", bg=PANEL, fg=DIM, font=ui_font(8), anchor="w", justify="left",
                                    wraplength=px(230))
        self.place_label.pack(fill="x", padx=px(12))
        frame, self.tree = tree(self, (), (), show="tree")
        frame.pack(fill="both", expand=True, pady=(px(4), 0))
        self.tree.bind("<<TreeviewSelect>>", self._preview)
        self.tree.bind("<Double-1>", lambda _e: self.insert_code())
        self.tree.bind("<Button-3>", self._context)
        self.preview = tk.Frame(self, bg=PANEL_ALT, height=px(170))
        self.preview.pack(fill="x", padx=px(8), pady=px(8))
        self.preview.pack_propagate(False)
        self.preview_label = tk.Label(self.preview, bg=PANEL_ALT, fg=DIM, font=ui_font(9), text="choose a file")
        self.preview_label.pack(fill="both", expand=True)
        actions = tk.Frame(self, bg=PANEL)
        actions.pack(fill="x", padx=px(8), pady=(0, px(8)))
        self.insert_button = BracketButton(actions, "insert code", icon_name="code", size=9, command=self.insert_code)
        self.insert_button.pack(side="left")
        self.play_button = BracketButton(actions, "play", icon_name="play", kind="ghost", size=9, command=self.play)
        self.play_button.pack(side="left", padx=px(4))
        self.edit_button = BracketButton(actions, "edit", icon_name="brush", kind="ghost", size=9,
                                         command=self.edit_selected)
        self.edit_button.pack(side="left")
        self.paths = {}

    def set_folder(self, project_folder):
        self.folder = os.path.join(project_folder, "assets") if project_folder else None
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self.paths = {}
        if not self.folder:
            self.place_label.configure(text="save your program first. its assets folder sits next to it.")
            return
        if not os.path.isdir(self.folder):
            self.place_label.configure(text="no assets folder yet. import a file or paint a sprite to make one.")
            return
        self.place_label.configure(text="double-click a file to put the code for it in your program.")
        count = 0
        for directory, dirs, files in os.walk(self.folder):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            relative = os.path.relpath(directory, os.path.dirname(self.folder))
            for name in sorted(files, key=str.lower):
                extension = os.path.splitext(name)[1].lower()
                if extension not in MEDIA_IMAGES + MEDIA_SOUNDS + (".ttf", ".otf", ".txt", ".json", ".csv"):
                    continue
                path = os.path.join(directory, name)
                display = os.path.join(relative, name).replace(os.sep, "/")
                node = self.tree.insert("", "end", text=display, tags=("moss",) if extension in MEDIA_IMAGES else ())
                self.paths[node] = path
                count += 1
                if count > 2000:
                    return

    def selected(self):
        selection = self.tree.selection()
        return self.paths.get(selection[0]) if selection else None

    def relative(self, path):
        base = os.path.dirname(self.folder)
        return os.path.relpath(path, base).replace(os.sep, "/")

    def _preview(self, _event=None):
        path = self.selected()
        self.preview_image = None
        if not path:
            return
        extension = os.path.splitext(path)[1].lower()
        size = os.path.getsize(path) if os.path.exists(path) else 0
        info = f"{os.path.basename(path)}\n{size // 1024 if size >= 1024 else size} {'kb' if size >= 1024 else 'bytes'}"
        if extension in (".png", ".gif") and size <= 8 * 1024 * 1024:
            try:
                image = tk.PhotoImage(file=path)
                width, height = image.width(), image.height()
                factor = max(1, int(max(width / px(220), height / px(140))) + (1 if max(width / px(220),
                                                                                       height / px(140)) > 1 else 0))
                if factor > 1:
                    image = image.subsample(factor, factor)
                elif width and height and max(width, height) <= 32:
                    zoom = max(1, min(px(140) // max(width, height), 8))
                    image = image.zoom(zoom, zoom)
                self.preview_image = image
                self.preview_label.configure(image=image, text="", compound="center")
                # one tooltip, updated (1.0.5 added a new one for every picture clicked)
                if getattr(self, "preview_tip", None) is None:
                    self.preview_tip = Tooltip(self.preview_label, "")
                self.preview_tip.text = lower(f"{info}\n{width} x {height} pixels")
                return
            except tk.TclError:
                pass
        self.preview_label.configure(image="", text=info, fg=MUTED)
        if getattr(self, "preview_tip", None) is not None:
            self.preview_tip.text = ""

    def code_for(self, path):
        relative = self.relative(path)
        quoted = f'"{relative}"' if " " in relative else relative
        extension = os.path.splitext(path)[1].lower()
        stem = re.sub(r"\W+", "_", os.path.splitext(os.path.basename(path))[0]).strip("_").lower() or "picture"
        if stem[0].isdigit():
            stem = "pic_" + stem
        if extension in MEDIA_IMAGES:
            return f"image {stem} {quoted} 40 40"
        if extension in (".ogg", ".mp3") and os.path.getsize(path) > 400_000:
            return f"music {quoted}"
        if extension in MEDIA_SOUNDS:
            return f"sound {quoted}"
        return f"// {relative}"

    def insert_code(self):
        path = self.selected()
        if path:
            self.hooks["insert"](self.code_for(path))

    def play(self):
        path = self.selected()
        if not path:
            return
        extension = os.path.splitext(path)[1].lower()
        if extension == ".wav" and sys.platform == "win32":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        elif sys.platform == "win32":
            os.startfile(path)  # noqa: S606 - opens the user's own media file in their player

    def edit_selected(self):
        path = self.selected()
        if path and path.lower().endswith(".png"):
            self.hooks["sprite_editor"](path)

    def open_folder(self):
        if not self.folder:
            self.hooks["message"]("save your program first")
            return
        os.makedirs(self.folder, exist_ok=True)
        reveal(self.folder)
        self.refresh()

    def import_files(self):
        if not self.folder:
            self.hooks["message"]("save your program first. assets go in a folder next to it.")
            return
        from tkinter import filedialog
        files = filedialog.askopenfilenames(parent=self, title="import pictures and sounds", filetypes=[
            ("pictures and sounds", "*.png *.gif *.jpg *.jpeg *.bmp *.wav *.ogg *.mp3"), ("all files", "*.*")])
        if not files:
            return
        try:
            os.makedirs(self.folder, exist_ok=True)
        except OSError as err:
            self.hooks["message"](f"could not make the assets folder: {str(err).lower()}")
            return
        copied, failed = 0, []
        for source in files:
            target = os.path.join(self.folder, os.path.basename(source))
            try:
                if os.path.normcase(os.path.abspath(source)) != os.path.normcase(os.path.abspath(target)):
                    shutil.copy2(source, target)
                copied += 1
            except (OSError, shutil.Error):
                failed.append(os.path.basename(source))
        self.refresh()
        text = f"imported {plural(copied, 'file')} into assets"
        if failed:
            text += f". could not copy {', '.join(failed[:3])}" + (" and more" if len(failed) > 3 else "")
        self.hooks["message"](text)

    def _context(self, event):
        node = self.tree.identify_row(event.y)
        if node:
            self.tree.selection_set(node)
        path = self.paths.get(node)
        items = []
        if path:
            items.append(("insert code", self.insert_code))
            items.append(("copy path", lambda: (self.clipboard_clear(), self.clipboard_append(self.relative(path)))))
            if path.lower().endswith(".png"):
                items.append(("edit in sprite painter", self.edit_selected))
            items.append(("show in explorer", lambda: reveal(path)))
            items.append("-")
        items.append(("import files", self.import_files))
        items.append(("paint a new sprite", lambda: self.hooks["sprite_editor"](None)))
        show_menu(self.tree, items, event.x_root, event.y_root)
