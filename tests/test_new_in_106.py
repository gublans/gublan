"""tests for what is new in 1.0.6: pictures and sounds from a live session host, the crash guard and unsaved-work
recovery, reading odd files safely, switching themes without a restart, and the mcp setup fixes."""
import codecs
import gc
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import gublanmcp  # noqa: E402
from gublancore import GublanRuntime  # noqa: E402
from studio import collab, config, guard, textfiles, theme, updater, version  # noqa: E402


class VersionTests(unittest.TestCase):
    def test_version_is_106(self):
        self.assertEqual(version.VERSION, "1.0.6")
        self.assertEqual(gublanmcp._version(), "1.0.6")

    def test_new_settings_have_defaults(self):
        for key in ("reload_changed_files", "live_share_files"):
            self.assertIn(key, config.DEFAULTS)


# ----- files from the live session host ------------------------------------------------------------------------
class HostPathTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="gublan_host_")
        os.makedirs(os.path.join(self.folder, "assets"))
        for name in ("assets/pic.png", "song.ogg", "notes.docx"):
            with open(os.path.join(self.folder, *name.split("/")), "wb") as handle:
                handle.write(b"data")
        self.outside = tempfile.mkdtemp(prefix="gublan_outside_")
        with open(os.path.join(self.outside, "secret.png"), "wb") as handle:
            handle.write(b"secret")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)
        shutil.rmtree(self.outside, ignore_errors=True)

    def test_clean_relative_keeps_programs_inside_their_folder(self):
        self.assertEqual(collab.clean_relative("assets\\pic.png"), "assets/pic.png")
        self.assertEqual(collab.clean_relative('"./assets//pic.png"'), "assets/pic.png")
        for bad in ("../secret.png", "assets/../../x.png", "/etc/passwd", "C:/Windows/win.ini", "", "  "):
            self.assertIsNone(collab.clean_relative(bad), bad)

    def test_only_media_and_code_inside_the_folder_are_shared(self):
        path, _why = collab.host_path(self.folder, "assets/pic.png")
        self.assertEqual(path, os.path.realpath(os.path.join(self.folder, "assets", "pic.png")))
        self.assertIsNotNone(collab.host_path(self.folder, "song.ogg")[0])
        path, why = collab.host_path(self.folder, "notes.docx")
        self.assertIsNone(path)
        self.assertIn("pictures, sounds", why)
        relative = os.path.relpath(os.path.join(self.outside, "secret.png"), self.folder).replace(os.sep, "/")
        self.assertIsNone(collab.host_path(self.folder, relative)[0])
        self.assertIn("doesn't have", collab.host_path(self.folder, "missing.png")[1])


class _Root:
    def after(self, _ms, _function):
        return None

    def after_cancel(self, _job):
        pass


class _Editor:
    def __init__(self, text):
        self.value = text
        self.collab_listener = None
        self.collab_cursor = None

    def get(self):
        return self.value

    def live_apply(self, start, end, insert):
        self.value = self.value[:start] + insert + self.value[end:]

    def live_replace_all(self, text):
        self.value = text

    def show_peers(self, peers):
        pass


class _Doc:
    def __init__(self, name, text, folder=None):
        self.name = name
        self.folder = folder
        self.editor = _Editor(text)


class _App:
    def __init__(self, docs=(), folder=None):
        self.root = _Root()
        self.docs = list(docs)
        self.messages = []
        self.settings = {"folder": folder or ""}

    def live_open(self, name, text):
        doc = _Doc(name, text)
        self.docs.append(doc)
        return doc

    def live_message(self, text, kind="info"):
        self.messages.append(text)

    def live_changed(self):
        pass


