"""look and feel for gublan studio.

three rules hold everywhere in the studio:
  - no rounded corners: every window asks windows 11 not to round it, and every widget is square
  - no capitals: every label, title and message is lowercase
  - the soft green and soft black palette below, nothing else
"""

import ctypes
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# ----- palette ---------------------------------------------------------------
BG = "#141414"
PANEL = "#1c1c1c"
PANEL_ALT = "#262626"
EDITOR_BG = "#171717"
TEXT = "#e5e5e5"
MUTED = "#aaaaaa"
DIM = "#6f6f6f"
MOSS = "#647f4a"
MOSS_LIGHT = "#94b66c"
MOSS_DARK = "#3c4c2d"
NUMBER = "#d7bd75"
ERROR = "#e16b6b"
ACTIVE_LINE = "#1f251d"
ERROR_LINE = "#332222"
DEBUG_LINE = "#293328"
BORDER = "#2c2c2c"
HOVER = "#232323"
SELECT = "#2f3d27"
SELECT_TEXT = "#f0f5ea"

SYNTAX = {
    "command": MOSS_LIGHT,
    "flow": "#b9cf8f",
    "string": "#a8c49a",
    "number": NUMBER,
    "comment": "#6b7266",
    "brace": "#8fb3a0",
    "function": "#cfe0b0",
    "keyword": "#c2c79a",
    "color": "#b0c48a",
    "operator": "#9aa596",
}

# block and category colours: all greens and olives so the palette stays soft green and black
CATEGORY_COLORS = {
    "basics": "#94b66c",
    "control": "#b9cf8f",
    "functions": "#7fa36a",
    "lists and maps": "#6f9a7d",
    "display": "#a3b08a",
    "2d": "#8fb08a",
    "3d": "#7a9a8f",
    "objects": "#9db07a",
    "input": "#c2c79a",
    "sound": "#88a878",
    "web": "#8a9a80",
    "saving": "#a8b27c",
    "discord": "#8f9cc4",
    "comments": "#6b7266",
    "code": "#7d8a74",
}

# ----- fonts -------------------------------------------------------------------
UI_FAMILY = "Segoe UI"
MONO_FAMILY = "Consolas"
ICON_FAMILY = "Segoe MDL2 Assets"
_SCALE = 1.0

ICONS = {
    "run": "", "stop": "", "pause": "", "step": "", "save": "",
    "open": "", "new": "", "export": "", "convert": "", "blocks": "",
    "code": "", "settings": "", "help": "", "files": "", "outline": "",
    "assets": "", "search": "", "close": "", "check": "", "warning": "",
    "error": "", "info": "", "play": "", "folder": "", "file": "",
    "image": "", "sound": "", "chevron": "", "down": "", "up": "",
    "brush": "", "trash": "", "add": "", "copy": "", "palette": "",
    "bug": "", "learn": "", "game": "", "dot": "", "refresh": "",
    "menu": "", "more": "", "back": "", "breakpoint": "",
}


def pick_fonts(root):
    """choose the best fonts installed on this computer."""
    global UI_FAMILY, MONO_FAMILY, ICON_FAMILY, _SCALE
    families = set(tkfont.families(root))
    for name in ("Segoe UI Variable Text", "Segoe UI", "Tahoma", "DejaVu Sans"):
        if name in families:
            UI_FAMILY = name
            break
    for name in ("Cascadia Mono", "Cascadia Code", "JetBrains Mono", "Consolas", "Courier New"):
        if name in families:
            MONO_FAMILY = name
            break
    for name in ("Segoe Fluent Icons", "Segoe MDL2 Assets"):
        if name in families:
            ICON_FAMILY = name
            break
    else:
        ICON_FAMILY = ""
    try:
        _SCALE = max(1.0, root.winfo_fpixels("1i") / 96.0)
    except tk.TclError:
        _SCALE = 1.0


def px(value):
    """scale a pixel size for high dpi screens."""
    return int(round(value * _SCALE))


def ui_font(size=10, weight="normal"):
    return (UI_FAMILY, size, weight)


def mono_font(size=11, weight="normal"):
    return (MONO_FAMILY, size, weight)


def icon_font(size=11):
    return (ICON_FAMILY or UI_FAMILY, size)


