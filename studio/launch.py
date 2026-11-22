"""start gublan studio: show a small square splash straight away, then load the heavy parts.

this module only needs tkinter, so the splash appears before pygame and opengl are imported.
"""

import os
import sys
import tkinter as tk

from .assets import logo_image, set_window_icon
from . import theme


def _splash(root):
    window = tk.Toplevel(root)
    window.overrideredirect(True)
    window.configure(bg=theme.BG)
    width, height = theme.px(360), theme.px(150)
    x = (window.winfo_screenwidth() - width) // 2
    y = (window.winfo_screenheight() - height) // 3
    window.geometry(f"{width}x{height}+{x}+{y}")
    canvas = tk.Canvas(window, width=width, height=height, bg=theme.BG, highlightthickness=1,
                       highlightbackground=theme.MOSS_DARK)
    canvas.pack(fill="both", expand=True)
    arm, line = theme.px(16), theme.px(2)
    pad = theme.px(10)
    for cx, cy, dx, dy in ((pad, pad, 1, 1), (width - pad, pad, -1, 1), (pad, height - pad, 1, -1),
                           (width - pad, height - pad, -1, -1)):
        canvas.create_line(cx, cy, cx + dx * arm, cy, fill=theme.MOSS_LIGHT, width=line)
        canvas.create_line(cx, cy, cx, cy + dy * arm, fill=theme.MOSS_LIGHT, width=line)
    logo = logo_image(window, theme.px(44))
    canvas.create_image(width / 2, height / 2 - theme.px(20), image=logo)
    window.logo_image = logo
    canvas.create_text(width / 2, height / 2 + theme.px(24), text="gublan studio", fill=theme.TEXT,
                       font=theme.ui_font(18, "bold"))
    canvas.create_text(width / 2, height / 2 + theme.px(48), text="getting ready...", fill=theme.DIM,
                       font=theme.ui_font(9))
    window.update()
    theme.square_window(window)
    return window


def launch(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    from . import guard
    guard.prepare_process()
    if argv and argv[0] in ("--mcp", "mcp"):
        # GublanStudio.exe --mcp [project folder]: be an mcp server for ai helpers instead of opening a window
        import gublanmcp
        return gublanmcp.serve(argv[1] if len(argv) > 1 else None)
    theme.enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    root.logo_image = set_window_icon(root)
    theme.pick_fonts(root)
    splash = _splash(root)
    try:
        from .app import GublanStudio
        theme.setup_styles(root)
        studio = GublanStudio(root, [path for path in argv if os.path.exists(path)])
    finally:
        splash.destroy()
    root.deiconify()
    theme.square_window(root, caption=theme.BG)
    root.after(200, lambda: studio.current and studio.current.editor.focus_editor())
    root.mainloop()
    return 0
