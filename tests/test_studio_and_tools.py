"""tests for the newer language features, the converter, export planning, the studio helpers and the cli."""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import gublanconvert  # noqa: E402
from gublancore import COMMAND_SPECS, GublanRuntime, analyze_source  # noqa: E402
from studio import blocks, docsgen, exporter, theme  # noqa: E402
from studio.app import find_includes  # noqa: E402
from studio.dialogs import _score  # noqa: E402
from studio.editor import line_tokens  # noqa: E402


def run(source, answers=(), base_dir=None):
    output, errors = [], []
    answers = list(answers)
    runtime = GublanRuntime(onlog=output.append, oninput=lambda _prompt: answers.pop(0), base_dir=base_dir,
                            onerror=lambda message, _file, line: errors.append((line, message)))
    runtime.run(source)
    return output, errors


class NewLanguageFeatureTests(unittest.TestCase):
    def test_compound_assignment(self):
        output, errors = run("x = 5\nx += 2\nx -= 1\nx *= 3\nx /= 2\nprint {x}\n"
                             "player = {\"hp\": 10}\nplayer.hp -= 3\nprint {player.hp}")
        self.assertEqual(errors, [])
        self.assertEqual(output, ["9", "7"])

    def test_typed_answers_that_look_like_numbers_become_numbers(self):
        output, _ = run("input age how old?\nprint {age + 1}\ninput name who?\nprint hi {name}", ["12", "sam"])
        self.assertEqual(output, ["13", "hi sam"])

    def test_else_if_and_elif_mean_elseif(self):
        source = ("v = 2\nif v > 5\n    print a\nelse if v > 1\n    print b\nelse\n    print c\nend\n"
                  "if v == 9\n    print x\nelif v == 2\n    print d\nend\n")
        self.assertEqual(analyze_source(source), [])
        self.assertEqual(run(source)[0], ["b", "d"])

    def test_dt_is_zero_before_the_first_frame(self):
        self.assertEqual(run("print {dt}")[0], ["0"])

    def test_unknown_command_suggests_a_close_match(self):
        problems = analyze_source("bo player 1 2 3 4")
        self.assertEqual(len(problems), 1)
        self.assertIn("box", problems[0]["message"])

    def test_errors_inside_braces_are_reported_with_their_line(self):
        _output, errors = run("x = 1\nprint {x / 0}")
        self.assertEqual(errors, [(2, "cannot divide by zero")])
        output, errors = run("print {nmae}")
        self.assertEqual(output, [])
        self.assertEqual(errors[0][0], 1)
        self.assertIn("nmae", errors[0][1])

    def test_braces_that_are_not_expressions_stay_as_text(self):
        self.assertEqual(run("print a {: b} c")[0], ["a {: b} c"])


class ConverterTests(unittest.TestCase):
    SAMPLES = {
        "python": "score = 0\nfor i in range(3):\n    score += i\nprint(f'score {score}')\n"
                  "def add(a, b):\n    return a + b\nprint(add(2, 3))\n",
        "javascript": "let score = 0;\nfor (let i = 0; i < 3; i++) {\n  score += i;\n}\n"
                      "console.log(`score ${score}`);\nfunction add(a, b) { return a + b; }\nconsole.log(add(2, 3));\n",
        "lua": "local score = 0\nfor i = 0, 2 do\n  score = score + i\nend\nprint(\"score \" .. score)\n"
               "local function add(a, b)\n  return a + b\nend\nprint(add(2, 3))\n",
    }

    def test_each_language_converts_to_a_program_that_runs_the_same(self):
        for language, code in self.SAMPLES.items():
            with self.subTest(language=language):
                result = gublanconvert.convert(code, language)
                self.assertEqual(result.language, language)
                self.assertEqual(result.todos, 0)
                self.assertEqual(analyze_source(result.text), [])
                self.assertEqual(run(result.text)[0], ["score 3", "5"])

    def test_language_is_detected_from_the_code(self):
        for language, code in self.SAMPLES.items():
            with self.subTest(language=language):
                self.assertEqual(gublanconvert.detect_language(code), language)
        self.assertEqual(gublanconvert.detect_language("local x = 1\nprint(x)\n"), "lua")
        self.assertEqual(gublanconvert.detect_language("x", filename="game.js"), "javascript")

    def test_names_that_clash_with_commands_are_renamed(self):
        result = gublanconvert.convert(self.SAMPLES["python"], "python")
        self.assertNotRegex(result.text, r"(?m)^function add\b")
        self.assertRegex(result.text, r"(?m)^function add_fn a b$")

    def test_code_that_cannot_be_converted_becomes_a_todo_note(self):
        result = gublanconvert.convert("import socket\ns = socket.socket()\nwith open('x') as f:\n    pass\n",
                                       "python")
        self.assertGreater(result.todos, 0)
        self.assertIn("// todo", result.text)
        self.assertEqual([item for item in analyze_source(result.text) if item.get("severity") == "error"], [])


class ExportPlanTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.outside = tempfile.TemporaryDirectory()
        self.base = self.folder.name
        os.makedirs(os.path.join(self.base, "assets"))
        for name in ("hero.png", "jump sound.wav", "spare.ogg"):
            with open(os.path.join(self.base, "assets", name), "wb") as handle:
                handle.write(b"x")
        self.far = os.path.join(self.outside.name, "far.png")
        with open(self.far, "wb") as handle:
            handle.write(b"x")

    def tearDown(self):
        self.folder.cleanup()
        self.outside.cleanup()

    def test_media_is_found_missing_files_are_reported_and_outside_files_are_copied_in(self):
        source = (f'mode 2d\nimage hero assets/hero.png 1 1\nsound "assets/jump sound.wav"\n'
                  f'image far "{self.far}" 0 0\nimage gone assets/missing.png 0 0\n')
        plan = exporter.plan_export(source, self.base, include_folder=True)
        self.assertEqual(sorted(plan.assets), ["assets/external/far.png", "assets/hero.png",
                                               "assets/jump sound.wav", "assets/spare.ogg"])
        self.assertEqual(plan.missing, [(5, "assets/missing.png")])
        self.assertFalse(plan.console)
        # the bundled program points at the copied file, so the path still works inside the .exe
        self.assertIn('image far "assets/external/far.png" 0 0', plan.source)
        self.assertNotIn(self.far, plan.source)
        self.assertTrue(any("1 file from outside" in note and " is copied" in note for note in plan.notes))

    def test_text_programs_get_a_console_and_only_used_files_without_the_folder(self):
        plan = exporter.plan_export("print hi\n", self.base, include_folder=False)
        self.assertEqual(plan.assets, {})
        self.assertTrue(plan.console)

    def test_build_refuses_missing_media_before_running_pyinstaller(self):
        with patch("studio.exporter.subprocess.run") as fake_run:
            with self.assertRaises(exporter.ExportError) as caught:
                exporter.build("mode 2d\nimage gone assets/missing.png 0 0\n", os.path.join(self.base, "g.exe"),
                               "python", self.base, lambda source, _base: source)
        fake_run.assert_not_called()
        self.assertIn("missing.png", str(caught.exception))

    def test_pyinstaller_status_tells_missing_from_broken(self):
        cases = [
            (subprocess.CompletedProcess([], 0, "6.11.0\n", ""), ("6.11.0", None)),
            (subprocess.CompletedProcess([], 1, "", "C:\\py\\python.exe: No module named PyInstaller\n"),
             (None, None)),
            (subprocess.CompletedProcess([], 1, "", "Traceback\nModuleNotFoundError: No module named 'packaging'\n"),
             (None, "ModuleNotFoundError: No module named 'packaging'")),
        ]
        for completed, expected in cases:
            with self.subTest(expected=expected):
                with patch("studio.exporter.subprocess.run", return_value=completed):
                    self.assertEqual(exporter.pyinstaller_status("python"), expected)


