"""tests for what is new in 1.0.9: the 3d scene editor, more 3d, files, the new commands and functions, publishing
and playground links, find in files and rename, opening .gubl files from explorer, and the website's new parts."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
WEB = os.path.join(ROOT, "web")
if WEB not in sys.path:
    sys.path.insert(0, WEB)

import build_site  # noqa: E402
import gublancore  # noqa: E402
import gublanmcp  # noqa: E402
import gublantranslate  # noqa: E402
from gublancore import GublanRuntime, shape_matrix, shape_mesh  # noqa: E402
from studio import account, config, refactor, shell, version  # noqa: E402
from studio.scene3d import Scene  # noqa: E402

ENV = dict(os.environ, PYGAME_HIDE_SUPPORT_PROMPT="1", SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
ENV.pop("GUBLAN_STYLE", None)
LOVE = shutil.which("lovec") or next((path for path in ("C:/Program Files/LOVE/lovec.exe",) if os.path.isfile(path)),
                                     None)

NEW_COMMANDS = ("seed", "swap", "pop", "screenshot", "block", "cylinder", "cone", "plane", "turn", "lookat", "walk",
                "light", "velocity", "gravity", "writefile", "appendfile", "readfile", "deletefile", "makefolder",
                "copyfile", "renamefile")
NEW_FUNCTIONS = ("year", "month", "day", "hour", "minute", "second", "weekday", "timetext", "left", "right", "matches",
                 "normalize", "dot", "cross", "percent", "sample", "findindex", "clicked", "hovering", "distance",
                 "screenpos", "camerapos", "camerayaw", "camerapitch", "readfile", "readlines", "fileexists",
                 "isfolder", "listfiles", "filesize", "filename", "extension", "fromcsv", "tocsv")
NEW_EXAMPLES = ("bouncy_balls.gubl", "dodge_3d.gubl", "garden_3d.gubl", "notes_and_files.gubl")

# runs the same in gublan, python, javascript and lua: no window, and the files stay in the program's folder
PARITY = r'''print {percent(1, 4)} {timetext(3723)} {timetext(65.7)}
print {left("hello", 2)} {right("hello", 3)} {matches("photo.PNG", "*.png")} {matches("ab", "a?")}
print {normalize(vec2(3, 4))} {dot([1, 2], [3, 4])} {cross(vec3(1, 0, 0), vec3(0, 1, 0))}
print {fromcsv("a,1\nb,2.5")} {tocsv([["a", 1], ["b", "x,y"]])}
print {filename("maps/one.txt")} {extension("a.png")} {extension("noext")}
xs = [1, 2, 3]
pop xs last
print {last} {xs}
pop xs first 0
print {first} {xs}
a = 1
b = 2
swap a b
print {a} {b}
seed 5
x = random(1, 100)
seed 5
y = random(1, 100)
print {x == y}
print {weekday() != ""} {year() > 2000} {month() >= 1} {day() >= 1}
print {findindex([1, 5, 9], n => n > 3)} {len(sample([1, 2, 3, 4], 2))}
writefile notes.txt hello there
appendfile notes.txt second line
appendfile notes.txt third {1 + 2}
readfile notes.txt text
print {lines(text)}
print {readlines("notes.txt")} {fileexists("notes.txt")} {fileexists("nope.txt")}
makefolder saves/deep
copyfile notes.txt saves/copy.txt
renamefile saves/copy.txt saves/deep/moved.txt
print {listfiles("saves")} {listfiles("saves/deep")} {isfolder("saves")}
deletefile saves/deep/moved.txt
deletefile saves/deep
print {listfiles("saves")}
try
    where = ".." + "/outside.txt"
    readfile {where} t
catch problem
    print caught
end
'''
PARITY_OUTPUT = ["25 1:02:03 1:05", "he llo true true", "vec2(0.6, 0.8) 11 vec3(0, 0, 1)",
                 '[["a", 1], ["b", 2.5]] a,1', 'b,"x,y"', "one.txt png ", "3 [1, 2]", "1 [2]", "2 1", "true",
                 "true true true true", "1 2", '["hello there", "second line", "third 3"]',
                 '["hello there", "second line", "third 3"] true false', '["deep"] ["moved.txt"] true', "[]",
                 "caught"]


def run(source, folder=None):
    output, errors = [], []
    runtime = GublanRuntime(onlog=output.append, base_dir=folder or tempfile.mkdtemp(prefix="gublan_109_"),
                            onerror=lambda message, _file, line: errors.append((line, message)))
    runtime.run(source)
    return "\n".join(output).splitlines(), errors


def errors_in(source):
    return [item for item in gublancore.analyze_source(source) if item.get("severity", "error") == "error"]


def translated_output(source, language, command):
    result = gublantranslate.translate(source, language, name="demo")
    folder = tempfile.mkdtemp(prefix="gublan_translate_")
    try:
        gublantranslate.write_files(result, folder)
        target = folder if language == "lua" else os.path.join(folder, result.main)
        finished = subprocess.run(command + [target], capture_output=True, text=True, env=ENV, timeout=90,
                                  cwd=folder)
        lines = [line for line in finished.stdout.splitlines() if not line.startswith(("pygame ", "Hello from"))]
        return lines, finished.stderr
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def make_root(test):
    """a hidden tk root that is cleaned up after the test, with its waiting timers cancelled first."""
    try:
        root = tk.Tk()
    except tk.TclError as err:
        test.skipTest(f"no display: {err}")
    root.withdraw()

    def close():
        for job in root.tk.splitlist(root.tk.call("after", "info")):
            root.tk.call("after", "cancel", job)  # not after_cancel: destroy() frees the callbacks itself
        root.destroy()

    test.addCleanup(close)
    return root


class TempSettings(unittest.TestCase):
    """every test here gets its own settings folder, so the real one is never touched."""

    def setUp(self):
        self.settings = tempfile.mkdtemp(prefix="gublan_settings_")
        patcher = mock.patch.object(config, "settings_folder", lambda: self.settings)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.settings, True)


class VersionTests(unittest.TestCase):
    def test_version_is_at_least_109(self):
        self.assertGreaterEqual(tuple(int(part) for part in version.VERSION.split(".")), (1, 0, 9))

    def test_the_mcp_server_reports_the_same_version(self):
        self.assertEqual(gublanmcp._version(), version.VERSION)


# ----- the language --------------------------------------------------------------------------------------------------
class CommandTests(unittest.TestCase):
    def test_every_new_command_is_documented(self):
        for name in NEW_COMMANDS:
            self.assertIn(name, gublancore.COMMAND_SPECS, name)
            _category, usage, _parts, summary, example = gublancore.COMMAND_SPECS[name]
            self.assertTrue(usage.startswith(name) and summary and example.startswith(name), name)
            self.assertEqual(errors_in(example + "\n"), [], name)

    def test_every_new_function_is_documented(self):
        for name in NEW_FUNCTIONS:
            self.assertIn(name, gublancore.EXPRESSION_FUNCTIONS, name)

    def test_the_checker_keeps_files_in_the_programs_folder(self):
        for line in ("readfile ../secret.txt t", "writefile C:/windows/x.txt hi", "deletefile /etc/passwd",
                     "copyfile notes.txt ../../out.txt"):
            with self.subTest(line=line):
                self.assertTrue(errors_in(line + "\n"))
        self.assertEqual(errors_in("writefile saves/one.txt hi\nreadfile saves/one.txt t\n"), [])

    def test_the_checker_counts_shape_words(self):
        self.assertEqual(errors_in("block wall 0 0 -8 4 2 0.5 sand\nplane g 0 -1 -8 20 20\n"), [])
        self.assertTrue(errors_in("block wall 0 0 -8 4 2\n"))

    def test_the_new_functions_and_files_give_the_right_answers(self):
        self.assertEqual(run(PARITY), (PARITY_OUTPUT, []))

    def test_a_variable_holding_an_objects_name_reads_and_sets_its_fields(self):
        output, errors = run("mode 2d\nbox b1 10 20 5 5\nbox b2 30 40 5 5\nlist boxes b1 b2\nfor one in boxes\n"
                             "    one.y = one.y + 100\n    one.vx = 3\n    print {one} {one.x} {one.y} {one.vx}\nend\n")
        self.assertEqual((output, errors), (["b1 10 120 3", "b2 30 140 3"], []))

    def test_3d_shapes_have_their_own_fields(self):
        output, errors = run("block wall 0 0 -8 4 2 0.5 sand\ncylinder p -2 0 -8 0.4 3 gray\n"
                             "plane g 0 -1 -8 20 20 moss\nturn wall 10 45 5\n"
                             "print {wall.angle} {wall.rx} {wall.rz} {wall.d} {p.r} {p.h} {g.w}\n"
                             "set wall.d = 2\nprint {wall.d}\n")
        self.assertEqual((output, errors), (["45 10 5 0.5 0.4 3 20", "2"], []))


class FileTests(unittest.TestCase):
    def setUp(self):
        self.parent = tempfile.mkdtemp(prefix="gublan_files_")
        self.folder = os.path.join(self.parent, "program")
        os.makedirs(self.folder)
        self.addCleanup(shutil.rmtree, self.parent, True)

    def test_paths_made_while_running_cant_leave_the_folder(self):
        with open(os.path.join(self.parent, "secret.txt"), "w", encoding="utf-8") as handle:
            handle.write("keep out")
        outside = os.path.join(self.parent, "secret.txt").replace("\\", "/")
        for line in ('where = ".." + "/secret.txt"\nreadfile {where} t\nprint {t}\n',
                     f'where = "{outside}"\nprint {{readfile(where)}}\n',
                     'where = "../made.txt"\nwritefile {where} hi\n'):
            with self.subTest(line=line):
                output, errors = run(line, self.folder)
                self.assertEqual(output, [])
                self.assertEqual(len(errors), 1)
                self.assertIn("inside your program's folder", errors[0][1])
        self.assertEqual(sorted(os.listdir(self.parent)), ["program", "secret.txt"])

    def test_files_are_written_next_to_the_program(self):
        output, errors = run("makefolder levels\nwritefile levels/one.txt ####\nappendfile log.txt started\n"
                             "print {listfiles()}\n", self.folder)
        self.assertEqual((output, errors), (['["levels", "log.txt"]'], []))
        with open(os.path.join(self.folder, "levels", "one.txt"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "####")

    def test_a_missing_file_says_so(self):
        _output, errors = run("readfile nothing.txt t\n", self.folder)
        self.assertEqual(len(errors), 1)
        self.assertIn("was not found", errors[0][1])


class MeshTests(unittest.TestCase):
    def test_a_plane_is_one_level_face(self):
        faces = shape_mesh("plane", (4, 2))
        self.assertEqual(len(faces), 1)
        normal, corners = faces[0]
        self.assertEqual(normal, (0, 1, 0))
        self.assertEqual({corner[1] for corner in corners}, {0})
        self.assertEqual(sorted({abs(corner[0]) for corner in corners} | {abs(corner[2]) for corner in corners}),
                         [1.0, 2.0])

    def test_shapes_have_the_right_number_of_faces(self):
        self.assertEqual(len(shape_mesh("block", (2, 1, 1))), 6)
        self.assertEqual(len(shape_mesh("cube", (1,))), 6)
        self.assertEqual(len(shape_mesh("cylinder", (0.5, 2), sides=12)), 14)
        self.assertEqual(len(shape_mesh("cone", (0.5, 2), sides=12)), 13)

    def test_a_turn_about_y_by_90_degrees(self):
        matrix = shape_matrix({"type": "block", "angle": 90})
        point = [sum(matrix[row][k] * (1, 0, 0)[k] for k in range(3)) for row in range(3)]
        self.assertAlmostEqual(point[0], 0, places=6)
        self.assertAlmostEqual(abs(point[2]), 1, places=6)


class TranslateTests(unittest.TestCase):
    def test_python_version_prints_what_gublan_prints(self):
        lines, stderr = translated_output(PARITY, "python", [sys.executable])
        self.assertEqual(lines, PARITY_OUTPUT, stderr)

    def test_javascript_version_prints_what_gublan_prints(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        lines, stderr = translated_output(PARITY, "javascript", [node])
        self.assertEqual(lines, PARITY_OUTPUT, stderr)

    def test_lua_version_prints_what_gublan_prints(self):
        if not LOVE:
            self.skipTest("love2d is not installed")
        lines, stderr = translated_output(PARITY, "lua", [LOVE])
        self.assertEqual(lines, PARITY_OUTPUT, stderr)

    def test_the_new_examples_check_cleanly_and_translate_without_notes(self):
        for name in NEW_EXAMPLES:
            with open(os.path.join(ROOT, "examples", name), encoding="utf-8") as handle:
                source = handle.read()
            with self.subTest(example=name):
                self.assertEqual(errors_in(source), [])
                result = gublantranslate.translate(source, "javascript", name="demo")
                self.assertEqual(result.notes, [])


# ----- the 3d scene editor -------------------------------------------------------------------------------------------
SCENE = """// a test scene
mode 3d
background #9cc7e6
camera 0 2 4
plane ground 0 -1 -8 20 20 moss
block wall 0 0 -8 4 2 0.5 sand
turn wall 0 30
cube crate 2 0 -6 1 brown

