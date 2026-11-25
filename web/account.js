// gublan accounts on gublan.xyz: sign in with discord through supabase, and keep a little data per person.
// it makes the same calls as gublan studio (studio/account.py). web/build_site.py fills in the url and key from
// there. both are public: the row level security policy on user_data is what keeps each person's row private.
//
//   GublanAccount.configured        false when the site was built without a supabase project
//   GublanAccount.ready             a promise, settled once a sign-in that just came back has finished
//                                   (true if it signed someone in; rejects with the reason if that failed)
//   GublanAccount.user()            {id, name, avatar} or null
//   GublanAccount.signIn()          off to discord, then back to this page
//   GublanAccount.signOut()
//   GublanAccount.load()            the user_data row: {settings, project, updated_at} or null
//   GublanAccount.save(fields)      upsert some of the row's columns
//   GublanAccount.deleteData()
//   GublanAccount.onChange(fn)      fn(user) whenever someone signs in or out (in any tab)
//
// creations: programs people publish to gublan.xyz. anyone can look at them; only their owner can change them.
//   GublanAccount.creation(id)      one creation with its files: {id, title, about, author, files, main, uses_3d,
//                                   user_id, created_at, updated_at}, or null
//   GublanAccount.creations(opts)   a page of creations without their files, newest first.
//                                   opts: {search, mine, only3d, limit, offset}
//   GublanAccount.publish(row)      publish {title, about, files, main, uses_3d}, or update one of yours with
//                                   row.id. gives back the saved creation. the server fills in the author.
//   GublanAccount.unpublish(id)     take one of yours down
//   GublanAccount.creationLink(id)  where anyone can play it
(function () {
  "use strict";
  const SUPABASE_URL = "{{SUPABASE_URL}}".replace(/\/+$/, "");
  const SUPABASE_KEY = "{{SUPABASE_KEY}}";
  const SESSION_KEY = "gublan-account:session";
  const VERIFIER_KEY = "gublan-account:verifier";
  const REFRESH_EARLY = 120;
  const configured = /^https:\/\//.test(SUPABASE_URL) && !!SUPABASE_KEY && !/^\{\{/.test(SUPABASE_KEY); // not built yet

  const store = {
    get(key) { try { return localStorage.getItem(key); } catch (_) { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch (_) { /* private mode */ } },
    remove(key) { try { localStorage.removeItem(key); } catch (_) { /* nothing to remove */ } },
  };
  const listeners = new Set();
  let refreshing = null;

  function readSession() {
    try { return JSON.parse(store.get(SESSION_KEY) || "null"); } catch (_) { return null; }
  }
  function writeSession(session) {
    if (session) store.set(SESSION_KEY, JSON.stringify(session));
    else store.remove(SESSION_KEY);
    tell();
  }
  function tell() {
    const now = user();
    for (const listener of listeners) { try { listener(now); } catch (_) { /* one listener can't stop the rest */ } }
  }
  addEventListener("storage", (event) => { if (event.key === SESSION_KEY) tell(); });

  function user() {
    const session = readSession();
    const found = session && session.user;
    if (!found || !found.id) return null;
    const meta = found.user_metadata || {};
    const claims = meta.custom_claims || {};
    return {
      id: found.id,
      name: String(claims.global_name || meta.full_name || meta.name || meta.user_name || "you"),
      avatar: String(meta.avatar_url || ""),
    };
  }

  async function request(method, path, body, token, headers) {
    const response = await fetch(SUPABASE_URL + path, {
      method,
      headers: Object.assign({ apikey: SUPABASE_KEY, "Content-Type": "application/json" },
        token ? { Authorization: "Bearer " + token } : {}, headers || {}),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await response.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (_) { data = null; }
    if (!response.ok) {
      const detail = data && (data.msg || data.message || data.error_description || data.error);
      const error = new Error(`${detail || response.statusText || "request failed"} (${response.status})`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function toSession(data) {
    if (!data || !data.access_token || !data.refresh_token) throw new Error("the account server didn't send a session");
    return {
      access_token: data.access_token, refresh_token: data.refresh_token, user: data.user || null,
      expires_at: data.expires_at || Math.floor(Date.now() / 1000) + Number(data.expires_in || 3600),
    };
  }

  // a working access token, refreshed first when it is about to run out
  async function token() {
    const session = readSession();
    if (!session) throw new Error("not signed in");
    if (session.expires_at - REFRESH_EARLY > Date.now() / 1000) return session.access_token;
    if (!refreshing) {
      refreshing = (async () => {
        try {
          const latest = readSession(); // another tab may have refreshed it already
          if (!latest) throw new Error("not signed in");
          if (latest.expires_at - REFRESH_EARLY > Date.now() / 1000) return latest.access_token;
          const fresh = toSession(await request("POST", "/auth/v1/token?grant_type=refresh_token",
            { refresh_token: latest.refresh_token }));
          if (!fresh.user) fresh.user = latest.user;
          writeSession(fresh);
          return fresh.access_token;
        } catch (error) {
          if ([400, 401, 403].includes(error.status)) writeSession(null); // revoked or expired for good
          throw error;
        } finally {
          refreshing = null;
        }
      })();
    }
    return refreshing;
  }

  // ----- signing in (pkce: only this browser knows the verifier that turns the code into a session) ----------
  const base64url = (bytes) => btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

  async function signIn() {
    if (!configured) throw new Error("accounts aren't set up on this site");
    const verifier = base64url(crypto.getRandomValues(new Uint8Array(32)));
    const challenge = base64url(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier))));
    store.set(VERIFIER_KEY, verifier);
    const back = location.origin + location.pathname;
    const query = new URLSearchParams({ provider: "discord", redirect_to: back, code_challenge: challenge, code_challenge_method: "s256" });
    location.assign(`${SUPABASE_URL}/auth/v1/authorize?${query}`);
  }

  // coming back from discord: ?code=... (or ?error=...) on this page. true when it signed someone in.
  async function finishSignIn() {
    const params = new URLSearchParams(location.search);
    const code = params.get("code");
    const problem = params.get("error_description") || params.get("error");
    if (!code && !problem) return false;
    params.delete("code");
    for (const name of ["error", "error_code", "error_description", "state"]) params.delete(name);
    const rest = params.toString();
    history.replaceState(null, "", location.pathname + (rest ? "?" + rest : "") + location.hash);
    const verifier = store.get(VERIFIER_KEY);
    store.remove(VERIFIER_KEY);
    if (problem) throw new Error(problem);
    if (!verifier) throw new Error("this sign-in was started in another browser or tab. try signing in again.");
    writeSession(toSession(await request("POST", "/auth/v1/token?grant_type=pkce", { auth_code: code, code_verifier: verifier })));
    return true;
  }

  async function signOut() {
    try { await request("POST", "/auth/v1/logout?scope=local", undefined, await token()); } catch (_) { /* still sign out here */ }
    writeSession(null);
  }

  // ----- the user_data row ----------------------------------------------------------------------------------
  function me() {
    const found = user();
    if (!found) throw new Error("not signed in");
    return found.id;
  }

  async function load() {
    const id = me();
    const rows = await request("GET", `/rest/v1/user_data?select=settings,project,updated_at&user_id=eq.${encodeURIComponent(id)}`,
      undefined, await token());
    return Array.isArray(rows) && rows.length ? rows[0] : null;
  }

  async function save(fields) {
    const row = Object.assign({ user_id: me(), updated_at: new Date().toISOString() }, fields);
    await request("POST", "/rest/v1/user_data?on_conflict=user_id", row, await token(),
      { Prefer: "resolution=merge-duplicates,return=minimal" });
  }

  async function deleteData() {
    await request("DELETE", `/rest/v1/user_data?user_id=eq.${encodeURIComponent(me())}`, undefined, await token());
  }

  // ----- creations -------------------------------------------------------------------------------------------
  const LISTED = "id,title,about,author,uses_3d,user_id,created_at,updated_at";
  const SITE = "https://gublan.xyz";

  // signed in people read with their token, everyone else as the public
  async function maybeToken() {
    try { return user() ? await token() : undefined; } catch (_) { return undefined; }
  }

  async function creation(id) {
    if (!configured) throw new Error("accounts aren't set up on this site");
    const clean = String(id || "").replace(/[^\w-]/g, "");
    if (!clean) return null;
    const rows = await request("GET", `/rest/v1/creations?select=${LISTED},files,main&id=eq.${clean}`, undefined, await maybeToken());
    return Array.isArray(rows) && rows.length ? rows[0] : null;
  }

  async function creations(options) {
    if (!configured) throw new Error("accounts aren't set up on this site");
    const { search = "", mine = false, only3d = null, limit = 24, offset = 0 } = options || {};
    const query = new URLSearchParams({ select: LISTED, order: "created_at.desc", limit: String(limit), offset: String(offset) });
    if (mine) query.set("user_id", "eq." + me());
    if (only3d !== null && only3d !== undefined) query.set("uses_3d", "eq." + Boolean(only3d));
    // letters, numbers and spaces only: the rest mean something to the database's filter language
    const words = String(search).toLowerCase().replace(/[^\p{L}\p{N} _-]+/gu, " ").trim().slice(0, 60);
    if (words) query.set("or", `(title.ilike.*${words}*,author.ilike.*${words}*,about.ilike.*${words}*)`);
    const rows = await request("GET", "/rest/v1/creations?" + query, undefined, await maybeToken());
    return Array.isArray(rows) ? rows : [];
  }

  async function publish(row) {
    me();
    const fields = { title: String(row.title || "").trim().slice(0, 80), about: String(row.about || "").trim().slice(0, 1000),
      files: row.files, main: String(row.main || ""), uses_3d: Boolean(row.uses_3d) };
    if (!fields.title) throw new Error("give it a name first");
    const prefer = { Prefer: "return=representation" };
    if (row.id) {
      const clean = String(row.id).replace(/[^\w-]/g, "");
      const rows = await request("PATCH", `/rest/v1/creations?id=eq.${clean}&select=${LISTED},main`, fields, await token(), prefer);
      if (Array.isArray(rows) && rows.length) return rows[0];
      throw new Error("that creation isn't yours any more, or it was taken down");
    }
    const rows = await request("POST", `/rest/v1/creations?select=${LISTED},main`, fields, await token(), prefer);
    if (!Array.isArray(rows) || !rows.length) throw new Error("the server didn't say what it saved");
    return rows[0];
  }

  async function unpublish(id) {
    const clean = String(id || "").replace(/[^\w-]/g, "");
    await request("DELETE", `/rest/v1/creations?id=eq.${clean}&user_id=eq.${encodeURIComponent(me())}`, undefined, await token());
  }

  // the playground plays it. a copy of the site on another address links to itself.
  function creationLink(id) {
    const here = /^https?:$/.test(location.protocol) && location.hostname !== "gublan.xyz" ? location.origin : SITE;
    const root = here === SITE ? "/" : location.pathname.replace(/\/(playground|explore)\/.*$/, "/").replace(/[^/]*$/, "");
    return `${here}${root}playground/?c=${encodeURIComponent(id)}`;
  }

  const ready = configured ? finishSignIn() : Promise.resolve(false);
  ready.catch(() => { /* the page shows it: GublanAccount.ready rejects with the reason */ });

  window.GublanAccount = {
    configured, ready, user, signIn, signOut, load, save, deleteData,
    creation, creations, publish, unpublish, creationLink,
    onChange(listener) { listeners.add(listener); return () => listeners.delete(listener); },
  };
})();
