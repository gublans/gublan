"""the 3d scene editor (tools > 3d scene editor): place, move, size, turn and colour 3d shapes with the mouse.

the program's code is the only copy of the scene. the editor reads the shape lines at the top level of the program
(cube, sphere, block, cylinder, cone and plane with plain numbers), the turn lines that go with them and the camera
line. every change is written straight back into those lines as one undo step, so ctrl+z works in the editor and in
the code, and the program runs the same way with or without the editor. shapes made inside loops or functions are
drawn when their numbers are plain, but they can only be changed in the code.
"""

import difflib
import math
import re
import tkinter as tk

from gublancore import BLOCK_OPENERS, COLORS, GAME_STYLE, color_value, is_color, look_angles, shape_matrix, shape_mesh

from . import theme
from .dialogs import Dialog
from .theme import (BORDER, DIM, EDITOR_BG, MOSS, MOSS_DARK, MOSS_LIGHT, MUTED, NUMBER, PANEL, TEXT,
                    BracketButton, Segmented, Toggle, flat_entry, mono_font, px, scrollbar, ui_font)

KINDS = ("block", "cube", "sphere", "cylinder", "cone", "plane")
SIZE_LABELS = {"cube": ("size",), "sphere": ("radius",), "block": ("width", "height", "depth"),
               "cylinder": ("radius", "height"), "cone": ("radius", "height"), "plane": ("width", "depth")}
NEW_SIZES = {"block": [2, 1, 1], "cube": [1], "sphere": [0.5], "cylinder": [0.5, 2], "cone": [0.5, 1.5],
             "plane": [10, 10]}
NEW_COLORS = {"block": "sand", "cube": "brown", "sphere": "white", "cylinder": "gray", "cone": "forest",
              "plane": "moss"}
PALETTE = ("white", "gray", "darkgray", "black", "red", "orange", "gold", "yellow", "lime", "green", "moss", "forest",
           "teal", "cyan", "sky", "blue", "navy", "purple", "pink", "brown", "sand")
TOOLS = (("select", "select"), ("move", "move"), ("size", "size"), ("turn", "turn"))
FOV = 45.0
NEAR = -0.1
_NUMBER = re.compile(r"-?(?:\d+\.?\d*|\.\d+)$")
_ASSIGN = re.compile(r"[A-Za-z_][\w.]*\s*[-+*/]?=(?!=)")
_FOCAL = 1 / math.tan(math.radians(FOV) / 2)


def fmt(value):
    """a number as short code: 2, 0.5, -1.25 (three decimals at most, never -0)."""
    value = round(float(value), 3)
    if value == int(value):
        return str(int(value))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _numbers(words):
    if all(_NUMBER.match(word) for word in words):
        return [float(word) for word in words]
    return None


def _color_words(words):
    """the colour at the end of a shape line: [] (the current colour), [name], [#hex] or three numbers."""
    if not words:
        return []
    if len(words) == 1 and is_color(words[0]):
        return words
    if len(words) == 3 and _numbers(words) is not None:
        return words
    return None


def _rgb(words, fallback=(255, 255, 255)):
    if not words:
        return fallback
    if len(words) == 3:
        return tuple(max(0, min(255, int(float(word)))) for word in words)
    return tuple(color_value(words[0])[:3])


def hex_color(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(part)))) for part in rgb[:3])


def _opens_block(stripped):
    word = stripped.split(None, 1)[0]
    return word in BLOCK_OPENERS and not _ASSIGN.match(stripped)


# ----- the scene, read from the code -------------------------------------------------------------------------------
class Part:
    """one 3d shape line in the program."""

    def __init__(self, kind, name, numbers, color, line, editable, active_color):
        self.kind, self.name = kind, name
        self.x, self.y, self.z = numbers[:3]
        self.sizes = list(numbers[3:])
        self.color = list(color)
        self.active_color = active_color
        self.line = line
        self.editable = editable
        self.turn_line = None
        self.rx = self.ry = self.rz = 0.0

    def rgb(self):
        return _rgb(self.color, self.active_color)

    def obj(self):
        """the shape as gublancore keeps it, for its mesh and turn helpers."""
        fields = {"cube": ("size",), "sphere": ("radius",), "block": ("w", "h", "d"), "cylinder": ("r", "h"),
                  "cone": ("r", "h"), "plane": ("w", "d")}[self.kind]
        obj = {"type": self.kind, "x": self.x, "y": self.y, "z": self.z, "angle": self.ry, "rx": self.rx,
               "rz": self.rz}
        obj.update(zip(fields, self.sizes))
        return obj

    def turned(self):
        return any(abs(value) > 1e-9 for value in (self.rx, self.ry, self.rz))

    def text(self):
        return " ".join([self.kind, self.name] + [fmt(value) for value in (self.x, self.y, self.z, *self.sizes)]
                        + self.color)

    def turn_text(self):
        return f"turn {self.name} {fmt(self.rx)} {fmt(self.ry)} {fmt(self.rz)}"

    def extent(self):
        if self.kind == "sphere":
            return self.sizes[0]
        if self.kind in ("cylinder", "cone"):
            return max(self.sizes[0], self.sizes[1] / 2)
        return max(self.sizes) / 2


