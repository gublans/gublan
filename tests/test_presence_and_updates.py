"""tests for the 1.0.4 additions: discord presence, the updater's clean installer launch, and the new built-ins."""
import os
import re
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import gublanpresence  # noqa: E402
from gublancore import GublanRuntime, analyze_source, parse_line, save_file_name  # noqa: E402
from studio import config, presence, updater, version  # noqa: E402


def run(source, **options):
    output, errors = [], []
    runtime = GublanRuntime(onlog=output.append, onerror=lambda message, _file, line: errors.append((line, message)),
                            **options)
    runtime.run(source)
    return output, errors, runtime


# ----- discord ipc ------------------------------------------------------------------------------------------------
class FakeConnection:
    """stands in for the discord app: answers the handshake and every SET_ACTIVITY."""

    def __init__(self, reject=None):
        self.sent = []
        self.answers = []
        self.reject = reject or (lambda activity: "")
        self.closed = False
        self.lock = threading.Condition()

    def send(self, op, payload):
        with self.lock:
            self.sent.append((op, payload))
            if op == gublanpresence.OP_HANDSHAKE:
                self.answers.append((gublanpresence.OP_FRAME, {
                    "cmd": "DISPATCH", "evt": "READY", "data": {"user": {"username": "sam"}}}))
            elif payload.get("cmd") == "SET_ACTIVITY":
                error = self.reject(payload["args"]["activity"])
                answer = {"cmd": "SET_ACTIVITY", "nonce": payload["nonce"], "data": {}}
                if error:
                    answer.update(evt="ERROR", data={"code": 4000, "message": error})
                self.answers.append((gublanpresence.OP_FRAME, answer))
            self.lock.notify_all()

    def receive(self, timeout=5):
        with self.lock:
            if not self.lock.wait_for(lambda: self.answers, timeout):
                raise TimeoutError("no answer")
            return self.answers.pop(0)

    def alive(self):
        return not self.closed

    def close(self):
        self.closed = True

    def activities(self):
        return [payload["args"]["activity"] for op, payload in self.sent if payload.get("cmd") == "SET_ACTIVITY"]


def wait_for(check, seconds=3.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.01)
    return check()


class PresenceModuleTests(unittest.TestCase):
    def test_clean_activity_keeps_what_discord_accepts(self):
        cleaned = gublanpresence.clean_activity({
            "details": "x", "state": "  lots   of   space  ", "assets": {"large_text": "no picture"},
            "buttons": [{"label": "a" * 40, "url": "https://example.com"}, {"label": "bad", "url": "ftp://x"},
                        {"label": "b", "url": "http://example.com"}, {"label": "c", "url": "https://c.com"}],
            "party": {"size": [5, 2]}, "timestamps": {"start": 12.7, "end": -1}, "type": 3,
        })
        self.assertEqual(cleaned["details"], "x\u2800")
        self.assertEqual(cleaned["state"], "lots of space")
        self.assertNotIn("assets", cleaned)
        self.assertNotIn("party", cleaned)
        self.assertEqual(cleaned["timestamps"], {"start": 12})
        self.assertEqual([button["label"] for button in cleaned["buttons"]], ["a" * 32, "b\u2800"])
        self.assertEqual(cleaned["type"], 3)
        self.assertIsNone(gublanpresence.clean_activity({"details": "   "}))
        self.assertEqual(len(gublanpresence.clean_activity({"details": "y" * 300})["details"]), 128)

    def test_application_ids(self):
        self.assertTrue(gublanpresence.valid_application_id(gublanpresence.DEFAULT_APPLICATION_ID))
        self.assertEqual(gublanpresence.DEFAULT_APPLICATION_ID, "1574014510690205746")
        self.assertFalse(gublanpresence.valid_application_id("12ab"))
        self.assertFalse(gublanpresence.valid_application_id(""))

    def test_client_says_hello_sends_the_newest_status_and_clears_it_when_closed(self):
        fake = FakeConnection()
        client = gublanpresence.PresenceClient("123456789012345678", connector=lambda: fake, interval=0.05)
        client.update({"details": "one"})
        client.update({"details": "two"})
        self.assertTrue(wait_for(lambda: {"details": "two"} in fake.activities()))
        self.assertEqual(fake.sent[0], (gublanpresence.OP_HANDSHAKE, {"v": 1, "client_id": "123456789012345678"}))
        self.assertTrue(client.connected)
        self.assertIn("sam", client.status[1])
        client.close(timeout=2)
        self.assertIsNone(fake.activities()[-1])
        self.assertTrue(fake.closed)

    def test_client_leaves_out_pictures_discord_refuses(self):
        fake = FakeConnection(reject=lambda activity: "bad image" if activity and "assets" in activity else "")
        client = gublanpresence.PresenceClient(connector=lambda: fake, interval=0.01)
        client.update({"details": "hi", "assets": {"large_image": "missing"}, "type": 3})
        self.assertTrue(wait_for(lambda: client.sent == {"details": "hi"}))
        self.assertEqual(client.status[0], "connected")
        self.assertIn("pictures", client.status[1])
        client.close(timeout=2)

    def test_client_waits_quietly_when_discord_is_closed(self):
        attempts = []

        def connector():
            attempts.append(1)
            raise OSError("the discord app is not running")

        client = gublanpresence.PresenceClient(connector=connector, interval=0.01, retry=60)
        client.update({"details": "hi"})
        self.assertTrue(wait_for(lambda: client.status[0] == "waiting"))
        time.sleep(0.1)
        self.assertEqual(len(attempts), 1)
        client.close(timeout=1)

    def test_switching_application_reconnects(self):
        connections = []

        def connector():
            connections.append(FakeConnection())
            return connections[-1]

        client = gublanpresence.PresenceClient("111111111111111111", connector=connector, interval=0.01)
        client.update({"details": "hi"})
        self.assertTrue(wait_for(lambda: connections and connections[0].activities()))
        client.set_application("222222222222222222")
        self.assertTrue(wait_for(lambda: len(connections) == 2 and connections[1].activities()))
        self.assertEqual(connections[1].sent[0][1]["client_id"], "222222222222222222")
        self.assertIsNone(connections[0].activities()[-1])
        client.close(timeout=2)


