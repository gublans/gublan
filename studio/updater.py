"""Check GitHub Releases and install a downloaded Gublan Studio setup package."""

import json
import os
import re
import subprocess
import sys
import tempfile
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

REPOSITORY = "gublans/gublan"
INSTALLER_NAME = "GublanStudioSetup.exe"
VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+)*)$")
MAX_INSTALLER_SIZE = 500 * 1024 * 1024


def _version_key(value):
    match = VERSION_RE.fullmatch(value)
    if not match:
        raise ValueError(f"release version {value!r} must contain numeric dot-separated parts")
    return tuple(int(part) for part in match.group(1).split("."))


def _is_newer(latest, current):
    latest_parts = _version_key(latest)
    current_parts = _version_key(current)
    length = max(len(latest_parts), len(current_parts))
    return latest_parts + (0,) * (length - len(latest_parts)) > \
        current_parts + (0,) * (length - len(current_parts))


def latest_release_from_payload(payload, current_version):
    if not isinstance(payload, dict):
        raise ValueError("GitHub returned invalid release data")
    tag = payload.get("tag_name")
    if not isinstance(tag, str):
        raise ValueError("GitHub release data is missing its version tag")
    if not _is_newer(tag, current_version):
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
        return tag, url
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


def is_installed_application():
    if not getattr(sys, "frozen", False):
        return False
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return False
    executable = os.path.normcase(os.path.realpath(sys.executable))
    install_dir = os.path.normcase(os.path.realpath(
        os.path.join(local_app_data, "Programs", "Gublan Studio")))
    try:
        return os.path.commonpath((executable, install_dir)) == install_dir
    except ValueError:
        return False


def download_installer(url):
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
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_INSTALLER_SIZE:
                    raise ValueError("the downloaded installer is larger than 500 MB")
                output.write(chunk)
        if total == 0:
            raise ValueError("GitHub returned an empty installer")
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


def launch_installer(path):
    return subprocess.Popen([path])
