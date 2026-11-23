"""square, lowercase dialogs: messages, questions, settings, converter, export, palette and sprites."""

import os
import struct
import subprocess
import threading
import tkinter as tk
import zlib
from tkinter import filedialog, ttk

from gublancore import COMMAND_SPECS, DIALOG_ANIMATIONS, GAME_STYLE, color_value, game_style

from . import config, exporter, guard, sounds, theme
from .caret import CARET_BLINKS, CARET_STYLES, TYPING_EFFECTS
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
        if theme.MOTION:
            theme.slide_in(self, x, y, width, height, dy=px(10), duration=180)
        else:
            theme.fade_in(self, 150)
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


def from_thread(widget, func, *args):
    """hand a worker thread's result to the tk thread (calling widget.after from a thread can crash tcl)."""
    def call():
        try:
            alive = widget.winfo_exists()
        except tk.TclError:
            alive = False
        if alive:
            func(*args)
    guard.call_soon(call)


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
    def __init__(self, master, settings, on_apply, presence=None, app=None):
        super().__init__(master, "settings", resizable=True)
        self.settings = settings
        self.on_apply = on_apply
        self.presence = presence
        self.app = app
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
                          ("rainbow_brackets", "colour brackets by how deep they are"),
                          ("smooth_scroll", "smooth scrolling")):
            self._toggle(page, key, text)
        self._editor_look(page)

        self._heading(page, "running")
        for key, text in (("check_before_run", "check for problems before running"),
                          ("warnings", "show warnings, not just errors"),
                          ("clear_output", "clear the output each run"),
                          ("show_variables_on_run", "open the variables panel when a program runs"),
                          ("autosave", "save before running"),
                          ("toolbar_labels", "show words on the toolbar buttons")):
            self._toggle(page, key, text)

        self._look_section(page)
        self._sounds_section(page)
        self._plugins_section(page)
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
        sounds.configure(self.settings)
        self.on_apply(self.settings)
        self._show_discord()

    def _choices(self, parent, key, text, options, default, convert=str, per_row=6, about=None):
        """a labelled row (or rows) of square choices for one setting."""
        variable = tk.StringVar(value=str(self.settings.get(key, default)))
        self.vars[key] = variable
        about_label = None

        def chosen(value):
            self._set(key, convert(value))
            if about_label is not None:
                about_label.configure(text=about.get(value, ""))

        for start in range(0, max(1, len(options)), per_row):
            row = tk.Frame(parent, bg=PANEL)
            row.pack(fill="x", pady=px(2))
            tk.Label(row, text=text if start == 0 else "", bg=PANEL, fg=TEXT, font=ui_font(10), width=14,
                     anchor="w").pack(side="left")
            Segmented(row, [(str(value), shown) for value, shown in options[start:start + per_row]], variable,
                      command=chosen, bg=PANEL, size=9).pack(side="left", padx=px(4))
        if about:
            about_label = tk.Label(parent, text=about.get(variable.get(), ""), bg=PANEL, fg=DIM, font=ui_font(9),
                                   anchor="w", justify="left", wraplength=px(520))
            about_label.pack(fill="x", pady=(0, px(4)))
        return variable

    def _editor_look(self, page):
        fonts = [("", "default")] + [(shown, shown) for shown, _family in theme.editor_fonts(self)][:9]
        self._choices(page, "editor_font", "code font", fonts, "", per_row=4)
        self._choices(page, "line_spacing", "line spacing", [(0, "tight"), (1, "normal"), (3, "roomy"),
                                                             (5, "airy")], 1, convert=int)
        self._heading(page, "cursor and typing")
        self._toggle(page, "smooth_caret", "a smooth cursor that glides from place to place")
        self._choices(page, "caret_style", "cursor shape", [(name, name) for name in CARET_STYLES], "line")
        self._choices(page, "caret_blink", "blinking", [(name, {"solid": "don't blink"}.get(name, name))
                                                       for name in CARET_BLINKS], "fade")
        self._choices(page, "caret_motion", "movement", [("smooth", "glide"), ("instant", "jump")], "smooth")
        self._choices(page, "caret_width", "thickness", [(1, "thin"), (2, "normal"), (3, "thick"), (4, "chunky")],
                      2, convert=int)
        self._choices(page, "typing_effect", "new letters", [(name, {"fade": "fade in"}.get(name, name))
                                                            for name in TYPING_EFFECTS], "fade",
                      about={"fade": "letters you type fade in from the background.",
                             "ink": "letters start bright and settle into their colour, like wet ink.",
                             "glow": "a soft light grows behind each letter and fades away.",
                             "off": "letters just appear."})

    # ----- look --------------------------------------------------------------------------------------------
    def _look_section(self, page):
        self._heading(page, "look")
        names = theme.theme_names()
        self.theme_var = tk.StringVar(value=self.settings.get("theme", theme.DEFAULT_THEME))
        self._first_theme = self.theme_var.get()
        for start in range(0, len(names), 5):
            row = tk.Frame(page, bg=PANEL)
            row.pack(fill="x", pady=px(2))
            if start == 0:
                tk.Label(row, text="theme", bg=PANEL, fg=TEXT, font=ui_font(10), width=6, anchor="w").pack(
                    side="left")
            else:
                tk.Label(row, text="", bg=PANEL, width=6).pack(side="left")
            Segmented(row, [(name, name) for name in names[start:start + 5]], self.theme_var,
                      command=self._choose_theme, bg=PANEL, size=9).pack(side="left", padx=px(12))
        self.theme_about = tk.Label(page, text="", bg=PANEL, fg=DIM, font=ui_font(9), anchor="w", justify="left",
                                    wraplength=px(520))
        self.theme_about.pack(fill="x", pady=(px(2), 0))
        row = tk.Frame(page, bg=PANEL)
        row.pack(fill="x", pady=(px(4), px(4)))
        self.restart_button = BracketButton(row, "restart for a clean redraw", command=self._restart, size=9,
                                            bg=PANEL)
        self.themes_button = BracketButton(row, "open the themes folder", command=self._themes_folder, size=9,
                                           bg=PANEL)
        self.themes_button.pack(side="left")
        self._needs_restart = False
        self._show_theme()
        self._accent_row(page)
        self._choices(page, "animation_speed", "animation speed", [("slow", "slow"), ("normal", "normal"),
                                                                   ("fast", "fast")], "normal")
        self._first_scale = int(self.settings.get("ui_scale", 100))
        self._choices(page, "ui_scale", "interface size", [(90, "90%"), (100, "100%"), (110, "110%"),
                                                           (125, "125%"), (150, "150%")], 100,
                      convert=self._choose_scale)
        self._toggle(page, "animations", "animate buttons, menus, windows and messages")

    def _choose_scale(self, value):
        value = int(value)
        self._needs_restart = value != self._first_scale
        self.after_idle(self._show_theme)
        return value

    def _accent_row(self, page):
        row = tk.Frame(page, bg=PANEL)
        row.pack(fill="x", pady=(px(6), px(2)))
        tk.Label(row, text="accent colour", bg=PANEL, fg=TEXT, font=ui_font(10), width=14, anchor="w").pack(
            side="left")
        self.accent_cells = {}
        holder = tk.Frame(row, bg=PANEL)
        holder.pack(side="left", padx=px(4))
        for name, color in theme.accent_choices():
            cell = tk.Canvas(holder, width=px(24), height=px(24), bg=PANEL, highlightthickness=0, cursor="hand2")
            cell.pack(side="left", padx=(0, px(4)))
            cell.bind("<Button-1>", lambda _e, c=color: self._choose_accent(c))
            theme.Tooltip(cell, name if color else "the theme's own colour")
            self.accent_cells[color] = cell
        BracketButton(holder, "other...", command=self._custom_accent, size=9, bg=PANEL).pack(side="left",
                                                                                            padx=(px(4), 0))
        self._paint_accents()

    def _paint_accents(self):
        current = str(self.settings.get("accent_color") or "").lower()
        base = theme.theme_spec(self.settings.get("theme", theme.DEFAULT_THEME)) or {}
        own = (base.get("colors") or {}).get("accent") or theme.MOSS
        size = px(24)
        for color, cell in self.accent_cells.items():
            cell.delete("all")
            fill = color or own
            chosen = color.lower() == current or (not color and not current)
            cell.create_rectangle(px(3), px(3), size - px(3), size - px(3), fill=fill, outline="")
            if not color:
                cell.create_line(px(3), size - px(3), size - px(3), px(3), fill=PANEL, width=px(2))
            if chosen:
                cell.create_rectangle(1, 1, size - 1, size - 1, outline=TEXT, width=px(2))

    def _choose_accent(self, color):
        self._set("accent_color", color)
        self._paint_accents()

    def _custom_accent(self):
        from tkinter import colorchooser
        current = self.settings.get("accent_color") or theme.MOSS
        chosen = colorchooser.askcolor(color=current, title="pick an accent colour", parent=self)
        if chosen and chosen[1]:
            self._choose_accent(chosen[1].lower())
    def _choose_theme(self, name):
        self._set("theme", name)
        self._show_theme()

    def _show_theme(self):
        name = self.theme_var.get()
        spec = theme.theme_spec(name) or {}
        about = spec.get("about") or ("your own theme" if name not in theme.BUILTIN_THEMES else "")
        changed = name != getattr(self, "_first_theme", name)
        scaled = getattr(self, "_needs_restart", False)
        note = "  a few shades only change after a restart." if changed else ""
        if scaled:
            note += "  the new interface size shows after a restart."
        self.theme_about.configure(text=about + note)
        if hasattr(self, "accent_cells"):
            self._paint_accents()
        if (changed or scaled) and self.app is not None:
            self.restart_button.pack(side="left", padx=(0, px(8)), before=self.themes_button)
        else:
            self.restart_button.pack_forget()

    def _restart(self):
        if self.app is not None:
            self.cancel()
            self.app.restart()

    def _themes_folder(self):
        if self.app is not None:
            self.app.open_themes_folder()

    # ----- sounds ------------------------------------------------------------------------------------------
    def _sounds_section(self, page):
        self._heading(page, "sounds")
        self._toggle(page, "sounds", "play soft sounds when things open, run, finish or go wrong")
        self._choices(page, "sound_pack", "sound set", [(name, name) for name in sounds.PACKS], "soft",
                      about=sounds.ABOUT)
        self._choices(page, "sound_volume", "volume", [(15, "whisper"), (30, "quiet"), (45, "normal"),
                                                       (65, "loud"), (85, "louder")], 45, convert=int)
        self._toggle(page, "typing_sounds", "a tiny tick for each letter you type")
        row = tk.Frame(page, bg=PANEL)
        row.pack(fill="x", pady=(px(4), px(2)))
        tk.Label(row, text="listen", bg=PANEL, fg=TEXT, font=ui_font(10), width=14, anchor="w").pack(side="left")
        for event in ("open", "run", "done", "save", "error", "notify"):
            BracketButton(row, event, command=lambda e=event: sounds.play(e, force=True), size=9,
                          bg=PANEL).pack(side="left", padx=(px(4), 0))

    # ----- plugins -----------------------------------------------------------------------------------------
    def _plugins_section(self, page):
        from . import plugins
        self._heading(page, "plugins")
        tk.Label(page, text="plugins are python files that add commands, functions and menu items to gublan "
                            "studio. they run with your permissions, so only add ones you trust. changes take a "
                            "restart.",
                 bg=PANEL, fg=DIM, font=ui_font(9), anchor="w", justify="left", wraplength=px(520)).pack(
            fill="x", pady=(0, px(4)))
        self._toggle(page, "plugins", "load plugins from the plugins folder")
        loaded = {info.key: info for info in (getattr(self.app, "plugins", None) or [])}
        found = plugins.find_plugins()
        disabled = set(self.settings.get("disabled_plugins", []))
        for info in found:
            shown = loaded.get(info.key, info)
            variable = tk.BooleanVar(value=info.key not in disabled)
            text = shown.describe() if shown.status != "off" else info.key
            Toggle(page, text, variable, command=lambda k=info.key, v=variable: self._plugin_on(k, v.get()),
                   bg=PANEL).pack(anchor="w", pady=px(2), padx=(px(24), 0))
        if not found:
            tk.Label(page, text="no plugins yet. the folder button adds an example to copy.", bg=PANEL, fg=DIM,
                     font=ui_font(9), anchor="w").pack(fill="x", padx=(px(24), 0))
        row = tk.Frame(page, bg=PANEL)
        row.pack(fill="x", pady=(px(6), 0))
        BracketButton(row, "open the plugins folder", command=self._plugins_folder, size=9, bg=PANEL).pack(
            side="left")
        if self.app is not None:
            BracketButton(row, "restart now", command=self._restart, size=9, bg=PANEL).pack(side="left",
                                                                                             padx=(px(8), 0))

    def _plugin_on(self, key, on):
        disabled = [name for name in self.settings.get("disabled_plugins", []) if name != key]
        if not on:
            disabled.append(key)
        self._set("disabled_plugins", disabled)

    def _plugins_folder(self):
        if self.app is not None:
            self.app.open_plugins_folder()
        else:
            from . import plugins
            plugins.write_example()

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
# ----- game window and popups ---------------------------------------------------------------------------
POPUP_LOOKS = {
    "moss": {},
    "paper": {"dialog_background": "#f4f1e8", "dialog_text": "#2a2a2a", "dialog_hint": "#7a7468",
              "dialog_accent": "#5b7a3a", "dialog_border": "#2a2a2a", "dialog_field": "#ffffff",
              "dialog_border_width": 2, "dialog_shade": 40},
    "night": {"dialog_background": "#141a2a", "dialog_text": "#dfe6ff", "dialog_hint": "#7f8bb0",
              "dialog_accent": "#7aa2ff", "dialog_border": "#7aa2ff", "dialog_field": "#0b0f1a",
              "dialog_border_width": 2, "dialog_shade": 80},
    "arcade": {"dialog_background": "#1a1060", "dialog_text": "#ffe14d", "dialog_hint": "#b9a8ff",
               "dialog_accent": "#ff5fa2", "dialog_border": "#ffe14d", "dialog_field": "#0d0838",
               "dialog_border_width": 4, "dialog_shade": 60},
    "glass": {"dialog_background": "#2a3138", "dialog_text": "#ffffff", "dialog_hint": "#b8c4cc",
              "dialog_accent": "#9fd3ff", "dialog_border": "#5c6a75", "dialog_field": "#1b2026",
              "dialog_border_width": 1, "dialog_shade": 40},
}
WINDOW_SIZES = ((540, 420), (640, 480), (800, 600), (960, 540), (1280, 720))
STYLE_DEMO = """mode 2d
text hello 20 20 this is your game window
box player 40 80 70 70
circle ball 260 140 30
popup this is how popups look. press a key or click to go on
input name and this is how questions look. what is your name?
popup nice to meet you, {name}!
kill
"""


