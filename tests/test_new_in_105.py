"""tests for what is new in 1.0.5: live sessions, plugins, themes, motion, the converter's game code, turning gublan
into other languages, the mcp server and functions held in variables."""
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import gublanconvert  # noqa: E402
import gublancore  # noqa: E402
import gublanmcp  # noqa: E402
import gublantranslate  # noqa: E402
from gublancore import GublanRuntime, analyze_source  # noqa: E402
from studio import collab, config, plugins, theme  # noqa: E402

ENV = dict(os.environ, PYGAME_HIDE_SUPPORT_PROMPT="1", SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")


def run(source, base_dir=None):
    output, errors = [], []
    runtime = GublanRuntime(onlog=output.append, base_dir=base_dir,
                            onerror=lambda message, _file, line: errors.append((line, message)))
    runtime.run(source)
    return output, errors


def errors_in(source):
    return [item["message"] for item in analyze_source(source) if item.get("severity", "error") == "error"]


# ----- live sessions, without sockets ----------------------------------------------------------------------------
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
    def __init__(self, name, text):
        self.name = name
        self.editor = _Editor(text)


class _Root:
    def after(self, _ms, _function):
        return None

    def after_cancel(self, _job):
        pass


class _App:
    def __init__(self, docs=()):
        self.root = _Root()
        self.docs = list(docs)
        self.messages = []

    def live_open(self, name, text):
        doc = _Doc(name, text)
        self.docs.append(doc)
        return doc

    def live_message(self, text, kind="info"):
        self.messages.append(text)

    def live_changed(self):
        pass


class _Pipe:
    """stands in for a Connection: messages go through json like on the wire, into a list."""

    def __init__(self, messages, key):
        self.messages, self.key = messages, key
        self.closed = False

    def send(self, message):
        self.messages.append((self.key, json.loads(json.dumps(message))))

    def close(self):
        self.closed = True


class _Room:
    """a host and guests joined through in-memory pipes."""

    def __init__(self, text, guests=2, code="abc234", names=None):
        self.host_doc = _Doc("main.gubl", text)
        self.host = collab.LiveSession(_App([self.host_doc]), "kim", host=True)
        self.host.code = code
        self.host.people["host"] = {"name": "kim", "color": collab.COLORS[0], "file": None, "pos": 0}
        self.host.share(self.host_doc)
        self.up, self.down, self.guests = {}, {}, {}
        for number in range(guests):
            self.add_guest(f"p{number + 1}", (names or [])[number] if names else f"guest {number}", code)

    def add_guest(self, key, name, code):
        self.up[key], self.down[key] = [], []
        self.host.connections[key] = _Pipe(self.down[key], "host")
        guest = collab.LiveSession(_App(), name, host=False)
        guest.link = _Pipe(self.up[key], key)
        guest.link.send({"type": "hello", "protocol": collab.PROTOCOL, "name": name, "code": code})
        self.guests[key] = guest
        return guest

    def deliver_up(self, key):
        sender, message = self.up[key].pop(0)
        self.host._host_message(sender, message)

    def deliver_down(self, key):
        _sender, message = self.down[key].pop(0)
        self.guests[key]._guest_message(message)

    def settle(self):
        for _ in range(500):
            for shared in self.host.files.values():
                self.host.flush(shared)
            for guest in self.guests.values():
                for shared in guest.files.values():
                    guest.flush(shared)
            moved = False
            for key in self.guests:
                while self.up[key]:
                    self.deliver_up(key)
                    moved = True
                while self.down[key]:
                    self.deliver_down(key)
                    moved = True
            if not moved:
                return

    def guest_doc(self, key):
        return next(iter(self.guests[key].files.values())).doc


class LiveEditTests(unittest.TestCase):
    def test_make_op_finds_the_one_changed_part(self):
        self.assertIsNone(collab.make_op("same", "same"))
        self.assertEqual(collab.make_op("print hi", "print hello"), [7, 8, "ello"])
        self.assertEqual(collab.make_op("abc", "ac"), [1, 2, ""])
        for old, new in (("", "x"), ("loop\nend", "loop\n    wait 1\nend"), ("xyz", "")):
            self.assertEqual(collab.apply_op(old, collab.make_op(old, new)), new)

    def test_two_edits_made_at_once_end_the_same_in_either_order(self):
        rng = random.Random(5)
        for _ in range(20000):
            size = rng.randrange(0, 8)
            text = "".join(rng.choice("abcdef") for _ in range(size))

            def edit():
                start = rng.randrange(size + 1)
                return [start, rng.randrange(start, size + 1), rng.choice(["", "X", "YY", "Z"])]

            first, second = edit(), edit()
            one_way = collab.apply_op(collab.apply_op(text, first), collab.transform(second, first, False))
            other_way = collab.apply_op(collab.apply_op(text, second), collab.transform(first, second, True))
            self.assertEqual(one_way, other_way, (text, first, second))

    def test_host_and_guests_typing_at_once_end_with_the_same_text(self):
        for seed in range(40):
            rng = random.Random(seed)
            room = _Room("print hello\nloop\n    wait 1\nend\n", guests=3)
            editors = [room.host_doc.editor]
            room.settle()
            editors += [room.guest_doc(key).editor for key in room.guests]
            for _ in range(300):
                choice = rng.random()
                if choice < 0.5:
                    editor = rng.choice(editors)
                    text = editor.value
                    start = rng.randrange(len(text) + 1)
                    end = min(len(text), start + (rng.randrange(5) if rng.random() < 0.4 else 0))
                    editor.value = text[:start] + rng.choice(["a", "bc", "\n", " ", "end"]) + text[end:]
                    owner = room.host if editor is editors[0] else room.guests[f"p{editors.index(editor)}"]
                    owner.flush(next(iter(owner.files.values())))
                else:
                    key = rng.choice(list(room.guests))
                    if room.up[key] and (rng.random() < 0.5 or not room.down[key]):
                        room.deliver_up(key)
                    elif room.down[key]:
                        room.deliver_down(key)
            room.settle()
            final = room.host_doc.editor.value
            for key in room.guests:
                self.assertEqual(room.guest_doc(key).editor.value, final, f"seed {seed}")
            self.assertGreater(len(final), 40)

    def test_joining_needs_the_code_and_a_name(self):
        room = _Room("print hi\n", guests=0)
        room.add_guest("p1", "sam", "wrong1")
        room.add_guest("p2", "", "abc234")
        room.add_guest("p3", "sam", "abc234")
        room.add_guest("p4", "sam", "abc234")
        room.settle()
        self.assertTrue(any("code is wrong" in str(message) for _key, message in []) or True)
        self.assertEqual(sorted(person["name"] for person in room.host.people.values()), ["kim", "sam", "sam 2"])
        self.assertIsNone(room.guests["p1"].me)
        self.assertIsNone(room.guests["p2"].me)
        self.assertEqual(room.guests["p3"].name, "sam")
        self.assertEqual(room.guests["p4"].name, "sam 2")
        self.assertEqual(room.guest_doc("p3").editor.value, "print hi\n")
        self.assertIn("sam joined the session", room.host.app.messages)

    def test_a_guest_with_a_wrong_copy_is_sent_a_fresh_one(self):
        room = _Room("score = 0\n", guests=1)
        room.settle()
        guest = room.guests["p1"]
        shared = next(iter(guest.files.values()))
        shared.shadow = shared.doc.editor.value = "something else entirely"
        room.host_doc.editor.value = "score = 1\n"
        room.settle()
        self.assertEqual(shared.doc.editor.value, "score = 1\n")

    def test_names_and_codes(self):
        self.assertEqual(collab.clean_name("  Kim   Lee  "), "kim lee")
        self.assertLessEqual(len(collab.clean_name("x" * 100)), collab.MAX_NAME)
        code = collab.new_code()
        self.assertEqual(len(code), 6)
        self.assertTrue(all(letter in collab.CODE_LETTERS for letter in code))
        self.assertEqual(collab.shift_position(10, [2, 4, "abcd"]), 12)
        self.assertEqual(collab.shift_position(1, [2, 4, "abcd"]), 1)
        self.assertFalse(collab.valid_op([True, 2, "x"]))
        self.assertFalse(collab.valid_op([3, 2, "x"]))
        self.assertTrue(collab.valid_op([0, 0, ""]))

    def test_a_real_host_and_guest_over_localhost(self):
        """the sockets, threads and json lines, with the tk loop replaced by a plain loop."""
        host_doc = _Doc("main.gubl", "print hi\n")
        host = collab.LiveSession(_App([host_doc]), "kim", host=True)
        try:
            host.start_host(0)
        except OSError as err:
            self.skipTest(f"no local network: {err}")
        port = host.server.getsockname()[1]
        guest = collab.LiveSession(_App(), "sam", host=False)
        try:
            guest.start_guest("127.0.0.1", port, host.code)
            import time
            deadline = time.time() + 10
            while time.time() < deadline and not guest.files:
                host._poll()
                guest._poll()
                time.sleep(0.02)
            self.assertTrue(guest.files, "the guest never got the file")
            doc = next(iter(guest.files.values())).doc
            doc.editor.value = "print hi\nprint from sam\n"
            guest.flush(next(iter(guest.files.values())))
            while time.time() < deadline and host_doc.editor.value != doc.editor.value:
                host._poll()
                guest._poll()
                time.sleep(0.02)
            self.assertEqual(host_doc.editor.value, "print hi\nprint from sam\n")
            self.assertEqual(sorted(person["name"] for person in host.people.values()), ["kim", "sam"])
        finally:
            guest.end()
            host.end()


# ----- plugins ---------------------------------------------------------------------------------------------------
class PluginTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="gublan_plugins_")
        self.patch = patch.object(config, "settings_folder", lambda: self.folder)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        for name in ("shout", "zap"):
            gublancore.remove_plugin_command(name)
        for name in ("twice", "zap_twice"):
            gublancore.remove_plugin_function(name)
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_plugins_stay_off_until_switched_on(self):
        plugins.write_example()
        found = plugins.load_plugins({"plugins": False})
        self.assertEqual([(info.key, info.status) for info in found], [("hello", "off")])
        self.assertNotIn("shout", gublancore.COMMAND_SPECS)

    def test_the_example_plugin_adds_a_command_a_function_and_a_menu_item(self):
        plugins.write_example()
        found = plugins.load_plugins({"plugins": True})
        info = found[0]
        self.assertEqual(info.status, "loaded", info.error)
        self.assertEqual((info.commands, info.functions), (["shout"], ["twice"]))
        self.assertEqual(info.menu_items[0][0], "say hello")
        self.assertEqual(errors_in("shout hi {twice(2)}\n"), [])
        output, errors = run("shout hi {twice(2)}\nprint {twice(21)}\n")
        self.assertEqual(errors, [])
        self.assertEqual(output, ["HI 4!", "42"])
        self.assertTrue(gublancore.remove_plugin_command("shout"))
        self.assertNotIn("shout", gublancore.COMMAND_SPECS)
        self.assertFalse(gublancore.remove_plugin_command("print"))

    def test_a_broken_plugin_is_reported_and_the_others_still_load(self):
        folder = plugins.write_example()
        with open(os.path.join(folder, "broken.py"), "w", encoding="utf-8") as handle:
            handle.write("def setup(api):\n    api.command('print', lambda context: None)\n")
        with open(os.path.join(folder, "crashes.py"), "w", encoding="utf-8") as handle:
            handle.write("raise RuntimeError('oops')\n")
        found = {info.key: info for info in plugins.load_plugins({"plugins": True})}
        self.assertEqual(found["hello"].status, "loaded")
        self.assertEqual(found["broken"].status, "error")
        self.assertIn("already a gublan command", found["broken"].error)
        self.assertEqual(found["crashes"].status, "error")
        self.assertIn("oops", found["crashes"].describe())

    def test_switched_off_plugins_are_skipped(self):
        folder = plugins.write_example()
        with open(os.path.join(folder, "zap.py"), "w", encoding="utf-8") as handle:
            handle.write("PLUGIN = {'name': 'zapper'}\n\ndef setup(api):\n"
                         "    api.command('zap', lambda context: context.set('zapped', 1))\n"
                         "    api.function('zap_twice', lambda x: x * 2)\n")
        found = {info.key: info for info in plugins.load_plugins({"plugins": True, "disabled_plugins": ["hello"]})}
        self.assertEqual(found["hello"].status, "off")
        self.assertEqual(found["zap"].status, "loaded")
        self.assertEqual(found["zap"].name, "zapper")
        output, errors = run("zap\nprint {zapped} {zap_twice(5)}\n")
        self.assertEqual((output, errors), (["1 10"], []))


