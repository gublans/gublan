"""keep gublan studio standing.

tkinter is not thread safe. two things used to take the whole studio down without a message:

* worker threads (checking code, running tests, exporting, the mcp test...) called ``widget.after`` to hand
  their results back. tcl only allows that from the thread that made the window, and every so often it
  crashed instead of complaining.
* python's garbage collector runs in whatever thread happens to allocate. when it ran in a worker thread
  it freed tk variables, pictures and fonts from that thread ("main thread is not in main loop"), which
  can crash tcl too.

so the studio turns automatic garbage collection off and collects on the tk thread instead, and worker
threads hand work back with ``call_soon`` (a plain queue that the tk thread empties). hard crashes are
written to crash.log, and unsaved programs are copied to a recovery folder so a crash never loses work.
"""

import faulthandler
import gc
import json
import os
import queue
import sys
import threading
import time
import traceback

_calls = queue.SimpleQueue()
_state = {"root": None, "crash_file": None, "on_error": None, "ticks": 0}
PUMP_MS = 15
COLLECT_MS = 500


def settings_folder():
    from . import config
    return config.settings_folder()


def _path(name):
    return os.path.join(settings_folder(), name)


# ----- the process ------------------------------------------------------------------------------------------
def prepare_process():
    """call first thing when the studio starts.

    the one-file exe unpacks itself into a temporary _MEI folder and deletes it when it closes. a copy of the
    studio started from inside (restarting for a new theme, the mcp self test, an exported game) used to reuse
    that folder and crash once it was deleted. this makes every child unpack its own copy.
    """
    if getattr(sys, "frozen", False):
        os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"


def clean_environment():
    """the environment for starting another copy of the studio (or anything pyinstaller made)."""
    from . import updater
    return updater.installer_environment()


# ----- the tk side -------------------------------------------------------------------------------------------
def install(root, on_error=None):
    """take over garbage collection and start emptying the call queue. call once, on the tk thread."""
    _state["root"] = root
    _state["on_error"] = on_error
    _start_crash_log()
    threading.excepthook = _thread_error
    gc.disable()
    root.after(PUMP_MS, _pump)
    root.after(COLLECT_MS, _collect)


def installed():
    return _state["root"] is not None


def call_soon(func, *args):
    """run func(*args) on the tk thread as soon as it is free. safe to call from any thread."""
    if not installed():
        # nothing is pumping the queue (tests, the command line): just call it
        func(*args)
        return
    _calls.put((func, args))


def _pump():
    root = _state["root"]
    if root is None:
        return
    started = time.perf_counter()
    while time.perf_counter() - started < 0.05:
        try:
            func, args = _calls.get_nowait()
        except queue.Empty:
            break
        try:
            func(*args)
        except Exception:  # noqa: BLE001 - one bad callback must not stop the rest
            _report(*sys.exc_info())
    try:
        root.after(PUMP_MS, _pump)
    except Exception:  # noqa: BLE001 - the window is closing
        _state["root"] = None


def _collect():
    """the garbage collector, run on the tk thread: young objects often, everything now and then."""
    root = _state["root"]
    if root is None:
        return
    _state["ticks"] += 1
    ticks = _state["ticks"]
    try:
        if ticks % 120 == 0:
            gc.collect()
        elif ticks % 12 == 0:
            gc.collect(1)
        elif gc.get_count()[0] > 400:
            gc.collect(0)
    except Exception:  # noqa: BLE001
        pass
    try:
        root.after(COLLECT_MS, _collect)
    except Exception:  # noqa: BLE001
        _state["root"] = None


def uninstall():
    """put things back (when the studio closes, or after a test)."""
    _state["root"] = None
    gc.enable()
    while True:
        try:
            _calls.get_nowait()
        except queue.Empty:
            break
    _stop_crash_log()


def _report(kind, value, trace):
    handler = _state["on_error"]
    if handler is not None:
        try:
            handler(kind, value, trace)
            return
        except Exception:  # noqa: BLE001
            pass
    log_error("".join(traceback.format_exception(kind, value, trace)))


