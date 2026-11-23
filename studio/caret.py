"""motion inside the code editor: a smooth caret, typing effects, line flashes and smooth scrolling.

tk's own text cursor can only blink, so the editor hides it and draws its own on a tiny canvas that sits
on top of the text. the canvas glides to where the cursor goes, fades instead of blinking, and can be a
line, a block or an underline. typed letters fade in (or glow, or settle from a bright ink) using a small
pool of text tags that one ticker animates.
"""

import math
import time
import tkinter as tk

from . import theme

CARET_STYLES = ("line", "block", "underline")
CARET_BLINKS = ("fade", "blink", "solid")
TYPING_EFFECTS = ("fade", "ink", "glow", "off")


def _blink_amount(kind, seconds):
    """how visible the caret is (0 to 1) this long after it last moved."""
    if kind == "solid" or seconds < 0.5:
        return 1.0
    if kind == "blink":
        return 1.0 if (seconds - 0.5) % 1.06 >= 0.53 else 0.0
    phase = (seconds - 0.5) % 1.1
    if phase < 0.18:
        return 0.5 + 0.5 * math.cos(phase / 0.18 * math.pi)
    if phase < 0.5:
        return 0.0
    if phase < 0.68:
        return 0.5 - 0.5 * math.cos((phase - 0.5) / 0.18 * math.pi)
    return 1.0


