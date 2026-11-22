"""square, lowercase dialogs: messages, questions, settings, converter, export, palette and sprites."""

import os
import struct
import subprocess
import threading
import tkinter as tk
import zlib
from tkinter import filedialog, ttk

from gublancore import COMMAND_SPECS

from . import config, exporter
from .editor import line_tokens
from .templates import TEMPLATES
from .theme import (
    BORDER, DIM, EDITOR_BG, ERROR, MOSS, MOSS_DARK, MOSS_LIGHT, MUTED, NUMBER, PANEL, PANEL_ALT, SELECT,
    SELECT_TEXT, SYNTAX, TEXT, BracketButton, ScrollFrame, Segmented, Toggle, flat_entry, icon, icon_font, lower,
    mono_font, plural, popup_window, px, scrollbar, square_window, ui_font,
)


# ----- base -----------------------------------------------------------------------------------
class Dialog(tk.Toplevel):
    def __init__(self, master, title, resizable=False):
        super().__init__(master)
        self.withdraw()
        self.master_window = master.winfo_toplevel()
        self.title(lower(title))
        self.configure(bg=PANEL)
        self.transient(self.master_window)
        self.resizable(resizable, resizable)
        self.result = None
        self.buttons = tk.Frame(self, bg=PANEL)
        self.buttons.pack(side="bottom", fill="x", padx=px(18), pady=(px(4), px(16)))
        self.body = tk.Frame(self, bg=PANEL)
        self.body.pack(fill="both", expand=True, padx=px(18), pady=(px(16), px(8)))
        self.bind("<Escape>", lambda _e: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)

    def add_button(self, text, command, kind="normal", side="right", icon_name=None):
        button = BracketButton(self.buttons, text, command=command, kind=kind, icon_name=icon_name, bg=PANEL)
        button.pack(side=side, padx=(px(8), 0) if side == "right" else (0, px(8)))
        return button

    def show(self, width=None, height=None, modal=True):
        self.update_idletasks()
        width = width or self.winfo_reqwidth()
        height = height or self.winfo_reqheight()
        master = self.master_window
        try:
            x = master.winfo_rootx() + (master.winfo_width() - width) // 2
            y = master.winfo_rooty() + max(0, (master.winfo_height() - height) // 3)
        except tk.TclError:
            x, y = 200, 120
        x = max(0, min(x, self.winfo_screenwidth() - width - 10))
        y = max(0, min(y, self.winfo_screenheight() - height - 60))
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        square_window(self, caption=PANEL)
        self.lift()
        self.focus_force()
        if modal:
            try:
                self.grab_set()
            except tk.TclError:
                pass
            self.wait_window(self)
        return self.result

    def close(self, result=None):
        self.result = result
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def cancel(self):
        self.close(None)


def message(parent, title, text, kind="info", details=None):
    dialog = Dialog(parent, title)
    row = tk.Frame(dialog.body, bg=PANEL)
    row.pack(fill="both", expand=True)
    colors = {"info": MOSS_LIGHT, "warning": NUMBER, "error": ERROR}
    tk.Label(row, text=icon(kind if kind != "info" else "info", "!"), bg=PANEL, fg=colors.get(kind, MOSS_LIGHT),
             font=icon_font(20)).pack(side="left", anchor="n", padx=(0, px(14)))
    tk.Label(row, text=lower(text), bg=PANEL, fg=TEXT, font=ui_font(10), justify="left",
             wraplength=px(440)).pack(side="left", anchor="w", fill="x")
    if details:
        box = tk.Text(dialog.body, height=8, bg=EDITOR_BG, fg=MUTED, relief="flat", font=mono_font(9),
                      highlightthickness=0, wrap="word", padx=px(8), pady=px(6))
        box.insert("1.0", lower(details))
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, pady=(px(12), 0))
    ok = dialog.add_button("ok", lambda: dialog.close(True), kind="accent")
    dialog.bind("<Return>", lambda _e: dialog.close(True))
    ok.focus_set()
    return dialog.show(width=px(560) if details else None)


def confirm(parent, title, text, yes="yes", no="cancel", third=None, danger=False, details=None):
    """True for yes, False for no, the string "third" for the third button, None if closed."""
    dialog = Dialog(parent, title)
    tk.Label(dialog.body, text=lower(text), bg=PANEL, fg=TEXT, font=ui_font(10), justify="left",
             wraplength=px(440)).pack(anchor="w")
    if details:
        box = tk.Text(dialog.body, height=10, bg=EDITOR_BG, fg=MUTED, relief="flat", font=mono_font(9),
                      highlightthickness=0, wrap="word", padx=px(8), pady=px(6))
        box.insert("1.0", lower(details))
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, pady=(px(12), 0))
    dialog.add_button(yes, lambda: dialog.close(True), kind="danger" if danger else "accent")
    if third:
        dialog.add_button(third, lambda: dialog.close("third"))
    dialog.add_button(no, lambda: dialog.close(False), kind="ghost")
    dialog.bind("<Return>", lambda _e: dialog.close(True))
    return dialog.show(width=max(px(560) if details else px(420), dialog.winfo_reqwidth()))


def ask(parent, title, prompt, initial="", mono=False):
    dialog = Dialog(parent, title)
    tk.Label(dialog.body, text=lower(prompt), bg=PANEL, fg=MUTED, font=ui_font(10), anchor="w", justify="left",
             wraplength=px(420)).pack(fill="x", pady=(0, px(8)))
    variable = tk.StringVar(value=initial)
    entry = flat_entry(dialog.body, variable, width=40, mono=mono)
    entry.pack(fill="x")
    entry.select_range(0, "end")
    entry.icursor("end")
    dialog.add_button("ok", lambda: dialog.close(variable.get()), kind="accent")
    dialog.add_button("cancel", dialog.cancel, kind="ghost")
    entry.bind("<Return>", lambda _e: dialog.close(variable.get()))
    dialog.after(50, entry.focus_set)
    return dialog.show(width=px(460))