class StudioHelperTests(unittest.TestCase):
    def test_blocks_round_trip_keeps_the_source(self):
        source = ("// note\nscore = 0\nif score > 1\n    print {score}\nelse if score == 0\n    print none\nend\n"
                  "loop 3\n    box a 1 2 3 4\nend\nfunction greet name\n    print hi {name}\nend\n")
        self.assertEqual(blocks.blocks_source(blocks.parse_blocks(source)), source)

    def test_blocks_keep_how_else_if_was_written(self):
        for spelling in ("else if", "elif", "elseif"):
            source = f"if x > 1\n    print a\n{spelling} x > 0\n    print b\nend\n"
            with self.subTest(spelling=spelling):
                self.assertEqual(blocks.blocks_source(blocks.parse_blocks(source)), source)

    def test_every_command_makes_a_valid_new_block(self):
        for command in COMMAND_SPECS:
            with self.subTest(command=command):
                made = blocks.new_block(command)
                self.assertTrue(made)
                self.assertIn(made[0].kind, ("command", "assign", "for", "code"))
                if command in blocks.NEEDS_END:
                    self.assertEqual(made[-1].command, "end")

    def test_line_tokens_colour_commands_expressions_and_comments(self):
        self.assertEqual(line_tokens("// hi"), [("comment", 0, 5)])
        tags = {tag for tag, _start, _end in line_tokens("print hi {x + 1}")}
        self.assertTrue({"command", "brace", "operator", "number"} <= tags)
        self.assertIn(("operator", 6, 8), line_tokens("score += 1"))

    def test_fuzzy_palette_score_prefers_whole_words(self):
        self.assertGreater(_score("save", "file: save"), _score("save", "view: show variables"))
        self.assertGreater(_score("fs", "file: save"), 0)
        self.assertEqual(_score("zzz", "file: save"), 0)

    def test_find_includes_follows_nested_files(self):
        with tempfile.TemporaryDirectory() as folder:
            for name, text in (("a.gubl", "include b.gubl\n"), ("b.gubl", "print b\n")):
                with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
                    handle.write(text)
            found = find_includes("include a.gubl\nprint main\n", folder)
            self.assertEqual(sorted(found), ["a.gubl", "b.gubl"])

    def test_plural(self):
        self.assertEqual(theme.plural(1, "file"), "1 file")
        self.assertEqual(theme.plural(3, "file"), "3 files")

    def test_ui_text_has_no_capitals(self):
        """the studio's own words are lowercase: check every string literal shown in the ui modules."""
        allowed = re.compile(r"^(?:[A-Z_]+|.*[\\/%{}<>].*|[A-Z][a-z]+(?:[A-Z][a-z]+)+|Segoe.*|Consolas|"
                             r"TkDefaultFont|Flat\..*|.*\.T\w+|Control-.*|Shift-.*|Key.*|Button.*|Return|Escape|"
                             r"Up|Down|Left|Right|Tab|Prior|Next|Home|End|Delete|BackSpace|KP_\w+|ISO_\w+|"
                             r"F\d+|MouseWheel|Motion|Configure|Destroy|Enter|Leave|FocusIn|FocusOut|Map|"
                             r"Double-1|B1-Motion|ButtonRelease-1|SystemButtonFace|TkFixedFont)$")
        studio = os.path.join(ROOT, "studio")
        offenders = []
        for name in ("app.py", "dialogs.py", "panels.py", "blocks.py", "guides.py", "templates.py", "config.py"):
            path = os.path.join(studio, name)
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for match in re.finditer(r'(?<![\w\\])(?:text|label|title)=f?"([^"\n]+)"', text):
                value = match.group(1)
                if re.search(r"[A-Z]", value) and not allowed.match(value):
                    offenders.append(f"{name}: {value}")
        self.assertEqual(offenders, [])


class DocsAndCliTests(unittest.TestCase):
    def test_generated_docs_cover_every_command_and_match_the_file(self):
        markdown = docsgen.commands_markdown()
        for command in COMMAND_SPECS:
            self.assertIn(f"### `{command}`", markdown)
        with open(os.path.join(ROOT, "docs", "COMMANDS.md"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), markdown, "run: py gublancli.py docs")

    def test_every_example_in_the_docs_is_valid(self):
        examples = re.findall(r"```gublan\n(.*?)```", docsgen.commands_markdown(), re.S)
        self.assertGreater(len(examples), 50)
        for example in examples:
            with self.subTest(example=example[:40]):
                problems = [item for item in analyze_source(example) if item.get("severity", "error") == "error"
                            and "include" not in item["message"]]
                self.assertEqual(problems, [])

    def test_cli_check_reports_problems_with_an_exit_code(self):
        with tempfile.TemporaryDirectory() as folder:
            good = os.path.join(folder, "good.gubl")
            bad = os.path.join(folder, "bad.gubl")
            with open(good, "w", encoding="utf-8") as handle:
                handle.write("print hi\n")
            with open(bad, "w", encoding="utf-8") as handle:
                handle.write("loop\nend\n")
            cli = os.path.join(ROOT, "gublancli.py")
            env = dict(os.environ, PYGAME_HIDE_SUPPORT_PROMPT="1")
            ok = subprocess.run([sys.executable, cli, "check", good], capture_output=True, text=True, env=env)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn("0 errors, 0 warnings", ok.stdout)
            broken = subprocess.run([sys.executable, cli, "check", bad], capture_output=True, text=True, env=env)
            self.assertEqual(broken.returncode, 1)
            self.assertIn("line 1", broken.stdout)
            self.assertIn("1 error,", broken.stdout)

    def test_cli_runs_a_program(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "hi.gubl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("x = 2\nprint hi {x * 3}\n")
            env = dict(os.environ, PYGAME_HIDE_SUPPORT_PROMPT="1", SDL_VIDEODRIVER="dummy")
            result = subprocess.run([sys.executable, os.path.join(ROOT, "gublancli.py"), "run", path],
                                    capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("hi 6", result.stdout)


if __name__ == "__main__":
    unittest.main()
