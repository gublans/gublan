"""discord rich presence over discord's local ipc pipe, using only the python standard library.

the discord desktop app listens on a named pipe (windows) or a unix socket (macos and linux). a program says
hello with its discord application id, then sends SET_ACTIVITY commands. PresenceClient keeps that connection
on a background thread so callers never wait on discord: they hand over the newest activity and the worker
sends it when it can, at most once every few seconds (discord allows 5 updates every 20 seconds).

    client = PresenceClient()
    client.update({"details": "editing game.gubl", "state": "line 4 of 30"})
    ...
    client.close()

gublan studio uses this for its own status, and the gublan `presence` command uses it so games can show theirs.
"""

import json
import os
import socket
import struct
import sys
import threading
import time
import uuid

DEFAULT_APPLICATION_ID = "1574014510690205746"
DEFAULT_IMAGE = "https://raw.githubusercontent.com/gublans/gublan/main/logo.png"

OP_HANDSHAKE, OP_FRAME, OP_CLOSE, OP_PING, OP_PONG = 0, 1, 2, 3, 4
MIN_INTERVAL = 4.0      # seconds between two activity updates
RETRY_INTERVAL = 15.0   # seconds between attempts to reach the discord app
ANSWER_TIMEOUT = 5.0    # seconds to wait for discord to answer a command
MAX_FRAME = 1024 * 1024

ACTIVITY_TYPES = {"playing": 0, "listening": 2, "watching": 3, "competing": 5}
_TEXT_FIELDS = ("details", "state")
_ASSET_FIELDS = ("large_image", "large_text", "small_image", "small_text")
_PAD = "\u2800"  # an invisible character: discord refuses texts shorter than two characters


class PresenceError(Exception):
    """discord refused the connection, for example because the application id is wrong."""


def valid_application_id(value):
    text = str(value or "").strip()
    return text.isdigit() and 15 <= len(text) <= 22


def _text(value, limit=128):
    text = " ".join(str(value).split()) if value is not None else ""
    if not text:
        return ""
    text = text[:limit]
    return text + _PAD if len(text) < 2 else text


def _url(value):
    text = str(value or "").strip()
    return text if text.lower().startswith(("https://", "http://")) and len(text) <= 512 and " " not in text \
        else ""


def clean_activity(activity):
    """trim an activity to what discord accepts. returns None when nothing is left to show."""
    if not activity:
        return None
    result = {}
    for key in _TEXT_FIELDS:
        text = _text(activity.get(key))
        if text:
            result[key] = text
    assets = {}
    raw_assets = activity.get("assets") or {}
    for key in _ASSET_FIELDS:
        value = raw_assets.get(key)
        if value:
            text = str(value).strip()
            assets[key] = text[:512] if key.endswith("image") else _text(text)
    for image, label in (("large_image", "large_text"), ("small_image", "small_text")):
        if label in assets and image not in assets:
            del assets[label]
    if assets:
        result["assets"] = assets
    timestamps = {}
    for key in ("start", "end"):
        value = (activity.get("timestamps") or {}).get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            timestamps[key] = int(value)
    if timestamps:
        result["timestamps"] = timestamps
    party = activity.get("party") or {}
    size = party.get("size")
    if isinstance(size, (list, tuple)) and len(size) == 2:
        try:
            current, most = int(size[0]), int(size[1])
        except (TypeError, ValueError):
            current = most = 0
        if 1 <= current <= most:
            result["party"] = {"id": str(party.get("id") or "gublan"), "size": [current, most]}
    buttons = []
    for button in activity.get("buttons") or []:
        label = _text((button or {}).get("label"), 32)
        url = _url((button or {}).get("url"))
        if label and url:
            buttons.append({"label": label, "url": url})
    if buttons:
        result["buttons"] = buttons[:2]
    kind = activity.get("type")
    if kind in ACTIVITY_TYPES.values() and kind != 0:
        result["type"] = kind
    return result or None


# ----- talking to the discord app ------------------------------------------------------------------------------
def _ipc_paths():
    if sys.platform == "win32":
        return [rf"\\.\pipe\discord-ipc-{number}" for number in range(10)]
    base = next((os.environ[key] for key in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP") if os.environ.get(key)),
                "/tmp")
    folders = [base, os.path.join(base, "app", "com.discordapp.Discord"), os.path.join(base, "snap.discord"),
               os.path.join(base, ".flatpak", "com.discordapp.Discord", "xdg-run")]
    return [os.path.join(folder, f"discord-ipc-{number}") for number in range(10) for folder in folders]


_peek = None


def _pipe_available(stream):
    """bytes waiting in a windows pipe, so reads can time out instead of blocking forever."""
    global _peek
    import ctypes
    import msvcrt
    from ctypes import wintypes
    if _peek is None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _peek = kernel32.PeekNamedPipe
        _peek.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, wintypes.LPDWORD, wintypes.LPDWORD,
                          wintypes.LPDWORD]
        _peek.restype = wintypes.BOOL
    available = wintypes.DWORD(0)
    if not _peek(msvcrt.get_osfhandle(stream.fileno()), None, 0, None, ctypes.byref(available), None):
        raise OSError("discord closed the connection")
    return available.value


