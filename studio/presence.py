"""gublan studio's own discord status: what you're working on, built from the discord settings.

build_activity turns the settings and a snapshot of the studio into a discord activity, without touching tk or
discord, so it is easy to test. StudioPresence owns the background PresenceClient (see gublanpresence.py) and is
told by the app whenever something worth showing changes.
"""

import os
import re
import time

from gublanpresence import (ACTIVITY_TYPES, DEFAULT_APPLICATION_ID, DEFAULT_IMAGE, PresenceClient, clean_activity,
                            valid_application_id)

from . import version

PLACEHOLDERS = {
    "action": "editing, running, paused in or looking at",
    "file": "the file name, like game.gubl",
    "name": "the file name without .gubl",
    "folder": "the folder the file is in",
    "line": "the line the cursor is on",
    "lines": "how many lines the file has",
    "column": "the column the cursor is on",
    "view": "code, blocks or code and blocks",
    "level": "beginner, standard or expert",
    "problems": "how many problems the file has",
    "version": "the gublan studio version",
}
HIDDEN_FILE = "a program"
VIEW_NAMES = {"code": "code", "blocks": "blocks", "split": "code and blocks"}
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def fill(template, values):
    """put values into {placeholders}. unknown names are left as they are."""
    return _PLACEHOLDER_RE.sub(lambda match: str(values[match.group(1)]) if match.group(1) in values
                               else match.group(0), str(template or ""))


def application_id(settings):
    custom = str(settings.get("discord_app_id") or "").strip()
    return custom if valid_application_id(custom) else DEFAULT_APPLICATION_ID


def values_for(settings, info):
    info = info or {}
    show_file = settings.get("discord_show_file", True)
    file_name = info.get("file") or ""
    values = {
        "action": info.get("action", "editing"),
        "file": file_name if show_file else HIDDEN_FILE,
        "name": os.path.splitext(file_name)[0] if show_file else HIDDEN_FILE,
        "folder": (os.path.basename(info.get("folder") or "") or "") if show_file else "",
        "line": info.get("line", 1),
        "lines": info.get("lines", 1),
        "column": info.get("column", 1),
        "view": VIEW_NAMES.get(info.get("view"), info.get("view") or "code"),
        "level": settings.get("level", "beginner"),
        "problems": info.get("problems", 0),
        "version": version.VERSION,
    }
    return values


def build_activity(settings, info, started=None, program=None):
    """the activity to show, or None when discord status is off.

    info describes the open file (None when nothing is open). program is a running program's own activity from
    `presence` lines, which replaces the studio's words while it runs.
    """
    if not settings.get("discord_presence", True):
        return None
    values = values_for(settings, info)
    if info:
        details = fill(settings.get("discord_details", ""), values)
        state = fill(settings.get("discord_state", ""), values)
    else:
        details = fill(settings.get("discord_idle", ""), values)
        state = ""
    activity = {}
    if details.strip():
        activity["details"] = details
    if state.strip():
        activity["state"] = state
    image = str(settings.get("discord_image") or "").strip() or DEFAULT_IMAGE
    assets = {"large_image": image}
    image_text = fill(settings.get("discord_image_text", ""), values).strip()
    if image_text:
        assets["large_text"] = image_text
    small = str(settings.get("discord_small_image") or "").strip()
    if small:
        assets["small_image"] = small
        assets["small_text"] = values["action"]
    activity["assets"] = assets
    if settings.get("discord_show_time", True) and started:
        activity["timestamps"] = {"start": int(started)}
    label = fill(settings.get("discord_button_label", ""), values).strip()
    url = str(settings.get("discord_button_url") or "").strip()
    if label and url:
        activity["buttons"] = [{"label": label, "url": url}]
    kind = ACTIVITY_TYPES.get(str(settings.get("discord_activity") or "playing"), 0)
    if kind:
        activity["type"] = kind
    if program and settings.get("discord_programs", True):
        activity = {key: value for key, value in activity.items() if key not in ("details", "state", "party")}
        for key, value in program.items():
            if key == "assets":
                activity["assets"] = dict(activity.get("assets") or {}, **value)
            else:
                activity[key] = value
    return clean_activity(activity)