class LiveAssetTests(unittest.TestCase):
    """a real host and guest on this computer, talking over tcp."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="gublan_live_host_")
        os.makedirs(os.path.join(self.folder, "assets"))
        self.picture = os.urandom(collab.ASSET_CHUNK * 2 + 1234)  # three pieces
        with open(os.path.join(self.folder, "assets", "pic.png"), "wb") as handle:
            handle.write(self.picture)
        with open(os.path.join(self.folder, "helpers.gubl"), "w", encoding="utf-8") as handle:
            handle.write("function hello\n    print hello from the host\nend\n")
        source = "include helpers.gubl\ncall hello\n"
        self.host_doc = _Doc("main.gubl", source, folder=self.folder)
        self.host = collab.LiveSession(_App([self.host_doc]), "kim", host=True)
        self.host.start_host(0, code="abc234")
        port = self.host.server.getsockname()[1]
        self.guest = collab.LiveSession(_App(), "sam", host=False)
        self.running = True
        self.pump = threading.Thread(target=self._pump, daemon=True)
        self.pump.start()
        self.guest.start_guest("127.0.0.1", port, "abc234")
        self.wait_for(lambda: self.guest.files and self.guest.me)
        self.file_id = next(iter(self.guest.files))

    def tearDown(self):
        self.running = False
        self.pump.join(timeout=2)
        self.guest.end()
        self.host.end()
        shutil.rmtree(self.folder, ignore_errors=True)

    def _pump(self):
        while self.running:
            for session in (self.host, self.guest):
                if session.active:
                    session._poll()
            time.sleep(0.005)

    def wait_for(self, condition, seconds=10):
        end = time.time() + seconds
        while time.time() < end:
            if condition():
                return
            time.sleep(0.01)
        self.fail("timed out")

    def test_the_host_says_it_can_share_files(self):
        self.assertIn("assets", self.guest.host_features)

    def test_a_guest_gets_a_picture_in_pieces_and_keeps_a_copy(self):
        files = self.guest.host_files
        path = files.fetch(self.file_id, "assets/pic.png")
        self.assertIsNotNone(path)
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), self.picture)
        self.assertTrue(path.startswith(files.root))
        # asked again: the host only says "same"
        started = time.time()
        self.assertEqual(files.fetch(self.file_id, "assets/pic.png"), path)
        self.assertLess(time.time() - started, 5)
        # the host changes it: the guest gets the new one
        with open(os.path.join(self.folder, "assets", "pic.png"), "wb") as handle:
            handle.write(b"new picture")
        with open(files.fetch(self.file_id, "assets/pic.png"), "rb") as handle:
            self.assertEqual(handle.read(), b"new picture")
        self.assertTrue(any("sending assets/pic.png to sam" in text for text in self.host.app.messages))

    def test_files_outside_the_folder_or_missing_are_refused(self):
        said = []
        files = self.guest.host_files
        self.assertIsNone(files.fetch(self.file_id, "../outside.png", log=said.append))
        self.assertIsNone(files.fetch(self.file_id, "nothing.png", log=said.append))
        self.assertTrue(any("doesn't have that file" in text for text in said), said)

    def test_a_host_can_turn_sharing_off(self):
        self.host.share_files = False
        said = []
        self.assertIsNone(self.guest.host_files.fetch(self.file_id, "assets/pic.png", log=said.append))
        self.assertTrue(any("turned off" in text for text in said), said)

    def test_a_guest_runs_a_program_whose_include_is_on_the_host(self):
        output, errors = [], []
        files = self.guest.host_files
        runtime = GublanRuntime(onlog=output.append, onerror=lambda message, *_: errors.append(message),
                                base_dir=files.folder_for(self.file_id),
                                fetchfile=files.fetcher(self.file_id, log=output.append))
        runtime.run(self.guest.files[self.file_id].shadow)
        self.assertEqual(errors, [])
        self.assertIn("hello from the host", output)

    def test_ending_the_session_removes_the_copies(self):
        root = self.guest.host_files.folder_for(self.file_id)
        self.assertTrue(os.path.isdir(root))
        self.guest.end()
        self.assertFalse(os.path.exists(root))


class FetchHookTests(unittest.TestCase):
    def test_media_and_includes_ask_fetchfile_first(self):
        folder = tempfile.mkdtemp(prefix="gublan_fetch_")
        try:
            asked = []

            def fetch(relative):
                asked.append(relative)
                target = os.path.join(folder, *relative.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "w", encoding="utf-8") as handle:
                    handle.write("print included\n" if relative.endswith(".gubl") else "x")
                return target

            output = []
            runtime = GublanRuntime(onlog=output.append, base_dir=folder, fetchfile=fetch)
            self.assertEqual(runtime._media_path("sounds/beep.wav", "audio"),
                             os.path.join(folder, "sounds", "beep.wav"))
            runtime.run("include lib/extra.gubl\nprint done\n")
            self.assertEqual(output, ["included", "done"])
            self.assertIn("sounds/beep.wav", asked)
            self.assertIn("lib/extra.gubl", asked)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_a_broken_fetchfile_means_not_found(self):
        def broken(_relative):
            raise OSError("no network")

        runtime = GublanRuntime(onlog=lambda *_: None, base_dir=tempfile.gettempdir(), fetchfile=broken)
        with self.assertRaises(ValueError):
            runtime._media_path("nope_never_here.wav", "audio")


# ----- reading files --------------------------------------------------------------------------------------------
class TextFileTests(unittest.TestCase):
    def test_byte_order_marks_and_utf16_without_one(self):
        self.assertEqual(textfiles.decode(codecs.BOM_UTF8 + b"print hi\r\n"), ("print hi\n", "utf-8"))
        self.assertEqual(textfiles.decode(codecs.BOM_UTF16_LE + "print hi".encode("utf-16-le"))[0], "print hi")
        self.assertEqual(textfiles.decode("print hi\nprint café".encode("utf-16-le")),
                         ("print hi\nprint café", "utf-16-le"))
        self.assertEqual(textfiles.decode("print hi".encode("utf-16-be"))[1], "utf-16-be")

    def test_windows_1252_and_stray_zero_characters(self):
        self.assertEqual(textfiles.decode("print café\n".encode("cp1252")), ("print café\n", "windows-1252"))
        self.assertEqual(textfiles.decode(b"print a\x00b\n")[0], "print ab\n")

    def test_binary_files_are_not_text(self):
        with self.assertRaises(textfiles.NotText):
            textfiles.decode(bytes(range(256)) * 40)
        with self.assertRaises(textfiles.NotText):
            textfiles.decode(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x06\x00\x00")

    def test_long_lines_and_the_blocks_limit(self):
        self.assertEqual(textfiles.longest_line("ab\nabcd\n"), 4)
        self.assertGreater(textfiles.longest_line("x" * (textfiles.LONG_LINE + 5)), textfiles.LONG_LINE)
        self.assertFalse(textfiles.too_big_for_blocks("print hi\n" * 100))
        self.assertTrue(textfiles.too_big_for_blocks("print hi\n" * (textfiles.BLOCKS_LINES + 1)))
        self.assertEqual(textfiles.describe_size(3 * 1024 * 1024), "3.0 mb")


# ----- the crash guard and recovery ----------------------------------------------------------------------------
class GuardTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="gublan_guard_")
        self.patch = patch.object(guard, "settings_folder", lambda: self.folder)
        self.patch.start()

    def tearDown(self):
        guard.uninstall()
        self.patch.stop()
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_unsaved_work_is_kept_and_cleared(self):
        guard.save_recovery([{"name": "a.gubl", "path": None, "text": "print 1"},
                             {"name": "b.gubl", "path": "c:/b.gubl", "text": "print 2"}])
        items = guard.load_recovery()
        self.assertEqual([item["text"] for item in items], ["print 1", "print 2"])
        guard.save_recovery([{"name": "a.gubl", "path": None, "text": "print 3"}])
        self.assertEqual([item["text"] for item in guard.load_recovery()], ["print 3"])
        guard.clear_recovery()
        self.assertEqual(guard.load_recovery(), [])

    def test_a_leftover_running_note_means_the_last_session_crashed(self):
        self.assertFalse(guard.mark_running())
        guard.mark_closed()
        self.assertFalse(guard.mark_running())
        # still there at the next start, written by a process that is gone: a crash
        with open(os.path.join(self.folder, "running"), "w", encoding="utf-8") as handle:
            handle.write("999999999")
        self.assertTrue(guard.mark_running())
        guard.mark_closed()

    def test_last_crash_reads_the_previous_session(self):
        with open(os.path.join(self.folder, "crash.log"), "w", encoding="utf-8") as handle:
            handle.write("--- gublan studio started 1 ---\nFatal Python error: boom\n"
                         "--- gublan studio started 2 ---\n")
        self.assertIn("boom", guard.last_crash())

    def test_call_soon_runs_on_the_tk_thread_and_gc_waits_for_it(self):
        root = tk.Tk()
        root.withdraw()
        try:
            guard.install(root)
            self.assertFalse(gc.isenabled())
            ran = []
            worker = threading.Thread(target=lambda: guard.call_soon(lambda: ran.append(threading.current_thread())))
            worker.start()
            worker.join()
            end = time.time() + 3
            while not ran and time.time() < end:
                root.update()
                time.sleep(0.01)
            self.assertEqual(ran, [threading.main_thread()])
        finally:
            guard.uninstall()
            root.destroy()
        self.assertTrue(gc.isenabled())

    def test_errors_go_to_the_log(self):
        guard.log_error("something broke")
        with open(os.path.join(self.folder, "errors.log"), "r", encoding="utf-8") as handle:
            self.assertIn("something broke", handle.read())

    def test_restarting_gets_a_clean_environment(self):
        with patch.dict(os.environ, {"_PYI_APPLICATION_HOME_DIR": "x", "_MEIPASS2": "y"}):
            environment = guard.clean_environment()
        self.assertNotIn("_PYI_APPLICATION_HOME_DIR", environment)
        self.assertNotIn("_MEIPASS2", environment)
        self.assertEqual(environment.get("PYINSTALLER_RESET_ENVIRONMENT"), "1")
        self.assertEqual(updater.installer_environment.__module__, "studio.updater")


# ----- themes without a restart -----------------------------------------------------------------------------------
class LiveThemeTests(unittest.TestCase):
    def test_switching_recolours_widgets_and_future_defaults(self):
        start = theme.THEME_NAME
        root = tk.Tk()
        root.withdraw()
        try:
            frame = tk.Frame(root, bg=theme.PANEL)
            label = tk.Label(frame, bg=theme.PANEL, fg=theme.TEXT)
            text = tk.Text(frame, bg=theme.EDITOR_BG)
            text.tag_configure("x", foreground=theme.MUTED)
            button = theme.BracketButton(frame, "ok", bg=theme.PANEL)
            target = "paper" if start != "paper" else "midnight"
            self.assertTrue(theme.switch_theme(root, target))
            self.assertEqual(theme.THEME_NAME, target)
            self.assertEqual(frame.cget("bg").lower(), theme.PANEL.lower())
            self.assertEqual(label.cget("fg").lower(), theme.TEXT.lower())
            self.assertEqual(text.cget("bg").lower(), theme.EDITOR_BG.lower())
            self.assertEqual(str(text.tag_cget("x", "foreground")).lower(), theme.MUTED.lower())
            self.assertEqual(button.parent_bg.lower(), theme.PANEL.lower())
            entry = theme.flat_entry(frame)
            self.assertEqual(entry.cget("bg").lower(), theme.PANEL_ALT.lower())
            self.assertFalse(theme.switch_theme(root, "no such theme"))
        finally:
            theme.switch_theme(root, start)
            root.destroy()

    def test_shared_colours_prefer_the_right_name(self):
        old = {"BG": "#111111", "TEXT": "#eeeeee", "PANEL": "#111111"}
        new = {"BG": "#222222", "TEXT": "#000000", "PANEL": "#333333"}
        self.assertEqual(theme._color_map(old, new, ("PANEL",))["#111111"], "#333333")
        self.assertEqual(theme._color_map(old, new, ("BG",))["#111111"], "#222222")


# ----- mcp setup -------------------------------------------------------------------------------------------------
class McpSetupTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="gublan_mcp_setup_")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_pasted_folders_are_cleaned(self):
        self.assertEqual(gublanmcp.clean_folder(f' "{self.folder}{os.sep}" '), os.path.abspath(self.folder))
        self.assertEqual(gublanmcp.clean_folder(""), "")

    def test_a_missing_folder_falls_back_instead_of_failing(self):
        with patch.object(gublanmcp, "default_folder", lambda: self.folder):
            folder, note = gublanmcp.pick_folder(os.path.join(self.folder, "nope"))
            self.assertEqual(folder, self.folder)
            self.assertIn("there is no folder", note)
            self.assertEqual(gublanmcp.pick_folder(None), (self.folder, ""))
        program = os.path.join(self.folder, "game.gubl")
        with open(program, "w", encoding="utf-8") as handle:
            handle.write("print hi\n")
        self.assertEqual(gublanmcp.pick_folder(program), (self.folder, ""))
        server = gublanmcp.Server(self.folder)
        server.note = "a note"
        self.assertIn("a note", server.initialize({})["instructions"])

    def test_every_app_has_a_snippet_and_old_names_still_work(self):
        snippets = gublanmcp.client_snippets(self.folder)
        self.assertEqual(tuple(snippets), gublanmcp.APPS)
        self.assertIn("--scope user", snippets["claude code"][1])
        self.assertEqual(gublanmcp.OLD_APP_NAMES["claude desktop / cursor"], "claude desktop")

    def test_adding_to_an_apps_settings_keeps_what_was_there(self):
        path = os.path.join(self.folder, "app", "config.json")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"theme": "dark", "mcpServers": {"other": {"command": "x"}}}, handle)
        gublanmcp.add_to_config(path, "mcpServers", {"command": "gublan", "args": ["--mcp", self.folder]})
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["theme"], "dark")
        self.assertEqual(set(data["mcpServers"]), {"other", "gublan"})
        self.assertTrue(os.path.isfile(path + ".bak"))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{ not json")
        with self.assertRaises(ValueError):
            gublanmcp.add_to_config(path, "mcpServers", {"command": "gublan"})

    def test_project_files_for_claude_code_and_vs_code(self):
        written = gublanmcp.install("vs code", self.folder)
        self.assertEqual(written, [os.path.join(self.folder, ".vscode", "mcp.json")])
        with open(written[0], "r", encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["servers"]["gublan"]["type"], "stdio")
        written = gublanmcp.install("claude code", self.folder)
        self.assertEqual(written, [os.path.join(self.folder, ".mcp.json")])

    def test_claude_desktop_files_include_the_store_version(self):
        packages = os.path.join(self.folder, "Packages", "Claude_abc123", "LocalCache", "Roaming", "Claude")
        os.makedirs(packages)
        with patch.dict(os.environ, {"LOCALAPPDATA": self.folder, "APPDATA": os.path.join(self.folder, "r")}):
            if os.name == "nt":
                files = gublanmcp.claude_desktop_files()
                self.assertIn(os.path.join(packages, "claude_desktop_config.json"), files)
                chosen = [path for path, _key, _server in gublanmcp.app_config_files("claude desktop", self.folder)]
                self.assertEqual(chosen, [os.path.join(packages, "claude_desktop_config.json")])


class GuideTests(unittest.TestCase):
    def test_the_106_features_have_guides(self):
        from studio.guides import GUIDES
        bodies = dict(GUIDES)
        self.assertIn("when something goes wrong", bodies)
        self.assertIn("host's computer", bodies["code together"])
        self.assertIn("no restart", bodies["themes and plugins"])
        self.assertIn("add it to", bodies["ai helpers"])


if __name__ == "__main__":
    unittest.main()