class Connection:
    """one open pipe or socket to the discord app."""

    def __init__(self, stream=None, sock=None):
        self._stream = stream
        self._sock = sock

    @classmethod
    def open(cls):
        for path in _ipc_paths():
            try:
                if sys.platform == "win32":
                    return cls(stream=open(path, "r+b", buffering=0))
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    sock.settimeout(ANSWER_TIMEOUT)
                    sock.connect(path)
                except OSError:
                    sock.close()
                    raise
                return cls(sock=sock)
            except OSError:
                continue
        raise OSError("the discord app is not running")

    def send(self, op, payload):
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        frame = struct.pack("<II", op, len(data)) + data
        if self._sock is not None:
            self._sock.sendall(frame)
            return
        view = memoryview(frame)
        while view:
            written = self._stream.write(view)
            if not written:
                raise OSError("discord closed the connection")
            view = view[written:]

    def receive(self, timeout=ANSWER_TIMEOUT):
        deadline = time.monotonic() + timeout
        op, length = struct.unpack("<II", self._read(8, deadline))
        if length > MAX_FRAME:
            raise OSError("discord sent a message that is too large")
        body = self._read(length, deadline) if length else b""
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except ValueError:
            data = {}
        return op, data if isinstance(data, dict) else {}

    def alive(self):
        try:
            if self._stream is not None:
                _pipe_available(self._stream)
                return True
            self._sock.setblocking(False)
            try:
                return self._sock.recv(1, socket.MSG_PEEK) != b""
            except BlockingIOError:
                return True
            finally:
                self._sock.settimeout(ANSWER_TIMEOUT)
        except OSError:
            return False

    def _read(self, count, deadline):
        data = b""
        while len(data) < count:
            if self._stream is not None:
                available = _pipe_available(self._stream)
                if not available:
                    if time.monotonic() > deadline:
                        raise TimeoutError("discord did not answer")
                    time.sleep(0.02)
                    continue
                chunk = self._stream.read(min(available, count - len(data)))
            else:
                self._sock.settimeout(max(0.05, deadline - time.monotonic()))
                chunk = self._sock.recv(count - len(data))
            if not chunk:
                raise OSError("discord closed the connection")
            data += chunk
        return data

    def close(self):
        for thing in (self._stream, self._sock):
            if thing is not None:
                try:
                    thing.close()
                except OSError:
                    pass


def _answer(connection, nonce=None, timeout=ANSWER_TIMEOUT):
    """the next frame from discord (answering pings on the way), or the one with this nonce."""
    deadline = time.monotonic() + timeout
    while True:
        op, data = connection.receive(max(0.05, deadline - time.monotonic()))
        if op == OP_PING:
            connection.send(OP_PONG, data)
            continue
        if op == OP_CLOSE:
            raise PresenceError(str(data.get("message") or "discord closed the connection").lower())
        if nonce is None or data.get("nonce") == nonce:
            return data
        if time.monotonic() > deadline:
            raise TimeoutError("discord did not answer")


def handshake(connection, application_id):
    """say hello. returns the discord user's name when discord sends it."""
    connection.send(OP_HANDSHAKE, {"v": 1, "client_id": str(application_id)})
    data = _answer(connection)
    if data.get("evt") == "ERROR":
        raise PresenceError(str((data.get("data") or {}).get("message") or "discord refused the connection"))
    user = (data.get("data") or {}).get("user") or {}
    return user.get("global_name") or user.get("username") or ""


def set_activity(connection, activity, pid=None):
    """send one activity (None clears it). returns discord's error message, or "" when it was accepted."""
    nonce = uuid.uuid4().hex
    connection.send(OP_FRAME, {"cmd": "SET_ACTIVITY", "args": {"pid": pid or os.getpid(), "activity": activity},
                               "nonce": nonce})
    data = _answer(connection, nonce)
    if data.get("evt") == "ERROR":
        return str((data.get("data") or {}).get("message") or "discord did not accept the status")
    return ""


# ----- the client ------------------------------------------------------------------------------------------------
_UNSENT = object()


