"""gublan studio and windows explorer: one studio window at a time, and .gubl files that open (or run) in it.

one window: the first studio listens on 127.0.0.1 at a random port, and writes the port and a random token to
instance.json in the settings folder. opening a .gubl file (or "run with gublan") while that studio is open hands the
file to it instead of starting a second studio. if the studio crashed, instance.json is stale: nothing answers on
that port, so the new studio starts normally and takes over.

explorer: the installer (GublanStudio.iss) registers .gubl files. register() does the same for this windows user from
inside the studio, for the portable exe or a copy run from source: double-click opens a file in the studio, the right
click menu gets "run with gublan", and new > gublan program makes an empty one.

nothing here touches tk. InstanceServer calls on_open from its own thread, so the studio passes a function that
hands the paths to the tk thread.
"""

import hmac
import json
import os
import secrets
import socket
import sys
import threading

from . import config

INSTANCE_FILE = "instance.json"
PROG_ID = "GublanStudio.gubl"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIMIT = 256 * 1024  # bytes in one message: plenty of paths


def instance_path():
    return os.path.join(config.settings_folder(), INSTANCE_FILE)


def _read_instance():
    try:
        with open(instance_path(), "r", encoding="utf-8") as handle:
            info = json.load(handle)
        return int(info["port"]), str(info["token"]), int(info.get("pid") or 0)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def forward(paths, run=False, timeout=2.0):
    """hand paths to the studio that's already open. True when it took them (then this process can quit)."""
    found = _read_instance()
    if not found or not paths:
        return False
    port, token, _pid = found
    message = json.dumps({"token": token, "open": [os.path.abspath(path) for path in paths], "run": bool(run)})
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as connection:
            connection.settimeout(timeout)
            connection.sendall(message.encode("utf-8") + b"\n")
            return connection.recv(16).startswith(b"ok")
    except OSError:
        return False


class InstanceServer:
    """listens for files sent by forward(). on_open(paths, run) runs on this server's thread."""

    def __init__(self, on_open):
        self.on_open = on_open
        self.token = secrets.token_hex(16)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(4)
        self.port = self.socket.getsockname()[1]
        self.closed = False
        try:
            os.makedirs(os.path.dirname(instance_path()), exist_ok=True)
            temporary = instance_path() + f".{os.getpid()}.tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump({"port": self.port, "token": self.token, "pid": os.getpid()}, handle)
            os.replace(temporary, instance_path())
        except OSError:
            pass  # still works as a normal studio; files just won't be forwarded to it
        threading.Thread(target=self._serve, name="gublan-instance", daemon=True).start()

    def _serve(self):
        while not self.closed:
            try:
                connection, _address = self.socket.accept()
            except OSError:
                return
            try:
                self._answer(connection)
            except (OSError, ValueError):
                pass
            finally:
                connection.close()

    def _answer(self, connection):
        connection.settimeout(2.0)
        data = b""
        while not data.endswith(b"\n") and len(data) < _LIMIT:
            chunk = connection.recv(4096)
            if not chunk:
                break
            data += chunk
        message = json.loads(data.decode("utf-8"))
        if not isinstance(message, dict) or not hmac.compare_digest(str(message.get("token", "")), self.token):
            return
        paths = [path for path in message.get("open", []) if isinstance(path, str)]
        self.on_open(paths, bool(message.get("run")))
        connection.sendall(b"ok\n")

    def close(self):
        self.closed = True
        try:
            self.socket.close()
        except OSError:
            pass
        found = _read_instance()
        if found and found[2] == os.getpid():
            try:
                os.remove(instance_path())
            except OSError:
                pass


# ----- explorer -----------------------------------------------------------------------------------------------
def launcher():
    """how explorer should start this studio: the exe itself, or pythonw with gublanide.py when run from source."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    folder = os.path.dirname(sys.executable)
    windowless = os.path.join(folder, "pythonw.exe")
    return [windowless if os.path.isfile(windowless) else sys.executable, os.path.join(ROOT, "gublanide.py")]


def _icon():
    if getattr(sys, "frozen", False):
        return f"{sys.executable},0"
    return os.path.join(ROOT, "logo.ico")


def _command(extra=""):
    quoted = " ".join(f'"{part}"' for part in launcher())
    return f'{quoted} {extra}"%1"'.replace("  ", " ")


def _entries():
    """(subkey under HKCU\\Software\\Classes, value name, value) for everything register() writes."""
    return [
        (".gubl", "", PROG_ID),
        (".gubl", "Content Type", "text/plain"),
        (".gubl", "PerceivedType", "text"),
        (".gubl\\OpenWithProgids", PROG_ID, ""),
        (".gubl\\ShellNew", "NullFile", ""),
        (PROG_ID, "", "gublan program"),
        (PROG_ID + "\\DefaultIcon", "", _icon()),
        (PROG_ID + "\\shell", "", "open"),
        (PROG_ID + "\\shell\\open", "", "open in gublan studio"),
        (PROG_ID + "\\shell\\open\\command", "", _command()),
        (PROG_ID + "\\shell\\run", "", "run with gublan"),
        (PROG_ID + "\\shell\\run", "Icon", _icon()),
        (PROG_ID + "\\shell\\run\\command", "", _command("--run ")),
    ]


def _refresh_explorer():
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED
    except (AttributeError, OSError):
        pass


def registered():
    """True when .gubl files open in a gublan studio for this user (the installer's, or one register() set up)."""
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{PROG_ID}\\shell\\open\\command") as key:
            return bool(winreg.QueryValueEx(key, "")[0])
    except OSError:
        return False


def register():
    """set .gubl files up in explorer for this windows user. raises OSError if the registry says no."""
    if sys.platform != "win32":
        raise OSError("this only works on windows")
    import winreg
    for subkey, name, value in _entries():
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{subkey}", 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    _refresh_explorer()


def _delete_tree(root, path):
    import winreg
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(root, f"{path}\\{child}")
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        pass


def unregister():
    """undo register() (and the installer's file type) for this windows user. other programs' settings stay."""
    if sys.platform != "win32":
        return
    import winreg
    _delete_tree(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{PROG_ID}")
    _delete_tree(winreg.HKEY_CURRENT_USER, "Software\\Classes\\.gubl\\ShellNew")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software\\Classes\\.gubl\\OpenWithProgids", 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, PROG_ID)
    except OSError:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software\\Classes\\.gubl", 0,
                            winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            if winreg.QueryValueEx(key, "")[0] == PROG_ID:
                winreg.DeleteValue(key, "")
    except OSError:
        pass
    _refresh_explorer()
