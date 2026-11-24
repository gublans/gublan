// gublan.xyz: colours the sample program, links it to the playground, keeps the tabs in step with scrolling,
// and fills in live numbers from github. everything works (with less detail) if this script or github fails.
(function () {
  "use strict";
  const REPO = "gublans/gublan";
  const API = "https://api.github.com/repos/" + REPO;
  const INSTALLER = "GublanStudioSetup.exe";
  const CACHE_KEY = "gublan-site:github";
  const CACHE_MINUTES = 10;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const escape = (text) => text.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

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
    }, { rootMargin: "-64px 0px -40% 0px", threshold: [0, .1, .25, .5, .75, 1] });
    for (const tab of tabs) {
      const section = document.getElementById(tab.dataset.tab);
      if (section) observer.observe(section);
    }
  }

  // ----- github ----------------------------------------------------------------------------------------------
  const numberText = (n) => n >= 10000 ? (n / 1000).toFixed(n >= 100000 ? 0 : 1).replace(/\.0$/, "") + "k" : n.toLocaleString("en");
  const sizeText = (bytes) => (bytes / 1048576).toFixed(0) + " MB";
  const dateText = (iso) => new Date(iso).toLocaleDateString("en", { year: "numeric", month: "short", day: "numeric" });

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
      const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
      if (cached && Date.now() - cached.at < CACHE_MINUTES * 60000) return cached.data;
    } catch (_) { /* storage blocked or bad data */ }
    return null;
  }

  function writeCache(data) {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify({ at: Date.now(), data })); } catch (_) { /* fine */ }
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
    setStat("language", data.language || "–");
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
      list.innerHTML = `<li class="empty">No releases yet.</li>`;
      return;
    }
    const most = Math.max(1, ...data.releases.map((r) => r.downloads));
    list.innerHTML = data.releases.slice(0, 8).map((r) => `
      <li class="${r === latest ? "latest" : ""}">
        <a href="${escape(r.url)}" title="${escape(r.tag)} on GitHub">
          <span class="tag">${escape(r.tag)}<span class="when">${escape(dateText(r.date))}</span></span>
          <span class="bar" aria-hidden="true"><span style="width:${(r.downloads / most * 100).toFixed(1)}%"></span></span>
          <span class="count">${numberText(r.downloads)} ${r.downloads === 1 ? "download" : "downloads"}</span>
        </a>
      </li>`).join("");
    if (data.releases.length > 8) {
      list.insertAdjacentHTML("beforeend", `<li class="empty"><a href="https://github.com/${REPO}/releases">See all ${data.releases.length} releases</a></li>`);
    }
  }

  async function loadGithub() {
    const stats = $("#stats");
    const cached = readCache();
    if (cached) { show(cached); return; }
    stats.classList.add("loading");
    try {
      const data = await fetchGithub();
      writeCache(data);
      show(data);
    } catch (_) {
      $("#releases").innerHTML = `<li class="empty">Couldn't reach GitHub just now. <a href="https://github.com/${REPO}/releases">See the releases on GitHub</a>.</li>`;
      $("#gh-note").innerHTML = `Numbers from <a href="https://github.com/${REPO}">gublans/gublan</a> couldn't load right now.`;
    } finally {
      stats.classList.remove("loading");
    }
  }

  loadGithub();
})();