class PresenceClient:
    """keeps a discord status up to date from a background thread.

    status is a (state, text) pair the caller can show: state is "off", "connecting", "connected", "waiting"
    (discord isn't running yet) or "error".
    """

    def __init__(self, application_id=DEFAULT_APPLICATION_ID, connector=None, interval=MIN_INTERVAL,
                 retry=RETRY_INTERVAL, pid=None):
        self.application_id = str(application_id or DEFAULT_APPLICATION_ID)
        self.connector = connector or Connection.open
        self.interval = interval
        self.retry = retry
        self.pid = pid
        self.status = ("off", "not connected yet")
        self.user = ""
        self.sent = None
        self._cond = threading.Condition()
        self._wanted = None
        self._closing = False
        self._thread = None

    # ----- called from any thread ---------------------------------------------------------------------------
    def update(self, activity):
        cleaned = clean_activity(activity)
        with self._cond:
            if self._closing:
                return
            self._wanted = cleaned
            if self._thread is None and cleaned is not None:
                self._thread = threading.Thread(target=self._run, name="discord presence", daemon=True)
                self._thread.start()
            self._cond.notify_all()

    def clear(self):
        self.update(None)

    def set_application(self, application_id):
        application_id = str(application_id or DEFAULT_APPLICATION_ID)
        with self._cond:
            if application_id != self.application_id:
                self.application_id = application_id
                self._cond.notify_all()

    def close(self, timeout=1.5):
        """clear the status and stop. waits a moment so discord hears about it before the program exits."""
        with self._cond:
            self._closing = True
            self._cond.notify_all()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
        self.status = ("off", "stopped")

    @property
    def connected(self):
        return self.status[0] == "connected"

    # ----- the worker -----------------------------------------------------------------------------------------
    def _sleep(self, seconds):
        with self._cond:
            if not self._closing:
                self._cond.wait(max(0.0, seconds))

    def _run(self):
        connection, connected_to, sent = None, None, _UNSENT
        last_send, next_attempt = -self.interval, 0.0
        try:
            while True:
                with self._cond:
                    closing, wanted, app_id = self._closing, self._wanted, self.application_id
                    idle = connection is not None and connected_to == app_id and sent == wanted
                    if not closing and (idle or (connection is None and wanted is None)):
                        self._cond.wait(15)
                        if connection is not None and not self._closing and not connection.alive():
                            connection.close()
                            connection, sent = None, _UNSENT
                            self.status = ("waiting", "discord closed. trying again soon")
                        continue
                if closing:
                    return
                now = time.monotonic()
                if connection is not None and connected_to != app_id:
                    self._goodbye(connection)
                    connection, sent = None, _UNSENT
                if connection is None:
                    if now < next_attempt:
                        self._sleep(next_attempt - now)
                        continue
                    self.status = ("connecting", "looking for the discord app")
                    try:
                        connection = self.connector()
                        self.user = handshake(connection, app_id)
                    except PresenceError as err:
                        if connection is not None:
                            connection.close()
                        connection = None
                        next_attempt = time.monotonic() + self.retry * 4
                        self.status = ("error", f"discord refused application {app_id}: {err}")
                        continue
                    except (OSError, ValueError) as err:
                        if connection is not None:
                            connection.close()
                        connection = None
                        next_attempt = time.monotonic() + self.retry
                        self.status = ("waiting", str(err).lower() or "the discord app is not running")
                        continue
                    connected_to, sent = app_id, None
                    self.status = ("connected", f"connected as {self.user}" if self.user else "connected")
                wait = self.interval - (time.monotonic() - last_send)
                if wait > 0:
                    self._sleep(wait)
                    continue
                try:
                    error, note = self._send(connection, wanted)
                except (OSError, ValueError, PresenceError) as err:
                    connection.close()
                    connection, sent = None, _UNSENT
                    next_attempt = time.monotonic() + 1.0
                    self.status = ("waiting", str(err).lower() or "lost the connection to discord")
                    continue
                last_send, sent = time.monotonic(), wanted
                if error:
                    self.status = ("error", error.lower())
                else:
                    who = f" as {self.user}" if self.user else ""
                    text = f"showing your status{who}" if wanted else f"connected{who}"
                    self.status = ("connected", f"{text} ({note})" if note else text)
        finally:
            if connection is not None:
                self._goodbye(connection)
            with self._cond:
                self._thread = None

    def _send(self, connection, wanted):
        """send an activity. when discord refuses it, try again without the kind of activity, then without the
        pictures, so the words still show. returns (error, note about what was left out)."""
        error = set_activity(connection, wanted, self.pid)
        if not error:
            self.sent = wanted
            return "", ""
        for leave_out, what in ((("type",), "the activity kind, so it is"),
                                (("type", "assets"), "the pictures, so they are")):
            if not wanted or not any(key in wanted for key in leave_out):
                continue
            simpler = {key: value for key, value in wanted.items() if key not in leave_out}
            if not set_activity(connection, simpler, self.pid):
                self.sent = simpler
                return "", f"discord didn't accept {what} left out"
        self.sent = None
        return error, ""

    def _goodbye(self, connection):
        try:
            set_activity(connection, None, self.pid)
        except (OSError, ValueError, PresenceError):
            pass
        connection.close()
        self.sent = None