def _thread_error(args):
    if args.exc_type is SystemExit:
        return
    details = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    name = getattr(args.thread, "name", "a thread")
    log_error(f"in {name}:\n{details}")


# ----- logs ----------------------------------------------------------------------------------------------------
def log_error(details):
    """add a problem to errors.log in the settings folder (and the console, when there is one)."""
    try:
        os.makedirs(settings_folder(), exist_ok=True)
        path = _path("errors.log")
        if os.path.exists(path) and os.path.getsize(path) > 512 * 1024:
            os.replace(path, path + ".old")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(time.strftime("%Y-%m-%d %H:%M:%S ") + details.rstrip() + "\n\n")
    except OSError:
        pass
    if sys.stderr is not None:
        try:
            sys.stderr.write(details)
        except (OSError, ValueError):
            pass


def _start_crash_log():
    """a hard crash (inside tcl or sdl) skips python's error handling. faulthandler still writes where it was."""
    try:
        os.makedirs(settings_folder(), exist_ok=True)
        path = _path("crash.log")
        if os.path.exists(path) and os.path.getsize(path) > 256 * 1024:
            os.replace(path, path + ".old")
        handle = open(path, "a", encoding="utf-8")  # noqa: SIM115 - stays open for faulthandler
        handle.write(f"--- gublan studio started {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        handle.flush()
        faulthandler.enable(file=handle, all_threads=True)
        _state["crash_file"] = handle
    except (OSError, RuntimeError, ValueError):
        pass


def _stop_crash_log():
    handle = _state.pop("crash_file", None)
    _state["crash_file"] = None
    if handle is not None:
        try:
            faulthandler.disable()
            handle.close()
        except (OSError, ValueError):
            pass


# ----- did the studio crash last time? --------------------------------------------------------------------------
def mark_running():
    """leave a note that the studio is open. a clean exit removes it, so finding it at start-up means a crash.

    returns True when the note from the last session was still there.
    """
    path = _path("running")
    crashed = False
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                pid = handle.read().strip()
            crashed = not (pid.isdigit() and int(pid) != os.getpid() and _process_alive(int(pid)))
        os.makedirs(settings_folder(), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
    except OSError:
        pass
    return crashed


def mark_closed():
    try:
        os.remove(_path("running"))
    except OSError:
        pass


def _process_alive(pid):
    """is another studio with this process id still open? (two studios at once is fine, not a crash)"""
    if sys.platform == "win32":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # query limited information
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == 259  # still active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


# ----- unsaved work -----------------------------------------------------------------------------------------------
def recovery_folder():
    return _path("recovery")


def save_recovery(items):
    """items: [{"name", "path", "text"}] for every program with unsaved changes. replaces the last copy."""
    folder = recovery_folder()
    try:
        os.makedirs(folder, exist_ok=True)
        keep = set()
        for number, item in enumerate(items):
            name = f"{number}.json"
            keep.add(name)
            target = os.path.join(folder, name)
            temporary = target + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump({"name": item.get("name"), "path": item.get("path"), "text": item.get("text", ""),
                           "saved": time.time()}, handle)
            os.replace(temporary, target)
        for name in os.listdir(folder):
            if name not in keep:
                try:
                    os.remove(os.path.join(folder, name))
                except OSError:
                    pass
    except OSError:
        pass


def load_recovery():
    folder = recovery_folder()
    items = []
    try:
        names = sorted(os.listdir(folder), key=lambda n: (len(n), n))
    except OSError:
        return items
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, name), "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("text"), str):
            items.append(data)
    return items


def clear_recovery():
    save_recovery([])


def last_crash(limit=6000):
    """the end of crash.log (what faulthandler wrote), or '' when the last session left nothing there."""
    try:
        with open(_path("crash.log"), "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return ""
    sessions = text.split("--- gublan studio started ")
    # the newest entry is this session's header; the one before it is the session that crashed
    if len(sessions) < 3:
        return ""
    previous = sessions[-2]
    body = previous.split("---\n", 1)[1] if "---\n" in previous else ""
    return body.strip()[-limit:]