def describe(activity):
    """two short lines that preview an activity in the settings window."""
    if not activity:
        return "nothing is shown"
    words = [activity.get("details", ""), activity.get("state", "")]
    return "  /  ".join(word.replace("⠀", "").strip() for word in words if word) or "just the picture"


class StudioPresence:
    """keeps gublan studio's discord status in step with the app. every call is cheap: updates are gathered for
    a moment, then handed to the background client."""

    DELAY_MS = 600

    def __init__(self, app, client_factory=PresenceClient):
        self.app = app
        self.client_factory = client_factory
        self.client = None
        self.job = None
        self.started = time.time()
        self.program = None
        self.program_app = ""
        self.last = None
        self.told_off = False

    # ----- called by the app -----------------------------------------------------------------------------
    def refresh(self, now=False):
        """look again soon. a check that is already waiting is kept, not pushed back, so a stream of small changes
        (the run state changes several times a second) still reaches discord."""
        root = self.app.root
        if now:
            if self.job is not None:
                try:
                    root.after_cancel(self.job)
                except Exception:  # noqa: BLE001 - the window may be closing
                    pass
                self.job = None
            self._apply()
            return
        if self.job is not None:
            return
        try:
            self.job = root.after(self.DELAY_MS, self._apply)
        except Exception:  # noqa: BLE001 - the window may be closing
            self.job = None

    def set_program(self, application, activity):
        """a running program's own status (None when it ends or clears it)."""
        self.program = activity or None
        self.program_app = application or ""
        self.refresh()

    def program_allowed(self):
        settings = self.app.settings
        return bool(settings.get("discord_presence", True) and settings.get("discord_programs", True))

    def status(self):
        settings = self.app.settings
        if not settings.get("discord_presence", True):
            return ("off", "discord status is off")
        if self.client is None:
            return ("off", "starting")
        return self.client.status

    def status_text(self):
        state, text = self.status()
        note = ""
        custom = str(self.app.settings.get("discord_app_id") or "").strip()
        if custom and not valid_application_id(custom):
            note = " (that application id doesn't look right, so gublan studio's own is used)"
        return f"{text}{note}".lower()

    def preview(self):
        return describe(self.activity())

    def activity(self):
        program = self.program if self.program_allowed() else None
        return build_activity(self.app.settings, self.info(), self.started_for(), program)

    def close(self):
        if self.job is not None:
            try:
                self.app.root.after_cancel(self.job)
            except Exception:  # noqa: BLE001
                pass
            self.job = None
        if self.client is not None:
            self.client.close(timeout=1.0)
            self.client = None

    # ----- inside -------------------------------------------------------------------------------------------
    def started_for(self):
        app = self.app
        if app.running() and getattr(app, "run_wall_started", None):
            return app.run_wall_started
        return self.started

    def info(self):
        app = self.app
        doc = app.current
        running_doc = app.run_doc if app.running() and app.run_doc in app.docs else None
        doc = running_doc or doc
        if doc is None:
            return None
        if running_doc is not None:
            action = "paused in" if app.paused else "running"
        else:
            action = "editing"
        try:
            line, column = doc.editor.cursor()
            lines = doc.editor.line_count()
        except Exception:  # noqa: BLE001 - a tab that is being closed
            line, column, lines = 1, 0, 1
        problems = len(getattr(doc, "diagnostics", []) or [])
        return {"action": action, "file": doc.name, "folder": doc.folder or "", "line": line,
                "column": column + 1, "lines": lines, "view": doc.view, "problems": problems}

    def _apply(self):
        self.job = None
        settings = self.app.settings
        if not settings.get("discord_presence", True):
            if self.client is not None:
                self.client.close(timeout=0.5)
                self.client = None
            self.last = None
            return
        program = self.program if self.program_allowed() else None
        application = self.program_app if program and valid_application_id(self.program_app) \
            else application_id(settings)
        activity = self.activity()
        if self.client is None:
            self.client = self.client_factory(application)
        else:
            self.client.set_application(application)
        if (application, activity) != self.last:
            self.last = (application, activity)
            self.client.update(activity)
