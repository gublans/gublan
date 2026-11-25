// gublan.xyz/explore: the creations people published from the playground and gublan studio, newest first.
// account.js does the talking: anyone can read creations, and signed in people can take their own down.
(function () {
  "use strict";
  const account = window.GublanAccount;
  const $ = (id) => document.getElementById(id);
  const grid = $("grid");
  const statusLine = $("status");
  const moreButton = $("more");
  const search = $("search");
  const who = $("who");
  const PAGE = 24;

  let filter = new URLSearchParams(location.search).get("mine") ? "mine" : "all";
  let offset = 0;
  let asked = 0; // only the newest request may fill the grid

  const escape = (text) => String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  function agoText(iso) {
    const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
    if (seconds < 60) return "just now";
    const steps = [[60, "minute"], [24, "hour"], [7, "day"], [4.35, "week"], [12, "month"], [Infinity, "year"]];
    let value = seconds / 60;
    for (const [size, unit] of steps) {
      if (value < size) {
        const whole = Math.max(1, Math.floor(value));
        return `${whole} ${unit}${whole === 1 ? "" : "s"} ago`;
      }
      value /= size;
    }
    return "";
  }

  // every creation gets its own little pixel creature, made from its id, so the grid isn't a wall of text
  function hash(text) {
    let value = 2166136261;
    for (let i = 0; i < text.length; i++) value = Math.imul(value ^ text.charCodeAt(i), 16777619);
    return value >>> 0;
  }
  function creature(id, is3d) {
    let seed = hash(String(id));
    const next = () => {
      seed = Math.imul(seed ^ (seed >>> 15), 2246822507) >>> 0;
      seed = Math.imul(seed ^ (seed >>> 13), 3266489909) >>> 0;
      return (seed ^= seed >>> 16) / 4294967296;
    };
    const hue = Math.floor(next() * 360);
    const body = `hsl(${hue} 38% 66%)`;
    const shade = `hsl(${hue} 30% 46%)`;
    const cells = [];
    for (let y = 0; y < 7; y++) {
      for (let x = 0; x < 4; x++) {
        const edge = y === 0 || y === 6 || x === 0;
        if (next() < (edge ? 0.42 : 0.72)) {
          const fill = next() < 0.22 ? shade : body;
          cells.push(`<rect x="${x}" y="${y}" width="1" height="1" fill="${fill}"/>`);
          if (x < 3) cells.push(`<rect x="${6 - x}" y="${y}" width="1" height="1" fill="${fill}"/>`);
        }
      }
    }
    // two eyes, always
    const eyeY = 2 + Math.floor(next() * 2);
    cells.push(`<rect x="2" y="${eyeY}" width="1" height="1" fill="#182014"/><rect x="4" y="${eyeY}" width="1" height="1" fill="#182014"/>`);
    const back = is3d ? `<rect x="-1" y="7.4" width="9" height=".6" fill="${shade}" opacity=".5"/>` : "";
    return `<svg viewBox="-1 -1 9 9" aria-hidden="true">${back}${cells.join("")}</svg>`;
  }

  function card(item, mine) {
    const li = document.createElement("li");
    li.className = "card";
    li.style.animationDelay = Math.min(grid.children.length % PAGE, 12) * 30 + "ms";
    const link = account.creationLink(item.id);
    const when = agoText(item.updated_at || item.created_at);
    li.innerHTML = `<a href="${escape(link)}">
        <div class="thumb">${creature(item.id, item.uses_3d)}<span class="kind">${item.uses_3d ? "3d" : "2d"}</span>
          <span class="play"><svg viewBox="0 0 16 16"><path d="M4.5 2.8v10.4L13 8z"/></svg></span></div>
        <div class="card-text">
          <h2>${escape(item.title)}</h2>
          <p class="by">by ${escape(String(item.author || "someone").toLowerCase())}${when ? " · " + when : ""}</p>
          ${item.about ? `<p class="about">${escape(item.about)}</p>` : ""}
        </div>
      </a>`;
    if (mine) {
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "remove";
      remove.textContent = "take it down";
      remove.addEventListener("click", async () => {
        if (!window.confirm(`take "${item.title}" down? its link stops working.`)) return;
        remove.disabled = true;
        try {
          await account.unpublish(item.id);
          li.remove();
          if (!grid.children.length) load(true);
        } catch (error) {
          remove.disabled = false;
          statusLine.textContent = "couldn't take it down: " + String(error.message).toLowerCase();
        }
      });
      li.append(remove);
    }
    return li;
  }

  function emptyState(text, withButton) {
    const li = document.createElement("li");
    li.className = "empty-state";
    li.innerHTML = `<p>${escape(text)}</p>` + (withButton ? '<a class="btn primary" href="../playground/">open the playground</a>' : "");
    grid.append(li);
  }

  async function load(reset) {
    if (!account || !account.configured) {
      statusLine.textContent = "";
      grid.textContent = "";
      emptyState("this copy of the site has no account server, so there's nothing to explore here.", true);
      return;
    }
    if (reset) {
      offset = 0;
      grid.textContent = "";
    }
    const ticket = ++asked;
    const words = search.value.trim();
    statusLine.textContent = "loading…";
    moreButton.hidden = true;
    const mine = filter === "mine";
    let rows;
    try {
      rows = await account.creations({
        search: words, mine, only3d: filter === "3d" ? true : filter === "2d" ? false : null, limit: PAGE + 1, offset,
      });
    } catch (error) {
      if (ticket !== asked) return;
      const why = String(error.message || error).toLowerCase();
      statusLine.textContent = /relation|does not exist|\(404\)/.test(why) ? "publishing isn't switched on for this site yet." : "couldn't load creations: " + why;
      return;
    }
    if (ticket !== asked) return;
    const more = rows.length > PAGE;
    const user = account.user();
    for (const item of rows.slice(0, PAGE)) grid.append(card(item, Boolean(user && item.user_id === user.id && mine)));
    offset += Math.min(rows.length, PAGE);
    moreButton.hidden = !more;
    if (!grid.children.length) {
      statusLine.textContent = "";
      if (mine) emptyState("you haven't published anything yet. press publish in the playground, or file > publish in gublan studio.", true);
      else if (words) emptyState(`nothing matches "${words}".`, false);
      else emptyState("nothing here yet. be the first to publish something!", true);
    } else {
      statusLine.textContent = words ? `${offset}${more ? "+" : ""} found for "${words}"` : "";
    }
  }

  function setFilter(name) {
    filter = name;
    for (const button of document.querySelectorAll(".chips button")) button.setAttribute("aria-pressed", String(button.dataset.filter === name));
    const params = new URLSearchParams(location.search);
    if (name === "mine") params.set("mine", "1");
    else params.delete("mine");
    const rest = params.toString();
    history.replaceState(null, "", location.pathname + (rest ? "?" + rest : ""));
    load(true);
  }

  for (const button of document.querySelectorAll(".chips button")) button.addEventListener("click", () => setFilter(button.dataset.filter));
  let typing = 0;
  search.addEventListener("input", () => {
    clearTimeout(typing);
    typing = setTimeout(() => load(true), 300);
  });
  moreButton.addEventListener("click", () => load(false));

  // ----- who is signed in ---------------------------------------------------------------------------------
  const DISCORD = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.3 4.4A19.6 19.6 0 0 0 15.4 3l-.6 1.3a18.2 18.2 0 0 0-5.6 0L8.6 3a19.5 19.5 0 0 0-4.9 1.5C.6 9.1-.3 13.6.1 18.1a19.8 19.8 0 0 0 6 3l1.3-2.1c-.7-.3-1.4-.6-2-1l.5-.4a14.1 14.1 0 0 0 12.2 0l.5.4c-.6.4-1.3.7-2 1l1.3 2.1a19.7 19.7 0 0 0 6-3c.5-5.2-.8-9.7-3.6-13.7zM8 15.3c-1.2 0-2.2-1.1-2.2-2.4S6.8 10.5 8 10.5s2.2 1.1 2.2 2.4-1 2.4-2.2 2.4zm8 0c-1.2 0-2.2-1.1-2.2-2.4s1-2.4 2.2-2.4 2.2 1.1 2.2 2.4-1 2.4-2.2 2.4z"/></svg>';
  function showWho() {
    const user = account.user();
    who.hidden = false;
    who.innerHTML = user
      ? (user.avatar ? `<img src="${escape(user.avatar)}" alt="">` : DISCORD) + `<span>${escape(user.name.toLowerCase())}</span>`
      : DISCORD + "<span>sign in</span>";
    who.title = user ? `signed in as ${user.name.toLowerCase()}` : "sign in with discord to see and manage what you published";
    const mineChip = document.querySelector('.chips [data-filter="mine"]');
    mineChip.hidden = !user;
    if (!user && filter === "mine") setFilter("all");
  }

  if (account && account.configured) {
    who.addEventListener("click", () => {
      if (account.user()) setFilter("mine");
      else account.signIn().catch((error) => { statusLine.textContent = "couldn't start signing in: " + String(error.message).toLowerCase(); });
    });
    account.onChange(showWho);
    account.ready.catch((error) => { statusLine.textContent = "couldn't sign in: " + String(error.message).toLowerCase(); })
      .finally(() => {
        showWho();
        setFilter(filter);
      });
  } else load(true);
})();
