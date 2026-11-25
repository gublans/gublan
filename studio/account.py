"""signing in to gublan with discord, and keeping settings the same on every computer and on gublan.xyz.

accounts live in supabase. signing in is supabase's discord sign-in with pkce: the studio opens the browser, discord
asks the person, and supabase sends the browser back to a tiny web server on this computer (127.0.0.1, port
CALLBACK_PORT) with a one-time code. the studio swaps that code (and a secret only it knows) for a session.

SUPABASE_URL and SUPABASE_KEY are public: the website has them too (web/build_site.py copies them from here). what
keeps each person's data private is the row level security policy on the user_data table, which only lets a
signed-in person read and write their own row. never put the service_role key or the discord secret here.

the user_data row holds {"settings": {"studio": {...}, "playground": {...}}, "project": {...}}. the studio only
changes settings.studio and leaves the rest alone.

publishing puts a program on gublan.xyz/explore: a row in the creations table (docs/supabase_creations.sql) that
anyone can read and only its maker can change. share_link needs no account at all: like the playground's share
button, the whole program travels inside the link.

nothing here touches tk. the studio calls the slow parts from a background thread and hands the results back through
its queue (see GublanStudio's account methods in app.py).
"""

import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zlib
from datetime import datetime, timezone

from . import config, version

# from supabase: project settings > api keys. public on purpose (see above).
SUPABASE_URL = "https://cdhcazthrmltpvjwdosx.supabase.co"
SUPABASE_KEY = "sb_publishable_JjtsgObqZcsScs2Y4WLAfA_5sVSqScV"

# supabase must allow this address: authentication > url configuration > redirect urls: http://127.0.0.1:47813/**
CALLBACK_PORT = 47813
CALLBACK_PATH = "/auth/callback"
SIGN_IN_TIMEOUT = 300
TIMEOUT = 15
REFRESH_EARLY = 120  # refresh a session this many seconds before it runs out

PLAYGROUND = "https://gublan.xyz/playground/"
MAX_PUBLISH = 200_000  # characters in all the files together, the same as the playground
DATA_ENDINGS = (".txt", ".csv", ".tsv", ".json", ".md", ".dat", ".log")

# settings that belong to this computer rather than to the person: they never leave it
LOCAL_ONLY = frozenset({
    "recent", "session", "session_active", "folder", "window", "side_panel", "side_width", "bottom_panel",
    "bottom_height", "show_side", "show_bottom", "update_pending", "skipped_update", "export_folder", "live_address",
})


class AccountError(Exception):
    def __init__(self, text, status=None):
        super().__init__(text)
        self.status = status


def configured():
    return SUPABASE_URL.startswith("https://") and bool(SUPABASE_KEY)


def callback_url():
    return f"http://127.0.0.1:{CALLBACK_PORT}{CALLBACK_PATH}"


def account_path():
    return os.path.join(config.settings_folder(), "account.json")


def _now():
    return datetime.now(timezone.utc).isoformat()


# ----- talking to supabase --------------------------------------------------------------------------------
def _request(method, path, body=None, token=None, headers=None):
    request = urllib.request.Request(SUPABASE_URL.rstrip("/") + path, method=method,
                                     data=None if body is None else json.dumps(body).encode("utf-8"))
    request.add_header("apikey", SUPABASE_KEY)
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", f"GublanStudio/{version.VERSION}")
    if token:
        request.add_header("Authorization", "Bearer " + token)
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read()
    except urllib.error.HTTPError as err:
        detail = ""
        try:
            info = json.loads(err.read() or b"{}")
            detail = info.get("msg") or info.get("message") or info.get("error_description") or info.get("error") or ""
        except (ValueError, AttributeError, OSError):
            pass
        raise AccountError(f"{detail or err.reason} ({err.code})", err.code) from err
    except (OSError, ValueError) as err:
        raise AccountError(f"couldn't reach the gublan account server: {err}") from err
    try:
        return json.loads(raw) if raw.strip() else None
    except ValueError as err:
        raise AccountError("the gublan account server sent something unexpected") from err