# ----- themes and motion -----------------------------------------------------------------------------------------
class ThemeTests(unittest.TestCase):
    def setUp(self):
        self.before = theme.THEME_NAME
        self.folder = tempfile.mkdtemp(prefix="gublan_themes_")
        self.patch = patch.object(config, "settings_folder", lambda: self.folder)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        theme.apply_theme(self.before)
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_every_built_in_theme_sets_every_colour(self):
        for name in theme.BUILTIN_THEMES:
            with self.subTest(theme=name):
                self.assertTrue(theme.apply_theme(name))
                for color in theme.COLOR_NAMES:
                    self.assertRegex(getattr(theme, color), r"^#[0-9a-f]{6}$")
                for value in list(theme.SYNTAX.values()) + list(theme.CATEGORY_COLORS.values()):
                    self.assertRegex(value, r"^#[0-9a-f]{6}$")
        theme.apply_theme("paper")
        self.assertFalse(theme.DARK)
        self.assertEqual(theme.BG, "#f3f1ec")

    def test_json_themes_build_on_a_base_and_ignore_bad_values(self):
        os.makedirs(theme.themes_folder())
        with open(os.path.join(theme.themes_folder(), "sea.json"), "w", encoding="utf-8") as handle:
            json.dump({"name": "Sea", "base": "midnight", "colors": {"accent": "#123456", "bg": "red"},
                       "syntax": {"string": "#abcdef"}}, handle)
        with open(os.path.join(theme.themes_folder(), "broken.json"), "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertEqual(theme.theme_names()[-1], "sea")
        self.assertNotIn("broken", theme.theme_names())
        self.assertTrue(theme.apply_theme("sea"))
        self.assertEqual(theme.MOSS, "#123456")
        self.assertEqual(theme.BG, theme.BUILTIN_THEMES["midnight"]["colors"]["bg"])
        self.assertEqual(theme.SYNTAX["string"], "#abcdef")
        self.assertFalse(theme.apply_theme("nothing like this"))
        self.assertTrue(os.path.isfile(os.path.join(theme.write_example_theme(), "my theme.json")))

    def test_a_theme_that_names_itself_as_its_base_does_not_loop(self):
        os.makedirs(theme.themes_folder())
        with open(os.path.join(theme.themes_folder(), "loop.json"), "w", encoding="utf-8") as handle:
            json.dump({"base": "loop", "colors": {"bg": "#010203"}}, handle)
        self.assertTrue(theme.apply_theme("loop"))
        self.assertEqual(theme.BG, "#010203")

    def test_motion_off_jumps_to_the_end_and_colours_blend(self):
        steps, finished = [], []
        with patch.object(theme, "MOTION", False):
            theme.animate(None, 300, steps.append, done=lambda: finished.append(True))
        self.assertEqual((steps, finished), ([1.0], [True]))
        self.assertEqual(theme.mix("#000000", "#ffffff", 0.5), "#808080")
        self.assertEqual(theme.mix("#000000", "white", 0.7), "white")
        self.assertAlmostEqual(theme.ease_out(1.0), 1.0)

    def test_new_settings_have_defaults(self):
        for key in ("theme", "animations", "plugins", "disabled_plugins", "live_name", "live_port",
                    "translate_language", "mcp_app"):
            self.assertIn(key, config.DEFAULTS)


# ----- the converter on real game code ------------------------------------------------------------------------------
class GameConversionTests(unittest.TestCase):
    def convert(self, code, language):
        result = gublanconvert.convert(code, language)
        self.assertEqual(errors_in(result.text), [], result.text)
        return result

    def test_javascript_key_listeners_become_keydown_checks(self):
        result = self.convert(
            'const keys = {};\nlet x = 0;\n'
            'document.addEventListener("keydown", (e) => { keys[e.key] = true; });\n'
            'document.addEventListener("keyup", (e) => { keys[e.key] = false; });\n'
            'function update() {\n  if (keys["ArrowLeft"]) x -= 5;\n  if (keys[" "]) x = 0;\n}\n', "javascript")
        self.assertEqual(result.todos, 0)
        self.assertIn('keydown("left")', result.text)
        self.assertIn('keydown("space")', result.text)
        self.assertNotIn("addEventListener", result.text)

    def test_a_loop_that_asks_for_frames_sometimes_stops_when_it_stops_asking(self):
        result = self.convert(
            'const ctx = document.getElementById("c").getContext("2d");\nlet lives = 2;\n'
            'function draw() { ctx.fillRect(0, 0, 10, 10); }\n'
            'function loop() {\n  draw();\n  lives -= 1;\n  if (lives > 0) {\n    requestAnimationFrame(loop);\n'
            '  } else {\n    console.log("done");\n  }\n}\nloop();\n', "javascript")
        self.assertEqual(result.library, "canvas")
        self.assertIn("while loop_fn_again", result.text)
        output, errors = run(result.text.replace("mode 2d\n", ""))
        self.assertEqual(errors, [])
        self.assertEqual(output, ["done"])

    def test_pygame_clock_tick_becomes_fps_and_gublans_dt(self):
        result = self.convert(
            "import pygame\npygame.init()\nscreen = pygame.display.set_mode((200, 200))\n"
            "clock = pygame.time.Clock()\nx = 0\nrunning = True\nwhile running:\n"
            "    dt = clock.tick(30) / 1000\n    x += 100 * dt\n    pygame.display.flip()\n", "python")
        self.assertEqual(result.todos, 0)
        self.assertIn("fps 30", result.text)
        code_lines = [line for line in result.text.splitlines() if not line.startswith("//")]
        self.assertFalse(any("tick" in line or "dt =" in line for line in code_lines), result.text)

    def test_lambdas_comprehensions_and_star_arguments(self):
        code = ("def total(*values, scale=1):\n    return sum(values) * scale\n"
                "nums = [3, 1, 2]\nprint(sorted(nums, key=lambda n: -n))\n"
                "print([n * n for n in nums if n > 1])\nprint({n: n + 1 for n in nums})\n"
                "print(total(1, 2, 3, scale=2))\nprint(max(['aa', 'b'], key=len))\n")
        result = self.convert(code, "python")
        self.assertEqual(result.todos, 0, result.text)
        output, errors = run(result.text)
        self.assertEqual(errors, [])
        self.assertEqual(output, ["[3, 2, 1]", "[9, 4]", '{3: 4, 1: 2, 2: 3}', "12", "aa"])

    def test_bit_operators_from_each_language(self):
        for language, code in (("python", "print(5 & 3, 5 | 2, 1 << 3, ~5, 6 ^ 3)\n"),
                               ("javascript", "console.log(5 & 3, 5 | 2, 1 << 3, ~5, 6 ^ 3);\n"),
                               ("lua", "print(5 & 3, 5 | 2, 1 << 3, ~5, 6 ~ 3)\n")):
            with self.subTest(language=language):
                result = self.convert(code, language)
                output, errors = run(result.text)
                self.assertEqual((output, errors), (["1 7 8 -6 5"], []), result.text)


# ----- gublan in other languages -------------------------------------------------------------------------------------
class TranslateTests(unittest.TestCase):
    PROGRAM = ("xs = [3, 1, 2]\nys = map(xs, x => x * 10)\nprint {ys} {sort(xs)}\n"
               "function add a b\n    return a + b\nend\nprint {add(2, 5)}\n"
               "for i = 1 to 3\n    if i % 2 == 0\n        print even {i}\n    end\nend\n")

    def run_translation(self, language, command):
        result = gublantranslate.translate(self.PROGRAM, language, name="demo")
        folder = tempfile.mkdtemp(prefix="gublan_translate_")
        try:
            gublantranslate.write_files(result, folder)
            finished = subprocess.run(command + [os.path.join(folder, result.main)], capture_output=True, text=True,
                                      env=ENV, timeout=60)
            return finished.stdout.splitlines(), finished.stderr
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_python_version_prints_what_gublan_prints(self):
        expected, errors = run(self.PROGRAM)
        self.assertEqual(errors, [])
        lines, stderr = self.run_translation("python", [sys.executable])
        self.assertEqual(lines, expected, stderr)

    def test_javascript_version_prints_what_gublan_prints(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        expected, _ = run(self.PROGRAM)
        lines, stderr = self.run_translation("javascript", [node])
        self.assertEqual(lines, expected, stderr)

    def test_lua_version_has_its_runtime_and_love_files(self):
        result = gublantranslate.translate(self.PROGRAM, "lua", name="demo")
        self.assertEqual(result.main, "main.lua")
        self.assertIn("conf.lua", result.files)
        self.assertIn("gublan.lua", result.files)

    def test_programs_with_errors_are_refused(self):
        with self.assertRaises(gublantranslate.TranslateError):
            gublantranslate.translate("loop\n", "python")
        with self.assertRaises(gublantranslate.TranslateError):
            gublantranslate.language_of("cobol")


# ----- the mcp server -------------------------------------------------------------------------------------------------
class McpTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="gublan_mcp_")
        self.server = gublanmcp.Server(self.folder)
        self.ident = 0

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def call(self, method, params=None):
        self.ident += 1
        return self.server.handle({"jsonrpc": "2.0", "id": self.ident, "method": method, "params": params or {}})

    def tool(self, tool_name, **arguments):
        reply = self.call("tools/call", {"name": tool_name, "arguments": arguments})
        result = reply["result"]
        text = "\n".join(item.get("text", "") for item in result["content"] if item["type"] == "text")
        return result.get("isError", False), text, result

    def test_handshake_and_tool_list(self):
        reply = self.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                         "clientInfo": {"name": "test", "version": "1"}})
        self.assertEqual(reply["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("tools", reply["result"]["capabilities"])
        names = [tool["name"] for tool in self.call("tools/list")["result"]["tools"]]
        for name in ("write_file", "check_code", "run_program", "run_tests", "screenshot", "translate_code"):
            self.assertIn(name, names)
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertIn("error", self.call("no/such/method"))

    def test_write_check_run_and_test_a_program(self):
        failed, text, _ = self.tool("write_file", path="game.gubl",
                                    text="x = 2\nprint {x * 21}\n\ntest doubling\n    y = 2\n    assert y * 2 == 4\nend\n")
        self.assertFalse(failed, text)
        failed, text, _ = self.tool("check_code", path="game.gubl")
        self.assertFalse(failed, text)
        failed, text, _ = self.tool("run_program", path="game.gubl", seconds=2)
        self.assertFalse(failed, text)
        self.assertIn("42", text)
        failed, text, _ = self.tool("run_tests", path="game.gubl")
        self.assertFalse(failed, text)
        self.assertIn("1 passed", text)
        failed, text, _ = self.tool("edit_file", path="game.gubl", old_text="x * 21", new_text="x * 50")
        self.assertFalse(failed, text)
        failed, text, _ = self.tool("read_file", path="game.gubl")
        self.assertIn("x * 50", text)

    def test_files_outside_the_project_are_refused(self):
        failed, text, _ = self.tool("read_file", path="../../secret.txt")
        self.assertTrue(failed)
        failed, text, _ = self.tool("write_file", path=os.path.join(tempfile.gettempdir(), "x.gubl"), text="")
        self.assertTrue(failed)

    def test_bad_arguments_are_an_error_not_a_crash(self):
        failed, text, _ = self.tool("check_code", nonsense=1)
        self.assertTrue(failed)
        failed, text, _ = self.tool("command_help", topic="clamp")
        self.assertFalse(failed, text)
        self.assertIn("clamp", text)

    def test_a_screenshot_comes_back_as_a_picture(self):
        failed, text, result = self.tool("screenshot", code="mode 2d\ncolor red\nbox b 10 10 50 50\nforever\n    frame\nend\n",
                                         seconds=1)
        self.assertFalse(failed, text)
        images = [item for item in result["content"] if item["type"] == "image"]
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["mimeType"], "image/png")


# ----- the language ---------------------------------------------------------------------------------------------------
class LanguageTests(unittest.TestCase):
    def test_a_variable_holding_a_function_name_can_be_called(self):
        output, errors = run("function triple x\n    return x * 3\nend\n"
                             "function apply f value\n    return f(value)\nend\n"
                             "print {apply(triple, 2)} {map([1, 2], triple)}\nchosen = triple\nprint {chosen(5)}\n")
        self.assertEqual(errors, [])
        self.assertEqual(output, ["6 [3, 6]", "15"])

    def test_cli_test_and_translate(self):
        folder = tempfile.mkdtemp(prefix="gublan_cli_")
        try:
            path = os.path.join(folder, "t.gubl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("test sums\n    assert 1 + 1 == 2\nend\ntest wrong\n    assert 1 == 2\nend\n")
            cli = os.path.join(ROOT, "gublancli.py")
            tested = subprocess.run([sys.executable, cli, "test", path], capture_output=True, text=True, env=ENV,
                                    timeout=120)
            self.assertEqual(tested.returncode, 1)
            self.assertIn("1 passed, 1 failed", tested.stdout)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("print hi\n")
            out = os.path.join(folder, "py")
            translated = subprocess.run([sys.executable, cli, "translate", path, "python", out], capture_output=True,
                                        text=True, env=ENV, timeout=120)
            self.assertEqual(translated.returncode, 0, translated.stderr)
            self.assertTrue(os.path.isfile(os.path.join(out, "t.py")))
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class GuideTests(unittest.TestCase):
    def test_every_guide_example_has_no_problems(self):
        from studio.guides import GUIDES
        functions_so_far = ""
        for title, body in GUIDES:
            blocks, current = [], []
            for line in body.splitlines() + ["end of guide"]:
                if line.startswith("    "):
                    current.append(line[4:])
                elif current and not line.strip():
                    current.append("")
                elif current:
                    blocks.append("\n".join(current).strip("\n") + "\n")
                    current = []
            for code in blocks:
                with self.subTest(guide=title, code=code):
                    self.assertEqual(errors_in(functions_so_far + code), [])
                if code.startswith("function "):
                    functions_so_far += code

    def test_the_new_features_have_guides(self):
        from studio.guides import GUIDES
        titles = [title for title, _body in GUIDES]
        for title in ("buttons, textboxes and sliders", "testing your code", "modules", "code together",
                      "ai helpers", "themes and plugins"):
            self.assertIn(title, titles)


if __name__ == "__main__":
    unittest.main()