# ----- settings -----------------------------------------------------------------------------------------
class SettingsDialog(Dialog):
    def __init__(self, master, settings, on_apply, presence=None):
        super().__init__(master, "settings", resizable=True)
        self.settings = settings
        self.on_apply = on_apply
        self.presence = presence
        self.vars = {}
        self.text_vars = {}
        self.text_jobs = {}
        scroll = ScrollFrame(self.body, bg=PANEL)
        scroll.pack(fill="both", expand=True)
        page = scroll.inner

        self._heading(page, "how do you like to code?")
        self.level = tk.StringVar(value=settings.get("level", "beginner"))
        Segmented(page, [("beginner", "beginner"), ("standard", "standard"), ("expert", "expert")], self.level,
                  command=self._choose_level, bg=PANEL).pack(anchor="w", pady=(0, px(4)))
        self.level_about = tk.Label(page, text=config.LEVEL_ABOUT.get(self.level.get(), ""), bg=PANEL, fg=DIM,
                                    font=ui_font(9), justify="left", wraplength=px(520), anchor="w")
        self.level_about.pack(fill="x", pady=(0, px(6)))

        self._heading(page, "editor")
        row = tk.Frame(page, bg=PANEL)
        row.pack(fill="x", pady=px(2))
        tk.Label(row, text="text size", bg=PANEL, fg=TEXT, font=ui_font(10)).pack(side="left")
        self.size = tk.IntVar(value=settings.get("font_size", 11))
        Segmented(row, [(size, str(size)) for size in (9, 10, 11, 12, 14, 16, 18)], self.size,
                  command=lambda v: self._set("font_size", int(v)), bg=PANEL, size=9).pack(side="left", padx=px(12))
        row = tk.Frame(page, bg=PANEL)
        row.pack(fill="x", pady=px(2))
        tk.Label(row, text="indent", bg=PANEL, fg=TEXT, font=ui_font(10)).pack(side="left")
        self.indent = tk.IntVar(value=settings.get("indent", 4))
        Segmented(row, [(2, "2 spaces"), (4, "4 spaces")], self.indent,
                  command=lambda v: self._set("indent", int(v)), bg=PANEL, size=9).pack(side="left", padx=px(12))
        for key, text in (("explain", "explain the line you are on (great for learning)"),
                          ("hint_bar", "show the hint bar under the code"),
                          ("autocomplete", "suggest commands and names while typing"),
                          ("enter_accepts", "enter accepts a suggestion (tab always does)"),
                          ("hover", "show help when the pointer rests on a word"),
                          ("auto_end", "add 'end' after if, loop, while, for and function"),
                          ("auto_pair", "close brackets and quotes for me"),
                          ("auto_indent", "indent new lines inside blocks"),
                          ("line_numbers", "line numbers"),
                          ("highlight_line", "highlight the line with the cursor"),
                          ("wrap", "wrap long lines"),
                          ("block_cursor", "block cursor")):
            self._toggle(page, key, text)

        self._heading(page, "running")
        for key, text in (("check_before_run", "check for problems before running"),
                          ("warnings", "show warnings, not just errors"),
                          ("clear_output", "clear the output each run"),
                          ("show_variables_on_run", "open the variables panel when a program runs"),
                          ("autosave", "save before running"),
                          ("toolbar_labels", "show words on the toolbar buttons")):
            self._toggle(page, key, text)

        self._discord_section(page)

        self._heading(page, "starting up")
        for key, text in (("restore_session", "reopen the programs that were open last time"),
                          ("show_welcome", "show the welcome page when nothing is open"),
                          ("check_updates", "look for a new version of gublan studio when it starts")):
            self._toggle(page, key, text)

        tk.Label(page, text=f"settings are kept in {config.settings_path()}", bg=PANEL, fg=DIM, font=ui_font(8),
                 anchor="w", wraplength=px(520), justify="left").pack(fill="x", pady=(px(14), 0))
        scroll.bind_tree(page)
        self.add_button("done", self.cancel, kind="accent")

    @staticmethod
    def _heading(parent, text):
        tk.Label(parent, text=lower(text), bg=PANEL, fg=MOSS_LIGHT, font=ui_font(11, "bold"), anchor="w").pack(
            fill="x", pady=(px(14), px(6)))

    def _toggle(self, parent, key, text):
        variable = tk.BooleanVar(value=bool(self.settings.get(key)))
        self.vars[key] = variable
        Toggle(parent, text, variable, command=lambda k=key, v=variable: self._set(k, bool(v.get())),
               bg=PANEL).pack(anchor="w", pady=px(3))

    def _set(self, key, value):
        self.settings[key] = value
        self.on_apply(self.settings)
        self._show_discord()

    # ----- discord -----------------------------------------------------------------------------------------
    DISCORD_TEXTS = (
        ("discord_details", "first line"),
        ("discord_state", "second line"),
        ("discord_idle", "with nothing open"),
        ("discord_image", "picture"),
        ("discord_image_text", "picture hover text"),
        ("discord_small_image", "small picture"),
        ("discord_button_label", "button label"),
        ("discord_button_url", "button link"),
        ("discord_app_id", "application id"),
    )

    def _discord_section(self, page):
        from .presence import PLACEHOLDERS
        self._heading(page, "discord")
        tk.Label(page, text="while the discord app is open, your discord profile can show what you are making.",
                 bg=PANEL, fg=DIM, font=ui_font(9), anchor="w", justify="left", wraplength=px(520)).pack(
            fill="x", pady=(0, px(4)))
        for key, text in (("discord_presence", "show what i'm doing on my discord profile"),
                          ("discord_show_file", "show the file name (otherwise it says 'a program')"),
                          ("discord_show_time", "show how long i've been at it"),
                          ("discord_programs", "let my programs change it with presence lines")):
            self._toggle(page, key, text)
        row = tk.Frame(page, bg=PANEL)
        row.pack(fill="x", pady=(px(6), px(4)))
        tk.Label(row, text="shows as", bg=PANEL, fg=TEXT, font=ui_font(10)).pack(side="left")
        self.discord_kind = tk.StringVar(value=self.settings.get("discord_activity", "playing"))
        Segmented(row, [(kind, kind) for kind in ("playing", "watching", "listening", "competing")],
                  self.discord_kind, command=lambda v: self._set("discord_activity", v), bg=PANEL,
                  size=9).pack(side="left", padx=px(12))
        for key, text in self.DISCORD_TEXTS:
            self._text_setting(page, key, text)
        words = " ".join("{" + name + "}" for name in PLACEHOLDERS)
        tk.Label(page, text=f"words in braces are filled in: {words}", bg=PANEL, fg=DIM, font=ui_font(8),
                 anchor="w", justify="left", wraplength=px(520)).pack(fill="x", pady=(px(4), 0))
        tk.Label(page, text="a picture is an https address, or the name of a picture uploaded to your own discord "
                            "application (then put its id in application id). an empty picture shows the gublan "
                            "logo. buttons show to other people, not to you.",
                 bg=PANEL, fg=DIM, font=ui_font(8), anchor="w", justify="left", wraplength=px(520)).pack(
            fill="x", pady=(px(2), 0))
        self.discord_preview = tk.Label(page, text="", bg=PANEL, fg=TEXT, font=ui_font(9), anchor="w",
                                        justify="left", wraplength=px(520))
        self.discord_preview.pack(fill="x", pady=(px(8), 0))
        self.discord_status = tk.Label(page, text="", bg=PANEL, fg=DIM, font=ui_font(9), anchor="w",
                                       justify="left", wraplength=px(520))
        self.discord_status.pack(fill="x")
        BracketButton(page, "put the discord settings back", command=self._reset_discord, size=9,
                      bg=PANEL).pack(anchor="w", pady=(px(6), 0))
        self._watch_discord()

    def _text_setting(self, parent, key, text):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=px(2))
        tk.Label(row, text=text, bg=PANEL, fg=TEXT, font=ui_font(10), width=16, anchor="w").pack(side="left")
        variable = tk.StringVar(value=str(self.settings.get(key) or ""))
        self.text_vars[key] = variable
        entry = flat_entry(row, variable, width=36, mono=key in ("discord_app_id", "discord_button_url"))
        entry.pack(side="left", fill="x", expand=True)
        variable.trace_add("write", lambda *_a, k=key: self._text_changed(k))

    def _text_changed(self, key):
        job = self.text_jobs.pop(key, None)
        if job is not None:
            self.after_cancel(job)
        self.text_jobs[key] = self.after(500, lambda: self._text_done(key))

    def _text_done(self, key):
        self.text_jobs.pop(key, None)
        value = self.text_vars[key].get().strip()
        if value != self.settings.get(key):
            self._set(key, value)

    def _reset_discord(self):
        for key, value in config.DEFAULTS.items():
            if not key.startswith("discord_"):
                continue
            self.settings[key] = value
            if key in self.vars:
                self.vars[key].set(bool(value))
        for key, variable in self.text_vars.items():
            variable.set(str(self.settings.get(key) or ""))
        for job in list(self.text_jobs.values()):
            self.after_cancel(job)
        self.text_jobs.clear()
        self.discord_kind.set(self.settings.get("discord_activity", "playing"))
        self.on_apply(self.settings)
        self._show_discord()

    def _show_discord(self):
        if self.presence is None or not hasattr(self, "discord_status"):
            return
        try:
            on = self.settings.get("discord_presence", True)
            self.discord_preview.configure(text=f"preview: {self.presence.preview()}" if on else "")
            state, _text = self.presence.status()
            color = {"connected": MOSS_LIGHT, "error": ERROR}.get(state, DIM)
            self.discord_status.configure(text=f"status: {self.presence.status_text()}", fg=color)
        except tk.TclError:
            pass

    def _watch_discord(self):
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self._show_discord()
        self.after(1000, self._watch_discord)

    def _choose_level(self, level):
        config.apply_level(self.settings, level)
        self.level_about.configure(text=config.LEVEL_ABOUT.get(level, ""))
        for key, variable in self.vars.items():
            variable.set(bool(self.settings.get(key)))
        self.on_apply(self.settings)