loop 3
    sphere ball 0 3 -8 0.5 red
end
size = 2
cube big 0 0 -4 {size}
forever
    turn wall 0 {time()}
    frame
end
"""


class SceneTests(unittest.TestCase):
    def test_the_scene_reads_the_programs_shapes(self):
        scene = Scene(SCENE)
        self.assertTrue(scene.is_3d)
        self.assertEqual([part.name for part in scene.parts], ["ground", "wall", "crate", "ball"])
        self.assertEqual([part.editable for part in scene.parts], [True, True, True, False])
        self.assertEqual(scene.by_name["wall"].sizes, [4, 2, 0.5])
        self.assertEqual(scene.by_name["wall"].ry, 30)
        self.assertEqual(scene.by_name["wall"].turn_line, 6)
        self.assertEqual(scene.camera, [0, 2, 4])
        self.assertEqual(scene.background, (0x9c, 0xc7, 0xe6))
        self.assertEqual(scene.made_by_code, 1)  # cube big uses {size}
        self.assertEqual(scene.insert_at(), 8)  # after the last scene line, before the loop

    def test_a_part_writes_itself_back_as_a_gublan_line(self):
        part = Scene(SCENE).by_name["wall"]
        part.x, part.ry = 1.5, 45
        self.assertEqual(part.text(), "block wall 1.5 0 -8 4 2 0.5 sand")
        self.assertEqual(part.turn_text(), "turn wall 0 45 0")
        self.assertEqual(errors_in(part.text() + "\n" + part.turn_text() + "\n"), [])

    def test_new_names_are_unused(self):
        scene = Scene("mode 3d\ncube cube1 0 0 -5 1\nprint cube2\n")
        self.assertEqual(scene.new_name("cube"), "cube3")


class SceneEditorTests(unittest.TestCase):
    def setUp(self):
        from studio.editor import CodeEditor
        from studio.scene3d import SceneEditor
        self.root = make_root(self)
        self.code = CodeEditor(self.root, dict(config.DEFAULTS))
        self.code.pack()
        self.code.set_text(SCENE)
        self.editor = SceneEditor(self.root, self.code)
        self.editor.withdraw()
        self.root.update()

    def test_edits_go_into_the_code_and_one_undo_takes_each_back(self):
        editor, code = self.editor, self.code
        editor.select("crate")
        part = editor.part()
        part.x, part.ry = 3, 90
        editor.save_part(part, "moved")
        self.assertIn("cube crate 3 0 -6 1 brown\nturn crate 0 90 0\n", code.get())
        editor.add_part("cylinder")
        added = editor.selected
        self.assertTrue(re.search(rf"^cylinder {added} [-\d. ]+ gray$", code.get(), re.M))
        editor.duplicate_part()
        copy = editor.selected
        self.assertIn(f"cylinder {copy} ", code.get())
        editor.delete_part()
        self.assertNotIn(f"cylinder {copy} ", code.get())
        editor.undo()
        self.assertIn(f"cylinder {copy} ", code.get())
        self.assertEqual(errors_in(code.get()), [])
        self.assertTrue(code.get().index(f"cylinder {added}") < code.get().index("loop 3"))

    def test_rename_and_game_camera(self):
        editor, code = self.editor, self.code
        editor.rename_part(editor.scene.by_name["wall"], "fence")
        self.assertIn("block fence 0 0 -8", code.get())
        self.assertIn("turn fence 0 30", code.get())
        self.assertIn("turn fence 0 {time()}", code.get())
        editor.set_game_camera()
        self.assertEqual(len(re.findall(r"^camera ", code.get(), re.M)), 1)
        self.assertNotIn("camera 0 2 4\n", code.get())
        self.assertEqual(errors_in(code.get()), [])

    def test_shapes_made_in_code_cant_be_deleted_from_the_editor(self):
        self.editor.select("ball")
        self.editor.delete_part()
        self.assertIn("sphere ball 0 3 -8 0.5 red", self.code.get())


# ----- the studio ----------------------------------------------------------------------------------------------------
class RefactorTests(unittest.TestCase):
    def test_rename_leaves_text_and_other_objects_fields_alone(self):
        source = ("score = 0\nprint score is {score}\nscore += 1\nplayer.score = 3\nprint {other.score + score}\n"
                  'title "score"\nbox score 1 2 3 4\n')
        renamed, changed = refactor.rename(source, "score", "points")
        self.assertEqual(renamed, "points = 0\nprint score is {points}\npoints += 1\nplayer.score = 3\n"
                                  'print {other.score + points}\ntitle "score"\nbox points 1 2 3 4\n')
        self.assertEqual(changed, [1, 2, 3, 5, 7])

    def test_new_names_must_be_names(self):
        self.assertIsNone(refactor.check_new_name("points"))
        for bad in ("2fast", "has space", "print", "end", "true"):
            with self.subTest(name=bad):
                self.assertTrue(refactor.check_new_name(bad))

    def test_find_in_files_looks_in_programs_and_text_but_not_hidden_folders(self):
        folder = tempfile.mkdtemp(prefix="gublan_find_")
        self.addCleanup(shutil.rmtree, folder, True)
        for name, text in (("game.gubl", "score = 0\nprint score {score}\n"), ("notes.txt", "Score sheet\n"),
                           ("picture.png", "score"), (os.path.join(".git", "x.gubl"), "score\n")):
            os.makedirs(os.path.dirname(os.path.join(folder, name)), exist_ok=True)
            with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
                handle.write(text)
        found = refactor.find_in_files(folder, "score")
        self.assertEqual([(os.path.basename(path), line, column) for path, line, column, _text in found],
                         [("game.gubl", 1, 0), ("game.gubl", 2, 6), ("game.gubl", 2, 13), ("notes.txt", 1, 0)])
        self.assertEqual(len(refactor.find_in_files(folder, "score", match_case=True)), 3)
        self.assertEqual(len(refactor.find_in_files(folder, "scor", whole_word=True)), 0)

    def test_find_results_show_one_row_per_line(self):
        from studio.dialogs import FindInFilesDialog
        folder = tempfile.mkdtemp(prefix="gublan_find_")
        self.addCleanup(shutil.rmtree, folder, True)
        with open(os.path.join(folder, "game.gubl"), "w", encoding="utf-8") as handle:
            handle.write("score = 0\nprint score {score}\nscore += 1\n")
        root = make_root(self)
        opened = []
        dialog = FindInFilesDialog(root, folder, lambda *where: opened.append(where), initial="score")
        dialog.search()
        self.assertEqual(len(dialog.results), 4)
        self.assertEqual(len(dialog.line_of), 3)
        self.assertEqual(len(dialog.list.tag_ranges("hit")) // 2, 4)  # line 2's two hits share a row
        dialog._move(1)
        dialog._move(1)
        dialog._open_chosen()
        self.assertEqual([where[1:] for where in opened], [(3, 0)])
        dialog._move(-1)
        dialog._open_chosen()
        self.assertEqual(opened[-1][1:], (2, 6))


class EditorTests(unittest.TestCase):
    def test_replacing_all_the_text_is_one_undo_step(self):
        from studio.editor import CodeEditor
        root = make_root(self)
        editor = CodeEditor(root, dict(config.DEFAULTS))
        editor.set_text("print one\n")
        editor.replace_all_text("print two\n")
        self.assertEqual(editor.get().strip(), "print two")
        editor.undo()
        self.assertEqual(editor.get().strip(), "print one")


class ShareLinkTests(unittest.TestCase):
    def test_one_program_makes_a_short_z_link_and_reads_back(self):
        link = account.share_link([("game.gubl", "print héllo\n")], "game.gubl")
        self.assertTrue(link.startswith(account.PLAYGROUND + "#z="))
        self.assertNotIn("=", link.split("#z=", 1)[1])
        self.assertEqual(account.read_share_link(link), ([("shared.gubl", "print héllo\n")], "shared.gubl"))

    def test_a_project_makes_a_p_link_with_every_file(self):
        files = [("game.gubl", "include helpers\nreadfile level.txt t\n"), ("helpers.gubl", "function hi\nend\n"),
                 ("level.txt", "###\n")]
        link = account.share_link(files, "game.gubl")
        self.assertIn("#p=", link)
        self.assertEqual(account.read_share_link(link), (files, "game.gubl"))

    def test_a_data_file_alone_still_goes_as_a_project(self):
        self.assertIn("#p=", account.share_link([("notes.txt", "hi")], "notes.txt"))

    def test_links_that_arent_ours_read_as_none(self):
        for link in ("https://gublan.xyz/playground/", "https://gublan.xyz/playground/#z=!!!", "#p=AAAA", ""):
            self.assertIsNone(account.read_share_link(link), link)

    def test_creation_links_and_3d(self):
        self.assertEqual(account.creation_link("ab12/?x"), account.PLAYGROUND + "?c=ab12%2F%3Fx")
        self.assertTrue(account.uses_3d([("a.gubl", "// hi\n  mode 3d\n")]))
        self.assertFalse(account.uses_3d([("a.gubl", "mode 2d\n"), ("notes.txt", "mode 3d\n")]))


class ProgramFilesTests(unittest.TestCase):
    def test_includes_and_named_text_files_go_up_with_the_program(self):
        folder = tempfile.mkdtemp(prefix="gublan_publish_")
        self.addCleanup(shutil.rmtree, folder, True)
        files = {"helpers.gubl": "include more.gubl\nfunction hi\nend\n", "more.gubl": "print more\n",
                 "level.txt": "###\n", "scores.csv": "a,1\n", "unused.txt": "no\n"}
        for name, text in files.items():
            with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
                handle.write(text)
        main = "include helpers\nreadfile level.txt t\nprint {readlines(\"scores.csv\")}\nprint missing.txt\n"
        found = account.program_files(os.path.join(folder, "game.gubl"), main)
        self.assertEqual([name for name, _text in found], ["game.gubl", "helpers.gubl", "level.txt", "scores.csv",
                                                           "more.gubl"])
        self.assertEqual(found[0], ("game.gubl", main))

    def test_an_unsaved_program_goes_alone(self):
        self.assertEqual(account.program_files(None, "print hi\n"), [("program.gubl", "print hi\n")])


class InstanceTests(TempSettings):
    def test_a_second_launch_hands_its_files_to_the_open_studio(self):
        got = []
        server = shell.InstanceServer(lambda paths, start: got.append((paths, start)))
        self.addCleanup(server.close)
        self.assertTrue(os.path.isfile(shell.instance_path()))
        self.assertTrue(shell.forward(["a.gubl"], run=True))
        self.assertEqual(got, [([os.path.abspath("a.gubl")], True)])

    def test_a_wrong_token_is_ignored(self):
        got = []
        server = shell.InstanceServer(lambda paths, start: got.append(paths))
        self.addCleanup(server.close)
        with open(shell.instance_path(), "w", encoding="utf-8") as handle:
            json.dump({"port": server.port, "token": "not-the-token", "pid": os.getpid()}, handle)
        self.assertFalse(shell.forward(["a.gubl"]))
        self.assertEqual(got, [])

    def test_nothing_to_hand_to_after_the_studio_closes(self):
        server = shell.InstanceServer(lambda paths, start: None)
        server.close()
        self.assertFalse(os.path.exists(shell.instance_path()))
        self.assertFalse(shell.forward(["a.gubl"]))

    def test_explorer_entries_open_and_run(self):
        entries = {(key, name): value for key, name, value in shell._entries()}
        self.assertEqual(entries[(".gubl", "")], shell.PROG_ID)
        self.assertTrue(entries[(shell.PROG_ID + "\\shell\\open\\command", "")].endswith('"%1"'))
        self.assertIn('--run "%1"', entries[(shell.PROG_ID + "\\shell\\run\\command", "")])
        for (key, name), value in entries.items():
            if name == "" and key.endswith(("\\open", "\\run")) or key == shell.PROG_ID:
                self.assertEqual(value, value.lower(), key)

    def test_the_installer_registers_gubl_files_too(self):
        with open(os.path.join(ROOT, "GublanStudio.iss"), encoding="utf-8") as handle:
            script = handle.read()
        self.assertIn("ChangesAssociations=yes", script)
        self.assertIn('Subkey: "Software\\Classes\\GublanStudio.gubl\\shell\\run\\command"', script)
        self.assertIn('--run ""%1""', script)


class LowercaseTests(unittest.TestCase):
    def test_the_new_windows_use_lowercase_words(self):
        shown = re.compile(r'(?:(?<![\w\\])(?:text|label|title)=|add_button\(|say\(|flash\(|BracketButton\(\w+, |'
                           r'Toggle\(\w+, |ask\(self\.root, )f?"([^"\n]+)"')
        offenders = []
        for name in ("scene3d.py", "dialogs.py", "app.py", "shell.py"):
            with open(os.path.join(ROOT, "studio", name), encoding="utf-8") as handle:
                text = handle.read()
            for match in shown.finditer(text):
                value = re.sub(r"\{[^}]*\}", "", match.group(1))
                if re.search(r"[A-Z]", value):
                    offenders.append(f"{name}: {match.group(1)}")
        self.assertEqual(offenders, [])


# ----- the website ---------------------------------------------------------------------------------------------------
class WebsiteTests(unittest.TestCase):
    def test_the_site_has_explore_and_its_scripts_are_valid(self):
        self.assertEqual(build_site.EXPLORE_FILES, ["index.html", "explore.css", "explore.js"])
        for name in build_site.EXPLORE_FILES:
            self.assertTrue(os.path.isfile(os.path.join(WEB, "explore", name)), name)
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        for path in (os.path.join(WEB, "explore", "explore.js"), os.path.join(WEB, "playground", "playground.js"),
                     os.path.join(WEB, "account.js")):
            done = subprocess.run([node, "--check", path], capture_output=True, text=True, timeout=60)
            self.assertEqual(done.returncode, 0, done.stderr)

    def test_the_creations_table_is_locked_down(self):
        with open(os.path.join(ROOT, "docs", "supabase_creations.sql"), encoding="utf-8") as handle:
            sql = handle.read().lower()
        self.assertIn("alter table public.creations enable row level security", sql)
        self.assertIn("user_id = (select auth.uid())", sql)
        self.assertIn("revoke all on public.creations from anon, authenticated", sql)
        self.assertNotRegex(sql, r"grant (insert|update|delete)[^;]* to anon")

    def test_no_secret_keys_anywhere(self):
        pattern = re.compile(r"sb_secret_|service_role\"?\s*[:=]\s*\"ey|client_secret\s*[:=]\s*\"\w")
        for folder in ("studio", "web"):
            for base, _folders, names in os.walk(os.path.join(ROOT, folder)):
                for name in names:
                    if name.endswith((".py", ".js", ".html", ".json")):
                        with open(os.path.join(base, name), encoding="utf-8", errors="replace") as handle:
                            self.assertIsNone(pattern.search(handle.read()), os.path.join(base, name))


class GuideTests(unittest.TestCase):
    def test_the_109_features_have_guides(self):
        from studio.guides import GUIDES
        bodies = dict(GUIDES)
        self.assertIn("ctrl+shift+d", bodies["the 3d scene editor"])
        self.assertIn("appendfile", bodies["files"])
        self.assertIn("publish to gublan.xyz", bodies["publishing and sharing"])
        self.assertIn("run with gublan", bodies["from explorer"])
        self.assertIn("ctrl+shift+f find in files", bodies["keyboard shortcuts"])


if __name__ == "__main__":
    unittest.main()