# ----- links and the files that go with a program ---------------------------------------------------------
def _base64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def share_link(files, current):
    """the playground's own share link: one program is "#z=", a program with other files is "#p=" (json of
    {files: [{name, text}], current}). both are raw deflate in url-safe base64, so the playground reads them as
    if its share button had made them. files is a list of (name, text)."""
    files = [(str(name), str(text)) for name, text in files]
    if not files:
        raise ValueError("there's nothing to share")
    many = len(files) > 1 or not files[0][0].lower().endswith(".gubl")
    if many:
        body = json.dumps({"files": [{"name": name, "text": text} for name, text in files], "current": current},
                          ensure_ascii=False, separators=(",", ":"))
    else:
        body = files[0][1]
    packer = zlib.compressobj(9, zlib.DEFLATED, -15)
    data = packer.compress(body.encode("utf-8")) + packer.flush()
    return PLAYGROUND + "#" + ("p=" if many else "z=") + _base64url(data)


def read_share_link(link):
    """the other way round: (files, current) from a playground link, or None if it isn't one."""
    match = re.search(r"#([zp])=([\w-]+)$", str(link).strip())
    if not match:
        return None
    raw = match.group(2)
    try:
        data = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        text = zlib.decompress(data, -15).decode("utf-8")
        if match.group(1) == "z":
            return [("shared.gubl", text)], "shared.gubl"
        found = json.loads(text)
        files = [(str(item["name"]), str(item["text"])) for item in found.get("files", [])
                 if isinstance(item, dict) and "name" in item and "text" in item]
    except (ValueError, zlib.error, UnicodeDecodeError, AttributeError, TypeError):
        return None
    return (files, str(found.get("current") or files[0][0])) if files else None


def creation_link(creation_id):
    return PLAYGROUND + "?c=" + urllib.parse.quote(str(creation_id), safe="")


def is_data_file(name):
    return str(name).lower().endswith(DATA_ENDINGS)


def uses_3d(files):
    return any(not is_data_file(name) and re.search(r"^\s*mode\s+3d\b", text, re.M) for name, text in files)


_INCLUDE = re.compile(r"^\s*include\s+(.+?)\s*$", re.M)
_DATA_NAME = re.compile(r"[\w.-]+\.(?:" + "|".join(ending[1:] for ending in DATA_ENDINGS) + r")\b", re.I)


def program_files(path, text):
    """what a program needs on gublan.xyz, as [(name, text)]: the program first, then the .gubl files it includes
    and the text files it names (level.txt, scores.csv...) when they sit next to it. the website keeps files in one
    flat list, so only the file names travel, not folders. pictures and sounds stay behind."""
    folder = os.path.dirname(os.path.abspath(path)) if path else None
    main = os.path.basename(path) if path else "program.gubl"
    if not main.lower().endswith(".gubl"):
        main += ".gubl"
    found = [(main, text)]
    seen = {main.lower()}
    if not folder:
        return found
    waiting = [text]
    while waiting:
        source = waiting.pop()
        names = [name.strip().strip("\"'") for name in _INCLUDE.findall(source)]
        names = [name if name.lower().endswith(".gubl") else name + ".gubl" for name in names if name]
        names += [name.strip("\"'") for name in _DATA_NAME.findall(source)]
        for name in names:
            where = os.path.join(folder, name)
            short = os.path.basename(name)
            if short.lower() in seen or not os.path.isfile(where):
                continue
            try:
                with open(where, "r", encoding="utf-8") as handle:
                    content = handle.read()
            except (OSError, UnicodeDecodeError):
                continue
            seen.add(short.lower())
            found.append((short, content))
            if short.lower().endswith(".gubl"):
                waiting.append(content)
    return found