# ----- converter ------------------------------------------------------------------------------------------
def highlight_into(widget, source):
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", source)
    for tag, color in SYNTAX.items():
        widget.tag_configure(tag, foreground=color)
    widget.tag_configure("todo", foreground=NUMBER)
    for number, line in enumerate(source.split("\n"), start=1):
        if number > 20000:
            break
        if line.lstrip().startswith("// todo"):
            widget.tag_add("todo", f"{number}.0", f"{number}.end")
            continue
        for tag, start, end in line_tokens(line):
            widget.tag_add(tag, f"{number}.{start}", f"{number}.{end}")
    widget.configure(state="disabled")


class ConvertDialog(Dialog):
    """paste or open python, javascript or lua and get gublan back."""

    def __init__(self, master, on_open, initial_path=None):
        super().__init__(master, "convert code to gublan", resizable=True)
        self.on_open = on_open
        self.result_text = ""
        self.filename = None
        self.working = False
        top = tk.Frame(self.body, bg=PANEL)
        top.pack(fill="x", pady=(0, px(10)))
        tk.Label(top, text="from", bg=PANEL, fg=MUTED, font=ui_font(10)).pack(side="left")
        self.language = tk.StringVar(value="auto")
        Segmented(top, [("auto", "find out"), ("python", "python"), ("javascript", "javascript"), ("lua", "lua")],
                  self.language, bg=PANEL, size=9).pack(side="left", padx=px(10))
        BracketButton(top, "open a file", icon_name="open", size=9, command=self.open_file, bg=PANEL).pack(
            side="left", padx=(px(6), 0))
        self.convert_button = BracketButton(top, "convert", icon_name="convert", kind="accent", size=9,
                                            command=self.convert, bg=PANEL)
        self.convert_button.pack(side="right")
        self.status = tk.Label(top, text="", bg=PANEL, fg=DIM, font=ui_font(9))
        self.status.pack(side="right", padx=px(10))

        panes = tk.PanedWindow(self.body, orient="horizontal", bg=BORDER, sashwidth=px(4), bd=0, relief="flat",
                               showhandle=False)
        panes.pack(fill="both", expand=True)
        left = tk.Frame(panes, bg=PANEL)
        right = tk.Frame(panes, bg=PANEL)
        panes.add(left, stretch="always", minsize=px(280))
        panes.add(right, stretch="always", minsize=px(280))
        tk.Label(left, text="your code (paste it here)", bg=PANEL, fg=MUTED, font=ui_font(9), anchor="w").pack(
            fill="x", pady=(0, px(4)))
        self.source = self._code_box(left, editable=True)
        tk.Label(right, text="gublan", bg=PANEL, fg=MUTED, font=ui_font(9), anchor="w").pack(fill="x",
                                                                                             pady=(0, px(4)))
        self.output = self._code_box(right, editable=False)
        self.notes = tk.Label(self.body, text="", bg=PANEL, fg=MUTED, font=ui_font(9), justify="left", anchor="w",
                              wraplength=px(1000))
        self.notes.pack(fill="x", pady=(px(8), 0))
        self.add_button("open as a new program", self.open_result, kind="accent", icon_name="new")
        self.add_button("copy", self.copy_result, icon_name="copy")
        self.add_button("close", self.cancel, kind="ghost")
        self.source.bind("<Control-Return>", lambda _e: (self.convert(), "break")[1])
        tk.Label(self.buttons, text="ctrl+enter converts. lines that can't be converted become // todo notes.",
                 bg=PANEL, fg=DIM, font=ui_font(8)).pack(side="left")
        if initial_path:
            self.after(50, lambda: self.load_file(initial_path))

    def _code_box(self, parent, editable):
        frame = tk.Frame(parent, bg=EDITOR_BG, highlightthickness=1, highlightbackground=BORDER)
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, bg=EDITOR_BG, fg=TEXT, insertbackground=MOSS_LIGHT, relief="flat", borderwidth=0,
                       highlightthickness=0, font=mono_font(10), wrap="none", padx=px(8), pady=px(6), undo=editable,
                       selectbackground=SELECT, inactiveselectbackground=SELECT)
        bar = scrollbar(frame, "vertical", text.yview)
        hbar = scrollbar(frame, "horizontal", text.xview)
        text.configure(yscrollcommand=bar.set, xscrollcommand=hbar.set)
        hbar.pack(side="bottom", fill="x")
        bar.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        if not editable:
            text.configure(state="disabled")
        return text

    def open_file(self):
        path = filedialog.askopenfilename(parent=self, title="open code to convert", filetypes=[
            ("code", "*.py *.pyw *.js *.mjs *.lua"), ("python", "*.py *.pyw"), ("javascript", "*.js *.mjs"),
            ("lua", "*.lua"), ("all files", "*.*")])
        if path:
            self.load_file(path)

    def load_file(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                content = handle.read()
        except OSError as err:
            message(self, "convert", f"could not open the file: {str(err).lower()}", "error")
            return
        self.filename = path
        self.source.delete("1.0", "end")
        self.source.insert("1.0", content)
        self.status.configure(text=os.path.basename(path).lower())
        self.convert()

    def convert(self):
        if self.working:
            return
        code = self.source.get("1.0", "end-1c")
        if not code.strip():
            self.status.configure(text="paste some code first", fg=NUMBER)
            return
        language = None if self.language.get() == "auto" else self.language.get()
        self.working = True
        self.convert_button.set_enabled(False)
        self.status.configure(text="converting...", fg=DIM)

        def work():
            try:
                import gublanconvert
                result = gublanconvert.convert(code, language, filename=self.filename)
                error = None
            except Exception as err:  # noqa: BLE001 - shown to the user
                result, error = None, f"{type(err).__name__}: {err}"
            try:
                self.after(0, self._finished, result, error)
            except (tk.TclError, RuntimeError):
                pass

        threading.Thread(target=work, daemon=True).start()

    def _finished(self, result, error):
        self.working = False
        self.convert_button.set_enabled(True)
        if error:
            self.status.configure(text="could not convert", fg=ERROR)
            self.notes.configure(text=lower(error), fg=ERROR)
            return
        self.result_text = result.text
        highlight_into(self.output, result.text)
        library = f" with {result.library}" if result.library and result.library != "none" else ""
        self.status.configure(text=f"{result.language}{library}: {result.source_lines} lines in, "
                                   f"{result.output_lines} out", fg=MOSS_LIGHT)
        parts = []
        if result.todos:
            parts.append(f"{plural(result.todos, 'part')} {'needs' if result.todos == 1 else 'need'} a look (marked // todo).")
        parts.extend(lower(note) for note in result.notes[:6])
        self.notes.configure(text="  ".join(parts) or "everything converted.", fg=NUMBER if result.todos else MUTED)

    def copy_result(self):
        if self.result_text:
            self.clipboard_clear()
            self.clipboard_append(self.result_text)
            self.status.configure(text="copied", fg=MOSS_LIGHT)

    def open_result(self):
        if not self.result_text:
            self.convert()
            return
        name = os.path.splitext(os.path.basename(self.filename))[0] if self.filename else "converted"
        self.on_open(self.result_text, name)
        self.close(True)


# ----- export -------------------------------------------------------------------------------------------------
class ExportDialog(Dialog):
    """check a program's media, choose options and build a .exe."""

    def __init__(self, app, source, base_dir, name):
        super().__init__(app.root, "export program", resizable=True)
        self.app = app
        self.source = source
        self.base_dir = base_dir
        self.python = exporter.find_python()
        self.building = False
        self.plan = None
        self.output_path = None
        settings = app.settings
        grid = tk.Frame(self.body, bg=PANEL)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        tk.Label(grid, text="name", bg=PANEL, fg=MUTED, font=ui_font(10)).grid(row=0, column=0, sticky="w")
        self.name = tk.StringVar(value=exporter.safe_name(name))
        flat_entry(grid, self.name, width=30).grid(row=0, column=1, sticky="ew", padx=px(10), pady=px(3))
        tk.Label(grid, text="save in", bg=PANEL, fg=MUTED, font=ui_font(10)).grid(row=1, column=0, sticky="w")
        folder = settings.get("export_folder") or os.path.join(base_dir, "export")
        self.folder = tk.StringVar(value=folder)
        folder_entry = flat_entry(grid, self.folder, width=30)
        folder_entry.grid(row=1, column=1, sticky="ew", padx=px(10), pady=px(3))
        # long folder paths show their end, which is the part people recognise
        self.folder.trace_add("write", lambda *_: self.after_idle(folder_entry.xview_moveto, 1))
        self.after(50, folder_entry.xview_moveto, 1)
        BracketButton(grid, "choose", size=9, command=self._choose_folder, bg=PANEL).grid(row=1, column=2)
        tk.Label(grid, text="icon", bg=PANEL, fg=MUTED, font=ui_font(10)).grid(row=2, column=0, sticky="w")
        self.icon_path = tk.StringVar(value="")
        flat_entry(grid, self.icon_path, width=30).grid(row=2, column=1, sticky="ew", padx=px(10), pady=px(3))
        BracketButton(grid, "choose", size=9, command=self._choose_icon, bg=PANEL).grid(row=2, column=2)

        options = tk.Frame(self.body, bg=PANEL)
        options.pack(fill="x", pady=(px(10), px(4)))
        self.onefile = tk.StringVar(value="one" if settings.get("export_onefile", True) else "folder")
        tk.Label(options, text="make", bg=PANEL, fg=MUTED, font=ui_font(10)).pack(side="left")
        Segmented(options, [("one", "one .exe file"), ("folder", "a folder (starts faster)")], self.onefile,
                  bg=PANEL, size=9).pack(side="left", padx=(px(10), px(20)))
        tk.Label(options, text="console", bg=PANEL, fg=MUTED, font=ui_font(10)).pack(side="left")
        self.console = tk.StringVar(value=settings.get("export_console", "auto"))
        Segmented(options, [("auto", "auto"), ("on", "on"), ("off", "off")], self.console, bg=PANEL,
                  size=9).pack(side="left", padx=px(10))
        self.include_folder = tk.BooleanVar(value=settings.get("export_include_folder", True))
        Toggle(self.body, "include the whole assets folder (for files picked while the game runs)",
               self.include_folder, command=self.refresh_plan, bg=PANEL).pack(anchor="w", pady=px(4))

        tk.Label(self.body, text="media in your program", bg=PANEL, fg=MOSS_LIGHT, font=ui_font(10, "bold"),
                 anchor="w").pack(fill="x", pady=(px(10), px(4)))
        frame = tk.Frame(self.body, bg=PANEL)
        frame.pack(fill="both", expand=True)
        self.assets = ttk.Treeview(frame, columns=("source", "note"), style="Flat.Treeview", height=7)
        self.assets.heading("#0", text="in the game as", anchor="w")
        self.assets.heading("source", text="from", anchor="w")
        self.assets.heading("note", text="", anchor="w")
        self.assets.column("#0", width=px(220))
        self.assets.column("source", width=px(330))
        self.assets.column("note", width=px(120), stretch=False)
        self.assets.tag_configure("missing", foreground=ERROR)
        self.assets.tag_configure("external", foreground=NUMBER)
        bar = scrollbar(frame, "vertical", self.assets.yview)
        self.assets.configure(yscrollcommand=bar.set)
        self.assets.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.plan_note = tk.Label(self.body, text="", bg=PANEL, fg=DIM, font=ui_font(9), anchor="w",
                                  justify="left", wraplength=px(700))
        self.plan_note.pack(fill="x", pady=(px(4), 0))

        status_row = tk.Frame(self.body, bg=PANEL)
        status_row.pack(fill="x", pady=(px(10), 0))
        self.tool_status = tk.Label(status_row, text="checking pyinstaller...", bg=PANEL, fg=DIM, font=ui_font(9),
                                    anchor="w", justify="left", wraplength=px(560))
        self.tool_status.pack(side="left")
        self.install_button = BracketButton(status_row, "install pyinstaller", size=9, command=self.install,
                                            bg=PANEL)
        self.progress = ttk.Progressbar(self.body, style="Flat.Horizontal.TProgressbar", mode="indeterminate")
        self.log = tk.Label(self.body, text="", bg=PANEL, fg=MUTED, font=ui_font(9), anchor="w", justify="left",
                            wraplength=px(700))
        self.log.pack(fill="x", pady=(px(4), 0))
        self.build_button = self.add_button("build", self.build, kind="accent", icon_name="export")
        self.open_button = self.add_button("open folder", self.open_folder, icon_name="folder")
        self.open_button.set_enabled(False)
        self.add_button("close", self.cancel, kind="ghost")
        self.refresh_plan()
        threading.Thread(target=self._check_tool, daemon=True).start()

    def _choose_folder(self):
        folder = filedialog.askdirectory(parent=self, title="where should the program go?",
                                         initialdir=self.folder.get() or self.base_dir)
        if folder:
            self.folder.set(folder)

    def _choose_icon(self):
        path = filedialog.askopenfilename(parent=self, title="choose an icon", filetypes=[
            ("icons", "*.ico"), ("pictures", "*.png"), ("all files", "*.*")])
        if path:
            self.icon_path.set(path)

    def refresh_plan(self):
        self.assets.delete(*self.assets.get_children())
        try:
            expanded = self.app.runtime._expand_includes(self.source, self.base_dir)
            self.plan = exporter.plan_export(expanded, self.base_dir, include_folder=self.include_folder.get())
        except ValueError as err:
            self.plan = None
            self.plan_note.configure(text=f"include error: {str(err).lower()}", fg=ERROR)
            return
        plan = self.plan
        for line, path in plan.missing:
            self.assets.insert("", "end", text=path, values=("not found", f"line {line}"), tags=("missing",))
        for bundle, asset in sorted(plan.assets.items()):
            note = "outside folder" if asset.external else (f"line {asset.line}" if asset.line else "assets folder")
            self.assets.insert("", "end", text=bundle, values=(self._short_path(asset.source_path), note),
                               tags=("external",) if asset.external else ())
        notes = []
        if plan.missing:
            notes.append(f"{plural(len(plan.missing), 'file')} can't be found. fix those lines before building.")
        if not plan.assets and not plan.missing:
            notes.append("no pictures or sounds are used, so only the program goes in.")
        notes.extend(plan.notes)
        notes.append("text programs get a console window." if plan.console else "games open just their window.")
        self.plan_note.configure(text="  ".join(lower(note) for note in notes), fg=ERROR if plan.missing else DIM)

    def _short_path(self, path):
        """show media paths relative to the program when they live beside it, otherwise just the end."""
        try:
            relative = os.path.relpath(path, self.base_dir)
        except ValueError:
            relative = path
        if not relative.startswith(".."):
            return relative.replace(os.sep, "/")
        parts = os.path.normpath(path).split(os.sep)
        return path if len(parts) <= 3 else "..." + os.sep + os.sep.join(parts[-3:])

    def _check_tool(self):
        broken = False
        if not self.python:
            text, ok = "python wasn't found. building programs needs python from python.org.", False
        else:
            version, problem = exporter.pyinstaller_status(self.python)
            if version:
                text, ok = f"pyinstaller {version} is ready", True
            elif problem:
                problem = problem.split(": ", 1)[-1] if "Error: " in problem else problem
                text, ok, broken = f"pyinstaller won't start: {problem[:90]}", False, True
            else:
                text, ok = "pyinstaller is not installed. it builds the .exe.", False
        try:
            self.after(0, self._tool_checked, text, ok, broken)
        except (tk.TclError, RuntimeError):
            pass

    def _tool_checked(self, text, ok, broken=False):
        self.repair = broken
        self.tool_status.configure(text=lower(text), fg=MOSS_LIGHT if ok else NUMBER)
        if not ok and self.python:
            self.install_button.configure_text("repair pyinstaller" if broken else "install pyinstaller")
            self.install_button.pack(side="left", padx=px(10))
        else:
            self.install_button.pack_forget()

    def install(self):
        self.install_button.set_enabled(False)
        repair = getattr(self, "repair", False)
        self.tool_status.configure(text="repairing pyinstaller..." if repair else "installing pyinstaller...", fg=DIM)
        self.progress.pack(fill="x", pady=(px(6), 0), before=self.log)
        self.progress.start(12)
        command = [self.python, "-m", "pip", "install", "--upgrade", "pyinstaller"]
        if repair:
            command.insert(5, "--force-reinstall")

        def work():
            try:
                result = subprocess.run(command,
                                        capture_output=True, text=True,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                output = (result.stdout + result.stderr)[-600:]
                failed = result.returncode != 0
            except OSError as err:
                output, failed = str(err), True
            try:
                self.after(0, self._installed, output, failed)
            except (tk.TclError, RuntimeError):
                pass

        threading.Thread(target=work, daemon=True).start()

    def _installed(self, output, failed):
        self.progress.stop()
        self.progress.pack_forget()
        self.install_button.set_enabled(True)
        if failed:
            self.log.configure(text=lower(output), fg=ERROR)
        threading.Thread(target=self._check_tool, daemon=True).start()

    def build(self):
        if self.building:
            return
        if self.plan is None:
            message(self, "export", "fix the include error first", "error")
            return
        if not self.python:
            message(self, "export", "python is needed to build programs. install it from python.org.", "error")
            return
        folder = self.folder.get().strip() or os.path.join(self.base_dir, "export")
        name = exporter.safe_name(self.name.get())
        output = os.path.join(folder, name + ".exe")
        console = {"auto": None, "on": True, "off": False}[self.console.get()]
        settings = self.app.settings
        settings["export_onefile"] = self.onefile.get() == "one"
        settings["export_console"] = self.console.get()
        settings["export_include_folder"] = bool(self.include_folder.get())
        settings["export_folder"] = self.folder.get().strip() if self.folder.get().strip() != os.path.join(
            self.base_dir, "export") else ""
        self.building = True
        self.build_button.set_enabled(False)
        self.open_button.set_enabled(False)
        self.progress.pack(fill="x", pady=(px(6), 0), before=self.log)
        self.progress.start(12)
        self.log.configure(text="starting...", fg=MUTED)
        options = {"include_folder": bool(self.include_folder.get()), "onefile": self.onefile.get() == "one",
                   "console": console, "icon_path": self.icon_path.get().strip() or None}
        self.app.export_dialog = self
        threading.Thread(target=self.app.buildscript_exe, args=(self.source, output, self.python, self.base_dir),
                         kwargs={"progress": self.report, "options": options}, daemon=True).start()

    def report(self, status):
        try:
            self.after(0, lambda: self.log.configure(text=lower(status), fg=MUTED))
        except (tk.TclError, RuntimeError):
            pass

    def finished(self, output, error):
        self.building = False
        self.progress.stop()
        self.progress.pack_forget()
        self.build_button.set_enabled(True)
        if error:
            self.log.configure(text=lower(error)[-1500:], fg=ERROR)
            return
        self.output_path = output
        self.open_button.set_enabled(True)
        self.log.configure(text=f"done! {output}", fg=MOSS_LIGHT)

    def open_folder(self):
        if self.output_path:
            from .panels import reveal
            reveal(self.output_path)


# ----- command palette ---------------------------------------------------------------------------------------
def _score(query, text):
    """a small fuzzy match: every letter of the query in order, rewarding starts of words."""
    if not query:
        return 1
    text = text.lower()
    if query in text:
        return 100 - text.index(query) + (40 if text.startswith(query) else 0)
    position = 0
    score = 0
    for char in query:
        found = text.find(char, position)
        if found < 0:
            return 0
        score += 3 if found == 0 or text[found - 1] in " _-:" else 1
        position = found + 1
    return score


class CommandPalette:
    """ctrl+shift+p: every action, ':' to go to a line, '@' to jump to a function or shape."""

    def __init__(self, app, actions, symbols=None, initial=""):
        self.app = app
        self.actions = actions
        self.symbols = symbols or {}
        self.window = popup_window(app.root)
        frame = tk.Frame(self.window, bg=PANEL_ALT, highlightthickness=1, highlightbackground=MOSS)
        frame.pack(fill="both", expand=True)
        self.variable = tk.StringVar(value=initial)
        row = tk.Frame(frame, bg=PANEL_ALT)
        row.pack(fill="x")
        tk.Label(row, text=icon("search"), bg=PANEL_ALT, fg=MOSS_LIGHT, font=icon_font(11)).pack(
            side="left", padx=(px(12), 0))
        self.entry = tk.Entry(row, textvariable=self.variable, bg=PANEL_ALT, fg=TEXT, insertbackground=TEXT,
                              relief="flat", highlightthickness=0, font=ui_font(11), bd=px(8))
        self.entry.pack(side="left", fill="x", expand=True)
        self.placeholder = tk.Label(row, text="search for an action, or :line, @name", bg=PANEL_ALT, fg=DIM,
                                    font=ui_font(11))
        self.placeholder.bind("<Button-1>", lambda _e: self.entry.focus_set())
        self.variable.trace_add("write", lambda *_: self._placeholder())
        self._placeholder()
        tk.Frame(frame, bg=BORDER, height=1).pack(fill="x")
        self.list = tk.Listbox(frame, bg=PANEL_ALT, fg=TEXT, selectbackground=SELECT, selectforeground=SELECT_TEXT,
                               relief="flat", highlightthickness=0, bd=0, font=ui_font(10), activestyle="none",
                               height=12)
        self.list.pack(fill="both", expand=True, padx=px(4), pady=px(4))
        self.hint = tk.Label(frame, text="type to search   :  go to line   @  go to a name   esc  close",
                             bg=PANEL_ALT, fg=DIM, font=ui_font(8), anchor="w")
        self.hint.pack(fill="x", padx=px(8), pady=(0, px(6)))
        self.items = []
        self.variable.trace_add("write", lambda *_: self.refresh())
        self.entry.bind("<Down>", lambda _e: self.move(1))
        self.entry.bind("<Up>", lambda _e: self.move(-1))
        self.entry.bind("<Return>", lambda _e: self.run())
        self.entry.bind("<Escape>", lambda _e: self.close())
        self.entry.bind("<FocusOut>", lambda _e: self.window.after(120, self._maybe_close))
        self.list.bind("<ButtonRelease-1>", lambda _e: self.run())
        root = app.root
        width = px(620)
        x = root.winfo_rootx() + (root.winfo_width() - width) // 2
        y = root.winfo_rooty() + px(60)
        self.window.geometry(f"{width}x{px(360)}+{x}+{y}")
        self.window.deiconify()
        self.window.lift()
        self.entry.focus_force()
        self.entry.icursor("end")
        self.refresh()

    def _placeholder(self):
        if self.variable.get():
            self.placeholder.place_forget()
        else:
            self.placeholder.place(in_=self.entry, x=px(9), rely=0.5, anchor="w")

    def _maybe_close(self):
        try:
            focused = self.window.focus_get()
        except (tk.TclError, KeyError):
            focused = None
        if focused is None or not str(focused).startswith(str(self.window)):
            self.close()

    def refresh(self):
        query = self.variable.get().strip().lower()
        self.list.delete(0, "end")
        self.items = []
        if query.startswith(":"):
            number = query[1:].strip()
            if number.isdigit():
                self.items.append((f"go to line {number}", lambda n=int(number): self.app.goto_line(n)))
            else:
                self.items.append(("type a line number", None))
        elif query.startswith("@"):
            name = query[1:].strip()
            for kind in ("functions", "objects", "variables"):
                for symbol, info in self.symbols.get(kind, {}).items():
                    line = info["line"] if isinstance(info, dict) else info
                    if _score(name, symbol):
                        label_text = f"{symbol}    {kind[:-1] if kind != 'objects' else 'shape'}, line {line}"
                        self.items.append((label_text, lambda n=line: self.app.goto_line(n)))
        else:
            scored = []
            for label_text, shortcut, command in self.actions:
                score = _score(query, label_text)
                if score:
                    scored.append((score, label_text, shortcut, command))
            if query:
                for name, spec in COMMAND_SPECS.items():
                    score = _score(query, "insert " + name)
                    if score and query in name:
                        scored.append((score - 5, f"insert {name}: {spec[3]}", "",
                                       lambda example=spec[4]: self.app.insert_code(example)))
            scored.sort(key=lambda item: -item[0])
            for _score_value, label_text, shortcut, command in scored[:60]:
                self.items.append((f"{lower(label_text)}{'    ' + shortcut if shortcut else ''}", command))
        for label_text, _command in self.items:
            self.list.insert("end", "  " + label_text)
        if self.items:
            self.list.selection_set(0)

    def move(self, step):
        if not self.items:
            return "break"
        current = self.list.curselection()
        index = (current[0] if current else 0) + step
        index = max(0, min(len(self.items) - 1, index))
        self.list.selection_clear(0, "end")
        self.list.selection_set(index)
        self.list.see(index)
        return "break"

    def run(self):
        current = self.list.curselection()
        if not current or not self.items:
            return
        command = self.items[current[0]][1]
        self.close()
        if command:
            self.app.root.after(10, command)

    def close(self):
        try:
            self.window.destroy()
        except tk.TclError:
            pass


# ----- sprite painter -------------------------------------------------------------------------------------------
def write_png(path, width, height, pixels):
    """save rgba pixels (a list of rows of (r, g, b, a)) as a png, no extra libraries needed."""
    raw = b"".join(b"\x00" + bytes(channel for pixel in row for channel in pixel) for row in pixels)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    with open(path, "wb") as handle:
        handle.write(data)


SPRITE_COLORS = [
    (0, 0, 0), (34, 32, 52), (69, 40, 60), (102, 57, 49), (143, 86, 59), (223, 113, 38), (217, 160, 102),
    (238, 195, 154), (251, 242, 54), (153, 229, 80), (106, 190, 48), (55, 148, 110), (75, 105, 47), (82, 75, 36),
    (50, 60, 57), (63, 63, 116), (48, 96, 130), (91, 110, 225), (99, 155, 255), (95, 205, 228), (203, 219, 252),
    (255, 255, 255), (155, 173, 183), (132, 126, 135), (105, 106, 106), (89, 86, 82), (118, 66, 138),
    (172, 50, 50), (217, 87, 99), (215, 123, 186), (143, 151, 74), (138, 111, 48),
]


class SpriteEditor(Dialog):
    """paint small pixel pictures for games and save them as png files in the assets folder."""

    def __init__(self, master, folder, on_saved, path=None):
        super().__init__(master, "sprite painter", resizable=True)
        self.folder = folder
        self.on_saved = on_saved
        self.path = path
        self.size = 16
        self.pixels = None
        self.color = (106, 190, 48, 255)
        self.tool = tk.StringVar(value="pencil")
        self.mirror = tk.BooleanVar(value=False)
        self.grid_on = tk.BooleanVar(value=True)
        self.undo_stack = []
        self.preview = None
        top = tk.Frame(self.body, bg=PANEL)
        top.pack(fill="x", pady=(0, px(10)))
        tk.Label(top, text="name", bg=PANEL, fg=MUTED, font=ui_font(10)).pack(side="left")
        self.name = tk.StringVar(value=os.path.splitext(os.path.basename(path))[0] if path else "sprite")
        flat_entry(top, self.name, width=16).pack(side="left", padx=(px(8), px(16)))
        tk.Label(top, text="size", bg=PANEL, fg=MUTED, font=ui_font(10)).pack(side="left")
        self.size_var = tk.IntVar(value=16)
        Segmented(top, [(n, str(n)) for n in (8, 16, 24, 32, 48, 64)], self.size_var, command=self.resize,
                  bg=PANEL, size=9).pack(side="left", padx=px(8))
        main = tk.Frame(self.body, bg=PANEL)
        main.pack(fill="both", expand=True)
        tools = tk.Frame(main, bg=PANEL)
        tools.pack(side="left", fill="y", padx=(0, px(12)))
        Segmented(tools, [("pencil", "pencil"), ("eraser", "eraser")], self.tool, bg=PANEL, size=9).pack(
            anchor="w")
        Segmented(tools, [("fill", "fill"), ("picker", "picker")], self.tool, bg=PANEL, size=9).pack(
            anchor="w", pady=px(4))
        Toggle(tools, "mirror left and right", self.mirror, bg=PANEL).pack(anchor="w", pady=(px(8), px(2)))
        Toggle(tools, "grid", self.grid_on, command=self.draw, bg=PANEL).pack(anchor="w", pady=px(2))
        tk.Label(tools, text="colours", bg=PANEL, fg=MUTED, font=ui_font(9), anchor="w").pack(fill="x",
                                                                                              pady=(px(12), px(4)))
        swatches = tk.Frame(tools, bg=PANEL)
        swatches.pack(anchor="w")
        for number, rgb in enumerate(SPRITE_COLORS):
            hex_color = "#%02x%02x%02x" % rgb
            swatch = tk.Frame(swatches, bg=hex_color, width=px(20), height=px(20), cursor="hand2",
                              highlightthickness=1, highlightbackground=BORDER)
            swatch.grid(row=number // 4, column=number % 4, padx=px(1), pady=px(1))
            swatch.bind("<Button-1>", lambda _e, c=rgb: self.choose(c + (255,)))
        self.current = tk.Frame(tools, bg="#6abe30", width=px(86), height=px(22), highlightthickness=1,
                                highlightbackground=MOSS_LIGHT)
        self.current.pack(anchor="w", pady=(px(8), px(4)))
        BracketButton(tools, "other colour", size=9, command=self.custom_color, bg=PANEL).pack(anchor="w")
        tk.Label(tools, text="left click paints\nright click erases\nctrl+z undoes", bg=PANEL, fg=DIM,
                 font=ui_font(8), justify="left").pack(anchor="w", pady=(px(14), 0))
        self.canvas = tk.Canvas(main, bg=EDITOR_BG, highlightthickness=0, width=px(448), height=px(448),
                                cursor="crosshair")
        self.canvas.pack(side="left", fill="both", expand=True)
        side = tk.Frame(main, bg=PANEL)
        side.pack(side="left", fill="y", padx=(px(12), 0))
        tk.Label(side, text="preview", bg=PANEL, fg=MUTED, font=ui_font(9)).pack(anchor="w")
        self.preview_label = tk.Label(side, bg="#202020")
        self.preview_label.pack(anchor="w", pady=px(4))
        self.preview_big = tk.Label(side, bg="#202020")
        self.preview_big.pack(anchor="w", pady=px(4))
        BracketButton(side, "clear", size=9, command=self.clear, kind="ghost", bg=PANEL).pack(anchor="w",
                                                                                              pady=(px(10), 0))
        BracketButton(side, "flip", size=9, command=self.flip, kind="ghost", bg=PANEL).pack(anchor="w",
                                                                                            pady=px(2))
        self.canvas.bind("<ButtonPress-1>", lambda e: self.stroke(e, True, start=True))
        self.canvas.bind("<B1-Motion>", lambda e: self.stroke(e, True))
        self.canvas.bind("<ButtonPress-3>", lambda e: self.stroke(e, False, start=True))
        self.canvas.bind("<B3-Motion>", lambda e: self.stroke(e, False))
        self.canvas.bind("<Configure>", lambda _e: self.draw())
        self.bind("<Control-z>", lambda _e: self.undo())
        self.add_button("save", self.save, kind="accent", icon_name="save")
        self.add_button("cancel", self.cancel, kind="ghost")
        self.status = tk.Label(self.buttons, text="", bg=PANEL, fg=DIM, font=ui_font(9))
        self.status.pack(side="left")
        if path and os.path.isfile(path):
            self.load(path)
        else:
            self.resize(16)

    def resize(self, size):
        size = int(size)
        old = self.pixels
        self.size = size
        self.size_var.set(size)
        self.pixels = [[(0, 0, 0, 0)] * size for _ in range(size)]
        if old:
            for y in range(min(size, len(old))):
                for x in range(min(size, len(old))):
                    self.pixels[y][x] = old[y][x]
        self.draw()

    def load(self, path):
        try:
            image = tk.PhotoImage(file=path)
        except tk.TclError as err:
            self.status.configure(text=f"could not open: {str(err).lower()}", fg=ERROR)
            self.resize(16)
            return
        width, height = image.width(), image.height()
        size = max(width, height)
        if size > 128:
            self.status.configure(text="that picture is too big to paint here (128 pixels or less)", fg=ERROR)
            self.resize(16)
            return
        self.size = size
        self.pixels = [[(0, 0, 0, 0)] * size for _ in range(size)]
        for y in range(height):
            for x in range(width):
                if image.transparency_get(x, y):
                    continue
                value = image.get(x, y)
                if isinstance(value, str):
                    value = tuple(int(part) for part in value.split())
                self.pixels[y][x] = tuple(value[:3]) + (255,)
        self.size_var.set(size if size in (8, 16, 24, 32, 48, 64) else 0)
        self.draw()

    def cell(self):
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        return max(2, min(width, height) // self.size)

    def draw(self):
        canvas = self.canvas
        canvas.delete("all")
        if not self.pixels:
            return
        cell = self.cell()
        for y, row in enumerate(self.pixels):
            for x, pixel in enumerate(row):
                if pixel[3]:
                    fill = "#%02x%02x%02x" % pixel[:3]
                else:
                    fill = "#262626" if (x + y) % 2 else "#1f1f1f"
                outline = "#2c2c2c" if self.grid_on.get() and cell >= 6 else fill
                canvas.create_rectangle(x * cell, y * cell, (x + 1) * cell, (y + 1) * cell, fill=fill,
                                        outline=outline)
        canvas.create_rectangle(0, 0, cell * self.size, cell * self.size, outline=MOSS_DARK)
        self.after_idle(self.update_preview)

    def update_preview(self):
        size = self.size
        image = tk.PhotoImage(width=size, height=size)
        rows = []
        for row in self.pixels:
            rows.append("{" + " ".join("#%02x%02x%02x" % pixel[:3] if pixel[3] else "#202020" for pixel in row) + "}")
        image.put(" ".join(rows), to=(0, 0))
        self.preview = image
        self.preview_large = image.zoom(max(1, 96 // size))
        self.preview_label.configure(image=self.preview)
        self.preview_big.configure(image=self.preview_large)

    def choose(self, color):
        self.color = color
        self.current.configure(bg="#%02x%02x%02x" % color[:3])
        if self.tool.get() in ("eraser", "picker"):
            self.tool.set("pencil")

    def custom_color(self):
        from tkinter import colorchooser
        chosen = colorchooser.askcolor(color="#%02x%02x%02x" % self.color[:3], parent=self, title="choose a colour")
        if chosen and chosen[0]:
            self.choose(tuple(int(part) for part in chosen[0]) + (255,))

    def stroke(self, event, paint, start=False):
        cell = self.cell()
        x, y = event.x // cell, event.y // cell
        if not (0 <= x < self.size and 0 <= y < self.size):
            return
        if start:
            self.undo_stack.append([row[:] for row in self.pixels])
            self.undo_stack = self.undo_stack[-60:]
        tool = self.tool.get() if paint else "eraser"
        if tool == "picker":
            if self.pixels[y][x][3]:
                self.choose(self.pixels[y][x])
            return
        color = self.color if tool in ("pencil", "fill") else (0, 0, 0, 0)
        if tool == "fill":
            if start:
                self.fill(x, y, color)
            return
        self.pixels[y][x] = color
        if self.mirror.get():
            self.pixels[y][self.size - 1 - x] = color
        self.draw()

    def fill(self, x, y, color):
        target = self.pixels[y][x]
        if target == color:
            return
        stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            if 0 <= cx < self.size and 0 <= cy < self.size and self.pixels[cy][cx] == target:
                self.pixels[cy][cx] = color
                stack.extend(((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)))
        self.draw()

    def clear(self):
        self.undo_stack.append([row[:] for row in self.pixels])
        self.pixels = [[(0, 0, 0, 0)] * self.size for _ in range(self.size)]
        self.draw()

    def flip(self):
        self.undo_stack.append([row[:] for row in self.pixels])
        self.pixels = [list(reversed(row)) for row in self.pixels]
        self.draw()

    def undo(self):
        if self.undo_stack:
            self.pixels = self.undo_stack.pop()
            self.draw()

    def save(self):
        name = "".join(char for char in self.name.get().strip().lower() if char.isalnum() or char in "_-") or "sprite"
        os.makedirs(self.folder, exist_ok=True)
        path = os.path.join(self.folder, name + ".png")
        if os.path.exists(path) and os.path.normcase(path) != os.path.normcase(self.path or ""):
            if not confirm(self, "sprite painter", f"{name}.png already exists. replace it?", yes="replace"):
                return
        write_png(path, self.size, self.size, self.pixels)
        self.on_saved(path)
        self.close(path)


# ----- welcome page --------------------------------------------------------------------------------------------
class WelcomePage(tk.Frame):
    """what you see when nothing is open: templates, recent programs and how you like to code."""

    def __init__(self, parent, app):
        super().__init__(parent, bg=EDITOR_BG)
        self.app = app
        scroll = ScrollFrame(self, bg=EDITOR_BG)
        scroll.pack(fill="both", expand=True)
        page = tk.Frame(scroll.inner, bg=EDITOR_BG)
        page.pack(fill="both", expand=True, padx=px(48), pady=px(36))
        self.page = page
        head = tk.Frame(page, bg=EDITOR_BG)
        head.pack(fill="x")
        tk.Label(head, text="gublan studio", bg=EDITOR_BG, fg=TEXT, font=ui_font(26, "bold"), anchor="w").pack(
            anchor="w")
        tk.Label(head, text="make games and programs with simple commands. one idea per line.", bg=EDITOR_BG,
                 fg=MUTED, font=ui_font(11), anchor="w").pack(anchor="w", pady=(px(2), px(18)))
        columns = tk.Frame(page, bg=EDITOR_BG)
        columns.pack(fill="both", expand=True)
        left = tk.Frame(columns, bg=EDITOR_BG)
        left.pack(side="left", fill="y", anchor="n", padx=(0, px(40)))
        right = tk.Frame(columns, bg=EDITOR_BG)
        right.pack(side="left", fill="both", expand=True, anchor="n")

        self._heading(left, "start")
        for text, icon_name, command in (("new program", "new", app.new_tab),
                                         ("open a program", "open", app.open_dialog),
                                         ("open a folder", "folder", app.choose_folder),
                                         ("convert python, javascript or lua", "convert", app.open_converter),
                                         ("learn the basics", "learn", lambda: app.show_help("first steps"))):
            self._action(left, text, icon_name, command)

        self._heading(left, "how do you like to code?")
        self.level = tk.StringVar(value=app.settings.get("level", "beginner"))
        Segmented(left, [("beginner", "beginner"), ("standard", "standard"), ("expert", "expert")], self.level,
                  command=self._level, bg=EDITOR_BG, size=9).pack(anchor="w")
        self.level_about = tk.Label(left, text=config.LEVEL_ABOUT.get(self.level.get(), ""), bg=EDITOR_BG, fg=DIM,
                                    font=ui_font(9), justify="left", wraplength=px(300), anchor="w")
        self.level_about.pack(anchor="w", pady=(px(6), 0))

        recent = [path for path in app.settings.get("recent", []) if os.path.isfile(path)][:8]
        if recent:
            self._heading(left, "recent")
            for path in recent:
                row = tk.Frame(left, bg=EDITOR_BG, cursor="hand2")
                row.pack(fill="x", pady=px(1))
                name = tk.Label(row, text=os.path.basename(path), bg=EDITOR_BG, fg=MOSS_LIGHT, font=ui_font(10),
                                anchor="w", cursor="hand2")
                name.pack(side="left")
                where = tk.Label(row, text=self._short(os.path.dirname(path)), bg=EDITOR_BG, fg=DIM,
                                 font=ui_font(8), anchor="w", cursor="hand2")
                where.pack(side="left", padx=px(8))
                for widget in (row, name, where):
                    widget.bind("<Button-1>", lambda _e, p=path: app.open_path(p))
                name.bind("<Enter>", lambda _e, w=name: w.configure(fg=TEXT))
                name.bind("<Leave>", lambda _e, w=name: w.configure(fg=MOSS_LIGHT))

        self._heading(right, "start from a template")
        grid = tk.Frame(right, bg=EDITOR_BG)
        grid.pack(fill="x")
        for number, item in enumerate(TEMPLATES):
            card = self._card(grid, item)
            card.grid(row=number // 2, column=number % 2, sticky="nsew", padx=(0, px(10)), pady=(0, px(10)))
        grid.columnconfigure(0, weight=1, uniform="cards")
        grid.columnconfigure(1, weight=1, uniform="cards")
        self._heading(right, "tips")
        for tip in ("press f5 to run. press f10 to go one line at a time.",
                    "click the left edge of a line to pause there when running.",
                    "ctrl+space shows ideas. ctrl+shift+p finds any action.",
                    "the blocks view (ctrl+b) shows your program as blocks you can drag.",
                    "file > export program makes a .exe you can share."):
            tk.Label(right, text="·  " + tip, bg=EDITOR_BG, fg=MUTED, font=ui_font(9), anchor="w").pack(
                anchor="w", pady=px(1))
        scroll.bind_tree(scroll.inner)

    @staticmethod
    def _short(path, limit=46):
        return path if len(path) <= limit else "..." + path[-limit:]

    @staticmethod
    def _heading(parent, text):
        tk.Label(parent, text=lower(text), bg=EDITOR_BG, fg=DIM, font=ui_font(9, "bold"), anchor="w").pack(
            anchor="w", pady=(px(16), px(6)))

    def _action(self, parent, text, icon_name, command):
        row = tk.Frame(parent, bg=EDITOR_BG, cursor="hand2")
        row.pack(fill="x", pady=px(2))
        glyph = tk.Label(row, text=icon(icon_name), bg=EDITOR_BG, fg=MOSS_LIGHT, font=icon_font(12), width=2,
                         cursor="hand2")
        glyph.pack(side="left")
        name = tk.Label(row, text=lower(text), bg=EDITOR_BG, fg=TEXT, font=ui_font(11), anchor="w", cursor="hand2")
        name.pack(side="left", padx=px(6))
        for widget in (row, glyph, name):
            widget.bind("<Button-1>", lambda _e: command())
            widget.bind("<Enter>", lambda _e: name.configure(fg=MOSS_LIGHT))
            widget.bind("<Leave>", lambda _e: name.configure(fg=TEXT))

    def _card(self, parent, item):
        card = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER, cursor="hand2")
        top = tk.Frame(card, bg=PANEL)
        top.pack(fill="x", padx=px(12), pady=(px(10), px(2)))
        title = tk.Label(top, text=item["title"], bg=PANEL, fg=TEXT, font=ui_font(11, "bold"), anchor="w")
        title.pack(side="left")
        level = tk.Label(top, text=item["level"], bg=PANEL, fg=MOSS_LIGHT if item["level"] == "beginner" else DIM,
                         font=ui_font(8))
        level.pack(side="right")
        about = tk.Label(card, text=item["about"], bg=PANEL, fg=MUTED, font=ui_font(9), anchor="w", justify="left",
                         wraplength=px(200))
        about.pack(fill="x", padx=px(12), pady=(0, px(10)))
        # wrap to whatever width the card really gets, so descriptions are never cut off
        card.bind("<Configure>", lambda event: about.configure(wraplength=max(px(80), event.width - px(26))), add="+")
        widgets = (card, top, title, level, about)
        for widget in widgets:
            widget.bind("<Button-1>", lambda _e, key=item["key"]: self.app.new_from_template(key))
            widget.bind("<Enter>", lambda _e: card.configure(highlightbackground=MOSS))
            widget.bind("<Leave>", lambda _e: card.configure(highlightbackground=BORDER))
        return card

    def _level(self, level):
        self.app.set_level(level)
        self.level_about.configure(text=config.LEVEL_ABOUT.get(level, ""))
