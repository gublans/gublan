// the gublan playground: write gublan in the browser and run it.
//
// gublan's own checker and javascript translator (gublancore.py and gublantranslate.py) run in pyodide.
// the translated program runs with gublan_runtime.js inside a sandboxed iframe, the same way a program
// exported from gublan studio as a web page runs. web/build_site.py copies all of those files next to this one.
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const source = $("source");
  const highlight = $("highlight");
  const gutter = $("gutter");
  const editor = $("editor");
  const stage = $("stage");
  const stageNote = $("stage-note");
  const output = $("output");
  const statusText = $("status");
  const runButton = $("run");
  const stopButton = $("stop");
  const examplesBox = $("examples");

  const DRAFT_KEY = "gublan-playground:draft";
  const SAVES_KEY = "gublan-playground:saves";
  const FLOW = new Set(["if", "elseif", "else", "end", "loop", "forever", "while", "until", "for", "function",
    "match", "case", "try", "catch", "test", "return", "break", "continue"]);
  const OPENERS = new Set(["if", "elseif", "else", "loop", "forever", "while", "until", "for", "function",
    "match", "case", "try", "catch", "test"]);
  const INDENT = "    ";

  let bridge = null;
  let runtimeSource = "";
  let manifest = { version: "", examples: [] };
  let programName = "program";
  let loadedText = "";
  let problems = [];
  let frame = null;
  let checkTimer = 0;
  let draftTimer = 0;

  // ----- small helpers --------------------------------------------------------------------------------------
  const storage = {
    get(key) { try { return localStorage.getItem(key); } catch (_) { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch (_) { /* private mode: not saved */ } },
  };
  const escapeHtml = (text) => text.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);

  function setStatus(text, kind = "") {
    statusText.textContent = text;
    statusText.className = "status" + (kind ? " " + kind : "");
  }

  function say(text, kind = "") {
    const line = document.createElement("span");
    if (kind) line.className = kind;
    line.textContent = text + "\n";
    output.append(line);
    const panel = $("panel-output");
    panel.scrollTop = panel.scrollHeight;
  }

  function toast(text) {
    const note = document.createElement("div");
    note.className = "toast";
    note.setAttribute("role", "status");
    note.textContent = text;
    document.body.append(note);
    setTimeout(() => note.remove(), 2200);
  }

  // ----- highlighting --------------------------------------------------------------------------------------
  function paintLine(line) {
    const trimmed = line.trimStart();
    if (trimmed.startsWith("//")) return `<span class="t-comment">${escapeHtml(line)}</span>`;
    const lead = line.slice(0, line.length - trimmed.length);
    const match = /^([A-Za-z_][\w.]*)(.*)$/s.exec(trimmed);
    if (!match) return escapeHtml(lead) + paintRest(trimmed);
    const kind = FLOW.has(match[1]) ? "t-flow" : "t-command";
    return escapeHtml(lead) + `<span class="${kind}">${escapeHtml(match[1])}</span>` + paintRest(match[2]);
  }

  function paintRest(text) {
    let html = "";
    const pattern = /("(?:[^"\\]|\\.)*"?|'(?:[^'\\]|\\.)*'?)|(\b\d+(?:\.\d+)?\b)|([{}])|(#[0-9a-fA-F]{3,6}\b)/g;
    let last = 0;
    for (let m; (m = pattern.exec(text));) {
      html += escapeHtml(text.slice(last, m.index));
      const kind = m[1] ? "t-string" : m[2] || m[4] ? "t-number" : "t-brace";
      html += `<span class="${kind}">${escapeHtml(m[0])}</span>`;
      last = pattern.lastIndex;
    }
    return html + escapeHtml(text.slice(last));
  }

  function render() {
    const lines = source.value.split("\n");
    const marks = new Map();
    for (const problem of problems) {
      if (!problem.line) continue;
      const severity = problem.severity || "error";
      if (marks.get(problem.line) !== "error") marks.set(problem.line, severity);
    }
    highlight.innerHTML = lines.map((line, i) => {
      const painted = paintLine(line) || " ";
      return marks.get(i + 1) === "error" ? `<span class="line-error">${painted}</span>` : painted;
    }).join("\n") + "\n ";
    gutter.innerHTML = lines.map((_, i) => {
      const mark = marks.get(i + 1);
      return `<div${mark ? ` class="${mark}"` : ""} data-line="${i + 1}">${i + 1}</div>`;
    }).join("");
  }

  // ----- editing -------------------------------------------------------------------------------------------
  function insert(text) {
    source.focus();
    // execCommand keeps ctrl+z working; setRangeText is the fallback for browsers that dropped it
    if (!document.execCommand || !document.execCommand("insertText", false, text)) {
      source.setRangeText(text, source.selectionStart, source.selectionEnd, "end");
      source.dispatchEvent(new Event("input"));
    }
  }

  function lineStart(index) { return source.value.lastIndexOf("\n", index - 1) + 1; }

  function indentSelection(outdent) {
    const value = source.value;
    const from = lineStart(source.selectionStart);
    let to = source.selectionEnd;
    if (to > from && value[to - 1] === "\n") to--;
    const end = value.indexOf("\n", to) === -1 ? value.length : value.indexOf("\n", to);
    const block = value.slice(from, end);
    const changed = block.split("\n").map((line) => {
      if (!outdent) return INDENT + line;
      const spaces = /^ {0,4}|^\t/.exec(line)[0];
      return line.slice(spaces.length);
    }).join("\n");
    source.setSelectionRange(from, end);
    insert(changed);
    source.setSelectionRange(from, from + changed.length);
  }

  function goToLine(number) {
    const lines = source.value.split("\n");
    const index = Math.min(Math.max(number, 1), lines.length) - 1;
    const start = lines.slice(0, index).reduce((sum, line) => sum + line.length + 1, 0);
    source.focus();
    source.setSelectionRange(start, start + lines[index].length);
    const top = index * 21;
    if (top < editor.scrollTop || top > editor.scrollTop + editor.clientHeight - 60) {
      editor.scrollTop = Math.max(0, top - editor.clientHeight / 3);
    }
  }

  source.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      run();
    } else if (event.key === "Tab" && !event.ctrlKey && !event.altKey) {
      event.preventDefault();
      if (event.shiftKey || source.selectionStart !== source.selectionEnd) indentSelection(event.shiftKey);
      else insert(INDENT);
    } else if (event.key === "Enter" && !event.shiftKey && source.selectionStart === source.selectionEnd) {
      event.preventDefault();
      const start = lineStart(source.selectionStart);
      const current = source.value.slice(start, source.selectionStart);
      let indent = /^\s*/.exec(current)[0];
      if (OPENERS.has(current.trim().split(/\s+/)[0])) indent += INDENT;
      insert("\n" + indent);
    } else if (event.key === "Escape") {
      if (frame) stop();
      else source.blur(); // lets keyboard users tab out of the editor
    }
  });

  source.addEventListener("input", () => {
    render();
    clearTimeout(checkTimer);
    checkTimer = setTimeout(check, 350);
    clearTimeout(draftTimer);
    draftTimer = setTimeout(() => storage.set(DRAFT_KEY, JSON.stringify({ name: programName, text: source.value })), 500);
  });

  gutter.addEventListener("click", (event) => {
    const line = event.target.closest("[data-line]");
    if (line) goToLine(Number(line.dataset.line));
  });

  function setProgram(text, name) {
    source.value = text;
    loadedText = text;
    programName = name || "program";
    $("filename").textContent = programName + ".gubl";
    source.setSelectionRange(0, 0);
    editor.scrollTop = 0;
    editor.scrollLeft = 0;
    render();
    check();
  }

  // ----- checking ------------------------------------------------------------------------------------------
  function check() {
    if (!bridge) return;
    try {
      problems = JSON.parse(bridge.check(source.value));
    } catch (error) {
      problems = [{ line: 0, severity: "error", message: "the checker stopped: " + error.message }];
    }
    render();
    showProblems();
    if ($("panel-javascript").hidden === false) showJavaScript();
  }

  function showProblems() {
    const list = $("problems");
    list.textContent = "";
    const errors = problems.filter((p) => (p.severity || "error") === "error").length;
    const count = $("problem-count");
    count.hidden = problems.length === 0;
    count.textContent = String(problems.length);
    count.classList.toggle("warn", errors === 0);
    if (!problems.length) {
      const item = document.createElement("li");
      item.className = "empty";
      item.textContent = "No problems found.";
      list.append(item);
    }
    for (const problem of problems) {
      const item = document.createElement("li");
      item.className = problem.severity || "error";
      const where = document.createElement("span");
      where.className = "where";
      where.textContent = problem.line ? "line " + problem.line : "";
      const message = document.createElement("span");
      message.textContent = problem.message;
      item.append(where, message);
      if (problem.line) item.addEventListener("click", () => goToLine(problem.line));
      list.append(item);
    }
    if (!frame) {
      if (errors) setStatus(errors === 1 ? "1 problem to fix" : `${errors} problems to fix`, "bad");
      else setStatus("Ready", "good");
    }
  }

  function translate() {
    return JSON.parse(bridge.translate(source.value, programName));
  }

  function showJavaScript() {
    if (!bridge) return;
    const result = translate();
    $("javascript").textContent = result.ok ? result.code : "// " + result.error;
  }

  // ----- tabs ----------------------------------------------------------------------------------------------
  function openTab(name) {
    for (const tab of document.querySelectorAll(".tab")) {
      const chosen = tab.dataset.tab === name;
      tab.setAttribute("aria-selected", String(chosen));
      $("panel-" + tab.dataset.tab).hidden = !chosen;
    }
    if (name === "javascript") showJavaScript();
  }
  for (const tab of document.querySelectorAll(".tab")) tab.addEventListener("click", () => openTab(tab.dataset.tab));
  $("clear").addEventListener("click", () => { output.textContent = ""; });

  // ----- running -------------------------------------------------------------------------------------------
  // saved games (gublan's save and load) live in this page's storage, so a sandboxed program can still keep them
  function saves() {
    try { return JSON.parse(storage.get(SAVES_KEY) || "{}"); } catch (_) { return {}; }
  }

  // runs inside the sandboxed frame before the runtime: sends prints, errors and saves back to this page
  function frameBoot(saved, runtime, code) {
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
    const show = (type) => (...parts) => send({ type, text: parts.map(String).join(" ") });
    console.log = console.info = console.warn = show("print");
    console.error = show("error");
    addEventListener("error", (event) => send({ type: "error", text: "error: " + event.message }));
    addEventListener("unhandledrejection", (event) => {
      const reason = event.reason;
      send({ type: "error", text: "error: " + (reason && reason.message ? reason.message : String(reason)) });
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

  function frameDocument(code) {
    // "<" is escaped so the code can never close the <script> it sits in
    const json = (value) => JSON.stringify(value).replace(/</g, String.fromCharCode(92) + "u003c");
    const boot = `(${frameBoot.toString()})(${json(saves())}, ${json(runtimeSource)}, ${json(code)});`;
    const backdrop = getComputedStyle(stage).backgroundColor;
    return `<!doctype html><html><head><meta charset="utf-8"><meta name="color-scheme" content="light dark"><style>
html, body { margin: 0; height: 100%; background: ${backdrop}; overflow: hidden; }
#gublan-stage { display: flex; align-items: center; justify-content: center; height: 100%; padding: 12px; box-sizing: border-box; }
canvas { max-width: 100%; max-height: 100%; outline: none; box-shadow: 0 4px 24px rgba(0,0,0,.35); }
</style></head><body><div id="gublan-stage"></div><script>${boot}</script></body></html>`;
  }

  function stop(quiet) {
    if (frame) {
      frame.remove();
      frame = null;
      if (!quiet) say("stopped", "note");
    }
    stopButton.disabled = true;
    stageNote.hidden = false;
    stageNote.textContent = "Press Run to start the program. Windows and games show up here.";
    showProblems();
  }

  function run() {
    if (!bridge) return;
    stop(true);
    check();
    const result = translate();
    openTab("output");
    if (output.textContent) say("");
    if (!result.ok) {
      say(result.error, "error");
      setStatus("Fix the problems first", "bad");
      if (problems.length) openTab("problems");
      return;
    }
    $("javascript").textContent = result.code;
    for (const note of result.notes) say("note: " + note, "note");

    frame = document.createElement("iframe");
    frame.title = "Your program";
    // scripts, alerts and prompts only: no access to this page, its storage or its cookies
    frame.setAttribute("sandbox", "allow-scripts allow-modals");
    frame.srcdoc = frameDocument(result.code);
    stageNote.hidden = false;
    stageNote.textContent = "Running…";
    stage.append(frame);
    frame.addEventListener("load", () => frame && frame.focus());
    stopButton.disabled = false;
    setStatus("Running", "busy");
  }

  window.addEventListener("message", (event) => {
    if (!frame || event.source !== frame.contentWindow || !event.data || !event.data.gublan) return;
    const message = event.data;
    if (message.type === "print") say(message.text);
    else if (message.type === "error") { say(message.text, "error"); setStatus("Stopped with an error", "bad"); }
    else if (message.type === "window") { stageNote.hidden = true; frame.focus(); }
    else if (message.type === "save") {
      const all = saves();
      if (message.value === null) delete all[message.key];
      else all[message.key] = message.value;
      storage.set(SAVES_KEY, JSON.stringify(all));
    } else if (message.type === "done") {
      if (!statusText.classList.contains("bad")) setStatus("Finished", "good");
      stopButton.disabled = true;
      if (!stageNote.hidden) stageNote.textContent = "This program has no window. What it printed is below.";
    }
  });

  runButton.addEventListener("click", run);
  stopButton.addEventListener("click", () => stop());
  stage.addEventListener("click", () => frame && frame.focus());

  // ----- sharing -------------------------------------------------------------------------------------------
  function toBase64(bytes) {
    let binary = "";
    for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  const fromBase64 = (text) => Uint8Array.from(atob(text.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));

  async function pack(text) {
    const bytes = new TextEncoder().encode(text);
    if (!window.CompressionStream) return "t=" + toBase64(bytes);
    const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream("deflate-raw"));
    return "z=" + toBase64(new Uint8Array(await new Response(stream).arrayBuffer()));
  }

  async function unpack(hash) {
    const match = /^#(z|t)=([\w-]+)$/.exec(hash);
    if (!match) return null;
    const bytes = fromBase64(match[2]);
    if (match[1] === "t") return new TextDecoder().decode(bytes);
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
    return new TextDecoder().decode(await new Response(stream).arrayBuffer());
  }

  $("share").addEventListener("click", async () => {
    const link = location.href.split("#")[0] + "#" + await pack(source.value);
    history.replaceState(null, "", link);
    try {
      await navigator.clipboard.writeText(link);
      toast("Link copied");
    } catch (_) {
      window.prompt("Copy this link:", link);
    }
  });

  // ----- examples ------------------------------------------------------------------------------------------
  examplesBox.addEventListener("change", async () => {
    const chosen = manifest.examples.find((e) => e.file === examplesBox.value);
    examplesBox.value = "";
    if (!chosen) return;
    if (source.value.trim() && source.value !== loadedText && !window.confirm("Replace your program with this example?")) return;
    try {
      const response = await fetch(chosen.file);
      if (!response.ok) throw new Error(response.statusText);
      stop(true);
      setProgram(await response.text(), chosen.file.split("/").pop().replace(/\.gubl$/, ""));
      storage.set(DRAFT_KEY, JSON.stringify({ name: programName, text: source.value }));
    } catch (error) {
      say("couldn't open that example: " + error.message, "error");
    }
  });

  // ----- start up ------------------------------------------------------------------------------------------
  async function firstProgram() {
    try {
      const shared = await unpack(location.hash);
      if (shared !== null) return { text: shared, name: "shared" };
    } catch (_) {
      say("that link's program couldn't be read", "error");
    }
    try {
      const draft = JSON.parse(storage.get(DRAFT_KEY) || "null");
      if (draft && typeof draft.text === "string" && draft.text.trim()) return draft;
    } catch (_) { /* no draft */ }
    const first = manifest.examples[0];
    if (first) {
      const response = await fetch(first.file);
      if (response.ok) return { text: await response.text(), name: first.file.split("/").pop().replace(/\.gubl$/, "") };
    }
    return { text: "print hello from gublan\n", name: "program" };
  }

  async function loadGublan() {
    const pyodide = await loadPyodide();
    const files = ["bridge.py"].concat(manifest.python.map((name) => "gublan/" + name));
    const texts = await Promise.all(files.map(async (path) => {
      const response = await fetch(path);
      if (!response.ok) throw new Error(`${path}: ${response.status}`);
      return response.text();
    }));
    files.forEach((path, i) => {
      const target = "/gublan/" + path.replace(/^gublan\//, "");
      pyodide.FS.mkdirTree(target.slice(0, target.lastIndexOf("/")));
      pyodide.FS.writeFile(target, texts[i]);
    });
    pyodide.FS.mkdirTree("/gublan/project");
    pyodide.runPython("import sys; sys.path.insert(0, '/gublan')");
    runtimeSource = texts[files.indexOf("gublan/runtimes/gublan_runtime.js")];
    return pyodide.pyimport("bridge");
  }

  async function main() {
    setStatus("Loading Gublan…", "busy");
    try {
      manifest = await (await fetch("manifest.json")).json();
    } catch (_) {
      setStatus("This page is missing its files. Build it with web/build_site.py.", "bad");
      return;
    }
    $("version").textContent = manifest.version;
    for (const example of manifest.examples) {
      const option = document.createElement("option");
      option.value = example.file;
      option.textContent = example.title + (example.web ? "" : " (3D, studio only)");
      examplesBox.append(option);
    }
    const program = await firstProgram();
    setProgram(program.text, program.name);
    loadedText = program.name === "shared" ? program.text : loadedText;
    try {
      bridge = await loadGublan();
    } catch (error) {
      setStatus("Couldn't load Gublan. Check your connection and reload.", "bad");
      say("loading failed: " + error.message, "error");
      return;
    }
    runButton.disabled = false;
    check();
  }

  main();
})();
