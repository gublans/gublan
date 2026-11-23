"""tests for what is new in 1.0.7: the new built-in functions and commands, the look of game windows and popups,
the studio's soft sounds, cursor and typing effects, and the web playground's reference, projects and looks."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
WEB = os.path.join(ROOT, "web")
if WEB not in sys.path:
    sys.path.insert(0, WEB)

import pygame  # noqa: E402

import build_site  # noqa: E402
import gublancore  # noqa: E402
import gublanmcp  # noqa: E402
import gublantranslate  # noqa: E402
from gublancore import GAME_STYLE, GublanRuntime, game_style, wrap_words  # noqa: E402
from studio import caret, config, exporter, sounds, version  # noqa: E402
from studio.editor import bracket_depths  # noqa: E402

ENV = dict(os.environ, PYGAME_HIDE_SUPPORT_PROMPT="1", SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
ENV.pop("GUBLAN_STYLE", None)


def run(source, style=None):
    output, errors = [], []
    runtime = GublanRuntime(onlog=output.append, style=style,
                            onerror=lambda message, _file, line: errors.append((line, message)))
    runtime.run(source)
    return output, errors


def translated_output(source, language, command):
    result = gublantranslate.translate(source, language, name="demo")
    folder = tempfile.mkdtemp(prefix="gublan_translate_")
    try:
        gublantranslate.write_files(result, folder)
        finished = subprocess.run(command + [os.path.join(folder, result.main)], capture_output=True, text=True,
                                  env=ENV, timeout=60)
        return finished.stdout.splitlines(), finished.stderr
    finally:
        shutil.rmtree(folder, ignore_errors=True)


class VersionTests(unittest.TestCase):
    def test_version_is_107(self):
        self.assertEqual(version.VERSION, "1.0.7")
        self.assertEqual(gublanmcp._version(), "1.0.7")

    def test_new_settings_have_defaults(self):
        for key in ("smooth_caret", "caret_style", "caret_motion", "caret_blink", "caret_width", "typing_effect",
                    "smooth_scroll", "sounds", "sound_volume", "sound_pack", "typing_sounds", "game_style"):
            self.assertIn(key, config.DEFAULTS)
        self.assertIn(config.DEFAULTS["caret_style"], caret.CARET_STYLES)
        self.assertIn(config.DEFAULTS["caret_blink"], caret.CARET_BLINKS)
        self.assertIn(config.DEFAULTS["typing_effect"], caret.TYPING_EFFECTS)
        self.assertIn(config.DEFAULTS["sound_pack"], sounds.PACKS)
        self.assertEqual(config.DEFAULTS["game_style"], {})


# ----- new built-in functions ------------------------------------------------------------------------------------
FUNCTIONS = """xs = [5, 3, 8, 1]
print {take(xs, 2)} {drop(xs, 2)} {first(xs)} {last(xs)}
print {chunk([1, 2, 3, 4, 5], 2)}
print {median(xs)} {product([2, 3, 4])} {gcd(12, 18)} {hypot(3, 4)}
print {fract(2.75)} {snap(37, 16)} {between(5, 1, 10)} {smoothstep(0, 10, 5)}
print {commas(1234567)} {ordinal(2)} {ordinal(11)} {ordinal(23)} {plural(3, "coin")} {plural(1, "coin")}
print {fill(0, 3)} {without([1, 2, 1, 3], 1)} {enumerate(["a", "b"])}
m = {"a": 1, "b": 2}
extra = {"b": 5}
print {entries(m)} {frompairs([["x", 9]])} {merge(m, extra)} {get(m, "z", 7)} {get(xs, 1, 0)}
print {minby(xs, n => n)} {maxby(xs, n => n)} {groupby(["hi", "yo", "hey"], w => len(w))}
print {wraptext("the quick brown fox jumps", 10)}
print {ease(0.5, "linear")} {ease(0, "out")} {ease(1, "bounce")}
print {mixcolor("black", "white", 0.5)}
function shout word
    local loud = upper(word)
    return loud