def pkce_pair():
    """a random secret (the verifier) and its sha-256 (the challenge), both base64url without padding."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return verifier, challenge


def authorize_url(challenge, redirect):
    query = urllib.parse.urlencode({"provider": "discord", "redirect_to": redirect, "code_challenge": challenge,
                                    "code_challenge_method": "s256"})
    return f"{SUPABASE_URL.rstrip('/')}/auth/v1/authorize?{query}"


def _session(data):
    if not isinstance(data, dict) or not data.get("access_token") or not data.get("refresh_token"):
        raise AccountError("the gublan account server didn't send a session")
    expires_at = data.get("expires_at") or int(time.time()) + int(data.get("expires_in") or 3600)
    return {"access_token": data["access_token"], "refresh_token": data["refresh_token"],
            "expires_at": int(expires_at), "user": data.get("user") or {}}


# ----- the page the browser lands on after discord ----------------------------------------------------------
_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Gublan Studio</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#141414;color:#e5e5e5;
font:16px/1.5 "Segoe UI",system-ui,sans-serif}}
main{{max-width:420px;padding:32px;text-align:center}}
h1{{font-size:22px;margin:0 0 8px;color:{colour}}}p{{margin:0;color:#aaa}}
</style></head><body><main><h1>{title}</h1><p>{text}</p></main>{script}</body></html>"""

# supabase reports some problems after a #, which never reaches this server: send them back as a query
_FRAGMENT_SCRIPT = ("<script>if(location.hash.length>1&&!location.search)"
                    "location.replace(location.pathname+'?'+location.hash.slice(1))</script>")


def _escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - the name http.server wants
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != CALLBACK_PATH:
            self.send_error(404)
            return
        query = urllib.parse.parse_qs(parsed.query)
        code = (query.get("code") or [""])[0]
        error = (query.get("error_description") or query.get("error") or [""])[0]
        if code and not error:
            page = _PAGE.format(colour="#94b66c", title="You're signed in",
                                text="Go back to Gublan Studio. You can close this tab.", script="")
        elif error:
            page = _PAGE.format(colour="#e16b6b", title="Sign-in didn't work", text=_escape(error), script="")
        else:
            page = _PAGE.format(colour="#e5e5e5", title="Finishing sign-in…", text="One moment.",
                                script=_FRAGMENT_SCRIPT)
        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        if (code or error) and self.server.result is None:
            self.server.result = {"code": code, "error": error}
            self.server.finished.set()

    def log_message(self, *_args):
        pass


class _CallbackServer(http.server.HTTPServer):
    allow_reuse_address = False

    def __init__(self):
        super().__init__(("127.0.0.1", CALLBACK_PORT), _CallbackHandler)
        self.result = None
        self.finished = threading.Event()


_waiting = None  # the callback server of a sign-in that is still waiting for the browser
_waiting_lock = threading.Lock()


def cancel_sign_in():
    with _waiting_lock:
        server = _waiting
    if server is not None and server.result is None:
        server.result = {"code": "", "error": "sign-in was cancelled"}
        server.finished.set()


def sign_in(open_browser=webbrowser.open, timeout=SIGN_IN_TIMEOUT):
    """open the browser at discord's sign-in, wait for it to come back, and give back the new session.
    blocks for as long as the person takes, so call it from a background thread."""
    global _waiting
    if not configured():
        raise AccountError("accounts aren't set up in this copy of gublan studio")
    cancel_sign_in()  # a second click starts over instead of fighting the first one for the port
    verifier, challenge = pkce_pair()
    server = None
    for _attempt in range(10):
        try:
            server = _CallbackServer()
            break
        except OSError:
            time.sleep(0.1)  # the cancelled sign-in may still be letting go of the port
    if server is None:
        raise AccountError(f"port {CALLBACK_PORT} on this computer is busy, so sign-in can't finish. "
                           "close whatever is using it, then try again.")
    with _waiting_lock:
        _waiting = server
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
    worker.start()
    try:
        if not open_browser(authorize_url(challenge, callback_url())):
            raise AccountError("couldn't open a web browser for signing in")
        if not server.finished.wait(timeout):
            raise AccountError("sign-in took too long. try again when you're ready.")
    finally:
        with _waiting_lock:
            if _waiting is server:
                _waiting = None
        server.shutdown()
        server.server_close()
    if server.result["error"]:
        raise AccountError(server.result["error"])
    return _session(_request("POST", "/auth/v1/token?grant_type=pkce",
                             {"auth_code": server.result["code"], "code_verifier": verifier}))


# ----- settings sync ----------------------------------------------------------------------------------------
def syncable(settings):
    """the settings that follow the person: everything except what belongs to this computer."""
    return {key: value for key, value in settings.items() if key in config.DEFAULTS and key not in LOCAL_ONLY}


