"""live sessions: code together with people on your local network.

one person hosts. the programs they have open are shared, and everyone who joins (with a name and the session
code) gets them as tabs. everyone types at once; each edit is a replace [start, end, text] on the file's text.

how edits stay in step:
  - the host's copy is the real one. the host puts every edit in order and numbers it (seq).
  - a guest sends one edit at a time with the seq it was made on (base), and keeps typing meanwhile.
  - when the host gets an edit made on an older seq, it shifts it past the edits that came in between
    (transform) and sends it to everyone. the guest who made it treats that as "got it" and sends the next one.
  - edits from others are shifted past the guest's own unconfirmed edits before they are applied.
  - every edit carries a checksum of the host's text. a guest with nothing unconfirmed whose text doesn't match
    asks for a fresh copy, so a rare mix-up never lasts.

messages are json, one per line, over tcp.
"""

import hmac
import json
import queue
import secrets
import socket
import threading
import zlib

PROTOCOL = "gublan-live/1"
DEFAULT_PORT = 47800
MAX_LINE = 8 * 1024 * 1024
MAX_PEOPLE = 16
MAX_HISTORY = 4000
MAX_NAME = 24
CODE_LETTERS = "abcdefghjkmnpqrstuvwxyz23456789"
COLORS = ("#e0a050", "#6fb3e0", "#d77fb3", "#9fd36f", "#e07070", "#b39ae0", "#5fd0c0", "#e0d060")


# ----- edits ------------------------------------------------------------------------------------------------
def make_op(old, new):
    """the single replace [start, end, text] that turns old into new, or None when they are the same."""
    if old == new:
        return None
    start = 0
    limit = min(len(old), len(new))
    while start < limit and old[start] == new[start]:
        start += 1
    end_old, end_new = len(old), len(new)
    while end_old > start and end_new > start and old[end_old - 1] == new[end_new - 1]:
        end_old -= 1
        end_new -= 1
    return [start, end_old, new[start:end_new]]


def valid_op(op, length=None):
    if not (isinstance(op, list) and len(op) == 3 and isinstance(op[0], int) and isinstance(op[1], int)
            and isinstance(op[2], str) and not isinstance(op[0], bool) and not isinstance(op[1], bool)):
        return False
    return 0 <= op[0] <= op[1] and (length is None or op[1] <= length)


def apply_op(text, op):
    start, end, insert = op
    if not 0 <= start <= end <= len(text):
        raise ValueError("that edit is outside the file")
    return text[:start] + insert + text[end:]


def transform(op, other, op_first):
    """op and other were both made on the same text. give op changed so it can be applied after other.

    the rules, so both orders end with the same text:
      - an edit whose replaced range holds the other edit wins: the inner edit's text goes too
      - two edits on exactly the same range both keep their text, op_first's text first
      - edits that only partly overlap both keep their text; the overlap is deleted once
      - two people typing at the same spot: op_first's text goes first
    """
    start, end, insert = op
    other_start, other_end, other_text = other
    grow = len(other_text) - (other_end - other_start)
    nothing = [other_start, other_start, ""]
    if start < end and other_start < other_end:
        if (start, end) == (other_start, other_end):
            spot = other_start if op_first else other_start + len(other_text)
            return [spot, spot, insert]
        if start <= other_start and other_end <= end:
            return [start, end + grow, insert]  # op holds other: other's new text is replaced too
        if other_start <= start and end <= other_end:
            return nothing  # other holds op: op is gone
    elif start < end:  # other only types, at other_start
        if start < other_start < end:
            return [start, end + len(other_text), insert]
    elif other_start < other_end:  # op only types
        if other_start < start < other_end:
            return nothing
    elif start == other_start:  # both only type, at the same spot
        spot = start if op_first else start + len(other_text)
        return [spot, spot, insert]

    def place(position, is_end):
        if position < other_start or (position == other_start and (is_end or other_start < other_end)):
            return position
        if position > other_end or (position == other_end and other_start < other_end) or \
                (position == other_start == other_end):
            return position + grow
        # strictly inside the part other replaced: that text is gone, so land beside other's new text
        return other_start if is_end else other_start + len(other_text)

    new_start = place(start, False)
    new_end = new_start if start == end else place(end, True)
    return [new_start, max(new_start, new_end), insert]