class Scene:
    """the 3d parts of a program: its shapes, their turns, the camera, the light and the background."""

    def __init__(self, source):
        self.lines = source.split("\n")
        self.parts = []
        self.by_name = {}
        self.is_3d = False
        self.mode_line = None
        self.camera = [0.0, 0.0, 0.0]
        self.camera_turn = [0.0, 0.0]
        self.camera_line = None
        self.lookat_lines = []
        self.light = None
        self.background = tuple(color_value(GAME_STYLE.get("background", "black"))[:3])
        self.made_by_code = 0
        self.first_block = None
        self.last_scene_line = None
        active = (255, 255, 255)
        depth = 0
        for index, raw in enumerate(self.lines):
            stripped = raw.strip()
            if not stripped or stripped.startswith("//"):
                continue
            words = stripped.split()
            command = words[0]
            top = depth == 0
            if command == "end":
                depth = max(0, depth - 1)
                continue
            if _opens_block(stripped):
                if top and self.first_block is None:
                    self.first_block = index
                depth += 1
                continue
            if command == "mode" and len(words) > 1 and words[1] == "3d":
                self.is_3d = True
                if top and self.mode_line is None:
                    self.mode_line = index
                    self._scene_line(index)
            elif command == "background" and top:
                colour = _color_words(words[1:])
                if colour:
                    self.background = _rgb(colour)
                    self._scene_line(index)
            elif command == "color" and top:
                colour = _color_words(words[1:])
                if colour:
                    active = _rgb(colour)
            elif command in KINDS:
                self._read_shape(index, words, top, active)
            elif command == "turn" and len(words) in (4, 5):
                # only top-level turns set how a part starts. turns inside loops are animation
                part = self.by_name.get(words[1])
                numbers = _numbers(words[2:])
                if part is None or numbers is None or not top or part.turn_line is not None:
                    continue
                part.rx, part.ry = numbers[0], numbers[1]
                part.rz = numbers[2] if len(numbers) > 2 else 0.0
                if part.editable:
                    part.turn_line = index
                    self._scene_line(index)
            elif command == "camera" and top and len(words) in (4, 6):
                numbers = _numbers(words[1:])
                if numbers is not None:
                    self.camera = numbers[:3]
                    if len(numbers) == 5:
                        self.camera_turn = numbers[3:]
                    self.camera_line = index
                    self._scene_line(index)
            elif command == "lookat" and top and len(words) in (2, 4):
                if len(words) == 4 and _numbers(words[1:]) is not None:
                    target = _numbers(words[1:])
                elif len(words) == 2 and words[1] in self.by_name:
                    found = self.by_name[words[1]]
                    target = (found.x, found.y, found.z)
                else:
                    continue
                self.camera_turn = list(look_angles(self.camera, target))
                self.lookat_lines.append(index)
                self._scene_line(index)
            elif command == "light" and top and len(words) in (4, 5):
                numbers = _numbers(words[1:])
                if numbers is not None and any(numbers[:3]):
                    self.light = (numbers[0], numbers[1], numbers[2], numbers[3] if len(numbers) > 3 else 1.0)
                    self._scene_line(index)

    def _scene_line(self, index):
        if self.first_block is None:
            self.last_scene_line = index

    def _read_shape(self, index, words, top, active):
        count = 3 + len(SIZE_LABELS[words[0]])
        if len(words) < 2 + count:
            return
        numbers = _numbers(words[2:2 + count])
        colour = _color_words(words[2 + count:])
        name = words[1]
        if numbers is None or colour is None or any(size <= 0 for size in numbers[3:]) \
                or not re.fullmatch(r"[A-Za-z_]\w*", name):
            self.made_by_code += 1
            return
        if name in self.by_name:  # made again later: the first line is the one the editor shows
            return
        editable = top
        part = Part(words[0], name, numbers, colour, index, editable, active)
        self.parts.append(part)
        self.by_name[name] = part
        if editable:
            self._scene_line(index)

    def names(self):
        """every name in the program, so new parts get one nobody uses."""
        used = set()
        for raw in self.lines:
            used.update(re.findall(r"[A-Za-z_]\w*", raw))
        return used

    def new_name(self, base):
        used = self.names()
        number = 1
        while f"{base}{number}" in used:
            number += 1
        return f"{base}{number}"

    def insert_at(self):
        """the line new parts go on: after the last scene line, before the program's first loop or function."""
        if self.last_scene_line is not None:
            return self.last_scene_line + 1
        if self.first_block is not None:
            return self.first_block
        return len(self.lines) if any(line.strip() for line in self.lines) else 0


# ----- drawing helpers ---------------------------------------------------------------------------------------
def _times(matrix, point):
    return tuple(row[0] * point[0] + row[1] * point[1] + row[2] * point[2] for row in matrix)


def _view(eye, turn, point):
    yaw, pitch = math.radians(turn[0]), math.radians(turn[1])
    dx, dy, dz = point[0] - eye[0], point[1] - eye[1], point[2] - eye[2]
    x = dx * math.cos(yaw) + dz * math.sin(yaw)
    z = -dx * math.sin(yaw) + dz * math.cos(yaw)
    return x, dy * math.cos(pitch) - z * math.sin(pitch), dy * math.sin(pitch) + z * math.cos(pitch)


def clip_near(points, closed=True):
    """cut a polygon (or a line) where it passes behind the camera."""
    out = []
    count = len(points)
    for index in range(count if closed else count - 1):
        here, there = points[index], points[(index + 1) % count]
        here_in, there_in = here[2] <= NEAR, there[2] <= NEAR
        if here_in:
            out.append(here)
        if here_in != there_in:
            t = (NEAR - here[2]) / (there[2] - here[2])
            out.append(tuple(here[k] + (there[k] - here[k]) * t for k in range(3)))
    if not closed and count and points[-1][2] <= NEAR:
        out.append(points[-1])
    return out


def _split_quad(corners, size=2.0, most=10):
    """break a big four-cornered face into tiles, so faces sort properly against the shapes standing on them."""
    a, b, c, d = corners
    across = min(most, max(1, math.ceil(math.dist(a, b) / size)))
    down = min(most, max(1, math.ceil(math.dist(a, d) / size)))
    if across == down == 1:
        return [corners]

    def at(u, v):
        top = [a[k] + (b[k] - a[k]) * u for k in range(3)]
        bottom = [d[k] + (c[k] - d[k]) * u for k in range(3)]
        return tuple(top[k] + (bottom[k] - top[k]) * v for k in range(3))
    return [[at(i / across, j / down), at((i + 1) / across, j / down), at((i + 1) / across, (j + 1) / down),
             at(i / across, (j + 1) / down)] for i in range(across) for j in range(down)]


def part_faces(part, sides=16):
    """(world normal, world corners) for every face of a part."""
    matrix = shape_matrix(part.obj())
    sizes = [abs(value) for value in part.sizes]
    out = []
    for normal, corners in shape_mesh(part.kind, sizes, sides):
        normal = _times(matrix, normal)
        world = [tuple(value + offset for value, offset in zip(_times(matrix, corner), (part.x, part.y, part.z)))
                 for corner in corners]
        pieces = _split_quad(world) if len(world) == 4 and part.kind in ("plane", "block", "cube") else [world]
        out.extend((normal, piece) for piece in pieces)
    return out


