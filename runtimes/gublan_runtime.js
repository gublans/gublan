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

  function add(name, type, parts) {
    const obj = Object.assign({ type, color }, parts);
    objects.set(str(name), obj);
    return obj;
  }
  G.box = (name, x, y, w, h) => add(name, "box", { x, y, w, h });
  G.circle = (name, x, y, r) => add(name, "circle", { x, y, r });
  G.line = (name, x, y, x2, y2, width = 1) => add(name, "line", { x, y, x2, y2, width: Math.max(1, width) });
  G.text = (name, x, y, text) => add(name, "text", { x, y, text: str(text), size: textSize });
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
    for (const [name, obj] of objects) {
      if (obj.hidden) continue;
      const shade = rgb(obj.color);
      ctx.fillStyle = shade;
      ctx.strokeStyle = shade;
      if (obj.type === "box") ctx.fillRect(obj.x, obj.y, obj.w, obj.h);
      else if (obj.type === "circle") { ctx.beginPath(); ctx.arc(obj.x, obj.y, Math.abs(obj.r), 0, Math.PI * 2); ctx.fill(); }
      else if (obj.type === "line") {
        ctx.lineWidth = obj.width;
        ctx.beginPath(); ctx.moveTo(obj.x, obj.y); ctx.lineTo(obj.x2, obj.y2); ctx.stroke();
      } else if (obj.type === "text") { ctx.font = font(obj.size); ctx.fillText(obj.text, obj.x, obj.y); }
      else if (obj.type === "image" || obj.type === "sprite") {
        const p = obj.picture;
        if (!p || !p.complete || !p.naturalWidth) continue;
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
  G.ask = async function (question) {
    let answer;
    if (inBrowser) {
      await new Promise((done) => requestAnimationFrame(done));
      answer = window.prompt(str(question)) || "";
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
      window.alert(str(text));
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
