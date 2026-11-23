// the gublan playground: write gublan in the browser and run it.
//
// gublan's own checker and javascript translator (gublancore.py and gublantranslate.py) run in pyodide.
// the translated program runs with gublan_runtime.js inside a sandboxed iframe, the same way a program
// exported from gublan studio as a web page runs. web/build_site.py copies all of those files next to this one.
//
// the page keeps a small project (several .gubl files, so include works), its settings and saved games in
// this browser's storage. nothing is sent anywhere: sharing puts the program in the link itself.
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const source = $("source");
  const highlight = $("highlight");
  const gutter = $("gutter");
  const editor = $("editor");
  const code = $("code");
  const caret = $("caret");
  const activeLine = $("active-line");
  const completeBox = $("complete");
  const hintbar = $("hintbar");
  const editorPane = $("editor-pane");
  const runPane = $("run-pane");
  const layout = $("layout");
  const stage = $("stage");
  const stageNote = $("stage-note");
  const output = $("output");
  const statusText = $("status");
  const runButton = $("run");
  const stopButton = $("stop");
  const examplesBox = $("examples");
  const fileList = $("file-list");
  const findbar = $("findbar");
  const findText = $("find-text");
  const replaceText = $("replace-text");
  const palette = $("palette");
  const paletteInput = $("palette-input");
  const paletteList = $("palette-list");
  const drawer = $("settings");
  const scrim = $("scrim");

  const KEY = "gublan-playground:";
  const DRAFT_KEY = KEY + "draft"; // the 1.0.6 playground kept one program here
  const PROJECT_KEY = KEY + "project";
  const SETTINGS_KEY = KEY + "settings";
  const SAVES_KEY = KEY + "saves";

  // the same word lists gublan studio's editor uses (studio/meta.py). the bridge fills in the rest.
  const FLOW = new Set(["assert", "break", "case", "catch", "const", "continue", "elif", "else", "elseif", "end", "for",
    "forever", "function", "if", "include", "kill", "loop", "match", "return", "test", "then", "throw", "try", "until",
    "use", "wait", "while"]);
  let OPENERS = new Set(["if", "loop", "forever", "while", "until", "for", "function", "match", "try", "test"]);
  let MIDDLES = new Set(["elseif", "else", "case", "catch"]);
  let WORDS = new Set(["and", "or", "not", "in", "to", "step", "true", "false", "none", "pi", "dt", "all", "lambda"]);
  const EXPRESSION_LINES = new Set(["if", "elseif", "elif", "while", "return", "set", "for", "call", "calc"]);
  const COLOR_COMMANDS = new Set(["color", "paint", "background"]);
  const CATEGORY_ORDER = ["basics", "control", "functions", "testing", "lists and maps", "display", "2d", "3d", "ui",
    "objects", "input", "sound", "web", "saving", "discord", "plugins"];
  const INDENT = "    ";
  const PAD_TOP = 12;
  const PAD_LEFT = 14;
  const SPEEDS = { slow: 1.7, normal: 1, fast: 0.55 };
  const SPACING = { tight: 1.3, normal: 1.5, roomy: 1.7, airy: 1.9 };
  const FONTS = [["", "default"], ["'Cascadia Code', 'Cascadia Mono'", "cascadia"], ["'JetBrains Mono'", "jetbrains mono"],
    ["'Fira Code'", "fira code"], ["'Source Code Pro'", "source code pro"], ["Consolas", "consolas"],
    ["'Courier New'", "courier new"], ["monospace", "your system's"]];
  const FX_LIFE = 900;
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const DEFAULTS = {
    theme: "auto", accent: "", motion: !reducedMotion, speed: "normal",
    font: "", fontSize: 14, spacing: "normal",
    smoothCaret: true, caretStyle: "line", caretBlink: "fade", caretMotion: "glide", caretWidth: 2, typing: "fade",
    autoPairs: true, autoEnd: true, suggestions: true, hints: true, lineHighlight: true, rainbow: true,
    sounds: true, soundPack: "soft", volume: 45, typingSounds: false,
    split: 0.5, splitY: 0.6, game: {},
  };

  let settings = Object.assign({}, DEFAULTS);
  let project = { files: [], current: "" };
  let bridge = null;
  let runtimeSource = "";
  let manifest = { version: "", examples: [], themes: {}, accents: [], game: {} };
  let reference = null;
  const commandsByName = new Map();
  const functionsByName = new Map();
  const colorNames = new Map();
  let problems = [];
  let frame = null;
  let frameName = "program";
  let frameFailed = false;
  let checkTimer = 0;
  let saveTimer = 0;
  let lastText = "";
  let charWidth = 8;
  let lineHeight = 21;
  let fx = []; // letters that were just typed: {from, to, kind, born}
  const flashes = new Map(); // line number -> {kind, born}
  let findHits = [];
  let findIndex = -1;
  let completion = null;
  let lastHint = "";
  let lastCaretLine = -1;
  let currentGutterLine = null;
  const views = new Map(); // file name -> {start, end, top, left}

  // ----- small helpers --------------------------------------------------------------------------------------
  const storage = {
    get(key) { try { return localStorage.getItem(key); } catch (_) { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch (_) { /* private mode: not saved */ } },
    remove(key) { try { localStorage.removeItem(key); } catch (_) { /* nothing to remove */ } },
  };
  const escapeHtml = (text) => String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
  const mod = (event) => event.ctrlKey || event.metaKey;
  const speed = () => (settings.motion ? SPEEDS[settings.speed] || 1 : 0);

  function h(tag, attrs, ...children) {
    const element = document.createElement(tag);
    for (const [name, value] of Object.entries(attrs || {})) {
      if (value === undefined || value === null || value === false) continue;
      if (name === "class") element.className = value;
      else if (name === "text") element.textContent = value;
      else if (name.startsWith("on")) element.addEventListener(name.slice(2), value);
      else element.setAttribute(name, value === true ? "" : value);
    }
    for (const child of children.flat(Infinity)) if (child !== null && child !== undefined && child !== false) element.append(child);
    return element;
  }

  function setStatus(text, kind = "") {
    if (statusText.textContent !== text) {
      statusText.classList.remove("changed");
      void statusText.offsetWidth;
    }
    statusText.textContent = text;
    statusText.className = "status changed" + (kind ? " " + kind : "");
  }

  function say(text, kind = "") {
    const line = document.createElement("span");
    if (kind) line.className = kind;
    line.textContent = text || " ";
    output.append(line);
    while (output.childElementCount > 3000) output.firstElementChild.remove();
    const panel = $("panel-output");
    panel.scrollTop = panel.scrollHeight;
  }

  let toastShelf = null;
  function toast(text, kind = "") {
    if (!toastShelf) toastShelf = document.body.appendChild(h("div", { class: "toasts", "aria-live": "polite" }));
    const note = h("div", { class: "toast" + (kind ? " " + kind : ""), role: "status", text });
    toastShelf.append(note);
    setTimeout(() => {
      note.classList.add("leaving");
      setTimeout(() => note.remove(), 260 * (speed() || 0.01));
    }, 2200);
  }

  // hide something with its leaving animation (or at once when animations are off)
  function leave(element, ms, done) {
    clearTimeout(element.leaveTimer);
    if (!speed()) {
      element.hidden = true;
      if (done) done();
      return;
    }
    element.classList.add("leaving");
    element.leaveTimer = setTimeout(() => {
      element.hidden = true;
      element.classList.remove("leaving");
      if (done) done();
    }, ms * speed());
  }
  function arrive(element) {
    clearTimeout(element.leaveTimer);
    element.classList.remove("leaving");
    element.hidden = false;
  }

  function download(name, content, type = "text/plain") {
    const link = document.createElement("a");
    const url = typeof content === "string" && content.startsWith("data:") ? content
      : URL.createObjectURL(content instanceof Blob ? content : new Blob([content], { type }));
    link.href = url;
    link.download = name;
    document.body.append(link);
    link.click();
    link.remove();
    if (url.startsWith("blob:")) setTimeout(() => URL.revokeObjectURL(url), 10000);
  }

  // ----- colours -----------------------------------------------------------------------------------------
  const isHex = (value) => typeof value === "string" && /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(value.trim());
  function rgb(hex) {
    let digits = hex.trim().slice(1);
    if (digits.length === 3) digits = digits.split("").map((c) => c + c).join("");
    const n = parseInt(digits, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const toHex = (parts) => "#" + parts.map((v) => Math.round(clamp(v, 0, 255)).toString(16).padStart(2, "0")).join("");
  function mix(a, b, amount) {
    const x = rgb(a), y = rgb(b);
    return toHex(x.map((v, i) => v + (y[i] - v) * amount));
  }
  function luminance(hex) {
    const [r, g, b] = rgb(hex).map((v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }
  // a gublan colour (a name, #rgb or #rrggbb) as #rrggbb for colour pickers
  function gublanHex(value, fallback = "#ffffff") {
    if (isHex(String(value || ""))) return toHex(rgb(String(value)));
    const named = colorNames.get(String(value || "").toLowerCase()) || { white: [240, 240, 240], black: [12, 12, 12] }[value];
    return named ? toHex(named) : fallback;
  }

  // ----- sounds: the same soft notes gublan studio plays (studio/sounds.py), made with web audio -------------
  const SOUND_EVENTS = {
    open: [[660, 0, 0.11, 0.8], [880, 0.06, 0.14, 0.7]],
    close: [[880, 0, 0.1, 0.6], [660, 0.05, 0.14, 0.55]],
    run: [[523.25, 0, 0.12, 0.7], [659.25, 0.07, 0.12, 0.7], [783.99, 0.14, 0.22, 0.75]],
    stop: [[587.33, 0, 0.12, 0.6], [440, 0.08, 0.2, 0.55]],
    done: [[659.25, 0, 0.3, 0.45], [783.99, 0.03, 0.3, 0.4], [987.77, 0.07, 0.34, 0.35]],
    error: [[233.08, 0, 0.13, 0.85], [196, 0.11, 0.2, 0.85]],
    warning: [[440, 0, 0.16, 0.6]],
    save: [[1318.5, 0, 0.05, 0.45], [1760, 0.03, 0.07, 0.35]],
    click: [[1046.5, 0, 0.035, 0.35]],
    notify: [[783.99, 0, 0.18, 0.55], [1174.66, 0.05, 0.22, 0.35]],
    type: [[1600, 0, 0.012, 0.18]],
    pass: [[783.99, 0, 0.1, 0.55], [1046.5, 0.06, 0.18, 0.5]],
  };
  // wave, octave shift, attack seconds, how fast it fades, overtone amount
  const SOUND_PACKS = {
    soft: ["sine", 0, 0.008, 9, 0.18],
    glass: ["sine", 1, 0.002, 7, 0.42],
    wood: ["triangle", -1, 0.001, 22, 0.08],
    retro: ["square", 0, 0.001, 11, 0],
  };
  const PACK_ABOUT = {
    soft: "gentle round tones. the default.",
    glass: "bright little bells.",
    wood: "short knocks, like a wooden xylophone.",
    retro: "quiet square waves, like an old console.",
  };
  let audio = null;
  const lastSound = {};

  function audioContext() {
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) return null;
    try {
      if (!audio) audio = new Context();
      if (audio.state === "suspended") audio.resume().catch(() => {});
    } catch (_) { return null; }
    return audio;
  }

  function play(event, force = false) {
    if (!force && (!settings.sounds || (event === "type" && !settings.typingSounds))) return;
    const notes = SOUND_EVENTS[event];
    const volume = clamp(Number(settings.volume) || 0, 0, 100) / 100;
    if (!notes || !volume) return;
    const now = performance.now();
    if (now - (lastSound[event] || 0) < (event === "type" ? 30 : 80)) return;
    lastSound[event] = now;
    const context = audioContext();
    if (!context) return;
    const [kind, octave, attack, decay, overtone] = SOUND_PACKS[settings.soundPack] || SOUND_PACKS.soft;
    try {
      const master = context.createGain();
      master.gain.value = 0.22 * volume * (kind === "square" ? 0.45 : 1);
      master.connect(context.destination);
      const begin = context.currentTime + 0.01;
      for (const [frequency, start, seconds, loudness] of notes) {
        const at = begin + start;
        const fade = Math.max(0.05, seconds * 3) / decay;
        const voice = (type, pitch, amount, fall) => {
          const tone = context.createOscillator();
          const gain = context.createGain();
          tone.type = type;
          tone.frequency.value = pitch;
          gain.gain.setValueAtTime(0, at);
          gain.gain.linearRampToValueAtTime(amount, at + Math.max(0.001, attack));
          gain.gain.setTargetAtTime(0, at + attack, fall);
          gain.gain.setTargetAtTime(0, at + seconds, 0.012);
          tone.connect(gain).connect(master);
          tone.start(at);
          tone.stop(at + seconds + 0.12);
        };
        const pitch = frequency * 2 ** octave;
        voice(kind, pitch, loudness, fade);
        if (overtone) voice("sine", pitch * 2, loudness * overtone, fade / 2);
      }
      setTimeout(() => master.disconnect(), 1200);
    } catch (_) { /* sounds are a nicety; never let them break anything */ }
  }
  // browsers only allow sound after the first click or key press
  const unlock = () => { if (settings.sounds) audioContext(); };
  addEventListener("pointerdown", unlock, { once: true, capture: true });
  addEventListener("keydown", unlock, { once: true, capture: true });

  // ----- settings ----------------------------------------------------------------------------------------
  function loadSettings() {
    try {
      const stored = JSON.parse(storage.get(SETTINGS_KEY) || "{}");
      if (stored && typeof stored === "object") {
        for (const key of Object.keys(DEFAULTS)) if (key in stored) settings[key] = stored[key];
      }
    } catch (_) { /* broken settings: use the defaults */ }
    if (!settings.game || typeof settings.game !== "object" || Array.isArray(settings.game)) settings.game = {};
  }
  function saveSettings() { storage.set(SETTINGS_KEY, JSON.stringify(settings)); }

  function setSetting(key, value) {
    settings[key] = value;
    saveSettings();
    applySettings();
  }

  const THEME_VARS = { "--bg": "bg", "--panel": "panel", "--panel-alt": "panel_alt", "--editor-bg": "editor_bg",
    "--text": "text", "--muted": "muted", "--dim": "dim", "--accent": "moss", "--accent-light": "moss_light",
    "--accent-text": "accent_text", "--border": "border", "--hover": "hover", "--select": "select", "--match": "match",
    "--active-line": "active_line", "--error": "error", "--warning": "number", "--error-line": "error_line" };
  const SYNTAX_NAMES = ["command", "flow", "string", "number", "comment", "brace", "function", "keyword", "color", "operator"];

  function applyTheme() {
    const root = document.documentElement;
    for (const name of Object.keys(THEME_VARS)) root.style.removeProperty(name);
    for (const name of SYNTAX_NAMES) root.style.removeProperty("--syn-" + name);
    root.style.removeProperty("--stage-bg");
    root.style.removeProperty("color-scheme");
    const theme = settings.theme !== "auto" && manifest.themes ? manifest.themes[settings.theme] : null;
    let dark = !matchMedia("(prefers-color-scheme: light)").matches;
    if (theme) {
      dark = theme.dark;
      for (const [name, key] of Object.entries(THEME_VARS)) if (theme.colors[key]) root.style.setProperty(name, theme.colors[key]);
      for (const [name, value] of Object.entries(theme.syntax || {})) root.style.setProperty("--syn-" + name, value);
      root.style.setProperty("--stage-bg", dark ? mix(theme.colors.bg, "#000000", 0.25) : theme.colors.panel_alt);
      root.style.colorScheme = dark ? "dark" : "light";
    }
    if (isHex(settings.accent)) {
      const accent = toHex(rgb(settings.accent));
      const base = getComputedStyle(root).getPropertyValue("--editor-bg").trim();
      const behind = isHex(base) ? base : dark ? "#171717" : "#fbfaf7";
      const light = dark ? mix(accent, "#ffffff", 0.35) : mix(accent, "#000000", 0.2);
      root.style.setProperty("--accent", accent);
      root.style.setProperty("--accent-light", light);
      root.style.setProperty("--accent-text", luminance(accent) > 0.18 ? "#0d0f0a" : "#ffffff");
      root.style.setProperty("--select", mix(behind, accent, 0.32));
      root.style.setProperty("--match", mix(behind, accent, 0.42));
      root.style.setProperty("--active-line", mix(behind, accent, 0.07));
      root.style.setProperty("--syn-command", light);
    }
  }
  matchMedia("(prefers-color-scheme: light)").addEventListener?.("change", () => applySettings());

  function applySettings() {
    document.body.classList.toggle("no-motion", !settings.motion);
    document.documentElement.style.setProperty("--speed", String(SPEEDS[settings.speed] || 1));
    applyTheme();
    const size = clamp(Math.round(Number(settings.fontSize) || 14), 10, 26);
    editor.style.setProperty("--code-size", size + "px");
    editor.style.setProperty("--code-line", Math.round(size * (SPACING[settings.spacing] || 1.5)) + "px");
    if (settings.font) editor.style.setProperty("--mono", `${settings.font}, "Cascadia Mono", Consolas, "SF Mono", Menlo, monospace`);
    else editor.style.removeProperty("--mono");
    document.body.classList.toggle("smooth-caret", Boolean(settings.smoothCaret));
    hintbar.hidden = !settings.hints;
    measure();
    render();
    applySplit();
    updateCaret(true);
    updateHint();
    moveTabIndicator();
  }

  // ----- the editor: highlighting -------------------------------------------------------------------------
  const ASSIGN_START = /^([A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\[[^\]]*\])*)\s*(\+=|-=|\*=|\/=|=)(?!=)/;
  const EXPR_TOKEN = /("[^"]*"?|'[^']*'?)|(#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b)|((?<![\w.])\d+(?:\.\d+)?)|([A-Za-z_]\w*)|(==|!=|>=|<=|\+=|-=|\*=|\/=|&&|\|\||[-+*/%<>=!^])|([{}])/g;

  function matchBrace(text, index) {
    let depth = 0, quote = null;
    for (let scan = index; scan < text.length; scan++) {
      const char = text[scan];
      if (quote) { if (char === quote) quote = null; }
      else if (char === '"' || char === "'") quote = char;
      else if (char === "{") depth++;
      else if (char === "}") { depth--; if (depth === 0) return scan; }
    }
    return -1;
  }

  function expression(text, start, end, out) {
    const part = text.slice(0, end);
    const pattern = new RegExp(EXPR_TOKEN.source, "g");
    pattern.lastIndex = start;
    for (let m; (m = pattern.exec(part));) {
      const a = m.index, b = a + m[0].length;
      if (m[4]) {
        if (part.slice(b).trimStart().startsWith("(")) out.push(["function", a, b]);
        else if (WORDS.has(m[4])) out.push(["keyword", a, b]);
      } else if (m[1]) out.push(["string", a, b]);
      else if (m[2]) out.push(["color", a, b]);
      else if (m[3]) out.push(["number", a, b]);
      else if (m[5]) out.push(["operator", a, b]);
      else if (m[6]) out.push(["brace", a, b]);
    }
  }

  function plain(text, start, out, colours) {
    let index = start;
    const length = text.length;
    while (index < length) {
      if (/\s/.test(text[index])) { index++; continue; }
      const tokenStart = index;
      let simple = true;
      while (index < length && !/\s/.test(text[index])) {
        const char = text[index];
        if (char === '"' || (char === "'" && index === tokenStart)) {
          const closing = text.indexOf(char, index + 1);
          if (closing < 0) { index++; continue; }
          out.push(["string", index, closing + 1]);
          index = closing + 1;
          simple = false;
        } else if (char === "{") {
          const closing = matchBrace(text, index);
          if (closing < 0) { index++; continue; }
          out.push(["brace", index, index + 1], ["brace", closing, closing + 1]);
          expression(text, index + 1, closing, out);
          index = closing + 1;
          simple = false;
        } else index++;
      }
      if (simple) {
        const word = text.slice(tokenStart, index);
        if (/^-?\d+(?:\.\d+)?$/.test(word)) out.push(["number", tokenStart, index]);
        else if (/^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})$/.test(word)) out.push(["color", tokenStart, index]);
        else if (colours && colorNames.has(word.toLowerCase())) out.push(["color", tokenStart, index]);
      }
    }
  }

  // (kind, start, end) for one line, like studio/editor.py's line_tokens
  function lineTokens(text) {
    const out = [];
    const stripped = text.trimStart();
    if (!stripped) return out;
    const offset = text.length - stripped.length;
    if (stripped.startsWith("//")) return [["comment", offset, text.length]];
    const match = /^[A-Za-z_]\w*/.exec(stripped);
    const first = match ? match[0] : "";
    const after = offset + first.length;
    const known = commandsByName.size ? commandsByName.has(first) || first === "elif" : Boolean(first);
    if (known && (!ASSIGN_START.test(stripped) || first === "set" || first === "for" || !commandsByName.has(first))) {
      out.push([FLOW.has(first) ? "flow" : "command", offset, after]);
      const elseIf = first === "else" ? /^\s+if\b/.exec(text.slice(after)) : null;
      if (elseIf) {
        out.push(["flow", after + elseIf[0].length - 2, after + elseIf[0].length]);
        expression(text, after + elseIf[0].length, text.length, out);
      } else if (EXPRESSION_LINES.has(first)) expression(text, after, text.length, out);
      else if (first === "function") {
        const name = /^(\s+)([A-Za-z_]\w*)/.exec(text.slice(after));
        if (name) out.push(["function", after + name[1].length, after + name[0].length]);
      } else plain(text, after, out, COLOR_COMMANDS.has(first));
      return out;
    }
    if (ASSIGN_START.test(stripped)) {
      expression(text, offset, text.length, out);
      return out;
    }
    if (first && text.slice(after).trimStart().startsWith("(")) {
      out.push(["function", offset, after]);
      expression(text, after, text.length, out);
      return out;
    }
    plain(text, offset, out, false);
    return out;
  }

  // one line as html: syntax colours, rainbow brackets, find matches and letters that were just typed
  function paintLine(line, start, now) {
    const length = line.length;
    if (!length) return "";
    const kinds = new Array(length).fill("");
    for (const [kind, a, b] of lineTokens(line)) for (let i = a; i < b && i < length; i++) kinds[i] = "t-" + kind;
    if (settings.rainbow) {
      let depth = 0;
      for (let i = 0; i < length; i++) {
        if (kinds[i] === "t-string" || kinds[i] === "t-comment") continue;
        const char = line[i];
        if (char === "(" || char === "[") { kinds[i] = "b" + (depth % 3); depth++; }
        else if (char === ")" || char === "]") { depth = Math.max(0, depth - 1); kinds[i] = "b" + (depth % 3); }
      }
    }
    const marks = new Array(length).fill("");
    const delays = new Array(length).fill(0);
    const end = start + length;
    findHits.forEach(([a, b], index) => {
      if (b <= start || a >= end) return;
      for (let i = Math.max(a, start); i < Math.min(b, end); i++) marks[i - start] = index === findIndex ? "find-current" : "find-hit";
    });
    for (const effect of fx) {
      if (effect.to <= start || effect.from >= end) continue;
      const delay = Math.round(effect.born - now);
      for (let i = Math.max(effect.from, start); i < Math.min(effect.to, end); i++) {
        marks[i - start] = (marks[i - start] ? marks[i - start] + " " : "") + "fx-" + effect.kind;
        delays[i - start] = delay;
      }
    }
    let html = "";
    let i = 0;
    while (i < length) {
      let j = i + 1;
      while (j < length && kinds[j] === kinds[i] && marks[j] === marks[i] && delays[j] === delays[i]) j++;
      const piece = escapeHtml(line.slice(i, j));
      const classes = (kinds[i] + " " + marks[i]).trim();
      if (!classes) html += piece;
      else html += `<span class="${classes}"${delays[i] ? ` style="animation-delay:${delays[i]}ms"` : ""}>${piece}</span>`;
      i = j;
    }
    return html;
  }

  function problemLines() {
    const marks = new Map();
    for (const problem of problems) {
      if (!problem.line) continue;
      const severity = problem.severity || "error";
      if (marks.get(problem.line) !== "error") marks.set(problem.line, severity);
    }
    return marks;
  }

  function render() {
    const now = performance.now();
    fx = fx.filter((effect) => now - effect.born < FX_LIFE * (speed() || 0));
    for (const [line, flash] of flashes) if (now - flash.born > 1200 * (speed() || 0)) flashes.delete(line);
    const lines = source.value.split("\n");
    const marks = problemLines();
    let offset = 0;
    const html = lines.map((line, index) => {
      let painted = paintLine(line, offset, now);
      offset += line.length + 1;
      const number = index + 1;
      const flash = flashes.get(number);
      if (marks.get(number) === "error") painted = `<span class="line-error">${painted || " "}</span>`;
      if (flash) painted = `<span class="${flash.kind}" style="animation-delay:${Math.round(flash.born - now)}ms">${painted || " "}</span>`;
      return painted;
    });
    highlight.innerHTML = html.join("\n") + "\n ";
    gutter.innerHTML = lines.map((_, index) => {
      const mark = marks.get(index + 1);
      return `<div${mark ? ` class="${mark}"` : ""} data-line="${index + 1}">${index + 1}</div>`;
    }).join("");
    currentGutterLine = null;
  }

  // ----- the editor: the caret, the current line and keeping the caret in view -----------------------------
  // measures one letter; it sits in a box with no size so it never makes the editor scroll
  const measurer = h("span", { "aria-hidden": "true" });
  measurer.style.cssText = "visibility:hidden;white-space:pre;pointer-events:none";
  const measureBox = h("div", { "aria-hidden": "true" }, measurer);
  measureBox.style.cssText = "position:absolute;left:0;top:0;width:0;height:0;overflow:hidden";
  code.append(measureBox);
  function measure() {
    measurer.textContent = "0".repeat(80);
    const width = measurer.getBoundingClientRect().width / 80;
    if (width > 0) charWidth = width;
    const height = parseFloat(getComputedStyle(highlight).lineHeight);
    if (height > 0) lineHeight = height;
  }

  const lineStart = (index) => source.value.lastIndexOf("\n", index - 1) + 1;
  function lineEnd(index) {
    const end = source.value.indexOf("\n", index);
    return end === -1 ? source.value.length : end;
  }
  function visualColumn(text) {
    let column = 0;
    for (const char of text) column = char === "\t" ? column + 4 - (column % 4) : column + 1;
    return column;
  }
  function caretPoint(index) {
    const text = source.value;
    const start = text.lastIndexOf("\n", index - 1) + 1;
    let line = 0;
    for (let i = text.indexOf("\n"); i !== -1 && i < start; i = text.indexOf("\n", i + 1)) line++;
    const column = visualColumn(text.slice(start, index));
    return { line, column, x: PAD_LEFT + column * charWidth, y: PAD_TOP + line * lineHeight };
  }
  const activeEnd = () => (source.selectionDirection === "backward" ? source.selectionStart : source.selectionEnd);

  function keepVisible(point) {
    const top = point.y - 6, bottom = point.y + lineHeight + 6;
    if (top < editor.scrollTop) editor.scrollTop = Math.max(0, top);
    else if (bottom > editor.scrollTop + editor.clientHeight) editor.scrollTop = bottom - editor.clientHeight;
    const side = gutter.offsetWidth;
    const x = side + point.x;
    if (x - 24 < editor.scrollLeft + side) editor.scrollLeft = Math.max(0, point.x - 24);
    else if (x + 24 > editor.scrollLeft + editor.clientWidth) editor.scrollLeft = x + 24 - editor.clientWidth;
  }

  let caretFrame = 0;
  function scheduleCaret(follow) {
    if (follow) scheduleCaret.follow = true;
    if (caretFrame) return;
    caretFrame = requestAnimationFrame(() => {
      caretFrame = 0;
      updateCaret(false, scheduleCaret.follow);
      scheduleCaret.follow = false;
      updateHint();
    });
  }

  function updateCaret(snap, follow) {
    const focused = document.activeElement === source;
    code.classList.toggle("focused", focused);
    const point = caretPoint(activeEnd());
    const collapsed = source.selectionStart === source.selectionEnd;
    activeLine.style.transform = `translateY(${point.y - PAD_TOP}px)`;
    activeLine.style.height = lineHeight + "px";
    code.classList.toggle("show-line", Boolean(settings.lineHighlight) && focused && collapsed);
    if (currentGutterLine !== point.line) {
      const old = gutter.children[currentGutterLine];
      if (old) old.classList.remove("current");
      const now = gutter.children[point.line];
      if (now) now.classList.add("current");
      currentGutterLine = point.line;
    }
    if (settings.smoothCaret) {
      const style = settings.caretStyle;
      let width = clamp(Number(settings.caretWidth) || 2, 1, 6), height = lineHeight, y = point.y;
      if (style === "block") width = charWidth;
      else if (style === "underline") { width = charWidth; height = 2; y = point.y + lineHeight - 2; }
      const jump = snap || settings.caretMotion === "jump" || !settings.motion || Math.abs(point.line - lastCaretLine) > 8;
      caret.className = "caret" + (style !== "line" ? " " + style : "") + (jump ? " snap" : "");
      caret.style.width = width + "px";
      caret.style.height = height + "px";
      caret.style.transform = `translate(${point.x - (style === "line" ? width / 2 : 0)}px, ${y}px)`;
      caret.style.visibility = collapsed ? "" : "hidden";
      void caret.offsetWidth; // restart the blink, so the caret stays solid while it moves
      if (settings.caretBlink !== "solid") caret.classList.add("blink-" + (settings.caretBlink === "blink" ? "blink" : "fade"));
    }
    lastCaretLine = point.line;
    if (follow) keepVisible(point);
  }

  // ----- the editor: changing the text --------------------------------------------------------------------
  function insert(text) {
    source.focus();
    // execCommand keeps ctrl+z working; setRangeText is the fallback for browsers that dropped it
    if (!document.execCommand || !document.execCommand("insertText", false, text)) {
      source.setRangeText(text, source.selectionStart, source.selectionEnd, "end");
      source.dispatchEvent(new Event("input"));
    }
  }
  function replaceRange(from, to, text, selectFrom, selectTo) {
    source.focus();
    source.setSelectionRange(from, to);
    if (text === "" && from !== to) {
      if (!document.execCommand || !document.execCommand("delete")) {
        source.setRangeText("", from, to, "end");
        source.dispatchEvent(new Event("input"));
      }
    } else if (text !== "" || from !== to) insert(text);
    if (selectFrom !== undefined) source.setSelectionRange(selectFrom, selectTo === undefined ? selectFrom : selectTo);
    scheduleCaret(true);
  }

  // the whole lines the selection touches
  function selectedLines() {
    const value = source.value;
    const from = lineStart(source.selectionStart);
    let to = source.selectionEnd;
    if (to > from && value[to - 1] === "\n" && to > source.selectionStart) to--;
    const end = lineEnd(to);
    return { from, to: end, text: value.slice(from, end) };
  }

  function indentSelection(outdent) {
    const { from, to, text } = selectedLines();
    const changed = text.split("\n").map((line) => {
      if (!outdent) return INDENT + line;
      return line.slice(/^( {0,4}|\t)/.exec(line)[0].length);
    }).join("\n");
    replaceRange(from, to, changed, from, from + changed.length);
  }

  function toggleComment() {
    const { from, to, text } = selectedLines();
    const lines = text.split("\n");
    const filled = lines.filter((line) => line.trim());
    const commented = filled.length && filled.every((line) => line.trimStart().startsWith("//"));
    const least = Math.min(...filled.map((line) => line.length - line.trimStart().length), Infinity);
    const changed = lines.map((line) => {
      if (!line.trim()) return line;
      if (commented) return line.replace(/^(\s*)\/\/ ?/, "$1");
      const cut = Number.isFinite(least) ? least : 0;
      return line.slice(0, cut) + "// " + line.slice(cut);
    }).join("\n");
    replaceRange(from, to, changed, from, from + changed.length);
  }

  function duplicateLines() {
    const { to, text } = selectedLines();
    const start = source.selectionStart, end = source.selectionEnd, shift = text.length + 1;
    replaceRange(to, to, "\n" + text, start + shift, end + shift);
  }

  function deleteLines() {
    const { from, to } = selectedLines();
    const value = source.value;
    if (to < value.length) replaceRange(from, to + 1, "", from);
    else if (from > 0) replaceRange(from - 1, to, "", lineStart(from - 1));
    else replaceRange(from, to, "", 0);
  }

  function moveLines(down) {
    const { from, to, text } = selectedLines();
    const value = source.value;
    const start = source.selectionStart, end = source.selectionEnd;
    if (down) {
      if (to >= value.length) return;
      const nextEnd = lineEnd(to + 1);
      const next = value.slice(to + 1, nextEnd);
      const shift = next.length + 1;
      replaceRange(from, nextEnd, next + "\n" + text, start + shift, end + shift);
    } else {
      if (from === 0) return;
      const prevStart = lineStart(from - 1);
      const prev = value.slice(prevStart, from - 1);
      const shift = prev.length + 1;
      replaceRange(prevStart, to, text + "\n" + prev, start - shift, end - shift);
    }
  }

  const firstWord = (line) => (/^\s*([A-Za-z_]\w*)/.exec(line) || [])[1] || "";
  const leading = (line) => /^[ \t]*/.exec(line)[0];
  // a line that starts a block (and isn't a one-line "if x then print hi")
  const opensBlock = (line) => OPENERS.has(firstWord(line)) && !/\bthen\s+\S/.test(line);

  // does the program have more blocks opened than closed?
  function needsEnd() {
    let depth = 0;
    for (const line of source.value.split("\n")) {
      if (opensBlock(line)) depth++;
      else if (firstWord(line) === "end") depth--;
    }
    return depth > 0;
  }

  // where end, else, elseif, case and catch should sit: level with the block they belong to
  function matchingIndent(index) {
    const lines = source.value.slice(0, lineStart(index)).split("\n");
    lines.pop();
    let depth = 0;
    for (let i = lines.length - 1; i >= 0; i--) {
      const word = firstWord(lines[i]);
      if (word === "end") depth++;
      else if (opensBlock(lines[i])) {
        if (depth === 0) return leading(lines[i]);
        depth--;
      }
    }
    return null;
  }

  function tidyIndentation() {
    let depth = 0;
    const tidy = source.value.split("\n").map((line) => {
      const text = line.trim();
      if (!text) return "";
      const word = firstWord(text);
      if (word === "end") depth = Math.max(0, depth - 1);
      const level = MIDDLES.has(word) || word === "elif" ? Math.max(0, depth - 1) : depth;
      if (opensBlock(text)) depth++;
      return INDENT.repeat(level) + text;
    }).join("\n");
    if (tidy === source.value) { toast("The indentation is already tidy"); return; }
    const caretLine = caretPoint(source.selectionStart).line;
    replaceRange(0, source.value.length, tidy);
    goToLine(caretLine + 1, false, true);
    toast("Tidied up the indentation");
  }

  function pressEnter() {
    const index = source.selectionStart;
    const start = lineStart(index);
    let current = source.value.slice(start, index);
    const word = firstWord(current);
    // end and the middle words move to the level of their block before the new line starts
    if (word === "end" || MIDDLES.has(word) || word === "elif") {
      const wanted = matchingIndent(index);
      const have = leading(current);
      if (wanted !== null && wanted !== have) {
        replaceRange(start, start + have.length, wanted, index - have.length + wanted.length);
        current = wanted + current.slice(have.length);
      }
    }
    const indent = leading(current);
    const rest = source.value.slice(source.selectionStart, lineEnd(source.selectionStart));
    if (opensBlock(current) && settings.autoEnd && !rest.trim() && needsEnd()) {
      const at = source.selectionStart;
      insert("\n" + indent + INDENT + "\n" + indent + "end");
      const inside = at + 1 + indent.length + INDENT.length;
      source.setSelectionRange(inside, inside);
    } else {
      const deeper = opensBlock(current) || MIDDLES.has(word) || word === "elif";
      insert("\n" + indent + (deeper ? INDENT : ""));
    }
    scheduleCaret(true);
  }

  const PAIRS = { "(": ")", "[": "]", "{": "}", '"': '"' };
  function autoPair(event) {
    const start = source.selectionStart, end = source.selectionEnd, value = source.value;
    const next = value[end] || "";
    const key = event.key;
    if ((key === ")" || key === "]" || key === "}" || key === '"') && start === end && next === key) {
      source.setSelectionRange(start + 1, start + 1);
      scheduleCaret(true);
      return true;
    }
    if (!PAIRS[key]) return false;
    if (start !== end) {
      const chosen = value.slice(start, end);
      insert(key + chosen + PAIRS[key]);
      source.setSelectionRange(start + 1, start + 1 + chosen.length);
      return true;
    }
    if (key === '"' && /[\w"]/.test(value[start - 1] || "")) return false;
    if (next && !/[\s)\]},]/.test(next)) return false;
    insert(key + PAIRS[key]);
    source.setSelectionRange(start + 1, start + 1);
    return true;
  }

  // ----- suggestions and the hint bar -------------------------------------------------------------------
  function documentNames() {
    const names = new Map();
    for (const line of source.value.split("\n")) {
      const text = line.trim();
      if (!text || text.startsWith("//")) continue;
      let m;
      if ((m = /^(?:set|local|const|global|input|for)\s+([A-Za-z_]\w*)/.exec(text))) names.set(m[1], "var");
      else if ((m = /^function\s+([A-Za-z_]\w*)/.exec(text))) names.set(m[1], "own");
      else if ((m = /^([A-Za-z_]\w*)\s*(?:\+=|-=|\*=|\/=|=)(?!=)/.exec(text)) && !commandsByName.has(m[1])) names.set(m[1], "var");
      else {
        const words = text.split(/\s+/);
        const command = commandsByName.get(words[0]);
        if (command && ["2d", "3d", "ui"].includes(command.category) && words.length > 2 && /^[A-Za-z_]\w*$/.test(words[1])) {
          if (!names.has(words[1])) names.set(words[1], "obj");
        }
      }
    }
    return names;
  }

  function completionContext(force) {
    const index = source.selectionStart;
    if (index !== source.selectionEnd) return null;
    const start = lineStart(index);
    const before = source.value.slice(start, index);
    if (/\w/.test(source.value[index] || "")) return null;
    if (before.trimStart().startsWith("//")) return null;
    const word = /[A-Za-z_]\w*$/.exec(before);
    const prefix = word ? word[0] : "";
    if (!prefix && !force) return null;
    const head = before.slice(0, before.length - prefix.length);
    if ((head.match(/"/g) || []).length % 2) return null;
    const opens = (head.match(/{/g) || []).length - (head.match(/}/g) || []).length;
    const command = firstWord(before);
    const first = head.trim() === "";
    const inExpression = opens > 0 || EXPRESSION_LINES.has(command) || ASSIGN_START.test(before.trimStart());
    return { prefix, from: index - prefix.length, to: index, first, inExpression, command };
  }

  function suggestions(context) {
    const out = [];
    const names = documentNames();
    const lower = context.prefix.toLowerCase();
    const add = (name, kind, about) => { if (name.toLowerCase().startsWith(lower)) out.push({ name, kind, about }); };
    if (context.first) {
      for (const command of commandsByName.values()) add(command.name, "cmd", command.usage);
    }
    if (context.inExpression) {
      for (const fn of functionsByName.values()) add(fn.name, "fn", fn.usage);
      for (const word of WORDS) add(word, "word", "keyword");
    }
    for (const [name, kind] of names) {
      if (name === context.prefix) continue;
      if (kind === "own") add(name, "fn", "your function");
      else if (!context.first || kind === "var" || kind === "obj") add(name, kind, kind === "obj" ? "object" : "variable");
    }
    if (!context.first && (COLOR_COMMANDS.has(context.command) || context.inExpression)) {
      for (const name of colorNames.keys()) add(name, "color", "colour");
    }
    const rank = { var: 0, obj: 1, cmd: 2, fn: 3, word: 4, color: 5 };
    const seen = new Set();
    return out.filter((item) => !seen.has(item.name) && seen.add(item.name))
      .sort((a, b) => (a.name.toLowerCase() === lower ? -1 : 0) - (b.name.toLowerCase() === lower ? -1 : 0)
        || rank[a.kind] - rank[b.kind] || a.name.length - b.name.length || a.name.localeCompare(b.name))
      .slice(0, context.prefix ? 8 : 40);
  }

  function showCompletion(force) {
    if (!reference || (!settings.suggestions && !force)) return closeCompletion();
    const context = completionContext(force);
    if (!context) return closeCompletion();
    const items = suggestions(context);
    if (!items.length || (!force && items.length === 1 && items[0].name === context.prefix)) return closeCompletion();
    completion = Object.assign(context, { items, index: 0 });
    completeBox.textContent = "";
    items.forEach((item, index) => {
      const row = h("div", { class: "item " + item.kind + (index === 0 ? " chosen" : ""), role: "option", id: "suggestion-" + index,
        "aria-selected": String(index === 0) }, h("b", { text: item.name }), h("span", { text: item.about || "" }));
      row.addEventListener("mousedown", (event) => { event.preventDefault(); acceptCompletion(index); });
      completeBox.append(row);
    });
    const wasHidden = completeBox.hidden;
    completeBox.hidden = false;
    source.setAttribute("aria-activedescendant", "suggestion-0");
    placeCompletion(wasHidden);
  }

  function placeCompletion() {
    const point = caretPoint(completion.from);
    const codeBox = code.getBoundingClientRect();
    const pane = editorPane.getBoundingClientRect();
    const width = completeBox.offsetWidth, height = completeBox.offsetHeight;
    let left = codeBox.left + point.x - pane.left - 8;
    let top = codeBox.top + point.y + lineHeight - pane.top + 2;
    left = clamp(left, 4, Math.max(4, pane.width - width - 4));
    if (top + height > pane.height - hintbar.offsetHeight - 4) top = codeBox.top + point.y - pane.top - height - 2;
    completeBox.style.left = left + "px";
    completeBox.style.top = Math.max(4, top) + "px";
  }

  function closeCompletion() {
    completion = null;
    completeBox.hidden = true;
    source.removeAttribute("aria-activedescendant");
  }

  function chooseCompletion(step) {
    const rows = completeBox.children;
    rows[completion.index]?.classList.remove("chosen");
    rows[completion.index]?.setAttribute("aria-selected", "false");
    completion.index = (completion.index + step + rows.length) % rows.length;
    const row = rows[completion.index];
    row.classList.add("chosen");
    row.setAttribute("aria-selected", "true");
    row.scrollIntoView({ block: "nearest" });
    source.setAttribute("aria-activedescendant", row.id);
  }

  let quietInput = false;
  function acceptCompletion(index) {
    const item = completion.items[index === undefined ? completion.index : index];
    const { from, to, first } = completion;
    closeCompletion();
    quietInput = true;
    source.focus();
    source.setSelectionRange(from, to);
    const next = source.value[to] || "";
    if (item.kind === "fn") {
      insert(item.name + (settings.autoPairs ? "()" : "("));
      if (settings.autoPairs) source.setSelectionRange(source.selectionStart - 1, source.selectionStart - 1);
    } else insert(item.name + (item.kind === "cmd" && first && next !== " " ? " " : ""));
    quietInput = false;
    play("click");
    scheduleCaret(true);
  }

  function updateHint() {
    if (!settings.hints) return;
    const index = source.selectionStart;
    const start = lineStart(index);
    const line = source.value.slice(start, lineEnd(index));
    const before = source.value.slice(start, index);
    const number = caretPoint(index).line + 1;
    let html = "";
    const problem = problems.find((p) => p.line === number);
    if (problem) {
      html = `<span class="${problem.severity === "warning" ? "warn" : "bad"}">line ${number}: ${escapeHtml(problem.message)}</span>`;
    } else if (reference) {
      let fn = null;
      for (let i = before.length - 1, depth = 0; i >= 0; i--) {
        if (before[i] === ")") depth++;
        else if (before[i] === "(") {
          if (depth === 0) {
            const name = /([A-Za-z_]\w*)\s*$/.exec(before.slice(0, i));
            fn = name ? functionsByName.get(name[1]) : null;
            break;
          }
          depth--;
        }
      }
      const command = commandsByName.get(firstWord(line));
      if (fn) html = `<code>${escapeHtml(fn.usage)}</code> ${escapeHtml(fn.summary)}`;
      else if (command) html = `<code>${escapeHtml(command.usage)}</code> ${escapeHtml(command.summary)}`;
    }
    if (!html) {
      html = "<kbd>Ctrl</kbd>+<kbd>Space</kbd> suggestions · <kbd>F1</kbd> help for the word under the cursor · " +
        "<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> every action";
    }
    if (html !== lastHint) {
      lastHint = html;
      hintbar.innerHTML = `<span class="fade">${html}</span>`;
    }
  }

  function wordAtCaret() {
    const index = source.selectionStart, value = source.value;
    let a = index, b = index;
    while (a > 0 && /\w/.test(value[a - 1])) a--;
    while (b < value.length && /\w/.test(value[b])) b++;
    return value.slice(a, b);
  }

  // ----- the editor: events -------------------------------------------------------------------------------
  source.addEventListener("keydown", (event) => {
    if (completion) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        chooseCompletion(event.key === "ArrowDown" ? 1 : -1);
        return;
      }
      if ((event.key === "Enter" || event.key === "Tab") && !event.shiftKey && !mod(event)) {
        event.preventDefault();
        acceptCompletion();
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        closeCompletion();
        return;
      }
    }
    const key = event.key.toLowerCase();
    if (mod(event) && event.key === " ") {
      event.preventDefault();
      showCompletion(true);
    } else if (event.key === "Tab" && !mod(event) && !event.altKey) {
      event.preventDefault();
      if (event.shiftKey || source.selectionStart !== source.selectionEnd) indentSelection(event.shiftKey);
      else insert(INDENT);
    } else if (mod(event) && (event.key === "]" || event.key === "[")) {
      event.preventDefault();
      indentSelection(event.key === "[");
    } else if (event.key === "Enter" && !event.shiftKey && !mod(event) && !event.altKey && source.selectionStart === source.selectionEnd) {
      event.preventDefault();
      pressEnter();
    } else if (mod(event) && event.key === "/") {
      event.preventDefault();
      toggleComment();
    } else if (mod(event) && !event.shiftKey && key === "d") {
      event.preventDefault();
      duplicateLines();
    } else if (mod(event) && event.shiftKey && key === "k") {
      event.preventDefault();
      deleteLines();
    } else if (event.altKey && !mod(event) && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
      event.preventDefault();
      moveLines(event.key === "ArrowDown");
    } else if (event.key === "Backspace" && settings.autoPairs && source.selectionStart === source.selectionEnd) {
      const at = source.selectionStart, value = source.value;
      if (at > 0 && PAIRS[value[at - 1]] && PAIRS[value[at - 1]] === value[at]) {
        event.preventDefault();
        replaceRange(at - 1, at + 1, "", at - 1);
      }
    } else if (settings.autoPairs && !mod(event) && !event.altKey && event.key.length === 1 && autoPair(event)) {
      event.preventDefault();
    }
    if (/^(Arrow|Home|End|Page)/.test(event.key)) scheduleCaret(true);
  });

  function changedRange(before, after) {
    let start = 0;
    const shortest = Math.min(before.length, after.length);
    while (start < shortest && before.charCodeAt(start) === after.charCodeAt(start)) start++;
    let tail = 0;
    while (tail < shortest - start && before.charCodeAt(before.length - 1 - tail) === after.charCodeAt(after.length - 1 - tail)) tail++;
    return { at: start, removed: before.length - start - tail, added: after.length - start - tail };
  }

  source.addEventListener("input", (event) => {
    const text = source.value;
    const change = changedRange(lastText, text);
    const delta = change.added - change.removed;
    // letters that were typed earlier move along with the text around them
    fx = fx.filter((effect) => effect.to <= change.at || effect.from >= change.at + change.removed);
    for (const effect of fx) if (effect.from >= change.at) { effect.from += delta; effect.to += delta; }
    if (change.added > 0 && settings.motion) {
      const pasted = event.inputType === "insertFromPaste" || event.inputType === "insertFromDrop" || change.added > 40;
      const kind = pasted ? "paste" : settings.typing;
      if (kind && kind !== "off") fx.push({ from: change.at, to: change.at + change.added, kind, born: performance.now() });
    }
    lastText = text;
    const file = currentFile();
    if (file) {
      file.text = text;
      file.pristine = false;
    }
    if (!findbar.hidden) updateFind(true);
    else render();
    clearTimeout(checkTimer);
    checkTimer = setTimeout(check, 350);
    saveProject();
    scheduleCaret(true);
    if (!quietInput) {
      if (event.inputType === "insertText" && /\w/.test(event.data || "")) showCompletion(false);
      else if (completion && event.inputType === "deleteContentBackward") showCompletion(false);
      else closeCompletion();
      if (event.inputType && event.inputType.startsWith("insert")) play("type");
    }
  });

  for (const name of ["mouseup", "keyup", "select", "focus"]) source.addEventListener(name, () => scheduleCaret(false));
  source.addEventListener("mousedown", () => {
    closeCompletion();
    const follow = () => scheduleCaret(false);
    source.addEventListener("mousemove", follow);
    addEventListener("mouseup", () => source.removeEventListener("mousemove", follow), { once: true });
  });
  source.addEventListener("blur", () => {
    code.classList.remove("focused", "show-line");
    setTimeout(() => { if (document.activeElement !== source) closeCompletion(); }, 120);
  });
  document.addEventListener("selectionchange", () => { if (document.activeElement === source) scheduleCaret(false); });
  editor.addEventListener("scroll", () => { if (completion) placeCompletion(); }, { passive: true });

  gutter.addEventListener("click", (event) => {
    const line = event.target.closest("[data-line]");
    if (line) goToLine(Number(line.dataset.line), false);
  });

  function goToLine(number, flash = true, quiet = false) {
    const lines = source.value.split("\n");
    const index = clamp(number, 1, lines.length) - 1;
    const start = lines.slice(0, index).reduce((sum, line) => sum + line.length + 1, 0);
    source.focus();
    if (quiet) source.setSelectionRange(start + leading(lines[index]).length, start + leading(lines[index]).length);
    else source.setSelectionRange(start, start + lines[index].length);
    const top = PAD_TOP + index * lineHeight;
    if (top < editor.scrollTop || top > editor.scrollTop + editor.clientHeight - lineHeight * 2) {
      editor.scrollTop = Math.max(0, top - editor.clientHeight / 3);
    }
    if (flash && settings.motion) {
      flashes.set(index + 1, { kind: flash === "error" ? "fx-error" : "fx-jump", born: performance.now() });
      render();
    }
    updateCaret(true);
  }

  // ----- find and replace ---------------------------------------------------------------------------------
  function openFind(replacing) {
    const chosen = source.value.slice(source.selectionStart, source.selectionEnd);
    if (chosen && !chosen.includes("\n")) findText.value = chosen;
    arrive(findbar);
    const box = replacing ? replaceText : findText;
    box.focus();
    box.select();
    updateFind();
  }
  function closeFind() {
    findHits = [];
    findIndex = -1;
    findbar.hidden = true;
    render();
    source.focus();
  }
  function updateFind(keep) {
    const query = findText.value;
    const before = findHits[findIndex];
    findHits = [];
    if (query) {
      const hay = source.value.toLowerCase(), needle = query.toLowerCase();
      for (let i = hay.indexOf(needle); i !== -1 && findHits.length < 5000; i = hay.indexOf(needle, i + needle.length)) {
        findHits.push([i, i + query.length]);
      }
    }
    const from = keep && before ? before[0] : source.selectionStart;
    findIndex = findHits.length ? Math.max(0, findHits.findIndex(([a]) => a >= from)) : -1;
    if (findHits.length && findHits.findIndex(([a]) => a >= from) === -1) findIndex = 0;
    countFind();
    render();
  }
  function countFind() {
    const count = $("find-count");
    count.textContent = !findText.value ? "" : findHits.length ? `${findIndex + 1} of ${findHits.length}` : "no matches";
  }
  function goFind(step) {
    if (!findHits.length) return;
    findIndex = (findIndex + step + findHits.length) % findHits.length;
    const [a, b] = findHits[findIndex];
    source.setSelectionRange(a, b);
    keepVisible(caretPoint(a));
    countFind();
    render();
    updateCaret(false);
  }
  function replaceOne() {
    if (findIndex < 0 || !findHits.length) return;
    const [a, b] = findHits[findIndex];
    replaceRange(a, b, replaceText.value, a + replaceText.value.length);
    updateFind();
    goFind(0);
    replaceText.focus();
  }
  function replaceAll() {
    if (!findHits.length) return;
    let text = source.value;
    const count = findHits.length;
    for (let i = findHits.length - 1; i >= 0; i--) {
      const [a, b] = findHits[i];
      text = text.slice(0, a) + replaceText.value + text.slice(b);
    }
    replaceRange(0, source.value.length, text, 0);
    updateFind();
    toast(count === 1 ? "Replaced 1 match" : `Replaced ${count} matches`);
    replaceText.focus();
  }
  findText.addEventListener("input", () => { updateFind(); goFind(0); findText.focus(); });
  for (const box of [findText, replaceText]) {
    box.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        if (box === replaceText && !event.shiftKey) replaceOne();
        else goFind(event.shiftKey ? -1 : 1);
      } else if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        closeFind();
      }
    });
  }
  $("find-next").addEventListener("click", () => goFind(1));
  $("find-prev").addEventListener("click", () => goFind(-1));
  $("replace-one").addEventListener("click", replaceOne);
  $("replace-all").addEventListener("click", replaceAll);
  $("find-close").addEventListener("click", closeFind);

  // ----- files ------------------------------------------------------------------------------------------
  const currentFile = () => project.files.find((file) => file.name === project.current) || project.files[0];

  function cleanName(name) {
    let base = String(name || "").split(/[\\/]/).pop().replace(/\.(gubl|gub|txt)$/i, "");
    base = base.replace(/[^\w\- ]+/g, "").trim().slice(0, 40) || "program";
    return base + ".gubl";
  }
  function uniqueName(name, except) {
    const wanted = cleanName(name);
    const taken = (candidate) => project.files.some((file) => file !== except && file.name.toLowerCase() === candidate.toLowerCase());
    if (!taken(wanted)) return wanted;
    const base = wanted.slice(0, -5);
    for (let n = 2; ; n++) if (!taken(`${base} ${n}.gubl`)) return `${base} ${n}.gubl`;
  }

  function saveProject(now) {
    clearTimeout(saveTimer);
    const write = () => storage.set(PROJECT_KEY, JSON.stringify({
      files: project.files.map(({ name, text, pristine }) => ({ name, text, pristine: Boolean(pristine) })),
      current: project.current,
    }));
    if (now) write();
    else saveTimer = setTimeout(write, 400);
  }

  function rememberView() {
    const file = currentFile();
    if (file) views.set(file.name, { start: source.selectionStart, end: source.selectionEnd, top: editor.scrollTop, left: editor.scrollLeft });
  }

  function selectFile(name, quiet) {
    if (project.current !== name) rememberView();
    const file = project.files.find((f) => f.name === name) || project.files[0];
    project.current = file.name;
    source.value = file.text;
    lastText = file.text;
    fx = [];
    flashes.clear();
    problems = [];
    closeCompletion();
    const view = views.get(file.name);
    source.setSelectionRange(view ? view.start : 0, view ? view.end : 0);
    editor.scrollTop = view ? view.top : 0;
    editor.scrollLeft = view ? view.left : 0;
    if (!findbar.hidden) updateFind();
    else render();
    renderTabs();
    check();
    updateCaret(true);
    saveProject();
    if (!quiet) play("click");
  }

  function addFile(name, text, pristine = false) {
    const file = { name: uniqueName(name), text: String(text), pristine };
    project.files.push(file);
    selectFile(file.name, true);
    return file;
  }

  function newFile() {
    const asked = window.prompt("Name for the new file:", uniqueName("helpers"));
    if (asked === null) return;
    addFile(asked, "// " + cleanName(asked).slice(0, -5) + "\n");
    toast(`Made ${currentFile().name}. Use it from another file with: include ${currentFile().name}`);
    play("open");
  }

  function renameFile(file) {
    const asked = window.prompt("Rename this file:", file.name);
    if (asked === null || cleanName(asked) === file.name) return;
    const name = uniqueName(asked, file);
    const view = views.get(file.name);
    views.delete(file.name);
    if (view) views.set(name, view);
    if (project.current === file.name) project.current = name;
    file.name = name;
    renderTabs();
    saveProject();
  }

  function closeFile(file) {
    if (project.files.length < 2) return;
    if (file.text.trim() && !file.pristine && !window.confirm(`Delete ${file.name}? Its code will be gone.`)) return;
    const index = project.files.indexOf(file);
    const tab = fileList.querySelector(`[data-name="${CSS.escape(file.name)}"]`);
    const finish = () => {
      project.files.splice(project.files.indexOf(file), 1);
      views.delete(file.name);
      if (project.current === file.name) selectFile(project.files[Math.max(0, index - 1)].name, true);
      else renderTabs();
      saveProject();
    };
    play("close");
    if (tab && speed()) {
      tab.classList.add("leaving");
      setTimeout(finish, 180 * speed());
    } else finish();
  }

  function renderTabs() {
    fileList.textContent = "";
    const many = project.files.length > 1;
    for (const file of project.files) {
      const chosen = file.name === project.current;
      const tab = h("button", { class: "file-tab", role: "tab", "aria-selected": String(chosen), "data-name": file.name,
        title: "Double-click (or F2) to rename" + (many ? ", Delete to remove" : "") },
      h("span", { class: "name", text: file.name }),
      many ? h("span", { class: "close", role: "button", "aria-label": "Delete " + file.name, title: "Delete this file", text: "×" }) : null);
      tab.addEventListener("click", (event) => {
        if (event.target.classList.contains("close")) { event.stopPropagation(); closeFile(file); return; }
        if (!chosen) selectFile(file.name);
        else source.focus();
      });
      tab.addEventListener("dblclick", (event) => { if (!event.target.classList.contains("close")) renameFile(file); });
      tab.addEventListener("keydown", (event) => {
        if (event.key === "F2") { event.preventDefault(); renameFile(file); }
        else if (event.key === "Delete") { event.preventDefault(); closeFile(file); }
      });
      fileList.append(tab);
      if (chosen) requestAnimationFrame(() => tab.scrollIntoView({ block: "nearest", inline: "nearest" }));
    }
  }
  $("add-file").addEventListener("click", newFile);

  async function openFiles(list) {
    let last = null;
    for (const picked of list) {
      if (picked.size > 2_000_000) { toast(picked.name + " is too big to open here", "bad"); continue; }
      last = addFile(picked.name, await picked.text());
    }
    if (last) {
      play("open");
      toast(list.length === 1 ? `Opened ${last.name}` : `Opened ${list.length} files`);
    }
  }
  $("open-file").addEventListener("change", (event) => {
    openFiles([...event.target.files]);
    event.target.value = "";
  });
  editor.addEventListener("dragover", (event) => {
    if ([...(event.dataTransfer?.types || [])].includes("Files")) event.preventDefault();
  });
  editor.addEventListener("drop", (event) => {
    const files = [...(event.dataTransfer?.files || [])].filter((file) => /\.(gubl|gub|txt)$/i.test(file.name));
    if (!files.length) return;
    event.preventDefault();
    openFiles(files);
  });

  // ----- checking ---------------------------------------------------------------------------------------
  function syncFiles() {
    if (!bridge || !bridge.set_files) return;
    const files = {};
    for (const file of project.files) files[file.name] = file.text;
    try { bridge.set_files(JSON.stringify(files)); } catch (_) { /* include just won't find them */ }
  }

  function check() {
    if (!bridge) return;
    try {
      problems = JSON.parse(bridge.check(source.value));
    } catch (error) {
      problems = [{ line: 0, severity: "error", message: "the checker stopped: " + error.message }];
    }
    render();
    updateCaret(false);
    showProblems();
    lastHint = "";
    updateHint();
    if ($("panel-javascript").hidden === false) showJavaScript();
  }

  function showProblems() {
    const list = $("problems");
    list.textContent = "";
    const errors = problems.filter((p) => (p.severity || "error") === "error").length;
    const count = $("problem-count");
    const text = String(problems.length);
    if (count.textContent !== text && problems.length) {
      count.classList.remove("bump");
      void count.offsetWidth;
      count.classList.add("bump");
    }
    count.hidden = problems.length === 0;
    count.textContent = text;
    count.classList.toggle("warn", errors === 0);
    if (!problems.length) list.append(h("li", { class: "empty", text: "No problems found." }));
    problems.forEach((problem, index) => {
      const item = h("li", { class: problem.severity || "error" },
        h("span", { class: "where", text: problem.line ? "line " + problem.line : "" }),
        h("span", { text: problem.message }));
      item.style.animationDelay = Math.min(index, 12) * 25 + "ms";
      if (problem.line) item.addEventListener("click", () => goToLine(problem.line, problem.severity === "warning" ? true : "error"));
      list.append(item);
    });
    if (!document.body.classList.contains("running")) {
      if (errors) setStatus(errors === 1 ? "1 problem to fix" : `${errors} problems to fix`, "bad");
      else setStatus("Ready", "good");
    }
  }

  function translate(text, name) {
    syncFiles();
    return JSON.parse(bridge.translate(text, name));
  }
  const programName = () => (currentFile() ? currentFile().name.replace(/\.gubl$/, "") : "program");

  function showJavaScript() {
    if (!bridge) return;
    const result = translate(source.value, programName());
    $("javascript").textContent = result.ok ? result.code : "// " + result.error;
  }

  // ----- tabs ------------------------------------------------------------------------------------------
  function openTab(name) {
    for (const tab of document.querySelectorAll(".tab")) {
      const chosen = tab.dataset.tab === name;
      tab.setAttribute("aria-selected", String(chosen));
      $("panel-" + tab.dataset.tab).hidden = !chosen;
    }
    if (name === "javascript") showJavaScript();
    moveTabIndicator();
    applySplit();
  }
  function moveTabIndicator() {
    const tab = document.querySelector('.tab[aria-selected="true"]');
    const line = $("tab-indicator");
    if (!tab || !line) return;
    line.style.width = tab.offsetWidth + "px";
    line.style.transform = `translateX(${tab.offsetLeft}px)`;
  }
  for (const tab of document.querySelectorAll(".tab")) tab.addEventListener("click", () => openTab(tab.dataset.tab));
  $("clear").addEventListener("click", () => { output.textContent = ""; });

  // ----- the reference ---------------------------------------------------------------------------------
  function loadReference() {
    try {
      reference = JSON.parse(bridge.reference());
    } catch (_) {
      reference = null;
      return;
    }
    for (const command of reference.commands) commandsByName.set(command.name, command);
    for (const fn of reference.functions) functionsByName.set(fn.name, fn);
    for (const [name, value] of Object.entries(reference.colors || {})) colorNames.set(name, value);
    if (reference.words) {
      OPENERS = new Set(reference.words.openers);
      MIDDLES = new Set(reference.words.middles);
      WORDS = new Set([...WORDS, ...reference.words.keywords]);
    }
    renderReference();
  }

  function insertExample(example) {
    const index = source.selectionStart;
    const start = lineStart(index), end = lineEnd(index);
    const line = source.value.slice(start, end);
    if (!line.trim()) replaceRange(start, end, leading(line) + example);
    else replaceRange(end, end, "\n" + leading(line) + example);
    play("click");
  }

  function renderReference(flashName) {
    const box = $("reference");
    if (!reference) return;
    const query = $("ref-filter").value.trim().toLowerCase();
    const matches = (...texts) => !query || texts.some((text) => String(text).toLowerCase().includes(query));
    box.textContent = "";
    const groups = new Map();
    for (const command of reference.commands) {
      if (!matches(command.name, command.summary, command.category)) continue;
      if (!groups.has(command.category)) groups.set(command.category, []);
      groups.get(command.category).push(command);
    }
    const order = [...groups.keys()].sort((a, b) => (CATEGORY_ORDER.indexOf(a) + 1 || 99) - (CATEGORY_ORDER.indexOf(b) + 1 || 99));
    let found = 0, flashed = null;
    const entry = (name, usage, summary, extra, kind) => {
      const row = h("div", { class: "entry" + (kind ? " " + kind : ""), "data-name": name },
        h("code", { text: usage }), " ", h("span", { class: "about", text: summary }), extra);
      if (name === flashName) flashed = row;
      found++;
      return row;
    };
    for (const category of order) {
      box.append(h("h3", { text: category }));
      for (const command of groups.get(category)) {
        const example = command.example ? h("div", { class: "example" }, h("code", { text: command.example }),
          h("button", { text: "insert", title: "Put this example in your program", onclick: () => insertExample(command.example) })) : null;
        box.append(entry(command.name, command.usage, command.summary, example));
      }
    }
    const fns = reference.functions.filter((fn) => matches(fn.name, fn.summary));
    if (fns.length) {
      box.append(h("h3", { text: "functions for {expressions}" }));
      for (const fn of fns) box.append(entry(fn.name, fn.usage, fn.summary, null, "fn"));
    }
    const colours = Object.entries(reference.colors || {}).filter(([name]) => matches(name, "colour color"));
    if (colours.length) {
      box.append(h("h3", { text: "colour names" }));
      const row = h("div", { class: "entry swatch-row" });
      for (const [name, value] of colours) {
        const chip = h("span", { class: "chip", title: toHex(value) }, h("i", {}), name);
        chip.firstChild.style.background = toHex(value);
        row.append(chip);
      }
      box.append(row);
      found++;
    }
    if (!found) box.append(h("p", { class: "empty", text: `Nothing matches “${query}”.` }));
    if (flashed) {
      flashed.scrollIntoView({ block: "center" });
      flashed.classList.add("flash");
    }
  }
  $("ref-filter").addEventListener("input", () => renderReference());

  function helpForWord() {
    const word = wordAtCaret();
    openTab("reference");
    const known = commandsByName.has(word) || functionsByName.has(word);
    $("ref-filter").value = known ? word : "";
    renderReference(known ? word : null);
    if (!known) $("ref-filter").focus();
  }

  // ----- running ---------------------------------------------------------------------------------------
  // saved games (gublan's save and load) live in this page's storage, so a sandboxed program can still keep them
  function saves() {
    try { return JSON.parse(storage.get(SAVES_KEY) || "{}"); } catch (_) { return {}; }
  }

  // gublan studio's game window and popup look (settings > game window and popups). popups always get the
  // studio's look, so they match the preview in settings; the window keeps the web runtime's own size unless
  // a size was picked.
  function gameStyle() {
    const style = {};
    for (const [key, value] of Object.entries(manifest.game?.defaults || {})) if (key.startsWith("dialog_")) style[key] = value;
    Object.assign(style, settings.game || {});
    return Object.keys(style).length ? style : null;
  }

  // runs inside the sandboxed frame before the runtime: sends prints, errors and saves back to this page
  function frameBoot(saved, runtime, code, style) {
    const send = (message) => parent.postMessage(Object.assign({ gublan: true }, message), "*");
    const data = saved;
    const store = {
      getItem: (key) => (Object.prototype.hasOwnProperty.call(data, key) ? data[key] : null),
      setItem: (key, value) => { data[key] = String(value); send({ type: "save", key, value: String(value) }); },
      removeItem: (key) => { delete data[key]; send({ type: "save", key, value: null }); },
      clear: () => {},
      key: (i) => Object.keys(data)[i] ?? null,
      get length() { return Object.keys(data).length; },
    };
    try { Object.defineProperty(window, "localStorage", { value: store, configurable: true }); } catch (_) { /* keep the real one */ }
    if (style) window.GUBLAN_STYLE = style;
    const show = (type) => (...parts) => send({ type, text: parts.map(String).join(" ") });
    console.log = console.info = console.warn = show("print");
    console.error = show("error");
    addEventListener("error", (event) => send({ type: "error", text: "error: " + event.message }));
    addEventListener("unhandledrejection", (event) => {
      const reason = event.reason;
      send({ type: "error", text: "error: " + (reason && reason.message ? reason.message : String(reason)) });
    });
    addEventListener("message", (event) => {
      if (!event.data || event.data.gublanAsk !== "picture") return;
      const canvas = document.querySelector("canvas");
      let picture = null;
      try { picture = canvas ? canvas.toDataURL("image/png") : null; } catch (_) { picture = null; }
      send({ type: "picture", data: picture });
    });
    new MutationObserver(() => { if (document.querySelector("canvas")) send({ type: "window" }); })
      .observe(document.body, { childList: true, subtree: true });
    const add = (text) => {
      const script = document.createElement("script");
      script.textContent = text;
      document.body.append(script);
    };
    add(runtime);
    const start = G.start;
    G.start = (main, name) => start(async () => {
      try { await main(); } finally { send({ type: "done" }); }
    }, name);
    add(code);
  }

  function frameDocument(code, style) {
    // "<" is escaped so the code can never close the <script> it sits in
    const json = (value) => JSON.stringify(value).replace(/</g, String.fromCharCode(92) + "u003c");
    const boot = `(${frameBoot.toString()})(${json(saves())}, ${json(runtimeSource)}, ${json(code)}, ${json(style)});`;
    const backdrop = getComputedStyle(stage).backgroundColor;
    return `<!doctype html><html><head><meta charset="utf-8"><meta name="color-scheme" content="light dark"><style>
html, body { margin: 0; height: 100%; background: ${backdrop}; overflow: hidden; }
#gublan-stage { display: flex; align-items: center; justify-content: center; height: 100%; padding: 12px; box-sizing: border-box; }
canvas { max-width: 100%; max-height: 100%; outline: none; box-shadow: 0 4px 24px rgba(0,0,0,.35); }
</style></head><body><div id="gublan-stage"></div><script>${boot}</script></body></html>`;
  }

  function showStageNote(text) {
    stageNote.hidden = false;
    stageNote.innerHTML = `<span>${text}</span>`;
  }
  const IDLE_NOTE = "Press <kbd>Run</kbd> to start the program. Windows and games show up here.";

  function stop(quiet) {
    const wasRunning = Boolean(frame);
    if (frame) {
      frame.remove();
      frame = null;
      if (!quiet) {
        say("stopped", "note");
        play("stop");
      }
    }
    document.body.classList.remove("running");
    stopButton.disabled = true;
    showStageNote(IDLE_NOTE);
    if (wasRunning || !quiet) showProblems();
  }

  function run(demo) {
    if (!bridge) return;
    stop(true);
    let text = source.value, name = programName();
    if (demo === true) {
      text = manifest.game?.demo || "popup hello\n";
      name = "game window preview";
    } else check();
    const result = translate(text, name);
    openTab("output");
    if (output.textContent) say("");
    if (!result.ok) {
      say(result.error, "error");
      setStatus("Fix the problems first", "bad");
      play("error");
      const first = problems.find((p) => p.line && (p.severity || "error") === "error");
      if (first) {
        openTab("problems");
        goToLine(first.line, "error");
      }
      return;
    }
    if (demo !== true) $("javascript").textContent = result.code;
    for (const note of result.notes) say("note: " + note, "note");

    frameName = name;
    frameFailed = false;
    frame = document.createElement("iframe");
    frame.title = "Your program";
    // scripts, alerts and prompts only: no access to this page, its storage or its cookies
    frame.setAttribute("sandbox", "allow-scripts allow-modals");
    frame.srcdoc = frameDocument(result.code, gameStyle());
    showStageNote("Running…");
    stage.append(frame);
    frame.addEventListener("load", () => frame && frame.focus());
    stopButton.disabled = false;
    document.body.classList.add("running");
    setStatus(demo === true ? "Showing the game window and popups" : "Running", "busy");
    play("run");
  }

  window.addEventListener("message", (event) => {
    if (!frame || event.source !== frame.contentWindow || !event.data || !event.data.gublan) return;
    const message = event.data;
    if (message.type === "print") say(message.text);
    else if (message.type === "error") {
      say(message.text, "error");
      setStatus("Stopped with an error", "bad");
      if (!frameFailed) play("error");
      frameFailed = true;
      statusText.classList.add("bad");
    } else if (message.type === "window") {
      stageNote.hidden = true;
      frame.focus();
    } else if (message.type === "save") {
      const all = saves();
      if (message.value === null) delete all[message.key];
      else all[message.key] = message.value;
      storage.set(SAVES_KEY, JSON.stringify(all));
    } else if (message.type === "picture") {
      if (!message.data) {
        toast("This program has no window to take a picture of", "bad");
        return;
      }
      download(frameName + ".png", message.data);
      play("save");
      toast("Saved a picture of the game");
    } else if (message.type === "done") {
      document.body.classList.remove("running");
      if (!frameFailed) {
        setStatus("Finished", "good");
        play("done");
      }
      stopButton.disabled = true;
      if (!stageNote.hidden) showStageNote("This program has no window. What it printed is below.");
    }
  });

  function screenshot() {
    if (!frame) {
      toast("Run the program first, then take a picture", "bad");
      return;
    }
    frame.contentWindow.postMessage({ gublanAsk: "picture" }, "*");
  }

  function fullscreen() {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (stage.requestFullscreen) stage.requestFullscreen().then(() => frame && frame.focus()).catch(() => toast("Full screen isn't allowed here", "bad"));
  }

  runButton.addEventListener("click", () => run());
  stopButton.addEventListener("click", () => stop());
  $("restart").addEventListener("click", () => run(frameName === "game window preview" ? true : undefined));
  $("screenshot").addEventListener("click", screenshot);
  $("fullscreen").addEventListener("click", fullscreen);
  stage.addEventListener("click", () => frame && frame.focus());

  // a single web page with the runtime and program inside, that works anywhere
  function exportPage() {
    if (!bridge) return;
    const result = translate(source.value, programName());
    if (!result.ok) {
      toast("Fix the problems first", "bad");
      play("error");
      return;
    }
    const safe = (text) => text.replace(/<\/(script)/gi, "<\\/$1").replace(/<!--/g, "<\\!--");
    const style = gameStyle();
    const title = escapeHtml(programName());
    const page = `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title}</title>
<style>
  body { margin: 0; background: #101010; color: #e5e5e5; font: 15px/1.5 Consolas, monospace; }
  #gublan-stage { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 16px; }
  canvas { max-width: 100%; outline: none; }
  #gublan-log { white-space: pre-wrap; margin: 0; max-width: 100%; }
</style>
</head>
<body>
<div id="gublan-stage"><pre id="gublan-log"></pre></div>
${style ? `<script>globalThis.GUBLAN_STYLE = ${JSON.stringify(style).replace(/</g, "\\u003c")};</script>\n` : ""}<script>
${safe(runtimeSource)}
</script>
<script>
${safe(result.code)}
</script>
</body>
</html>
`;
    download(programName() + ".html", page, "text/html");
    play("save");
    toast("Saved a web page you can open anywhere");
  }

  // ----- sharing ---------------------------------------------------------------------------------------
  function toBase64(bytes) {
    let binary = "";
    for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  const fromBase64 = (text) => Uint8Array.from(atob(text.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));

  // one file: z= (squeezed) or t=. a whole project: p= (squeezed) or q=.
  async function pack(text, many) {
    const bytes = new TextEncoder().encode(text);
    if (!window.CompressionStream) return (many ? "q=" : "t=") + toBase64(bytes);
    const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream("deflate-raw"));
    return (many ? "p=" : "z=") + toBase64(new Uint8Array(await new Response(stream).arrayBuffer()));
  }

  async function unpack(hash) {
    const match = /^#([ztpq])=([\w-]+)$/.exec(hash);
    if (!match) return null;
    const bytes = fromBase64(match[2]);
    let text;
    if (match[1] === "t" || match[1] === "q") text = new TextDecoder().decode(bytes);
    else {
      const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
      text = new TextDecoder().decode(await new Response(stream).arrayBuffer());
    }
    if (match[1] === "z" || match[1] === "t") return { files: [{ name: "shared.gubl", text }], current: "shared.gubl" };
    const data = JSON.parse(text);
    const files = (data.files || []).filter((f) => f && typeof f.name === "string" && typeof f.text === "string")
      .map((f) => ({ name: cleanName(f.name), text: f.text }));
    if (!files.length) return null;
    return { files, current: cleanName(data.current || files[0].name) };
  }

  async function share() {
    const many = project.files.length > 1;
    const body = many ? JSON.stringify({ files: project.files.map(({ name, text }) => ({ name, text })), current: project.current }) : source.value;
    const link = location.href.split("#")[0] + "#" + await pack(body, many);
    history.replaceState(null, "", link);
    play("notify");
    try {
      await navigator.clipboard.writeText(link);
      toast(many ? `Link copied, with all ${project.files.length} files` : "Link copied");
    } catch (_) {
      window.prompt("Copy this link:", link);
    }
  }
  $("share").addEventListener("click", share);

  // a link's program joins the project without losing anything already there
  function takeShared(shared) {
    const lone = project.files.length === 1 && (project.files[0].pristine || !project.files[0].text.trim());
    const same = (file) => project.files.find((f) => f.text === file.text);
    if (shared.files.every(same)) {
      const pick = shared.files.find((f) => f.name === shared.current) || shared.files[0];
      selectFile(same(pick).name, true);
      return;
    }
    if (lone) project.files = [];
    else if (shared.files.length > 1 && window.confirm(`This link has ${shared.files.length} files. ` +
      "Replace your files with them? (Cancel puts them next to yours.)")) project.files = [];
    let chosen = null;
    for (const file of shared.files) {
      const existing = same(file);
      const added = existing || { name: uniqueName(file.name), text: file.text, pristine: false };
      if (!existing) project.files.push(added);
      if (file.name === shared.current) chosen = added;
    }
    selectFile((chosen || project.files[project.files.length - 1]).name, true);
    saveProject(true);
  }

  // ----- examples --------------------------------------------------------------------------------------
  async function fetchText(path) {
    const response = await fetch(path);
    if (!response.ok) throw new Error(`${path}: ${response.status} ${response.statusText}`);
    return response.text();
  }

  async function openExample(example) {
    try {
      const text = await fetchText(example.file);
      const name = example.file.split("/").pop();
      const same = project.files.find((file) => file.text === text);
      const current = currentFile();
      if (same) selectFile(same.name, true);
      else if (current && (current.pristine || !current.text.trim())) {
        views.delete(current.name);
        current.name = uniqueName(name, current);
        current.text = text;
        current.pristine = true;
        project.current = current.name;
        selectFile(current.name, true);
      } else addFile(name, text, true);
      saveProject(true);
      play("open");
      if (!example.web) say(`note: ${example.title} uses 3d, which only works in gublan studio`, "note");
    } catch (error) {
      say("couldn't open that example: " + error.message, "error");
      play("error");
    }
  }
  examplesBox.addEventListener("change", () => {
    const chosen = manifest.examples.find((e) => e.file === examplesBox.value);
    examplesBox.value = "";
    if (chosen) openExample(chosen);
  });

  // ----- splitters -------------------------------------------------------------------------------------
  const wide = () => matchMedia("(min-width: 821px)").matches;
  function applySplit() {
    const panels = document.querySelectorAll(".panel");
    if (!wide()) {
      layout.style.gridTemplateColumns = "";
      stage.style.flex = "";
      panels.forEach((panel) => { panel.style.flex = ""; });
      return;
    }
    const split = clamp(Number(settings.split) || 0.5, 0.2, 0.8);
    const splitY = clamp(Number(settings.splitY) || 0.6, 0.12, 0.92);
    layout.style.gridTemplateColumns = `minmax(0, ${split}fr) 5px minmax(0, ${1 - split}fr)`;
    stage.style.flex = `${splitY} 1 0`;
    panels.forEach((panel) => { panel.style.flex = `${1 - splitY} 1 0`; });
  }

  function splitter(element, key, vertical) {
    const place = (event) => {
      if (vertical) {
        const box = layout.getBoundingClientRect();
        settings[key] = clamp((event.clientX - box.left) / box.width, 0.2, 0.8);
      } else {
        const top = stage.getBoundingClientRect().top;
        const panel = document.querySelector(".panel:not([hidden])");
        const room = stage.offsetHeight + (panel ? panel.offsetHeight : 0);
        settings[key] = clamp((event.clientY - top) / room, 0.12, 0.92);
      }
      applySplit();
    };
    element.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      element.setPointerCapture(event.pointerId);
      element.classList.add("dragging");
      document.body.classList.add("resizing");
      document.body.style.cursor = vertical ? "col-resize" : "row-resize";
      element.addEventListener("pointermove", place);
      const done = () => {
        element.removeEventListener("pointermove", place);
        element.classList.remove("dragging");
        document.body.classList.remove("resizing");
        document.body.style.cursor = "";
        saveSettings();
        moveTabIndicator();
        if (completion) placeCompletion();
      };
      element.addEventListener("pointerup", done, { once: true });
      element.addEventListener("pointercancel", done, { once: true });
    });
    element.addEventListener("keydown", (event) => {
      const step = { ArrowLeft: -0.03, ArrowUp: -0.03, ArrowRight: 0.03, ArrowDown: 0.03 }[event.key];
      if (!step) return;
      event.preventDefault();
      const [low, high] = vertical ? [0.2, 0.8] : [0.12, 0.92];
      settings[key] = clamp((Number(settings[key]) || DEFAULTS[key]) + step, low, high);
      applySplit();
      saveSettings();
    });
    element.addEventListener("dblclick", () => {
      settings[key] = DEFAULTS[key];
      applySplit();
      saveSettings();
    });
  }
  splitter($("split-x"), "split", true);
  splitter($("split-y"), "splitY", false);
  addEventListener("resize", () => {
    applySplit();
    moveTabIndicator();
    if (completion) placeCompletion();
  });

  // ----- settings drawer -------------------------------------------------------------------------------
  const SHORTCUTS = [
    ["Ctrl+Enter", "run the program"], ["Esc", "stop the program, or close what's open"],
    ["Ctrl+S", "save now (it saves by itself too)"], ["Ctrl+Shift+S", "download this file"],
    ["Ctrl+O", "open .gubl files"], ["Ctrl+Alt+N", "new file"], ["Ctrl+Shift+P, Ctrl+K", "find any action"],
    ["Ctrl+F, Ctrl+H", "find, replace"], ["Ctrl+G", "go to a line"], ["Ctrl+Space", "suggestions"],
    ["F1", "help for the word under the cursor"], ["Ctrl+/", "comment or uncomment lines"],
    ["Ctrl+D", "copy the line below"], ["Alt+↑, Alt+↓", "move lines up or down"], ["Ctrl+Shift+K", "delete the line"],
    ["Tab, Shift+Tab", "indent, outdent"], ["Shift+Alt+F", "tidy up the indentation"], ["Ctrl+,", "settings"],
  ];
  const VOLUMES = [[15, "whisper"], [30, "quiet"], [45, "normal"], [65, "loud"], [85, "louder"]];

  function choiceRow(label, key, options, about, onPick) {
    const row = h("div", { class: "choices", role: "group", "aria-label": label });
    for (const [value, text] of options) {
      const button = h("button", { type: "button", text, "aria-pressed": String(settings[key] === value) });
      button.addEventListener("click", () => {
        for (const other of row.children) other.setAttribute("aria-pressed", "false");
        button.setAttribute("aria-pressed", "true");
        if (onPick) onPick(value);
        else setSetting(key, value);
        if (aboutLine && about) aboutLine.textContent = about[value] || "";
        play("click");
      });
      row.append(button);
    }
    const aboutLine = about ? h("p", { class: "about", text: about[settings[key]] || "" }) : null;
    return [h("div", { class: "setting" }, h("span", { text: label }), row), aboutLine];
  }

  function checkRow(label, key, onChange) {
    const box = h("input", { type: "checkbox" });
    box.checked = Boolean(settings[key]);
    box.addEventListener("change", () => {
      if (onChange) onChange(box.checked);
      else setSetting(key, box.checked);
      play("click");
    });
    return h("label", { class: "check" }, box, h("span", { text: label }));
  }

  function selectRow(label, key, options) {
    const select = h("select", { "aria-label": label });
    for (const [value, text, title] of options) {
      const option = h("option", { value, text, title });
      if (String(settings[key]) === String(value)) option.selected = true;
      select.append(option);
    }
    select.addEventListener("change", () => setSetting(key, select.value));
    return h("label", { class: "setting" }, h("span", { text: label }), select);
  }

  function rangeRow(label, key, min, max, step, show, onChange) {
    const value = h("output", { text: show(settings[key]) });
    const range = h("input", { type: "range", min, max, step, value: settings[key], "aria-label": label });
    range.addEventListener("input", () => {
      value.textContent = show(Number(range.value));
      if (onChange) onChange(Number(range.value));
      else setSetting(key, Number(range.value));
    });
    return h("label", { class: "setting" }, h("span", { text: label }), h("div", { class: "color-row" }, range, value));
  }

  function accentRow() {
    const row = h("div", { class: "swatches", role: "group", "aria-label": "Accent colour" });
    const own = h("input", { type: "color", value: isHex(settings.accent) ? toHex(rgb(settings.accent)) : "#647f4a",
      title: "Pick any colour", "aria-label": "Pick any accent colour" });
    const mark = () => {
      for (const swatch of row.querySelectorAll(".swatch")) {
        swatch.setAttribute("aria-pressed", String((swatch.dataset.color || "") === (settings.accent || "")));
      }
    };
    const accents = manifest.accents && manifest.accents.length ? manifest.accents : [{ name: "theme", color: "" }];
    for (const { name, color } of accents) {
      const swatch = h("button", { type: "button", class: "swatch" + (color ? "" : " theme-own"), title: name === "theme" ? "the theme's own colour" : name,
        "aria-label": name, "data-color": color });
      if (color) swatch.style.background = color;
      swatch.addEventListener("click", () => { setSetting("accent", color); mark(); play("click"); });
      row.append(swatch);
    }
    own.addEventListener("input", () => { settings.accent = own.value; applyTheme(); mark(); });
    own.addEventListener("change", () => { setSetting("accent", own.value); });
    row.append(own);
    mark();
    return h("div", { class: "setting" }, h("span", { text: "accent colour" }), row);
  }

  // ----- settings: the game window and popups (the same options as gublan studio's tools menu) -----------
  function gameValue(key) {
    const chosen = settings.game || {};
    return key in chosen ? chosen[key] : (manifest.game?.defaults || {})[key];
  }
  function setGame(key, value) {
    const defaults = manifest.game?.defaults || {};
    const game = Object.assign({}, settings.game);
    const same = key in defaults && JSON.stringify(defaults[key]) === JSON.stringify(value);
    const windowKey = !key.startsWith("dialog_") && key !== "width" && key !== "height";
    if (value === undefined || value === "" || (same && windowKey)) delete game[key];
    else game[key] = value;
    settings.game = game;
    saveSettings();
    paintGamePreview();
  }

  let gamePreview = null;
  function paintGamePreview(replay) {
    if (!gamePreview) return;
    const v = gameValue;
    const width = Number(v("width")) || 540, height = Number(v("height")) || 420;
    const preview = gamePreview;
    preview.style.aspectRatio = `${width} / ${height}`;
    preview.style.background = gublanHex(v("background"), "#141414");
    preview.style.setProperty("--gp-width", width);
    preview.style.alignItems = { top: "flex-start", bottom: "flex-end" }[v("dialog_position")] || "center";
    const shade = preview.querySelector(".gp-shade");
    shade.style.opacity = String(clamp(Number(v("dialog_shade")) || 0, 0, 100) / 100);
    const box = preview.querySelector(".gp-box");
    const edge = clamp(Number(v("dialog_border_width")) || 0, 0, 12);
    box.style.background = gublanHex(v("dialog_background"), "#262626");
    box.style.color = gublanHex(v("dialog_text"), "#e5e5e5");
    box.style.border = `calc(${edge} / ${width} * 100cqw) solid ${gublanHex(v("dialog_border"), "#94b66c")}`;
    box.style.borderTopColor = gublanHex(v("dialog_accent"), "#94b66c");
    box.style.width = `${clamp((Number(v("dialog_width")) || 450) / width * 100, 20, 96)}%`;
    box.style.fontSize = `calc(${Number(v("dialog_text_size")) || 26} / ${width} * 100cqw)`;
    const field = preview.querySelector(".gp-field");
    field.style.background = gublanHex(v("dialog_field"), "#171717");
    field.querySelector("i").style.background = gublanHex(v("dialog_accent"), "#94b66c");
    const hint = preview.querySelector(".gp-hint");
    hint.hidden = !v("dialog_hints");
    hint.style.color = gublanHex(v("dialog_hint"), "#aaaaaa");
    preview.querySelector(".gp-fps").hidden = !v("show_fps");
    preview.querySelector(".gp-title").textContent = v("title") || "your program";
    if (replay) {
      box.className = "gp-box";
      void box.offsetWidth;
      box.classList.add("gp-" + (v("dialog_animation") || "pop"));
    }
  }

  function colorField(label, key) {
    const input = h("input", { type: "color", value: gublanHex(gameValue(key)), "aria-label": label });
    const value = h("code", { text: String(gameValue(key)) });
    input.addEventListener("input", () => { value.textContent = input.value; setGame(key, input.value); });
    input.dataset.key = key;
    return h("label", { class: "color-row" }, input, h("span", { text: label }), value);
  }

  function gameSection() {
    const game = manifest.game || {};
    if (!game.defaults) return null;
    gamePreview = h("div", { class: "game-preview", "aria-hidden": "true" },
      h("div", { class: "gp-title" }), h("div", { class: "gp-fps", text: "fps 60" }), h("div", { class: "gp-shade" }),
      h("div", { class: "gp-box" }, h("div", { text: "this is how questions look. what is your name?" }),
        h("div", { class: "gp-field" }, "gub", h("i", {})), h("div", { class: "gp-hint", text: "enter to accept" })));
    gamePreview.addEventListener("click", () => paintGamePreview(true));
    const looks = Object.entries(game.looks || {});
    const pickLook = (name) => {
      const look = name === "playground" ? playgroundLook() : game.looks[name] || {};
      const keep = Object.fromEntries(Object.entries(settings.game || {}).filter(([key]) => !key.startsWith("dialog_")));
      const fresh = {};
      for (const [key, value] of Object.entries(game.defaults)) if (key.startsWith("dialog_")) fresh[key] = value;
      for (const key of ["dialog_animation", "dialog_position", "dialog_hints", "dialog_sound", "dialog_width", "dialog_text_size"]) {
        if (settings.game && key in settings.game) fresh[key] = settings.game[key];
      }
      settings.game = Object.assign(keep, fresh, look);
      saveSettings();
      buildSettings("settings-game");
      paintGamePreview(true);
    };
    const sizes = [["", "default"]].concat((game.sizes || []).map(([w, hh]) => [`${w}x${hh}`, `${w} × ${hh}`]));
    const currentSize = "width" in (settings.game || {}) ? `${settings.game.width}x${settings.game.height}` : "";
    const sizeRow = h("div", { class: "choices", role: "group", "aria-label": "window size" });
    for (const [value, text] of sizes) {
      const button = h("button", { type: "button", text, "aria-pressed": String(value === currentSize) });
      button.addEventListener("click", () => {
        for (const other of sizeRow.children) other.setAttribute("aria-pressed", "false");
        button.setAttribute("aria-pressed", "true");
        if (value) {
          const [w, hh] = value.split("x").map(Number);
          setGame("width", w);
          setGame("height", hh);
        } else {
          const rest = Object.assign({}, settings.game);
          delete rest.width;
          delete rest.height;
          settings.game = rest;
          saveSettings();
        }
        paintGamePreview();
        play("click");
      });
      sizeRow.append(button);
    }
    const gameChoice = (label, key, options) => {
      const row = h("div", { class: "choices", role: "group", "aria-label": label });
      for (const [value, text] of options) {
        const button = h("button", { type: "button", text, "aria-pressed": String(gameValue(key) === value) });
        button.addEventListener("click", () => {
          for (const other of row.children) other.setAttribute("aria-pressed", "false");
          button.setAttribute("aria-pressed", "true");
          setGame(key, value);
          paintGamePreview(true);
          play("click");
        });
        row.append(button);
      }
      return h("div", { class: "setting" }, h("span", { text: label }), row);
    };
    const gameCheck = (label, key) => {
      const box = h("input", { type: "checkbox" });
      box.checked = Boolean(gameValue(key));
      box.addEventListener("change", () => { setGame(key, box.checked); play("click"); });
      return h("label", { class: "check" }, box, h("span", { text: label }));
    };
    const gameRange = (label, key, min, max, step, unit) => {
      const shown = h("output", { text: gameValue(key) + unit });
      const range = h("input", { type: "range", min, max, step, value: gameValue(key), "aria-label": label });
      range.addEventListener("input", () => { shown.textContent = range.value + unit; setGame(key, Number(range.value)); });
      return h("label", { class: "setting" }, h("span", { text: label }), h("div", { class: "color-row" }, range, shown));
    };
    const titleBox = h("input", { type: "text", value: gameValue("title") || "", placeholder: "the program's name", "aria-label": "window title" });
    titleBox.addEventListener("input", () => setGame("title", titleBox.value.trim()));
    titleBox.className = "text-field";
    return h("section", { id: "settings-game" },
      h("h3", { text: "game window and popups" }),
      h("p", { class: "about", text: "how game windows, popups and questions look when you run a program here. a program's own window, background and fps lines still win." }),
      gamePreview,
      h("div", { class: "setting" }, h("span", { text: "popup look" }), h("div", { class: "choices" },
        [["playground", "match this page"]].concat(looks.map(([name]) => [name, name])).map(([name, text]) =>
          h("button", { type: "button", text, onclick: () => { pickLook(name); play("click"); } })))),
      h("div", { class: "setting" }, h("span", { text: "window size" }), sizeRow),
      h("label", { class: "setting" }, h("span", { text: "window title" }), titleBox),
      gameChoice("frames a second", "fps", [[30, "30"], [60, "60"], [120, "120"]]),
      gameCheck("show the frame rate in the corner", "show_fps"),
      gameChoice("popups open with", "dialog_animation", (game.animations || ["pop", "fade", "slide", "none"]).map((a) => [a, a])),
      gameChoice("popups sit at the", "dialog_position", (game.positions || ["center", "top", "bottom"]).map((p) => [p, p])),
      gameRange("popup width", "dialog_width", 160, 1000, 10, "px"),
      gameRange("popup text size", "dialog_text_size", 10, 48, 1, "px"),
      gameRange("popup border", "dialog_border_width", 0, 12, 1, "px"),
      gameRange("dim the game behind", "dialog_shade", 0, 100, 5, "%"),
      h("div", { class: "color-grid" },
        colorField("window", "background"), colorField("drawing", "color"),
        colorField("popup", "dialog_background"), colorField("words", "dialog_text"),
        colorField("accent", "dialog_accent"), colorField("border", "dialog_border"),
        colorField("hints", "dialog_hint"), colorField("answer box", "dialog_field")),
      gameCheck("show how to answer under popups", "dialog_hints"),
      gameCheck("a soft blip when a popup opens", "dialog_sound"),
      h("div", { class: "row" },
        h("button", { type: "button", class: "primary", text: "try it in a game window", onclick: () => { closeSettings(true); run(true); } }),
        h("button", { type: "button", text: "back to the default look", onclick: () => {
          settings.game = {};
          saveSettings();
          buildSettings("settings-game");
          paintGamePreview(true);
          play("click");
        } })));
  }

  // popups in this page's own colours
  function playgroundLook() {
    const css = getComputedStyle(document.documentElement);
    const take = (name, fallback) => {
      const value = css.getPropertyValue(name).trim();
      return isHex(value) ? toHex(rgb(value)) : fallback;
    };
    return {
      dialog_background: take("--panel-alt", "#262626"), dialog_text: take("--text", "#e5e5e5"),
      dialog_hint: take("--muted", "#aaaaaa"), dialog_accent: take("--accent-light", "#94b66c"),
      dialog_border: take("--border", "#2c2c2c"), dialog_field: take("--editor-bg", "#171717"),
      dialog_border_width: 1, dialog_shade: 55,
    };
  }

  function buildSettings(scrollTo) {
    const body = $("settings-body");
    const keepScroll = body.scrollTop;
    body.textContent = "";
    gamePreview = null;
    const themes = Object.entries(manifest.themes || {});
    const sections = [
      h("section", {},
        h("h3", { text: "look" }),
        selectRow("theme", "theme", [["auto", "match my system"]].concat(themes.map(([name, info]) => [name, name, info.about]))),
        accentRow(),
        checkRow("animations", "motion"),
        ...choiceRow("animation speed", "speed", [["slow", "slow"], ["normal", "normal"], ["fast", "fast"]])),
      h("section", {},
        h("h3", { text: "editor" }),
        selectRow("font", "font", FONTS),
        rangeRow("text size", "fontSize", 11, 24, 1, (v) => v + "px"),
        ...choiceRow("line spacing", "spacing", [["tight", "tight"], ["normal", "normal"], ["roomy", "roomy"], ["airy", "airy"]]),
        checkRow("suggest commands and names as I type", "suggestions"),
        checkRow("show help for the line I'm on", "hints"),
        checkRow("close brackets and quotes for me", "autoPairs"),
        checkRow("add end after if, loop, function…", "autoEnd"),
        checkRow("highlight the line I'm on", "lineHighlight"),
        checkRow("rainbow brackets", "rainbow")),
      h("section", {},
        h("h3", { text: "cursor and typing" }),
        checkRow("smooth cursor", "smoothCaret"),
        ...choiceRow("cursor shape", "caretStyle", [["line", "line"], ["block", "block"], ["underline", "underline"]]),
        ...choiceRow("cursor width", "caretWidth", [[1, "thin"], [2, "normal"], [3, "thick"], [4, "chunky"]]),
        ...choiceRow("blinking", "caretBlink", [["fade", "fade"], ["blink", "blink"], ["solid", "solid"]]),
        ...choiceRow("movement", "caretMotion", [["glide", "glide"], ["jump", "jump"]]),
        ...choiceRow("new letters", "typing", [["fade", "fade in"], ["ink", "ink"], ["glow", "glow"], ["off", "off"]], {
          fade: "letters fade in as you type them.", ink: "letters arrive bright and settle into their colour.",
          glow: "a soft glow behind what you just typed.", off: "letters just appear.",
        })),
      h("section", {},
        h("h3", { text: "sounds" }),
        checkRow("soft sounds for running, errors, saving and more", "sounds", (on) => {
          setSetting("sounds", on);
          if (on) play("notify", true);
        }),
        ...choiceRow("sound pack", "soundPack", [["soft", "soft"], ["glass", "glass"], ["wood", "wood"], ["retro", "retro"]], PACK_ABOUT,
          (value) => { setSetting("soundPack", value); play("open", true); }),
        ...choiceRow("volume", "volume", VOLUMES, null, (value) => { setSetting("volume", value); play("notify", true); }),
        checkRow("tiny clicks while typing", "typingSounds"),
        h("div", { class: "setting" }, h("span", { text: "listen" }), h("div", { class: "choices" },
          ["open", "run", "done", "save", "error", "notify"].map((event) =>
            h("button", { type: "button", text: event, onclick: () => play(event, true) }))))),
      gameSection(),
      h("section", { id: "settings-keys" },
        h("h3", { text: "keyboard shortcuts" }),
        h("ul", { class: "keys" }, SHORTCUTS.map(([keys, what]) => h("li", {},
          h("span", {}, keys.split(", ").map((combo, i) => [i ? ", " : "", ...combo.split("+").map((k, j) => [j ? "+" : "", h("kbd", { text: k })])])),
          h("span", { text: what }))))),
      h("section", {},
        h("h3", { text: "your data" }),
        h("p", { class: "about", text: "your files, settings and saved games stay in this browser. nothing is uploaded." }),
        h("div", { class: "row" },
          h("button", { type: "button", text: "forget saved games", onclick: () => {
            if (!window.confirm("Forget every saved game made with save in this browser?")) return;
            storage.remove(SAVES_KEY);
            toast("Saved games forgotten");
          } }),
          h("button", { type: "button", text: "reset settings", onclick: () => {
            settings = Object.assign({}, DEFAULTS, { game: {} });
            saveSettings();
            applySettings();
            buildSettings();
            toast("Settings are back to how they started");
          } }))),
    ];
    body.append(...sections.filter(Boolean));
    paintGamePreview(true);
    if (scrollTo && $(scrollTo)) {
      $(scrollTo).scrollIntoView({ block: "start" });
      for (const section of body.querySelectorAll("section")) section.style.animation = "none";
    } else body.scrollTop = keepScroll;
  }

  function openSettings(scrollTo) {
    closePalette(true);
    arrive(scrim);
    arrive(drawer);
    buildSettings(scrollTo);
    $("close-settings").focus();
    play("open");
  }
  function closeSettings(quiet) {
    if (drawer.hidden) return;
    leave(drawer, 220);
    leave(scrim, 200);
    if (!quiet) play("close");
    source.focus();
  }
  $("open-settings").addEventListener("click", () => openSettings());
  $("close-settings").addEventListener("click", () => closeSettings());
  scrim.addEventListener("click", () => closeSettings());
  $("show-keys").addEventListener("click", (event) => {
    event.preventDefault();
    openSettings("settings-keys");
  });

  // ----- the command palette ---------------------------------------------------------------------------
  function actions() {
    const list = [
      ["run the program", "Ctrl+Enter", () => run()],
      ["stop the program", "Esc", () => stop()],
      ["share a link to this program", "", share],
      ["new file", "Ctrl+Alt+N", newFile],
      ["open .gubl files from this computer", "Ctrl+O", () => $("open-file").click()],
      ["download this file", "Ctrl+Shift+S", () => { download(currentFile().name, source.value); play("save"); }],
      ["save as a web page (.html)", "", exportPage],
      ["rename this file", "F2", () => renameFile(currentFile())],
      ["find", "Ctrl+F", () => openFind(false)],
      ["replace", "Ctrl+H", () => openFind(true)],
      ["go to a line", "Ctrl+G", () => openPalette(":")],
      ["tidy up the indentation", "Shift+Alt+F", tidyIndentation],
      ["comment or uncomment lines", "Ctrl+/", toggleComment],
      ["take a picture of the game", "", screenshot],
      ["full screen game", "", fullscreen],
      ["show the javascript", "", () => openTab("javascript")],
      ["show the reference", "F1", () => openTab("reference")],
      ["clear the output", "", () => { output.textContent = ""; }],
      ["settings", "Ctrl+,", () => openSettings()],
      ["game window and popups", "", () => openSettings("settings-game")],
      ["try the game window and popups", "", () => run(true)],
      ["keyboard shortcuts", "", () => openSettings("settings-keys")],
      [settings.sounds ? "turn sounds off" : "turn sounds on", "", () => { setSetting("sounds", !settings.sounds); if (settings.sounds) play("notify"); }],
      [settings.motion ? "turn animations off" : "turn animations on", "", () => setSetting("motion", !settings.motion)],
      ["bigger text", "", () => setSetting("fontSize", clamp(settings.fontSize + 1, 11, 24))],
      ["smaller text", "", () => setSetting("fontSize", clamp(settings.fontSize - 1, 11, 24))],
    ].map(([title, keys, go]) => ({ kind: "action", title, keys, go }));
    list.push({ kind: "theme", title: "theme: match my system", keys: "", go: () => setSetting("theme", "auto") });
    for (const [name, info] of Object.entries(manifest.themes || {})) {
      list.push({ kind: "theme", title: "theme: " + name, keys: info.about, go: () => setSetting("theme", name) });
    }
    for (const file of project.files) list.push({ kind: "file", title: file.name, keys: "", go: () => selectFile(file.name) });
    for (const example of manifest.examples) {
      list.push({ kind: "example", title: example.title, keys: example.web ? "" : "3d, studio only", go: () => openExample(example) });
    }
    if (reference) {
      for (const command of reference.commands) {
        list.push({ kind: "command", title: command.name, keys: command.usage, go: () => { openTab("reference"); $("ref-filter").value = command.name; renderReference(command.name); } });
      }
      for (const fn of reference.functions) {
        list.push({ kind: "function", title: fn.name, keys: fn.usage, go: () => { openTab("reference"); $("ref-filter").value = fn.name; renderReference(fn.name); } });
      }
    }
    return list;
  }

  // a forgiving match: every letter of the query, in order. earlier and closer letters score higher.
  function fuzzy(text, query) {
    if (!query) return { score: 0, hits: [] };
    const lower = text.toLowerCase();
    const at = lower.indexOf(query);
    if (at !== -1) return { score: 100 - at - (text.length - query.length) * 0.1 + (at === 0 ? 50 : 0), hits: [...Array(query.length)].map((_, i) => at + i) };
    const hits = [];
    let score = 0, last = -1;
    for (const char of query) {
      const found = lower.indexOf(char, last + 1);
      if (found === -1) return null;
      score += found === last + 1 ? 6 : 1;
      hits.push(found);
      last = found;
    }
    return { score: score - text.length * 0.05, hits };
  }

  let paletteItems = [];
  let paletteIndex = 0;
  function fillPalette() {
    const query = paletteInput.value.trim().toLowerCase();
    paletteList.textContent = "";
    const jump = /^:(\d*)$/.exec(query);
    if (jump) {
      const total = source.value.split("\n").length;
      const number = Number(jump[1]);
      paletteItems = [{ kind: "line", title: number ? `go to line ${clamp(number, 1, total)}` : `type a line number (1 to ${total})`, keys: "",
        go: () => { if (number) goToLine(number); } }];
    } else {
      const order = { action: 0, file: 1, example: 2, theme: 3, command: 4, function: 5 };
      paletteItems = actions().map((item) => Object.assign(item, { match: fuzzy(item.title, query) }))
        .filter((item) => item.match && (query || item.kind === "action" || item.kind === "file"))
        .sort((a, b) => (b.match.score - a.match.score) || order[a.kind] - order[b.kind])
        .slice(0, 60);
    }
    paletteIndex = 0;
    paletteItems.forEach((item, index) => {
      const hits = new Set(item.match ? item.match.hits : []);
      const title = h("span", {}, h("span", { class: "kind", text: item.kind }));
      [...item.title].forEach((char, i) => title.append(hits.has(i) ? h("mark", { text: char }) : char));
      const row = h("li", { role: "option", class: index === 0 ? "chosen" : "", id: "palette-" + index }, title, item.keys ? h("small", { text: item.keys }) : null);
      row.addEventListener("mousedown", (event) => { event.preventDefault(); pickPalette(index); });
      row.addEventListener("mousemove", () => markPalette(index));
      paletteList.append(row);
    });
    if (!paletteItems.length) paletteList.append(h("li", { class: "empty", text: "Nothing matches." }));
  }
  function markPalette(index) {
    if (!paletteItems.length) return;
    paletteList.children[paletteIndex]?.classList.remove("chosen");
    paletteIndex = (index + paletteItems.length) % paletteItems.length;
    const row = paletteList.children[paletteIndex];
    row.classList.add("chosen");
    row.scrollIntoView({ block: "nearest" });
    paletteInput.setAttribute("aria-activedescendant", row.id);
  }
  function pickPalette(index) {
    const item = paletteItems[index];
    closePalette(true);
    if (item) {
      play("click");
      item.go();
    }
  }
  function openPalette(prefill = "") {
    closeCompletion();
    arrive(palette);
    $("more").setAttribute("aria-expanded", "true");
    paletteInput.value = prefill;
    fillPalette();
    paletteInput.focus();
    paletteInput.setSelectionRange(prefill.length, prefill.length);
  }
  function closePalette(picked) {
    if (palette.hidden) return;
    $("more").setAttribute("aria-expanded", "false");
    leave(palette, 140);
    if (!picked) source.focus();
  }
  paletteInput.addEventListener("input", fillPalette);
  paletteInput.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      markPalette(paletteIndex + (event.key === "ArrowDown" ? 1 : -1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      pickPalette(paletteIndex);
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closePalette();
    }
  });
  $("more").addEventListener("click", () => (palette.hidden ? openPalette() : closePalette()));
  document.addEventListener("mousedown", (event) => {
    if (!palette.hidden && !palette.contains(event.target) && !$("more").contains(event.target)) closePalette(true);
    if (completion && !completeBox.contains(event.target) && event.target !== source) closeCompletion();
  });

  // ----- shortcuts anywhere on the page ------------------------------------------------------------------
  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented) return;
    const key = event.key.toLowerCase();
    if (mod(event) && event.key === "Enter") {
      event.preventDefault();
      run();
    } else if ((mod(event) && event.shiftKey && key === "p") || (mod(event) && !event.shiftKey && key === "k")) {
      event.preventDefault();
      openPalette();
    } else if (mod(event) && event.key === ",") {
      event.preventDefault();
      if (drawer.hidden) openSettings();
      else closeSettings();
    } else if (mod(event) && key === "s") {
      event.preventDefault();
      if (event.shiftKey) download(currentFile().name, source.value);
      else {
        saveProject(true);
        toast("Saved in this browser");
      }
      play("save");
      const tab = fileList.querySelector('[aria-selected="true"]');
      if (tab && speed()) tab.animate([{ background: "var(--select)" }, { background: "var(--editor-bg)" }], 500 * speed());
    } else if (mod(event) && !event.shiftKey && key === "o") {
      event.preventDefault();
      $("open-file").click();
    } else if (mod(event) && event.altKey && key === "n") {
      event.preventDefault();
      newFile();
    } else if (mod(event) && !event.shiftKey && (key === "f" || key === "h")) {
      event.preventDefault();
      openFind(key === "h");
    } else if (mod(event) && !event.shiftKey && key === "g") {
      event.preventDefault();
      openPalette(":");
    } else if (event.key === "F1") {
      event.preventDefault();
      helpForWord();
    } else if (event.shiftKey && event.altKey && key === "f") {
      event.preventDefault();
      tidyIndentation();
    } else if (event.key === "Escape") {
      if (!palette.hidden) closePalette();
      else if (!drawer.hidden) closeSettings();
      else if (!findbar.hidden) closeFind();
      else if (frame) stop();
      else if (document.activeElement === source) source.blur(); // lets keyboard users tab out of the editor
    }
  });

  // ----- start up -------------------------------------------------------------------------------------
  function bootStep(name, state) {
    const step = document.querySelector(`[data-step="${name}"]`);
    if (!step) return;
    step.classList.remove("active", "done", "failed");
    if (state) step.classList.add(state);
  }
  const progressParts = { files: 0, python: 0, gublan: 0 };
  function progress(part, amount) {
    progressParts[part] = amount;
    const total = progressParts.files * 0.3 + progressParts.python * 0.55 + progressParts.gublan * 0.15;
    const percent = Math.round(clamp(total, 0, 1) * 100) + "%";
    $("boot-bar").style.width = percent;
    $("progress").firstElementChild.style.width = percent;
    if (total >= 1) setTimeout(() => $("progress").classList.add("done"), 400);
  }
  function finishBoot() {
    const boot = $("boot");
    if (!boot) return;
    boot.classList.add("gone");
    setTimeout(() => boot.remove(), 600 * (speed() || 0.01));
    showStageNote(IDLE_NOTE);
  }

  async function loadGublan() {
    if (typeof loadPyodide !== "function") throw new Error("python for the browser (pyodide) didn't download");
    bootStep("files", "active");
    bootStep("python", "active");
    const creep = setInterval(() => progress("python", progressParts.python + (0.9 - progressParts.python) * 0.04), 200);
    const python = loadPyodide().then((pyodide) => {
      clearInterval(creep);
      progress("python", 1);
      bootStep("python", "done");
      return pyodide;
    }, (error) => {
      clearInterval(creep);
      bootStep("python", "failed");
      throw error;
    });
    python.catch(() => {}); // handled below, once the files are in
    const files = ["bridge.py"].concat(manifest.python.map((name) => "gublan/" + name));
    let fetched = 0;
    const texts = await Promise.all(files.map(async (path) => {
      const text = await fetchText(path);
      progress("files", ++fetched / files.length);
      return text;
    })).catch((error) => { bootStep("files", "failed"); throw error; });
    bootStep("files", "done");
    const pyodide = await python;
    bootStep("gublan", "active");
    files.forEach((path, i) => {
      const target = "/gublan/" + path.replace(/^gublan\//, "");
      pyodide.FS.mkdirTree(target.slice(0, target.lastIndexOf("/")));
      pyodide.FS.writeFile(target, texts[i]);
    });
    pyodide.FS.mkdirTree("/gublan/project");
    pyodide.runPython("import sys; sys.path.insert(0, '/gublan')");
    runtimeSource = texts[files.indexOf("gublan/runtimes/gublan_runtime.js")];
    const loaded = pyodide.pyimport("bridge");
    progress("gublan", 1);
    bootStep("gublan", "done");
    return loaded;
  }

  async function firstProject() {
    try {
      const stored = JSON.parse(storage.get(PROJECT_KEY) || "null");
      if (stored && Array.isArray(stored.files) && stored.files.length) {
        const files = [];
        for (const file of stored.files) {
          if (file && typeof file.text === "string") files.push({ name: cleanName(file.name), text: file.text, pristine: Boolean(file.pristine) });
        }
        if (files.length) return { files, current: stored.current };
      }
    } catch (_) { /* no project yet */ }
    try {
      const draft = JSON.parse(storage.get(DRAFT_KEY) || "null");
      if (draft && typeof draft.text === "string" && draft.text.trim()) {
        return { files: [{ name: cleanName(draft.name || "program"), text: draft.text, pristine: false }] };
      }
    } catch (_) { /* no draft */ }
    const first = manifest.examples[0];
    if (first) {
      try {
        return { files: [{ name: cleanName(first.file), text: await fetchText(first.file), pristine: true }] };
      } catch (_) { /* fall through */ }
    }
    return { files: [{ name: "program.gubl", text: "print hello from gublan\n", pristine: true }] };
  }

  async function main() {
    loadSettings();
    applySettings();
    setStatus("Loading Gublan…", "busy");
    try {
      manifest = Object.assign(manifest, await (await fetch("manifest.json")).json());
    } catch (_) {
      setStatus("This page is missing its files. Build it with web/build_site.py.", "bad");
      bootStep("files", "failed");
      return;
    }
    progress("files", 0.05);
    applySettings();
    $("version").textContent = manifest.version;
    for (const example of manifest.examples) {
      examplesBox.append(h("option", { value: example.file, text: example.title + (example.web ? "" : " (3D, studio only)") }));
    }
    const stored = await firstProject();
    project.files = [];
    const seen = new Set();
    for (const file of stored.files) {
      let name = file.name;
      for (let n = 2; seen.has(name.toLowerCase()); n++) name = file.name.replace(/\.gubl$/, ` ${n}.gubl`);
      seen.add(name.toLowerCase());
      project.files.push(Object.assign(file, { name }));
    }
    project.current = stored.current && project.files.some((f) => f.name === stored.current) ? stored.current : project.files[0].name;
    selectFile(project.current, true);
    try {
      const shared = await unpack(location.hash);
      if (shared) takeShared(shared);
    } catch (_) {
      say("that link's program couldn't be read", "error");
    }
    saveProject(true);
    if (storage.get(PROJECT_KEY)) storage.remove(DRAFT_KEY);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { measure(); updateCaret(true); moveTabIndicator(); });
    try {
      bridge = await loadGublan();
    } catch (error) {
      setStatus("Couldn't load Gublan. Check your connection and reload.", "bad");
      say("loading failed: " + error.message, "error");
      for (const step of document.querySelectorAll(".boot-steps li.active")) step.classList.replace("active", "failed");
      play("error");
      return;
    }
    loadReference();
    runButton.disabled = false;
    finishBoot();
    render();
    check();
    lastHint = "";
    updateHint();
  }

  moveTabIndicator();
  main();
})();