class SmoothCaret:
    """the editor's own text cursor."""

    def __init__(self, editor):
        self.editor = editor
        self.text = editor.text
        self.canvas = tk.Canvas(self.text, highlightthickness=0, bd=0, width=1, height=1, cursor="xterm",
                                bg=theme.MOSS_LIGHT, takefocus=0)
        self.style = "line"
        self.motion = "smooth"
        self.blink = "fade"
        self.width = 2
        self.enabled = True
        self.current = None  # (x, y, w, h) as drawn
        self.start = None
        self.target = None
        self.glide_started = 0.0
        self.glide_time = 0.085
        self.moved_at = time.perf_counter()
        self.focused = False
        self.shown = False
        self.job = None
        self.last_amount = None
        for sequence in ("<Button-1>", "<B1-Motion>", "<ButtonRelease-1>", "<Double-Button-1>",
                         "<Triple-Button-1>", "<Button-3>", "<Shift-Button-1>"):
            self.canvas.bind(sequence, lambda event, s=sequence: self._forward(event, s))
        self.canvas.bind("<MouseWheel>", self._forward_wheel)
        self.text.bind("<FocusIn>", lambda _e: self._focus(True), add="+")
        self.text.bind("<FocusOut>", lambda _e: self._focus(False), add="+")
        self.text.bind("<Configure>", lambda _e: self.update(animate=False), add="+")

    # ----- settings --------------------------------------------------------------------------------------
    def apply(self, settings):
        style = str(settings.get("caret_style") or ("block" if settings.get("block_cursor") else "line"))
        self.style = style if style in CARET_STYLES else "line"
        self.motion = "smooth" if settings.get("caret_motion", "smooth") == "smooth" else "instant"
        blink = str(settings.get("caret_blink", "fade"))
        self.blink = blink if blink in CARET_BLINKS else "fade"
        try:
            self.width = max(1, min(4, int(settings.get("caret_width", 2))))
        except (TypeError, ValueError):
            self.width = 2
        self.enabled = bool(settings.get("smooth_caret", True))
        if self.enabled:
            # hide tk's own cursor: this one is drawn instead
            self.text.configure(insertwidth=0, insertofftime=0, blockcursor=False)
        else:
            self.canvas.place_forget()
            self.shown = False
            off = 0 if self.blink == "solid" else 420
            self.text.configure(insertwidth=theme.px(self.width), insertofftime=off, insertontime=640,
                                blockcursor=self.style == "block")
        self.current = None
        self.update(animate=False)

    # ----- events ----------------------------------------------------------------------------------------
    def _focus(self, focused):
        self.focused = focused
        self.moved_at = time.perf_counter()
        self.update(animate=False)

    def _forward(self, event, sequence):
        x = event.x + self.canvas.winfo_x()
        y = event.y + self.canvas.winfo_y()
        try:
            self.text.event_generate(sequence, x=x, y=y, state=event.state)
        except tk.TclError:
            pass
        return "break"

    def _forward_wheel(self, event):
        try:
            self.text.event_generate("<MouseWheel>", delta=event.delta, x=event.x + self.canvas.winfo_x(),
                                     y=event.y + self.canvas.winfo_y(), state=event.state)
        except tk.TclError:
            pass
        return "break"

    # ----- where it goes ---------------------------------------------------------------------------------
    def _box(self):
        """(x, y, w, h) of the cursor inside the text widget, or None when it is out of view."""
        text = self.text
        try:
            box = text.bbox("insert")
        except tk.TclError:
            return None
        if not box:
            return None
        x, y, w, h = box
        if w <= 1 or text.get("insert") in ("\n", "\t", ""):
            w = max(w if text.get("insert") == "\t" else 0, self.editor.font.measure("0"))
        return x, y, w, h

    def update(self, animate=True):
        """call when the cursor may have moved, the text scrolled or the font changed."""
        if not self.enabled:
            return
        self.moved_at = time.perf_counter()
        target = self._box() if self.focused else None
        if target is None:
            self.target = None
            self._hide()
            return
        glide = animate and self.motion == "smooth" and theme.MOTION and self.current is not None
        if glide and self.current != target:
            distance = abs(target[0] - self.current[0]) + abs(target[1] - self.current[1])
            self.start = self.current
            self.glide_started = time.perf_counter()
            # long jumps (clicks, page down) move a little slower so the eye can follow
            self.glide_time = (0.07 if distance < 40 else 0.12) * theme.SPEED
        else:
            self.start = None
            self.current = target
        self.target = target
        self.last_amount = None
        self._draw()
        self._run()

    # ----- drawing -----------------------------------------------------------------------------------------
    def _line_bg(self):
        editor = self.editor
        if self.text.tag_ranges("sel"):
            return theme.EDITOR_BG
        if editor.settings.get("highlight_line", True):
            return theme.ACTIVE_LINE
        return theme.EDITOR_BG

    def _hide(self):
        if self.shown:
            self.canvas.place_forget()
            self.shown = False

    def _draw(self, amount=1.0):
        if self.current is None:
            self._hide()
            return
        x, y, w, h = self.current
        line_width = theme.px(self.width)
        color = theme.MOSS_LIGHT
        if self.style == "line":
            box = (x - line_width // 2, y, line_width, h)
        elif self.style == "underline":
            box = (x, y + h - line_width, w, line_width)
        else:
            box = (x, y, w, h)
        if amount <= 0.02:
            self._hide()
            return
        canvas = self.canvas
        shade = theme.mix(self._line_bg(), color, amount)
        canvas.configure(width=max(1, int(box[2])), height=max(1, int(box[3])))
        if self.style == "block":
            canvas.delete("all")
            canvas.configure(bg=shade)
            char = self.text.get("insert")
            if char not in ("\n", "\t", ""):
                canvas.create_text(1, box[3] // 2, text=char, anchor="w", font=self.editor.font,
                                   fill=theme.mix(theme.TEXT, theme.EDITOR_BG, amount))
        else:
            canvas.configure(bg=shade)
        canvas.place(x=int(box[0]), y=int(box[1]))
        if not self.shown:
            canvas.tk.call("raise", str(canvas))  # canvas.lift() means raising a drawing item
            self.shown = True

    def _run(self):
        if self.job is None and self.enabled:
            self.job = self.text.after(16, self._tick)

    def _tick(self):
        self.job = None
        if not self.enabled or self.target is None or not self.focused:
            return
        try:
            if not self.text.winfo_exists():
                return
        except tk.TclError:
            return
        now = time.perf_counter()
        busy = False
        if self.start is not None:
            progress = min(1.0, (now - self.glide_started) / max(0.001, self.glide_time))
            eased = theme.ease_out(progress)
            self.current = tuple(a + (b - a) * eased for a, b in zip(self.start, self.target))
            if progress >= 1.0:
                self.start = None
                self.current = self.target
            busy = True
        amount = _blink_amount(self.blink, now - self.moved_at) if theme.MOTION or self.blink != "fade" else 1.0
        if busy or amount != self.last_amount:
            self.last_amount = amount
            try:
                self._draw(amount)
            except tk.TclError:
                return
        delay = 16 if busy or 0.0 < amount < 1.0 else 60
        if self.blink == "solid" and not busy:
            return
        self.job = self.text.after(delay, self._tick)


class TypingEffects:
    """letters you type fade in, glow or settle from a bright ink; lines can flash."""

    POOL = 24

    def __init__(self, editor):
        self.editor = editor
        self.text = editor.text
        self.kind = "fade"
        self.active = []
        self.next_tag = 0
        self.job = None
        for index in range(self.POOL):
            self.text.tag_configure(f"fx{index}")
        self.text.tag_configure("fxflash")
        self.text.tag_configure("fxpaste")
        self.text.tag_raise("sel")

    def apply(self, settings):
        kind = str(settings.get("typing_effect", "fade"))
        self.kind = kind if kind in TYPING_EFFECTS else "fade"

    def _base_bg(self, index):
        if self.editor.settings.get("highlight_line", True):
            try:
                if self.text.compare(f"{index} linestart", "==", "insert linestart"):
                    return theme.ACTIVE_LINE
            except tk.TclError:
                pass
        return theme.EDITOR_BG

    def _final_color(self, index):
        """the colour a letter has once the effect ends: its highest syntax tag's colour."""
        try:
            names = self.text.tag_names(index)
        except tk.TclError:
            return theme.TEXT
        for name in reversed(names):
            if name.startswith("fx") or name in ("sel", "currentline"):
                continue
            try:
                color = str(self.text.tag_cget(name, "foreground"))
            except tk.TclError:
                continue
            if color:
                return color
        return theme.TEXT

    def typed(self, start, end):
        """letters were just typed between two text indexes."""
        if self.kind == "off" or not theme.MOTION:
            return
        tag = f"fx{self.next_tag}"
        self.next_tag = (self.next_tag + 1) % self.POOL
        self._finish_tag(tag)
        try:
            self.text.tag_add(tag, start, end)
        except tk.TclError:
            return
        duration = {"fade": 0.2, "ink": 0.45, "glow": 0.5}[self.kind] * theme.SPEED
        entry = {"tag": tag, "start": time.perf_counter(), "time": duration, "kind": self.kind, "index": start,
                 "final": None}
        if self.kind == "fade":
            self.text.tag_configure(tag, foreground=self._base_bg(start))
        elif self.kind == "ink":
            self.text.tag_configure(tag, foreground=theme.mix(theme.MOSS_LIGHT, theme.SELECT_TEXT, 0.55))
        else:
            self.text.tag_configure(tag, background=theme.MOSS_DARK)
        self.active.append(entry)
        self._run()

    def flash_range(self, start, end, color=None, duration=0.7, tag="fxpaste"):
        """a soft background glow over some text that fades away (pasted text, jumps)."""
        if not theme.MOTION:
            return
        self._finish_tag(tag)
        try:
            self.text.tag_add(tag, start, end)
        except tk.TclError:
            return
        self.text.tag_lower(tag, "sel")
        entry = {"tag": tag, "start": time.perf_counter(), "time": duration * theme.SPEED, "kind": "glow",
                 "index": start, "final": None, "color": color or theme.MOSS_DARK}
        self.text.tag_configure(tag, background=entry["color"])
        self.active.append(entry)
        self._run()

    def flash_line(self, line, color=None, duration=0.9):
        self.flash_range(f"{line}.0", f"{line}.0+1line", color=color, duration=duration, tag="fxflash")

    def _finish_tag(self, tag):
        for entry in list(self.active):
            if entry["tag"] == tag:
                self.active.remove(entry)
        try:
            self.text.tag_remove(tag, "1.0", "end")
            self.text.tag_configure(tag, foreground="", background="")
        except tk.TclError:
            pass

    def _run(self):
        if self.job is None:
            self.job = self.text.after(16, self._tick)

    def _tick(self):
        self.job = None
        try:
            if not self.text.winfo_exists():
                return
        except tk.TclError:
            return
        now = time.perf_counter()
        for entry in list(self.active):
            progress = min(1.0, (now - entry["start"]) / max(0.001, entry["time"]))
            tag = entry["tag"]
            if progress >= 1.0:
                self._finish_tag(tag)
                continue
            eased = theme.ease_out(progress)
            try:
                if entry["kind"] == "glow":
                    rest = self._base_bg(entry["index"])
                    self.text.tag_configure(tag, background=theme.mix(entry.get("color", theme.MOSS_DARK), rest,
                                                                      theme.ease_in_out(progress)))
                else:
                    if entry["final"] is None:
                        entry["final"] = self._final_color(entry["index"])
                    first = self._base_bg(entry["index"]) if entry["kind"] == "fade" else \
                        theme.mix(theme.MOSS_LIGHT, theme.SELECT_TEXT, 0.55)
                    self.text.tag_configure(tag, foreground=theme.mix(first, entry["final"], eased))
            except tk.TclError:
                self.active.remove(entry)
        if self.active:
            self.job = self.text.after(16, self._tick)


class SmoothScroll:
    """the mouse wheel glides the code instead of jumping three lines at a time."""

    def __init__(self, editor):
        self.editor = editor
        self.text = editor.text
        self.enabled = True
        self.remaining = 0.0
        self.job = None
        self.text.bind("<MouseWheel>", self._wheel, add="+")
        for sequence, step in (("<Button-4>", 120), ("<Button-5>", -120)):
            self.text.bind(sequence, lambda e, d=step: self._wheel(e, d), add="+")

    def apply(self, settings):
        self.enabled = bool(settings.get("smooth_scroll", True))

    def _wheel(self, event, delta=None):
        if not self.enabled or not theme.MOTION:
            return None
        if event.state & 0x4:  # ctrl + wheel zooms
            return None
        delta = event.delta if delta is None else delta
        if not delta:
            return None
        line_height = self.editor.font.metrics("linespace") + theme.px(2)
        notches = -delta / 120.0
        self.remaining += notches * 3 * line_height
        if self.job is None:
            self.job = self.text.after(0, self._tick)
        return "break"

    def _tick(self):
        self.job = None
        if abs(self.remaining) < 1:
            self.remaining = 0.0
            return
        step = self.remaining * min(1.0, 0.32 / max(0.3, theme.SPEED))
        step = int(step) if abs(step) >= 1 else (1 if self.remaining > 0 else -1)
        try:
            self.text.yview_scroll(step, "pixels")
        except tk.TclError:
            self.remaining = 0.0
            return
        first, last = self.text.yview()
        self.remaining -= step
        if (step < 0 and first <= 0.0) or (step > 0 and last >= 1.0):
            self.remaining = 0.0
            return
        self.job = self.text.after(14, self._tick)
