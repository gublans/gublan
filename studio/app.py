"""gublan studio: the main window.

top bar (menus + run controls + view switch), activity bar, side panels, editor tabs with code / blocks /
split views, bottom panels (output, problems, variables) and a status bar. everything is square, lowercase
and soft green on soft black.
"""

import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog

from gublancore import COMMAND_SPECS, GublanRuntime, analyze_source, format_value, parse_expression

from . import blocks as blocks_module
from . import config, exporter, theme, updater, version
from .assets import logo_image, set_window_icon
from .blocks import BlocksView
from .dialogs import (CommandPalette, ConvertDialog, ExportDialog, SettingsDialog, SpriteEditor, WelcomePage,
                      ask, confirm, message)
from .editor import CodeEditor
from .panels import (AssetsPanel, FilesPanel, HelpPanel, OutlinePanel, OutputPanel, ProblemsPanel,
                     VariablesPanel, reveal)
from .templates import TEMPLATES, template
from .theme import (BG, BORDER, DEBUG_LINE, DIM, EDITOR_BG, ERROR, HOVER, MOSS_DARK, MOSS_LIGHT, MUTED, NUMBER, PANEL,
                    PANEL_ALT, TEXT, BracketButton, PopupMenu, Tooltip, icon, icon_font, lower, px, show_menu,
                    ui_font)

APP_NAME = "gublan studio"
CODE_TYPES = [("gublan programs", "*.gubl *.gub *.txt"), ("all files", "*.*")]
FOREIGN = (".py", ".pyw", ".js", ".mjs", ".lua")
CONSOLE_COMMANDS = {name for name, spec in COMMAND_SPECS.items() if spec[0] in ("basics", "lists and maps")} | {
    "call", "vec2", "vec3"}


def unpx(value):
    """the opposite of px(): screen pixels back to the unscaled numbers kept in settings."""
    return int(round(value / max(1.0, theme._SCALE)))


def find_includes(source, base_dir, depth=0, found=None):
    """basename -> full path for every file a program includes (so errors in them can be opened)."""
    found = {} if found is None else found
    if depth > 8:
        return found
    for raw in source.splitlines():
        stripped = raw.strip()
        if not stripped.startswith("include "):
            continue
        path = os.path.realpath(os.path.join(base_dir, stripped[8:].strip().strip('"').strip("'")))
        name = os.path.basename(path)
        if name in found or not os.path.isfile(path):
            continue
        found[name] = path
        try:
            with open(path, "r", encoding="utf-8") as handle:
                find_includes(handle.read(), os.path.dirname(path), depth + 1, found)
        except OSError:
            pass
    return found


