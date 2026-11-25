"""the gublan runtime for programs turned into python by gublan studio.

it gives a translated program everything gublan has built in: its functions (sin works in degrees, round
goes half up...), windows, shapes, text, pictures, buttons, text boxes, keys, the mouse, sound and saving.
text-only programs need nothing else. windows and sound need pygame:  py -m pip install pygame-ce
"""

import colorsys
import json
import math
import os
import random as _random
import re
import sys
import time as _time

# python's own versions of the names gublan reuses (gublan's len, str, round... are defined below)
_len, _str, _int, _round, _range, _min, _max, _abs, _sum, _map, _filter, _any, _all, _zip, _pow, _type = (
    len, str, int, round, range, min, max, abs, sum, map, filter, any, all, zip, pow, type)
_enumerate = enumerate

pi = math.pi
dt = 0
screen_width, screen_height = 800, 600
buttons = {}
ui = ""
tests = {}

_started = _time.monotonic()
_save_name = "program"


class GublanError(Exception):
    """an error in the program (the same ones gublan shows)."""


class Vector:
    def __init__(self, *parts):
        self.parts = [float(part) if isinstance(part, float) else part for part in parts]

    x = property(lambda self: self.parts[0])
    y = property(lambda self: self.parts[1])
    z = property(lambda self: self.parts[2] if _len(self.parts) > 2 else 0)

    def _other(self, other):
        return other.parts if isinstance(other, Vector) else [other] * _len(self.parts)

    def __add__(self, other):
        return Vector(*[a + b for a, b in _zip(self.parts, self._other(other))])

    __radd__ = __add__

    def __sub__(self, other):
        return Vector(*[a - b for a, b in _zip(self.parts, self._other(other))])

    def __rsub__(self, other):
        return Vector(*[b - a for a, b in _zip(self.parts, self._other(other))])

    def __mul__(self, other):
        return Vector(*[a * b for a, b in _zip(self.parts, self._other(other))])

    __rmul__ = __mul__

    def __truediv__(self, other):
        return Vector(*[a / b for a, b in _zip(self.parts, self._other(other))])

    def __neg__(self):
        return Vector(*[-a for a in self.parts])

    def __eq__(self, other):
        return isinstance(other, Vector) and self.parts == other.parts

    def __hash__(self):
        return hash(tuple(self.parts))

    def __repr__(self):
        return f"vec{_len(self.parts)}({', '.join(str(part) for part in self.parts)})"