def hex_color(value):
    """#rrggbb for a gublan colour (a name, #rgb or #rrggbb)."""
    try:
        red, green, blue = color_value(value)[:3]
        return f"#{int(red):02x}{int(green):02x}{int(blue):02x}"
    except (ValueError, TypeError, KeyError):
        return "#000000"


class GameStyleDialog(Dialog):
    """tools > game window and popups: how game windows start and how popups and questions look, sound and
    move. the preview follows every change; programs can still set their own window, background and fps."""

    COLORS = (("dialog_background", "box"), ("dialog_text", "text"), ("dialog_border", "border"),
              ("dialog_accent", "cursor"), ("dialog_field", "answer field"), ("dialog_hint", "hints"))

    def __init__(self, master, settings, on_apply, app=None):
        super().__init__(master, "game window and popups", resizable=True)
        self.settings = settings
        self.on_apply = on_apply
        self.app = app
        stored = settings.get("game_style")
        self.style = game_style(stored if isinstance(stored, dict) else {})
        self.vars = {}
        self.swatches = {}
        self.intro = 1.0
        self._intro_stop = None
        self._store_job = None
        self._size_lock = False

        columns = tk.Frame(self.body, bg=PANEL)
        columns.pack(fill="both", expand=True)
        right = tk.Frame(columns, bg=PANEL)
        right.pack(side="right", fill="y", padx=(px(18), 0))
        scroll = ScrollFrame(columns, bg=PANEL)
        scroll.pack(side="left", fill="both", expand=True)
        page = scroll.inner

        tk.Label(right, text="preview", bg=PANEL, fg=MOSS_LIGHT, font=ui_font(11, "bold"), anchor="w").pack(
            fill="x", pady=(0, px(6)))
        self.preview_size = (px(360), px(290))
        self.preview = tk.Canvas(right, width=self.preview_size[0], height=self.preview_size[1], bg=EDITOR_BG,
                                 highlightthickness=1, highlightbackground=BORDER, cursor="hand2")
        self.preview.pack()
        self.preview.bind("<Button-1>", lambda _e: self.replay())
        tk.Label(right, text="click the preview to watch the popup open again", bg=PANEL, fg=DIM,
                 font=ui_font(9), anchor="w").pack(fill="x", pady=(px(4), px(8)))
        BracketButton(right, "try it in a game window", command=self.try_it, icon_name="play", size=9,
                      bg=PANEL).pack(anchor="w")
        tk.Label(right, text="programs you run and games you export use this look. a program's own\n"
                             "window, background and fps lines still win.", bg=PANEL, fg=DIM,
                 font=ui_font(8), anchor="w", justify="left").pack(fill="x", pady=(px(10), 0))

        self._heading(page, "game window")
        row = tk.Frame(page, bg=PANEL)
        row.pack(fill="x", pady=px(2))
        tk.Label(row, text="size", bg=PANEL, fg=TEXT, font=ui_font(10), width=12, anchor="w").pack(side="left")
        self.width_var = tk.StringVar(value=str(self.style["width"]))
        self.height_var = tk.StringVar(value=str(self.style["height"]))
        flat_entry(row, self.width_var, width=6, mono=True).pack(side="left", padx=(px(4), 0))
        tk.Label(row, text="by", bg=PANEL, fg=DIM, font=ui_font(10)).pack(side="left", padx=px(6))
        flat_entry(row, self.height_var, width=6, mono=True).pack(side="left")
        for variable in (self.width_var, self.height_var):
            variable.trace_add("write", lambda *_: self._size_typed())
        self.size_choice = tk.StringVar(value=self._size_key())
        row = tk.Frame(page, bg=PANEL)
        row.pack(fill="x", pady=px(2))
        tk.Label(row, text="", bg=PANEL, width=12).pack(side="left")
        Segmented(row, [(f"{w}x{h}", f"{w} x {h}") for w, h in WINDOW_SIZES], self.size_choice,
                  command=self._size_chosen, bg=PANEL, size=8).pack(side="left", padx=px(4))
        row = tk.Frame(page, bg=PANEL)
        row.pack(fill="x", pady=px(2))
        tk.Label(row, text="title", bg=PANEL, fg=TEXT, font=ui_font(10), width=12, anchor="w").pack(side="left")
        self.title_var = tk.StringVar(value=self.style["title"])
        flat_entry(row, self.title_var, width=28).pack(side="left", padx=(px(4), 0))
        self.title_var.trace_add("write", lambda *_: self._set("title", self.title_var.get()[:120], later=True))
        tk.Label(page, text="leave the title empty to use the program's name.", bg=PANEL, fg=DIM, font=ui_font(9),
                 anchor="w").pack(fill="x")
        grid = tk.Frame(page, bg=PANEL)
        grid.pack(fill="x", pady=(px(6), px(2)))
        self._swatch(grid, "background", "background").grid(row=0, column=0, sticky="w", pady=px(3))
        self._swatch(grid, "color", "drawing colour").grid(row=0, column=1, sticky="w", padx=(px(24), 0),
                                                            pady=px(3))
        self._choices(page, "fps", "fps", [(30, "30"), (60, "60"), (90, "90"), (120, "120"),
                                                        (144, "144")], int)
        self._toggle(page, "show_fps", "show a small fps counter in the corner")

        self._heading(page, "popups and questions")
        self.look = tk.StringVar(value=self._look_name())
        row = tk.Frame(page, bg=PANEL)
        row.pack(fill="x", pady=px(2))
        tk.Label(row, text="looks", bg=PANEL, fg=TEXT, font=ui_font(10), width=12, anchor="w").pack(side="left")
        Segmented(row, [(name, name) for name in list(POPUP_LOOKS) + ["studio"]], self.look,
                  command=self._choose_look, bg=PANEL, size=9).pack(side="left", padx=px(4))
        grid = tk.Frame(page, bg=PANEL)
        grid.pack(fill="x", pady=(px(6), px(2)))
        for index, (key, text) in enumerate(self.COLORS):
            self._swatch(grid, key, text).grid(row=index // 2, column=index % 2, sticky="w",
                                               padx=(0 if index % 2 == 0 else px(24), 0), pady=px(3))
        self._choices(page, "dialog_animation", "opening", [(name, name) for name in DIALOG_ANIMATIONS], str)
        self._choices(page, "dialog_position", "position", [("top", "top"), ("center", "middle"),
                                                            ("bottom", "bottom")], str)
        self._choices(page, "dialog_width", "box width", [(360, "narrow"), (450, "normal"), (560, "wide"),
                                                          (680, "wider")], int)
        self._choices(page, "dialog_text_size", "text size", [(18, "18"), (22, "22"), (26, "26"), (30, "30"),
                                                              (36, "36")], int)
        self._choices(page, "dialog_border_width", "border", [(0, "none"), (1, "thin"), (2, "normal"),
                                                              (4, "thick")], int)
        self._choices(page, "dialog_shade", "dim the game", [(0, "no"), (40, "a little"), (75, "normal"),
                                                             (92, "a lot")], int)
        self._toggle(page, "dialog_hints", "show the key hints under the message")
        self._toggle(page, "dialog_sound", "play a soft sound when a popup opens")
        scroll.bind_tree(page)

        self.add_button("done", self.cancel, kind="accent")
        self.add_button("back to the default look", self.reset, kind="ghost", side="left")
        self.draw_preview()
        self.after(250, self.replay)

    # ----- rows ----------------------------------------------------------------------------------------
    @staticmethod
    def _heading(parent, text):
        tk.Label(parent, text=text, bg=PANEL, fg=MOSS_LIGHT, font=ui_font(11, "bold"), anchor="w").pack(
            fill="x", pady=(px(12), px(6)))

    def _choices(self, parent, key, text, options, convert):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=px(2))
        tk.Label(row, text=text, bg=PANEL, fg=TEXT, font=ui_font(10), width=12, anchor="w").pack(side="left")
        variable = tk.StringVar(value=str(self.style[key]))
        self.vars[key] = variable
        Segmented(row, [(str(value), shown) for value, shown in options], variable,
                  command=lambda value: self._set(key, convert(value)), bg=PANEL, size=9).pack(side="left",
                                                                                              padx=px(4))

    def _toggle(self, parent, key, text):
        variable = tk.BooleanVar(value=bool(self.style[key]))
        self.vars[key] = variable
        Toggle(parent, text, variable, command=lambda: self._set(key, bool(variable.get())), bg=PANEL).pack(
            anchor="w", pady=px(3))

    def _swatch(self, parent, key, text):
        cell = tk.Frame(parent, bg=PANEL, cursor="hand2")
        box = tk.Canvas(cell, width=px(20), height=px(20), bg=PANEL, highlightthickness=0, cursor="hand2")
        box.pack(side="left")
        name = tk.Label(cell, text=text, bg=PANEL, fg=TEXT, font=ui_font(10), cursor="hand2")
        name.pack(side="left", padx=(px(8), 0))
        shown = tk.Label(cell, text="", bg=PANEL, fg=DIM, font=mono_font(9), cursor="hand2")
        shown.pack(side="left", padx=(px(6), 0))
        for widget in (cell, box, name, shown):
            widget.bind("<Button-1>", lambda _e, k=key: self.pick_color(k))
        self.swatches[key] = (box, shown)
        self._paint_swatch(key)
        return cell

    def _paint_swatch(self, key):
        box, shown = self.swatches[key]
        size = px(20)
        box.delete("all")
        box.create_rectangle(1, 1, size - 1, size - 1, fill=hex_color(self.style[key]), outline=BORDER)
        shown.configure(text=hex_color(self.style[key]))

    # ----- changes -------------------------------------------------------------------------------------
    def _set(self, key, value, later=False):
        self.style[key] = value
        if key.startswith("dialog_") and key in POPUP_LOOKS["paper"]:
            self.look.set(self._look_name())
        if key == "dialog_animation":
            self.replay()
        else:
            self.draw_preview()
        if self._store_job:
            self.after_cancel(self._store_job)
        self._store_job = self.after(400 if later else 0, self._store)

    def _store(self):
        self._store_job = None
        self.settings["game_style"] = {key: value for key, value in self.style.items()
                                       if value != GAME_STYLE[key]}
        self.on_apply(self.settings)

    def pick_color(self, key):
        from tkinter import colorchooser
        chosen = colorchooser.askcolor(color=hex_color(self.style[key]), title="pick a colour", parent=self)
        if chosen and chosen[1]:
            self._set(key, chosen[1].lower())
            self._paint_swatch(key)

    def _size_key(self):
        return f"{self.style['width']}x{self.style['height']}"

    def _size_chosen(self, value):
        width, height = (int(part) for part in value.split("x"))
        self._size_lock = True
        self.width_var.set(str(width))
        self.height_var.set(str(height))
        self._size_lock = False
        self.style["width"], self.style["height"] = width, height
        self._set("width", width)

    def _size_typed(self):
        if self._size_lock:
            return
        try:
            width = max(120, min(4096, int(self.width_var.get())))
            height = max(90, min(4096, int(self.height_var.get())))
        except ValueError:
            return
        self.style["width"], self.style["height"] = width, height
        self.size_choice.set(self._size_key())
        self._set("height", height, later=True)

    def _look_name(self):
        for name, look in POPUP_LOOKS.items():
            wanted = dict((key, GAME_STYLE[key]) for key in POPUP_LOOKS["paper"])
            wanted.update(look)
            if all(self.style[key] == value for key, value in wanted.items()):
                return name
        return ""

    def _studio_look(self):
        return {"dialog_background": theme.PANEL, "dialog_text": theme.TEXT, "dialog_hint": theme.MUTED,
                "dialog_accent": theme.MOSS_LIGHT, "dialog_border": theme.MOSS, "dialog_field": theme.EDITOR_BG,
                "dialog_border_width": 1, "dialog_shade": 60}

    def _choose_look(self, name):
        look = dict((key, GAME_STYLE[key]) for key in POPUP_LOOKS["paper"])
        look.update(self._studio_look() if name == "studio" else POPUP_LOOKS.get(name, {}))
        self.style.update(look)
        for key, value in look.items():
            if key in self.swatches:
                self._paint_swatch(key)
            elif key in self.vars:
                self.vars[key].set(str(value))
        self.look.set(name)
        self._set("dialog_background", self.style["dialog_background"])
        self.look.set(name)
        self.replay()

    def reset(self):
        self.style = game_style({})
        for key, variable in self.vars.items():
            variable.set(self.style[key] if isinstance(variable, tk.BooleanVar) else str(self.style[key]))
        for key in self.swatches:
            self._paint_swatch(key)
        self._size_lock = True
        self.width_var.set(str(self.style["width"]))
        self.height_var.set(str(self.style["height"]))
        self.title_var.set("")
        self._size_lock = False
        self.size_choice.set(self._size_key())
        self.look.set(self._look_name())
        self._set("width", self.style["width"])
        self.replay()

    def try_it(self):
        if self.app is not None:
            self.app.try_game_style(dict(self.style))

    # ----- preview -------------------------------------------------------------------------------------
    def replay(self):
        if self._intro_stop:
            self._intro_stop()

        def step(progress):
            self.intro = progress
            self.draw_preview()

        if self.style["dialog_animation"] == "none":
            step(1.0)
            return
        self.intro = 0.0
        self._intro_stop = theme.animate(self.preview, 320, step, ease=lambda t: t)

    def draw_preview(self):
        """a small copy of the game window with a question box on it, drawn the way gublancore draws it."""
        try:
            canvas = self.preview
            canvas.delete("all")
        except tk.TclError:
            return
        style = self.style
        area_width, area_height = self.preview_size
        bar = px(18)
        width, height = style["width"], style["height"]
        scale = min((area_width - px(24)) / width, (area_height - px(24) - bar) / height)
        shown_width, shown_height = int(width * scale), int(height * scale)
        left = (area_width - shown_width) // 2
        top = (area_height - shown_height - bar) // 2 + bar
        progress = self.intro
        shade = style["dialog_shade"] / 100 * min(1.0, progress * 1.4)

        def dim(color):
            return theme.mix(hex_color(color), "#000000", shade)

        canvas.create_rectangle(left, top - bar, left + shown_width, top, fill=PANEL_ALT, outline=BORDER)
        title = style["title"] or "my game"
        canvas.create_text(left + px(8), top - bar // 2, text=title, anchor="w", fill=MUTED, font=ui_font(8))
        canvas.create_text(left + shown_width - px(8), top - bar // 2, text="x", anchor="e", fill=MUTED,
                           font=ui_font(8))
        canvas.create_rectangle(left, top, left + shown_width, top + shown_height, fill=dim(style["background"]),
                                outline=BORDER)
        ink = dim(style["color"])
        canvas.create_rectangle(left + 40 * scale, top + 80 * scale, left + 110 * scale, top + 150 * scale,
                                fill=ink, outline="")
        canvas.create_oval(left + 230 * scale, top + 110 * scale, left + 290 * scale, top + 170 * scale,
                           fill=ink, outline="")
        canvas.create_text(left + 20 * scale, top + 20 * scale, text="score 120", anchor="nw", fill=ink,
                           font=(theme.UI_FAMILY, -max(6, int(20 * scale))))
        if style["show_fps"]:
            canvas.create_text(left + shown_width - px(6), top + px(5), text="fps 60", anchor="ne",
                               fill=dim(style["dialog_accent"]), font=(theme.UI_FAMILY, -max(6, int(16 * scale))))

        size = max(6, int(style["dialog_text_size"] * scale))
        font = (theme.UI_FAMILY, -size, "bold")
        hint_font = (theme.UI_FAMILY, -max(5, int((style["dialog_text_size"] - 4) * scale)))
        line = size * 1.25
        box_width = min(style["dialog_width"], width - 20) * scale
        box_height = (25 * scale + line + line + 24 * scale +
                      ((line * 0.85 + 20 * scale) if style["dialog_hints"] else 10 * scale))
        box_left = left + (shown_width - box_width) / 2
        place = style["dialog_position"]
        if place == "top":
            box_top = top + 20 * scale
        elif place == "bottom":
            box_top = top + shown_height - box_height - 20 * scale
        else:
            box_top = top + (shown_height - box_height) / 2
        animation = style["dialog_animation"]
        eased = 1 - (1 - progress) ** 3
        fade = 1.0
        grow = 1.0
        if progress < 1.0 and animation != "none":
            if animation == "pop":
                grow = 0.86 + 0.14 * (1 + 2.70158 * (progress - 1) ** 3 + 1.70158 * (progress - 1) ** 2)
                fade = min(1.0, progress * 1.6)
            elif animation == "slide":
                box_top += (40 if place != "top" else -40) * scale * (1 - eased)
                fade = eased
            else:
                fade = eased
        backdrop = dim(style["background"])

        def blend(color):
            return theme.mix(backdrop, hex_color(color), fade)

        center_x, center_y = box_left + box_width / 2, box_top + box_height / 2
        x0, y0 = center_x - box_width * grow / 2, center_y - box_height * grow / 2
        x1, y1 = center_x + box_width * grow / 2, center_y + box_height * grow / 2
        border = style["dialog_border_width"]
        canvas.create_rectangle(x0, y0, x1, y1, fill=blend(style["dialog_background"]),
                                outline=blend(style["dialog_border"]) if border else "",
                                width=max(1, round(border * scale)) if border else 0)
        if grow < 0.97 and animation == "pop":
            return
        y = y0 + 22 * scale * grow
        canvas.create_text(x0 + 20 * scale, y, text="what is your name?", anchor="nw",
                           fill=blend(style["dialog_text"]), font=font)
        y += line + 10 * scale
        field_bottom = y + line + 12 * scale
        canvas.create_rectangle(x0 + 20 * scale, y, x1 - 20 * scale, field_bottom,
                                fill=blend(style["dialog_field"]), outline="")
        typed = canvas.create_text(x0 + 28 * scale, y + 6 * scale, text="gublan fan", anchor="nw",
                                   fill=blend(style["dialog_text"]), font=font)
        right_edge = canvas.bbox(typed)[2] if canvas.bbox(typed) else x0
        canvas.create_line(right_edge + 2, y + 4 * scale, right_edge + 2, field_bottom - 5 * scale,
                           fill=blend(style["dialog_accent"]), width=max(1, round(2 * scale)))
        if style["dialog_hints"]:
            canvas.create_text(x0 + 20 * scale, field_bottom + 12 * scale, text="enter to accept  |  esc to cancel",
                               anchor="nw", fill=blend(style["dialog_hint"]), font=hint_font)


def highlight_into(widget, source):
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", source)
    for tag, color in SYNTAX.items():
        widget.tag_configure(tag, foreground=color)
    widget.tag_configure("todo", foreground=NUMBER)
    for number, line in enumerate(source.split("\n"), start=1):
        if number > 6000 or len(line) > 2000:
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
            if os.path.getsize(path) > 8 * 1024 * 1024:
                message(self, "convert", "that file is too big to convert (over 8 mb).", "error")
                return
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                content = handle.read()
        except OSError as err:
            message(self, "convert", f"could not open the file: {str(err).lower()}", "error")
            return
        if "\x00" in content[:4096]:
            message(self, "convert", "that file isn't code (it looks like a binary file).", "error")
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
                from_thread(self, self._finished, result, error)
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


# ----- export as another language -------------------------------------------------------------------------------
def highlight_foreign(widget, source, comment):
    """light colouring for python, javascript or lua: comments dim, todo notes stand out."""
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", source)
    widget.tag_configure("comment", foreground=DIM)
    widget.tag_configure("todo", foreground=NUMBER)
    for number, line in enumerate(source.split("\n"), start=1):
        if number > 6000:
            break
        stripped = line.lstrip()
        if stripped.startswith(comment):
            tag = "todo" if stripped[len(comment):].lstrip().startswith("todo") else "comment"
            widget.tag_add(tag, f"{number}.0", f"{number}.end")
    widget.configure(state="disabled")


class TranslateDialog(Dialog):
    """turn the open gublan program into python, javascript or lua (with the small runtime it needs)."""

    COMMENTS = {"python": "#", "javascript": "//", "lua": "--"}

    def __init__(self, master, source, name, base_dir, settings=None):
        super().__init__(master, "export as another language", resizable=True)
        self.source_code = source
        self.program = os.path.splitext(name)[0] or "program"
        self.base_dir = base_dir
        self.settings = settings if settings is not None else {}
        self.result = None
        self.files = {}
        top = tk.Frame(self.body, bg=PANEL)
        top.pack(fill="x", pady=(0, px(10)))
        tk.Label(top, text="to", bg=PANEL, fg=MUTED, font=ui_font(10)).pack(side="left")
        self.language = tk.StringVar(value=self.settings.get("translate_language", "python"))
        Segmented(top, [("python", "python"), ("javascript", "javascript (web)"), ("lua", "lua (love2d)")],
                  self.language, bg=PANEL, size=9, command=lambda *_: self.translate()).pack(side="left", padx=px(10))
        self.status = tk.Label(top, text="", bg=PANEL, fg=DIM, font=ui_font(9))
        self.status.pack(side="right")

        files_row = tk.Frame(self.body, bg=PANEL)
        files_row.pack(fill="x", pady=(0, px(6)))
        tk.Label(files_row, text="file", bg=PANEL, fg=MUTED, font=ui_font(9)).pack(side="left")
        self.shown_file = tk.StringVar(value="")
        self.file_tabs = tk.Frame(files_row, bg=PANEL)
        self.file_tabs.pack(side="left", padx=px(10))
        self.preview = self._code_box(self.body)

        self.notes = tk.Label(self.body, text="", bg=PANEL, fg=MUTED, font=ui_font(9), justify="left", anchor="w",
                              wraplength=px(860))
        self.notes.pack(fill="x", pady=(px(8), 0))
        where = tk.Frame(self.body, bg=PANEL)
        where.pack(fill="x", pady=(px(8), 0))
        where.columnconfigure(1, weight=1)
        tk.Label(where, text="save in", bg=PANEL, fg=MUTED, font=ui_font(10)).grid(row=0, column=0, sticky="w")
        self.folder = tk.StringVar(value="")
        entry = flat_entry(where, self.folder, width=40)
        entry.grid(row=0, column=1, sticky="ew", padx=px(10))
        self.folder.trace_add("write", lambda *_: self.after_idle(entry.xview_moveto, 1))
        BracketButton(where, "choose", size=9, command=self._choose_folder, bg=PANEL).grid(row=0, column=2)

        self.save_button = self.add_button("save the files", self.save_files, kind="accent", icon_name="save")
        self.add_button("copy", self.copy_shown, icon_name="copy")
        self.add_button("close", self.cancel, kind="ghost")
        tk.Label(self.buttons, text="the runtime file next to it gives the program gublan's built-in commands.",
                 bg=PANEL, fg=DIM, font=ui_font(8)).pack(side="left")
        self.after(30, self.translate)

    def _code_box(self, parent):
        frame = tk.Frame(parent, bg=EDITOR_BG, highlightthickness=1, highlightbackground=BORDER)
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, bg=EDITOR_BG, fg=TEXT, relief="flat", borderwidth=0, highlightthickness=0,
                       font=mono_font(10), wrap="none", padx=px(8), pady=px(6), selectbackground=SELECT,
                       inactiveselectbackground=SELECT, state="disabled")
        bar = scrollbar(frame, "vertical", text.yview)
        hbar = scrollbar(frame, "horizontal", text.xview)
        text.configure(yscrollcommand=bar.set, xscrollcommand=hbar.set)
        hbar.pack(side="bottom", fill="x")
        bar.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        return text

    def _default_folder(self, language):
        return os.path.join(self.base_dir, "export", f"{self.program}_{language}")

    def translate(self):
        import gublantranslate
        language = self.language.get()
        self.settings["translate_language"] = language
        try:
            style = (self.settings or {}).get("game_style") if language == "javascript" else None
            self.result = gublantranslate.translate(self.source_code, language, name=self.program, style=style,
                                                    base_dir=self.base_dir)
        except gublantranslate.TranslateError as err:
            self.result = None
            self.status.configure(text="could not translate", fg=ERROR)
            self.notes.configure(text=lower(str(err)), fg=ERROR)
            highlight_foreign(self.preview, "", "#")
            self.save_button.set_enabled(False)
            return
        except Exception as err:  # noqa: BLE001 - a translator bug should be reported, not crash the studio
            self.result = None
            self.status.configure(text="could not translate", fg=ERROR)
            self.notes.configure(text=f"the translator hit a problem: {type(err).__name__}: {lower(str(err))}",
                                 fg=ERROR)
            self.save_button.set_enabled(False)
            return
        self.save_button.set_enabled(True)
        folder = self.folder.get().strip()
        if not folder or os.path.basename(folder) in {f"{self.program}_{other}" for other in self.COMMENTS}:
            self.folder.set(self._default_folder(language))
        self._file_buttons()
        self.show_file(self.result.main)
        result = self.result
        self.status.configure(text=f"{result.source_lines} gublan lines -> {result.output_lines} {language} lines",
                              fg=MOSS_LIGHT)
        how = gublantranslate.LANGUAGES[language]["how"].format(main=result.main)
        parts = [how + "."]
        if result.todos:
            parts.append(f"{plural(result.todos, 'line')} could not be translated (marked todo).")
        parts.extend(lower(note) for note in result.notes[:4])
        self.notes.configure(text="  ".join(parts), fg=NUMBER if result.todos else MUTED)

    def _file_buttons(self):
        for child in self.file_tabs.winfo_children():
            child.destroy()
        names = list(self.result.files)
        Segmented(self.file_tabs, [(name, name) for name in names], self.shown_file, bg=PANEL, size=9,
                  command=lambda *_: self.show_file(self.shown_file.get())).pack(side="left")

    def show_file(self, name):
        if not self.result or name not in self.result.files:
            return
        self.shown_file.set(name)
        extension = os.path.splitext(name)[1]
        comment = {".py": "#", ".js": "//", ".lua": "--", ".html": "<!--"}.get(extension, "#")
        highlight_foreign(self.preview, self.result.files[name], comment)

    def _choose_folder(self):
        folder = filedialog.askdirectory(parent=self, title="save the translated program in",
                                         initialdir=self.base_dir)
        if folder:
            self.folder.set(os.path.join(folder, f"{self.program}_{self.language.get()}"))

    def copy_shown(self):
        if self.result:
            self.clipboard_clear()
            self.clipboard_append(self.result.files.get(self.shown_file.get(), self.result.text))
            self.status.configure(text="copied", fg=MOSS_LIGHT)

    def save_files(self):
        import gublantranslate
        if not self.result:
            return
        folder = self.folder.get().strip() or self._default_folder(self.language.get())
        try:
            written = gublantranslate.write_files(self.result, folder)
        except OSError as err:
            message(self, "export as another language", f"could not save the files: {lower(str(err))}", "error")
            return
        self.status.configure(text=f"saved {plural(len(written), 'file')}", fg=MOSS_LIGHT)
        from .panels import reveal
        reveal(os.path.join(folder, self.result.main))