# ----- one open program ---------------------------------------------------------------------------------
class Document:
    counter = 0

    def __init__(self, app, path=None, text="", name=None):
        self.app = app
        self.path = os.path.abspath(path) if path else None
        if not path and not name:
            Document.counter += 1
            name = f"untitled {Document.counter}"
        self.untitled_name = name
        self.view = "code"
        self.diagnostics = []
        self.analysed_version = -1
        self.analysis_job = None
        self.blocks_job = None
        self.tab = None
        self.frame = tk.PanedWindow(app.content, orient="horizontal", bg=BORDER, sashwidth=px(4), bd=0,
                                    relief="flat", showhandle=False, opaqueresize=True)
        self.editor = CodeEditor(self.frame, app.settings, hooks={
            "changed": lambda: app.on_changed(self),
            "cursor": lambda line, col: app.on_cursor(self, line, col),
            "symbols": lambda: app.on_symbols(self),
            "breakpoints": lambda: app.on_breakpoints(self),
            "zoom": app.zoom,
            "value_of": app.value_of,
            "define_elsewhere": lambda word: app.define_elsewhere(self, word),
        })
        self.editor.set_text(text)
        self.editor.mark_saved()
        self.blocks = None
        self.frame.add(self.editor, stretch="always")

    @property
    def name(self):
        return os.path.basename(self.path) if self.path else self.untitled_name

    @property
    def folder(self):
        return os.path.dirname(self.path) if self.path else None

    @property
    def dirty(self):
        return self.editor.dirty

    def set_view(self, view):
        if view != "code" and self.blocks is None:
            self.blocks = BlocksView(self.frame, on_change=self.from_blocks, settings=self.app.settings,
                                     hooks={"pick_asset": self.app.pick_asset})
        for pane in (self.editor, self.blocks):
            if pane is not None:
                try:
                    self.frame.forget(pane)
                except tk.TclError:
                    pass
        self.view = view
        if view in ("code", "split"):
            self.frame.add(self.editor, stretch="always", minsize=px(260))
        if view in ("blocks", "split"):
            self.blocks.load(self.editor.get())
            self.frame.add(self.blocks, stretch="always", minsize=px(360))
        if view == "split":
            self.frame.after_idle(self._even_split)
        if view == "blocks":
            self.blocks.focus_set()
        else:
            self.editor.focus_editor()

    def _even_split(self):
        try:
            width = self.frame.winfo_width()
            if width > 10:
                self.frame.sash_place(0, width // 2, 0)
        except tk.TclError:
            pass

    def from_blocks(self, source):
        if source != self.editor.get():
            self.editor.replace_all_text(source)

    def sync_blocks(self):
        self.blocks_job = None
        if self.blocks is not None and self.view != "code":
            self.blocks.load(self.editor.get())


# ----- the studio ----------------------------------------------------------------------------------------
class GublanStudio:
    @staticmethod
    def parseblocksource(source):
        return blocks_module.parseblocksource(source)

    def __init__(self, root, paths=()):
        self.root = root
        self.settings = config.load()
        self.docs = []
        self.current = None
        self.runtime = GublanRuntime()
        self.console_runtime = None
        self.queue = queue.Queue()
        self.run_thread = None
        self.run_active = False
        self._state = ("ready", MOSS_LIGHT)
        self.run_doc = None
        self.run_breakpoints = set()
        self.run_includes = {}
        self.run_started = 0.0
        self.active_runtime = None
        self.stop_event = threading.Event()
        self.resume_event = threading.Event()
        self.paused = False
        self.pause_requested = False
        self.step_mode = False
        self.paused_line = None
        self.pending_answer = None
        self.export_dialog = None
        self.settings_dialog = None
        self.side_name = self.settings.get("side_panel", "files")
        self.bottom_name = self.settings.get("bottom_panel", "output")
        self.status_message_job = None
        self._build_window()
        self._bind_shortcuts()
        self.apply_settings(self.settings, save=False)
        self._restore(paths)
        self.root.after(40, self._poll)
        self.root.after(5000, self._check_for_updates)
        self.root.protocol("WM_DELETE_WINDOW", self.exit)

    # ----- window ----------------------------------------------------------------------------------------
    def _build_window(self):
        root = self.root
        root.title(APP_NAME)
        root.configure(bg=BG)
        root.minsize(px(860), px(520))
        geometry = self.settings.get("window") or ""
        if geometry == "zoomed":
            root.geometry(f"{px(1280)}x{px(800)}")
            try:
                root.state("zoomed")
            except tk.TclError:
                pass
        elif re.match(r"^\d+x\d+[+-]-?\d+[+-]-?\d+$", geometry):
            root.geometry(geometry)
        else:
            width = min(px(1360), root.winfo_screenwidth() - px(80))
            height = min(px(860), root.winfo_screenheight() - px(120))
            root.geometry(f"{width}x{height}+{px(40)}+{px(30)}")
        self._set_icon()
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        self._build_topbar()
        body = tk.Frame(root, bg=BG)
        body.grid(row=1, column=0, sticky="nsew")
        tk.Frame(root, bg=BORDER, height=1).grid(row=2, column=0, sticky="ew")
        self._build_statusbar()

        self.activity = tk.Frame(body, bg=BG, width=px(46))
        self.activity.pack(side="left", fill="y")
        self.activity.pack_propagate(False)
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")
        self.hpanes = tk.PanedWindow(body, orient="horizontal", bg=BORDER, sashwidth=px(3), bd=0, relief="flat",
                                     showhandle=False, opaqueresize=True)
        self.hpanes.pack(side="left", fill="both", expand=True)

        self.side = tk.Frame(self.hpanes, bg=PANEL)
        self.side_panels = {
            "files": FilesPanel(self.side, on_open=self.open_path, on_choose_folder=self.choose_folder,
                                on_message=self.flash),
            "outline": OutlinePanel(self.side, on_open=self.goto_line),
            "assets": AssetsPanel(self.side, hooks={"insert": self.insert_code, "sprite_editor": self.sprite_editor,
                                                    "message": self.flash}),
            "help": HelpPanel(self.side, on_insert=self.insert_code),
        }
        self.activity_buttons = {}
        for name, icon_name, tip in (("files", "files", "files (ctrl+shift+e)"),
                                     ("outline", "outline", "outline: functions, shapes and variables"),
                                     ("assets", "assets", "pictures and sounds"),
                                     ("help", "learn", "help and guides (f1)")):
            button = BracketButton(self.activity, icon_name=icon_name, kind="ghost", size=13, pad_x=9, pad_y=9,
                                   tooltip=tip, bg=BG, command=lambda n=name: self.toggle_side(n))
            button.pack(side="top", pady=(px(4), 0))
            self.activity_buttons[name] = button
        BracketButton(self.activity, icon_name="settings", kind="ghost", size=13, pad_x=9, pad_y=9,
                      tooltip="settings (ctrl+,)", bg=BG, command=self.open_settings).pack(side="bottom",
                                                                                          pady=px(6))
        self.vpanes = tk.PanedWindow(self.hpanes, orient="vertical", bg=BORDER, sashwidth=px(3), bd=0,
                                     relief="flat", showhandle=False, opaqueresize=True)
        self.hpanes.add(self.side, width=px(self.settings.get("side_width", 250)), minsize=px(170), stretch="never")
        self.hpanes.add(self.vpanes, stretch="always", minsize=px(380))

        center = tk.Frame(self.vpanes, bg=EDITOR_BG)
        self._build_tabs(center)
        self.content = tk.Frame(center, bg=EDITOR_BG)
        self.content.pack(fill="both", expand=True)
        self.welcome = None
        self.empty_hint = tk.Label(self.content, text="ctrl+n makes a new program. ctrl+o opens one.", bg=EDITOR_BG,
                                   fg=DIM, font=ui_font(10))
        self.bottom = tk.Frame(self.vpanes, bg=PANEL)
        self._build_bottom(self.bottom)
        self.vpanes.add(center, stretch="always", minsize=px(160))
        self.vpanes.add(self.bottom, height=px(self.settings.get("bottom_height", 210)), minsize=px(90),
                        stretch="never")
        self.show_side_panel(self.side_name, visible=self.settings.get("show_side", True))
        self.show_bottom_panel(self.bottom_name, visible=self.settings.get("show_bottom", True))

    def _set_icon(self):
        self.icon_image = set_window_icon(self.root)

    def _build_topbar(self):
        bar = tk.Frame(self.root, bg=BG)
        bar.grid(row=0, column=0, sticky="ew")
        self.topbar = bar
        mark = tk.Frame(bar, bg=BG)
        mark.pack(side="left", padx=(px(12), px(10)), pady=px(6))
        self.brand_image = logo_image(mark, px(18))
        tk.Label(mark, image=self.brand_image, bg=BG).pack(side="left")
        tk.Label(mark, text="gublan", bg=BG, fg=TEXT, font=ui_font(10, "bold")).pack(side="left", padx=(px(8), 0))
        self.menu_labels = {}
        for name in ("file", "edit", "view", "run", "tools", "help"):
            label_widget = tk.Label(bar, text=name, bg=BG, fg=MUTED, font=ui_font(10), padx=px(8), pady=px(4),
                                    cursor="hand2")
            label_widget.pack(side="left")
            label_widget.bind("<Button-1>", lambda _e, n=name: self.open_menu(n))
            label_widget.bind("<Enter>", lambda _e, n=name: self._menu_hover(n, True))
            label_widget.bind("<Leave>", lambda _e, n=name: self._menu_hover(n, False))
            self.menu_labels[name] = label_widget
        self.open_menu_name = None
        tk.Frame(bar, bg=BORDER, width=1, height=px(22)).pack(side="left", padx=px(10))
        self.toolbar = tk.Frame(bar, bg=BG)
        self.toolbar.pack(side="left", fill="y")
        self.right_tools = tk.Frame(bar, bg=BG)
        self.right_tools.pack(side="right", padx=px(8))
        self._build_toolbar()

    def _build_toolbar(self):
        for child in self.toolbar.winfo_children() + self.right_tools.winfo_children():
            child.destroy()
        labels = self.settings.get("toolbar_labels", True)

        def tool(parent, text, icon_name, command, tip, kind="ghost", side="left"):
            button = BracketButton(parent, text if labels else "", icon_name=icon_name, kind=kind, size=9,
                                   pad_x=9 if labels else 7, pad_y=4, tooltip=tip, bg=BG, command=command)
            button.pack(side=side, padx=(0, px(3)), pady=px(5))
            return button

        self.run_button = tool(self.toolbar, "run", "run", self.run_or_continue, "run the program (f5)", "accent")
        self.stop_button = tool(self.toolbar, "stop", "stop", self.stop, "stop (shift+f5)")
        self.pause_button = tool(self.toolbar, "pause", "pause", self.pause, "pause (f6)")
        self.step_button = tool(self.toolbar, "step", "step", self.step, "run one line at a time (f10)")
        tk.Frame(self.toolbar, bg=BORDER, width=1, height=px(22)).pack(side="left", padx=px(8))
        self.view_buttons = {}
        for view, text, icon_name, tip in (("code", "code", "code", "code view (ctrl+1)"),
                                           ("blocks", "blocks", "blocks", "blocks view (ctrl+2 or ctrl+b)"),
                                           ("split", "both", "more", "code and blocks side by side (ctrl+3)")):
            self.view_buttons[view] = tool(self.toolbar, text, icon_name, lambda v=view: self.set_view(v), tip)
        tool(self.right_tools, "", "search", self.command_palette, "find any action (ctrl+shift+p)", side="right")
        self.level_button = BracketButton(self.right_tools, self.settings.get("level", "beginner") + "  ▾",
                                          kind="ghost", size=9, pad_x=9, pad_y=4, bg=BG,
                                          tooltip="how much help the editor gives", command=self._level_menu)
        self.level_button.pack(side="right", padx=px(4), pady=px(5))
        tool(self.right_tools, "export", "export", self.open_export, "make a .exe to share (ctrl+shift+b)",
             side="right")
        self.update_run_controls()
        self.update_view_buttons()

    def _level_menu(self):
        level = self.settings.get("level")
        items = [{"label": f"{name}: {config.LEVEL_ABOUT[name][:58]}...", "checked": level == name,
                  "command": lambda n=name: self.set_level(n)} for name in ("beginner", "standard", "expert")]
        items += ["-", ("all settings...", self.open_settings, "ctrl+,")]
        show_menu(self.level_button, items)

    def _build_tabs(self, parent):
        holder = tk.Frame(parent, bg=PANEL, height=px(34))
        holder.pack(fill="x")
        holder.pack_propagate(False)
        self.tab_canvas = tk.Canvas(holder, bg=PANEL, highlightthickness=0, bd=0, height=px(34))
        self.tab_canvas.pack(side="left", fill="both", expand=True)
        self.tab_strip = tk.Frame(self.tab_canvas, bg=PANEL)
        self.tab_canvas.create_window(0, 0, anchor="nw", window=self.tab_strip)
        self.tab_strip.bind("<Configure>", lambda _e: self.tab_canvas.configure(
            scrollregion=(0, 0, self.tab_strip.winfo_reqwidth(), px(34))))
        self.tab_canvas.bind("<MouseWheel>", self._tab_wheel)
        BracketButton(holder, icon_name="add", kind="ghost", size=10, pad_x=8, pad_y=5, bg=PANEL,
                      tooltip="new program (ctrl+n)", command=self.new_tab).pack(side="right", padx=px(4))

    def _tab_wheel(self, event):
        self.tab_canvas.xview_scroll(int(-event.delta / 120) * 3, "units")
        return "break"

    def _build_bottom(self, parent):
        head = tk.Frame(parent, bg=PANEL)
        head.pack(fill="x")
        self.bottom_tabs = {}
        for name in ("output", "problems", "variables"):
            cell = tk.Frame(head, bg=PANEL, cursor="hand2")
            cell.pack(side="left", padx=(px(6) if name == "output" else 0, 0))
            label_widget = tk.Label(cell, text=name, bg=PANEL, fg=MUTED, font=ui_font(9), padx=px(10), pady=px(5),
                                    cursor="hand2")
            label_widget.pack()
            line = tk.Frame(cell, bg=PANEL, height=px(2))
            line.pack(fill="x")
            for widget in (cell, label_widget):
                widget.bind("<Button-1>", lambda _e, n=name: self.show_bottom_panel(n))
            self.bottom_tabs[name] = (label_widget, line)
        actions = tk.Frame(head, bg=PANEL)
        actions.pack(side="right", padx=px(6))
        for icon_name, tip, command in (("close", "hide the panel (ctrl+j)", lambda: self.show_bottom_panel(
                                            self.bottom_name, visible=False)),
                                        ("copy", "copy the output", lambda: self.output.copy_all()),
                                        ("trash", "clear the output", lambda: self.output.clear())):
            BracketButton(actions, icon_name=icon_name, kind="ghost", size=9, pad_x=6, pad_y=3, tooltip=tip,
                          bg=PANEL, command=command).pack(side="right", padx=(px(2), 0))
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x")
        self.bottom_body = tk.Frame(parent, bg=PANEL)
        self.bottom_body.pack(fill="both", expand=True)
        self.output = OutputPanel(self.bottom_body, on_console=self.console_line)
        self.output.on_link = self.open_location
        self.problems = ProblemsPanel(self.bottom_body, on_open=lambda item: self.goto_line(item.get("line") or 1))
        self.variables = VariablesPanel(self.bottom_body, evaluate=self.evaluate_watch)
        self.bottom_panels = {"output": self.output, "problems": self.problems, "variables": self.variables}

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=PANEL, height=px(26))
        bar.grid(row=3, column=0, sticky="ew")
        bar.pack_propagate(False)
        self.statusbar = bar
        self.status_state = tk.Label(bar, text="  ready", bg=PANEL, fg=MOSS_LIGHT, font=ui_font(9), padx=px(10))
        self.status_state.pack(side="left")
        self.status_problems = tk.Label(bar, text="", bg=PANEL, fg=MUTED, font=ui_font(9), padx=px(8),
                                        cursor="hand2")
        self.status_problems.pack(side="left")
        self.status_problems.bind("<Button-1>", lambda _e: self.show_bottom_panel("problems"))
        self.status_message = tk.Label(bar, text="", bg=PANEL, fg=MUTED, font=ui_font(9), padx=px(8))
        self.status_message.pack(side="left")
        self.status_right = []
        for key in ("level", "indent", "position"):
            label_widget = tk.Label(bar, text="", bg=PANEL, fg=MUTED, font=ui_font(9), padx=px(10), cursor="hand2")
            label_widget.pack(side="right")
            self.status_right.append(label_widget)
        self.status_level, self.status_indent, self.status_position = self.status_right
        self.status_level.bind("<Button-1>", lambda _e: self._level_menu())
        self.status_indent.bind("<Button-1>", lambda _e: self.open_settings())
        self.status_position.bind("<Button-1>", lambda _e: self.goto_line_prompt())
        self.status_widgets = [bar, self.status_state, self.status_problems, self.status_message] + self.status_right

    # ----- menus ---------------------------------------------------------------------------------------------
    def menus(self):
        doc = self.current
        recent = [path for path in self.settings.get("recent", []) if os.path.isfile(path)][:10]
        wrap = self.settings.get("wrap")
        return {
            "file": [
                ("new program", self.new_tab, "ctrl+n"),
                ("new from template", [(f"{item['title']}  ({item['level']})",
                                        lambda k=item["key"]: self.new_from_template(k)) for item in TEMPLATES]),
                ("open...", self.open_dialog, "ctrl+o"),
                ("open folder...", self.choose_folder, ""),
                ("open recent", [(self._short(path), lambda p=path: self.open_path(p)) for path in recent]
                 or [{"label": "nothing yet", "enabled": False}]),
                "-",
                {"label": "save", "command": self.save, "shortcut": "ctrl+s", "enabled": doc is not None},
                {"label": "save as...", "command": self.save_as, "shortcut": "ctrl+shift+s", "enabled": doc is not None},
                ("save all", self.save_all, ""),
                "-",
                {"label": "export program...", "command": self.open_export, "shortcut": "ctrl+shift+b",
                 "enabled": doc is not None},
                {"label": "show in explorer", "command": lambda: doc and doc.path and reveal(doc.path),
                 "enabled": bool(doc and doc.path)},
                "-",
                {"label": "close tab", "command": self.close_current, "shortcut": "ctrl+w", "enabled": doc is not None},
                ("exit", self.exit, "alt+f4"),
            ],
            "edit": [
                ("undo", lambda: self._edit("undo"), "ctrl+z"),
                ("redo", lambda: self._edit("redo"), "ctrl+y"),
                "-",
                ("cut", lambda: self._edit("<<Cut>>"), "ctrl+x"),
                ("copy", lambda: self._edit("<<Copy>>"), "ctrl+c"),
                ("paste", lambda: self._edit("<<Paste>>"), "ctrl+v"),
                ("select all", lambda: self._edit("select_all"), "ctrl+a"),
                "-",
                ("find", lambda: self._edit("find"), "ctrl+f"),
                ("replace", lambda: self._edit("replace"), "ctrl+h"),
                ("go to line...", self.goto_line_prompt, "ctrl+g"),
                ("go to definition", lambda: self._edit("definition"), "f12"),
                "-",
                ("comment or uncomment", lambda: self._edit("comment"), "ctrl+/"),
                ("duplicate line", lambda: self._edit("duplicate"), "ctrl+d"),
                ("move line up", lambda: self._edit("up"), "alt+up"),
                ("move line down", lambda: self._edit("down"), "alt+down"),
                ("delete line", lambda: self._edit("delete"), "ctrl+shift+k"),
                ("indent", lambda: self._edit("indent"), "ctrl+]"),
                ("unindent", lambda: self._edit("dedent"), "ctrl+["),
                "-",
                ("suggest", lambda: self._edit("complete"), "ctrl+space"),
            ],
            "view": [
                {"label": "code", "command": lambda: self.set_view("code"), "shortcut": "ctrl+1",
                 "checked": bool(doc and doc.view == "code")},
                {"label": "blocks", "command": lambda: self.set_view("blocks"), "shortcut": "ctrl+2",
                 "checked": bool(doc and doc.view == "blocks")},
                {"label": "code and blocks", "command": lambda: self.set_view("split"), "shortcut": "ctrl+3",
                 "checked": bool(doc and doc.view == "split")},
                "-",
                ("files", lambda: self.show_side_panel("files"), "ctrl+shift+e"),
                ("outline", lambda: self.show_side_panel("outline"), "ctrl+shift+o"),
                ("assets", lambda: self.show_side_panel("assets"), "ctrl+shift+a"),
                ("help", lambda: self.show_side_panel("help"), "f1"),
                {"label": "side bar", "command": self.toggle_side_bar, "shortcut": "ctrl+\\",
                 "checked": self.side_visible()},
                "-",
                ("output", lambda: self.show_bottom_panel("output"), "ctrl+shift+u"),
                ("problems", lambda: self.show_bottom_panel("problems"), "ctrl+shift+m"),
                ("variables", lambda: self.show_bottom_panel("variables"), "ctrl+shift+v"),
                {"label": "bottom panel", "command": self.toggle_bottom, "shortcut": "ctrl+j",
                 "checked": self.bottom_visible()},
                "-",
                ("bigger text", lambda: self.zoom(1), "ctrl+="),
                ("smaller text", lambda: self.zoom(-1), "ctrl+-"),
                ("normal text size", lambda: self.zoom(0), "ctrl+0"),
                {"label": "wrap long lines", "command": lambda: self.set_option("wrap", not wrap), "checked": wrap},
                {"label": "line numbers", "command": lambda: self.set_option(
                    "line_numbers", not self.settings.get("line_numbers")),
                 "checked": self.settings.get("line_numbers")},
                {"label": "explain the current line", "command": lambda: self.set_option(
                    "explain", not self.settings.get("explain")), "checked": self.settings.get("explain")},
            ],
            "run": [
                ("run" if not self.running() else "continue", self.run_or_continue, "f5"),
                {"label": "stop", "command": self.stop, "shortcut": "shift+f5", "enabled": self.running()},
                {"label": "pause", "command": self.pause, "shortcut": "f6",
                 "enabled": self.running() and not self.paused},
                ("step (one line at a time)", self.step, "f10"),
                "-",
                ("breakpoint on this line", lambda: self._edit("breakpoint"), "f9"),
                ("remove all breakpoints", self.clear_breakpoints, ""),
                "-",
                ("check for problems", self.check_now, "f8"),
                ("clear output", self.output.clear, ""),
            ],
            "tools": [
                ("convert python, javascript or lua...", self.open_converter, "ctrl+shift+c"),
                ("sprite painter...", lambda: self.sprite_editor(None), ""),
                ("find any action...", self.command_palette, "ctrl+shift+p"),
                "-",
                ("how much help", [{"label": name, "command": lambda n=name: self.set_level(n),
                                    "checked": self.settings.get("level") == name}
                                   for name in ("beginner", "standard", "expert")]),
                ("settings...", self.open_settings, "ctrl+,"),
            ],
            "help": [
                ("guides", lambda: self.show_help("first steps"), "f1"),
                ("every command", lambda: self.show_help(None), ""),
                ("keyboard shortcuts", lambda: self.show_help("keyboard shortcuts"), ""),
                ("making a game", lambda: self.show_help("making a game"), ""),
                "-",
                ("welcome page", self.show_welcome_tab, ""),
                ("open the command list file", self.open_command_docs, ""),
                ("about gublan studio", self.about, ""),
            ],
        }

    def open_menu(self, name):
        if PopupMenu.active is not None and self.open_menu_name == name:
            PopupMenu.active.close()
            return
        label_widget = self.menu_labels[name]
        self.open_menu_name = name
        label_widget.configure(bg=PANEL_ALT, fg=TEXT)

        def closed(n=name):
            self.menu_labels[n].configure(bg=BG, fg=MUTED)
            self.root.after(60, lambda: setattr(self, "open_menu_name", None)
                            if PopupMenu.active is None else None)

        show_menu(label_widget, self.menus()[name], on_close=closed)

    def _menu_hover(self, name, inside):
        label_widget = self.menu_labels[name]
        if inside and PopupMenu.active is not None and self.open_menu_name and self.open_menu_name != name:
            PopupMenu.active.close()
            self.open_menu(name)
            return
        if self.open_menu_name != name or PopupMenu.active is None:
            label_widget.configure(fg=TEXT if inside else MUTED)

    def palette_actions(self):
        actions = []

        def walk(items, prefix=""):
            for item in items:
                if item == "-" or item is None:
                    continue
                if isinstance(item, dict):
                    if item.get("enabled", True) and "command" in item:
                        actions.append((prefix + item["label"], item.get("shortcut", ""), item["command"]))
                elif isinstance(item[1], list):
                    walk(item[1], prefix + item[0] + ": ")
                else:
                    actions.append((prefix + item[0], item[2] if len(item) > 2 else "", item[1]))

        for name, items in self.menus().items():
            walk(items, name + ": ")
        return actions

    def command_palette(self, initial=""):
        symbols = self.current.editor.symbols if self.current else {}
        CommandPalette(self, self.palette_actions(), symbols, initial=initial)

    # ----- shortcuts -----------------------------------------------------------------------------------------
    def _bind_shortcuts(self):
        self.shortcuts = {
            "f5": self.run_or_continue, "shift+f5": self.stop, "f6": self.pause, "f10": self.step,
            "f8": self.check_now, "f1": lambda: self.show_side_panel("help"),
            "f9": lambda: self._edit("breakpoint"),
            "ctrl+n": self.new_tab, "ctrl+o": self.open_dialog, "ctrl+s": self.save, "ctrl+shift+s": self.save_as,
            "ctrl+w": self.close_current, "ctrl+f4": self.close_current,
            "ctrl+tab": lambda: self.cycle_tab(1), "ctrl+shift+tab": lambda: self.cycle_tab(-1),
            "ctrl+shift+iso_left_tab": lambda: self.cycle_tab(-1),
            "ctrl+f": lambda: self._edit("find"), "ctrl+h": lambda: self._edit("replace"),
            "ctrl+g": self.goto_line_prompt, "ctrl+shift+p": self.command_palette, "ctrl+p": self.command_palette,
            "ctrl+b": self.toggle_blocks, "ctrl+1": lambda: self.set_view("code"),
            "ctrl+2": lambda: self.set_view("blocks"), "ctrl+3": lambda: self.set_view("split"),
            "ctrl+equal": lambda: self.zoom(1), "ctrl+plus": lambda: self.zoom(1),
            "ctrl+shift+plus": lambda: self.zoom(1), "ctrl+minus": lambda: self.zoom(-1),
            "ctrl+0": lambda: self.zoom(0), "ctrl+comma": self.open_settings, "ctrl+j": self.toggle_bottom,
            "ctrl+backslash": self.toggle_side_bar, "ctrl+shift+e": lambda: self.show_side_panel("files"),
            "ctrl+shift+o": lambda: self.show_side_panel("outline"),
            "ctrl+shift+a": lambda: self.show_side_panel("assets"),
            "ctrl+shift+u": lambda: self.show_bottom_panel("output"),
            "ctrl+shift+m": lambda: self.show_bottom_panel("problems"),
            "ctrl+shift+v": lambda: self.show_bottom_panel("variables"),
            "ctrl+shift+b": self.open_export, "ctrl+shift+c": self.open_converter,
        }
        self.root.bind_class("GublanKeys", "<KeyPress>", self._on_key, add="+")
        self.root.bind("<KeyPress>", self._on_key, add="+")

    def _on_key(self, event):
        keysym = event.keysym
        state = event.state
        ctrl = bool(state & 0x4)
        if not ctrl and not re.match(r"^F\d+$", keysym):
            return None
        shift = bool(state & 0x1)
        name = ("ctrl+" if ctrl else "") + ("shift+" if shift else "") + keysym.lower()
        action = self.shortcuts.get(name)
        if action is None:
            return None
        try:
            if event.widget.winfo_toplevel() is not self.root:
                return None
        except (AttributeError, tk.TclError, KeyError):
            pass
        self.root.after_idle(action)
        return "break"

    def _edit(self, what):
        doc = self.current
        if doc is None:
            return
        editor = doc.editor
        if what == "find":
            if doc.view == "blocks":
                self.set_view("code")
            editor.show_find(replace=False)
            return
        if what == "replace":
            if doc.view == "blocks":
                self.set_view("code")
            editor.show_find(replace=True)
            return
        if doc.view == "blocks" and what in ("undo", "redo"):
            getattr(editor, what)()
            doc.sync_blocks()
            return
        editor.focus_editor()
        text = editor.text
        actions = {
            "undo": editor.undo, "redo": editor.redo, "select_all": editor.select_all,
            "definition": editor.goto_definition, "comment": editor.toggle_comment,
            "duplicate": editor.duplicate_line, "up": lambda: editor.move_lines(-1),
            "down": lambda: editor.move_lines(1), "delete": editor.delete_line,
            "indent": lambda: editor.indent_lines(1), "dedent": lambda: editor.indent_lines(-1),
            "complete": lambda: editor.update_completion(auto=False), "breakpoint": editor.toggle_breakpoint,
        }
        if what in actions:
            actions[what]()
        else:
            text.event_generate(what)

    # ----- panels ---------------------------------------------------------------------------------------------
    def side_visible(self):
        return str(self.side) in [str(pane) for pane in self.hpanes.panes()]

    def bottom_visible(self):
        return str(self.bottom) in [str(pane) for pane in self.vpanes.panes()]

    def show_side_panel(self, name, visible=True):
        if not visible:
            if self.side_visible():
                if self.side.winfo_width() > 50:
                    self.settings["side_width"] = unpx(self.side.winfo_width())
                self.hpanes.forget(self.side)
            self.settings["show_side"] = False
            self._paint_activity(None)
            return
        if not self.side_visible():
            self.hpanes.add(self.side, before=self.vpanes, width=px(self.settings.get("side_width", 250)),
                            minsize=px(170), stretch="never")
        for panel_name, panel in self.side_panels.items():
            if panel_name == name:
                panel.pack(fill="both", expand=True)
            else:
                panel.pack_forget()
        self.side_name = name
        self.settings["side_panel"] = name
        self.settings["show_side"] = True
        self._paint_activity(name)
        if name == "outline" and self.current:
            self.side_panels["outline"].show(self.current.editor.symbols)

    def _paint_activity(self, active):
        for name, button in self.activity_buttons.items():
            button.set_checked(name == active)

    def toggle_side(self, name):
        if self.side_visible() and self.side_name == name:
            self.show_side_panel(name, visible=False)
        else:
            self.show_side_panel(name)

    def toggle_side_bar(self):
        self.show_side_panel(self.side_name, visible=not self.side_visible())

    def show_bottom_panel(self, name, visible=True):
        if not visible:
            if self.bottom_visible():
                height = self.bottom.winfo_height()
                if height > 60:
                    self.settings["bottom_height"] = unpx(height)
                self.vpanes.forget(self.bottom)
            self.settings["show_bottom"] = False
            return
        if not self.bottom_visible():
            self.vpanes.add(self.bottom, height=px(self.settings.get("bottom_height", 210)), minsize=px(90),
                            stretch="never")
        for panel_name, panel in self.bottom_panels.items():
            label_widget, line = self.bottom_tabs[panel_name]
            if panel_name == name:
                panel.pack(fill="both", expand=True)
                label_widget.configure(fg=TEXT)
                line.configure(bg=MOSS_LIGHT)
            else:
                panel.pack_forget()
                label_widget.configure(fg=MUTED)
                line.configure(bg=PANEL)
        self.bottom_name = name
        self.settings["bottom_panel"] = name
        self.settings["show_bottom"] = True
        if name == "variables":
            self.refresh_variables()

    def toggle_bottom(self):
        self.show_bottom_panel(self.bottom_name, visible=not self.bottom_visible())

    def show_help(self, topic):
        self.show_side_panel("help")
        if topic:
            self.side_panels["help"].show_topic(topic)
        else:
            self.side_panels["help"].show_topic(None)

    # ----- documents and tabs -------------------------------------------------------------------------------------
    def new_tab(self, source="", name=None, path=None, select=True):
        self._hide_welcome()
        doc = Document(self, path=path, text=source, name=name)
        self.docs.append(doc)
        self._make_tab(doc)
        if select:
            self.select(doc)
        return doc

    def new_from_template(self, key):
        item = template(key)
        if not item:
            return
        doc = self.new_tab(item["source"], name=item["key"] if item["key"] != "blank" else None)
        doc.editor.goto_line(1)
        self.flash(f"made a new program from the {item['title']} template. press f5 to run it.")

    def _make_tab(self, doc):
        cell = tk.Frame(self.tab_strip, bg=PANEL, cursor="hand2")
        cell.pack(side="left", fill="y")
        accent = tk.Frame(cell, bg=PANEL, height=px(2))
        accent.pack(side="top", fill="x")
        row = tk.Frame(cell, bg=PANEL)
        row.pack(side="top", fill="both", expand=True)
        name = tk.Label(row, text=doc.name, bg=PANEL, fg=MUTED, font=ui_font(9), padx=px(4))
        name.pack(side="left", padx=(px(10), 0))
        close = tk.Label(row, text="", bg=PANEL, fg=DIM, font=icon_font(8), width=2, cursor="hand2")
        close.pack(side="left", padx=(px(2), px(6)))
        divider = tk.Frame(cell, bg=BORDER, width=1)
        divider.place(relx=1.0, rely=0, relheight=1.0, anchor="ne")
        doc.tab = {"cell": cell, "accent": accent, "row": row, "name": name, "close": close, "hover": False,
                   "tip": Tooltip(name, doc.path or "not saved yet")}
        for widget in (cell, row, name):
            widget.bind("<Button-1>", lambda _e, d=doc: self.select(d))
            widget.bind("<Button-2>", lambda _e, d=doc: self.close_tab(d))
            widget.bind("<Button-3>", lambda e, d=doc: self._tab_menu(e, d))
            widget.bind("<MouseWheel>", self._tab_wheel)
        close.bind("<Button-1>", lambda _e, d=doc: self.close_tab(d))
        for widget in (cell, row, name, close):
            widget.bind("<Enter>", lambda _e, d=doc: self._tab_hover(d, True), add="+")
            widget.bind("<Leave>", lambda _e, d=doc: self._tab_hover(d, False), add="+")
        self._paint_tab(doc)

    def _tab_hover(self, doc, inside):
        if doc.tab:
            doc.tab["hover"] = inside
            self._paint_tab(doc)

    def _paint_tab(self, doc):
        tab = doc.tab
        if not tab:
            return
        active = doc is self.current
        bg = EDITOR_BG if active else (HOVER if tab["hover"] else PANEL)
        for key in ("cell", "row", "name", "close"):
            tab[key].configure(bg=bg)
        tab["accent"].configure(bg=MOSS_LIGHT if active else bg)
        tab["name"].configure(text=doc.name, fg=TEXT if active else MUTED)
        tab["tip"].text = lower(doc.path or "not saved yet")
        if doc.dirty and not tab["hover"]:
            tab["close"].configure(text="●", font=ui_font(8), fg=NUMBER)
        else:
            tab["close"].configure(text=icon("close", "x"), font=icon_font(8),
                                   fg=MUTED if tab["hover"] or active else bg)

    def _tab_menu(self, event, doc):
        others = [d for d in self.docs if d is not doc]
        show_menu(doc.tab["cell"], [
            ("close", lambda: self.close_tab(doc), "ctrl+w"),
            {"label": "close the others", "command": lambda: [self.close_tab(d) for d in others],
             "enabled": bool(others)},
            "-",
            {"label": "copy path", "command": lambda: self._copy(doc.path), "enabled": bool(doc.path)},
            {"label": "show in explorer", "command": lambda: reveal(doc.path), "enabled": bool(doc.path)},
            {"label": "rename...", "command": lambda: self.rename(doc), "enabled": bool(doc.path)},
        ], event.x_root, event.y_root)

    def _copy(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.flash("copied")

    def select(self, doc):
        if doc not in self.docs:
            return
        previous = self.current
        if previous is doc:
            doc.editor.focus_editor()
            return
        if previous is not None:
            previous.frame.pack_forget()
        self._hide_welcome()
        self.current = doc
        doc.frame.pack(fill="both", expand=True)
        for other in self.docs:
            self._paint_tab(other)
        self.root.after_idle(lambda: self._scroll_tab_into_view(doc))
        if doc.view == "blocks" and doc.blocks is not None:
            doc.blocks.focus_set()
        else:
            doc.editor.focus_editor()
        self.update_title()
        self.update_view_buttons()
        self._show_status_for(doc)
        self.side_panels["outline"].show(doc.editor.symbols)
        folder = doc.folder or self.settings.get("folder") or None
        self.side_panels["assets"].set_folder(folder)
        if doc.folder and not self.settings.get("folder"):
            self.side_panels["files"].set_folder(doc.folder)
        self.problems.show(doc.diagnostics)
        self.schedule_analysis(doc, 50)

    def _scroll_tab_into_view(self, doc):
        try:
            cell = doc.tab["cell"]
            total = max(1, self.tab_strip.winfo_reqwidth())
            left = cell.winfo_x()
            right = left + cell.winfo_width()
            first, last = self.tab_canvas.xview()
            view_left, view_right = first * total, last * total
            if left < view_left:
                self.tab_canvas.xview_moveto(left / total)
            elif right > view_right:
                self.tab_canvas.xview_moveto(max(0, (right - (view_right - view_left)) / total))
        except (tk.TclError, TypeError):
            pass

    def cycle_tab(self, step):
        if len(self.docs) < 2 or self.current is None:
            return
        index = self.docs.index(self.current)
        self.select(self.docs[(index + step) % len(self.docs)])

    def close_current(self):
        if self.current:
            self.close_tab(self.current)

    def close_tab(self, doc, ask_first=True):
        if doc not in self.docs:
            return True
        if ask_first and doc.dirty:
            answer = confirm(self.root, "close", f"save the changes to {doc.name} before closing?", yes="save",
                             no="cancel", third="don't save")
            if answer is None or answer is False:
                return False
            if answer is True and not self.save(doc):
                return False
        if self.run_doc is doc and self.running():
            self.stop()
        index = self.docs.index(doc)
        self.docs.remove(doc)
        doc.tab["cell"].destroy()
        doc.frame.destroy()
        if self.current is doc:
            self.current = None
            if self.docs:
                self.select(self.docs[min(index, len(self.docs) - 1)])
            else:
                self._show_empty()
        return True

    def _show_empty(self):
        self.update_title()
        self.update_view_buttons()
        self.problems.show([])
        self.side_panels["outline"].show({})
        self.status_position.configure(text="")
        self.status_problems.configure(text="")
        if self.settings.get("show_welcome", True):
            self.show_welcome_tab()
        else:
            self.empty_hint.place(relx=0.5, rely=0.45, anchor="center")

    def show_welcome_tab(self):
        if self.current is not None:
            self.current.frame.pack_forget()
            self.current = None
            for doc in self.docs:
                self._paint_tab(doc)
            self.update_title()
            self.update_view_buttons()
        if self.welcome is not None:
            self.welcome.destroy()
        self.empty_hint.place_forget()
        self.welcome = WelcomePage(self.content, self)
        self.welcome.pack(fill="both", expand=True)

    def _hide_welcome(self):
        if self.welcome is not None:
            self.welcome.destroy()
            self.welcome = None
        self.empty_hint.place_forget()

    def update_title(self):
        doc = self.current
        if doc is None:
            self.root.title(APP_NAME)
            return
        mark = "● " if doc.dirty else ""
        where = f"  ({self._short(doc.folder, 50)})" if doc.folder else ""
        self.root.title(f"{mark}{doc.name}{where} - {APP_NAME}")

    @staticmethod
    def _short(path, limit=60):
        if not path:
            return ""
        return path if len(path) <= limit else "..." + path[-limit:]

    # ----- views ------------------------------------------------------------------------------------------
    def set_view(self, view):
        doc = self.current
        if doc is None:
            return
        if doc.view != view:
            doc.set_view(view)
        self.update_view_buttons()

    def toggle_blocks(self):
        doc = self.current
        if doc is not None:
            self.set_view("code" if doc.view == "blocks" else "blocks")

    def update_view_buttons(self):
        view = self.current.view if self.current else None
        for name, button in getattr(self, "view_buttons", {}).items():
            button.set_checked(name == view)
            button.set_enabled(self.current is not None)

    # ----- editor callbacks ---------------------------------------------------------------------------------
    def on_changed(self, doc):
        self._paint_tab(doc)
        if doc is self.current:
            self.update_title()
        self.schedule_analysis(doc)
        if doc.blocks is not None and doc.view != "code":
            if doc.blocks_job:
                self.root.after_cancel(doc.blocks_job)
            doc.blocks_job = self.root.after(500 if doc.view == "split" else 50, doc.sync_blocks)

    def on_cursor(self, doc, line, column):
        if doc is self.current:
            self.status_position.configure(text=f"line {line}, column {column + 1}")

    def on_symbols(self, doc):
        if doc is self.current and self.side_name == "outline" and self.side_visible():
            self.side_panels["outline"].show(doc.editor.symbols)

    def on_breakpoints(self, doc):
        if doc is self.run_doc:
            self.run_breakpoints = set(doc.editor.breakpoints)

    def clear_breakpoints(self):
        for doc in self.docs:
            doc.editor.breakpoints.clear()
            doc.editor.draw_gutter()
            self.on_breakpoints(doc)

    def value_of(self, name):
        runtime = self.active_runtime
        if runtime is None or not self.running():
            return None
        try:
            if name in runtime.vars:
                return format_value(runtime.vars[name])
        except Exception:  # noqa: BLE001 - values can change under us while the program runs
            return None
        return None

    def define_elsewhere(self, doc, word):
        base = doc.folder or self.settings.get("folder") or os.getcwd()
        for name, path in find_includes(doc.editor.get(), base).items():
            del name
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    lines = handle.read().splitlines()
            except OSError:
                continue
            for number, raw in enumerate(lines, start=1):
                parts = raw.split()
                if len(parts) >= 2 and parts[0] == "function" and parts[1] == word:
                    target = self.open_path(path)
                    if target:
                        target.editor.goto_line(number, select_line=True)
                    return True
        for other in self.docs:
            if other is doc:
                continue
            info = other.editor.symbols.get("functions", {}).get(word)
            if info:
                self.select(other)
                other.editor.goto_line(info["line"], select_line=True)
                return True
        self.flash(f"couldn't find where {word} is made")
        return False

    # ----- problems -------------------------------------------------------------------------------------------
    def schedule_analysis(self, doc, delay=450):
        if doc.analysis_job:
            self.root.after_cancel(doc.analysis_job)
        doc.analysis_job = self.root.after(delay, lambda: self._analyse(doc))

    def _analyse(self, doc):
        doc.analysis_job = None
        if doc not in self.docs:
            return
        version = doc.editor.version
        if version == doc.analysed_version:
            self._show_problems(doc)
            return
        source = doc.editor.get()
        warnings = bool(self.settings.get("warnings", True))

        def work():
            try:
                items = analyze_source(source, warnings=warnings)
            except Exception as err:  # noqa: BLE001 - the checker must never take the editor down
                items = [{"line": None, "severity": "warning", "message": f"the checker had a problem: {err}"}]
            try:
                self.root.after(0, lambda: self._analysed(doc, version, items))
            except (RuntimeError, tk.TclError):
                pass

        threading.Thread(target=work, daemon=True).start()

    def _analysed(self, doc, version, items):
        if doc not in self.docs or doc.editor.version != version:
            return
        doc.analysed_version = version
        doc.diagnostics = list(items) + [item for item in doc.diagnostics if item.get("runtime")]
        doc.editor.set_diagnostics(doc.diagnostics)
        self._show_problems(doc)

    def _show_problems(self, doc):
        if doc is not self.current:
            return
        self.problems.show(doc.diagnostics)
        errors = sum(1 for item in doc.diagnostics if item.get("severity", "error") == "error")
        warnings = len(doc.diagnostics) - errors
        label_widget, _line = self.bottom_tabs["problems"]
        label_widget.configure(text=f"problems ({len(doc.diagnostics)})" if doc.diagnostics else "problems")
        if errors or warnings:
            parts = []
            if errors:
                parts.append(f"{errors} error{'s' if errors != 1 else ''}")
            if warnings:
                parts.append(f"{warnings} warning{'s' if warnings != 1 else ''}")
            self.status_problems.configure(text=", ".join(parts), fg=ERROR if errors else NUMBER)
        else:
            self.status_problems.configure(text="no problems", fg=MUTED)

    def _show_status_for(self, doc):
        line, column = doc.editor.cursor()
        self.status_position.configure(text=f"line {line}, column {column + 1}")
        self.status_indent.configure(text=f"{self.settings.get('indent', 4)} spaces")
        self._show_problems(doc)

    def check_now(self):
        doc = self.current
        if doc is None:
            return
        source = doc.editor.get()
        items = analyze_source(source, warnings=bool(self.settings.get("warnings", True)))
        doc.analysed_version = doc.editor.version
        doc.diagnostics = list(items)
        doc.editor.set_diagnostics(doc.diagnostics)
        self._show_problems(doc)
        self.show_bottom_panel("problems")

    # ----- files ------------------------------------------------------------------------------------------------
    def open_dialog(self):
        initial = (self.current.folder if self.current and self.current.folder else None) or \
            self.settings.get("folder") or os.getcwd()
        paths = filedialog.askopenfilenames(parent=self.root, title="open a program", initialdir=initial,
                                            filetypes=CODE_TYPES + [("code to convert", "*.py *.js *.lua")])
        last = None
        for path in paths:
            last = self.open_path(path) or last
        return last

    def open_path(self, path):
        path = os.path.abspath(path)
        for doc in self.docs:
            if doc.path and os.path.normcase(doc.path) == os.path.normcase(path):
                self.select(doc)
                return doc
        if os.path.isdir(path):
            self.set_folder(path)
            return None
        extension = os.path.splitext(path)[1].lower()
        if extension in FOREIGN:
            self.open_converter(path)
            return None
        if extension in (".png", ".gif", ".jpg", ".jpeg", ".bmp", ".wav", ".ogg", ".mp3", ".exe", ".ico"):
            reveal(path)
            return None
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                text = handle.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="latin-1") as handle:
                text = handle.read()
        except OSError as err:
            message(self.root, "open", f"could not open {os.path.basename(path)}: {str(err).lower()}", "error")
            return None
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # an untouched empty untitled tab is replaced by the file
        current = self.current
        replace = current if current and not current.path and not current.dirty and not current.editor.get() \
            else None
        doc = self.new_tab(text, path=path)
        if replace is not None:
            self.close_tab(replace, ask_first=False)
            self.select(doc)
        config.add_recent(self.settings, path)
        if not self.settings.get("folder"):
            self.side_panels["files"].set_folder(os.path.dirname(path))
        return doc

    def save(self, doc=None):
        doc = doc or self.current
        if doc is None:
            return False
        if doc.view == "blocks" and doc.blocks is not None:
            doc.blocks.push(now=True)
        if not doc.path:
            return self.save_as(doc)
        return self._write(doc, doc.path)

    def save_as(self, doc=None):
        doc = doc or self.current
        if doc is None:
            return False
        initial = doc.folder or self.settings.get("folder") or os.getcwd()
        name = doc.name if doc.path else re.sub(r"[^\w\- ]+", "", doc.name).replace(" ", "_") + ".gubl"
        path = filedialog.asksaveasfilename(parent=self.root, title="save program", initialdir=initial,
                                            initialfile=name, defaultextension=".gubl", filetypes=CODE_TYPES)
        if not path:
            return False
        ok = self._write(doc, path)
        if ok:
            doc.path = os.path.abspath(path)
            config.add_recent(self.settings, doc.path)
            self._paint_tab(doc)
            self.update_title()
            self.side_panels["assets"].set_folder(doc.folder)
            self.side_panels["files"].refresh()
        return ok

    def _write(self, doc, path):
        text = doc.editor.get()
        try:
            temporary = path + ".saving"
            with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text if text.endswith("\n") or not text else text + "\n")
            os.replace(temporary, path)
        except OSError as err:
            message(self.root, "save", f"could not save {os.path.basename(path)}: {str(err).lower()}", "error")
            return False
        doc.editor.mark_saved()
        self._paint_tab(doc)
        self.update_title()
        self.flash(f"saved {os.path.basename(path)}")
        return True

    def save_all(self):
        for doc in list(self.docs):
            if doc.dirty:
                if not self.save(doc):
                    return False
        return True

    def rename(self, doc):
        if not doc.path:
            return
        new = ask(self.root, "rename", "new name", os.path.basename(doc.path))
        if not new or new == os.path.basename(doc.path):
            return
        target = os.path.join(os.path.dirname(doc.path), new)
        if os.path.exists(target):
            message(self.root, "rename", f"{new} already exists", "error")
            return
        try:
            os.rename(doc.path, target)
        except OSError as err:
            message(self.root, "rename", str(err).lower(), "error")
            return
        doc.path = target
        self._paint_tab(doc)
        self.update_title()
        self.side_panels["files"].refresh()

    def choose_folder(self):
        folder = filedialog.askdirectory(parent=self.root, title="open a folder",
                                         initialdir=self.settings.get("folder") or os.getcwd())
        if folder:
            self.set_folder(folder)

    def set_folder(self, folder):
        self.settings["folder"] = os.path.abspath(folder)
        self.side_panels["files"].set_folder(self.settings["folder"])
        self.show_side_panel("files")
        if self.current is None or not self.current.folder:
            self.side_panels["assets"].set_folder(self.settings["folder"])

    def project_folder(self, doc=None):
        doc = doc or self.current
        return (doc.folder if doc else None) or self.settings.get("folder") or None

    def pick_asset(self):
        folder = self.project_folder()
        if not folder:
            message(self.root, "choose a file", "save your program first, so its files can be found next to it.")
            return None
        assets = os.path.join(folder, "assets")
        path = filedialog.askopenfilename(parent=self.root, title="choose a picture or sound",
                                          initialdir=assets if os.path.isdir(assets) else folder, filetypes=[
                                              ("pictures and sounds", "*.png *.gif *.jpg *.jpeg *.bmp *.wav *.ogg "
                                                                      "*.mp3"), ("all files", "*.*")])
        if not path:
            return None
        try:
            inside = os.path.commonpath((os.path.realpath(folder), os.path.realpath(path))) == \
                os.path.realpath(folder)
        except ValueError:
            inside = False
        if not inside:
            import shutil
            os.makedirs(assets, exist_ok=True)
            target = os.path.join(assets, os.path.basename(path))
            if not os.path.exists(target):
                shutil.copy2(path, target)
            path = target
            self.side_panels["assets"].refresh()
            self.flash(f"copied {os.path.basename(path)} into assets")
        return os.path.relpath(path, folder).replace(os.sep, "/")

    def insert_code(self, code):
        doc = self.current
        if doc is None:
            doc = self.new_tab()
        if doc.view == "blocks":
            doc.blocks.insert_blocks(blocks_module.parse_blocks(code))
            return
        doc.editor.insert_lines(code)
        doc.editor.focus_editor()

    def sprite_editor(self, path):
        folder = self.project_folder()
        if not folder:
            message(self.root, "sprite painter", "save your program first. sprites are kept in an assets folder "
                                                 "next to it.")
            return
        assets = os.path.join(folder, "assets")

        def saved(saved_path):
            self.side_panels["assets"].refresh()
            relative = os.path.relpath(saved_path, folder).replace(os.sep, "/")
            self.flash(f"saved {relative}. double-click it in assets to use it.")

        editor = SpriteEditor(self.root, assets, saved, path)
        editor.show(width=px(860), height=px(640))

    def open_converter(self, path=None):
        def opened(text, name):
            doc = self.new_tab(text, name=f"{name} (gublan)")
            doc.editor.goto_line(1)
            self.check_now()

        dialog = ConvertDialog(self.root, on_open=opened, initial_path=path)
        dialog.show(width=px(1100), height=px(700))

    def open_settings(self):
        if self.settings_dialog is not None:
            try:
                self.settings_dialog.lift()
                return
            except tk.TclError:
                self.settings_dialog = None
        dialog = SettingsDialog(self.root, self.settings, lambda settings: self.apply_settings(settings))
        self.settings_dialog = dialog
        dialog.bind("<Destroy>", lambda e: setattr(self, "settings_dialog", None) if e.widget is dialog else None,
                    add="+")
        dialog.show(width=px(600), height=px(min(760, self.root.winfo_screenheight() - 120)), modal=False)

    def open_export(self):
        doc = self.current
        if doc is None:
            message(self.root, "export", "open a program first")
            return
        if doc.view == "blocks" and doc.blocks is not None:
            doc.blocks.push(now=True)
        if not doc.path:
            if not confirm(self.root, "export", "save your program first, so its pictures and sounds can be found.",
                           yes="save"):
                return
            if not self.save_as(doc):
                return
        if self.export_dialog is not None:
            try:
                if self.export_dialog.winfo_exists():
                    self.export_dialog.lift()
                    return
            except tk.TclError:
                pass
        dialog = ExportDialog(self, doc.editor.get(), doc.folder, os.path.splitext(doc.name)[0])
        self.export_dialog = dialog
        dialog.show(width=px(780), height=px(640), modal=False)

    def open_command_docs(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "COMMANDS.md")
        if os.path.isfile(path):
            os.startfile(path) if sys.platform == "win32" else reveal(path)  # noqa: S606
        else:
            self.show_help(None)

    def about(self):
        message(self.root, "about", f"{APP_NAME}\n\nmake games and programs with simple commands.\n\n"
                                    f"python {sys.version.split()[0]}, tk {self.root.tk.call('info', 'patchlevel')}\n"
                                    f"settings: {config.settings_path()}")

    # ----- export (used by the export window and the tests) -------------------------------------------------
    def buildscript_exe(self, source, output, python, base_dir=None, progress=None, options=None, **kwargs):
        """build a .exe in the calling thread and report back through exportfinished on the tk thread."""
        options = dict(options or {})
        options.update(kwargs)
        try:
            result = exporter.build(source, output, python, base_dir or os.getcwd(), self.runtime._expand_includes,
                                    progress=progress, **options)
            error = ""
        except exporter.ExportError as err:
            result, error = output, str(err)
        except Exception as err:  # noqa: BLE001 - shown to the user instead of crashing the worker
            result, error = output, f"{type(err).__name__}: {err}"
        self.root.after(0, self.exportfinished, result, error)

    def exportfinished(self, output, error):
        dialog = self.export_dialog
        try:
            alive = dialog is not None and dialog.winfo_exists()
        except tk.TclError:
            alive = False
        if alive:
            dialog.finished(output, error)
        if error:
            self.output.write(f"export failed: {lower(error)}", "error")
            if not alive:
                message(self.root, "export", "export failed", "error", details=error)
        else:
            self.output.write(f"exported {output}", "good")
            self.flash(f"exported {os.path.basename(output)}")

    # ----- running -----------------------------------------------------------------------------------------
    def running(self):
        return self.run_active

    def run_or_continue(self):
        if self.running():
            if self.paused:
                self.resume()
            else:
                self.flash("already running. shift+f5 stops it.")
            return
        self.start_run()

    def start_run(self, step=False):
        doc = self.current
        if doc is None:
            self.flash("open or make a program first")
            return
        if doc.view == "blocks" and doc.blocks is not None:
            doc.blocks.push(now=True)
        if self.settings.get("autosave") and doc.path and doc.dirty:
            self.save(doc)
        source = doc.editor.get()
        if not source.strip():
            self.flash("this program is empty. try print hello")
            return
        if self.settings.get("check_before_run", True):
            items = analyze_source(source, warnings=bool(self.settings.get("warnings", True)))
            doc.analysed_version = doc.editor.version
            doc.diagnostics = list(items)
            doc.editor.set_diagnostics(items)
            self._show_problems(doc)
            errors = [item for item in items if item.get("severity", "error") == "error"]
            if errors:
                first = errors[0]
                self.show_bottom_panel("problems")
                if first.get("line"):
                    doc.editor.goto_line(first["line"], select_line=False)
                self.set_state(f"fix line {first.get('line') or '?'} first", ERROR)
                self.flash(f"line {first.get('line') or '?'}: {lower(first['message'])}")
                return
        base_dir = doc.folder or self.settings.get("folder") or os.getcwd()
        if self.settings.get("clear_output", True):
            self.output.clear()
        self.output.cancel_question()
        self.output.write(f"running {doc.name}", "info")
        doc.diagnostics = [item for item in doc.diagnostics if not item.get("runtime")]
        doc.editor.set_diagnostics(doc.diagnostics)
        self.run_doc = doc
        self.run_breakpoints = set(doc.editor.breakpoints)
        self.run_includes = find_includes(source, base_dir)
        self.stop_event = threading.Event()
        self.resume_event = threading.Event()
        self.paused = False
        self.pause_requested = False
        self.step_mode = step
        self.paused_line = None
        runtime = GublanRuntime(onlog=self._from_log, shouldstop=self.stop_event.is_set, waitstep=self._waitstep,
                                base_dir=base_dir, onerror=self._from_error, hold_window=True,
                                oninput=self._from_input, onpopup=self._from_popup)
        self.active_runtime = runtime
        self.variables.previous = {}
        self.run_started = time.perf_counter()
        self.run_thread = threading.Thread(target=self._run_worker, args=(runtime, source, base_dir), daemon=True)
        self.run_active = True
        self.run_thread.start()
        self.set_state("running", MOSS_LIGHT)
        self.update_run_controls()
        if self.settings.get("show_variables_on_run") and self.settings.get("show_bottom", True):
            self.show_bottom_panel("variables" if not self._is_text_program(source) else "output")
        elif not self.bottom_visible() or self.bottom_name != "output":
            self.show_bottom_panel("output")
        self.root.after(250, self._watch_run)

    @staticmethod
    def _is_text_program(source):
        return not exporter.uses_window(source)

    def _run_worker(self, runtime, source, base_dir):
        try:
            runtime.run(source, base_dir)
        except Exception as err:  # noqa: BLE001 - report crashes inside the runtime instead of hiding them
            self.queue.put(("error", f"the program crashed: {type(err).__name__}: {err}", None, None))
        self.queue.put(("done", runtime))

    # callbacks from the runner thread (never touch tk here: only the queue) ---------------------------
    def _from_log(self, text):
        self.queue.put(("log", str(text)))

    def _from_error(self, text, file, line):
        self.queue.put(("error", str(text), file, line))

    def _from_input(self, prompt):
        holder = {"event": threading.Event(), "value": None}
        self.queue.put(("input", str(prompt), holder))
        while not holder["event"].wait(0.05):
            if self.stop_event.is_set():
                return None
        return holder["value"]

    def _from_popup(self, text):
        holder = {"event": threading.Event(), "value": None}
        self.queue.put(("popup", str(text), holder))
        while not holder["event"].wait(0.05):
            if self.stop_event.is_set():
                return

    def _waitstep(self, line):
        runtime = self.active_runtime
        statement = runtime.current if runtime is not None else None
        in_main = statement is None or statement.file is None
        if not in_main:
            return
        if not (self.step_mode or self.pause_requested or line in self.run_breakpoints):
            return
        self.pause_requested = False
        self.paused = True
        self.resume_event.clear()
        self.queue.put(("paused", line))
        last_pump = 0.0
        while not self.resume_event.wait(0.03):
            if self.stop_event.is_set():
                break
            if runtime is not None and runtime.screen is not None:
                now = time.perf_counter()
                if now - last_pump > 0.05:
                    last_pump = now
                    try:
                        runtime.pumpevents()
                    except Exception:  # noqa: BLE001 - a closed window simply stops the program
                        self.stop_event.set()
                    if not runtime.running:
                        break
        self.paused = False

    # tk side ---------------------------------------------------------------------------------------
    def _poll(self):
        try:
            logs = []
            for _ in range(3000):
                try:
                    item = self.queue.get_nowait()
                except queue.Empty:
                    break
                kind = item[0]
                if kind == "log":
                    logs.append(item[1])
                    continue
                if logs:
                    self._write_logs(logs)
                    logs = []
                self._handle(item)
            if logs:
                self._write_logs(logs)
        finally:
            self.root.after(30, self._poll)

    def _write_logs(self, logs):
        if len(logs) > 1500:
            skipped = len(logs) - 1500
            logs = [f"... {skipped} earlier lines skipped to keep up ..."] + logs[-1500:]
        self.output.write("\n".join(logs))

    def _handle(self, item):
        kind = item[0]
        if kind == "error":
            _kind, text, file, line = item
            where = f"{file} line {line}: " if file and line else f"line {line}: " if line else ""
            self.output.write(f"{where}{lower(text)}", "error")
            doc = self.run_doc
            if doc in self.docs and line and not file:
                doc.diagnostics = [entry for entry in doc.diagnostics if not entry.get("runtime")] + [
                    {"line": line, "severity": "error", "message": text, "runtime": True}]
                doc.editor.set_diagnostics(doc.diagnostics)
                if doc is self.current:
                    doc.editor.goto_line(line)
                    self._show_problems(doc)
            self.show_bottom_panel("output")
            self.set_state(f"stopped: error on line {line}" if line else "stopped with an error", ERROR)
        elif kind == "input":
            _kind, prompt, holder = item
            self.show_bottom_panel("output")
            self.pending_answer = holder

            def answered(value, h=holder):
                h["value"] = value
                h["event"].set()
                if self.pending_answer is h:
                    self.pending_answer = None

            self.output.ask(prompt, answered)
            self.set_state("waiting for your answer", NUMBER)
        elif kind == "popup":
            _kind, text, holder = item
            self.output.write(text, "system")
            # shown from the main loop, not from inside _poll, so the modal wait can't start a second poll loop
            self.root.after(0, lambda: self._show_popup(text, holder))
        elif kind == "paused":
            line = item[1]
            self.paused_line = line
            doc = self.run_doc
            if doc in self.docs:
                if doc is not self.current:
                    self.select(doc)
                if doc.view == "blocks":
                    self.set_view("split")
                doc.editor.set_debug_line(line)
            self.set_state(f"paused on line {line}. f5 continues, f10 steps", NUMBER)
            if self.bottom_name != "variables" or not self.bottom_visible():
                self.show_bottom_panel("variables")
            self.refresh_variables()
            self.update_run_controls()
        elif kind == "done":
            runtime = item[1]
            if runtime is not self.active_runtime:
                return
            self._finished(runtime)

    def _show_popup(self, text, holder):
        self.set_state("showing a message", NUMBER)
        message(self.root, self.run_doc.name if self.run_doc else "message", text)
        holder["event"].set()
        if self.running():
            self.set_state("running", MOSS_LIGHT)

    def _finished(self, runtime):
        self.run_active = False
        seconds = time.perf_counter() - self.run_started
        doc = self.run_doc
        if doc in self.docs:
            doc.editor.set_debug_line(None)
        self.output.cancel_question()
        if self.pending_answer:
            self.pending_answer["event"].set()
            self.pending_answer = None
        self.refresh_variables(final=True)
        if runtime.last_error:
            self.set_state(*self._state)
        elif self.stop_event.is_set():
            self.output.write("stopped", "info")
            self.set_state("stopped", MUTED)
        else:
            self.output.write(f"finished in {seconds:.2f} s", "info")
            self.set_state("finished", MOSS_LIGHT)
        self.paused = False
        self.update_run_controls()

    def _watch_run(self):
        if not self.running():
            return
        runtime = self.active_runtime
        if not self.paused and runtime is not None:
            statement = runtime.current
            if runtime.finished and runtime.screen is not None:
                if self._state[0] != "finished: close the game window or press stop":
                    self.set_state("finished: close the game window or press stop", MOSS_LIGHT)
            elif statement is not None and statement.file is None and self.pending_answer is None \
                    and self._state[0].startswith("running"):
                self.set_state(f"running, line {statement.line}", MOSS_LIGHT)
            if self.bottom_name == "variables" and self.bottom_visible():
                self.refresh_variables()
        self.root.after(250, self._watch_run)

    def refresh_variables(self, final=False):
        runtime = self.active_runtime
        if runtime is None:
            return
        for _attempt in range(3):
            try:
                variables = dict(runtime.vars)
                objects = {name: dict(info) if isinstance(info, dict) else info
                           for name, info in list(runtime.objects.items())
                           if not str(name).startswith(("button:", "uibtn"))}
                break
            except RuntimeError:
                continue
        else:
            return
        where = "finished" if final else (f"paused on line {self.paused_line}" if self.paused else "running")
        try:
            self.variables.refresh((variables, objects, where))
        except (RuntimeError, tk.TclError):
            return
        if final:
            self.variables.set_state(f"values when the program ended ({len(variables)} variables)", MUTED)
        elif self.paused:
            self.variables.set_state(f"paused on line {self.paused_line}", NUMBER)
        else:
            self.variables.set_state("running: values update four times a second", MOSS_LIGHT)

    def evaluate_watch(self, expression, variables, objects):
        runtime = self.active_runtime or self.console_runtime
        del objects
        if runtime is None:
            return ""
        try:
            node = parse_expression(expression)
            saved = runtime.vars
            if not self.running():
                runtime.vars = variables
            try:
                return format_value(runtime._eval(node, lenient=False))
            finally:
                runtime.vars = saved
        except Exception as err:  # noqa: BLE001 - shown in the panel
            return f"({lower(getattr(err, 'message', err))})"

    def stop(self):
        if not self.running():
            return
        self.stop_event.set()
        self.resume_event.set()
        if self.pending_answer:
            self.pending_answer["event"].set()
        self.set_state("stopping...", MUTED)

    def pause(self):
        if self.running() and not self.paused:
            self.pause_requested = True

    def resume(self):
        if self.running() and self.paused:
            self.step_mode = False
            doc = self.run_doc
            if doc in self.docs:
                doc.editor.set_debug_line(None)
            self.resume_event.set()
            self.set_state("running", MOSS_LIGHT)
            self.update_run_controls()

    def step(self):
        if not self.running():
            self.start_run(step=True)
            return
        self.step_mode = True
        if self.paused:
            self.resume_event.set()
        else:
            self.pause_requested = True

    def set_state(self, text, color=MOSS_LIGHT):
        self._state = (text, color)
        self.status_state.configure(text=f"●  {lower(text)}", fg=color)
        running = self.running()
        # running fills the bar with moss; paused uses the same dim moss as the paused line in the editor
        bg = MOSS_DARK if running and not self.paused else (DEBUG_LINE if running else PANEL)
        for widget in self.status_widgets:
            widget.configure(bg=bg)
        self.status_state.configure(fg=TEXT if running else color)

    def update_run_controls(self):
        if not hasattr(self, "run_button"):
            return
        running = self.running()
        labels = self.settings.get("toolbar_labels", True)
        if running and self.paused:
            self.run_button.configure_text("continue" if labels else "", icon_name="run")
        else:
            self.run_button.configure_text("run" if labels else "", icon_name="run")
        self.run_button.set_enabled(not running or self.paused)
        self.stop_button.set_enabled(running)
        self.pause_button.set_enabled(running and not self.paused)
        self.step_button.set_enabled(not running or self.paused)

    # ----- quick console ----------------------------------------------------------------------------
    def console_line(self, line):
        line = line.strip()
        first = line.split()[0] if line.split() else ""
        paused_runtime = self.active_runtime if self.running() and self.paused else None
        is_statement = first in COMMAND_SPECS or bool(re.match(r"^[\w.\[\]\"']+\s*(\+=|-=|\*=|/=|=)(?!=)", line))
        if not is_statement:
            runtime = paused_runtime or self._console()
            try:
                node = parse_expression(line)
                value = runtime._eval(node, lenient=False)
                self.output.write(format_value(value), "good")
            except Exception as err:  # noqa: BLE001 - shown to the user
                self.output.write(lower(getattr(err, "message", None) or err), "error")
            return
        if paused_runtime is not None:
            self.output.write("while a program is paused the console can only work out values, like score * 2",
                              "info")
            return
        if self.running():
            self.output.write("a program is running. stop it or pause it to use the console", "info")
            return
        if first not in CONSOLE_COMMANDS and first in COMMAND_SPECS:
            self.output.write(f"'{first}' needs a program. the console runs simple lines like print, "
                              "set, maths and lists.", "info")
            return
        runtime = self._console()
        try:
            mapped = [(line, None, 1)]
            runtime._compile(mapped)
            runtime.running = True
            runtime._exec(0, len(runtime._prog))
        except Exception as err:  # noqa: BLE001 - shown to the user
            self.output.write(lower(getattr(err, "message", None) or err), "error")
        finally:
            runtime.running = False

    def _console(self):
        if self.console_runtime is None:
            self.console_runtime = GublanRuntime(onlog=lambda text: self.output.write(str(text)),
                                                 onerror=lambda text, _f, _l: self.output.write(lower(text), "error"),
                                                 base_dir=self.project_folder() or os.getcwd())
        return self.console_runtime

    # ----- navigation ----------------------------------------------------------------------------------
    def goto_line(self, line, select_line=True):
        doc = self.current
        if doc is None:
            return
        if doc.view == "blocks":
            self.set_view("split")
        doc.editor.goto_line(int(line), select_line=select_line)

    def goto_line_prompt(self):
        if self.current is None:
            return
        self.command_palette(":")

    def open_location(self, line, file=None):
        if file:
            path = self.run_includes.get(file)
            if path:
                doc = self.open_path(path)
                if doc:
                    doc.editor.goto_line(line, select_line=True)
                return
        doc = self.run_doc if self.run_doc in self.docs else self.current
        if doc is not None:
            self.select(doc)
            self.goto_line(line)

    # ----- settings ---------------------------------------------------------------------------------------
    def apply_settings(self, settings, save=True):
        self.settings = settings
        for doc in self.docs:
            doc.editor.settings = settings
            doc.editor.apply_settings(settings)
            if doc.blocks is not None:
                doc.blocks.settings = settings
            self.schedule_analysis(doc, 100)
            doc.analysed_version = -1
        if hasattr(self, "level_button"):
            labels_changed = getattr(self, "_labels", None) != settings.get("toolbar_labels")
            if labels_changed and getattr(self, "_labels", None) is not None:
                self._build_toolbar()
            self._labels = settings.get("toolbar_labels")
            self.level_button.configure_text(settings.get("level", "beginner") + "  ▾")
        self.status_level.configure(text=settings.get("level", "beginner"))
        self.status_indent.configure(text=f"{settings.get('indent', 4)} spaces")
        if save:
            config.save(settings)

    def set_option(self, key, value):
        self.settings[key] = value
        self.apply_settings(self.settings)

    def set_level(self, level):
        config.apply_level(self.settings, level)
        self.apply_settings(self.settings)
        self.flash(f"{level}: {config.LEVEL_ABOUT.get(level, '')}")

    def zoom(self, delta):
        size = int(self.settings.get("font_size", 11))
        size = 11 if delta == 0 else max(7, min(36, size + delta))
        self.set_option("font_size", size)
        self.flash(f"text size {size}")

    def flash(self, text, seconds=6):
        self.status_message.configure(text=lower(text)[:160])
        if self.status_message_job:
            self.root.after_cancel(self.status_message_job)
        self.status_message_job = self.root.after(int(seconds * 1000),
                                                  lambda: self.status_message.configure(text=""))

    def _check_for_updates(self):
        if updater.is_installed_application():
            threading.Thread(target=self._lookup_update, daemon=True).start()

    def _lookup_update(self):
        try:
            release = updater.latest_release(version.VERSION)
        except (OSError, ValueError) as error:
            try:
                self.root.after(0, lambda error=error: self.flash(f"update check failed: {error}"))
            except tk.TclError:
                pass
            return
        if release:
            try:
                self.root.after(0, lambda: self._offer_update(*release))
            except tk.TclError:
                pass

    def _offer_update(self, release_tag, download_url):
        if not confirm(self.root, "update available", f"version {release_tag} is available. download and install it?",
                       yes="install update", no="later"):
            return
        self.flash("downloading update...")
        threading.Thread(target=self._download_update, args=(download_url,), daemon=True).start()

    def _download_update(self, download_url):
        try:
            installer = updater.download_installer(download_url)
        except (OSError, ValueError) as error:
            try:
                self.root.after(0, lambda error=error: message(
                    self.root, "update failed", str(error), kind="error"))
            except tk.TclError:
                pass
            return
        try:
            self.root.after(0, lambda: self._install_update(installer))
        except tk.TclError:
            updater.remove_download(installer)

    def _install_update(self, installer):
        message(self.root, "update ready", "Gublan Studio will close to run the installer.")
        try:
            exited = self.exit(after_exit=lambda: updater.launch_installer(installer))
        except OSError as error:
            message(self.root, "update failed", str(error), kind="error")
            updater.remove_download(installer)
            return
        if not exited:
            updater.remove_download(installer)

    # ----- session -------------------------------------------------------------------------------------
    def _restore(self, paths):
        opened = False
        if self.settings.get("folder") and os.path.isdir(self.settings["folder"]):
            self.side_panels["files"].set_folder(self.settings["folder"])
        else:
            self.settings["folder"] = ""
        if not paths and self.settings.get("restore_session", True):
            session = [path for path in self.settings.get("session", []) if os.path.isfile(path)]
            for path in session:
                if self.open_path(path):
                    opened = True
            active = self.settings.get("session_active", 0)
            if opened and 0 <= active < len(self.docs):
                self.select(self.docs[active])
        for path in paths:
            if self.open_path(path):
                opened = True
        if not self.docs:
            self._show_empty()
        self.set_state("ready", MOSS_LIGHT)

    def exit(self, after_exit=None):
        dirty = [doc for doc in self.docs if doc.dirty]
        if dirty:
            names = ", ".join(doc.name for doc in dirty[:4]) + (" and more" if len(dirty) > 4 else "")
            answer = confirm(self.root, "exit", f"save changes to {names}?", yes="save all", no="cancel",
                             third="don't save")
            if answer is None or answer is False:
                return False
            if answer is True:
                for doc in dirty:
                    if not self.save(doc):
                        return False
        if self.running():
            self.stop()
            self.run_thread.join(timeout=1.5)
        saved = [doc for doc in self.docs if doc.path]
        self.settings["session"] = [doc.path for doc in saved]
        self.settings["session_active"] = saved.index(self.current) if self.current in saved else 0
        try:
            self.settings["window"] = "zoomed" if self.root.state() == "zoomed" else self.root.geometry()
        except tk.TclError:
            pass
        if self.side_visible() and self.side.winfo_width() > 50:
            self.settings["side_width"] = unpx(self.side.winfo_width())
        if self.bottom_visible() and self.bottom.winfo_height() > 60:
            self.settings["bottom_height"] = unpx(self.bottom.winfo_height())
        config.save(self.settings)
        if after_exit:
            after_exit()
        self.root.destroy()
        return True


def main(argv=None):
    from .launch import launch
    return launch(argv)