class StudioPresenceTests(unittest.TestCase):
    def settings(self, **changes):
        settings = dict(config.DEFAULTS)
        settings.update(changes)
        return settings

    def test_default_status_fills_in_the_file_and_line(self):
        info = {"action": "editing", "file": "game.gubl", "folder": "C:/games", "line": 4, "lines": 30,
                "column": 2, "view": "split", "problems": 1}
        activity = presence.build_activity(self.settings(), info, started=1000)
        self.assertEqual(activity["details"], "editing game.gubl")
        self.assertEqual(activity["state"], "line 4 of 30")
        self.assertEqual(activity["timestamps"], {"start": 1000})
        self.assertEqual(activity["assets"]["large_image"], gublanpresence.DEFAULT_IMAGE)
        self.assertEqual(activity["assets"]["large_text"], f"gublan studio {version.VERSION}")
        self.assertEqual(activity["buttons"][0]["url"], "https://github.com/gublans/gublan")
        self.assertNotIn("type", activity)

    def test_status_can_hide_the_file_and_be_customised(self):
        info = {"action": "running", "file": "secret.gubl", "folder": "x", "line": 1, "lines": 2, "column": 1,
                "view": "blocks", "problems": 0}
        settings = self.settings(discord_show_file=False, discord_show_time=False,
                                 discord_details="{action} {name} in {view}", discord_state="{level} {unknown}",
                                 discord_button_label="", discord_activity="watching", discord_small_image="dot")
        activity = presence.build_activity(settings, info, started=5)
        self.assertEqual(activity["details"], "running a program in blocks")
        self.assertEqual(activity["state"], "beginner {unknown}")
        self.assertNotIn("timestamps", activity)
        self.assertNotIn("buttons", activity)
        self.assertEqual(activity["type"], 3)
        self.assertEqual(activity["assets"]["small_image"], "dot")
        self.assertNotIn("secret", str(activity))

    def test_idle_off_and_program_status(self):
        self.assertEqual(presence.build_activity(self.settings(), None)["details"], "thinking about what to make")
        self.assertIsNone(presence.build_activity(self.settings(discord_presence=False), None))
        program = {"details": "level 3", "assets": {"small_image": "https://example.com/a.png"}}
        info = {"action": "running", "file": "a.gubl", "line": 1, "lines": 1}
        activity = presence.build_activity(self.settings(), info, program=program)
        self.assertEqual(activity["details"], "level 3")
        self.assertNotIn("state", activity)
        self.assertEqual(activity["assets"]["small_image"], "https://example.com/a.png")
        self.assertEqual(activity["assets"]["large_image"], gublanpresence.DEFAULT_IMAGE)
        ignored = presence.build_activity(self.settings(discord_programs=False), info, program=program)
        self.assertEqual(ignored["details"], "running a.gubl")

    def test_custom_application_id_falls_back_when_it_is_not_a_number(self):
        self.assertEqual(presence.application_id(self.settings(discord_app_id="nope")),
                         gublanpresence.DEFAULT_APPLICATION_ID)
        self.assertEqual(presence.application_id(self.settings(discord_app_id=" 123456789012345678 ")),
                         "123456789012345678")

    def test_settings_keep_their_types(self):
        for key in ("discord_presence", "discord_details", "discord_app_id", "check_updates", "skipped_update",
                    "update_pending"):
            self.assertIn(key, config.DEFAULTS)


