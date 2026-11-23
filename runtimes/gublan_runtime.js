// the gublan runtime for programs turned into javascript by gublan studio.
//
// it gives a translated program everything gublan has built in: its functions (sin works in degrees, round
// goes half up...), a canvas with shapes, text, pictures, buttons and text boxes, keys, the mouse, sound and
// saving. in a web page it draws on a <canvas>; in node (node game.js) text programs work the same way.
(function (root) {
  "use strict";
  const G = {};
  const inBrowser = typeof document !== "undefined";
  const started = Date.now();

  G.pi = Math.PI;
  G.dt = 0;
  G.screen_width = 800;
  G.screen_height = 600;
  G.buttons = {};
  G.ui = "";
  G.tests = {};

  class GublanError extends Error {}
  G.GublanError = GublanError;
  const KILL = { kill: true };
  G.KILL = KILL;

  class Vector {
    constructor(...parts) { this.parts = parts; }
    get x() { return this.parts[0]; }
    set x(v) { this.parts[0] = v; }
    get y() { return this.parts[1]; }
    set y(v) { this.parts[1] = v; }
    get z() { return this.parts.length > 2 ? this.parts[2] : 0; }
    set z(v) { this.parts[2] = v; }
  }
  G.Vector = Vector;

  const isMap = (v) => v !== null && typeof v === "object" && !Array.isArray(v) && !(v instanceof Vector);
  const isNumber = (v) => typeof v === "number";
  const fail = (text) => { throw new GublanError(text); };

  // ----- values ------------------------------------------------------------------------------------------
  function str(value) {
    if (value === true) return "true";
    if (value === false) return "false";
    if (value === null || value === undefined) return "none";
    if (typeof value === "number") {
      if (Number.isInteger(value) && Math.abs(value) < 1e15) return String(value);
      if (Number.isNaN(value)) return "nan";
      if (!Number.isFinite(value)) return value > 0 ? "inf" : "-inf";
      return general(value);
    }
    if (typeof value === "string") return value;
    if (value instanceof Vector) return `vec${value.parts.length}(${value.parts.map(str).join(", ")})`;
    if (Array.isArray(value)) return "[" + value.map(item).join(", ") + "]";
    if (typeof value === "function") return "function";
    if (isMap(value)) return "{" + Object.keys(value).map((k) => `${k}: ${item(value[k])}`).join(", ") + "}";
    return String(value);
  }
  // the same as "%.10g": ten significant digits, no trailing zeros, e-notation for very big or small numbers
  function general(value) {
    const [mantissa, power] = value.toExponential(9).split("e");
    const exponent = Number(power);
    const strip = (text) => (text.includes(".") ? text.replace(/0+$/, "").replace(/\.$/, "") : text);
    if (exponent < -4 || exponent >= 10) {
      return strip(mantissa) + "e" + (exponent < 0 ? "-" : "+") + String(Math.abs(exponent)).padStart(2, "0");
    }
    return strip(value.toFixed(Math.max(0, 9 - exponent)));
  }
  const item = (v) => (typeof v === "string" ? `"${v}"` : str(v));
  G.str = str;
  G.string = str;

  G.print = function (text) {
    const line = str(text);
    console.log(line);
    if (inBrowser) {
      const log = document.getElementById("gublan-log");
      if (log) log.textContent += line + "\n";
    }
  };

  G.message = function (error) {
    if (error === KILL) throw error;
    if (error instanceof Error) return error.message;
    return str(error);
  };

  G.missing = (name) => () => fail(`'${name}' is not available outside gublan`);

  G.truthy = function (value) {
    if (value === null || value === undefined || value === false) return false;
    if (typeof value === "number") return value !== 0;
    if (typeof value === "string" || Array.isArray(value)) return value.length > 0;
    if (value instanceof Vector) return true;
    if (isMap(value)) return Object.keys(value).length > 0;
    return true;
  };

  function eq(a, b) {
    if (a === b) return true;
    if (a instanceof Vector && b instanceof Vector) return eq(a.parts, b.parts);
    if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((v, i) => eq(v, b[i]));
    if (isMap(a) && isMap(b)) {
      const ka = Object.keys(a), kb = Object.keys(b);
      return ka.length === kb.length && ka.every((k) => k in b && eq(a[k], b[k]));
    }
    return false;
  }
  G.eq = eq;

  G.contains = function (container, value) {
    if (typeof container === "string") return container.includes(str(value));
    if (Array.isArray(container)) return container.some((v) => eq(v, value));
    if (isMap(container)) return Object.prototype.hasOwnProperty.call(container, String(value));
    fail("'in' needs a list, map or text on the right");
  };

  G.at = function (list, index) {
    if (isMap(list)) {
      if (!Object.prototype.hasOwnProperty.call(list, index)) fail(`the map has no key '${str(index)}'`);
      return list[index];
    }
    if (list instanceof Vector) return list.parts[index];
    if (typeof index !== "number") fail("list positions are numbers");
    const items = typeof list === "string" ? Array.from(list) : list;
    if (index < 0) index += items.length;
    const value = items[index];
    if (value === undefined) fail(`list index ${index} is out of range`);
    return value;
  };

  G.put = function (container, key, value) {
    if (Array.isArray(container)) {
      if (typeof key !== "number") fail("list positions are numbers");
      if (key < 0) key += container.length;
      if (key < 0 || key >= container.length) fail(`list index ${key} is out of range`);
      container[key] = value;
    } else if (container instanceof Vector || isMap(container)) {
      container[key] = value;
    } else {
      fail(`can't change '${str(container)}' with []`);
    }
  };

  function vectorMath(a, b, op) {
    const parts = a instanceof Vector ? a.parts : b.parts;
    const left = a instanceof Vector ? a.parts : parts.map(() => a);
    const right = b instanceof Vector ? b.parts : parts.map(() => b);
    return new Vector(...left.map((v, i) => op(v, right[i])));
  }

  G.add = function (a, b) {
    if (typeof a === "string" || typeof b === "string") return str(a) + str(b);
    if (Array.isArray(a) && Array.isArray(b)) return a.concat(b);
    if (a instanceof Vector || b instanceof Vector) return vectorMath(a, b, (x, y) => x + y);
    if (!isNumber(a) || !isNumber(b)) fail(`can't do math with '${str(a)}' and '${str(b)}'`);
    return a + b;
  };

  G.sub = function (a, b) {
    if (a instanceof Vector || b instanceof Vector) return vectorMath(a, b, (x, y) => x - y);
    return a - b;
  };

  G.mul = function (a, b) {
    if ((typeof a === "string" || Array.isArray(a)) && isNumber(b)) return G.repeat(a, b);
    if ((typeof b === "string" || Array.isArray(b)) && isNumber(a)) return G.repeat(b, a);
    if (a instanceof Vector || b instanceof Vector) return vectorMath(a, b, (x, y) => x * y);
    return a * b;
  };

  G.div = (a, b) => {
    if (b === 0) fail("cannot divide by zero");
    if (a instanceof Vector || b instanceof Vector) return vectorMath(a, b, (x, y) => x / y);
    return a / b;
  };
  G.idiv = (a, b) => Math.floor(G.div(a, b));
  G.mod = (a, b) => {
    if (b === 0) fail("cannot divide by zero");
    return a - b * Math.floor(a / b);
  };

  G.field = function (base, key) {
    if (typeof base === "string") return objectField(base, key);
    if (base instanceof Vector) return base[key];
    if (Array.isArray(base) && ["length", "size", "count"].includes(key)) return base.length;
    if (isMap(base)) {
      if (!(key in base)) fail(`the map has no key '${key}'`);
      return base[key];
    }
    fail(`'${str(base)}' has no '${key}'`);
  };

  G.set_field = function (base, key, value) {
    if (typeof base === "string") return setObjectField(base, key, value);
    if (base instanceof Vector || isMap(base)) { base[key] = value; return; }
    fail(`'${str(base)}' has no '${key}' to change`);
  };

  G.steps = function (start, end, step = 1) {
    if (step === 0) fail("a for loop step cannot be zero");
    const out = [];
    for (let v = start; step > 0 ? v <= end : v >= end; v += step) out.push(v);
    return out;
  };

  G.each = function (value) {
    if (Array.isArray(value)) return value.slice();
    if (typeof value === "string") return Array.from(value);
    if (isMap(value)) return Object.keys(value);
    if (typeof value === "number") return G.range(Math.trunc(value));
    fail(`can't go through '${str(value)}' with for`);
  };

  G.remove_at = function (container, key) {
    if (Array.isArray(container)) {
      if (key < 0) key += container.length;
      if (key < 0 || key >= container.length) fail(`list index ${key} is out of range`);
      container.splice(key, 1);
    } else {
      if (!(key in container)) fail(`the map has no key '${key}'`);
      delete container[key];
    }
  };
  G.insert = (items, position, value) => {
    items.splice(position < 0 ? items.length + position : position, 0, value);
  };
  G.remove = (items, value) => {
    const index = items.findIndex((v) => eq(v, value));
    if (index >= 0) items.splice(index, 1);
  };
  const compare = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  G.shuffle_list = (items) => {
    for (let i = items.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [items[i], items[j]] = [items[j], items[i]];
    }
  };
  G.sort_list = (items, backwards) => {
    items.sort(compare);
    if (backwards) items.reverse();
  };

  G.check = (passed, source) => { if (!passed) fail(`assert failed: ${source}`); };
  G.kill = () => { throw KILL; };
  G.time = () => (Date.now() - started) / 1000;
  const sleep = (seconds) => new Promise((done) => setTimeout(done, Math.max(0, seconds * 1000)));
  G.wait = (seconds) => sleep(seconds);

  // ----- math ----------------------------------------------------------------------------------------------
  const radians = (d) => (d * Math.PI) / 180;
  const degrees = (r) => (r * 180) / Math.PI;
  const listOr = (args) => (args.length === 1 && Array.isArray(args[0]) ? args[0] : args);
  Object.assign(G, {
    abs: (x) => (x instanceof Vector ? G.mag(x) : Math.abs(x)),
    min: (...args) => listOr(args).reduce((a, b) => (b < a ? b : a)),
    max: (...args) => listOr(args).reduce((a, b) => (b > a ? b : a)),
    round: (x, digits = 0) => {
      if (!digits) return Math.floor(x + 0.5);
      const scale = 10 ** digits;
      return Math.round(x * scale) / scale;
    },
    floor: Math.floor, ceil: Math.ceil, sqrt: Math.sqrt,
    sin: (d) => Math.sin(radians(d)), cos: (d) => Math.cos(radians(d)), tan: (d) => Math.tan(radians(d)),
    asin: (x) => degrees(Math.asin(x)), acos: (x) => degrees(Math.acos(x)), atan: (x) => degrees(Math.atan(x)),
    atan2: (y, x) => degrees(Math.atan2(y, x)), rad: radians, deg: degrees,
    clamp: (x, low, high) => Math.max(low, Math.min(high, x)),
    lerp: (a, b, t) => a + (b - a) * t,
    sign: (x) => (x > 0 ? 1 : x < 0 ? -1 : 0),
    dist: (...args) => {
      if (args.length === 2) return Math.hypot(...args[0].parts.map((v, i) => v - args[1].parts[i]));
      return Math.hypot(args[2] - args[0], args[3] - args[1]);
    },
    mag: (v) => Math.hypot(...v.parts),
    pow: (x, n) => x ** n,
    log: (x, base) => (base === undefined ? Math.log(x) : Math.log(x) / Math.log(base)),
    exp: Math.exp,
    wrap: (x, low, high) => low + G.mod(x - low, high - low),
    remap: (x, l1, h1, l2, h2) => l2 + ((x - l1) * (h2 - l2)) / (h1 - l1),
    approach: (x, target, step) => {
      step = Math.abs(step);
      return x < target ? Math.min(x + step, target) : Math.max(x - step, target);
    },
    angleto: (...args) => {
      const [x1, y1, x2, y2] = args.length === 2 ? [...args[0].parts.slice(0, 2), ...args[1].parts.slice(0, 2)] : args;
      return degrees(Math.atan2(y2 - y1, x2 - x1));
    },
    random: (low, high) => {
      if (low === undefined) return Math.random();
      if (low > high) [low, high] = [high, low];
      if (Number.isInteger(low) && Number.isInteger(high)) return low + Math.floor(Math.random() * (high - low + 1));
      return low + Math.random() * (high - low);
    },
    randint: (low, high) => {
      low = Math.trunc(low); high = Math.trunc(high);
      if (low > high) [low, high] = [high, low];
      return low + Math.floor(Math.random() * (high - low + 1));
    },
    chance: (percent) => Math.random() * 100 < percent,
    vec2: (x, y) => new Vector(x, y),
    vec3: (x, y, z) => new Vector(x, y, z),
    hsv: (hue, saturation, value) => {
      const h = (G.mod(hue, 360)) / 60, s = G.clamp(saturation, 0, 1), v = G.clamp(value, 0, 1);
      const i = Math.floor(h) % 6, f = h - Math.floor(h);
      const p = v * (1 - s), q = v * (1 - s * f), t = v * (1 - s * (1 - f));
      const rgb = [[v, t, p], [q, v, p], [p, v, t], [p, q, v], [t, p, v], [v, p, q]][i];
      return rgb.map((c) => Math.round(c * 255));
    },
  });

  // noise: the same numbers gublan gives (32-bit multiplications done carefully)
  const mul32 = (a, b) => Math.imul(a | 0, b | 0) >>> 0;
  function noiseHash(x, y) {
    let n = (mul32(x, 374761393) + mul32(y, 668265263)) >>> 0;
    n = mul32((n ^ (n >>> 13)) >>> 0, 1274126177);
    return ((n ^ (n >>> 16)) & 0xffff) / 65535;
  }
  G.noise = function (x, y = 0) {
    const x0 = Math.floor(x), y0 = Math.floor(y);
    let fx = x - x0, fy = y - y0;
    fx = fx * fx * (3 - 2 * fx);
    fy = fy * fy * (3 - 2 * fy);
    const top = noiseHash(x0, y0) + (noiseHash(x0 + 1, y0) - noiseHash(x0, y0)) * fx;
    const bottom = noiseHash(x0, y0 + 1) + (noiseHash(x0 + 1, y0 + 1) - noiseHash(x0, y0 + 1)) * fx;
    return top + (bottom - top) * fy;
  };

  // ----- text ------------------------------------------------------------------------------------------------
  Object.assign(G, {
    num: (value) => {
      if (typeof value === "number") return value;
      const text = String(value).trim();
      if (!/^-?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$/i.test(text)) fail(`'${str(value)}' is not a number`);
      return Number(text);
    },
    int: (value) => Math.trunc(typeof value === "string" ? G.num(value) : value),
    len: (value) => (isMap(value) ? Object.keys(value).length : value.length),
    type: (value) => {
      if (typeof value === "boolean") return "boolean";
      if (typeof value === "number") return "number";
      if (typeof value === "string") return "text";
      if (Array.isArray(value)) return "list";
      if (value instanceof Vector) return `vec${value.parts.length}`;
      if (typeof value === "function") return "function";
      if (value === null || value === undefined) return "none";
      return "map";
    },
    upper: (t) => str(t).toUpperCase(),
    lower: (t) => str(t).toLowerCase(),
    trim: (t) => str(t).trim(),
    capitalize: (t) => str(t).replace(/\b([a-z])/g, (m) => m.toUpperCase()),
    join: (items, separator = " ") => items.map(str).join(str(separator)),
    split: (text, separator) => {
      text = str(text);
      if (separator === undefined || separator === null || separator === "") return text.split(/\s+/).filter(Boolean);
      return text.split(str(separator));
    },
    replace: (text, old, now) => str(text).split(str(old)).join(str(now)),
    startswith: (t, s) => str(t).startsWith(str(s)),
    endswith: (t, s) => str(t).endsWith(str(s)),
    pad: (value, width, fill = " ") => {
      const text = str(value);
      fill = str(fill);
      if (fill === "0" && text.startsWith("-")) return "-" + text.slice(1).padStart(width - 1, "0");
      return text.padStart(width, fill);
    },
    decimals: (x, digits) => x.toFixed(digits),
    isnumber: (v) => typeof v === "number" || (typeof v === "string" && /^\s*-?(\d+\.?\d*|\.\d+)\s*$/.test(v)),
    lines: (t) => str(t).split(/\r?\n/),
    words: (t) => str(t).split(/\s+/).filter(Boolean),
    char: (c) => String.fromCodePoint(c),
    code: (letter) => str(letter).codePointAt(0),
    tojson: (v) => jsonText(storable(v)),
    fromjson: (t) => {
      let parsed;
      try { parsed = JSON.parse(str(t)); } catch (error) { fail("fromjson() got text that isn't json"); }
      return restored(parsed);
    },
    date: () => new Date().toISOString().slice(0, 10),
    clock: () => new Date().toTimeString().slice(0, 5),
    now: () => Date.now() / 1000,
  });

  G.number = G.num;

  // ----- lists and little functions ----------------------------------------------------------------------------
  const seq = (v) => (isMap(v) ? Object.keys(v) : Array.from(v));
  Object.assign(G, {
    call: (f, ...values) => f(...values),
    map: (items, f) => seq(items).map((v) => f(v)),
    filter: (items, f) => seq(items).filter((v) => G.truthy(f(v))),
    reduce: (items, f, start) => {
      items = seq(items);
      if (start === undefined) { start = items[0]; items = items.slice(1); }
      return items.reduce((total, v) => f(total, v), start);
    },
    find: (items, f) => { const found = seq(items).find((v) => G.truthy(f(v))); return found === undefined ? null : found; },
    any: (items, f) => seq(items).some((v) => G.truthy(f ? f(v) : v)),
    every: (items, f) => seq(items).every((v) => G.truthy(f ? f(v) : v)),
    sortby: (items, f) => seq(items).map((v, i) => [f(v), i, v]).sort((a, b) => compare(a[0], b[0]) || a[1] - b[1]).map((e) => e[2]),
    zip: (...lists) => {
      const all = lists.map(seq);
      const size = Math.min(...all.map((l) => l.length));
      return Array.from({ length: size }, (_, i) => all.map((l) => l[i]));
    },
    slice: (value, start, end) => {
      const size = value.length;
      const fix = (i) => (i === null || i === undefined ? undefined : i < 0 ? Math.max(0, size + i) : i);
      return value.slice(fix(start), fix(end));
    },
    flat: (items) => items.flatMap((v) => (Array.isArray(v) ? v : [v])),
    repeat: (value, times) => {
      times = Math.max(0, Math.trunc(times));
      if (Array.isArray(value)) return Array.from({ length: times }, () => value).flat();
      return str(value).repeat(times);
    },
    range: (...args) => {
      let [start, stop, step] = args.length === 1 ? [0, args[0], 1] : [args[0], args[1], args[2] || 1];
      const out = [];
      for (let v = Math.trunc(start); step > 0 ? v < stop : v > stop; v += step) out.push(v);
      return out;
    },
    sum: (items) => items.reduce((a, b) => a + b, 0),
    sort: (items) => items.slice().sort(compare),
    reverse: (items) => items.slice().reverse(),
    keys: (values) => Object.keys(values),
    values: (values) => Object.values(values),
    indexof: (container, value) => (typeof container === "string" ? container.indexOf(str(value))
      : container.findIndex((v) => eq(v, value))),
    choice: (items) => items[Math.floor(Math.random() * items.length)],
    shuffle: (items) => { const copy = items.slice(); G.shuffle_list(copy); return copy; },
    unique: (items) => items.filter((v, i) => items.findIndex((w) => eq(v, w)) === i),
    count: (container, value) => {
      if (typeof container === "string") return str(value) ? container.split(str(value)).length - 1 : 0;
      return container.filter((v) => eq(v, value)).length;
    },
    average: (items) => G.sum(items) / items.length,
  });

  // ----- added in 1.0.7: more math, lists and maps, text, colours and timers --------------------------------------
  const EASINGS = ["linear", "in", "out", "inout", "smooth", "bounce", "elastic", "back"];
  G.ease = (t, kind = "inout") => {
    t = t < 0 ? 0 : t > 1 ? 1 : t;
    kind = str(kind).trim().toLowerCase();
    if (kind === "linear") return t;
    if (kind === "in") return t * t;
    if (kind === "out") return 1 - (1 - t) * (1 - t);
    if (kind === "inout") return t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
    if (kind === "smooth") return t * t * (3 - 2 * t);
    if (kind === "bounce") {
      const n = 7.5625, d = 2.75;
      if (t < 1 / d) return n * t * t;
      if (t < 2 / d) { t -= 1.5 / d; return n * t * t + 0.75; }
      if (t < 2.5 / d) { t -= 2.25 / d; return n * t * t + 0.9375; }
      t -= 2.625 / d; return n * t * t + 0.984375;
    }
    if (kind === "elastic") return t === 0 || t === 1 ? t : 2 ** (-10 * t) * Math.sin((t * 10 - 0.75) * ((2 * Math.PI) / 3)) + 1;
    if (kind === "back") { const c = 1.70158; return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2; }
    return fail(`'${kind}' is not an easing. try: ${EASINGS.join(", ")}`);
  };
  const listOf = (v) => (typeof v === "string" ? Array.from(v) : v);
  function colorChannels(value) {
    if (Array.isArray(value) && (value.length === 3 || value.length === 4)) return value.slice(0, 3).map((c) => G.clamp(Math.trunc(c), 0, 255));
    const text = str(value).toLowerCase();
    if (COLORS[text]) return COLORS[text].slice();
    if (/^#[0-9a-f]{6}$/.test(text)) return [1, 3, 5].map((i) => parseInt(text.slice(i, i + 2), 16));
    if (/^#[0-9a-f]{3}$/.test(text)) return [1, 2, 3].map((i) => parseInt(text[i] + text[i], 16));
    return fail(`'${str(value)}' is not a colour. use a name like red, #ff8800 or [255, 136, 0]`);
  }
  const timers = new Map();
  Object.assign(G, {
    hypot: (x, y) => Math.hypot(x, y),
    fract: (x) => x - Math.floor(x),
    smoothstep: (low, high, x) => {
      if (high === low) return x < low ? 0 : 1;
      const t = G.clamp((x - low) / (high - low), 0, 1);
      return t * t * (3 - 2 * t);
    },
    snap: (x, step) => (step === 0 ? x : Math.floor(x / step + 0.5) * step),
    between: (x, low, high) => low <= x && x <= high,
    gcd: (a, b) => { a = Math.abs(Math.trunc(a)); b = Math.abs(Math.trunc(b)); while (b) [a, b] = [b, a % b]; return a; },
    median: (items) => {
      if (!items.length) fail("median() of an empty list has no middle");
      const sorted = items.slice().sort((a, b) => a - b), middle = Math.floor(sorted.length / 2);
      return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
    },
    product: (items) => items.reduce((a, b) => a * b, 1),
    first: (items) => (listOf(items).length ? listOf(items)[0] : null),
    last: (items) => { const list = listOf(items); return list.length ? list[list.length - 1] : null; },
    take: (items, n) => items.slice(0, Math.max(0, Math.trunc(n))),
    drop: (items, n) => items.slice(Math.max(0, Math.trunc(n))),
    chunk: (items, size) => {
      size = Math.trunc(size);
      if (size < 1) fail("chunk() needs a size of 1 or more");
      const list = listOf(items), out = [];
      for (let i = 0; i < list.length; i += size) out.push(list.slice(i, i + size));
      return out;
    },
    enumerate: (items) => listOf(items).map((v, i) => [i, v]),
    minby: (items, f) => {
      const list = listOf(items);
      if (!list.length) return null;
      let best = list[0], key = f(best);
      for (const v of list.slice(1)) { const k = f(v); if (k < key) { best = v; key = k; } }
      return best;
    },
    maxby: (items, f) => {
      const list = listOf(items);
      if (!list.length) return null;
      let best = list[0], key = f(best);
      for (const v of list.slice(1)) { const k = f(v); if (k > key) { best = v; key = k; } }
      return best;
    },
    groupby: (items, f) => {
      const groups = {};
      for (const v of listOf(items)) { const k = str(f(v)); (groups[k] = groups[k] || []).push(v); }
      return groups;
    },
    without: (items, value) => listOf(items).filter((v) => !eq(v, value)),
    fill: (value, count) => Array.from({ length: Math.max(0, Math.trunc(count)) },
      () => (Array.isArray(value) ? value.slice() : isMap(value) ? Object.assign({}, value) : value)),
    merge: (a, b) => Object.assign({}, a, b),
    get: (container, key, fallback = null) => {
      if (isMap(container)) return str(key) in container ? container[str(key)] : fallback;
      if (typeof key !== "number" || !Number.isInteger(key)) return fallback;
      const index = key < 0 ? container.length + key : key;
      return index >= 0 && index < container.length ? container[index] : fallback;
    },
    entries: (map) => Object.entries(map),
    frompairs: (pairs) => {
      const made = {};
      for (const pair of pairs) {
        if (!Array.isArray(pair) || pair.length !== 2) fail("frompairs() needs a list of [name, value] pairs");
        made[str(pair[0])] = pair[1];
      }
      return made;
    },
    commas: (x) => {
      const text = str(x), sign = text.startsWith("-") ? "-" : "";
      const [digits, rest] = text.replace(/^-/, "").split(".");
      if (!/^\d+$/.test(digits)) return text;
      return sign + digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (rest !== undefined ? "." + rest : "");
    },
    ordinal: (n) => {
      n = Math.trunc(n);
      const lastTwo = Math.abs(n) % 100, last = Math.abs(n) % 10;
      return `${n}${lastTwo >= 11 && lastTwo <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[last] || "th"}`;
    },
    plural: (count, word, many) => `${str(count)} ${count === 1 ? str(word) : many === undefined ? str(word) + "s" : str(many)}`,
    wraptext: (text, width) => {
      width = Math.trunc(width);
      if (width < 1) fail("wraptext() needs a width of 1 or more");
      const lines = [];
      for (const paragraph of str(text).split("\n")) {
        let line = "";
        for (let word of paragraph.split(/\s+/).filter(Boolean)) {
          while (word.length > width) {
            if (line) { lines.push(line); line = ""; }
            lines.push(word.slice(0, width));
            word = word.slice(width);
          }
          if (!word) continue;
          if (!line) line = word;
          else if (line.length + 1 + word.length <= width) line += " " + word;
          else { lines.push(line); line = word; }
        }
        lines.push(line);
      }
      return lines;
    },
    mixcolor: (a, b, t) => {
      const one = colorChannels(a), two = colorChannels(b);
      t = G.clamp(t, 0, 1);
      return one.map((c, i) => Math.floor(c + (two[i] - c) * t + 0.5));
    },
    randomcolor: () => G.hsv(Math.random() * 360, 0.65, 0.95),
    cooldown: (name, seconds) => {
      const key = "cooldown:" + str(name), now = G.time(), last = timers.get(key);
      if (last === undefined || now - last >= seconds) { timers.set(key, now); return true; }
      return false;
    },
    pulse: (name, seconds) => {
      const key = "pulse:" + str(name), now = G.time(), last = timers.get(key);
      if (last === undefined) { timers.set(key, now); return false; }
      if (now - last >= seconds) { timers.set(key, now); return true; }
      return false;
    },
    after: (name, seconds) => {
      const key = "after:" + str(name), now = G.time();
      if (!timers.has(key)) { timers.set(key, now); return seconds <= 0; }
      return now - timers.get(key) >= seconds;
    },
    scrollx: () => scrollX,
    scrolly: () => scrollY,
  });

  // ----- saving -------------------------------------------------------------------------------------------------
  let saveName = "program";
  // the same json shapes gublan itself saves, so saves and json text work in both
  function storable(v, depth = 0) {
    if (depth > 32) fail("that value is nested too deeply to save");
    if (v instanceof Vector) return { ["$vec" + v.parts.length]: v.parts.slice() };
    if (Array.isArray(v)) return v.map((x) => storable(x, depth + 1));
    if (isMap(v)) return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, storable(x, depth + 1)]));
    if (typeof v === "number" && !Number.isFinite(v)) fail("only finite numbers can be saved");
    if (typeof v === "function") fail("can't save function values");
    return v === undefined ? null : v;
  }
  // json text spaced the way python writes it: {"a": [1, 2]}
  function jsonText(v) {
    if (Array.isArray(v)) return "[" + v.map(jsonText).join(", ") + "]";
    if (isMap(v)) return "{" + Object.keys(v).map((k) => JSON.stringify(k) + ": " + jsonText(v[k])).join(", ") + "}";
    return JSON.stringify(v);
  }
  function restored(v) {
    if (isMap(v) && Object.keys(v).length === 1 && ("$vec2" in v || "$vec3" in v)) {
      const parts = v.$vec2 || v.$vec3;
      if (Array.isArray(parts) && (parts.length === 2 || parts.length === 3)) return new Vector(...parts);
    }
    if (Array.isArray(v)) return v.map(restored);
    if (isMap(v)) return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, restored(x)]));
    return v;
  }
  function readSaves() {
    try {
      if (inBrowser) return JSON.parse(localStorage.getItem("gublan:" + saveName) || "{}");
      const fs = require("fs"), path = require("path"), os = require("os");
      return JSON.parse(fs.readFileSync(path.join(os.homedir(), ".gublan_" + saveName + ".json"), "utf8"));
    } catch (error) {
      return {};
    }
  }
  function writeSaves(data) {
    try {
      if (inBrowser) { localStorage.setItem("gublan:" + saveName, JSON.stringify(data)); return; }
      const fs = require("fs"), path = require("path"), os = require("os");
      fs.writeFileSync(path.join(os.homedir(), ".gublan_" + saveName + ".json"), JSON.stringify(data));
    } catch (error) {
      fail("could not save: " + error.message);
    }
  }
  G.save = (name, value) => { const data = readSaves(); data[str(name)] = storable(value); writeSaves(data); };
  G.load = (name, fallback = 0) => { const data = readSaves(); return str(name) in data ? restored(data[str(name)]) : fallback; };
  G.saved = (name) => str(name) in readSaves();
  G.forget = (name) => {
    let data = readSaves();
    if (str(name) === "all") data = {}; else delete data[str(name)];
    writeSaves(data);
  };

  G.fetch = async function (url) {
    if (!String(url).startsWith("https://")) fail("get only works with https:// addresses");
    const response = await fetch(String(url));
    return await response.text();
  };

  // ----- the canvas ------------------------------------------------------------------------------------------------
  const COLORS = {
    red: [225, 65, 65], blue: [65, 145, 245], green: [65, 205, 105], yellow: [245, 215, 65], white: [240, 240, 240],
    moss: [148, 182, 108], orange: [245, 145, 65], purple: [170, 115, 225], cyan: [75, 205, 215], black: [12, 12, 12],
    gray: [128, 128, 128], grey: [128, 128, 128], darkgray: [52, 52, 52], pink: [240, 130, 190], brown: [140, 95, 60],
    lime: [170, 235, 70], teal: [40, 150, 140], navy: [25, 40, 90], gold: [225, 185, 60], sand: [215, 195, 150],
    sky: [135, 200, 245], forest: [40, 95, 55],
  };
  const KEY_ALIASES = {
    esc: "escape", enter: "return", spacebar: "space", shift: "left shift", lshift: "left shift", rshift: "right shift",
    ctrl: "left ctrl", control: "left ctrl", lctrl: "left ctrl", rctrl: "right ctrl", alt: "left alt",
    lalt: "left alt", ralt: "right alt", del: "delete", bksp: "backspace", pgup: "page up", pgdn: "page down",
    arrowleft: "left", arrowright: "right", arrowup: "up", arrowdown: "down",
  };

  let canvas = null, ctx = null;
  const objects = new Map();
  let title = "", background = [12, 12, 12], color = "white", textSize = 24, fps = 60;
  let lastFrame = performance.now();
  const held = new Set(), presses = new Set(), mouseHeld = new Set(), clicks = new Set();
  let mouse = [0, 0], focused = null, dragging = null, uiButton = null;
  const images = {};

  function rgb(value) {
    if (Array.isArray(value)) return `rgb(${value.slice(0, 3).map((c) => G.clamp(Math.trunc(c), 0, 255)).join(",")})`;
    const text = str(value).toLowerCase();
    if (COLORS[text]) return `rgb(${COLORS[text].join(",")})`;
    if (/^#([0-9a-f]{3}){1,2}$/.test(text)) return text;
    return `rgb(${COLORS.white.join(",")})`;
  }
  const font = (size) => `${Math.max(6, Math.round(size * 0.72))}px "Segoe UI", Arial, sans-serif`;

  G.mode = function (kind = "2d") {
    if (kind !== "2d") fail("only 2d windows can be used outside gublan");
    if (!inBrowser) return;
    if (!canvas) {
      canvas = document.createElement("canvas");
      canvas.tabIndex = 0;
      (document.getElementById("gublan-stage") || document.body).prepend(canvas);
      listen();
      requestAnimationFrame(drawLoop);
    }
    canvas.width = G.screen_width;
    canvas.height = G.screen_height;
    ctx = canvas.getContext("2d");
    document.title = title || document.title;
    canvas.focus();
  };
  G.window = function (width, height, text) {
    G.screen_width = Math.trunc(width);
    G.screen_height = Math.trunc(height);
    if (text !== undefined) title = str(text);
    if (canvas) G.mode("2d");
  };
  G.title = (text) => { title = str(text); if (inBrowser) document.title = title; };
  G.background = (...value) => { background = value.length === 3 ? value : value[0]; };
  G.color = (...value) => { color = value.length === 3 ? value : value[0]; };
  G.paint = (name, ...value) => {
    const chosen = value.length === 3 ? value : value[0];
    if (name === "all") objects.forEach((o) => { o.color = chosen; });
    else object(name).color = chosen;
  };
  G.fps = (value) => { fps = value; };
  G.textsize = (value) => { textSize = Math.trunc(value); };
  G.clear = () => {};

  const STYLE_KEYS = ["layer", "alpha", "fixed"];
  function add(name, type, parts) {
    const old = objects.get(str(name));
    const obj = Object.assign({ type, color }, parts);
    if (old) for (const key of STYLE_KEYS) if (key in old && !(key in obj)) obj[key] = old[key];
    objects.set(str(name), obj);
    return obj;
  }
  G.box = (name, x, y, w, h) => add(name, "box", { x, y, w, h });
  G.circle = (name, x, y, r) => add(name, "circle", { x, y, r });
  G.line = (name, x, y, x2, y2, width = 1) => add(name, "line", { x, y, x2, y2, width: Math.max(1, width) });
  G.text = (name, x, y, text) => add(name, "text", { x, y, text: str(text), size: textSize });
  G.ellipse = (name, x, y, w, h) => add(name, "ellipse", { x, y, w, h });
  G.polygon = (name, points) => {
    if (points.length % 2) fail("polygon points come in pairs: x y x y x y");
    if (points.length < 6) fail("a polygon needs at least three points");
    const xs = points.filter((_, i) => i % 2 === 0), ys = points.filter((_, i) => i % 2 === 1);
    const left = Math.min(...xs), top = Math.min(...ys);
    const w = Math.max(1, Math.max(...xs) - left), h = Math.max(1, Math.max(...ys) - top);
    add(name, "polygon", { x: left, y: top, w, h, pw: w, ph: h, points: xs.map((x, i) => [x - left, ys[i] - top]) });
  };

  // ----- the view, effects and tweens ------------------------------------------------------------------------------
  let scrollX = 0, scrollY = 0, shake = null, shakeX = 0, shakeY = 0, effectsTime = performance.now();
  let particles = [];
  let tweens = [];
  G.scroll = (x, y) => { scrollX = x; scrollY = y; };
  G.shake = (strength, seconds = 0.3) => {
    if (strength < 0 || seconds < 0) fail("shake strength and time can't be negative");
    shake = strength > 0 && seconds > 0 ? [strength, seconds, seconds] : null;
    if (!shake) shakeX = shakeY = 0;
  };
  G.particles = (x, y, count = 20, speed = 160) => {
    count = Math.trunc(count);
    if (count < 0 || count > 500) fail("particles can make from 0 to 500 at a time");
    const shade = rgb(color);
    for (let i = 0; i < count; i++) {
      const angle = Math.random() * Math.PI * 2, velocity = speed * (0.25 + Math.random() * 0.75);
      const life = 0.45 + Math.random() * 0.55;
      particles.push([x, y, Math.cos(angle) * velocity, Math.sin(angle) * velocity, life, life, shade, 3 + Math.random() * 3]);
    }
    if (particles.length > 2000) particles.splice(0, particles.length - 2000);
  };
  const TWEEN_FIELDS = { x: "x", y: "y", z: "z", w: "w", width: "w", h: "h", height: "h", r: "r", radius: "r", angle: "angle",
    rotation: "angle", opacity: "alpha", alpha: "alpha", size: "size" };
  function tweenStart(obj, key) {
    if (key === "alpha") return obj.alpha === undefined ? 1 : obj.alpha;
    if ((key === "w" || key === "h") && obj[key] === undefined && obj.picture) {
      return key === "w" ? obj.picture.naturalWidth : obj.picture.naturalHeight;
    }
    return obj[key] === undefined ? 0 : obj[key];
  }
  function applyTween(obj, key, value) {
    if ((key === "x" || key === "y") && obj.type === "line") obj[key + "2"] += value - obj[key];
    if (key === "alpha") value = G.clamp(value, 0, 1);
    else if (["w", "h", "r", "size"].includes(key)) value = Math.max(0, value);
    obj[key] = value;
  }
  G.tween = (name, field, value, seconds, easing = "inout") => {
    const obj = object(name), key = TWEEN_FIELDS[str(field).toLowerCase()];
    const pictured = obj.type === "image" || obj.type === "sprite";
    if (!key || !(key in obj || key === "alpha" || (pictured && ["w", "h", "angle"].includes(key)))) {
      fail(`tween can change x, y, w, h, r, angle or opacity of a ${obj.type}, not '${str(field)}'`);
    }
    if (seconds < 0) fail("tween time can't be negative");
    easing = str(easing).toLowerCase();
    if (!EASINGS.includes(easing)) fail(`'${easing}' is not an easing. try: ${EASINGS.join(", ")}`);
    tweens = tweens.filter((t) => !(t[0] === obj && t[1] === key));
    if (seconds === 0) applyTween(obj, key, value);
    else tweens.push([obj, key, tweenStart(obj, key), value, seconds, 0, easing]);
  };
  G.opacity = (name, value) => {
    value = G.clamp(value, 0, 1);
    if (name === "all") objects.forEach((o) => { o.alpha = value; });
    else object(name).alpha = value;
  };
  G.layer = (name, value) => { object(name).layer = value; };
  G.fixed = (name) => { object(name).fixed = true; };
  function tickEffects() {
    const now = performance.now(), step = Math.min(0.1, Math.max(0, (now - effectsTime) / 1000));
    effectsTime = now;
    if (tweens.length) {
      for (const tween of tweens.slice()) {
        const [obj, key, start, target, duration, elapsed, easing] = tween;
        tween[5] = elapsed + step;
        const progress = duration > 0 ? Math.min(1, tween[5] / duration) : 1;
        applyTween(obj, key, start + (target - start) * G.ease(progress, easing));
        if (progress >= 1) tweens.splice(tweens.indexOf(tween), 1);
      }
    }
    if (particles.length) {
      particles = particles.filter((p) => {
        p[4] -= step;
        if (p[4] <= 0) return false;
        p[0] += p[2] * step; p[1] += p[3] * step; p[3] += 240 * step;
        return true;
      });
    }
    if (shake) {
      shake[1] -= step;
      if (shake[1] <= 0) { shake = null; shakeX = shakeY = 0; }
      else {
        const strength = (shake[0] * shake[1]) / shake[2];
        shakeX = (Math.random() * 2 - 1) * strength; shakeY = (Math.random() * 2 - 1) * strength;
      }
    }
  }
  function picture(path) {
    if (!images[path] && inBrowser) {
      images[path] = new Image();
      images[path].src = path;
    }
    return images[path] || null;
  }
  G.image = (name, path, x, y) => add(name, "image", { x, y, picture: picture(path) });
  G.sprite = (name, path, x, y, w, h) => {
    const previous = objects.get(str(name));
    add(name, "sprite", { x, y, w, h, picture: picture(path), angle: previous ? previous.angle || 0 : 0 });
  };
  G.spin = (name, angle) => { object(name).angle = angle; };
  G.button = (variable, x, y, w, h, label) => {
    if (!(variable in G.buttons)) G.buttons[variable] = 0;
    add("button:" + variable, "button", { x, y, w, h, label: str(label), variable });
  };
  G.ui_button = (label) => { uiButton = str(label); };
  G.textbox = (name, x, y, w, hint = "") => {
    const old = objects.get(str(name)) || {};
    add(name, "textbox", { x, y, w, h: 36, hint: str(hint), text: old.text || "", cursor: old.cursor || 0, submitted: false });
  };
  G.slider = (name, x, y, w, min, max, start) => {
    const value = start === undefined ? min : G.clamp(start, Math.min(min, max), Math.max(min, max));
    add(name, "slider", { x, y, w, h: 20, min, max, value, whole: Number.isInteger(min) && Number.isInteger(max) });
  };
  G.checkbox = (name, x, y, label) => add(name, "checkbox", { x, y, w: 22, h: 22, label: str(label), checked: false });
  G.focus = (name) => { focused = name === null || name === undefined ? null : str(name); };

  function object(name) {
    name = str(name);
    const obj = objects.get(name) || objects.get("button:" + name);
    if (!obj) fail(`there is no object named '${name}'`);
    return obj;
  }
  const FIELD_ALIASES = { width: "w", height: "h", radius: "r", rotation: "angle" };
  function objectField(name, key) {
    const obj = object(name);
    key = FIELD_ALIASES[key] || key;
    if (key === "visible") return !obj.hidden;
    if (key === "focused") return focused === name;
    if (key === "submitted") { const was = !!obj.submitted; obj.submitted = false; return was; }
    if ((key === "w" || key === "h") && obj[key] === undefined && obj.picture) {
      return key === "w" ? obj.picture.naturalWidth : obj.picture.naturalHeight;
    }
    if (!(key in obj)) fail(`object '${name}' has no '${key}'`);
    return obj[key];
  }
  function setObjectField(name, key, value) {
    const obj = object(name);
    key = FIELD_ALIASES[key] || key;
    if (key === "visible") obj.hidden = !G.truthy(value);
    else if (key === "text" && obj.type === "textbox") { obj.text = str(value); obj.cursor = obj.text.length; }
    else obj[key] = value;
  }
  G.move = (name, dx, dy) => {
    const obj = object(name);
    if (dx instanceof Vector) { dy = dx.y; dx = dx.x; }
    obj.x += dx; obj.y += dy;
    if (obj.type === "line") { obj.x2 += dx; obj.y2 += dy; }
  };
  G.place = (name, x, y) => {
    const obj = object(name);
    if (obj.type === "line") { obj.x2 += x - obj.x; obj.y2 += y - obj.y; }
    obj.x = x; obj.y = y;
  };
  G.resize = (name, w, h = w) => {
    const obj = object(name);
    if (obj.type === "circle") obj.r = w;
    else if (obj.type === "text") obj.size = Math.trunc(w);
    else { obj.w = w; obj.h = h; }
  };
  G.hide = (name) => { object(name).hidden = true; };
  G.show = (name) => { object(name).hidden = false; };
  G.delete = (name) => {
    objects.delete(str(name)) || objects.delete("button:" + str(name));
    if (focused === str(name)) focused = null;
  };
  G.exists = (name) => objects.has(str(name)) || objects.has("button:" + str(name));
  G.animate = async (name, x, y, seconds) => {
    const obj = object(name), sx = obj.x, sy = obj.y, begin = performance.now();
    for (;;) {
      const progress = seconds <= 0 ? 1 : Math.min(1, (performance.now() - begin) / 1000 / seconds);
      const eased = progress * progress * (3 - 2 * progress);
      G.place(name, sx + (x - sx) * eased, sy + (y - sy) * eased);
      if (progress >= 1) return;
      await sleep(1 / 60);
    }
  };

  function measure(text, size) {
    if (!ctx) return str(text).length * size * 0.5;
    ctx.font = font(size);
    return ctx.measureText(str(text)).width;
  }
  G.textwidth = (text, size = textSize) => Math.round(measure(text, size));

  function shape(obj) {
    if (obj.type === "circle") return ["circle", obj.x, obj.y, Math.abs(obj.r)];
    if (obj.type === "text") return ["rect", obj.x, obj.y, measure(obj.text, obj.size), obj.size * 0.72];
    if (obj.picture && obj.w === undefined) return ["rect", obj.x, obj.y, obj.picture.naturalWidth, obj.picture.naturalHeight];
    return ["rect", obj.x, obj.y, obj.w || 0, obj.h || 0];
  }
  G.touching = (first, second) => {
    let a = object(first), b = object(second);
    if (a.hidden || b.hidden) return false;
    a = shape(a); b = shape(b);
    if (a[0] === "circle" && b[0] === "circle") return (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2 <= (a[3] + b[3]) ** 2;
    if (a[0] === "rect" && b[0] === "rect") return a[1] <= b[1] + b[3] && b[1] <= a[1] + a[3] && a[2] <= b[2] + b[4] && b[2] <= a[2] + a[4];
    const [c, r] = a[0] === "circle" ? [a, b] : [b, a];
    const nx = Math.min(Math.max(c[1], r[1]), r[1] + r[3]), ny = Math.min(Math.max(c[2], r[2]), r[2] + r[4]);
    return (c[1] - nx) ** 2 + (c[2] - ny) ** 2 <= c[3] ** 2;
  };
  G.overlap = (first, second) => {
    const rect = (v) => {
      if (typeof v === "string") {
        const s = shape(object(v));
        return s[0] === "circle" ? [s[1] - s[3], s[2] - s[3], s[3] * 2, s[3] * 2] : s.slice(1);
      }
      return Array.isArray(v) ? v : [v.x, v.y, v.w, v.h];
    };
    const a = rect(first), b = rect(second);
    return a[0] < b[0] + b[2] && b[0] < a[0] + a[2] && a[1] < b[1] + b[3] && b[1] < a[1] + a[3];
  };

  function draw() {
    tickEffects();
    if (!ctx) return;
    ctx.fillStyle = rgb(background);
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.textBaseline = "top";
    if (uiButton !== null) {
      ctx.fillStyle = "rgb(109,137,79)";
      ctx.fillRect(20, 20, 180, 38);
      ctx.fillStyle = "rgb(240,240,240)";
      ctx.font = font(20);
      ctx.fillText(uiButton, 32, 30);
    }
    const items = [...objects];
    if (items.some(([, o]) => o.layer)) items.sort((a, b) => (a[1].layer || 0) - (b[1].layer || 0));
    for (const [name, obj] of items) {
      if (obj.hidden) continue;
      const alpha = obj.alpha === undefined ? 1 : obj.alpha;
      if (alpha <= 0) continue;
      ctx.save();
      ctx.globalAlpha = alpha;
      if (!UI_KINDS.has(obj.type) && !obj.fixed) ctx.translate(shakeX - scrollX, shakeY - scrollY);
      drawObject(name, obj);
      ctx.restore();
    }
    if (particles.length) {
      ctx.save();
      ctx.translate(shakeX - scrollX, shakeY - scrollY);
      for (const [x, y, , , life, total, shade, size] of particles) {
        const fade = G.clamp(life / total, 0, 1), side = Math.max(1, size * (0.4 + 0.6 * fade));
        ctx.globalAlpha = fade;
        ctx.fillStyle = shade;
        ctx.fillRect(x - side / 2, y - side / 2, side, side);
      }
      ctx.restore();
    }
    if (showFps) drawFps();
  }
  let showFps = false;
  const frameTimes = [];
  function drawFps() {
    const now = performance.now();
    frameTimes.push(now);
    while (frameTimes.length && now - frameTimes[0] > 1000) frameTimes.shift();
    const label = "fps " + frameTimes.length;
    ctx.save();
    ctx.font = font(18);
    ctx.textBaseline = "top";
    const width = ctx.measureText(label).width + 10;
    ctx.fillStyle = "rgba(0,0,0,0.6)";
    ctx.fillRect(canvas.width - width - 6, 6, width, 20);
    ctx.fillStyle = G.style.accent;
    ctx.fillText(label, canvas.width - width - 1, 9);
    ctx.restore();
  }
  const UI_KINDS = new Set(["button", "textbox", "slider", "checkbox"]);
  function drawObject(name, obj) {
    {
      const shade = rgb(obj.color);
      ctx.fillStyle = shade;
      ctx.strokeStyle = shade;
      if (obj.type === "box") ctx.fillRect(obj.x, obj.y, obj.w, obj.h);
      else if (obj.type === "circle") { ctx.beginPath(); ctx.arc(obj.x, obj.y, Math.abs(obj.r), 0, Math.PI * 2); ctx.fill(); }
      else if (obj.type === "ellipse") {
        ctx.beginPath();
        ctx.ellipse(obj.x + obj.w / 2, obj.y + obj.h / 2, Math.abs(obj.w / 2), Math.abs(obj.h / 2), 0, 0, Math.PI * 2);
        ctx.fill();
      } else if (obj.type === "polygon") {
        const sx = obj.pw ? obj.w / obj.pw : 1, sy = obj.ph ? obj.h / obj.ph : 1;
        ctx.beginPath();
        obj.points.forEach(([px, py], i) => (i ? ctx.lineTo : ctx.moveTo).call(ctx, obj.x + px * sx, obj.y + py * sy));
        ctx.closePath();
        ctx.fill();
      }
      else if (obj.type === "line") {
        ctx.lineWidth = obj.width;
        ctx.beginPath(); ctx.moveTo(obj.x, obj.y); ctx.lineTo(obj.x2, obj.y2); ctx.stroke();
      } else if (obj.type === "text") { ctx.font = font(obj.size); ctx.fillText(obj.text, obj.x, obj.y); }
      else if (obj.type === "image" || obj.type === "sprite") {
        const p = obj.picture;
        if (!p || !p.complete || !p.naturalWidth) return;
        const w = obj.w === undefined ? p.naturalWidth : obj.w, h = obj.h === undefined ? p.naturalHeight : obj.h;
        ctx.save();
        ctx.translate(obj.x + w / 2, obj.y + h / 2);
        ctx.rotate(((obj.angle || 0) * Math.PI) / 180);
        ctx.drawImage(p, -w / 2, -h / 2, w, h);
        ctx.restore();
      } else if (obj.type === "button") {
        const over = mouse[0] >= obj.x && mouse[0] <= obj.x + obj.w && mouse[1] >= obj.y && mouse[1] <= obj.y + obj.h;
        ctx.fillStyle = over ? "rgb(148,182,108)" : "rgb(82,105,61)";
        ctx.fillRect(obj.x, obj.y, obj.w, obj.h);
        ctx.fillStyle = "rgb(240,240,240)";
        ctx.font = font(24);
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText(obj.label, obj.x + obj.w / 2, obj.y + obj.h / 2);
        ctx.textAlign = "left"; ctx.textBaseline = "top";
      } else if (obj.type === "textbox") {
        ctx.fillStyle = "rgb(23,23,23)"; ctx.fillRect(obj.x, obj.y, obj.w, obj.h);
        ctx.lineWidth = 2; ctx.strokeStyle = focused === name ? "rgb(148,182,108)" : "rgb(90,90,90)";
        ctx.strokeRect(obj.x, obj.y, obj.w, obj.h);
        ctx.font = font(24);
        ctx.fillStyle = obj.text ? shade : "rgb(120,120,120)";
        ctx.fillText(obj.text || (focused === name ? "" : obj.hint), obj.x + 8, obj.y + 10);
        if (focused === name && Math.floor(performance.now() / 500) % 2 === 0) {
          const caret = obj.x + 8 + ctx.measureText(obj.text.slice(0, obj.cursor)).width;
          ctx.fillStyle = "rgb(148,182,108)"; ctx.fillRect(caret, obj.y + 7, 2, obj.h - 14);
        }
      } else if (obj.type === "slider") {
        const share = obj.max === obj.min ? 0 : (obj.value - obj.min) / (obj.max - obj.min), middle = obj.y + obj.h / 2;
        ctx.fillStyle = "rgb(60,60,60)"; ctx.fillRect(obj.x, middle - 3, obj.w, 6);
        ctx.fillStyle = shade; ctx.fillRect(obj.x, middle - 3, obj.w * share, 6);
        ctx.beginPath(); ctx.arc(obj.x + obj.w * share, middle, 9, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = "rgb(200,200,200)"; ctx.font = font(20); ctx.textBaseline = "middle";
        ctx.fillText(str(obj.value), obj.x + obj.w + 12, middle); ctx.textBaseline = "top";
      } else if (obj.type === "checkbox") {
        ctx.fillStyle = "rgb(23,23,23)"; ctx.fillRect(obj.x, obj.y, obj.w, obj.h);
        ctx.lineWidth = 2; ctx.strokeStyle = obj.checked ? shade : "rgb(110,110,110)";
        ctx.strokeRect(obj.x, obj.y, obj.w, obj.h);
        if (obj.checked) {
          ctx.lineWidth = 3; ctx.beginPath();
          ctx.moveTo(obj.x + 5, obj.y + obj.h / 2); ctx.lineTo(obj.x + 10, obj.y + obj.h - 6); ctx.lineTo(obj.x + obj.w - 5, obj.y + 6);
          ctx.stroke();
        }
        ctx.fillStyle = "rgb(229,229,229)"; ctx.font = font(24); ctx.textBaseline = "middle";
        ctx.fillText(obj.label, obj.x + obj.w + 8, obj.y + obj.h / 2); ctx.textBaseline = "top";
      }
    }
  }
  function drawLoop() {
    draw();
    requestAnimationFrame(drawLoop);
  }

  G.frame = async function () {
    const target = 1000 / Math.max(1, fps);
    if (inBrowser) {
      await new Promise((done) => requestAnimationFrame(done));
      const left = lastFrame + target - performance.now();
      if (left > 1) await sleep(left / 1000);
    } else {
      await sleep(Math.max(0, lastFrame + target - performance.now()) / 1000);
      tickEffects();
    }
    const current = performance.now();
    G.dt = Math.min(0.25, (current - lastFrame) / 1000);
    lastFrame = current;
  };

  // ----- keys and the mouse ------------------------------------------------------------------------------------------
  function keyName(event) {
    const sides = { ShiftLeft: "left shift", ShiftRight: "right shift", ControlLeft: "left ctrl", ControlRight: "right ctrl",
      AltLeft: "left alt", AltRight: "right alt" };
    if (sides[event.code]) return sides[event.code];
    const named = { " ": "space", Enter: "return", Escape: "escape", Backspace: "backspace", Tab: "tab", Delete: "delete",
      ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down", PageUp: "page up", PageDown: "page down",
      Home: "home", End: "end", Insert: "insert" };
    return named[event.key] || event.key.toLowerCase();
  }
  const wanted = (name) => { name = str(name).trim().toLowerCase(); return KEY_ALIASES[name] || name; };
  const typing = () => focused !== null && objects.has(focused) && objects.get(focused).type === "textbox";
  G.keydown = (name) => held.has(wanted(name)) && !typing();
  G.keypressed = (name) => presses.delete(wanted(name));
  G.mousex = () => mouse[0];
  G.mousey = () => mouse[1];
  const buttonNumber = { left: 0, middle: 1, right: 2 };
  G.mousedown = (which = "left") => mouseHeld.has(buttonNumber[str(which)]);
  G.mousepressed = (which = "left") => clicks.delete(buttonNumber[str(which)]);
  G.cursor = (visible) => { if (canvas) canvas.style.cursor = visible ? "default" : "none"; };

  function slide(obj, x) {
    const value = obj.min + (obj.max - obj.min) * G.clamp((x - obj.x) / Math.max(1, obj.w), 0, 1);
    obj.value = obj.whole ? Math.round(value) : Math.round(value * 10000) / 10000;
  }
  function listen() {
    window.addEventListener("keydown", (event) => {
      const box = focused !== null ? objects.get(focused) : null;
      if (box && box.type === "textbox") {
        if (event.key.length === 1) { box.text = box.text.slice(0, box.cursor) + event.key + box.text.slice(box.cursor); box.cursor++; }
        else if (event.key === "Backspace" && box.cursor > 0) { box.text = box.text.slice(0, box.cursor - 1) + box.text.slice(box.cursor); box.cursor--; }
        else if (event.key === "Delete") box.text = box.text.slice(0, box.cursor) + box.text.slice(box.cursor + 1);
        else if (event.key === "ArrowLeft") box.cursor = Math.max(0, box.cursor - 1);
        else if (event.key === "ArrowRight") box.cursor = Math.min(box.text.length, box.cursor + 1);
        else if (event.key === "Enter") box.submitted = true;
        else if (event.key === "Escape") focused = null;
        event.preventDefault();
        return;
      }
      const name = keyName(event);
      if (!held.has(name)) presses.add(name);
      held.add(name);
      if (["space", "up", "down", "left", "right", "tab"].includes(name)) event.preventDefault();
    });
    window.addEventListener("keyup", (event) => { held.delete(keyName(event)); });
    window.addEventListener("blur", () => held.clear());
    const where = (event) => {
      const box = canvas.getBoundingClientRect();
      return [(event.clientX - box.left) * (canvas.width / box.width), (event.clientY - box.top) * (canvas.height / box.height)];
    };
    canvas.addEventListener("mousemove", (event) => {
      mouse = where(event);
      if (dragging && objects.has(dragging)) slide(objects.get(dragging), mouse[0]);
    });
    canvas.addEventListener("contextmenu", (event) => event.preventDefault());
    canvas.addEventListener("mousedown", (event) => {
      mouse = where(event);
      mouseHeld.add(event.button);
      clicks.add(event.button);
      if (event.button !== 0) return;
      const [mx, my] = mouse;
      if (uiButton !== null && mx >= 20 && mx <= 200 && my >= 20 && my <= 58) G.ui = uiButton;
      let chosen = null;
      for (const [name, obj] of objects) {
        if (obj.hidden || !["button", "textbox", "slider", "checkbox"].includes(obj.type)) continue;
        const width = obj.w + (obj.type === "checkbox" ? 8 + measure(obj.label, 24) : 0), grow = obj.type === "slider" ? 6 : 0;
        if (mx < obj.x || mx > obj.x + width || my < obj.y - grow || my > obj.y + obj.h + grow) continue;
        if (obj.type === "button") G.buttons[obj.variable] = 1;
        else if (obj.type === "textbox") chosen = name;
        else if (obj.type === "checkbox") obj.checked = !obj.checked;
        else { dragging = name; slide(obj, mx); }
      }
      focused = chosen;
      canvas.focus();
    });
    window.addEventListener("mouseup", (event) => {
      mouseHeld.delete(event.button);
      dragging = null;
      objects.forEach((obj) => { if (obj.type === "button") G.buttons[obj.variable] = 0; });
    });
  }

  // ----- questions and messages ------------------------------------------------------------------------------------------
  // the look of popups and questions. a page can set globalThis.GUBLAN_STYLE before this file runs to change it.
  // it takes this file's own names (dialog, text, accent...) or gublan studio's game style names (width,
  // background, dialog_background, dialog_animation...), so the studio's tools > game window and popups
  // settings carry over to web exports.
  G.style = Object.assign({
    dialog: "#141414", text: "#e6e6e6", accent: "#94b66c", border: "#2c2c2c", shade: 0.55,
    font: "Segoe UI, Arial, sans-serif", size: 18, animate: true, animation: "pop", position: "center",
    boxWidth: 520, borderWidth: 1, hints: false, hint: "#9a9a9a", field: "rgba(0,0,0,.25)", sound: false,
  }, root.GUBLAN_STYLE || {});
  (function gameStyle(given) {
    if (!given) return;
    const style = G.style, has = (key) => Object.prototype.hasOwnProperty.call(given, key);
    const names = { dialog_background: "dialog", dialog_text: "text", dialog_accent: "accent", dialog_border: "border",
      dialog_hint: "hint", dialog_field: "field", dialog_position: "position", dialog_width: "boxWidth",
      dialog_border_width: "borderWidth", dialog_hints: "hints", dialog_sound: "sound" };
    for (const [key, name] of Object.entries(names)) if (has(key)) style[name] = given[key];
    if (has("dialog_shade")) style.shade = G.clamp(Number(given.dialog_shade) / 100, 0, 1);
    if (has("dialog_text_size")) style.size = Math.max(10, Math.round(Number(given.dialog_text_size) * 0.72));
    if (has("dialog_animation")) {
      style.animation = str(given.dialog_animation);
      style.animate = style.animation !== "none";
    }
    if (has("width") && has("height")) {
      G.screen_width = Math.trunc(G.clamp(Number(given.width), 120, 4096));
      G.screen_height = Math.trunc(G.clamp(Number(given.height), 90, 4096));
    }
    if (has("background")) background = given.background;
    if (has("color")) color = given.color;
    if (has("fps")) fps = Math.max(1, Number(given.fps) || 60);
    if (has("title") && given.title) title = str(given.title);
    if (has("show_fps")) showFps = Boolean(given.show_fps);
  })(root.GUBLAN_STYLE);
  function dialogBlip() {
    const Context = inBrowser && (window.AudioContext || window.webkitAudioContext);
    if (!Context) return;
    try {
      if (!audioContext) audioContext = new Context();
      const start = audioContext.currentTime, gain = audioContext.createGain(), tone = audioContext.createOscillator();
      tone.type = "sine";
      tone.frequency.value = 880;
      gain.gain.setValueAtTime(0, start);
      gain.gain.linearRampToValueAtTime(0.06 * soundVolume, start + 0.008);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.16);
      tone.connect(gain).connect(audioContext.destination);
      tone.start(start);
      tone.stop(start + 0.18);
    } catch (_) { /* no sound is fine */ }
  }
  function pageDialog(message, asking) {
    return new Promise((done) => {
      const style = G.style, motion = style.animate ? ".18s" : "0s";
      const place = { top: "flex-start", bottom: "flex-end" }[style.position] || "center";
      const shade = document.createElement("div");
      shade.style.cssText = `position:fixed;inset:0;display:flex;align-items:${place};justify-content:center;z-index:2147483000;` +
        `padding:24px 0;box-sizing:border-box;background:rgba(0,0,0,${style.shade});opacity:0;transition:opacity ${motion} ease-out`;
      const start = { pop: "scale(.86)", slide: `translateY(${style.position === "top" ? -28 : 28}px)`, fade: "none" }[style.animation]
        || "translateY(10px) scale(.98)";
      const panel = document.createElement("div");
      const edge = Math.max(0, Number(style.borderWidth) || 0);
      panel.style.cssText = `background:${style.dialog};color:${style.text};border:${edge}px solid ${style.border};` +
        `border-top:${Math.max(edge, 2)}px solid ${style.accent};font:${style.size}px ${style.font};padding:18px 20px;min-width:260px;` +
        `max-width:min(${Math.trunc(style.boxWidth) || 520}px,86vw);box-shadow:0 18px 40px rgba(0,0,0,.45);transform:${start};` +
        `transition:transform ${motion} cubic-bezier(.2,.9,.3,1.25)`;
      const words = document.createElement("div");
      words.textContent = message;
      words.style.cssText = "white-space:pre-wrap;line-height:1.4;margin-bottom:14px";
      panel.appendChild(words);
      let field = null;
      if (asking) {
        field = document.createElement("input");
        field.style.cssText = `width:100%;box-sizing:border-box;background:${style.field};color:${style.text};` +
          `border:1px solid ${style.border};border-bottom:2px solid ${style.accent};padding:8px 10px;outline:none;` +
          `font:inherit;margin-bottom:14px`;
        panel.appendChild(field);
      }
      const ok = document.createElement("button");
      ok.textContent = asking ? "ok" : "continue";
      ok.style.cssText = `background:${style.accent};color:#0c0c0c;border:0;padding:7px 16px;font:inherit;cursor:pointer`;
      panel.appendChild(ok);
      if (style.hints) {
        const hint = document.createElement("div");
        hint.textContent = asking ? "enter to accept" : "enter or space to continue";
        hint.style.cssText = `margin-top:10px;font-size:.75em;color:${style.hint}`;
        panel.appendChild(hint);
      }
      shade.appendChild(panel);
      document.body.appendChild(shade);
      if (style.sound) dialogBlip();
      requestAnimationFrame(() => { shade.style.opacity = "1"; panel.style.transform = "none"; });
      held.clear();
      const finish = () => {
        const answer = field ? field.value : "";
        shade.style.opacity = "0";
        setTimeout(() => shade.remove(), style.animate ? 160 : 0);
        if (canvas) canvas.focus();
        done(answer);
      };
      ok.addEventListener("click", finish);
      shade.addEventListener("keydown", (event) => {
        event.stopPropagation();
        if (event.key === "Enter" || (!asking && (event.key === " " || event.key === "Escape"))) { event.preventDefault(); finish(); }
      });
      (field || ok).focus();
    });
  }
  G.ask = async function (question) {
    let answer;
    if (inBrowser) {
      await new Promise((done) => requestAnimationFrame(done));
      answer = document.body ? await pageDialog(str(question), true) : window.prompt(str(question)) || "";
    } else {
      const readline = require("readline");
      const reader = readline.createInterface({ input: process.stdin, output: process.stdout });
      answer = await new Promise((done) => reader.question(str(question) + " ", done));
      reader.close();
    }
    const cleaned = answer.trim();
    return /^-?(0|[1-9][0-9]*)(\.[0-9]+)?$/.test(cleaned) ? Number(cleaned) : answer;
  };
  G.popup = async function (text) {
    if (inBrowser) {
      await new Promise((done) => requestAnimationFrame(done));
      if (document.body) await pageDialog(str(text), false);
      else window.alert(str(text));
    } else {
      console.log(str(text));
    }
  };

  // ----- sound -------------------------------------------------------------------------------------------------------------
  let soundVolume = 1, song = null;
  const playing = new Set();
  G.sound = (path) => {
    if (!inBrowser) return;
    const audio = new Audio(path);
    audio.volume = soundVolume;
    playing.add(audio);
    audio.addEventListener("ended", () => playing.delete(audio));
    audio.play().catch(() => {});
  };
  G.music = (path) => {
    if (!inBrowser) return;
    if (song) song.pause();
    song = new Audio(path);
    song.loop = true;
    song.volume = soundVolume;
    song.play().catch(() => {});
  };
  G.stopmusic = () => { if (song) song.pause(); song = null; };
  G.stopsounds = () => { playing.forEach((a) => a.pause()); playing.clear(); };
  G.volume = (value) => { soundVolume = G.clamp(value, 0, 1); if (song) song.volume = soundVolume; };
  const WAVES = ["square", "sine", "triangle", "saw", "noise"];
  let audioContext = null;
  G.beep = (frequency, seconds = 0.15, wave = "square") => {
    wave = str(wave).toLowerCase();
    if (!(frequency >= 20 && frequency <= 20000)) fail("beep frequency must be from 20 to 20000 (440 is the a above middle c)");
    if (!(seconds > 0 && seconds <= 5)) fail("a beep can last from just above 0 up to 5 seconds");
    if (!WAVES.includes(wave)) fail(`'${wave}' is not a wave. try: ${WAVES.join(", ")}`);
    if (!inBrowser) return;
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) return;
    if (!audioContext) audioContext = new Context();
    const start = audioContext.currentTime, loud = 0.22 * soundVolume;
    const gain = audioContext.createGain();
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(loud, start + 0.003);
    gain.gain.setValueAtTime(loud, Math.max(start + 0.003, start + seconds - 0.02));
    gain.gain.linearRampToValueAtTime(0, start + seconds);
    gain.connect(audioContext.destination);
    let source;
    if (wave === "noise") {
      const buffer = audioContext.createBuffer(1, Math.max(1, Math.floor(audioContext.sampleRate * seconds)), audioContext.sampleRate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
      source = audioContext.createBufferSource();
      source.buffer = buffer;
    } else {
      source = audioContext.createOscillator();
      source.type = wave === "saw" ? "sawtooth" : wave;
      source.frequency.value = frequency;
    }
    source.connect(gain);
    source.start(start);
    source.stop(start + seconds + 0.01);
  };

  // ----- starting -----------------------------------------------------------------------------------------------------------
  // node game.js --test (or game.html#test): run every test block instead of the program
  G.runTests = async function () {
    let passed = 0, failed = 0;
    for (const [name, test] of Object.entries(G.tests)) {
      const label = name.replace(/^test_/, "").replace(/_/g, " ");
      try {
        await test();
      } catch (error) {
        if (error !== KILL) {
          failed++;
          G.print(`fail: ${label}: ${G.message(error)}`);
          continue;
        }
      }
      passed++;
      G.print(`pass: ${label}`);
    }
    G.print(`${passed} passed, ${failed} failed`);
    return failed === 0;
  };

  G.start = function (main, name = "program") {
    saveName = name;
    const testing = inBrowser ? location.hash === "#test"
      : typeof process !== "undefined" && process.argv.slice(2).includes("--test");
    if (testing) {
      saveName = name + "_tests";
      const go = () => G.runTests().then((good) => { if (!inBrowser && !good) process.exitCode = 1; });
      if (inBrowser && document.readyState === "loading") document.addEventListener("DOMContentLoaded", go);
      else go();
      return;
    }
    const run = async () => {
      try {
        await main();
      } catch (error) {
        if (error === KILL) return;
        const text = "error: " + (error instanceof Error ? error.message : str(error));
        console.error(text);
        if (inBrowser) {
          const log = document.getElementById("gublan-log");
          if (log) log.textContent += text + "\n";
        } else {
          process.exitCode = 1;
        }
      }
    };
    if (inBrowser && document.readyState === "loading") document.addEventListener("DOMContentLoaded", run);
    else run();
  };

  G.storable = storable;
  if (typeof module !== "undefined" && module.exports) module.exports = G;
  root.G = G;
})(typeof globalThis !== "undefined" ? globalThis : this);