# ----- values ---------------------------------------------------------------------------------------------------
def str(value):
    """turn a value into the same friendly text gublan shows (true, none, 2 instead of 2.0)."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "none"
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer() and _abs(value) < 1e15:
            return _str(_int(value))
        return f"{value:.10g}"
    if isinstance(value, _str):
        return value
    if isinstance(value, Vector):
        return f"vec{_len(value.parts)}(" + ", ".join(str(part) for part in value.parts) + ")"
    if isinstance(value, list):
        return "[" + ", ".join(_item(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{key}: {_item(item)}" for key, item in value.items()) + "}"
    if callable(value):
        return "function"
    return _str(value)


string = str


def _item(value):
    return f'"{value}"' if isinstance(value, _str) else str(value)


def message(error):
    """the text of an error, for catch."""
    if isinstance(error, (GublanError, ValueError)):
        return _str(error)
    if isinstance(error, ZeroDivisionError):
        return "cannot divide by zero"
    if isinstance(error, (KeyError, IndexError)):
        return f"there is nothing at {error}"
    return _str(error) or _type(error).__name__


def missing(name):
    def fail(*_args):
        raise GublanError(f"'{name}' is not available outside gublan")
    return fail


def field(base, key):
    """a.key: a field of a map, a part of a vector or something about an object on screen."""
    if isinstance(base, _str):
        return _object_field(base, key)
    if isinstance(base, Vector):
        return getattr(base, key)
    if isinstance(base, dict):
        if key not in base:
            raise GublanError(f"the map has no key '{key}'")
        return base[key]
    if isinstance(base, (list, _str)) and key in ("length", "size", "count"):
        return _len(base)
    raise GublanError(f"'{str(base)}' has no '{key}'")


def set_field(base, key, value):
    if isinstance(base, _str):
        _set_object_field(base, key, value)
    elif isinstance(base, dict):
        base[key] = value
    elif isinstance(base, Vector) and key in "xyz":
        base.parts["xyz".index(key)] = value
    else:
        raise GublanError(f"'{str(base)}' has no '{key}' to change")


def steps(start, end, step=1):
    """the numbers of 'for i = start to end step n' (the end is included)."""
    if step == 0:
        raise GublanError("a for loop step cannot be zero")
    value = start
    while (step > 0 and value <= end) or (step < 0 and value >= end):
        yield value
        value += step


def each(value):
    """what 'for x in value' goes through: a list, the letters of text, the names in a map or 0 up to a number."""
    if isinstance(value, dict):
        return list(value.keys())
    if isinstance(value, (list, _str)):
        return list(value)
    if isinstance(value, (_int, float)) and not isinstance(value, bool):
        return list(_range(_int(value)))
    raise GublanError(f"can't go through '{str(value)}' with for")


def remove_at(container, key):
    del container[key]


def insert(items, position, value):
    items.insert(position, value)


def remove(items, value):
    if value in items:
        items.remove(value)


def shuffle_list(items):
    _random.shuffle(items)


def sort_list(items, backwards=False):
    items.sort(reverse=backwards)


def check(passed, source):
    """assert: stop with a message when something that should be true is not."""
    if not passed:
        raise GublanError(f"assert failed: {source}")


class _Killed(SystemExit):
    """kill: the program stops and its window closes."""


def kill():
    raise _Killed(0)


def time():
    return _time.monotonic() - _started


def wait(seconds):
    end = _time.monotonic() + max(0.0, float(seconds))
    while True:
        left = end - _time.monotonic()
        if left <= 0:
            return
        if _screen is not None:
            _pump()
            _render()
            _time.sleep(min(left, 1 / 60))
        else:
            _time.sleep(left)


# ----- math --------------------------------------------------------------------------------------------------------
def _number(value, what="value"):
    if isinstance(value, bool) or not isinstance(value, (_int, float)):
        raise GublanError(f"{what} must be a number, but got '{str(value)}'")
    return value


def abs(x):
    if isinstance(x, Vector):
        return mag(x)
    return _abs(x)


def min(*values):
    return _min(values[0] if _len(values) == 1 and isinstance(values[0], list) else values)


def max(*values):
    return _max(values[0] if _len(values) == 1 and isinstance(values[0], list) else values)


def round(x, digits=0):
    if digits:
        return _round(x, _int(digits))
    return _int(math.floor(x + 0.5))


def floor(x):
    return math.floor(x)


def ceil(x):
    return math.ceil(x)


def sqrt(x):
    return math.sqrt(x)


def sin(degrees):
    return math.sin(math.radians(degrees))


def cos(degrees):
    return math.cos(math.radians(degrees))


def tan(degrees):
    return math.tan(math.radians(degrees))


def asin(x):
    return math.degrees(math.asin(x))


def acos(x):
    return math.degrees(math.acos(x))


def atan(x):
    return math.degrees(math.atan(x))


def atan2(y, x):
    return math.degrees(math.atan2(y, x))


def rad(degrees):
    return math.radians(degrees)


def deg(radians):
    return math.degrees(radians)


def clamp(x, low, high):
    return _max(low, _min(high, x))


def lerp(a, b, t):
    return a + (b - a) * t


def sign(x):
    return (x > 0) - (x < 0)


def dist(*args):
    if _len(args) == 2:
        return math.dist(args[0].parts, args[1].parts)
    return math.dist(args[:2], args[2:4])


def mag(vector):
    return math.sqrt(_sum(part * part for part in vector.parts))


def pow(x, n):
    return x ** n


def log(x, base=None):
    return math.log(x) if base is None else math.log(x, base)


def exp(x):
    return math.exp(x)


def wrap(x, low, high):
    return low + (x - low) % (high - low)


def remap(x, low1, high1, low2, high2):
    return low2 + (x - low1) * (high2 - low2) / (high1 - low1)


def approach(x, target, step):
    step = _abs(step)
    return _min(x + step, target) if x < target else _max(x - step, target)


def angleto(*args):
    if _len(args) == 2:
        (x1, y1), (x2, y2) = args[0].parts[:2], args[1].parts[:2]
    else:
        x1, y1, x2, y2 = args
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def random(low=None, high=None):
    if low is None:
        return _random.random()
    if low > high:
        low, high = high, low
    if isinstance(low, _int) and isinstance(high, _int):
        return _random.randint(low, high)
    return _random.uniform(low, high)


def randint(low, high):
    low, high = _int(low), _int(high)
    return _random.randint(_min(low, high), _max(low, high))


def chance(percent):
    return _random.random() * 100 < percent


def vec2(x, y):
    return Vector(x, y)


def vec3(x, y, z):
    return Vector(x, y, z)


def _noise_hash(x, y):
    n = (x * 374761393 + y * 668265263) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def noise(x, y=0.0):
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = x - x0, y - y0
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    top = _noise_hash(x0, y0) + (_noise_hash(x0 + 1, y0) - _noise_hash(x0, y0)) * fx
    bottom = _noise_hash(x0, y0 + 1) + (_noise_hash(x0 + 1, y0 + 1) - _noise_hash(x0, y0 + 1)) * fx
    return top + (bottom - top) * fy


def hsv(hue, saturation, value):
    red, green, blue = colorsys.hsv_to_rgb((hue % 360) / 360, clamp(saturation, 0, 1), clamp(value, 0, 1))
    return [_int(_round(red * 255)), _int(_round(green * 255)), _int(_round(blue * 255))]


# ----- text ----------------------------------------------------------------------------------------------------------
def num(value):
    if isinstance(value, (_int, float)) and not isinstance(value, bool):
        return value
    text = _str(value).strip()
    try:
        return _int(text) if re.fullmatch(r"-?\d+", text) else float(text)
    except ValueError:
        raise GublanError(f"'{str(value)}' is not a number") from None


number = num


def int(value):
    return _int(num(value) if isinstance(value, _str) else value)


def len(value):
    return _len(value)


def type(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (_int, float)):
        return "number"
    if isinstance(value, _str):
        return "text"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "map"
    if isinstance(value, Vector):
        return f"vec{_len(value.parts)}"
    if callable(value):
        return "function"
    return "none" if value is None else "value"


def upper(text):
    return str(text).upper()


def lower(text):
    return str(text).lower()


def trim(text):
    return str(text).strip()


def capitalize(text):
    return re.sub(r"\b([a-z])", lambda match: match.group(1).upper(), str(text))


def contains(container, item):
    if isinstance(container, _str):
        return str(item) in container
    return item in container


def join(items, separator=" "):
    return str(separator).join(str(item) for item in items)


def split(text, separator=None):
    text = str(text)
    return text.split(str(separator)) if separator else text.split()


def replace(text, old, new):
    return str(text).replace(str(old), str(new))


def startswith(text, start):
    return str(text).startswith(str(start))


def endswith(text, ending):
    return str(text).endswith(str(ending))


def pad(value, width, fill=" "):
    text, fill = str(value), str(fill)
    if fill == "0" and text.startswith("-"):
        return "-" + text[1:].rjust(_int(width) - 1, "0")
    return text.rjust(_int(width), fill)


def decimals(x, digits):
    return f"{x:.{_int(digits)}f}"


def isnumber(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, (_int, float)):
        return True
    return isinstance(value, _str) and bool(re.fullmatch(r"\s*-?(?:\d+\.?\d*|\.\d+)\s*", value))


def lines(text):
    return str(text).splitlines()


def words(text):
    return str(text).split()


def char(code):
    return chr(_int(code))


def code(letter):
    return ord(str(letter))


def tojson(value):
    return json.dumps(_storable(value))


def fromjson(text):
    try:
        return _restored(json.loads(str(text)))
    except (ValueError, RecursionError):
        raise GublanError("fromjson() got text that isn't json") from None


def textwidth(text, size=None):
    if _pygame() is None:
        return _len(str(text)) * (size or _text_size) // 2
    return _font(size or _text_size).size(str(text))[0]


def date():
    return _time.strftime("%Y-%m-%d")


def clock():
    return _time.strftime("%H:%M")


def now():
    return _time.time()


# ----- lists and little functions -----------------------------------------------------------------------------------
def _sequence(value):
    return list(value.keys()) if isinstance(value, dict) else list(value)


def call(function, *values):
    return function(*values)


def map(items, function):
    return [function(item) for item in _sequence(items)]


def filter(items, function):
    return [item for item in _sequence(items) if function(item)]


def reduce(items, function, start=None):
    items = _sequence(items)
    if start is None:
        start, items = items[0], items[1:]
    for item in items:
        start = function(start, item)
    return start


def find(items, function):
    for item in _sequence(items):
        if function(item):
            return item
    return None


def any(items, function=None):
    return _any(function(item) if function else item for item in _sequence(items))


def every(items, function=None):
    return _all(function(item) if function else item for item in _sequence(items))


def sortby(items, function):
    return sorted(_sequence(items), key=function)


def zip(*lists):
    return [list(group) for group in _zip(*(_sequence(items) for items in lists))]


def slice(value, start, end=None):
    return value[_int(start):None if end is None else _int(end)]


def flat(items):
    out = []
    for item in items:
        out.extend(item if isinstance(item, list) else [item])
    return out


def repeat(value, times):
    return (value if isinstance(value, (list, _str)) else str(value)) * _max(_int(times), 0)


def range(*args):
    return list(_range(*(_int(arg) for arg in args)))


def sum(items):
    return _sum(items)


def sort(items):
    return sorted(items)


def reverse(items):
    return list(reversed(items))


def keys(values):
    return list(values.keys())


def values(values):
    return list(values.values())


def indexof(container, item):
    if isinstance(container, _str):
        return container.find(str(item))
    return container.index(item) if item in container else -1


def choice(items):
    return _random.choice(items)


def shuffle(items):
    mixed = list(items)
    _random.shuffle(mixed)
    return mixed


def unique(items):
    kept = []
    for item in items:
        if item not in kept:
            kept.append(item)
    return kept


def count(container, item):
    if isinstance(container, _str):
        return container.count(str(item)) if str(item) else 0
    return _sum(1 for value in container if value == item)


def average(items):
    return _sum(items) / _len(items)


# ----- added in 1.0.7: more math, lists and maps, text, colours and timers ---------------------------------------------
EASINGS = ("linear", "in", "out", "inout", "smooth", "bounce", "elastic", "back")


def ease(t, kind="inout"):
    t = 0.0 if t < 0 else 1.0 if t > 1 else float(t)
    kind = _str(kind).strip().lower()
    if kind == "linear":
        return t
    if kind == "in":
        return t * t
    if kind == "out":
        return 1 - (1 - t) * (1 - t)
    if kind == "inout":
        return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2
    if kind == "smooth":
        return t * t * (3 - 2 * t)
    if kind == "bounce":
        n, d = 7.5625, 2.75
        if t < 1 / d:
            return n * t * t
        if t < 2 / d:
            t -= 1.5 / d
            return n * t * t + 0.75
        if t < 2.5 / d:
            t -= 2.25 / d
            return n * t * t + 0.9375
        t -= 2.625 / d
        return n * t * t + 0.984375
    if kind == "elastic":
        return t if t in (0.0, 1.0) else 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1
    if kind == "back":
        c1 = 1.70158
        return 1 + (c1 + 1) * (t - 1) ** 3 + c1 * (t - 1) ** 2
    raise GublanError(f"'{kind}' is not an easing. try: {', '.join(EASINGS)}")


def _listed(value):
    return list(value) if isinstance(value, _str) else value


def hypot(x, y):
    return math.hypot(x, y)


def fract(x):
    return x - math.floor(x)


def smoothstep(low, high, x):
    if high == low:
        return 0.0 if x < low else 1.0
    t = clamp((x - low) / (high - low), 0, 1)
    return t * t * (3 - 2 * t)


def snap(x, step):
    if step == 0:
        return x
    snapped = math.floor(x / step + 0.5) * step
    return _int(snapped) if isinstance(x, _int) and isinstance(step, _int) else snapped


def between(x, low, high):
    return low <= x <= high


def gcd(a, b):
    return math.gcd(_int(a), _int(b))


def median(items):
    if not items:
        raise GublanError("median() of an empty list has no middle")
    ordered = sorted(items)
    middle = _len(ordered) // 2
    return ordered[middle] if _len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def product(items):
    return math.prod(items)


def first(items):
    items = _listed(items)
    return items[0] if items else None


def last(items):
    items = _listed(items)
    return items[-1] if items else None


def take(items, n):
    return items[:_max(0, _int(n))]


def drop(items, n):
    return items[_max(0, _int(n)):]


def chunk(items, size):
    size = _int(size)
    if size < 1:
        raise GublanError("chunk() needs a size of 1 or more")
    items = _listed(items)
    return [items[index:index + size] for index in _range(0, _len(items), size)]


def enumerate(items):
    return [[index, item] for index, item in _enumerate(_listed(items))]


def minby(items, function):
    items = _listed(items)
    if not items:
        return None
    best, key = items[0], function(items[0])
    for item in items[1:]:
        value = function(item)
        if value < key:
            best, key = item, value
    return best


def maxby(items, function):
    items = _listed(items)
    if not items:
        return None
    best, key = items[0], function(items[0])
    for item in items[1:]:
        value = function(item)
        if value > key:
            best, key = item, value
    return best


def groupby(items, function):
    groups = {}
    for item in _listed(items):
        groups.setdefault(str(function(item)), []).append(item)
    return groups


def without(items, value):
    return [item for item in _listed(items) if item != value]


def fill(value, count):
    return [list(value) if isinstance(value, list) else dict(value) if isinstance(value, dict) else value
            for _ in _range(_max(0, _int(count)))]


def merge(first_map, second_map):
    merged = dict(first_map)
    merged.update(second_map)
    return merged


def get(container, key, default=None):
    if isinstance(container, dict):
        if key in container:
            return container[key]
        return container.get(str(key), default)
    if isinstance(key, bool) or not isinstance(key, (_int, float)) or key != _int(key):
        return default
    index = _int(key)
    return container[index] if -_len(container) <= index < _len(container) else default


def entries(values):
    return [[key, value] for key, value in values.items()]


def frompairs(pairs):
    made = {}
    for pair in pairs:
        if not isinstance(pair, list) or _len(pair) != 2:
            raise GublanError("frompairs() needs a list of [name, value] pairs")
        made[pair[0] if isinstance(pair[0], _str) else str(pair[0])] = pair[1]
    return made


def commas(x):
    text = str(x)
    sign = "-" if text.startswith("-") else ""
    digits, dot, rest = text.lstrip("-").partition(".")
    if not digits.isdigit():
        return text
    return sign + f"{_int(digits):,}" + (dot + rest if dot else "")


def ordinal(n):
    n = _int(n)
    last_two = _abs(n) % 100
    suffix = "th" if 11 <= last_two <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(_abs(n) % 10, "th")
    return f"{n}{suffix}"


def plural(count, word, many=None):
    return f"{str(count)} {str(word) if count == 1 else (str(word) + 's' if many is None else str(many))}"


def wraptext(words_text, width):
    width = _int(width)
    if width < 1:
        raise GublanError("wraptext() needs a width of 1 or more")
    found = []
    for paragraph in str(words_text).split("\n"):
        current = ""
        for word in paragraph.split():
            while _len(word) > width:
                if current:
                    found.append(current)
                    current = ""
                found.append(word[:width])
                word = word[width:]
            if not word:
                continue
            if not current:
                current = word
            elif _len(current) + 1 + _len(word) <= width:
                current += " " + word
            else:
                found.append(current)
                current = word
        found.append(current)
    return found


def mixcolor(first_color, second_color, t):
    one, two = _rgb(first_color), _rgb(second_color)
    t = clamp(t, 0, 1)
    return [_int(math.floor(a + (b - a) * t + 0.5)) for a, b in _zip(one, two)]


def randomcolor():
    return hsv(_random.random() * 360, 0.65, 0.95)


_timers = {}


def cooldown(name, seconds):
    key, now_time = ("cooldown", str(name)), _time.monotonic()
    started = _timers.get(key)
    if started is None or now_time - started >= seconds:
        _timers[key] = now_time
        return True
    return False


def pulse(name, seconds):
    key, now_time = ("pulse", str(name)), _time.monotonic()
    started = _timers.get(key)
    if started is None:
        _timers[key] = now_time
        return False
    if now_time - started >= seconds:
        _timers[key] = now_time
        return True
    return False


def after(name, seconds):
    key, now_time = ("after", str(name)), _time.monotonic()
    if key not in _timers:
        _timers[key] = now_time
        return seconds <= 0
    return now_time - _timers[key] >= seconds


def scrollx():
    return _scroll[0]


def scrolly():
    return _scroll[1]


# ----- saving ----------------------------------------------------------------------------------------------------------
def _storable(value, depth=0):
    """the same json shapes gublan itself saves, so saves and json text work in both."""
    if depth > 32:
        raise GublanError("that value is nested too deeply to save")
    if isinstance(value, Vector):
        return {f"$vec{_len(value.parts)}": list(value.parts)}
    if isinstance(value, list):
        return [_storable(item, depth + 1) for item in value]
    if isinstance(value, dict):
        return {_str(key): _storable(item, depth + 1) for key, item in value.items()}
    if isinstance(value, float) and not math.isfinite(value):
        raise GublanError("only finite numbers can be saved")
    if callable(value):
        raise GublanError("can't save function values")
    return value


def _restored(value):
    if isinstance(value, dict) and _len(value) == 1 and ("$vec2" in value or "$vec3" in value):
        parts = value.get("$vec2") or value.get("$vec3")
        if isinstance(parts, list) and _len(parts) in (2, 3):
            return Vector(*parts)
    if isinstance(value, list):
        return [_restored(item) for item in value]
    if isinstance(value, dict):
        return {key: _restored(item) for key, item in value.items()}
    return value


def _save_path():
    folder = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "GublanGames")
    return os.path.join(folder, re.sub(r"[^\w.-]+", "_", _save_name) + ".json")


def _saves():
    try:
        with open(_save_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_saves(data):
    os.makedirs(os.path.dirname(_save_path()), exist_ok=True)
    with open(_save_path(), "w", encoding="utf-8") as handle:
        json.dump(data, handle)


def save(name, value):
    data = _saves()
    data[str(name)] = _storable(value)
    _write_saves(data)


def load(name, default=0):
    data = _saves()
    return _restored(data[str(name)]) if str(name) in data else default


def saved(name):
    return str(name) in _saves()


def forget(name):
    data = _saves()
    if str(name) == "all":
        data = {}
    else:
        data.pop(str(name), None)
    _write_saves(data)


# ----- the web ---------------------------------------------------------------------------------------------------------
def fetch(url):
    import urllib.request
    if not str(url).startswith("https://"):
        raise GublanError("get only works with https:// addresses")
    with urllib.request.urlopen(str(url), timeout=10) as response:
        return response.read(2_000_000).decode("utf-8", "replace")


# ----- the window ----------------------------------------------------------------------------------------------------
COLORS = {
    "red": (225, 65, 65), "blue": (65, 145, 245), "green": (65, 205, 105), "yellow": (245, 215, 65),
    "white": (240, 240, 240), "moss": (148, 182, 108), "orange": (245, 145, 65), "purple": (170, 115, 225),
    "cyan": (75, 205, 215), "black": (12, 12, 12), "gray": (128, 128, 128), "grey": (128, 128, 128),
    "darkgray": (52, 52, 52), "pink": (240, 130, 190), "brown": (140, 95, 60), "lime": (170, 235, 70),
    "teal": (40, 150, 140), "navy": (25, 40, 90), "gold": (225, 185, 60), "sand": (215, 195, 150),
    "sky": (135, 200, 245), "forest": (40, 95, 55),
}
_KEY_ALIASES = {
    "esc": "escape", "enter": "return", "spacebar": "space", "shift": "left shift", "lshift": "left shift",
    "rshift": "right shift", "ctrl": "left ctrl", "control": "left ctrl", "lctrl": "left ctrl",
    "rctrl": "right ctrl", "alt": "left alt", "lalt": "left alt", "ralt": "right alt", "del": "delete",
    "bksp": "backspace", "pgup": "page up", "pgdn": "page down", "arrowleft": "left", "arrowright": "right",
    "arrowup": "up", "arrowdown": "down",
}

_pg = None
_screen = None
_objects = {}
_title = ""
_background = (12, 12, 12)
_color = "white"
_text_size = 24
_fps = 60
_last_frame = _time.perf_counter()
_fonts = {}
_images = {}
_presses = set()
_clicks = set()
_focus = None
_dragging = None
_cursor_visible = True
_ui_button = None


def _pygame():
    global _pg
    if _pg is None:
        try:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame
            _pg = pygame
        except ImportError:
            _pg = False
    return _pg or None


def _need_pygame():
    if _pygame() is None:
        raise GublanError("windows, shapes and sound need pygame. install it with: py -m pip install pygame-ce")
    return _pg


def _rgb(*args):
    if _len(args) == 3:
        return tuple(_int(clamp(channel, 0, 255)) for channel in args)
    value = args[0] if args else "white"
    if isinstance(value, (list, tuple)) and _len(value) >= 3:
        return tuple(_int(clamp(channel, 0, 255)) for channel in value[:3])
    text = str(value).lower()
    if text in COLORS:
        return COLORS[text]
    if re.fullmatch(r"#[0-9a-f]{6}", text):
        return tuple(_int(text[i:i + 2], 16) for i in (1, 3, 5))
    if re.fullmatch(r"#[0-9a-f]{3}", text):
        return tuple(_int(c * 2, 16) for c in text[1:])
    return COLORS["white"]


def _font(size):
    pygame = _need_pygame()
    if not pygame.font.get_init():
        pygame.font.init()
    size = _max(6, _min(_int(size), 300))
    if size not in _fonts:
        _fonts[size] = pygame.font.Font(None, size)
    return _fonts[size]


def mode(kind="2d"):
    global _screen, _last_frame
    if kind != "2d":
        raise GublanError("only 2d windows can be used outside gublan")
    pygame = _need_pygame()
    pygame.init()
    _screen = pygame.display.set_mode((screen_width, screen_height))
    pygame.display.set_caption(_title or "gublan")
    pygame.mouse.set_visible(_cursor_visible)
    _last_frame = _time.perf_counter()


def window(width, height, title_text=None):
    global screen_width, screen_height, _title
    screen_width, screen_height = _int(width), _int(height)
    if title_text is not None:
        _title = str(title_text)
    if _screen is not None:
        mode("2d")


def title(text):
    global _title
    _title = str(text)
    if _screen is not None:
        _pg.display.set_caption(_title)


def background(*color):
    global _background
    _background = _rgb(*color)


def color(*value):
    global _color
    _color = value if _len(value) == 3 else value[0]


def paint(name, *value):
    chosen = value if _len(value) == 3 else value[0]
    if name == "all":
        for obj in _objects.values():
            obj["color"] = chosen
    else:
        _object(name)["color"] = chosen


def fps(value):
    global _fps
    _fps = value


def textsize(value):
    global _text_size
    _text_size = _int(value)


def _add(name, kind, **parts):
    parts.update(type=kind, color=_color)
    old = _objects.get(str(name))
    if isinstance(old, dict):
        for key in ("layer", "alpha", "fixed"):
            if key in old and key not in parts:
                parts[key] = old[key]
    _objects[str(name)] = parts
    return parts


def ellipse(name, x, y, w, h):
    _add(name, "ellipse", x=x, y=y, w=w, h=h)


def polygon(name, points):
    if _len(points) % 2:
        raise GublanError("polygon points come in pairs: x y x y x y")
    if _len(points) < 6:
        raise GublanError("a polygon needs at least three points")
    xs, ys = points[0::2], points[1::2]
    left, top = _min(xs), _min(ys)
    width, height = _max(1, _max(xs) - left), _max(1, _max(ys) - top)
    _add(name, "polygon", x=left, y=top, w=width, h=height, pw=width, ph=height,
         points=[(x - left, y - top) for x, y in _zip(xs, ys)])


# ----- the view, effects and tweens ------------------------------------------------------------------------------------
_scroll = [0, 0]
_shake = None
_shake_offset = (0.0, 0.0)
_particles = []
_tweens = []
_effects_time = _time.perf_counter()
_layer_surface = None


def scroll(x, y):
    _scroll[0], _scroll[1] = x, y


def shake(strength, seconds=0.3):
    global _shake, _shake_offset
    if strength < 0 or seconds < 0:
        raise GublanError("shake strength and time can't be negative")
    _shake = [float(strength), float(seconds), float(seconds)] if strength and seconds else None
    if not _shake:
        _shake_offset = (0.0, 0.0)


def particles(x, y, count=20, speed=160):
    count = _int(count)
    if not 0 <= count <= 500:
        raise GublanError("particles can make from 0 to 500 at a time")
    shade = _rgb(*_color) if isinstance(_color, (tuple, list)) and _len(_color) == 3 else _rgb(_color)
    for _ in _range(count):
        angle = _random.uniform(0, math.tau)
        velocity = speed * _random.uniform(0.25, 1.0)
        life = _random.uniform(0.45, 1.0)
        _particles.append([float(x), float(y), math.cos(angle) * velocity, math.sin(angle) * velocity, life, life,
                           shade, _random.uniform(3, 6)])
    if _len(_particles) > 2000:
        del _particles[:_len(_particles) - 2000]


_TWEEN_FIELDS = {"x": "x", "y": "y", "z": "z", "w": "w", "width": "w", "h": "h", "height": "h", "r": "r",
                 "radius": "r", "angle": "angle", "rotation": "angle", "opacity": "alpha", "alpha": "alpha",
                 "size": "size"}


def _apply_tween(obj, key, value):
    if key in ("x", "y") and obj["type"] == "line":
        obj[key + "2"] += value - obj[key]
    if key in ("w", "h") and obj.get("surface") is not None:
        width, height = obj["surface"].get_size()
        width, height = (value, height) if key == "w" else (width, value)
        if width >= 1 and height >= 1:
            source = obj.setdefault("source", obj["surface"])
            obj["surface"] = _pg.transform.smoothscale(source, (_int(width), _int(height)))
        return
    if key == "alpha":
        value = clamp(value, 0, 1)
    elif key in ("w", "h", "r", "size"):
        value = _max(0, value)
    obj[key] = value


def tween(name, field, value, seconds, easing="inout"):
    global _tweens
    obj = _object(name)
    key = _TWEEN_FIELDS.get(_str(field).lower())
    pictured = obj.get("surface") is not None
    if key is None or not (key in obj or key == "alpha" or (pictured and key in ("w", "h", "angle"))):
        raise GublanError(f"tween can change x, y, w, h, r, angle or opacity of a {obj['type']}, not '{field}'")
    if seconds < 0:
        raise GublanError("tween time can't be negative")
    easing = _str(easing).lower()
    if easing not in EASINGS:
        raise GublanError(f"'{easing}' is not an easing. try: {', '.join(EASINGS)}")
    if pictured and key in ("w", "h"):
        start_value = obj["surface"].get_size()[0 if key == "w" else 1]
    else:
        start_value = obj.get(key, 1.0 if key == "alpha" else 0.0)
    _tweens = [item for item in _tweens if not (item[0] is obj and item[1] == key)]
    if seconds == 0:
        _apply_tween(obj, key, value)
    else:
        _tweens.append([obj, key, float(start_value), float(value), float(seconds), 0.0, easing])


def opacity(name, value):
    value = clamp(value, 0, 1)
    if name == "all":
        for obj in _objects.values():
            obj["alpha"] = value
        return
    _object(name)["alpha"] = value


def layer(name, value):
    _object(name)["layer"] = value


def fixed(name):
    _object(name)["fixed"] = True


def _tick_effects():
    global _effects_time, _particles, _shake, _shake_offset
    current = _time.perf_counter()
    step = _min(0.1, _max(0.0, current - _effects_time))
    _effects_time = current
    _tick_motion(step)
    for item in list(_tweens):
        obj, key, start_value, target, duration, elapsed, easing = item
        item[5] = elapsed + step
        progress = _min(1.0, item[5] / duration) if duration > 0 else 1.0
        _apply_tween(obj, key, start_value + (target - start_value) * ease(progress, easing))
        if progress >= 1:
            _tweens.remove(item)
    if _particles:
        alive = []
        for particle in _particles:
            particle[4] -= step
            if particle[4] <= 0:
                continue
            particle[0] += particle[2] * step
            particle[1] += particle[3] * step
            particle[3] += 240 * step
            alive.append(particle)
        _particles = alive
    if _shake:
        _shake[1] -= step
        if _shake[1] <= 0:
            _shake, _shake_offset = None, (0.0, 0.0)
        else:
            strength = _shake[0] * _shake[1] / _shake[2]
            _shake_offset = (_random.uniform(-strength, strength), _random.uniform(-strength, strength))


def box(name, x, y, w, h):
    _add(name, "box", x=x, y=y, w=w, h=h)


def circle(name, x, y, r):
    _add(name, "circle", x=x, y=y, r=r)


def line(name, x1, y1, x2, y2, thickness=1):
    _add(name, "line", x=x1, y=y1, x2=x2, y2=y2, width=_max(1, thickness))


def text(name, x, y, words_text):
    _add(name, "text", x=x, y=y, text=str(words_text), size=_text_size)


def _image_file(path):
    pygame = _need_pygame()
    if path not in _images:
        if not pygame.display.get_init() or pygame.display.get_surface() is None:
            raise GublanError("add 'mode 2d' before showing a picture")
        _images[path] = pygame.image.load(path).convert_alpha()
    return _images[path]


def image(name, path, x, y):
    _add(name, "image", x=x, y=y, surface=_image_file(path))


def sprite(name, path, x, y, w, h):
    previous = _objects.get(str(name), {})
    surface = _pg.transform.smoothscale(_image_file(path), (_int(w), _int(h)))
    _add(name, "sprite", x=x, y=y, surface=surface, angle=previous.get("angle", 0))


def spin(name, angle):
    _object(name)["angle"] = angle


def button(variable, x, y, w, h, label):
    buttons.setdefault(variable, 0)
    _add("button:" + variable, "button", x=x, y=y, w=w, h=h, label=str(label), variable=variable)


def ui_button(label):
    global _ui_button
    _ui_button = str(label)


def textbox(name, x, y, w, hint=""):
    old = _objects.get(str(name), {})
    _add(name, "textbox", x=x, y=y, w=w, h=36, hint=str(hint), text=old.get("text", ""),
         cursor=old.get("cursor", 0), submitted=False)


def slider(name, x, y, w, low, high, start=None):
    value = low if start is None else clamp(start, _min(low, high), _max(low, high))
    whole = all(isinstance(v, _int) for v in (low, high))
    _add(name, "slider", x=x, y=y, w=w, h=20, min=low, max=high, value=value, whole=whole)


def checkbox(name, x, y, label):
    _add(name, "checkbox", x=x, y=y, w=22, h=22, label=str(label), checked=False)


def focus(name):
    global _focus
    _focus = None if name is None else str(name)
    if _pg and _screen is not None:
        (_pg.key.start_text_input if _focus else _pg.key.stop_text_input)()


def _object(name):
    name = str(name)
    obj = _objects.get(name) or _objects.get("button:" + name)
    if obj is None:
        raise GublanError(f"there is no object named '{name}'")
    return obj


_ALIASES = {"width": "w", "height": "h", "radius": "r", "rotation": "angle", "depth": "d"}


def _object_field(name, key):
    obj = _object(name)
    key = _ALIASES.get(key, key)
    if key in ("vx", "vy", "vz") and "x" in obj:
        return obj.get(key, 0)
    if key == "visible":
        return not obj.get("hidden", False)
    if key == "focused":
        return _focus == name
    if key == "submitted":
        was, obj["submitted"] = obj.get("submitted", False), False
        return was
    if key in ("w", "h") and key not in obj and obj.get("surface") is not None:
        width, height = obj["surface"].get_size()
        return width if key == "w" else height
    if key not in obj:
        raise GublanError(f"object '{name}' has no '{key}'")
    return obj[key]


def _set_object_field(name, key, value):
    obj = _object(name)
    key = _ALIASES.get(key, key)
    if key == "visible":
        obj["hidden"] = not value
    elif key == "text" and obj["type"] == "textbox":
        obj["text"], obj["cursor"] = str(value), _len(str(value))
    elif key in ("vx", "vy", "vz"):
        for part in ("vx", "vy", "vz"):
            obj.setdefault(part, 0)
        obj[key] = value
    else:
        obj[key] = value


def move(name, dx, dy=None, dz=None):
    obj = _object(name)
    if isinstance(dx, Vector):
        dx, dy = dx.x, dx.y
    obj["x"] += dx
    obj["y"] += dy
    if obj["type"] == "line":
        obj["x2"] += dx
        obj["y2"] += dy


def place(name, x, y, z=None):
    obj = _object(name)
    if obj["type"] == "line":
        obj["x2"] += x - obj["x"]
        obj["y2"] += y - obj["y"]
    obj["x"], obj["y"] = x, y


def resize(name, w, h=None):
    obj = _object(name)
    h = w if h is None else h
    if obj["type"] in ("ellipse", "polygon"):
        obj["w"], obj["h"] = w, h
    elif obj["type"] == "circle":
        obj["r"] = w
    elif obj["type"] == "text":
        obj["size"] = _int(w)
    elif obj.get("surface") is not None:
        obj["surface"] = _pg.transform.smoothscale(obj["surface"], (_int(w), _int(h)))
    else:
        obj["w"], obj["h"] = w, h


def hide(name):
    _object(name)["hidden"] = True


def show(name):
    _object(name)["hidden"] = False


def delete(name):
    global _focus
    _objects.pop(str(name), None) or _objects.pop("button:" + str(name), None)
    if _focus == str(name):
        _focus = None


def exists(name):
    return str(name) in _objects or ("button:" + str(name)) in _objects


def animate(name, x, y, seconds):
    obj = _object(name)
    start_x, start_y, started = obj["x"], obj["y"], _time.monotonic()
    while True:
        progress = 1.0 if seconds <= 0 else _min(1.0, (_time.monotonic() - started) / seconds)
        eased = progress * progress * (3 - 2 * progress)
        place(name, start_x + (x - start_x) * eased, start_y + (y - start_y) * eased)
        if _screen is not None:
            _pump()
            _render()
        if progress >= 1:
            return
        _time.sleep(1 / 60)


def _shape(obj):
    if obj["type"] == "circle":
        return ("circle", obj["x"], obj["y"], _abs(obj["r"]))
    if obj.get("surface") is not None:
        width, height = obj["surface"].get_size()
        return ("rect", obj["x"], obj["y"], width, height)
    if obj["type"] == "text":
        width, height = _font(obj["size"]).size(obj["text"]) if _pygame() else (0, 0)
        return ("rect", obj["x"], obj["y"], width, height)
    return ("rect", obj["x"], obj["y"], obj.get("w", 0), obj.get("h", 0))


def touching(first, second):
    a, b = _object(first), _object(second)
    if a.get("hidden") or b.get("hidden"):
        return False
    a, b = _shape(a), _shape(b)
    if a[0] == b[0] == "circle":
        return (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2 <= (a[3] + b[3]) ** 2
    if a[0] == "rect" and b[0] == "rect":
        return a[1] <= b[1] + b[3] and b[1] <= a[1] + a[3] and a[2] <= b[2] + b[4] and b[2] <= a[2] + a[4]
    circle_shape, rect = (a, b) if a[0] == "circle" else (b, a)
    _, cx, cy, radius = circle_shape
    _, rx, ry, width, height = rect
    nx, ny = _min(_max(cx, rx), rx + width), _min(_max(cy, ry), ry + height)
    return (cx - nx) ** 2 + (cy - ny) ** 2 <= radius ** 2


def overlap(first, second):
    def rect(value):
        if isinstance(value, _str):
            shape = _shape(_object(value))
            return (shape[1] - shape[3], shape[2] - shape[3], shape[3] * 2, shape[3] * 2) if shape[0] == "circle" \
                else shape[1:]
        if isinstance(value, dict):
            return value["x"], value["y"], value["w"], value["h"]
        return tuple(value)
    a, b = rect(first), rect(second)
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


# ----- drawing ---------------------------------------------------------------------------------------------------------
def _alpha_layer(screen):
    global _layer_surface
    size = screen.get_size()
    if _layer_surface is None or _layer_surface.get_size() != size:
        _layer_surface = _pg.Surface(size, _pg.SRCALPHA)
    _layer_surface.set_alpha(255)
    _layer_surface.fill((0, 0, 0, 0))
    return _layer_surface


_UI_KINDS = ("button", "textbox", "slider", "checkbox")


def _render():
    pygame = _pg
    screen = _screen
    _tick_effects()
    screen.fill(_background)
    mouse = pygame.mouse.get_pos()
    if _ui_button is not None:
        pygame.draw.rect(screen, (109, 137, 79), (20, 20, 180, 38))
        screen.blit(_font(20).render(_ui_button, True, (240, 240, 240)), (32, 30))
    items = [(name, obj) for name, obj in _objects.items() if not obj.get("hidden")]
    if _any(obj.get("layer") for _, obj in items):
        items.sort(key=lambda item: item[1].get("layer", 0))
    world = (_shake_offset[0] - _scroll[0], _shake_offset[1] - _scroll[1])
    for name, obj in items:
        alpha = obj.get("alpha", 1)
        if alpha <= 0:
            continue
        offset = (0, 0) if obj["type"] in _UI_KINDS or obj.get("fixed") else world
        if alpha < 1:
            target = _alpha_layer(screen)
            _draw_one(target, name, obj, offset, mouse)
            target.set_alpha(_int(alpha * 255))
            screen.blit(target, (0, 0))
        else:
            _draw_one(screen, name, obj, offset, mouse)
    if _particles:
        target = _alpha_layer(screen)
        for x, y, _vx, _vy, life, total, shade, size in _particles:
            fade = clamp(life / total, 0, 1)
            side = _max(1, _int(size * (0.4 + 0.6 * fade)))
            pygame.draw.rect(target, (*shade[:3], _int(255 * fade)),
                             (_int(x + world[0] - side / 2), _int(y + world[1] - side / 2), side, side))
        screen.blit(target, (0, 0))
    pygame.display.flip()


def _draw_one(screen, name, obj, offset, mouse):
    pygame = _pg
    ox, oy = offset
    kind, shade = obj["type"], _rgb(obj["color"]) if not isinstance(obj["color"], tuple) else _rgb(*obj["color"])
    if kind == "box":
        pygame.draw.rect(screen, shade, (obj["x"] + ox, obj["y"] + oy, obj["w"], obj["h"]))
    elif kind == "circle":
        pygame.draw.circle(screen, shade, (_int(obj["x"] + ox), _int(obj["y"] + oy)), _int(obj["r"]))
    elif kind == "ellipse":
        pygame.draw.ellipse(screen, shade, (obj["x"] + ox, obj["y"] + oy, _max(1, obj["w"]), _max(1, obj["h"])))
    elif kind == "polygon":
        scale_x = obj["w"] / obj["pw"] if obj["pw"] else 1
        scale_y = obj["h"] / obj["ph"] if obj["ph"] else 1
        pygame.draw.polygon(screen, shade, [(obj["x"] + ox + px * scale_x, obj["y"] + oy + py * scale_y)
                                            for px, py in obj["points"]])
    elif kind == "line":
        pygame.draw.line(screen, shade, (obj["x"] + ox, obj["y"] + oy), (obj["x2"] + ox, obj["y2"] + oy),
                         _int(obj["width"]))
    elif kind == "text":
        screen.blit(_font(obj["size"]).render(obj["text"], True, shade), (obj["x"] + ox, obj["y"] + oy))
    elif kind in ("image", "sprite"):
        surface = obj["surface"]
        if obj.get("angle"):
            turned = pygame.transform.rotate(surface, -obj["angle"])
            width, height = surface.get_size()
            screen.blit(turned, turned.get_rect(center=(obj["x"] + ox + width / 2, obj["y"] + oy + height / 2)))
        else:
            screen.blit(surface, (obj["x"] + ox, obj["y"] + oy))
    elif kind == "button":
        rect = pygame.Rect(obj["x"], obj["y"], obj["w"], obj["h"])
        pygame.draw.rect(screen, (148, 182, 108) if rect.collidepoint(mouse) else (82, 105, 61), rect)
        label = _font(24).render(obj["label"], True, (240, 240, 240))
        screen.blit(label, label.get_rect(center=rect.center))
    elif kind == "textbox":
        rect = pygame.Rect(obj["x"], obj["y"], obj["w"], obj["h"])
        pygame.draw.rect(screen, (23, 23, 23), rect)
        pygame.draw.rect(screen, (148, 182, 108) if _focus == name else (90, 90, 90), rect, 2)
        font = _font(24)
        shown = obj["text"] or ("" if _focus == name else obj["hint"])
        label = font.render(shown, True, shade if obj["text"] else (120, 120, 120))
        screen.blit(label, (rect.x + 8, rect.y + (rect.h - label.get_height()) // 2))
        if _focus == name and _int(_time.monotonic() * 2) % 2 == 0:
            caret = rect.x + 8 + font.size(obj["text"][:obj["cursor"]])[0]
            pygame.draw.line(screen, (148, 182, 108), (caret, rect.y + 7), (caret, rect.bottom - 7), 2)
    elif kind == "slider":
        share = 0 if obj["max"] == obj["min"] else (obj["value"] - obj["min"]) / (obj["max"] - obj["min"])
        middle = obj["y"] + obj["h"] // 2
        pygame.draw.rect(screen, (60, 60, 60), (obj["x"], middle - 3, obj["w"], 6))
        pygame.draw.rect(screen, shade, (obj["x"], middle - 3, _int(obj["w"] * share), 6))
        pygame.draw.circle(screen, shade, (_int(obj["x"] + obj["w"] * share), middle), 9)
        label = _font(20).render(str(obj["value"]), True, (200, 200, 200))
        screen.blit(label, (obj["x"] + obj["w"] + 12, middle - label.get_height() // 2))
    elif kind == "checkbox":
        rect = pygame.Rect(obj["x"], obj["y"], obj["w"], obj["h"])
        pygame.draw.rect(screen, (23, 23, 23), rect)
        pygame.draw.rect(screen, shade if obj["checked"] else (110, 110, 110), rect, 2)
        if obj["checked"]:
            pygame.draw.lines(screen, shade, False, [(rect.x + 5, rect.centery), (rect.x + 10, rect.bottom - 6),
                                                      (rect.right - 5, rect.y + 6)], 3)
        label = _font(24).render(obj["label"], True, (229, 229, 229))
        screen.blit(label, (rect.right + 8, rect.centery - label.get_height() // 2))


def _slide(obj, mouse_x):
    share = clamp((mouse_x - obj["x"]) / _max(1, obj["w"]), 0, 1)
    value = obj["min"] + (obj["max"] - obj["min"]) * share
    obj["value"] = _int(_round(value)) if obj["whole"] else _round(value, 4)


def _pump():
    global ui, _dragging
    pygame = _pg
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            raise SystemExit(0)
        if event.type == pygame.KEYDOWN:
            box_ = _objects.get(_focus)
            if box_ is not None and box_["type"] == "textbox":
                _type_key(box_, event)
            else:
                _presses.add(event.key)
        elif event.type == pygame.TEXTINPUT:
            box_ = _objects.get(_focus)
            if box_ is not None and box_["type"] == "textbox":
                box_["text"] = box_["text"][:box_["cursor"]] + event.text + box_["text"][box_["cursor"]:]
                box_["cursor"] += _len(event.text)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            _clicks.add(event.button)
            if event.button != 1:
                continue
            mx, my = event.pos
            _click_list.append((mx, my))
            del _click_list[:-16]
            if _ui_button is not None and 20 <= mx <= 200 and 20 <= my <= 58:
                ui = _ui_button
            chosen = None
            for name, obj in list(_objects.items()):
                if obj.get("hidden") or obj["type"] not in ("button", "textbox", "slider", "checkbox"):
                    continue
                width = obj["w"] + (8 + _font(24).size(obj["label"])[0] if obj["type"] == "checkbox" else 0)
                grow = 6 if obj["type"] == "slider" else 0
                if not pygame.Rect(obj["x"], obj["y"] - grow, width, obj["h"] + grow * 2).collidepoint(mx, my):
                    continue
                if obj["type"] == "button":
                    buttons[obj["variable"]] = 1
                elif obj["type"] == "textbox":
                    chosen = name
                elif obj["type"] == "checkbox":
                    obj["checked"] = not obj["checked"]
                else:
                    _dragging = name
                    _slide(obj, mx)
            focus(chosen)
        elif event.type == pygame.MOUSEBUTTONUP:
            _dragging = None
            for obj in _objects.values():
                if obj["type"] == "button":
                    buttons[obj["variable"]] = 0
        elif event.type == pygame.MOUSEMOTION and _dragging in _objects:
            _slide(_objects[_dragging], event.pos[0])


def _type_key(obj, event):
    pygame = _pg
    if event.key == pygame.K_BACKSPACE and obj["cursor"] > 0:
        obj["text"] = obj["text"][:obj["cursor"] - 1] + obj["text"][obj["cursor"]:]
        obj["cursor"] -= 1
    elif event.key == pygame.K_DELETE:
        obj["text"] = obj["text"][:obj["cursor"]] + obj["text"][obj["cursor"] + 1:]
    elif event.key == pygame.K_LEFT:
        obj["cursor"] = _max(0, obj["cursor"] - 1)
    elif event.key == pygame.K_RIGHT:
        obj["cursor"] = _min(_len(obj["text"]), obj["cursor"] + 1)
    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
        obj["submitted"] = True
    elif event.key == pygame.K_ESCAPE:
        focus(None)


def clear():
    if _screen is not None:
        _render()


def frame():
    global dt, _last_frame, _frame_clicks, _click_list, _frames_drawn
    if _screen is not None:
        _pump()
        _render()
    else:
        _tick_effects()
    _frame_clicks, _click_list = _click_list, []
    _frames_drawn += 1
    target = 1.0 / _max(1, _fps)
    left = _last_frame + target - _time.perf_counter()
    if left > 0:
        _time.sleep(left)
    current = _time.perf_counter()
    dt = _min(0.25, current - _last_frame)
    _last_frame = current


# ----- keys and the mouse -----------------------------------------------------------------------------------------------
def _key(name):
    pygame = _need_pygame()
    name = _KEY_ALIASES.get(str(name).strip().lower(), str(name).strip().lower())
    try:
        return pygame.key.key_code(name)
    except ValueError:
        raise GublanError(f"'{name}' is not a key name. try left, right, up, down, space, a, 1") from None


def _typing():
    return _focus is not None and _objects.get(_focus, {}).get("type") == "textbox"


def keydown(name):
    if _screen is None:
        raise GublanError("add 'mode 2d' before you check the keyboard")
    _pump()
    return bool(_pg.key.get_pressed()[_key(name)]) and not _typing()


def keypressed(name):
    if _screen is None:
        raise GublanError("add 'mode 2d' before you check the keyboard")
    _pump()
    code_ = _key(name)
    if code_ in _presses:
        _presses.discard(code_)
        return True
    return False


def mousex():
    return _pg.mouse.get_pos()[0] if _screen is not None else 0


def mousey():
    return _pg.mouse.get_pos()[1] if _screen is not None else 0


def mousedown(which="left"):
    if _screen is None:
        return False
    return bool(_pg.mouse.get_pressed(3)[{"left": 0, "middle": 1, "right": 2}[str(which)]])


def mousepressed(which="left"):
    if _screen is None:
        return False
    _pump()
    number_ = {"left": 1, "middle": 2, "right": 3}[str(which)]
    if number_ in _clicks:
        _clicks.discard(number_)
        return True
    return False


def cursor(visible):
    global _cursor_visible
    _cursor_visible = bool(visible)
    if _screen is not None:
        _pg.mouse.set_visible(_cursor_visible)


# ----- questions and messages -------------------------------------------------------------------------------------------
def _dialog(question, answer=None):
    pygame = _pg
    _render()
    shade = pygame.Surface(_screen.get_size(), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 170))
    _screen.blit(shade, (0, 0))
    width = _min(screen_width - 40, 520)
    rect = pygame.Rect((screen_width - width) // 2, screen_height // 2 - 70, width, 140)
    pygame.draw.rect(_screen, (23, 23, 23), rect)
    pygame.draw.rect(_screen, (148, 182, 108), rect, 2)
    _screen.blit(_font(24).render(question, True, (229, 229, 229)), (rect.x + 16, rect.y + 18))
    if answer is not None:
        field_rect = pygame.Rect(rect.x + 16, rect.y + 56, rect.w - 32, 34)
        pygame.draw.rect(_screen, (12, 12, 12), field_rect)
        _screen.blit(_font(24).render(answer + "|", True, (240, 240, 240)), (field_rect.x + 8, field_rect.y + 8))
    hint = "press enter" if answer is not None else "press enter or click to close"
    _screen.blit(_font(18).render(hint, True, (130, 130, 130)), (rect.x + 16, rect.bottom - 26))
    pygame.display.flip()


def ask(question):
    if _screen is None:
        answer = input(f"{question} ")
    else:
        pygame = _pg
        answer = ""
        pygame.key.start_text_input()
        try:
            while True:
                _dialog(str(question), answer)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        raise SystemExit(0)
                    if event.type == pygame.TEXTINPUT:
                        answer += event.text
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_BACKSPACE:
                            answer = answer[:-1]
                        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            raise StopIteration
                _time.sleep(1 / 60)
        except StopIteration:
            pass
        finally:
            if _focus is None:
                pygame.key.stop_text_input()
    cleaned = answer.strip()
    if re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:[.][0-9]+)?", cleaned):
        return float(cleaned) if "." in cleaned else _int(cleaned)
    return answer


def popup(text_value):
    if _screen is None:
        print(text_value)
        return
    pygame = _pg
    while True:
        _dialog(str(text_value))
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise SystemExit(0)
            if event.type == pygame.MOUSEBUTTONDOWN or (event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE, pygame.K_SPACE)):
                return
        _time.sleep(1 / 60)


# ----- sound ---------------------------------------------------------------------------------------------------------
_sounds = {}
_volume = 1.0


def _mixer():
    pygame = _need_pygame()
    if not pygame.mixer.get_init():
        pygame.mixer.init()
    return pygame.mixer


def sound(path):
    mixer = _mixer()
    if path not in _sounds:
        _sounds[path] = mixer.Sound(path)
    _sounds[path].set_volume(_volume)
    _sounds[path].play()


def music(path):
    mixer = _mixer()
    mixer.music.load(path)
    mixer.music.set_volume(_volume)
    mixer.music.play(-1)


_WAVES = ("square", "sine", "triangle", "saw", "noise")


def beep(frequency, seconds=0.15, wave="square"):
    import array as _array
    wave = _str(wave).lower()
    if not 20 <= frequency <= 20000:
        raise GublanError("beep frequency must be from 20 to 20000 (440 is the a above middle c)")
    if not 0 < seconds <= 5:
        raise GublanError("a beep can last from just above 0 up to 5 seconds")
    if wave not in _WAVES:
        raise GublanError(f"'{wave}' is not a wave. try: {', '.join(_WAVES)}")
    if _pygame() is None:
        return
    mixer = _mixer()
    key = ("beep", frequency, seconds, wave)
    if key not in _sounds:
        rate, _size, channels = mixer.get_init()
        channels = _max(1, channels)
        count = _max(1, _int(rate * seconds))
        samples = _array.array("h")
        for index in _range(count):
            phase = (index * frequency / rate) % 1.0
            if wave == "sine":
                value = math.sin(2 * math.pi * phase)
            elif wave == "square":
                value = 1.0 if phase < 0.5 else -1.0
            elif wave == "triangle":
                value = 4 * _abs(phase - 0.5) - 1
            elif wave == "saw":
                value = 2 * phase - 1
            else:
                value = _random.uniform(-1, 1)
            envelope = _min(1.0, index / (rate * 0.003), (count - index) / (rate * 0.02))
            samples.extend([_int(value * 0.22 * 32767 * envelope)] * channels)
        _sounds[key] = mixer.Sound(buffer=samples.tobytes())
    _sounds[key].set_volume(_volume)
    _sounds[key].play()


def stopmusic():
    if _pygame() and _pg.mixer.get_init():
        _pg.mixer.music.stop()


def stopsounds():
    if _pygame() and _pg.mixer.get_init():
        _pg.mixer.stop()


def volume(value):
    global _volume
    _volume = clamp(value, 0, 1)
    if _pygame() and _pg.mixer.get_init():
        _pg.mixer.music.set_volume(_volume)


# ----- added in 1.0.9: files, movement, clicks and more functions ------------------------------------------------------
import csv as _csv  # noqa: E402
import io as _io  # noqa: E402

_gravity = 0
_click_list = []
_frame_clicks = []
_frames_drawn = 0
_base_dir = None
_FILE_LIMIT = 10 * 1024 * 1024
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _whole(value):
    return _int(value) if isinstance(value, float) and value.is_integer() else value


def seed(value):
    _random.seed(value if isinstance(value, (_int, float)) and not isinstance(value, bool) else str(value))


def pop(items, position=None):
    if not isinstance(items, list):
        raise GublanError("pop needs a list")
    if not items:
        raise GublanError("that list is empty, so there is nothing to take")
    if position is None:
        return items.pop()
    if isinstance(position, bool) or not isinstance(position, _int):
        raise GublanError("list positions must be whole numbers")
    if not -_len(items) <= position < _len(items):
        raise GublanError(f"position {position} is past the end (length {_len(items)})")
    return items.pop(position)


def velocity(name, vx, vy, vz=0):
    obj = _object(name)
    if "x" not in obj or "y" not in obj:
        raise GublanError(f"a {obj['type']} can't move by itself")
    if vz:
        raise GublanError("only 3d shapes can move along z")
    obj["vx"], obj["vy"], obj["vz"] = vx, vy, 0


def gravity(amount):
    global _gravity
    _gravity = amount


def _tick_motion(step):
    if step <= 0:
        return
    for obj in list(_objects.values()):
        if not isinstance(obj, dict) or "vx" not in obj:
            continue
        if _gravity:
            obj["vy"] += _gravity * step
        dx, dy = obj["vx"] * step, obj["vy"] * step
        obj["x"] += dx
        obj["y"] += dy
        if obj["type"] == "line":
            obj["x2"] += dx
            obj["y2"] += dy


def screenshot(path):
    if _screen is None:
        raise GublanError("add 'mode 2d' before you take a screenshot")
    path = _file_path(path, "screenshot")
    if not path.lower().endswith(".png"):
        path += ".png"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _pg.image.save(_screen, path)


# dates and time
def year():
    return _time.localtime().tm_year


def month():
    return _time.localtime().tm_mon


def day():
    return _time.localtime().tm_mday


def hour():
    return _time.localtime().tm_hour


def minute():
    return _time.localtime().tm_min


def second():
    return _time.localtime().tm_sec


def weekday():
    return _WEEKDAYS[_time.localtime().tm_wday]


def timetext(seconds):
    sign = "-" if seconds < 0 else ""
    seconds = _int(math.floor(_abs(seconds)))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{sign}{hours}:{minutes:02d}:{seconds:02d}"
    return f"{sign}{minutes}:{seconds:02d}"


# text
def left(value, count):
    count = _int(count)
    return "" if count <= 0 else str(value)[:count]


def right(value, count):
    count = _int(count)
    return "" if count <= 0 else str(value)[-count:]


def matches(value, pattern):
    regex = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in str(pattern))
    return re.fullmatch(regex, str(value), re.IGNORECASE | re.DOTALL) is not None


# vectors and numbers
def _vector(value, name):
    if isinstance(value, Vector):
        return [float(part) for part in value.parts], Vector
    if isinstance(value, list) and _len(value) in (2, 3) and _all(
            not isinstance(item, bool) and isinstance(item, (_int, float)) for item in value):
        return [float(item) for item in value], list
    raise GublanError(f"{name}() needs a vec2, a vec3 or a list of numbers, got '{str(value)}'")


def normalize(value):
    values, kind = _vector(value, "normalize")
    length = math.sqrt(_sum(v * v for v in values))
    values = [v / length for v in values] if length else values
    return Vector(*values) if kind is Vector else [_whole(v) for v in values]


def dot(first, second):
    a, b = _vector(first, "dot")[0], _vector(second, "dot")[0]
    if _len(a) != _len(b):
        raise GublanError("dot() needs two vectors of the same size")
    return _whole(_sum(x * y for x, y in _zip(a, b)))


def cross(first, second):
    a, b = _vector(first, "cross")[0], _vector(second, "cross")[0]
    ax, ay, az = a + [0.0] * (3 - _len(a))
    bx, by, bz = b + [0.0] * (3 - _len(b))
    return Vector(ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)


def percent(part, whole):
    return 0 if not whole else _whole(part / whole * 100)


# lists
def sample(items, count):
    if not isinstance(items, (list, _str)):
        raise GublanError(f"sample() needs a list, got '{str(items)}'")
    items = list(items)
    return _random.sample(items, _max(0, _min(_int(count), _len(items))))


def findindex(items, function):
    for index, item in _enumerate(_sequence(items)):
        if function(item):
            return index
    return -1


# the mouse on objects
def _centre(value):
    if isinstance(value, Vector):
        return [float(part) for part in value.parts]
    obj = _object(value)
    if obj["type"] == "line":
        return [(obj["x"] + obj["x2"]) / 2, (obj["y"] + obj["y2"]) / 2]
    shape = _shape(obj)
    if shape[0] == "circle":
        return [shape[1], shape[2]]
    return [shape[1] + shape[3] / 2, shape[2] + shape[4] / 2]


def _point_on(obj, mx, my):
    if obj.get("hidden"):
        return False
    if obj["type"] not in _UI_KINDS and not obj.get("fixed"):
        mx, my = mx + _scroll[0], my + _scroll[1]
    shape = _shape(obj)
    if shape[0] == "circle":
        return (mx - shape[1]) ** 2 + (my - shape[2]) ** 2 <= shape[3] ** 2
    _, x, y, w, h = shape
    return x <= mx <= x + w and y <= my <= y + h


def clicked(name):
    if _screen is None:
        raise GublanError("add 'mode 2d' before you check the mouse")
    obj = _object(name)
    if _frames_drawn == 0:
        _pump()
        for click in list(_click_list):
            if _point_on(obj, *click):
                _click_list.remove(click)
                return True
        return False
    return _any(_point_on(obj, *click) for click in _frame_clicks)


def hovering(name):
    if _screen is None:
        raise GublanError("add 'mode 2d' before you check the mouse")
    _pump()
    return _point_on(_object(name), *_pg.mouse.get_pos())


def distance(first, second):
    a, b = _centre(first), _centre(second)
    size = _min(_len(a), _len(b))
    return _whole(math.sqrt(_sum((x - y) ** 2 for x, y in _zip(a[:size], b[:size]))))


# files. they stay inside the program's folder
def _folder():
    if _base_dir:
        return _base_dir
    main = sys.modules.get("__main__")
    where = getattr(main, "__file__", None)
    return os.path.dirname(os.path.abspath(where)) if where else os.getcwd()


def _file_path(relative, what="file"):
    relative = str(relative).strip()
    if not relative:
        raise GublanError(f"give the {what} a name, like notes.txt")
    cleaned = relative.replace("\\", "/")
    if cleaned.startswith("/") or ":" in cleaned or ".." in cleaned.split("/"):
        raise GublanError("file paths stay inside your program's folder, like notes.txt or saves/one.txt")
    base = _folder()
    pieces = [piece for piece in cleaned.split("/") if piece not in ("", ".")]
    return os.path.abspath(os.path.join(base, *pieces)) if pieces else base


def _read_text(relative):
    path = _file_path(relative)
    if os.path.isdir(path):
        raise GublanError(f"'{relative}' is a folder, not a file")
    if not os.path.isfile(path):
        raise GublanError(f"file '{relative}' was not found")
    if os.path.getsize(path) > _FILE_LIMIT:
        raise GublanError(f"file '{relative}' is too big to read (the most is 10 mb)")
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline=None) as handle:
        return handle.read()


def _write_text(relative, value, append=False):
    path = _file_path(relative)
    if os.path.isdir(path):
        raise GublanError(f"'{relative}' is a folder, not a file")
    if _len(value) > _FILE_LIMIT:
        raise GublanError("that is too much to write at once (the most is 10 mb)")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if append and os.path.isfile(path) and os.path.getsize(path):
        with open(path, "rb") as handle:
            handle.seek(-1, os.SEEK_END)
            if handle.read(1) not in (b"\n", b"\r"):
                value = "\n" + value
    with open(path, "a" if append else "w", encoding="utf-8", newline="") as handle:
        handle.write(value)


def _file_value(value):
    return "\n".join(str(item) for item in value) if isinstance(value, list) else str(value)


def writefile(path, value):
    _write_text(path, _file_value(value))


def appendfile(path, value):
    _write_text(path, _file_value(value) + "\n", append=True)


def readfile(path):
    return _read_text(path)


def readlines(path):
    return _read_text(path).splitlines()


def deletefile(relative):
    path = _file_path(relative)
    if path == _folder():
        raise GublanError("gublan won't delete your program's own folder")
    if os.path.isdir(path):
        if os.listdir(path):
            raise GublanError(f"folder '{relative}' is not empty. delete the files in it first")
        os.rmdir(path)
    elif os.path.exists(path):
        os.remove(path)


def makefolder(relative):
    path = _file_path(relative, "folder")
    if os.path.isfile(path):
        raise GublanError(f"'{relative}' is already a file")
    os.makedirs(path, exist_ok=True)


def _move_file(source_name, target_name, keep):
    source, target = _file_path(source_name), _file_path(target_name)
    if not os.path.isfile(source):
        raise GublanError(f"file '{source_name}' was not found")
    if os.path.isdir(target):
        target = os.path.join(target, os.path.basename(source))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if keep:
        with open(source, "rb") as reading, open(target, "wb") as writing:
            writing.write(reading.read())
    else:
        os.replace(source, target)


def copyfile(source, target):
    _move_file(source, target, True)


def renamefile(source, target):
    _move_file(source, target, False)


def fileexists(path):
    return os.path.exists(_file_path(path))


def isfolder(path):
    return os.path.isdir(_file_path(path))


def filesize(path):
    where = _file_path(path)
    if not os.path.isfile(where):
        raise GublanError(f"file '{path}' was not found")
    return os.path.getsize(where)


def listfiles(path=""):
    where = _file_path(path, "folder") if str(path).strip() else _folder()
    if not os.path.isdir(where):
        raise GublanError(f"'{path}' is not a folder")
    return sorted(os.listdir(where), key=_str.lower)


def filename(path):
    return str(path).replace("\\", "/").rstrip("/").split("/")[-1]


def extension(path):
    base = str(path).replace("\\", "/").split("/")[-1]
    return base.rsplit(".", 1)[1] if "." in base.strip(".") else ""


def _csv_value(cell):
    cleaned = cell.strip()
    if re.fullmatch(r"-?(?:0|[1-9][0-9]*)", cleaned):
        return _int(cleaned)
    if re.fullmatch(r"-?(?:0|[1-9][0-9]*)[.][0-9]+", cleaned):
        return float(cleaned)
    return cell


def fromcsv(value):
    return [[_csv_value(cell) for cell in row] for row in _csv.reader(_io.StringIO(str(value)))]


def tocsv(rows):
    if not isinstance(rows, list):
        raise GublanError(f"tocsv() needs a list of rows, got '{str(rows)}'")
    if rows and not _all(isinstance(row, list) for row in rows):
        rows = [rows]
    out = _io.StringIO()
    writer = _csv.writer(out, lineterminator="\n")
    for row in rows:
        writer.writerow([str(cell) for cell in row])
    return out.getvalue().rstrip("\n")


# ----- starting -----------------------------------------------------------------------------------------------------------
def run_tests(functions):
    """run every test_ function (py game.py --test). prints pass or fail for each and gives back True if all passed."""
    passed = failed = 0
    for name, function in [*functions.items()]:
        if not name.startswith("test_") or not callable(function):
            continue
        label = (function.__doc__ or name[5:].replace("_", " ")).strip()
        if label.startswith("test "):
            label = label[5:]
        try:
            function()
        except _Killed:
            pass
        except Exception as error:  # noqa: BLE001 - a failing test is reported, not raised
            failed += 1
            print(f"fail: {label}: {message(error)}")
            continue
        passed += 1
        print(f"pass: {label}")
    print(f"{passed} passed, {failed} failed")
    return failed == 0


def start(main, name="program"):
    """run the program. errors are shown like gublan shows them, and a window stays open until it is closed."""
    global _save_name
    _save_name = name
    if "--test" in sys.argv[1:]:
        _save_name = name + "_tests"
        raise SystemExit(0 if run_tests(main.__globals__) else 1)
    folder = os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv and sys.argv[0] else os.getcwd()
    try:
        os.chdir(folder)
    except OSError:
        pass
    try:
        main()
    except _Killed:
        if _pg:
            _pg.quit()
        return
    except SystemExit:
        pass
    except KeyboardInterrupt:
        pass
    except Exception as error:  # noqa: BLE001 - every problem is shown to the player
        print(f"error: {message(error)}", file=sys.stderr)
        if _screen is not None:
            try:
                popup(f"error: {message(error)}")
            except SystemExit:
                pass
        raise SystemExit(1)
    try:
        while _screen is not None:
            frame()
    except SystemExit:
        pass
    finally:
        if _pg:
            _pg.quit()