# ----- updater ---------------------------------------------------------------------------------------------------
class UpdaterInstallTests(unittest.TestCase):
    def test_versions_compare_by_number(self):
        self.assertTrue(updater.is_newer("v1.0.10", "1.0.9"))
        self.assertFalse(updater.is_newer("1.0.4", "v1.0.4"))
        self.assertTrue(updater.same_version("v1.0.4", "1.0.4.0"))
        self.assertFalse(updater.same_version("", "1.0.4"))

    def test_installer_gets_a_clean_environment(self):
        bundle = os.path.join(tempfile.gettempdir(), "_MEI12345")
        environ = {
            "_PYI_ARCHIVE_FILE": "C:/old/GublanStudio.exe", "_PYI_APPLICATION_HOME_DIR": bundle,
            "_PYI_PARENT_PROCESS_LEVEL": "1", "_MEIPASS2": bundle,
            "TCL_LIBRARY": os.path.join(bundle, "tcl"), "PATH": os.pathsep.join([bundle, "C:/Windows"]),
            "APPDATA": "C:/Users/sam/AppData/Roaming",
        }
        clean = updater.installer_environment(environ, bundle=bundle)
        self.assertFalse([key for key in clean if key.startswith(("_PYI", "_MEIPASS"))])
        self.assertNotIn("TCL_LIBRARY", clean)
        self.assertEqual(clean["PATH"], "C:/Windows")
        self.assertEqual(clean["APPDATA"], "C:/Users/sam/AppData/Roaming")
        self.assertEqual(clean["PYINSTALLER_RESET_ENVIRONMENT"], "1")

    def test_installer_runs_silently_after_waiting_for_the_studio(self):
        arguments = updater.installer_arguments([10, 20], relaunch=True, log="C:/logs/update.log")
        self.assertEqual(arguments[:5], ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/SP-"])
        self.assertIn("/WAITPID=10,20", arguments)
        self.assertIn("/RELAUNCH=1", arguments)
        self.assertIn("/LOG=C:/logs/update.log", arguments)
        self.assertNotIn("/RELAUNCH=1", updater.installer_arguments([10], relaunch=False))

    def test_launch_installer_passes_the_clean_environment(self):
        with patch.object(updater.subprocess, "Popen") as popen, \
                patch.object(updater, "processes_to_wait_for", return_value=[42]), \
                patch.dict(os.environ, {"_PYI_ARCHIVE_FILE": "x"}):
            updater.launch_installer(os.path.join(tempfile.gettempdir(), "GublanStudioSetup-1.exe"))
        command = popen.call_args.args[0]
        self.assertTrue(command[0].endswith("GublanStudioSetup-1.exe"))
        self.assertIn("/WAITPID=42", command)
        self.assertIn("/RELAUNCH=1", command)
        self.assertNotIn("_PYI_ARCHIVE_FILE", popen.call_args.kwargs["env"])

    def test_release_notes_and_page_come_from_github(self):
        url = "https://github.com/gublans/gublan/releases/download/v9.0.0/GublanStudioSetup.exe"
        release = updater.latest_release_from_payload({
            "tag_name": "v9.0.0", "body": "new things\r\n" + "x" * 3000,
            "html_url": "https://github.com/gublans/gublan/releases/tag/v9.0.0",
            "assets": [{"name": "GublanStudioSetup.exe", "browser_download_url": url}],
        }, "1.0.4")
        self.assertTrue(release.notes.startswith("new things"))
        self.assertLessEqual(len(release.notes), updater.MAX_NOTES + 4)
        self.assertEqual(release.page, "https://github.com/gublans/gublan/releases/tag/v9.0.0")

    def test_installer_script_and_spec_take_the_version_from_version_py(self):
        with open(os.path.join(ROOT, "GublanStudio.iss"), encoding="utf-8") as handle:
            script = handle.read()
        self.assertIn("studio\\version.py", script)
        self.assertIn("{param:WAITPID|}", script)
        self.assertIn("Check: ShouldRelaunch", script)
        self.assertIn("PYINSTALLER_RESET_ENVIRONMENT", script)
        with open(os.path.join(ROOT, "GublanStudio.spec"), encoding="utf-8") as handle:
            spec = handle.read()
        self.assertIn("version=version_info", spec)
        self.assertIn("gublanpresence.py", spec)
        self.assertRegex(version.VERSION, r"^\d+\.\d+\.\d+$")


# ----- language ----------------------------------------------------------------------------------------------------
class NewBuiltinTests(unittest.TestCase):
    def test_list_commands(self):
        output, errors, _ = run("list fruit apple pear\ninsert fruit 0 lemon\ninsert fruit -1 fig\n"
                                "remove fruit pear\nremove fruit kiwi\nprint {fruit}\nlist n 3 1 2\nsort n\n"
                                "print {n}\nsort n reverse\nprint {n}\nshuffle n\nprint {sort(n)}")
        self.assertEqual(errors, [])
        self.assertEqual(output, ['["lemon", "apple", "fig"]', "[1, 2, 3]", "[3, 2, 1]", "[1, 2, 3]"])

    def test_new_functions(self):
        source = "\n".join([
            "print {count([1, 2, 2], 2)} {count(\"banana\", \"a\")} {unique([1, 1, 2])} {average([2, 4])}",
            "print {pad(7, 3, 0)} {pad(\"x\", 3)}| {decimals(2, 2)} {wrap(-10, 0, 360)} {remap(5, 0, 10, 100, 200)}",
            "print {approach(10, 3, 4)} {angleto(0, 0, 10, 0)} {angleto(vec2(0, 0), vec2(0, 5))} {hsv(0, 1, 1)}",
            "print {isnumber(\"-2.5\")} {isnumber(\"two\")} {isnumber(true)} {startswith(\"gublan\", \"gub\")}",
            "print {endswith(\"gublan\", \"lan\")} {chance(100)} {chance(0)} {len(shuffle([1, 2, 3]))}",
            "print {len(date())} {len(clock())} {now() > 1700000000}",
        ])
        output, errors, _ = run(source)
        self.assertEqual(errors, [])
        self.assertEqual(output, ["2 3 [1, 2] 3", "007   x| 2.00 350 150", "6 0 90 [255, 0, 0]",
                                  "true false false true", "true true false 3", "10 5 true"])

    def test_bad_values_give_friendly_errors(self):
        for line, words in (("print {average([])}", "average"), ("print {wrap(1, 5, 5)}", "bigger"),
                            ("print {pad(1, 3, \"ab\")}", "single"), ("print {date(1)}", "does not take"),
                            ("list a 1 2\ninsert a 9 x", "past the end"), ("x = 1\nsort x", "does not exist")):
            with self.subTest(line=line):
                _output, errors, _ = run(line)
                self.assertTrue(errors and words in errors[0][1], errors)

    def test_command_names_still_work_as_variables(self):
        output, errors, _ = run("load = 3\nsave = load + 1\nsave += 0\nprint {load} {save}")
        self.assertEqual(errors, [])
        self.assertEqual(output, ["3 4"])
        self.assertEqual(parse_line("cursor = 1").cmd, "set")
        self.assertEqual(parse_line("cursor hide").cmd, "cursor")

    def test_save_load_and_forget_between_runs(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"GUBLAN_SAVE_FOLDER": folder}):
            output, errors, _ = run("load best best 0\nprint {best} {saved(\"best\")}\nsave best 42\n"
                                    "save spot {vec2(1, 2)}\nsave bag {[\"a\", {\"b\": 1}]}", save_name="My Game!")
            self.assertEqual((output, errors), (["0 false"], []))
            self.assertEqual(os.listdir(folder), ["my game.json"])
            output, errors, _ = run("load best best 0\nload spot spot\nload bag bag\nprint {best} {spot.x} {bag[1].b}"
                                    "\nprint {load(\"missing\", 7)} {load(\"best\")}\nforget best\n"
                                    "print {saved(\"best\")}", save_name="My Game!")
            self.assertEqual((output, errors), (["42 1 1", "7 42", "false"], []))
            output, errors, _ = run("load best best nothing here\nprint {best}\nforget all\n"
                                    "print {saved(\"spot\")}", save_name="my game")
            self.assertEqual((output, errors), (["nothing here", "false"], []))
            other, _errors, _ = run("print {saved(\"bag\")}", save_name="another")
            self.assertEqual(other, ["false"])

    def test_saving_refuses_things_that_cannot_be_kept(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"GUBLAN_SAVE_FOLDER": folder}):
            runtime = GublanRuntime(save_name="t")
            with self.assertRaisesRegex(ValueError, "finite"):
                runtime._storable([1, float("inf")])
            with self.assertRaisesRegex(ValueError, "can't save"):
                runtime._storable(object())
            _output, errors, _ = run("big = \"x\"\nloop 19\n    big = big + big\nend\nsave big big",
                                     save_name="t")
            self.assertTrue(errors and ("256 kb" in errors[0][1] or "too large" in errors[0][1]), errors)
        self.assertEqual(save_file_name("../../evil"), "evil.json")
        self.assertEqual(save_file_name(""), "untitled.json")
        self.assertEqual(save_file_name("Space Dodge.gubl"), "space dodge.json")

    def test_presence_lines_reach_the_studio(self):
        seen = []
        _output, errors, _ = run("presence details exploring\npresence state level {1 + 1}\n"
                                 "presence image https://example.com/a.png the caves\npresence party 2 4\n"
                                 "presence button https://example.com play\npresence countdown 60\n"
                                 "presence app 123456789012345678\npresence state\npresence state\npresence clear",
                                 onpresence=lambda app, activity: seen.append((app, activity)))
        self.assertEqual(errors, [])
        self.assertEqual(seen[0], ("", {"details": "exploring"}))
        self.assertEqual(seen[1][1]["state"], "level 2")
        final_before_clear = seen[-2][1]
        self.assertEqual(seen[-2][0], "123456789012345678")
        self.assertEqual(final_before_clear["assets"], {"large_image": "https://example.com/a.png",
                                                        "large_text": "the caves"})
        self.assertEqual(final_before_clear["party"]["size"], [2, 4])
        self.assertEqual(final_before_clear["buttons"], [{"label": "play", "url": "https://example.com"}])
        self.assertIn("end", final_before_clear["timestamps"])
        self.assertNotIn("state", final_before_clear)
        self.assertEqual(seen[-1], ("123456789012345678", None))
        # the repeated "presence state" changed nothing, so it wasn't sent again
        self.assertEqual(len(seen), 9)

    def test_presence_without_the_studio_uses_its_own_client(self):
        made = []

        class Client:
            def __init__(self, application):
                self.application, self.updates, self.closed = application, [], False
                made.append(self)

            def set_application(self, application):
                self.application = application

            def update(self, activity):
                self.updates.append(activity)

            def close(self, timeout=None):
                self.closed = True

        with patch.object(gublanpresence, "PresenceClient", Client):
            _output, errors, _ = run("presence details hi\npresence timer")
        self.assertEqual(errors, [])
        self.assertEqual(len(made), 1)
        self.assertEqual(made[0].application, gublanpresence.DEFAULT_APPLICATION_ID)
        self.assertEqual(made[0].updates[0], {"details": "hi"})
        self.assertTrue(made[0].closed)

    def test_analyzer_checks_new_commands(self):
        problems = analyze_source("presence detials hi\npresence button ftp://x y\npresence party 1\n"
                                  "presence app 12ab\ncursor wiggle\nsort x sideways\nload a 9lives\nforget a b\n"
                                  "shuffle a b")
        messages = [item["message"] for item in problems]
        self.assertEqual([item["line"] for item in problems], list(range(1, 10)))
        self.assertIn("did you mean 'details'", messages[0])
        self.assertIn("https://", messages[1])
        self.assertEqual(analyze_source("presence details hi\npresence timer off\ncursor show\n"
                                        "list a 1\nsort a reverse\nload best x 0\nforget all"), [])


if __name__ == "__main__":
    unittest.main()