def icon(name, fallback=""):
    if not ICON_FAMILY:
        return fallback
    return ICONS.get(name, fallback)


# ----- windows -------------------------------------------------------------------
def enable_dpi_awareness():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _colorref(hex_color):
    hex_color = hex_color.lstrip("#")
    red, green, blue = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return blue << 16 | green << 8 | red


def square_window(window, caption=BG, border=MOSS_DARK, text=TEXT):
    """ask windows 11 for square corners and a soft black title bar."""
    if sys.platform != "win32":
        return
    try:
        window.update_idletasks()
        handle = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        dwm = ctypes.windll.dwmapi

        def setattr_(attribute, value):
            data = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(handle, attribute, ctypes.byref(data), ctypes.sizeof(data))

        setattr_(20, 1)  # dark mode title bar
        setattr_(33, 1)  # DWMWCP_DONOTROUND: square corners
        setattr_(34, _colorref(border))
        setattr_(35, _colorref(caption))
        setattr_(36, _colorref(text))
    except (AttributeError, OSError, tk.TclError):
        pass


def lower(text):
    return str(text).lower()


def plural(count, word, many=None):
    """'1 file', '3 files'."""
    return f"{count} {word if count == 1 else (many or word + 's')}"


# ----- ttk styles ----------------------------------------------------------------
def setup_styles(root):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(".", background=PANEL, foreground=TEXT, fieldbackground=PANEL_ALT, bordercolor=BORDER,
                    lightcolor=PANEL, darkcolor=PANEL, troughcolor=PANEL, focuscolor=MOSS,
                    selectbackground=SELECT, selectforeground=SELECT_TEXT, font=ui_font(10), relief="flat")
    for orient in ("Vertical", "Horizontal"):
        name = f"Flat.{orient}.TScrollbar"
        style.layout(name, [(f"{orient}.Scrollbar.trough", {"sticky": "nswe", "children": [
            (f"{orient}.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
        style.configure(name, background="#333333", troughcolor=PANEL, bordercolor=PANEL, lightcolor="#333333",
                        darkcolor="#333333", arrowsize=px(10), gripcount=0, relief="flat", borderwidth=0)
        style.map(name, background=[("active", "#4a4a4a"), ("pressed", MOSS)],
                  lightcolor=[("active", "#4a4a4a")], darkcolor=[("active", "#4a4a4a")])
    style.configure("Flat.Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, borderwidth=0,
                    rowheight=px(24), font=ui_font(10), relief="flat")
    style.map("Flat.Treeview", background=[("selected", SELECT)], foreground=[("selected", SELECT_TEXT)])
    style.configure("Flat.Treeview.Heading", background=PANEL_ALT, foreground=MUTED, relief="flat",
                    borderwidth=0, font=ui_font(9))
    style.map("Flat.Treeview.Heading", background=[("active", HOVER)])
    style.layout("Flat.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure("Flat.Horizontal.TProgressbar", troughcolor=PANEL_ALT, background=MOSS_LIGHT,
                    bordercolor=PANEL_ALT, lightcolor=MOSS_LIGHT, darkcolor=MOSS, thickness=px(6))
    style.configure("Flat.TCombobox", fieldbackground=PANEL_ALT, background=PANEL_ALT, foreground=TEXT,
                    arrowcolor=MUTED, bordercolor=BORDER, lightcolor=PANEL_ALT, darkcolor=PANEL_ALT)
    root.option_add("*TCombobox*Listbox.background", PANEL_ALT)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", SELECT)
    root.option_add("*Font", ui_font(10))
    return style


def scrollbar(parent, orient="vertical", command=None):
    name = "Flat.Vertical.TScrollbar" if orient == "vertical" else "Flat.Horizontal.TScrollbar"
    return ttk.Scrollbar(parent, orient=orient, command=command, style=name)


# ----- widgets ---------------------------------------------------------------------
class BracketButton(tk.Canvas):
    """a flat square button with the moss corner-bracket accent.

    kinds: "normal", "accent" (filled moss), "ghost" (no background), "danger".
    """

    def __init__(self, parent, text="", command=None, icon_name=None, kind="normal", size=10, width=None,
                 tooltip=None, pad_x=12, pad_y=6, bg=None):
        self.parent_bg = bg or _bg_of(parent)
        super().__init__(parent, highlightthickness=0, bd=0, bg=self.parent_bg, cursor="hand2",
                         takefocus=1)
        self.command = command
        self.kind = kind
        self.text = lower(text)
        self.icon_text = icon(icon_name) if icon_name else ""
        self.font = ui_font(size)
        self.icon_font = icon_font(size + 1)
        self.pad_x, self.pad_y = px(pad_x), px(pad_y)
        self.fixed_width = px(width) if width else None
        self.hover = False
        self.pressed = False
        self.enabled = True
        self.checked = False
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<KeyPress-space>", lambda _e: self.invoke())
        self.bind("<KeyPress-Return>", lambda _e: self.invoke())
        self.bind("<FocusIn>", lambda _e: self.draw())
        self.bind("<FocusOut>", lambda _e: self.draw())
        if tooltip:
            Tooltip(self, tooltip)
        self._measure()
        self.draw()

    def _measure(self):
        measure = tkfont.Font(font=self.font)
        width = measure.measure(self.text) if self.text else 0
        if self.icon_text:
            width += tkfont.Font(font=self.icon_font).measure(self.icon_text) + (px(7) if self.text else 0)
        height = measure.metrics("linespace")
        self.configure(width=self.fixed_width or width + self.pad_x * 2, height=height + self.pad_y * 2)

    def configure_text(self, text=None, icon_name=None):
        if text is not None:
            self.text = lower(text)
        if icon_name is not None:
            self.icon_text = icon(icon_name)
        self._measure()
        self.draw()

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        self.configure(cursor="hand2" if self.enabled else "arrow")
        self.draw()

    def set_checked(self, checked):
        self.checked = bool(checked)
        self.draw()

    def colors(self):
        if not self.enabled:
            return (PANEL if self.kind != "ghost" else self.parent_bg), DIM, BORDER
        if self.kind == "accent":
            fill = MOSS_LIGHT if self.hover else MOSS
            return fill, "#10140c" if self.hover else SELECT_TEXT, MOSS_LIGHT
        if self.kind == "danger":
            fill = ERROR_LINE if self.hover else PANEL_ALT
            return fill, ERROR if self.hover else TEXT, ERROR
        if self.kind == "ghost":
            fill = HOVER if self.hover or self.checked else self.parent_bg
            return fill, (MOSS_LIGHT if self.checked else TEXT if self.hover else MUTED), MOSS
        fill = "#2e2e2e" if self.hover else PANEL_ALT
        if self.checked:
            fill = SELECT
        return fill, TEXT, MOSS_LIGHT if self.hover or self.checked else MOSS

    def draw(self):
        self.delete("all")
        width, height = int(self["width"]), int(self["height"])
        fill, foreground, accent = self.colors()
        if self.pressed and self.enabled:
            fill = MOSS_DARK if self.kind != "accent" else MOSS
        self.create_rectangle(0, 0, width, height, fill=fill, outline=fill)
        if self.kind != "ghost" or self.hover or self.checked or self.focus_get() is self:
            arm = px(5)
            line = px(1) if self.kind != "accent" else 0
            if line:
                for x, y, dx, dy in ((0, 0, 1, 1), (width - 1, 0, -1, 1), (0, height - 1, 1, -1),
                                     (width - 1, height - 1, -1, -1)):
                    self.create_line(x, y, x + dx * arm, y, fill=accent, width=line)
                    self.create_line(x, y, x, y + dy * arm, fill=accent, width=line)
        cursor_x = width / 2
        if self.icon_text and self.text:
            icon_width = tkfont.Font(font=self.icon_font).measure(self.icon_text)
            text_width = tkfont.Font(font=self.font).measure(self.text)
            start = (width - icon_width - text_width - px(7)) / 2
            self.create_text(start, height / 2 + px(1), text=self.icon_text, font=self.icon_font, fill=foreground,
                             anchor="w")
            self.create_text(start + icon_width + px(7), height / 2, text=self.text, font=self.font,
                             fill=foreground, anchor="w")
        elif self.icon_text:
            self.create_text(cursor_x, height / 2 + px(1), text=self.icon_text, font=self.icon_font,
                             fill=foreground)
        else:
            self.create_text(cursor_x, height / 2, text=self.text, font=self.font, fill=foreground)

    def _enter(self, _event):
        self.hover = True
        self.draw()

    def _leave(self, _event):
        self.hover = False
        self.pressed = False
        self.draw()

    def _press(self, _event):
        if self.enabled:
            self.pressed = True
            self.draw()

    def _release(self, event):
        was_pressed = self.pressed
        self.pressed = False
        self.draw()
        inside = 0 <= event.x <= int(self["width"]) and 0 <= event.y <= int(self["height"])
        if was_pressed and inside:
            self.invoke()

    def invoke(self):
        if self.enabled and self.command:
            self.command()


class Toggle(tk.Frame):
    """a square checkbox with a lowercase label."""

    def __init__(self, parent, text, variable=None, command=None, bg=None):
        bg = bg or _bg_of(parent)
        super().__init__(parent, bg=bg)
        self.variable = variable or tk.BooleanVar(value=False)
        self.command = command
        self.box = tk.Canvas(self, width=px(16), height=px(16), bg=bg, highlightthickness=0, cursor="hand2")
        self.box.pack(side="left")
        self.label = tk.Label(self, text=lower(text), bg=bg, fg=TEXT, font=ui_font(10), cursor="hand2")
        self.label.pack(side="left", padx=(px(8), 0))
        for widget in (self, self.box, self.label):
            widget.bind("<Button-1>", self.flip)
        self.variable.trace_add("write", lambda *_: self.draw())
        self.draw()

    def flip(self, _event=None):
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()

    def draw(self):
        self.box.delete("all")
        size = px(16)
        on = bool(self.variable.get())
        self.box.create_rectangle(1, 1, size - 1, size - 1, outline=MOSS_LIGHT if on else "#4a4a4a",
                                  fill=MOSS if on else PANEL_ALT)
        if on:
            self.box.create_line(px(4), px(8), px(7), px(11), px(12), px(5), fill=SELECT_TEXT, width=px(2))


class Segmented(tk.Frame):
    """square toggle buttons standing in for radio buttons."""

    def __init__(self, parent, options, variable, command=None, bg=None, size=10):
        bg = bg or _bg_of(parent)
        super().__init__(parent, bg=bg)
        self.variable = variable
        self.command = command
        self.buttons = {}
        for value, label in options:
            button = BracketButton(self, label, command=lambda v=value: self.choose(v), kind="normal", size=size,
                                   bg=bg, pad_x=10, pad_y=5)
            button.pack(side="left", padx=(0, px(4)))
            self.buttons[value] = button
        self.variable.trace_add("write", lambda *_: self.refresh())
        self.refresh()

    def choose(self, value):
        self.variable.set(value)
        if self.command:
            self.command(value)

    def refresh(self):
        current = self.variable.get()
        for value, button in self.buttons.items():
            button.set_checked(value == current)


def flat_entry(parent, textvariable=None, width=20, mono=False, bg=PANEL_ALT):
    entry = tk.Entry(parent, textvariable=textvariable, width=width, bg=bg, fg=TEXT, insertbackground=TEXT,
                     relief="flat", highlightthickness=1, highlightbackground=BORDER, highlightcolor=MOSS,
                     selectbackground=SELECT, selectforeground=SELECT_TEXT, bd=px(4),
                     font=mono_font(10) if mono else ui_font(10))
    return entry


def label(parent, text, size=10, color=TEXT, weight="normal", bg=None, **kwargs):
    return tk.Label(parent, text=lower(text), bg=bg or _bg_of(parent), fg=color, font=ui_font(size, weight),
                    **kwargs)


def _bg_of(widget):
    try:
        return widget.cget("bg")
    except tk.TclError:
        return PANEL


class Tooltip:
    """a small square hint that appears when the pointer rests on a widget."""

    def __init__(self, widget, text, delay=550):
        self.widget = widget
        self.text = lower(text)
        self.delay = delay
        self.window = None
        self.job = None
        widget.bind("<Enter>", self.schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def schedule(self, _event=None):
        self.cancel()
        self.job = self.widget.after(self.delay, self.show)

    def cancel(self):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None

    def show(self):
        if self.window or not self.text:
            return
        x = self.widget.winfo_rootx() + px(4)
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + px(6)
        self.window = popup_window(self.widget)
        frame = tk.Frame(self.window, bg=PANEL_ALT, highlightthickness=1, highlightbackground=MOSS_DARK)
        frame.pack()
        tk.Label(frame, text=self.text, bg=PANEL_ALT, fg=TEXT, font=ui_font(9), justify="left",
                 wraplength=px(360)).pack(padx=px(8), pady=px(5))
        self.window.geometry(f"+{x}+{y}")
        self.window.deiconify()

    def hide(self, _event=None):
        self.cancel()
        if self.window:
            self.window.destroy()
            self.window = None


def popup_window(master):
    window = tk.Toplevel(master)
    window.withdraw()
    window.overrideredirect(True)
    window.configure(bg=PANEL_ALT)
    try:
        window.attributes("-topmost", True)
    except tk.TclError:
        pass
    square_window(window, border=MOSS_DARK)
    return window


class PopupMenu:
    """a square, lowercase replacement for native menus (which windows 11 rounds).

    items: (label, command), (label, command, shortcut), {"label", "command", "shortcut", "checked",
    "enabled"}, "-" for a separator, or (label, [items]) for a submenu.
    """

    active = None

    def __init__(self, master, items, on_close=None):
        self.master = master
        self.items = [self._normalise(item) for item in items]
        self.on_close = on_close
        self.window = None
        self.rows = []
        self.index = -1
        self.child = None
        self.child_index = -1
        self.parent_menu = None
        self._global = None

    @staticmethod
    def _normalise(item):
        if item == "-" or item is None:
            return None
        if isinstance(item, dict):
            return item
        if len(item) == 2 and isinstance(item[1], list):
            return {"label": item[0], "submenu": item[1]}
        return {"label": item[0], "command": item[1], "shortcut": item[2] if len(item) > 2 else ""}

    def post(self, x, y):
        if PopupMenu.active and self.parent_menu is None:
            PopupMenu.active.close()
        if self.parent_menu is None:
            PopupMenu.active = self
        self.window = popup_window(self.master)
        frame = tk.Frame(self.window, bg=PANEL_ALT, highlightthickness=1, highlightbackground=MOSS_DARK)
        frame.pack(fill="both", expand=True)
        for item in self.items:
            if item is None:
                tk.Frame(frame, bg=BORDER, height=1).pack(fill="x", padx=px(8), pady=px(4))
                continue
            row = tk.Frame(frame, bg=PANEL_ALT, cursor="hand2")
            row.pack(fill="x")
            enabled = item.get("enabled", True)
            mark = icon("check", "x") if item.get("checked") else ""
            check = tk.Label(row, text=mark, width=2, bg=PANEL_ALT, fg=MOSS_LIGHT, font=icon_font(9))
            check.pack(side="left", padx=(px(6), 0))
            name = tk.Label(row, text=lower(item["label"]), bg=PANEL_ALT, fg=TEXT if enabled else DIM,
                            font=ui_font(10), anchor="w")
            name.pack(side="left", fill="x", expand=True, padx=(px(2), px(24)), pady=px(5))
            hint_text = lower(item.get("shortcut", "")) if "submenu" not in item else icon("chevron", ">")
            hint = tk.Label(row, text=hint_text, bg=PANEL_ALT, fg=DIM,
                            font=ui_font(9) if "submenu" not in item else icon_font(8))
            hint.pack(side="right", padx=(0, px(12)))
            entry = (row, (row, check, name, hint), item)
            self.rows.append(entry)
            for widget in entry[1]:
                widget.bind("<Enter>", lambda _e, i=len(self.rows) - 1: self.highlight(i))
                widget.bind("<ButtonRelease-1>", lambda _e, i=len(self.rows) - 1: self.activate(i))
        self.window.update_idletasks()
        width = max(self.window.winfo_reqwidth(), px(200))
        height = self.window.winfo_reqheight()
        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()
        x = min(x, screen_w - width - 4)
        y = min(y, screen_h - height - 4)
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.deiconify()
        self.window.lift()
        if self.parent_menu is None:
            self.window.focus_force()
            self.window.bind("<FocusOut>", self._focus_out)
            self.window.bind("<Escape>", lambda _e: self.close())
            self.window.bind("<Down>", lambda _e: self.move(1))
            self.window.bind("<Up>", lambda _e: self.move(-1))
            self.window.bind("<Return>", lambda _e: (self.child or self).activate((self.child or self).index))
            self.window.bind("<Right>", lambda _e: self.open_child())
            self.window.bind("<Left>", lambda _e: self.close_child())
            self._global = None
            # bind later so the click that opened the menu doesn't close it straight away
            self.window.after(80, self._bind_outside_click)
        return self

    def _bind_outside_click(self):
        if self.window:
            self._global = self.master.winfo_toplevel().bind("<Button-1>", lambda _e: self.close(), add="+")

    def _focus_out(self, _event):
        self.window.after(60, self._check_focus)

    def _check_focus(self):
        if not self.window:
            return
        focused = self.window.focus_get()
        menus = [self]
        child = self.child
        while child:
            menus.append(child)
            child = child.child
        if focused is None or not any(menu.window and str(focused).startswith(str(menu.window)) for menu in menus):
            self.close()

    def highlight(self, index):
        if not self.rows:
            return
        self.index = index % len(self.rows)
        for number, (row, widgets, item) in enumerate(self.rows):
            on = number == self.index and item.get("enabled", True)
            for widget in widgets:
                widget.configure(bg=SELECT if on else PANEL_ALT)
        item = self.rows[self.index][2]
        if self.child and self.child_index != self.index:
            self.close_child()
        if "submenu" in item and not self.child:
            self.window.after(180, lambda i=self.index: self.index == i and self.open_child())

    def move(self, step):
        target = self.child if self.child else self
        if target.rows:
            target.highlight(target.index + step if target.index >= 0 else 0)

    def open_child(self):
        if self.index < 0 or self.child:
            return
        item = self.rows[self.index][2]
        if "submenu" not in item:
            return
        row = self.rows[self.index][0]
        self.child = PopupMenu(self.master, item["submenu"])
        self.child.parent_menu = self
        self.child_index = self.index
        self.child.post(row.winfo_rootx() + row.winfo_width(), row.winfo_rooty() - px(1))

    def close_child(self):
        if self.child:
            self.child.close()
            self.child = None

    def activate(self, index):
        if index < 0 or index >= len(self.rows):
            return
        item = self.rows[index][2]
        if not item.get("enabled", True):
            return
        if "submenu" in item:
            self.open_child()
            return
        command = item.get("command")
        root = self
        while root.parent_menu:
            root = root.parent_menu
        root.close()
        if command:
            self.master.after(10, command)

    def close(self):
        self.close_child()
        if self.window:
            try:
                if self.parent_menu is None and self._global:
                    self.master.winfo_toplevel().unbind("<Button-1>", self._global)
            except (tk.TclError, AttributeError):
                pass
            self.window.destroy()
            self.window = None
        if PopupMenu.active is self:
            PopupMenu.active = None
            if self.on_close:
                self.on_close()


def show_menu(widget, items, x=None, y=None, on_close=None):
    if x is None:
        x = widget.winfo_rootx()
        y = widget.winfo_rooty() + widget.winfo_height()
    return PopupMenu(widget, items, on_close=on_close).post(x, y)


class ScrollFrame(tk.Frame):
    """a frame whose contents scroll vertically with the mouse wheel."""

    def __init__(self, parent, bg=PANEL):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.bar = scrollbar(self, "vertical", self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.window = self.canvas.create_window(0, 0, anchor="nw", window=self.inner)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.bind_wheel(self.canvas)
        self.bind_wheel(self.inner)

    def bind_wheel(self, widget):
        widget.bind("<MouseWheel>", self._wheel, add="+")

    def bind_tree(self, widget):
        self.bind_wheel(widget)
        for child in widget.winfo_children():
            self.bind_tree(child)

    def _wheel(self, event):
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(int(-event.delta / 120) * 3, "units")
        return "break"

    def to_top(self):
        self.canvas.yview_moveto(0)