def shift_position(position, op):
    """where a cursor at position ends up after op."""
    start, end, insert = op
    if position <= start:
        return position
    if position >= end:
        return position + len(insert) - (end - start)
    return start + len(insert)


def checksum(text):
    return zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF


def clean_name(name):
    name = " ".join(str(name or "").split()).lower()
    return name[:MAX_NAME]


def new_code():
    return "".join(secrets.choice(CODE_LETTERS) for _ in range(6))


def local_addresses():
    """this computer's addresses on the local network (what guests type in)."""
    found = []
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("10.255.255.255", 1))  # no packet is sent; this only picks the outgoing interface
            found.append(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    try:
        for address in socket.gethostbyname_ex(socket.gethostname())[2]:
            if address not in found:
                found.append(address)
    except OSError:
        pass
    found = [address for address in found if not address.startswith("127.")]
    return found or ["127.0.0.1"]


# ----- the wire ----------------------------------------------------------------------------------------------
class Connection:
    """one tcp connection: a thread reads lines into the inbox, another writes the outbox."""

    def __init__(self, sock, inbox, key):
        self.sock = sock
        self.inbox = inbox
        self.key = key
        self.outbox = queue.Queue()
        self.closed = False
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._write, daemon=True).start()

    def send(self, message):
        if not self.closed:
            self.outbox.put(message)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.outbox.put(None)
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def _read(self):
        try:
            reader = self.sock.makefile("rb")
            while True:
                line = reader.readline(MAX_LINE + 1)
                if not line or len(line) > MAX_LINE:
                    break
                try:
                    message = json.loads(line.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    break
                if isinstance(message, dict):
                    self.inbox.put((self.key, message))
        except OSError:
            pass
        self.inbox.put((self.key, {"type": "_closed"}))

    def _write(self):
        while True:
            message = self.outbox.get()
            if message is None:
                return
            try:
                self.sock.sendall((json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8"))
            except OSError:
                self.inbox.put((self.key, {"type": "_closed"}))
                return


# ----- shared state for one file -----------------------------------------------------------------------------
class SharedFile:
    def __init__(self, file_id, name, text, seq=0):
        self.id = file_id
        self.name = name
        self.shadow = text  # the text as this side last saw it (the editor matches it after each flush)
        self.seq = seq
        self.first_seq = seq  # host: history[0] is the edit numbered first_seq + 1
        self.history = []  # host: every edit in order
        self.pending = None  # guest: sent, not yet confirmed
        self.buffer = []  # guest: typed while waiting
        self.doc = None


# ----- the session ------------------------------------------------------------------------------------------
class LiveSession:
    """a host or guest session tied to the studio. everything except the network threads runs on the tk thread.

    the studio side is reached through a small adapter (app):
        app.root, app.docs, app.live_open(name, text) -> doc, app.live_message(text, kind),
        app.live_changed(), doc.editor (get(), live_apply(op_start, op_end, text), show_peers(list))
    """

    def __init__(self, app, name, host=True):
        self.app = app
        self.name = clean_name(name)
        self.is_host = host
        self.inbox = queue.Queue()
        self.files = {}
        self.people = {}  # id -> {"name", "color", "file", "pos"}
        self.me = "host" if host else None
        self.code = ""
        self.port = DEFAULT_PORT
        self.server = None
        self.connections = {}  # host: id -> Connection
        self.link = None  # guest: the Connection to the host
        self.counter = 0
        self.active = True
        self.poll_job = None
        self.on_end = None
        self.host_name = "the host"

    # ----- starting -----------------------------------------------------------------------------------------
    def start_host(self, port=DEFAULT_PORT, code=None):
        self.code = code or new_code()
        self.port = int(port)
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            server.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)  # windows: nobody else on the port
        else:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("", self.port))
        except OSError:
            server.close()
            raise
        server.listen(8)
        self.server = server
        self.people["host"] = {"name": self.name, "color": COLORS[0], "file": None, "pos": 0}
        for doc in list(self.app.docs):
            self.share(doc)
        threading.Thread(target=self._accept, daemon=True).start()
        self._schedule()

    def start_guest(self, address, port, code, timeout=6.0):
        """connect (call this off the tk thread; it can take a few seconds)."""
        sock = socket.create_connection((address, int(port)), timeout=timeout)
        sock.settimeout(None)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.code = code
        self.port = int(port)
        self.link = Connection(sock, self.inbox, "host")
        self.link.send({"type": "hello", "protocol": PROTOCOL, "name": self.name, "code": code})

    def begin_polling(self):
        self._schedule()

    def _schedule(self):
        if self.active:
            self.poll_job = self.app.root.after(30, self._poll)

    def _accept(self):
        while self.active:
            try:
                sock, _address = self.server.accept()
            except OSError:
                return
            self.counter += 1
            key = f"p{self.counter}"
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.connections[key] = Connection(sock, self.inbox, key)

    # ----- the tk side loop ---------------------------------------------------------------------------------
    def _poll(self):
        self.poll_job = None
        handled = 0
        while handled < 200:
            try:
                key, message = self.inbox.get_nowait()
            except queue.Empty:
                break
            handled += 1
            try:
                if self.is_host:
                    self._host_message(key, message)
                else:
                    self._guest_message(message)
            except (KeyError, TypeError, ValueError) as err:
                if self.is_host and key in self.connections:
                    self._drop(key, f"sent something odd ({err})")
            if not self.active:
                return
        self._schedule()

    # ----- local edits (both sides) -------------------------------------------------------------------------
    def watch(self, shared):
        editor = shared.doc.editor
        editor.collab_listener = lambda s=shared: self.flush(s)
        editor.collab_cursor = lambda s=shared: self.cursor_moved(s)

    def unwatch(self, shared):
        if shared.doc is not None:
            shared.doc.editor.collab_listener = None
            shared.doc.editor.collab_cursor = None
            try:
                shared.doc.editor.show_peers([])
            except Exception:  # noqa: BLE001 - the tab may already be gone
                pass
        shared.doc = None

    def flush(self, shared):
        """turn whatever was typed since the last flush into an edit."""
        if shared.doc is None or not self.active:
            return
        text = shared.doc.editor.get()
        op = make_op(shared.shadow, text)
        if op is None:
            return
        shared.shadow = text
        for person in self.people.values():
            if person.get("file") == shared.id:
                person["pos"] = shift_position(person.get("pos", 0), op)
        if self.is_host:
            self._host_commit(shared, op, "host")
        elif shared.pending is None:
            shared.pending = op
            self.link.send({"type": "edit", "file": shared.id, "base": shared.seq, "op": op})
        else:
            shared.buffer.append(op)
        self._draw_peers(shared)

    def cursor_moved(self, shared):
        if shared.doc is None or not self.active:
            return
        self.flush(shared)
        editor = shared.doc.editor
        try:
            position = len(editor.text.get("1.0", "insert"))
        except Exception:  # noqa: BLE001
            return
        message = {"type": "cursor", "file": shared.id, "pos": position}
        if self.me in self.people:
            self.people[self.me]["file"], self.people[self.me]["pos"] = shared.id, position
        if self.is_host:
            me = self.people["host"]
            me["file"], me["pos"] = shared.id, position
            self._broadcast(dict(message, by="host"))
        else:
            self.link.send(message)

    def _apply(self, shared, op):
        """put someone else's edit into the editor."""
        shared.shadow = apply_op(shared.shadow, op)
        if shared.doc is not None:
            shared.doc.editor.live_apply(op[0], op[1], op[2])
        for person in self.people.values():
            if person.get("file") == shared.id:
                person["pos"] = shift_position(person.get("pos", 0), op)

    def _draw_peers(self, shared):
        if shared.doc is None:
            return
        marks = [(key, person["name"], person["color"], person.get("pos", 0))
                 for key, person in self.people.items()
                 if key != self.me and person.get("file") == shared.id]
        try:
            shared.doc.editor.show_peers(marks)
        except Exception:  # noqa: BLE001 - drawing must never break the session
            pass

    def _draw_all_peers(self):
        for shared in self.files.values():
            self._draw_peers(shared)
        self.app.live_changed()

    # ----- host -------------------------------------------------------------------------------------------
    def share(self, doc):
        if not self.is_host or any(shared.doc is doc for shared in self.files.values()):
            return
        self.counter += 1
        file_id = f"f{self.counter}"
        shared = SharedFile(file_id, doc.name, doc.editor.get())
        shared.doc = doc
        self.files[file_id] = shared
        self.watch(shared)
        self._broadcast({"type": "file", "file": file_id, "name": shared.name, "text": shared.shadow, "seq": 0})

    def unshare(self, doc):
        for file_id, shared in list(self.files.items()):
            if shared.doc is doc:
                self.unwatch(shared)
                if self.is_host:
                    del self.files[file_id]
                    self._broadcast({"type": "closed", "file": file_id})

    def _broadcast(self, message, skip=None):
        for key, connection in list(self.connections.items()):
            if key != skip and key in self.people:
                connection.send(message)

    def _host_commit(self, shared, op, author):
        shared.seq += 1
        shared.history.append(op)
        if len(shared.history) > MAX_HISTORY:
            drop = len(shared.history) - MAX_HISTORY
            del shared.history[:drop]
            shared.first_seq += drop
        self._broadcast({"type": "edit", "file": shared.id, "seq": shared.seq, "op": op, "by": author,
                         "sum": checksum(shared.shadow)})

    def _people_list(self):
        return [{"id": key, "name": person["name"], "color": person["color"], "file": person.get("file"),
                 "pos": person.get("pos", 0)} for key, person in self.people.items()]

    def _host_message(self, key, message):
        kind = message.get("type")
        connection = self.connections.get(key)
        if kind == "_closed":
            if key in self.people:
                name = self.people.pop(key)["name"]
                self.app.live_message(f"{name} left the session")
                self._broadcast({"type": "people", "people": self._people_list(), "left": name})
                self._draw_all_peers()
            if connection:
                connection.close()
            self.connections.pop(key, None)
            return
        if connection is None:
            return
        if key not in self.people:
            if kind != "hello":
                return self._drop(key, "said something before hello")
            if message.get("protocol") != PROTOCOL:
                return self._refuse(key, "that gublan studio is a different version. update both to the same one.")
            if not hmac.compare_digest(str(message.get("code", "")).strip().lower(), self.code):
                return self._refuse(key, "the session code is wrong")
            name = clean_name(message.get("name"))
            if not name:
                return self._refuse(key, "you need a name to join")
            if len(self.people) >= MAX_PEOPLE:
                return self._refuse(key, f"the session is full ({MAX_PEOPLE} people)")
            taken = {person["name"] for person in self.people.values()}
            base, number = name, 2
            while name in taken:
                name = f"{base[:MAX_NAME - 3]} {number}"
                number += 1
            color = COLORS[len(self.people) % len(COLORS)]
            self.people[key] = {"name": name, "color": color, "file": None, "pos": 0}
            for shared in self.files.values():
                self.flush(shared)
            connection.send({"type": "welcome", "you": key, "name": name, "host": self.name,
                             "people": self._people_list(),
                             "files": [{"file": shared.id, "name": shared.name, "text": shared.shadow,
                                        "seq": shared.seq} for shared in self.files.values()]})
            self._broadcast({"type": "people", "people": self._people_list(), "joined": name}, skip=key)
            self.app.live_message(f"{name} joined the session")
            self._draw_all_peers()
            return
        person = self.people[key]
        if kind == "edit":
            shared = self.files.get(message.get("file"))
            if shared is None:
                return
            base, op = message.get("base"), message.get("op")
            if not isinstance(base, int) or not valid_op(op):
                raise ValueError("a broken edit")
            self.flush(shared)
            if base < shared.first_seq or base > shared.seq:
                connection.send({"type": "file", "file": shared.id, "name": shared.name, "text": shared.shadow,
                                 "seq": shared.seq})
                return
            for earlier in shared.history[base - shared.first_seq:]:
                op = transform(op, earlier, False)
            if op[1] > len(shared.shadow):
                connection.send({"type": "file", "file": shared.id, "name": shared.name, "text": shared.shadow,
                                 "seq": shared.seq})
                return
            self._apply(shared, op)
            self._host_commit(shared, op, key)
            self._draw_peers(shared)
        elif kind == "cursor":
            shared = self.files.get(message.get("file"))
            position = message.get("pos")
            if shared is None or not isinstance(position, int):
                return
            person["file"], person["pos"] = shared.id, max(0, min(position, len(shared.shadow)))
            self._broadcast({"type": "cursor", "file": shared.id, "pos": person["pos"], "by": key}, skip=key)
            self._draw_peers(shared)
            self.app.live_changed()
        elif kind == "sync":
            shared = self.files.get(message.get("file"))
            if shared is not None:
                self.flush(shared)
                connection.send({"type": "file", "file": shared.id, "name": shared.name, "text": shared.shadow,
                                 "seq": shared.seq})
        elif kind == "chat":
            text = str(message.get("text", ""))[:500]
            if text.strip():
                self._broadcast({"type": "chat", "from": person["name"], "text": text}, skip=key)
                self.app.live_message(f"{person['name']}: {text}", "chat")

    def _refuse(self, key, reason):
        connection = self.connections.get(key)
        if connection:
            connection.send({"type": "refused", "reason": reason})
            self.app.root.after(400, connection.close)
        self.connections.pop(key, None)

    def _drop(self, key, reason):
        connection = self.connections.pop(key, None)
        if connection:
            connection.close()
        if key in self.people:
            name = self.people.pop(key)["name"]
            self.app.live_message(f"{name} was disconnected: {reason}", "warning")
            self._broadcast({"type": "people", "people": self._people_list(), "left": name})
            self._draw_all_peers()

    # ----- guest ------------------------------------------------------------------------------------------
    def _guest_message(self, message):
        kind = message.get("type")
        if kind == "_closed":
            self.end("the session ended" if self.me else "could not join the session")
            return
        if kind == "refused":
            self.end(f"could not join: {message.get('reason', 'the host said no')}")
            return
        if kind == "welcome":
            self.me = message["you"]
            self.name = message.get("name", self.name)
            self.host_name = message.get("host", "the host")
            self._set_people(message.get("people", []))
            for item in message.get("files", []):
                self._guest_file(item)
            self.app.live_message(f"you joined {self.host_name}'s session as {self.name}")
            self._draw_all_peers()
            return
        if self.me is None:
            return
        if kind == "file":
            self._guest_file(message)
        elif kind == "closed":
            shared = self.files.pop(message.get("file"), None)
            if shared is not None:
                if shared.doc is not None:
                    self.app.live_message(f"{self.host_name} closed {shared.name}; your copy stays open")
                self.unwatch(shared)
        elif kind == "edit":
            shared = self.files.get(message.get("file"))
            if shared is None or shared.doc is None:
                return
            seq, op = message["seq"], message["op"]
            if not isinstance(seq, int) or not valid_op(op) or seq <= shared.seq:
                return
            self.flush(shared)
            if message.get("by") == self.me and shared.pending is not None:
                shared.pending = None
                shared.seq = seq
                if shared.buffer:
                    shared.pending = shared.buffer.pop(0)
                    self.link.send({"type": "edit", "file": shared.id, "base": shared.seq, "op": shared.pending})
            else:
                remote = op
                if shared.pending is not None:
                    remote, shared.pending = transform(remote, shared.pending, True), transform(
                        shared.pending, remote, False)
                moved = []
                for mine in shared.buffer:
                    remote, mine = transform(remote, mine, True), transform(mine, remote, False)
                    moved.append(mine)
                shared.buffer = moved
                if remote[1] > len(shared.shadow):
                    self.link.send({"type": "sync", "file": shared.id})
                    return
                self._apply(shared, remote)
                shared.seq = seq
            if shared.pending is None and not shared.buffer and "sum" in message and \
                    checksum(shared.shadow) != message["sum"]:
                self.link.send({"type": "sync", "file": shared.id})
            self._draw_peers(shared)
        elif kind == "cursor":
            person = self.people.get(message.get("by"))
            shared = self.files.get(message.get("file"))
            if person is not None and shared is not None and isinstance(message.get("pos"), int):
                person["file"], person["pos"] = shared.id, message["pos"]
                self._draw_all_peers()
        elif kind == "people":
            self._set_people(message.get("people", []))
            if message.get("joined"):
                self.app.live_message(f"{message['joined']} joined the session")
            if message.get("left"):
                self.app.live_message(f"{message['left']} left the session")
            self._draw_all_peers()
        elif kind == "chat":
            self.app.live_message(f"{message.get('from', '?')}: {str(message.get('text', ''))[:500]}", "chat")

    def _set_people(self, people):
        self.people = {item["id"]: {"name": item["name"], "color": item["color"], "file": item.get("file"),
                                    "pos": item.get("pos", 0)} for item in people if isinstance(item, dict)}

    def _guest_file(self, item):
        file_id, text = item["file"], item["text"]
        shared = self.files.get(file_id)
        if shared is not None and shared.doc is not None:
            shared.shadow = text
            shared.seq = item.get("seq", 0)
            shared.pending, shared.buffer = None, []
            shared.doc.editor.live_replace_all(text)
            return
        shared = SharedFile(file_id, item.get("name", "shared"), text, item.get("seq", 0))
        shared.doc = self.app.live_open(f"{shared.name} (live)", text)
        self.files[file_id] = shared
        self.watch(shared)

    def doc_closed(self, doc):
        """a tab was closed on this computer."""
        if self.is_host:
            self.unshare(doc)
        else:
            for shared in self.files.values():
                if shared.doc is doc:
                    self.unwatch(shared)

    def doc_opened(self, doc):
        if self.is_host:
            self.share(doc)

    # ----- both -------------------------------------------------------------------------------------------
    def say(self, text):
        text = str(text).strip()[:500]
        if not text:
            return
        if self.is_host:
            self._broadcast({"type": "chat", "from": self.name, "text": text})
        elif self.link:
            self.link.send({"type": "chat", "text": text})

    def describe_people(self):
        """[(name, color, where)] for the people list."""
        rows = []
        for key, person in self.people.items():
            shared = self.files.get(person.get("file"))
            where = ""
            if shared is not None:
                line = shared.shadow.count("\n", 0, min(person.get("pos", 0), len(shared.shadow))) + 1
                where = f"{shared.name}, line {line}"
            label = person["name"] + (" (you)" if key == self.me else " (host)" if key == "host" else "")
            rows.append((label, person["color"], where))
        return rows

    def end(self, reason=None):
        if not self.active:
            return
        self.active = False
        if self.poll_job is not None:
            try:
                self.app.root.after_cancel(self.poll_job)
            except Exception:  # noqa: BLE001
                pass
        for shared in self.files.values():
            self.unwatch(shared)
        if self.is_host:
            for connection in self.connections.values():
                connection.send({"type": "refused", "reason": "the host ended the session"})
                connection.close()
            if self.server is not None:
                try:
                    self.server.close()
                except OSError:
                    pass
        elif self.link is not None:
            self.link.close()
        if reason:
            self.app.live_message(reason)
        if self.on_end:
            self.on_end()
