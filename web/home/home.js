// gublan.xyz: colours the sample program, links it to the playground, keeps the tabs in step with scrolling,
// fills in live numbers from github, shows who is signed in, and hides a gublan or two.
// everything works (with less detail) if this script, github or the account server fails.
(function () {
  "use strict";
  const REPO = "gublans/gublan";
  const API = "https://api.github.com/repos/" + REPO;
  const INSTALLER = "GublanStudioSetup.exe";
  const CACHE_KEY = "gublan-site:github";
  const EGG_KEY = "gublan-site:found";
  const CACHE_MINUTES = 10;
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const escape = (text) => String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const store = {
    get(key) { try { return localStorage.getItem(key); } catch (_) { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch (_) { /* private mode */ } },
  };

  // a message along the bottom of the page
  let noteTimer = null;
  function note(text, seconds = 3.5) {
    let box = $("#note");
    if (!box) {
      box = document.createElement("div");
      box.id = "note";
      box.className = "egg-note";
      box.setAttribute("role", "status");
      document.body.append(box);
    }
    box.textContent = text;
    requestAnimationFrame(() => box.classList.add("show"));
    clearTimeout(noteTimer);
    noteTimer = setTimeout(() => box.classList.remove("show"), seconds * 1000);
  }

  // ----- the sample program ------------------------------------------------------------------------------
  // a small version of the playground's highlighter: enough for the sample, not the whole language
  const FLOW = new Set(["if", "elseif", "else", "end", "forever", "loop", "while", "for", "function", "return",
    "break", "continue", "match", "case", "try", "catch", "until", "call"]);
  const WORDS = new Set(["and", "or", "not", "in", "to", "true", "false", "dt", "pi"]);
  const EXPR = /("[^"]*")|(\d+(?:\.\d+)?)|([A-Za-z_]\w*)(\s*\()?|([{}])|(\+=|-=|==|!=|>=|<=|[-+*/<>=])|(\s+|.)/g;

  function expression(text) {
    let html = "";
    for (const m of text.matchAll(EXPR)) {
      if (m[1]) html += `<span class="t-string">${escape(m[1])}</span>`;
      else if (m[2]) html += `<span class="t-number">${m[2]}</span>`;
      else if (m[3] && m[4]) html += `<span class="t-function">${m[3]}</span>${escape(m[4])}`;
      else if (m[3]) html += WORDS.has(m[3]) ? `<span class="t-keyword">${m[3]}</span>` : m[3];
      else if (m[5]) html += `<span class="t-brace">${m[5]}</span>`;
      else if (m[6]) html += `<span class="t-operator">${escape(m[6])}</span>`;
      else html += escape(m[7]);
    }
    return html;
  }

  // plain command words, with {braces} holding expressions
  function words(text) {
    return text.split(/(\{[^}]*\})/).map((part) => {
      if (part.startsWith("{")) return `<span class="t-brace">{</span>${expression(part.slice(1, -1))}<span class="t-brace">}</span>`;
      return part.split(/(\s+)/).map((w) => /^-?\d+(?:\.\d+)?$/.test(w) ? `<span class="t-number">${w}</span>` : escape(w)).join("");
    }).join("");
  }

  function paint(line) {
    const indent = line.match(/^\s*/)[0];
    const rest = line.slice(indent.length);
    if (!rest) return "";
    if (rest.startsWith("//")) return indent + `<span class="t-comment">${escape(rest)}</span>`;
    const first = rest.match(/^[A-Za-z_]\w*/);
    if (!first) return indent + escape(rest);
    const word = first[0], after = rest.slice(word.length);
    if (/^\s*(\+=|-=|=)(?!=)/.test(after)) return indent + expression(rest);
    if (word === "function") {
      const name = after.match(/^(\s+)(\w+)(.*)$/);
      return indent + `<span class="t-flow">function</span>` + (name ? `${name[1]}<span class="t-function">${name[2]}</span>${escape(name[3])}` : escape(after));
    }
    const kind = FLOW.has(word) ? "t-flow" : "t-command";
    const tail = ["if", "elseif", "while", "until", "return"].includes(word) ? expression(after) : words(after);
    return indent + `<span class="${kind}">${word}</span>` + tail;
  }

  const snippet = $("#snippet");
  if (snippet) {
    const source = snippet.textContent.replace(/\s+$/, "") + "\n";
    snippet.innerHTML = source.trimEnd().split("\n").map((line) => `<span class="ln">${paint(line) || " "}</span>`).join("");
    // the playground opens "#t=<program>" links (the plain form of its share links)
    const bytes = new TextEncoder().encode(source);
    let binary = "";
    for (const b of bytes) binary += String.fromCharCode(b);
    const packed = btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    $("#run-snippet").href = "playground/#t=" + packed;
  }

  // ----- tabs follow the section on screen -----------------------------------------------------------------
  const nav = $("#nav");
  const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 8);
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  const tabs = $$(".tabs a[data-tab]");
  const setTab = (id) => tabs.forEach((tab) => tab.setAttribute("aria-current", tab.dataset.tab === id ? "true" : "false"));
  if ("IntersectionObserver" in window) {
    const seen = new Map();
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) seen.set(entry.target.id, entry.isIntersecting ? entry.intersectionRatio : 0);
      let best = "top", most = 0;
      for (const [id, ratio] of seen) if (ratio > most) { most = ratio; best = id; }
      setTab(best);
    }, { rootMargin: "-72px 0px -40% 0px", threshold: [0, .1, .25, .5, .75, 1] });
    for (const tab of tabs) {
      const section = document.getElementById(tab.dataset.tab);
      if (section) observer.observe(section);
    }
  }

  // ----- who is signed in (account.js) ---------------------------------------------------------------------
  const account = window.GublanAccount;
  const who = $("#who");
  const DISCORD = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.3 4.4A19.6 19.6 0 0 0 15.4 3l-.6 1.3a18.2 18.2 0 0 0-5.6 0L8.6 3a19.5 19.5 0 0 0-4.9 1.5C.6 9.1-.3 13.6.1 18.1a19.8 19.8 0 0 0 6 3l1.3-2.1c-.7-.3-1.4-.6-2-1l.5-.4a14.1 14.1 0 0 0 12.2 0l.5.4c-.6.4-1.3.7-2 1l1.3 2.1a19.7 19.7 0 0 0 6-3c.5-5.2-.8-9.7-3.6-13.7zM8 15.3c-1.2 0-2.2-1.1-2.2-2.4S6.8 10.5 8 10.5s2.2 1.1 2.2 2.4-1 2.4-2.2 2.4zm8 0c-1.2 0-2.2-1.1-2.2-2.4s1-2.4 2.2-2.4 2.2 1.1 2.2 2.4-1 2.4-2.2 2.4z"/></svg>';

  function showWho() {
    if (!account || !account.configured) return;
    const user = account.user();
    who.hidden = false;
    if (user) {
      who.innerHTML = (user.avatar ? `<img src="${escape(user.avatar)}" alt="">` : DISCORD) + `<span>${escape(user.name.toLowerCase())}</span>`;
      who.title = `signed in as ${user.name.toLowerCase()}. your settings and files sync in the playground and the studio.`;
    } else {
      who.innerHTML = DISCORD + "<span>sign in</span>";
      who.title = "sign in with discord to keep your settings and files everywhere";
    }
  }
  if (account && account.configured && who) {
    who.addEventListener("click", () => {
      if (account.user()) location.href = "playground/#account";
      else account.signIn().catch((error) => note("couldn't start signing in: " + String(error.message).toLowerCase(), 6));
    });
    account.onChange(showWho);
    account.ready.then((justSignedIn) => {
      const user = account.user();
      if (justSignedIn && user) note(`signed in as ${user.name.toLowerCase()}`);
    }, (error) => note("couldn't sign in: " + String(error.message).toLowerCase(), 6)).finally(showWho);
    showWho();
  }

  // ----- github ----------------------------------------------------------------------------------------------
  const numberText = (n) => n >= 10000 ? (n / 1000).toFixed(n >= 100000 ? 0 : 1).replace(/\.0$/, "") + "k" : n.toLocaleString("en");
  const sizeText = (bytes) => (bytes / 1048576).toFixed(0) + " mb";
  const dateText = (iso) => new Date(iso).toLocaleDateString("en", { year: "numeric", month: "short", day: "numeric" }).toLowerCase();

  function agoText(iso) {
    const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
    const steps = [[60, "second"], [60, "minute"], [24, "hour"], [7, "day"], [4.35, "week"], [12, "month"], [Infinity, "year"]];
    let value = seconds;
    for (const [size, unit] of steps) {
      if (value < size) {
        const whole = Math.max(1, Math.floor(value));
        return unit === "second" ? "just now" : `${whole} ${unit}${whole === 1 ? "" : "s"} ago`;
      }
      value /= size;
    }
    return dateText(iso);
  }

  function setStat(name, text) {
    for (const el of $$(`[data-stat="${name}"]`)) el.textContent = text;
  }

  function readCache() {
    try {
      const cached = JSON.parse(store.get(CACHE_KEY) || "null");
      if (cached && Date.now() - cached.at < CACHE_MINUTES * 60000) return cached.data;
    } catch (_) { /* bad data */ }
    return null;
  }

  async function getJSON(url) {
    const response = await fetch(url, { headers: { Accept: "application/vnd.github+json" } });
    if (!response.ok) throw new Error(response.status + " from " + url);
    return response;
  }

  // the number of commits is the last page number when asking for one commit per page
  async function commitCount() {
    try {
      const response = await getJSON(API + "/commits?per_page=1");
      const last = /[?&]page=(\d+)>;\s*rel="last"/.exec(response.headers.get("Link") || "");
      return last ? Number(last[1]) : (await response.json()).length;
    } catch (_) {
      return null;
    }
  }

  async function fetchGithub() {
    const [repoResponse, releasesResponse, commits] = await Promise.all([
      getJSON(API), getJSON(API + "/releases?per_page=100"), commitCount(),
    ]);
    const repo = await repoResponse.json();
    const releases = (await releasesResponse.json()).filter((r) => !r.draft);
    return {
      stars: repo.stargazers_count, forks: repo.forks_count, issues: repo.open_issues_count,
      language: repo.language, pushed: repo.pushed_at, created: repo.created_at, commits,
      releases: releases.map((r) => {
        const installer = r.assets.find((a) => a.name === INSTALLER);
        return {
          tag: r.tag_name, url: r.html_url, date: r.published_at, prerelease: r.prerelease,
          downloads: r.assets.reduce((sum, a) => sum + a.download_count, 0),
          size: installer ? installer.size : null,
        };
      }),
    };
  }

  function show(data) {
    const stable = data.releases.filter((r) => !r.prerelease);
    const latest = stable[0] || data.releases[0];
    const downloads = data.releases.reduce((sum, r) => sum + r.downloads, 0);

    setStat("stars", numberText(data.stars));
    setStat("forks", numberText(data.forks));
    setStat("issues", numberText(data.issues));
    setStat("releases", numberText(data.releases.length));
    setStat("downloads", numberText(downloads));
    setStat("commits", data.commits == null ? "–" : numberText(data.commits));
    setStat("language", (data.language || "–").toLowerCase());
    setStat("pushed", data.pushed ? agoText(data.pushed) : "–");
    setStat("created", data.created ? dateText(data.created) : "–");

    if (latest) {
      setStat("version", latest.tag.replace(/^v/, ""));
      setStat("released", " · released " + dateText(latest.date));
      setStat("latest", `${latest.tag}, ${agoText(latest.date)}`);
      if (latest.size) setStat("size-dot", " · " + sizeText(latest.size) + " installer");
    }

    const list = $("#releases");
    if (!data.releases.length) {
      list.innerHTML = `<li class="empty">no releases yet.</li>`;
      return;
    }
    const most = Math.max(1, ...data.releases.map((r) => r.downloads));
    list.innerHTML = data.releases.slice(0, 8).map((r) => `
      <li class="${r === latest ? "latest" : ""}">
        <a href="${escape(r.url)}" title="${escape(r.tag)} on github">
          <span class="tag-name">${escape(r.tag)}<span class="when">${escape(dateText(r.date))}</span></span>
          <span class="bar" aria-hidden="true"><span style="width:${(r.downloads / most * 100).toFixed(1)}%"></span></span>
          <span class="count">${numberText(r.downloads)} ${r.downloads === 1 ? "download" : "downloads"}</span>
        </a>
      </li>`).join("");
    if (data.releases.length > 8) {
      list.insertAdjacentHTML("beforeend", `<li class="empty"><a href="https://github.com/${REPO}/releases">see all ${data.releases.length} releases</a></li>`);
    }
  }

  async function loadGithub() {
    const stats = $("#stats");
    const cached = readCache();
    if (cached) { show(cached); return; }
    stats.classList.add("loading");
    try {
      const data = await fetchGithub();
      store.set(CACHE_KEY, JSON.stringify({ at: Date.now(), data }));
      show(data);
    } catch (_) {
      $("#releases").innerHTML = `<li class="empty">couldn't reach github just now. <a href="https://github.com/${REPO}/releases">see the releases on github</a>.</li>`;
      $("#gh-note").innerHTML = `numbers from <a href="https://github.com/${REPO}">gublans/gublan</a> couldn't load right now.`;
    } finally {
      stats.classList.remove("loading");
    }
  }

  loadGithub();

  // ----- the easter egg: click the gublan a few times ------------------------------------------------------
  const LINES = ["hi!", "hello again", "hehe", "that tickles", "ok stop", "i'm warning you", "fine."];
  const mascot = $("#mascot");
  const bubble = $("#bubble");
  let clicks = 0, lastClick = 0, bubbleTimer = null, raining = false, audio = null;

  function blip(step) {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      const notes = step < 0 ? [523, 659, 784, 1047] : [392 + step * 55];
      notes.forEach((frequency, i) => {
        const osc = audio.createOscillator(), gain = audio.createGain();
        const start = audio.currentTime + i * 0.08;
        osc.type = "square";
        osc.frequency.value = frequency;
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.exponentialRampToValueAtTime(0.05, start + 0.01);
        gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.14);
        osc.connect(gain).connect(audio.destination);
        osc.start(start);
        osc.stop(start + 0.16);
      });
    } catch (_) { /* no sound: still fun */ }
  }

  function say(text) {
    if (!bubble) return;
    bubble.textContent = text;
    bubble.classList.add("show");
    clearTimeout(bubbleTimer);
    bubbleTimer = setTimeout(() => bubble.classList.remove("show"), 1400);
  }

  function rain() {
    raining = true;
    const found = Number(store.get(EGG_KEY) || 0) + 1;
    store.set(EGG_KEY, String(found));
    blip(-1);
    if (mascot) {
      mascot.classList.remove("spin");
      void mascot.offsetWidth;
      mascot.classList.add("spin");
    }
    note(found === 1 ? "you found the gublan swarm" : `the gublan swarm, again (${found} times now)`, 5);
    if (calm) { raining = false; return; }

    const layer = document.createElement("div");
    layer.className = "rain";
    layer.setAttribute("aria-hidden", "true");
    document.body.append(layer);
    const width = innerWidth, floor = innerHeight;
    const sizes = [25, 50, 50, 75];
    const gublans = Array.from({ length: Math.min(60, Math.round(width / 22)) }, () => {
      const size = sizes[Math.floor(Math.random() * sizes.length)];
      const img = new Image(size, size);
      img.src = "logo.png";
      img.alt = "";
      layer.append(img);
      return {
        img, size, x: Math.random() * (width - size), y: -size - Math.random() * floor * 0.9,
        vx: (Math.random() - 0.5) * 120, vy: Math.random() * 200, spin: (Math.random() - 0.5) * 540, angle: 0,
        flip: Math.random() < 0.5 ? -1 : 1,
      };
    });
    let last = performance.now();
    const started = last;
    function step(now) {
      const dt = Math.min(0.033, (now - last) / 1000);
      last = now;
      for (const g of gublans) {
        g.vy += 1700 * dt;
        g.x += g.vx * dt;
        g.y += g.vy * dt;
        g.angle += g.spin * dt;
        if (g.y + g.size > floor) {
          g.y = floor - g.size;
          g.vy *= -0.42;
          g.vx *= 0.8;
          g.spin *= 0.6;
          if (Math.abs(g.vy) < 40) g.vy = 0;
        }
        if (g.x < 0 || g.x + g.size > width) { g.vx *= -1; g.x = Math.max(0, Math.min(width - g.size, g.x)); }
        g.img.style.transform = `translate(${g.x}px, ${g.y}px) rotate(${g.angle}deg) scaleX(${g.flip})`;
      }
      const age = now - started;
      if (age > 5200) layer.style.opacity = String(Math.max(0, 1 - (age - 5200) / 900));
      if (age < 6100) requestAnimationFrame(step);
      else { layer.remove(); raining = false; }
    }
    requestAnimationFrame(step);
  }

  for (const gublan of $$("[data-gublan]")) {
    gublan.addEventListener("click", (event) => {
      // the logo links home, and this is home: stay, scroll up, and count the click
      if (gublan.matches("a")) {
        event.preventDefault();
        if (scrollY > 0) scrollTo({ top: 0, behavior: calm ? "auto" : "smooth" });
      }
      const now = performance.now();
      clicks = now - lastClick < 1400 ? clicks + 1 : 1;
      lastClick = now;
      if (mascot) {
        mascot.classList.remove("boop");
        void mascot.offsetWidth;
        mascot.classList.add("boop");
      }
      if (raining) return;
      if (clicks >= LINES.length) {
        clicks = 0;
        say(LINES[LINES.length - 1]);
        rain();
      } else {
        blip(clicks);
        say(LINES[clicks - 1]);
      }
    });
  }
})();
