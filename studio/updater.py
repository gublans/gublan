"""Check GitHub Releases and install a downloaded Gublan Studio setup package.

the installer runs silently once gublan studio has closed, then opens the new version. it is started with a clean
environment: gublan studio is a pyinstaller onefile program, and a copy of it started from a process that still
carries the old copy's _PYI_* variables would unpack nothing and run the old files, which made updated installs
look like they were still on the previous version.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from collections import namedtuple
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

REPOSITORY = "gublans/gublan"
INSTALLER_NAME = "GublanStudioSetup.exe"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases"
VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+)*)$")
MAX_INSTALLER_SIZE = 500 * 1024 * 1024
MAX_NOTES = 1500

Release = namedtuple("Release", "tag url notes page")


def _version_key(value):
    match = VERSION_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"release version {value!r} must contain numeric dot-separated parts")
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(latest, current):
    latest_parts = _version_key(latest)
    current_parts = _version_key(current)
    length = max(len(latest_parts), len(current_parts))
    return latest_parts + (0,) * (length - len(latest_parts)) > \
        current_parts + (0,) * (length - len(current_parts))


_is_newer = is_newer


def same_version(first, second):
    try:
        return not is_newer(first, second) and not is_newer(second, first)
    except ValueError:
        return False


def _notes(text):
    text = (text or "").replace("\r\n", "\n").strip()
    if len(text) > MAX_NOTES:
        text = text[:MAX_NOTES].rsplit("\n", 1)[0].rstrip() + "\n..."
    return text


def latest_release_from_payload(payload, current_version):
    if not isinstance(payload, dict):
        raise ValueError("GitHub returned invalid release data")
    tag = payload.get("tag_name")
    if not isinstance(tag, str):
        raise ValueError("GitHub release data is missing its version tag")
    if not is_newer(tag, current_version):
        return None

    assets = payload.get("assets", [])
    if not isinstance(assets, list):
        raise ValueError(f"release {tag} has invalid asset data")
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError(f"release {tag} has invalid asset data")
        if asset.get("name") != INSTALLER_NAME:
            continue
        url = asset.get("browser_download_url")
        parsed = urlparse(url or "")
        if parsed.scheme != "https" or parsed.hostname != "github.com":
            raise ValueError("the release installer must be hosted on github.com over HTTPS")
        page = payload.get("html_url")
        if not (isinstance(page, str) and urlparse(page).scheme == "https"
                and urlparse(page).hostname == "github.com"):
            page = RELEASES_PAGE
        body = payload.get("body")
        return Release(tag, url, _notes(body if isinstance(body, str) else ""), page)
    raise ValueError(f"release {tag} is missing {INSTALLER_NAME}")


def latest_release(current_version):
    request = Request(
        f"https://api.github.com/repos/{REPOSITORY}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "GublanStudio-Updater"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise
    return latest_release_from_payload(payload, current_version)


def install_folder():
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return ""
    return os.path.join(local_app_data, "Programs", "Gublan Studio")


def is_installed_application():
    if not getattr(sys, "frozen", False):
        return False
    folder = install_folder()
    if not folder:
        return False
    executable = os.path.normcase(os.path.realpath(sys.executable))
    install_dir = os.path.normcase(os.path.realpath(folder))
    try:
        return os.path.commonpath((executable, install_dir)) == install_dir
    except ValueError:
        return False


def download_installer(url, progress=None):
    """download the setup file to a temporary path. progress(done_bytes, total_bytes_or_0) is called as it goes."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise ValueError("the installer download URL must be hosted on github.com over HTTPS")

    request = Request(url, headers={"User-Agent": "GublanStudio-Updater"})
    descriptor, path = tempfile.mkstemp(prefix="GublanStudioSetup-", suffix=".exe")
    try:
        total = 0
        with os.fdopen(descriptor, "wb") as output, urlopen(request, timeout=30) as response:
            final_url = urlparse(response.geturl())
            if final_url.scheme != "https" or not (
                final_url.hostname == "github.com"
                or (final_url.hostname or "").endswith(".githubusercontent.com")
            ):
                raise ValueError("GitHub redirected the installer download to an unexpected host")
            try:
                expected = int(response.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                expected = 0
            if expected > MAX_INSTALLER_SIZE:
                raise ValueError("the downloaded installer is larger than 500 MB")
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_INSTALLER_SIZE:
                    raise ValueError("the downloaded installer is larger than 500 MB")
                output.write(chunk)
                if progress is not None:
                    progress(total, expected)
        if total == 0:
            raise ValueError("GitHub returned an empty installer")
        if expected and total != expected:
            raise ValueError("the installer download was cut short. try again")
        with open(path, "rb") as handle:
            if handle.read(2) != b"MZ":
                raise ValueError("the downloaded file is not a windows program")
        return path
    except (OSError, ValueError):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        raise


def remove_download(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


# ----- running the installer ------------------------------------------------------------------------------------
def installer_environment(environ=None, bundle=None):
    """the environment for the setup program and the new gublan studio it opens, without this copy's leftovers."""
    environ = dict(os.environ if environ is None else environ)
    bundle = os.path.normcase(os.path.realpath(bundle or getattr(sys, "_MEIPASS", "") or "")) \
        if (bundle or getattr(sys, "_MEIPASS", "")) else ""
    clean = {}
    for key, value in environ.items():
        upper = key.upper()
        if upper.startswith("_PYI_") or upper.startswith("_MEIPASS") or upper == "PYINSTALLER_RESET_ENVIRONMENT":
            continue
        if bundle and upper in ("TCL_LIBRARY", "TK_LIBRARY", "TCLLIBPATH", "PYTHONHOME", "PYTHONPATH",
                                "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE"):
            if os.path.normcase(os.path.realpath(value or ".")).startswith(bundle):
                continue
        clean[key] = value
    if bundle:
        # pyinstaller puts its unpack folder at the front of PATH; the new copy unpacks its own
        parts = [part for part in clean.get("PATH", "").split(os.pathsep)
                 if part and not os.path.normcase(os.path.realpath(part)).startswith(bundle)]
        if "PATH" in clean:
            clean["PATH"] = os.pathsep.join(parts)
    clean["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return clean


def _process_image(pid):
    if sys.platform != "win32":
        return ""
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def processes_to_wait_for():
    """this process, plus the pyinstaller launcher that started it (it holds GublanStudio.exe open too)."""
    pids = [os.getpid()]
    parent = os.getppid() if hasattr(os, "getppid") else 0
    if parent and getattr(sys, "frozen", False):
        try:
            same = os.path.normcase(os.path.realpath(_process_image(parent))) == \
                os.path.normcase(os.path.realpath(sys.executable))
        except (OSError, ValueError):
            same = False
        if same:
            pids.append(parent)
    return pids


def update_log_path():
    from .config import settings_folder
    return os.path.join(settings_folder(), "update.log")


def installer_arguments(pids=(), relaunch=True, log=None):
    arguments = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/SP-"]
    pids = [str(int(pid)) for pid in pids if int(pid) > 0]
    if pids:
        arguments.append("/WAITPID=" + ",".join(pids))
    if relaunch:
        arguments.append("/RELAUNCH=1")
    if log:
        arguments.append(f"/LOG={log}")
    return arguments


def launch_installer(path, relaunch=True):
    """start the setup program. it waits for gublan studio to close, installs silently, then (when relaunch is on)
    opens the new version."""
    log = update_log_path()
    try:
        os.makedirs(os.path.dirname(log), exist_ok=True)
    except OSError:
        log = None
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    return subprocess.Popen([path] + installer_arguments(processes_to_wait_for(), relaunch, log),
                            env=installer_environment(), cwd=os.path.dirname(os.path.abspath(path)),
                            close_fds=True, creationflags=flags)


def read_update_log(limit=40):
    """the end of the installer's log from the last update, to show when an update didn't finish."""
    try:
        with open(update_log_path(), "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-limit:])


def remove_old_downloads():
    """delete setup files left in the temp folder by earlier updates (a running installer can't delete itself)."""
    folder = tempfile.gettempdir()
    try:
        names = os.listdir(folder)
    except OSError:
        return
    for name in names:
        if name.startswith("GublanStudioSetup-") and name.endswith(".exe"):
            try:
                os.unlink(os.path.join(folder, name))
            except OSError:
                pass