# ----- the window ---------------------------------------------------------------------------------------------
class SceneEditor(Dialog):
    def __init__(self, master, code, run=None):
        super().__init__(master, "3d scene editor", resizable=True)
        self.code = code
        self.run_program = run
        self.scene = Scene(code.get())
        self.seen = code.version
        self.selected = None
        self.tool = tk.StringVar(value="move")
        self.snap = tk.BooleanVar(value=True)
        self.show_grid = tk.BooleanVar(value=True)
        self.target = [0.0, 0.5, -6.0]
        self.distance = 12.0
        self.yaw, self.pitch = 0.0, 25.0
        self.drag = None
        self.pending = False
        self.fields = {}
        self.field_part = None
        self._build()
        self.frame_view(self.scene.parts)
        self.refresh()
        self.after(500, self.watch)

    # ----- layout
    def _build(self):
        bar = tk.Frame(self.body, bg=PANEL)
        bar.pack(fill="x", pady=(0, px(10)))
        Segmented(bar, TOOLS, self.tool, command=lambda _v: self.set_status_hint(), bg=PANEL, size=9).pack(
            side="left")
        tk.Label(bar, text="add", bg=PANEL, fg=MUTED, font=ui_font(9)).pack(side="left", padx=(px(16), px(6)))
        for kind in KINDS:
            BracketButton(bar, kind, command=lambda k=kind: self.add_part(k), size=9, pad_x=8, pad_y=5,
                          bg=PANEL).pack(side="left", padx=(0, px(4)))
        Toggle(bar, "snap", self.snap, bg=PANEL).pack(side="left", padx=(px(12), 0))
        Toggle(bar, "grid", self.show_grid, command=self.redraw, bg=PANEL).pack(side="left", padx=(px(8), 0))

        main = tk.Frame(self.body, bg=PANEL)
        main.pack(fill="both", expand=True)
        left = tk.Frame(main, bg=PANEL, width=px(170))
        left.pack(side="left", fill="y", padx=(0, px(10)))
        left.pack_propagate(False)
        tk.Label(left, text="parts", bg=PANEL, fg=MUTED, font=ui_font(9), anchor="w").pack(fill="x")
        box = tk.Frame(left, bg=EDITOR_BG, highlightthickness=1, highlightbackground=BORDER)
        box.pack(fill="both", expand=True, pady=(px(4), 0))
        self.listbox = tk.Listbox(box, bg=EDITOR_BG, fg=TEXT, selectbackground=MOSS_DARK, selectforeground=TEXT,
                                  relief="flat", highlightthickness=0, bd=0, font=mono_font(10), activestyle="none",
                                  exportselection=False)
        bar_y = scrollbar(box, "vertical", self.listbox.yview)
        self.listbox.configure(yscrollcommand=bar_y.set)
        bar_y.pack(side="right", fill="y")
        self.listbox.pack(side="left", fill="both", expand=True, padx=px(4), pady=px(4))
        self.listbox.bind("<<ListboxSelect>>", self._picked_in_list)
        self.listbox.bind("<Double-Button-1>", lambda _e: self.frame_view([self.part()] if self.part() else []))
        self.code_note = tk.Label(left, text="", bg=PANEL, fg=DIM, font=ui_font(8), justify="left", anchor="w",
                                  wraplength=px(165))
        self.code_note.pack(fill="x", pady=(px(6), 0))

        self.props = tk.Frame(main, bg=PANEL, width=px(240))
        self.props.pack(side="right", fill="y", padx=(px(10), 0))
        self.props.pack_propagate(False)

        self.canvas = tk.Canvas(main, bg=EDITOR_BG, highlightthickness=1, highlightbackground=BORDER,
                                highlightcolor=MOSS, takefocus=1, cursor="crosshair", width=px(560),
                                height=px(460))
        self.canvas.pack(side="left", fill="both", expand=True)
        canvas = self.canvas
        canvas.bind("<Configure>", lambda _e: self.redraw())
        canvas.bind("<ButtonPress-1>", self._press)
        canvas.bind("<B1-Motion>", self._motion)
        canvas.bind("<ButtonRelease-1>", self._release)
        for button in ("2", "3"):
            canvas.bind(f"<ButtonPress-{button}>", lambda e, b=button: self._look_press(e, b))
            canvas.bind(f"<B{button}-Motion>", self._look_motion)
            canvas.bind(f"<ButtonRelease-{button}>", lambda _e: setattr(self, "drag", None))
        canvas.bind("<MouseWheel>", lambda e: self.zoom(e.delta))
        canvas.bind("<Button-4>", lambda _e: self.zoom(120))
        canvas.bind("<Button-5>", lambda _e: self.zoom(-120))
        for key, step in (("w", (0, 0, 1)), ("s", (0, 0, -1)), ("a", (-1, 0, 0)), ("d", (1, 0, 0)),
                          ("e", (0, 1, 0)), ("q", (0, -1, 0))):
            canvas.bind(f"<KeyPress-{key}>", lambda _e, s=step: self.fly(*s))
        for key, step in (("Left", (-1, 0, 0)), ("Right", (1, 0, 0)), ("Up", (0, 0, 1)), ("Down", (0, 0, -1)),
                          ("Prior", (0, 1, 0)), ("Next", (0, -1, 0))):
            canvas.bind(f"<KeyPress-{key}>", lambda _e, s=step: self.nudge(*s))
        for number, (value, _label) in enumerate(TOOLS, start=1):
            canvas.bind(f"<KeyPress-{number}>", lambda _e, v=value: (self.tool.set(v), self.set_status_hint()))
        canvas.bind("<KeyPress-f>", lambda _e: self.frame_view([self.part()] if self.part() else self.scene.parts))
        canvas.bind("<Delete>", lambda _e: self.delete_part())
        canvas.bind("<BackSpace>", lambda _e: self.delete_part())
        self.bind("<Control-d>", lambda _e: self.duplicate_part())
        self.bind("<Control-z>", lambda _e: self.undo())
        self.bind("<Control-y>", lambda _e: self.redo())
        self.bind("<Control-Z>", lambda _e: self.redo())
        self.bind("<F5>", lambda _e: self.run_program and self.run_program())
        self.bind("<Escape>", lambda _e: self.escape())

        self.status = tk.Label(self.body, text="", bg=PANEL, fg=DIM, font=ui_font(9), anchor="w", justify="left")
        self.status.pack(fill="x", pady=(px(8), 0))
        self.add_button("close", self.cancel, kind="ghost")
        if self.run_program:
            self.add_button("run", self.run_program, kind="accent")
        self.add_button("view from game camera", self.view_from_game_camera)
        self.add_button("set game camera here", self.set_game_camera)
        self.set_status_hint()

    def set_status_hint(self, text=None):
        if text is None:
            text = {"select": "click a part to pick it",
                    "move": "drag a part to slide it along the ground. hold shift to lift it up or down",
                    "size": "drag a part right or up to make it bigger",
                    "turn": "drag to turn a part. shift turns it forwards, ctrl turns it sideways"}[self.tool.get()]
            text += ".   right-drag looks around, the wheel zooms, wasd flies, f frames the part, 1-4 pick a tool"
        self.status.configure(text=text, fg=DIM)

    def say(self, text, good=True):
        self.status.configure(text=text, fg=MOSS_LIGHT if good else NUMBER)

    # ----- reading and writing the code
    def part(self):
        return self.scene.by_name.get(self.selected) if self.selected else None

    def watch(self):
        try:
            alive = self.winfo_exists() and self.code.text.winfo_exists()
        except tk.TclError:
            alive = False
        if not alive:
            if self.winfo_exists():
                self.destroy()
            return
        if self.code.version != self.seen and self.drag is None:
            self.reload()
        self.after(500, self.watch)

    def reload(self):
        self.scene = Scene(self.code.get())
        self.seen = self.code.version
        if self.selected not in self.scene.by_name:
            self.selected = None
        self.refresh()

    def write(self, lines, message=None):
        """put the changed lines into the code as one undo step, touching only the lines that changed."""
        old_text = self.code.get()
        new_text = "\n".join(lines)
        if new_text != old_text:
            old_lines = old_text.split("\n")
            text = self.code.text
            text.configure(autoseparators=False)
            text.edit_separator()
            try:
                matcher = difflib.SequenceMatcher(None, old_lines, lines, autojunk=False)
                for tag, i1, i2, j1, j2 in reversed(matcher.get_opcodes()):
                    if tag == "equal":
                        continue
                    replacement = "\n".join(lines[j1:j2])
                    if i1 < i2 and j1 < j2:
                        text.delete(f"{i1 + 1}.0", f"{i2}.end")
                        text.insert(f"{i1 + 1}.0", replacement)
                    elif i1 < i2:
                        if i2 < len(old_lines):
                            text.delete(f"{i1 + 1}.0", f"{i2 + 1}.0")
                        elif i1 > 0:
                            text.delete(f"{i1}.end", f"{i2}.end")
                        else:
                            text.delete("1.0", "end-1c")
                    elif i1 < len(old_lines):
                        text.insert(f"{i1 + 1}.0", replacement + "\n")
                    else:
                        text.insert("end-1c", "\n" + replacement)
                if self.code.get() != new_text:
                    text.delete("1.0", "end-1c")
                    text.insert("1.0", new_text)
            finally:
                text.edit_separator()
                text.configure(autoseparators=True)
        self.reload()
        if message:
            self.say(message)

    def lines(self):
        return self.code.get().split("\n")

    def save_part(self, part, message=None):
        lines = self.lines()
        lines[part.line] = part.text()
        if part.turn_line is not None:
            lines[part.turn_line] = part.turn_text()
        elif part.turned():
            lines.insert(part.line + 1, part.turn_text())
        self.write(lines, message)

    def undo(self):
        self.code.undo()
        self.reload()
        self.say("undid the last change")

    def redo(self):
        self.code.redo()
        self.reload()
        self.say("redid it")

    # ----- making, copying and removing parts
    def make_3d(self):
        lines = self.lines()
        at = 0
        while at < len(lines) and lines[at].strip().startswith("//"):
            at += 1
        if not any(line.strip() for line in lines):
            lines = ["mode 3d", "plane ground 0 0 -6 20 20 moss", "", "forever", "    frame", "end"]
            self.write(lines, "made a new 3d scene with some ground")
            return
        lines.insert(at, "mode 3d")
        self.write(lines, "added mode 3d to the top of the program")

    def _ground_point(self):
        eye, _turn = self.eye()
        _origin, direction = self.ray(self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2)
        if direction[1] < -0.05:
            t = -eye[1] / direction[1]
            if t < 40:
                return [eye[0] + direction[0] * t, 0.0, eye[2] + direction[2] * t]
        return [self.target[0], 0.0, self.target[2]]

    def add_part(self, kind):
        if not self.scene.is_3d:
            self.make_3d()
        scene = self.scene
        name = scene.new_name(kind)
        sizes = list(NEW_SIZES[kind])
        x, _y, z = self._ground_point()
        if self.snap.get():
            x, z = round(x * 2) / 2, round(z * 2) / 2
        # resting on the grid: shapes are placed by their middle
        y = {"block": lambda: sizes[1] / 2, "cube": lambda: sizes[0] / 2, "sphere": lambda: sizes[0],
             "cylinder": lambda: sizes[1] / 2, "cone": lambda: sizes[1] / 2, "plane": lambda: 0}[kind]()
        part = Part(kind, name, [x, y, z] + sizes, [NEW_COLORS[kind]], 0, True, (255, 255, 255))
        lines = self.lines()
        lines.insert(scene.insert_at(), part.text())
        self.selected = name
        self.write(lines, f"added {kind} {name}. its line is in the code now")

    def duplicate_part(self):
        part = self.part()
        if part is None or not part.editable:
            return
        copy = Part(part.kind, self.scene.new_name(re.sub(r"\d+$", "", part.name) or part.kind),
                    [part.x + max(0.5, part.extent()), part.y, part.z] + part.sizes, part.color, 0, True,
                    part.active_color)
        copy.rx, copy.ry, copy.rz = part.rx, part.ry, part.rz
        lines = self.lines()
        after = max(part.line, part.turn_line if part.turn_line is not None else -1) + 1
        new = [copy.text()] + ([copy.turn_text()] if copy.turned() else [])
        lines[after:after] = new
        self.selected = copy.name
        self.write(lines, f"copied {part.name} as {copy.name}")

    def delete_part(self):
        part = self.part()
        if part is None:
            return
        if not part.editable:
            self.say(f"{part.name} is made inside a block of code, so delete it in the code", good=False)
            return
        lines = self.lines()
        for index in sorted({part.line, part.turn_line} - {None}, reverse=True):
            del lines[index]
        still_used = any(re.search(rf"\b{re.escape(part.name)}\b", line) for line in lines)
        self.selected = None
        self.write(lines, f"deleted {part.name}" + (". other lines still use its name" if still_used else ""))

    def rename_part(self, part, new_name):
        new_name = new_name.strip()
        if new_name == part.name:
            return
        if not re.fullmatch(r"[A-Za-z_]\w*", new_name):
            self.say("names are letters, numbers and _, and start with a letter", good=False)
            return
        if new_name in self.scene.names():
            self.say(f"'{new_name}' is already used in this program", good=False)
            return
        pattern = re.compile(rf"(?<![\w.]){re.escape(part.name)}\b")
        lines = [pattern.sub(new_name, line) for line in self.lines()]
        self.selected = new_name
        self.write(lines, f"renamed {part.name} to {new_name} everywhere in the code")

    # ----- the game camera
    def set_game_camera(self):
        if not self.scene.is_3d:
            self.make_3d()
        eye, turn = self.eye()
        text = "camera " + " ".join(fmt(value) for value in (*eye, *turn))
        lines = self.lines()
        removed = 0
        for index in sorted(self.scene.lookat_lines, reverse=True):
            del lines[index]
            removed += 1
        line = self.scene.camera_line
        if line is not None:
            line -= sum(1 for index in self.scene.lookat_lines if index < line)
            lines[line] = text
        else:
            lines.insert(min(self.scene.insert_at(), len(lines)), text)
        self.write(lines, "the game starts looking from here now" + (" (the lookat line made way for it)"
                                                                       if removed else ""))

    def view_from_game_camera(self):
        self.yaw, self.pitch = self.scene.camera_turn
        forward = self.forward()
        self.distance = 8.0
        self.target = [self.scene.camera[k] + forward[k] * self.distance for k in range(3)]
        self.redraw()
        self.say("this is what the game sees when it starts")

    # ----- the editor's own camera (it never changes the program)
    def forward(self):
        yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
        return (math.sin(yaw) * math.cos(pitch), -math.sin(pitch), -math.cos(yaw) * math.cos(pitch))

    def eye(self):
        forward = self.forward()
        return [self.target[k] - forward[k] * self.distance for k in range(3)], (self.yaw, self.pitch)

    def ray(self, sx, sy):
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        vx = (2 * sx / width - 1) * (width / height) / _FOCAL
        vy = (1 - 2 * sy / height) / _FOCAL
        vz = -1.0
        yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
        dy = vy * math.cos(pitch) + vz * math.sin(pitch)
        z1 = -vy * math.sin(pitch) + vz * math.cos(pitch)
        dx = vx * math.cos(yaw) - z1 * math.sin(yaw)
        dz = vx * math.sin(yaw) + z1 * math.cos(yaw)
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        return self.eye()[0], (dx / length, dy / length, dz / length)

    def frame_view(self, parts):
        parts = [part for part in parts if part is not None]
        if not parts:
            return
        low = [min(getattr(part, axis) - part.extent() for part in parts) for axis in "xyz"]
        high = [max(getattr(part, axis) + part.extent() for part in parts) for axis in "xyz"]
        self.target = [(a + b) / 2 for a, b in zip(low, high)]
        size = max(1.0, max(b - a for a, b in zip(low, high)))
        self.distance = min(150.0, max(3.0, size * 1.6))
        self.redraw()

    def zoom(self, delta):
        self.distance = min(200.0, max(1.0, self.distance * 0.88 ** (delta / 120)))
        self.redraw()

    def fly(self, right, up, ahead):
        yaw = math.radians(self.yaw)
        step = max(0.25, self.distance * 0.06)
        self.target[0] += (math.sin(yaw) * ahead + math.cos(yaw) * right) * step
        self.target[2] += (-math.cos(yaw) * ahead + math.sin(yaw) * right) * step
        self.target[1] += up * step
        self.redraw()

    def _look_press(self, event, button):
        self.canvas.focus_set()
        pan = button == "2" or bool(event.state & 0x0001)
        self.drag = {"kind": "pan" if pan else "orbit", "x": event.x, "y": event.y}

    def _look_motion(self, event):
        drag = self.drag
        if not drag or drag["kind"] not in ("orbit", "pan"):
            return
        dx, dy = event.x - drag["x"], event.y - drag["y"]
        drag["x"], drag["y"] = event.x, event.y
        if drag["kind"] == "orbit":
            self.yaw = (self.yaw + dx * 0.4) % 360
            self.pitch = max(-89.0, min(89.0, self.pitch + dy * 0.4))
        else:
            yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
            right = (math.cos(yaw), 0, math.sin(yaw))
            up = (math.sin(yaw) * math.sin(pitch), math.cos(pitch), -math.cos(yaw) * math.sin(pitch))
            step = self.distance * 0.0022
            for k in range(3):
                self.target[k] += (-dx * right[k] + dy * up[k]) * step
        self.schedule_draw()

    # ----- picking and dragging parts
    def part_at(self, x, y):
        for item in reversed(self.canvas.find_overlapping(x - 1, y - 1, x + 1, y + 1)):
            for tag in self.canvas.gettags(item):
                if tag.startswith("part:"):
                    return self.scene.by_name.get(tag[5:])
        return None

    def _press(self, event):
        self.canvas.focus_set()
        part = self.part_at(event.x, event.y)
        if part is None:
            self.select(None)
            self.drag = {"kind": "orbit", "x": event.x, "y": event.y}
            return
        self.select(part.name)
        tool = self.tool.get()
        if tool == "select":
            self.drag = None
            return
        if not part.editable:
            self.say(f"{part.name} is made inside a block of code, so change it in the code", good=False)
            self.drag = None
            return
        self.drag = {"kind": tool, "part": part, "x": event.x, "y": event.y, "start": (part.x, part.y, part.z),
                     "sizes": list(part.sizes), "turn": (part.rx, part.ry, part.rz), "moved": False}
        if tool == "move":
            hit = self._ground_hit(event.x, event.y, part.y)
            self.drag["offset"] = None if hit is None else (part.x - hit[0], part.z - hit[2])

    def _ground_hit(self, x, y, height):
        origin, direction = self.ray(x, y)
        if abs(direction[1]) < 1e-4:
            return None
        t = (height - origin[1]) / direction[1]
        if t <= 0 or t > 500:
            return None
        return [origin[k] + direction[k] * t for k in range(3)]

    def _snap(self, value, step):
        return round(value / step) * step if self.snap.get() else value

    def _motion(self, event):
        drag = self.drag
        if not drag:
            return
        if drag["kind"] in ("orbit", "pan"):
            self._look_motion(event)
            return
        part = drag["part"]
        dx, dy = event.x - drag["x"], event.y - drag["y"]
        if abs(dx) + abs(dy) > 2:
            drag["moved"] = True
        shift, ctrl = bool(event.state & 0x0001), bool(event.state & 0x0004)
        if drag["kind"] == "move":
            if shift or drag.get("offset") is None:
                eye = self.eye()[0]
                gap = math.dist(eye, drag["start"])
                per_pixel = gap * 2 * math.tan(math.radians(FOV) / 2) / max(1, self.canvas.winfo_height())
                part.y = self._snap(drag["start"][1] - dy * per_pixel, 0.25)
                part.x, part.z = drag["start"][0], drag["start"][2]
            else:
                hit = self._ground_hit(event.x, event.y, drag["start"][1])
                if hit is not None:
                    part.x = self._snap(hit[0] + drag["offset"][0], 0.5)
                    part.z = self._snap(hit[2] + drag["offset"][1], 0.5)
                part.y = drag["start"][1]
        elif drag["kind"] == "size":
            grow = math.exp((dx - dy) * 0.01)
            part.sizes = [max(0.05, self._snap(size * grow, 0.25) or 0.25) for size in drag["sizes"]]
        elif drag["kind"] == "turn":
            rx, ry, rz = drag["turn"]
            if shift:
                part.rx = self._snap(rx + dy * 0.6, 15)
            elif ctrl:
                part.rz = self._snap(rz + dx * 0.6, 15)
            else:
                part.ry = self._snap(ry + dx * 0.6, 15)
        self.show_numbers(part)
        self.schedule_draw()

    def _release(self, _event):
        drag, self.drag = self.drag, None
        if not drag or drag["kind"] in ("orbit", "pan"):
            return
        part = drag["part"]
        changed = (part.x, part.y, part.z) != drag["start"] or part.sizes != drag["sizes"] or \
            (part.rx, part.ry, part.rz) != drag["turn"]
        if changed:
            words = {"move": "moved", "size": "resized", "turn": "turned"}[drag["kind"]]
            self.save_part(part, f"{words} {part.name}")

    def nudge(self, right, up, ahead):
        part = self.part()
        if part is None or not part.editable:
            self.fly(right, up, ahead)
            return
        step = 0.5 if self.snap.get() else 0.1
        yaw = math.radians(self.yaw)
        ax, az = math.sin(yaw) * ahead + math.cos(yaw) * right, -math.cos(yaw) * ahead + math.sin(yaw) * right
        if abs(ax) >= abs(az):
            part.x = self._snap(part.x + math.copysign(step, ax), step) if ax else part.x
        else:
            part.z = self._snap(part.z + math.copysign(step, az), step)
        part.y += up * step
        self.save_part(part, f"moved {part.name}")

    def escape(self):
        if self.selected:
            self.select(None)
        else:
            self.cancel()

    # ----- the parts list and the properties
    def select(self, name):
        if name == self.selected:
            return
        self.selected = name
        self.refresh()
        part = self.part()
        if part is not None:
            self.code.flash_line(part.line + 1)
            try:
                self.code.text.see(f"{part.line + 1}.0")
            except tk.TclError:
                pass

    def _picked_in_list(self, _event):
        chosen = self.listbox.curselection()
        if not chosen:
            return
        names = [part.name for part in self.scene.parts]
        if chosen[0] < len(names):
            self.select(names[chosen[0]])

    def refresh(self):
        scene = self.scene
        self.listbox.delete(0, "end")
        for index, part in enumerate(scene.parts):
            self.listbox.insert("end", f"{part.name}  {part.kind}")
            if not part.editable:
                self.listbox.itemconfigure(index, foreground=DIM)
            if part.name == self.selected:
                self.listbox.selection_set(index)
                self.listbox.see(index)
        notes = []
        if scene.made_by_code:
            notes.append(f"{scene.made_by_code} more shape{'s' if scene.made_by_code != 1 else ''} use variables, "
                         "so they only show when the program runs")
        if any(not part.editable for part in scene.parts):
            notes.append("grey parts are made inside a block of code. change those in the code")
        self.code_note.configure(text="\n\n".join(notes))
        self.build_props()
        self.redraw()

    def _field(self, parent, label, value, on_set, width=7):
        cell = tk.Frame(parent, bg=PANEL)
        tk.Label(cell, text=label, bg=PANEL, fg=MUTED, font=ui_font(8), anchor="w").pack(fill="x")
        variable = tk.StringVar(value=value)
        entry = flat_entry(cell, variable, width=width, mono=True)
        entry.pack(fill="x")

        def apply(_event=None):
            # after the event: saving rebuilds this panel, and a box shouldn't be destroyed inside its own event
            self.after_idle(lambda: self.winfo_exists() and on_set(variable.get()))
        entry.bind("<Return>", apply)
        entry.bind("<FocusOut>", apply)
        entry.bind("<KP_Enter>", apply)
        return cell, variable

    def build_props(self):
        for child in self.props.winfo_children():
            child.destroy()
        self.fields = {}
        part = self.part()
        self.field_part = part.name if part else None
        if part is None:
            text = ("pick a part to change it, or add one with the buttons at the top.\n\n"
                    "everything here is written into your code, so the program runs the same with or without "
                    "this window.")
            if not self.scene.is_3d:
                text = "this program isn't 3d yet. adding a part puts mode 3d at the top for you."
            tk.Label(self.props, text=text, bg=PANEL, fg=MUTED, font=ui_font(9), justify="left", anchor="nw",
                     wraplength=px(230)).pack(fill="x")
            if not self.scene.is_3d:
                BracketButton(self.props, "make it 3d", command=self.make_3d, kind="accent", size=9,
                              bg=PANEL).pack(anchor="w", pady=(px(10), 0))
            return
        top = tk.Frame(self.props, bg=PANEL)
        top.pack(fill="x")
        tk.Label(top, text=part.kind, bg=PANEL, fg=MOSS_LIGHT, font=ui_font(10, "bold")).pack(side="left")
        tk.Label(top, text=f"line {part.line + 1}", bg=PANEL, fg=DIM, font=ui_font(8)).pack(side="right")
        state = "normal" if part.editable else "disabled"
        name_cell, _var = self._field(self.props, "name", part.name, lambda value: self.rename_part(part, value),
                                      width=18)
        name_cell.pack(fill="x", pady=(px(6), 0))

        def number_row(title, labels, values, setter):
            tk.Label(self.props, text=title, bg=PANEL, fg=MUTED, font=ui_font(9), anchor="w").pack(
                fill="x", pady=(px(10), px(2)))
            row = tk.Frame(self.props, bg=PANEL)
            row.pack(fill="x")
            variables = []
            for index, (label, value) in enumerate(zip(labels, values)):
                cell, variable = self._field(row, label, fmt(value),
                                             lambda text, i=index: setter(i, text))
                cell.pack(side="left", fill="x", expand=True, padx=(0, px(4)))
                variables.append(variable)
            for cell in row.winfo_children():
                for widget in cell.winfo_children():
                    if isinstance(widget, tk.Entry):
                        widget.configure(state=state)
            return variables

        def set_position(index, text):
            self._set_number(part, "xyz"[index], text)

        def set_size(index, text):
            self._set_size(part, index, text)

        def set_turn(index, text):
            self._set_number(part, ("rx", "ry", "rz")[index], text)

        self.fields["position"] = number_row("position", ("x", "y", "z"), (part.x, part.y, part.z), set_position)
        self.fields["size"] = number_row("size", SIZE_LABELS[part.kind], part.sizes, set_size)
        self.fields["turn"] = number_row("turn (degrees)", ("x", "y", "z"), (part.rx, part.ry, part.rz), set_turn)

        tk.Label(self.props, text="colour", bg=PANEL, fg=MUTED, font=ui_font(9), anchor="w").pack(
            fill="x", pady=(px(10), px(2)))
        swatches = tk.Frame(self.props, bg=PANEL)
        swatches.pack(anchor="w")
        current = " ".join(part.color)
        for number, name in enumerate(PALETTE):
            colour = hex_color(COLORS[name])
            chosen = name == current
            swatch = tk.Frame(swatches, bg=colour, width=px(22), height=px(22), cursor="hand2",
                              highlightthickness=2 if chosen else 1,
                              highlightbackground=MOSS_LIGHT if chosen else BORDER)
            swatch.grid(row=number // 7, column=number % 7, padx=px(1), pady=px(1))
            if part.editable:
                swatch.bind("<Button-1>", lambda _e, n=name: self._set_color(part, n))
        colour_cell, _var = self._field(self.props, "name, #hex or three numbers", current or "",
                                        lambda text: self._set_color(part, text), width=18)
        colour_cell.pack(fill="x", pady=(px(6), 0))
        buttons = tk.Frame(self.props, bg=PANEL)
        buttons.pack(fill="x", pady=(px(14), 0))
        if part.editable:
            BracketButton(buttons, "copy", command=self.duplicate_part, size=9, bg=PANEL,
                          tooltip="ctrl+d").pack(side="left")
            BracketButton(buttons, "delete", command=self.delete_part, size=9, kind="danger", bg=PANEL,
                          tooltip="delete").pack(side="left", padx=(px(6), 0))
        BracketButton(buttons, "show code", command=lambda: self.code.goto_line(part.line + 1, select_line=True),
                      size=9, kind="ghost", bg=PANEL).pack(side="left", padx=(px(6), 0))

    def show_numbers(self, part):
        """keep the property boxes in step while a part is dragged."""
        if self.field_part != part.name:
            return
        for key, values in (("position", (part.x, part.y, part.z)), ("size", part.sizes),
                            ("turn", (part.rx, part.ry, part.rz))):
            for variable, value in zip(self.fields.get(key, ()), values):
                variable.set(fmt(value))

    def _number(self, text):
        try:
            return float(str(text).strip())
        except ValueError:
            self.say(f"'{text}' is not a number", good=False)
            return None

    def _set_number(self, part, field, text):
        value = self._number(text)
        if value is None or not part.editable or abs(getattr(part, field) - value) < 1e-9:
            return
        setattr(part, field, value)
        self.save_part(part, f"changed {part.name}")

    def _set_size(self, part, index, text):
        value = self._number(text)
        if value is None or not part.editable or abs(part.sizes[index] - value) < 1e-9:
            return
        if value <= 0:
            self.say("sizes must be greater than zero", good=False)
            return
        part.sizes[index] = value
        self.save_part(part, f"resized {part.name}")

    def _set_color(self, part, text):
        words = str(text).split()
        colour = _color_words(words)
        if colour is None:
            self.say(f"'{text}' is not a colour. use a name like moss, #ff8800 or three numbers", good=False)
            return
        if colour == part.color or not part.editable:
            return
        part.color = colour
        self.save_part(part, f"painted {part.name}")

    # ----- drawing
    def schedule_draw(self):
        if not self.pending:
            self.pending = True
            self.after_idle(self.redraw)

    def redraw(self):
        self.pending = False
        canvas = self.canvas
        try:
            width, height = canvas.winfo_width(), canvas.winfo_height()
        except tk.TclError:
            return
        canvas.delete("all")
        if width < 20 or height < 20:
            return
        background = self.scene.background
        canvas.configure(bg=hex_color(background))
        eye, turn = self.eye()
        aspect = width / height

        def screen(point):
            x, y, z = point
            return ((_FOCAL / aspect * x / -z + 1) / 2 * width, (1 - _FOCAL * y / -z) / 2 * height)

        lightness = sum(background) / 3
        line_colour = hex_color([part + (40 if lightness < 128 else -40) for part in background])
        if self.show_grid.get():
            self.draw_grid(eye, turn, screen, line_colour)
        if self.scene.light:
            lx, ly, lz, brightness = self.scene.light
        else:
            lx, ly, lz, brightness = 0.35, 0.8, 1.0, 1.0
        length = math.sqrt(lx * lx + ly * ly + lz * lz) or 1
        light = (lx / length, ly / length, lz / length)
        diffuse, ambient = 0.85 * brightness, 0.32 * min(brightness, 1.5)
        faces = []
        for part in self.scene.parts:
            base = part.rgb()
            chosen = part.name == self.selected
            # a level floor seen from above goes under everything: shapes resting on it would sort badly
            layer = 0
            if part.kind == "plane" and abs(part.rx) < 1e-9 and abs(part.rz) < 1e-9:
                layer = -1 if eye[1] >= part.y else 1
            for normal, corners in part_faces(part):
                middle = [sum(point[k] for point in corners) / len(corners) for k in range(3)]
                facing = sum(normal[k] * (eye[k] - middle[k]) for k in range(3))
                if facing < 0:
                    if part.kind != "plane":
                        continue
                    normal = tuple(-value for value in normal)
                viewed = clip_near([_view(eye, turn, point) for point in corners])
                if len(viewed) < 3:
                    continue
                depth = sum(point[2] for point in viewed) / len(viewed)
                shade = min(1.0, 0.2 + ambient + diffuse * max(0.0, sum(n * l for n, l in zip(normal, light))))
                fill = hex_color([value * shade for value in base])
                points = [value for point in viewed for value in screen(point)]
                faces.append((layer, depth, points, fill, part.name, chosen))
        faces.sort(key=lambda face: (face[0], face[1]))
        for _layer, _depth, points, fill, name, chosen in faces:
            canvas.create_polygon(points, fill=fill, outline=MOSS_LIGHT if chosen else fill,
                                  width=1, tags=("part", "part:" + name))
        self.draw_game_camera(eye, turn, screen)
        part = self.part()
        if part is not None:
            self.draw_handles(part, eye, turn, screen)
        if not self.scene.parts:
            canvas.create_text(width / 2, height / 2, fill=MUTED, font=ui_font(10),
                               text="no 3d parts yet. add one with the buttons at the top")

    def draw_grid(self, eye, turn, screen, colour):
        canvas = self.canvas
        reach = int(min(60, max(10, self.distance * 2)))
        cx, cz = round(self.target[0]), round(self.target[2])
        for offset in range(-reach, reach + 1):
            for start, end, axis in (((cx + offset, 0, cz - reach), (cx + offset, 0, cz + reach), "x"),
                                     ((cx - reach, 0, cz + offset), (cx + reach, 0, cz + offset), "z")):
                on_axis = (axis == "x" and cx + offset == 0) or (axis == "z" and cz + offset == 0)
                line = clip_near([_view(eye, turn, start), _view(eye, turn, end)], closed=False)
                if len(line) < 2:
                    continue
                fill = ("#b25a5a" if axis == "z" else "#5a7fb2") if on_axis else colour
                canvas.create_line(*screen(line[0]), *screen(line[-1]), fill=fill, width=2 if on_axis else 1)

    def draw_game_camera(self, eye, turn, screen):
        position = self.scene.camera
        if math.dist(eye, position) < 1.5:  # looking from the game camera itself
            return
        yaw, pitch = (math.radians(value) for value in self.scene.camera_turn)
        forward = (math.sin(yaw) * math.cos(pitch), -math.sin(pitch), -math.cos(yaw) * math.cos(pitch))
        right = (math.cos(yaw), 0, math.sin(yaw))
        up = (right[1] * forward[2] - right[2] * forward[1], right[2] * forward[0] - right[0] * forward[2],
              right[0] * forward[1] - right[1] * forward[0])
        tip = [position[k] + forward[k] * 0.9 for k in range(3)]
        corners = [[tip[k] + (right[k] * sx + up[k] * sy) * 0.45 for k in range(3)]
                   for sx, sy in ((-1, -0.75), (1, -0.75), (1, 0.75), (-1, 0.75))]
        segments = [(position, corner) for corner in corners] + [
            (corners[i], corners[(i + 1) % 4]) for i in range(4)]
        for start, end in segments:
            line = clip_near([_view(eye, turn, start), _view(eye, turn, end)], closed=False)
            if len(line) >= 2:
                self.canvas.create_line(*screen(line[0]), *screen(line[-1]), fill=NUMBER, width=2)
        label = _view(eye, turn, position)
        if label[2] <= NEAR:
            x, y = screen(label)
            self.canvas.create_text(x, y - px(12), text="game camera", fill=NUMBER, font=ui_font(8))

    def draw_handles(self, part, eye, turn, screen):
        middle = (part.x, part.y, part.z)
        reach = part.extent() + 0.6
        for axis, colour in (((1, 0, 0), "#e06c6c"), ((0, 1, 0), MOSS_LIGHT), ((0, 0, 1), "#6c9ee0")):
            end = tuple(middle[k] + axis[k] * reach for k in range(3))
            line = clip_near([_view(eye, turn, middle), _view(eye, turn, end)], closed=False)
            if len(line) >= 2:
                self.canvas.create_line(*screen(line[0]), *screen(line[-1]), fill=colour, width=2,
                                        arrow="last", arrowshape=(px(8), px(10), px(3)))