# ----- ai helpers (mcp) ---------------------------------------------------------------------------------------------
# ----- live sessions -------------------------------------------------------------------------------------------
class LiveDialog(Dialog):
    """asks for your name (always) and, to join, the host's address and code."""

    def __init__(self, master, settings, host=True):
        super().__init__(master, "start a live session" if host else "join a live session")
        from . import collab
        self.collab = collab
        self.settings = settings
        self.host = host
        body = self.body
        about = ("people on the same network (the same wi-fi or cable) can join and type in your open programs "
                 "with you. you will get an address and a code to give them." if host else
                 "the host finds the address, port and code under tools > code together > how to join.")
        tk.Label(body, text=about, bg=PANEL, fg=MUTED, font=ui_font(9), justify="left", anchor="w",
                 wraplength=px(460)).pack(fill="x", pady=(0, px(10)))
        self.name = tk.StringVar(value=settings.get("live_name", ""))
        self.address = tk.StringVar(value=settings.get("live_address", ""))
        self.port = tk.StringVar(value=str(settings.get("live_port", collab.DEFAULT_PORT)))
        self.code = tk.StringVar(value="")
        first = self._field(body, "your name", self.name, "everyone sees this next to your cursor")
        if not host:
            self._field(body, "address", self.address, "like 192.168.1.20", mono=True)
            self._field(body, "code", self.code, "six letters and numbers", mono=True)
        self._field(body, "port", self.port, "47800 unless the host changed it", mono=True, width=8)
        if host:
            self.share_files = tk.BooleanVar(value=bool(settings.get("live_share_files", True)))
            Toggle(body, "let people use pictures, sounds and included files from my program's folder",
                   self.share_files, bg=PANEL).pack(anchor="w", pady=(px(8), 0))
            tk.Label(body, text="windows may ask if gublan studio can use the network the first time. allow it "
                                "on private networks so people can reach you.",
                     bg=PANEL, fg=DIM, font=ui_font(8), justify="left", anchor="w",
                     wraplength=px(460)).pack(fill="x", pady=(px(8), 0))
        self.problem = tk.Label(body, text="", bg=PANEL, fg=ERROR, font=ui_font(9), anchor="w", justify="left",
                                wraplength=px(460))
        self.problem.pack(fill="x", pady=(px(8), 0))
        self.add_button("start" if host else "join", self.ok, kind="accent")
        self.add_button("cancel", self.cancel)
        self.bind("<Return>", lambda _e: self.ok())
        self.after(50, first.focus_set)

    def _field(self, parent, label_text, variable, hint, mono=False, width=30):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=px(3))
        tk.Label(row, text=label_text, bg=PANEL, fg=TEXT, font=ui_font(10), width=10, anchor="w").pack(side="left")
        entry = flat_entry(row, variable, width=width, mono=mono)
        entry.pack(side="left", fill="x", expand=width >= 20)
        tk.Label(row, text=hint, bg=PANEL, fg=DIM, font=ui_font(8)).pack(side="left", padx=(px(8), 0))
        return entry

    def ok(self):
        name = self.collab.clean_name(self.name.get())
        if not name:
            self.problem.configure(text="type your name first. everyone in the session sees it.")
            return
        try:
            port = int(self.port.get().strip())
            if not 1024 <= port <= 65535:
                raise ValueError
        except ValueError:
            self.problem.configure(text="the port is a number from 1024 to 65535.")
            return
        answer = {"name": name, "port": port}
        if not self.host:
            address = self.address.get().strip()
            code = self.code.get().strip().lower()
            if not address:
                self.problem.configure(text="type the host's address.")
                return
            if len(code) != 6:
                self.problem.configure(text="the code is six letters and numbers long.")
                return
            answer.update(address=address, code=code)
            self.settings["live_address"] = address
        self.settings["live_name"] = name
        self.settings["live_port"] = port
        if self.host:
            self.settings["live_share_files"] = bool(self.share_files.get())
        config.save(self.settings)
        self.close(answer)