def clean(stored):
    """settings from the cloud that this version of the studio understands, the way config.load checks them."""
    cleaned = {}
    if not isinstance(stored, dict):
        return cleaned
    for key, value in stored.items():
        if key not in config.DEFAULTS or key in LOCAL_ONLY:
            continue
        default = config.DEFAULTS[key]
        if isinstance(default, bool):
            if isinstance(value, bool):
                cleaned[key] = value
        elif isinstance(default, int):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cleaned[key] = int(value)
        elif isinstance(value, type(default)):
            cleaned[key] = value
    return cleaned


def merge(local, cloud, synced):
    """bring this computer's settings and the cloud's together.

    synced is what both agreed on at the last sync (None if this computer never synced). the first time, the cloud
    wins, so signing in on a new computer brings your settings with you. after that, a setting changed here since
    the last sync keeps this computer's value and every other setting takes the cloud's."""
    if synced is None:
        merged = dict(local)
        merged.update(cloud)
        return merged
    merged = dict(local)
    for key, value in cloud.items():
        if key not in synced or local.get(key) == synced.get(key):
            merged[key] = value
    return merged


class Account:
    """the signed-in person, if any, kept in account.json next to settings.json. safe to use from several threads."""

    def __init__(self, path=None):
        self.path = path or account_path()
        self.lock = threading.RLock()  # guards self.state; never held during network calls
        self.refreshing = threading.Lock()  # one session refresh at a time
        self.state = self._read()

    def _read(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                state = json.load(handle)
            if isinstance(state, dict):
                return state
        except (OSError, ValueError):
            pass
        return {}

    def _write(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            temporary = self.path + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(self.state, handle, indent=2)
            os.replace(temporary, self.path)
        except OSError:
            pass

    # who is signed in
    @property
    def signed_in(self):
        with self.lock:
            return bool(self.state.get("session"))

    def user(self):
        """{"id", "name", "avatar"} for the signed-in person, or None."""
        with self.lock:
            session = self.state.get("session") or {}
        found = session.get("user") or {}
        if not found.get("id"):
            return None
        meta = found.get("user_metadata") or {}
        claims = meta.get("custom_claims") or {}
        name = claims.get("global_name") or meta.get("full_name") or meta.get("name") or meta.get("user_name") or "you"
        return {"id": found["id"], "name": str(name), "avatar": str(meta.get("avatar_url") or "")}

    def set_session(self, session):
        with self.lock:
            before = ((self.state.get("session") or {}).get("user") or {}).get("id")
            after = (session.get("user") or {}).get("id")
            if before != after:
                self.state.pop("synced", None)  # someone else's account: nothing has been synced with it yet
            self.state["session"] = session
            self._write()

    def forget(self):
        with self.lock:
            self.state = {}
            self._write()

    def _current(self):
        with self.lock:
            session = self.state.get("session")
        if not session:
            raise AccountError("not signed in")
        return session

    def token(self):
        """a working access token, refreshing the session first when it is about to run out. the network part
        happens outside self.lock, so the tk thread never waits on it."""
        session = self._current()
        if session.get("expires_at", 0) - REFRESH_EARLY > time.time():
            return session["access_token"]
        with self.refreshing:
            session = self._current()  # another thread may have just refreshed it
            if session.get("expires_at", 0) - REFRESH_EARLY > time.time():
                return session["access_token"]
            try:
                fresh = _session(_request("POST", "/auth/v1/token?grant_type=refresh_token",
                                          {"refresh_token": session["refresh_token"]}))
            except AccountError as err:
                if err.status in (400, 401, 403):
                    self.forget()  # the session was revoked or expired for good: sign in again
                    raise AccountError("you were signed out. sign in again to keep syncing.", err.status) from err
                raise
            if not fresh["user"]:
                fresh["user"] = session.get("user") or {}
            with self.lock:
                if self.state.get("session") is session:  # not signed out meanwhile
                    self.state["session"] = fresh
                    self._write()
            return fresh["access_token"]

    def sign_out(self):
        try:
            _request("POST", "/auth/v1/logout?scope=local", token=self.token())
        except AccountError:
            pass  # signing out here works even when the server can't be reached
        self.forget()

    # the user_data row
    def _user_id(self):
        found = self.user()
        if not found:
            raise AccountError("not signed in")
        return found["id"]

    def load_row(self):
        rows = _request("GET", f"/rest/v1/user_data?select=settings,updated_at&user_id=eq.{self._user_id()}",
                        token=self.token())
        return rows[0] if isinstance(rows, list) and rows else None

    def save_settings(self, everything):
        _request("POST", "/rest/v1/user_data?on_conflict=user_id",
                 {"user_id": self._user_id(), "settings": everything, "updated_at": _now()}, token=self.token(),
                 headers={"Prefer": "resolution=merge-duplicates,return=minimal"})

    def delete_data(self):
        _request("DELETE", f"/rest/v1/user_data?user_id=eq.{self._user_id()}", token=self.token())
        with self.lock:
            self.state.pop("synced", None)
            self._write()

    # published creations (gublan.xyz/explore)
    def published(self, path):
        """what this program was published as, by the person signed in now: {"id", "title", "about"} or None."""
        user = self.user()
        key = os.path.normcase(os.path.abspath(path)) if path else None
        with self.lock:
            found = (self.state.get("published") or {}).get(key) if key else None
        if not found or not user or found.get("user") != user["id"]:
            return None
        return found

    def _remember(self, path, saved):
        if not path:
            return
        key = os.path.normcase(os.path.abspath(path))
        with self.lock:
            published = dict(self.state.get("published") or {})
            if saved is None:
                published.pop(key, None)
            else:
                published[key] = saved
            self.state["published"] = published
            self._write()

    def publish(self, path, title, about, files, main, creation_id=None):
        """blocking: publish files ([(name, text)]) to gublan.xyz, or update creation_id. gives back the saved row."""
        user_id = self._user_id()
        title = str(title or "").strip()[:80]
        if not title:
            raise AccountError("give it a name first")
        size = sum(len(text) for _name, text in files)
        if size > MAX_PUBLISH:
            raise AccountError(f"that's {size:,} characters. creations can be up to {MAX_PUBLISH:,}.")
        fields = {"title": title, "about": str(about or "").strip()[:1000], "files": dict(files), "main": main,
                  "uses_3d": bool(uses_3d(files))}
        listed = "id,title,about,author,uses_3d,user_id,created_at,updated_at,main"
        prefer = {"Prefer": "return=representation"}
        if creation_id:
            clean = re.sub(r"[^\w-]", "", str(creation_id))
            rows = _request("PATCH", f"/rest/v1/creations?id=eq.{clean}&select={listed}", fields, token=self.token(),
                            headers=prefer)
            if not rows:
                raise AccountError("that creation isn't yours any more, or it was taken down")
        else:
            rows = _request("POST", f"/rest/v1/creations?select={listed}", fields, token=self.token(), headers=prefer)
            if not rows:
                raise AccountError("the server didn't say what it saved")
        saved = rows[0]
        self._remember(path, {"id": saved["id"], "user": user_id, "title": saved.get("title", title),
                              "about": saved.get("about", "")})
        return saved

    def unpublish(self, path, creation_id):
        clean = re.sub(r"[^\w-]", "", str(creation_id))
        _request("DELETE", f"/rest/v1/creations?id=eq.{clean}&user_id=eq.{self._user_id()}", token=self.token())
        self._remember(path, None)

    def needs_sync(self, settings):
        with self.lock:
            return self.signed_in and syncable(settings) != self.state.get("synced")

    def sync(self, settings):
        """blocking: bring settings and the cloud copy together. gives back the settings the studio should use now
        (a new dict; computer-only settings are untouched)."""
        local = syncable(settings)
        row = self.load_row()
        everything = (row or {}).get("settings")
        everything = dict(everything) if isinstance(everything, dict) else {}
        cloud = clean(everything.get("studio"))
        with self.lock:
            synced = self.state.get("synced")
        merged = merge(local, cloud, synced) if cloud else local
        if row is None or merged != cloud:
            everything["studio"] = merged
            self.save_settings(everything)
        with self.lock:
            self.state["synced"] = merged
            self._write()
        result = dict(settings)
        result.update(merged)
        return result
