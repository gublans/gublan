import os
import sys
import tkinter as tk


def asset_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, name)


def logo_image(master, size=None):
    image = tk.PhotoImage(master=master, file=asset_path("logo.png"))
    if size and image.width() != size:
        image = image.zoom(size, size).subsample(image.width(), image.height())
    return image


def set_window_icon(window):
    image = logo_image(window)
    window.iconphoto(True, image)
    return image