end
loud = "quiet"
print {shout("hey")} {loud}
"""

FUNCTION_OUTPUT = [
    "[5, 3] [8, 1] 5 1",
    "[[1, 2], [3, 4], [5]]",
    "4 24 6 5",
    "0.75 32 true 0.5",
    "1,234,567 2nd 11th 23rd 3 coins 1 coin",
    '[0, 0, 0] [2, 3] [[0, "a"], [1, "b"]]',
    '[["a", 1], ["b", 2]] {x: 9} {a: 1, b: 5} 7 3',
    '1 8 {2: ["hi", "yo"], 3: ["hey"]}',
    '["the quick", "brown fox", "jumps"]',
    "0.5 0 1",
    "[126, 126, 126]",
    "HEY quiet",
]


class FunctionTests(unittest.TestCase):
    def test_new_functions_give_the_right_answers(self):
        output, errors = run(FUNCTIONS)
        self.assertEqual(errors, [])
        self.assertEqual(output, FUNCTION_OUTPUT)

    def test_every_new_function_is_documented(self):
        for name in ("take", "drop", "first", "last", "chunk", "median", "product", "gcd", "hypot", "fract", "snap",
                     "between", "smoothstep", "commas", "ordinal", "plural", "fill", "without", "enumerate",
                     "entries", "frompairs", "merge", "get", "minby", "maxby", "groupby", "wraptext", "ease",
                     "mixcolor", "randomcolor", "cooldown", "pulse", "after", "scrollx", "scrolly"):
            self.assertIn(name, gublancore.EXPRESSION_FUNCTIONS, name)

    def test_local_only_lives_inside_its_function(self):
        output, errors = run("n = 1\nfunction bump\n    local n = 50\n    n += 1\n    print {n}\nend\n"
                             "bump()\nprint {n}\n")
        self.assertEqual((output, errors), (["51", "1"], []))

    def test_timers_by_name(self):
        output, errors = run('print {cooldown("a", 5)} {cooldown("a", 5)} {after("b", 100)} {pulse("c", 100)}\n')
        self.assertEqual(errors, [])
        self.assertEqual(output, ["true false false false"])

    def test_a_bad_easing_says_which_ones_exist(self):
        _output, errors = run('print {ease(0.5, "wobbly")}\n')
        self.assertEqual(len(errors), 1)
        self.assertIn("bounce", errors[0][1])


class TranslateTests(unittest.TestCase):
    def test_python_version_prints_what_gublan_prints(self):
        lines, stderr = translated_output(FUNCTIONS, "python", [sys.executable])
        self.assertEqual(lines, FUNCTION_OUTPUT, stderr)

    def test_javascript_version_prints_what_gublan_prints(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        lines, stderr = translated_output(FUNCTIONS, "javascript", [node])
        self.assertEqual(lines, FUNCTION_OUTPUT, stderr)

    def test_a_word_that_names_a_function_stays_a_word(self):
        source = "print go first then last and take a break\n"
        expected, errors = run(source)
        self.assertEqual((expected, errors), (["go first then last and take a break"], []))
        lines, stderr = translated_output(source, "python", [sys.executable])
        self.assertEqual(lines, expected, stderr)
        node = shutil.which("node")
        if node:
            lines, stderr = translated_output(source, "javascript", [node])
            self.assertEqual(lines, expected, stderr)


# ----- new commands ------------------------------------------------------------------------------------------------
class CommandTests(unittest.TestCase):
    def test_new_commands_run_in_a_window(self):
        output, errors = run(
            "mode 2d\nellipse egg 100 80 40 60\npolygon roof 100 100 150 50 200 100\nbox hud 10 10 50 20\n"
            "fixed hud\nlayer egg 2\nopacity roof 0.5\ntween egg y 40 0.1 bounce\nparticles 200 150 10\n"
            "scroll 30 0\nshake 4 0.1\nbeep 440 0.05\nloop 8\n    frame\nend\n"
            "print {scrollx()} {scrolly()} {egg.y}\n")
        self.assertEqual(errors, [])
        self.assertEqual(output, ["30 0 40"])

    def test_every_new_command_is_documented(self):
        for name in ("beep", "ellipse", "fixed", "layer", "local", "opacity", "particles", "polygon", "scroll",
                     "shake", "tween"):
            self.assertIn(name, gublancore.COMMAND_SPECS, name)
            category, usage, _parts, summary, example = gublancore.COMMAND_SPECS[name]
            self.assertTrue(usage.startswith(name) and summary and example.startswith(name), name)

    def test_the_checker_knows_the_new_commands(self):
        problems = gublancore.analyze_source("mode 2d\nellipse egg 1 2 3 4\ntween egg x 5 0.2 out\nlayer egg 1\n")
        self.assertEqual([item for item in problems if item.get("severity", "error") == "error"], [])


# ----- the look of game windows and popups --------------------------------------------------------------------------
class GameStyleTests(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.pop("GUBLAN_STYLE", None)

    def tearDown(self):
        os.environ.pop("GUBLAN_STYLE", None)
        if self._saved is not None:
            os.environ["GUBLAN_STYLE"] = self._saved

    def test_defaults(self):
        self.assertEqual(game_style(), GAME_STYLE)
        self.assertIsNot(game_style(), GAME_STYLE)

    def test_numbers_are_kept_in_range(self):
        style = game_style({"width": 5, "height": 99999, "fps": 0, "dialog_shade": 140, "dialog_text_size": 3.7,
                            "dialog_border_width": -2, "dialog_width": 10 ** 6})
        self.assertEqual((style["width"], style["height"], style["fps"]), (120, 4096, 1))
        self.assertEqual((style["dialog_shade"], style["dialog_text_size"], style["dialog_border_width"],
                          style["dialog_width"]), (100, 10, 0, 1600))

    def test_bad_values_are_skipped(self):
        style = game_style({"dialog_background": "not a colour", "dialog_position": "sideways",
                            "dialog_animation": "explode", "show_fps": "yes", "width": True, "nonsense": 1,
                            "dialog_hints": False, "title": "x" * 500})
        for key in ("dialog_background", "dialog_position", "dialog_animation", "show_fps", "width"):
            self.assertEqual(style[key], GAME_STYLE[key], key)
        self.assertNotIn("nonsense", style)
        self.assertFalse(style["dialog_hints"])
        self.assertEqual(len(style["title"]), 120)

    def test_the_environment_sets_it_and_overrides_win(self):
        os.environ["GUBLAN_STYLE"] = json.dumps({"dialog_animation": "slide", "dialog_accent": "#ff0000"})
        self.assertEqual(game_style()["dialog_animation"], "slide")
        both = game_style({"dialog_accent": "gold"})
        self.assertEqual((both["dialog_animation"], both["dialog_accent"]), ("slide", "gold"))
        os.environ["GUBLAN_STYLE"] = "{not json"
        self.assertEqual(game_style(), GAME_STYLE)

    def test_the_window_starts_at_the_chosen_size(self):
        output, errors = run("mode 2d\nframe\nprint {screen_width} {screen_height}\n",
                             style={"width": 400, "height": 300})
        self.assertEqual((output, errors), (["400 300"], []))

    def test_the_popup_looks_are_all_valid(self):
        from studio.dialogs import POPUP_LOOKS, STYLE_DEMO, WINDOW_SIZES
        for name, look in POPUP_LOOKS.items():
            style = game_style(look)
            for key, value in look.items():
                self.assertEqual(style[key], value, f"{name} {key}")
        for width, height in WINDOW_SIZES:
            self.assertEqual((game_style({"width": width, "height": height})["width"]), width)
        problems = gublancore.analyze_source(STYLE_DEMO)
        self.assertEqual([item for item in problems if item.get("severity", "error") == "error"], [])


class DialogDrawingTests(unittest.TestCase):
    def test_wrap_words_fits_the_width(self):
        pygame.font.init()
        font = pygame.font.Font(None, 24)
        lines = wrap_words("the quick brown fox jumps over the lazy dog\nnew line " + "x" * 80, font, 120)
        self.assertGreater(len(lines), 4)
        self.assertIn("new line", " ".join(lines))
        for line in lines:
            self.assertLessEqual(font.size(line)[0], 120, line)
        self.assertEqual(wrap_words("", font, 100), [""])

    def test_popups_draw_with_every_animation_and_position(self):
        for animation in gublancore.DIALOG_ANIMATIONS:
            for position in gublancore.DIALOG_POSITIONS:
                with self.subTest(animation=animation, position=position):
                    runtime = GublanRuntime(style={"dialog_animation": animation, "dialog_position": position,
                                                   "width": 400, "height": 300, "dialog_background": "#ff0000",
                                                   "dialog_shade": 0})
                    runtime.reset()
                    runtime.initstage("2d")
                    try:
                        for progress in (0.2, 0.6, 1.0):
                            runtime._draw_dialog("a long message that has to wrap onto more than one line",
                                                 value="abc", is_input=True, cursor=2, anchor=0,
                                                 progress=progress)
                        rect = runtime._dialog_rect
                        self.assertEqual(runtime.screen.get_at((rect.centerx, rect.y + 6))[:3], (255, 0, 0))
                        if position == "top":
                            self.assertEqual(rect.y, 20)
                        elif position == "bottom":
                            self.assertEqual(rect.bottom, 280)
                        else:
                            self.assertAlmostEqual(rect.centery, 150, delta=1)
                    finally:
                        pygame.quit()


class ExportStyleTests(unittest.TestCase):
    def test_exported_programs_keep_the_style(self):
        text = exporter.program_text("print hi\n", "demo", False, style={"dialog_animation": "fade"})
        compile(text, "program.py", "exec")
        self.assertIn("'dialog_animation': 'fade'", text)
        plain = exporter.program_text("print hi\n", "demo", False)
        compile(plain, "program.py", "exec")
        self.assertIn("STYLE = None", plain)

    def test_web_pages_carry_the_style_safely(self):
        result = gublantranslate.translate("print hi\n", "javascript", name="demo",
                                           style={"title": "</script><b>", "dialog_accent": "gold"})
        page = result.files["index.html"]
        self.assertIn("globalThis.GUBLAN_STYLE = ", page)
        self.assertNotIn("</script><b>", page)
        self.assertIn("\\u003c/script>", page)
        bare = gublantranslate.translate("print hi\n", "javascript", name="demo").files["index.html"]
        self.assertNotIn("GUBLAN_STYLE", bare)

    def test_the_javascript_runtime_understands_studio_names(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        script = ("globalThis.GUBLAN_STYLE = {dialog_background: '#123456', dialog_text_size: 25, dialog_shade: 40, "
                  "dialog_animation: 'none', dialog_width: 300, width: 320, height: 200, dialog_hints: true};"
                  "const G = require(process.argv[1]);"
                  "console.log(JSON.stringify([G.style.dialog, G.style.size, G.style.shade, G.style.animate, "
                  "G.style.boxWidth, G.screen_width, G.screen_height, G.style.hints]));")
        done = subprocess.run([node, "-e", script, os.path.join(ROOT, "runtimes", "gublan_runtime.js")],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), ["#123456", 18, 0.4, False, 300, 320, 200, True])


# ----- the studio's sounds, cursor and brackets ---------------------------------------------------------------------
class SoundTests(unittest.TestCase):
    def test_every_sound_in_every_set_is_a_real_wav(self):
        for pack in sounds.PACKS:
            for event in sounds.EVENTS:
                with self.subTest(pack=pack, event=event):
                    data = sounds.render(event, pack, 45)
                    with wave.open(io.BytesIO(data)) as handle:
                        self.assertEqual((handle.getnchannels(), handle.getsampwidth(), handle.getframerate()),
                                         (1, 2, sounds.RATE))
                        self.assertGreater(handle.getnframes(), sounds.RATE // 50)
            self.assertIn(pack, sounds.ABOUT)

    def test_volume_scales_and_never_clips(self):
        def peak(volume):
            with wave.open(io.BytesIO(sounds.render("done", "soft", volume))) as handle:
                frames = handle.readframes(handle.getnframes())
            return max(abs(int.from_bytes(frames[i:i + 2], "little", signed=True)) for i in range(0, len(frames), 2))
        self.assertEqual(peak(0), 0)
        self.assertLess(peak(20), peak(80))
        self.assertLessEqual(peak(100), 32767)

    def test_unknown_sounds_and_switched_off_sounds_are_quiet(self):
        with self.assertRaises(KeyError):
            sounds.render("trumpet")
        saved = dict(sounds._settings)
        try:
            sounds.configure({"sounds": False})
            self.assertFalse(sounds.play("run"))
            sounds.configure({"sounds": True, "typing_sounds": False})
            self.assertFalse(sounds.play("type"))
            self.assertFalse(sounds.play("trumpet", force=True))
        finally:
            sounds.configure(saved)


class CaretTests(unittest.TestCase):
    def test_the_cursor_stays_visible_right_after_it_moves(self):
        for kind in caret.CARET_BLINKS:
            self.assertEqual(caret._blink_amount(kind, 0.1), 1.0, kind)
        self.assertEqual(caret._blink_amount("solid", 12.3), 1.0)

    def test_blink_switches_and_fade_eases(self):
        amounts = {round(caret._blink_amount("blink", 0.5 + step / 100), 3) for step in range(0, 106)}
        self.assertEqual(amounts, {0.0, 1.0})
        fades = [caret._blink_amount("fade", 0.5 + step / 100) for step in range(0, 110)]
        self.assertTrue(all(0.0 <= amount <= 1.0 for amount in fades))
        self.assertTrue(any(0.1 < amount < 0.9 for amount in fades))
        self.assertIn(0.0, fades)

    def test_rainbow_brackets_skip_text_and_comments(self):
        self.assertEqual(bracket_depths("print {max([1, (2)])}"), [(10, 0), (11, 1), (15, 2), (17, 2), (18, 1),
                                                                    (19, 0)])
        self.assertEqual(bracket_depths('set a = len("(not)")'), [(11, 0), (19, 0)])
        self.assertEqual(bracket_depths('    // a comment (with brackets)'), [])


# ----- the web playground ---------------------------------------------------------------------------------------------
class PlaygroundTests(unittest.TestCase):
    def bridge(self, code, *args):
        script = ("import sys, json; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2]); import bridge\n"
                  + code)
        done = subprocess.run([sys.executable, "-I", "-c", script, ROOT, WEB, *args], capture_output=True, text=True,
                              timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_the_reference_has_every_command_function_and_colour(self):
        data = json.loads(self.bridge("print(bridge.reference())"))
        names = {item["name"] for item in data["commands"]}
        self.assertEqual(names, set(gublancore.COMMAND_SPECS))
        functions = {item["name"]: item for item in data["functions"]}
        self.assertEqual(set(functions), set(gublancore.EXPRESSION_FUNCTIONS))
        self.assertTrue(functions["abs"]["usage"].startswith("abs("))
        self.assertTrue(functions["abs"]["summary"])
        self.assertEqual(len(data["colors"]["moss"]), 3)
        self.assertIn("if", data["words"]["openers"])
        self.assertIn("else", data["words"]["middles"])

    def test_project_files_are_written_for_include(self):
        folder = tempfile.mkdtemp(prefix="gublan_project_")
        try:
            with open(os.path.join(folder, "old.gubl"), "w", encoding="utf-8") as handle:
                handle.write("print old\n")
            files = {"helpers.gubl": "function hi\n    print hi\nend\n", "../escape.gubl": "print x\n",
                     ".hidden.gubl": "print h\n", "notes.txt": "nope"}
            self.bridge("bridge.set_files(sys.argv[3], sys.argv[4])", json.dumps(files), folder)
            self.assertEqual(sorted(os.listdir(folder)), ["escape.gubl", "helpers.gubl"])
            self.assertFalse(os.path.exists(os.path.join(os.path.dirname(folder), "escape.gubl")))
            output, errors = [], []
            GublanRuntime(onlog=output.append, base_dir=folder,
                          onerror=lambda message, _file, line: errors.append(message)).run(
                "include helpers.gubl\nhi()\n")
            self.assertEqual((output, errors), (["hi"], []))
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_the_site_offers_the_studios_looks(self):
        themes, accents, game = build_site._looks()
        from studio import theme
        self.assertEqual(set(themes), set(theme.BUILTIN_THEMES))
        for name, info in themes.items():
            self.assertIn("bg", info["colors"], name)
            self.assertIsInstance(info["dark"], bool)
        self.assertEqual([item["color"] for item in accents], [color for _name, color in theme.accent_choices()])
        self.assertEqual(game["defaults"], GAME_STYLE)
        self.assertEqual(list(game["animations"]), list(gublancore.DIALOG_ANIMATIONS))
        self.assertIn("arcade", game["looks"])
        self.assertIn("mode 2d", game["demo"])

    def test_the_page_scripts_are_valid_javascript(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        done = subprocess.run([node, "--check", os.path.join(WEB, "playground.js")], capture_output=True, text=True,
                              timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)


class GuideTests(unittest.TestCase):
    def test_the_107_features_have_guides(self):
        from studio.guides import GUIDES
        bodies = dict(GUIDES)
        self.assertIn("tween", bodies["moving things smoothly"])
        self.assertIn("wraptext", bodies["handy functions"])
        self.assertIn("tools > game window and popups", bodies["game window and popups"])
        self.assertIn("typing", bodies["cursor, typing and sounds"])


if __name__ == "__main__":
    unittest.main()