class McpDialog(Dialog):
    """show how to connect an ai helper (claude, copilot, cursor) to this project through gublan's mcp server."""

    TOOLS_TEXT = ("the helper can read and write files in the project, check code for problems, run programs (and "
                  "press keys or click in them), run tests, take screenshots of the game window, look up commands, "
                  "and turn code into or out of gublan. it can only touch files inside the project folder.")

    def __init__(self, master, folder, settings=None):
        super().__init__(master, "connect an ai helper", resizable=True)
        import gublanmcp
        self.gublanmcp = gublanmcp
        self.settings = settings if settings is not None else {}
        tk.Label(self.body, text=self.TOOLS_TEXT, bg=PANEL, fg=MUTED, font=ui_font(10), justify="left",
                 anchor="w", wraplength=px(700)).pack(fill="x")

        where = tk.Frame(self.body, bg=PANEL)
        where.pack(fill="x", pady=(px(12), px(8)))
        where.columnconfigure(1, weight=1)
        tk.Label(where, text="project", bg=PANEL, fg=MUTED, font=ui_font(10)).grid(row=0, column=0, sticky="w")
        self.folder = tk.StringVar(value=folder)
        entry = flat_entry(where, self.folder, width=40)
        entry.grid(row=0, column=1, sticky="ew", padx=px(10))
        self.folder.trace_add("write", lambda *_: self.refresh())
        BracketButton(where, "choose", size=9, command=self._choose_folder, bg=PANEL).grid(row=0, column=2)

        row = tk.Frame(self.body, bg=PANEL)
        row.pack(fill="x", pady=(0, px(6)))
        tk.Label(row, text="for", bg=PANEL, fg=MUTED, font=ui_font(10)).pack(side="left")
        names = list(gublanmcp.client_snippets(folder))
        chosen = self.settings.get("mcp_app", names[0])
        chosen = gublanmcp.OLD_APP_NAMES.get(chosen, chosen)
        self.app_name = tk.StringVar(value=chosen if chosen in names else names[0])
        Segmented(row, [(name, name) for name in names], self.app_name, bg=PANEL, size=9,
                  command=lambda *_: self.refresh()).pack(side="left", padx=px(10))
        self.where_label = tk.Label(self.body, text="", bg=PANEL, fg=DIM, font=ui_font(9), anchor="w")
        self.where_label.pack(fill="x")
        frame = tk.Frame(self.body, bg=EDITOR_BG, highlightthickness=1, highlightbackground=BORDER)
        frame.pack(fill="both", expand=True, pady=(px(4), 0))
        self.snippet = tk.Text(frame, bg=EDITOR_BG, fg=TEXT, relief="flat", borderwidth=0, highlightthickness=0,
                               font=mono_font(10), wrap="char", padx=px(8), pady=px(6), height=9,
                               selectbackground=SELECT, inactiveselectbackground=SELECT)
        self.snippet.pack(fill="both", expand=True)
        self.status = tk.Label(self.body, text="", bg=PANEL, fg=DIM, font=ui_font(9), anchor="w", justify="left",
                               wraplength=px(700))
        self.status.pack(fill="x", pady=(px(8), 0))

        self.add_button("close", self.cancel, kind="ghost")
        self.add_button("copy", self.copy, icon_name="copy")
        self.save_button = self.add_button("add it for me", self.save_project_file, kind="accent", icon_name="save")
        self.add_button("test it", self.test, side="left")
        self.refresh()

    def _choose_folder(self):
        folder = filedialog.askdirectory(parent=self, title="the project the ai helper works on",
                                         initialdir=self.folder.get() or None)
        if folder:
            self.folder.set(os.path.normpath(folder))

    def chosen_folder(self):
        return self.gublanmcp.clean_folder(self.folder.get()) or self.gublanmcp.default_folder()

    def refresh(self):
        name = self.app_name.get()
        self.settings["mcp_app"] = name
        where, text = self.gublanmcp.client_snippets(self.chosen_folder())[name]
        self.where_label.configure(text=where)
        self.snippet.configure(state="normal")
        self.snippet.delete("1.0", "end")
        self.snippet.insert("1.0", text)
        self.snippet.configure(state="disabled")
        in_project = name in ("claude code", "vs code")
        self.save_button.configure_text("save in the project" if in_project else f"add it to {name}")

    def copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.snippet.get("1.0", "end-1c"))
        self.status.configure(text="copied. paste it into the ai app's settings, then restart the app.",
                              fg=MOSS_LIGHT)

    def save_project_file(self):
        """add the server to the chosen app's settings (claude desktop, cursor) or the project's file."""
        folder = self.gublanmcp.clean_folder(self.folder.get())
        if not folder or not os.path.isdir(folder):
            self.status.configure(text="choose a project folder that exists first", fg=ERROR)
            return
        name = self.app_name.get()
        try:
            written = self.gublanmcp.install(name, folder)
        except (OSError, ValueError) as err:
            self.status.configure(text=f"could not save it: {lower(str(err))}", fg=ERROR)
            return
        files = ", ".join(written)
        if name in ("claude code", "vs code"):
            text = f"saved {files}. the ai app finds it when it opens this folder."
        else:
            text = (f"added gublan to {files} (the old file is kept as .bak). quit {name} completely (also from "
                    "the tray) and open it again.")
        self.status.configure(text=text, fg=MOSS_LIGHT)

    def test(self):
        folder = self.gublanmcp.clean_folder(self.folder.get())
        if not folder or not os.path.isdir(folder):
            self.status.configure(text="choose a project folder that exists first", fg=ERROR)
            return
        self.status.configure(text="starting the server...", fg=DIM)

        def work():
            try:
                tools = self.gublanmcp.self_test(folder)
                text, colour = f"it works: the server answered with {plural(len(tools), 'tool')} " \
                               f"({', '.join(tools)}).", MOSS_LIGHT
            except Exception as err:  # noqa: BLE001 - shown in the dialog
                text, colour = f"the server did not start: {lower(str(err))}", ERROR
            try:
                from_thread(self, lambda: self.status.configure(text=text, fg=colour))
            except (tk.TclError, RuntimeError):
                pass

        threading.Thread(target=work, daemon=True).start()


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
            from_thread(self, self._tool_checked, text, ok, broken)
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
                from_thread(self, self._installed, output, failed)
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
            from_thread(self, lambda: self.log.configure(text=lower(status), fg=MUTED))
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
        self.preview_label = tk.Label(side, bg=theme.CODE_BG)
        self.preview_label.pack(anchor="w", pady=px(4))
        self.preview_big = tk.Label(side, bg=theme.CODE_BG)
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
                    fill = theme.PANEL_ALT if (x + y) % 2 else theme.FIELD_BG
                outline = theme.BORDER if self.grid_on.get() and cell >= 6 else fill
                canvas.create_rectangle(x * cell, y * cell, (x + 1) * cell, (y + 1) * cell, fill=fill,
                                        outline=outline)
        canvas.create_rectangle(0, 0, cell * self.size, cell * self.size, outline=MOSS_DARK)
        self.after_idle(self.update_preview)

    def update_preview(self):
        size = self.size
        image = tk.PhotoImage(width=size, height=size)
        rows = []
        for row in self.pixels:
            rows.append("{" + " ".join("#%02x%02x%02x" % pixel[:3] if pixel[3] else theme.CODE_BG for pixel in row) + "}")
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
