import os
import re
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from gublancore import GUBLANCOMMANDS, GublanRuntime, analyze_source, split_command
import gublanide

gublanide.analyze_source = analyze_source
gublanide.split_command = split_command
gublanide.BLOCK_COMMANDS = set(GUBLANCOMMANDS)


class LanguageFeatureTests(unittest.TestCase):
    def test_command_tokenizer_preserves_quoted_windows_paths(self):
        self.assertEqual(
            split_command('music "D:\\shaderglass\\Vapor Wave.mp3"'),
            ["music", "D:\\shaderglass\\Vapor Wave.mp3"],
        )
        self.assertEqual(
            split_command('image logo "assets\\Blue Sky.png" 20 24'),
            ["image", "logo", "assets\\Blue Sky.png", "20", "24"],
        )

    def test_examples_are_valid_scripts(self):
        examples_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples")
        for filename in os.listdir(examples_dir):
            if not filename.endswith(".gubl"):
                continue
            with self.subTest(filename=filename):
                with open(os.path.join(examples_dir, filename), encoding="utf-8") as file:
                    self.assertEqual(analyze_source(file.read()), [])

    def test_every_language_command_is_documented(self):
        docs_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "docs", "COMMANDS.md"
        )
        with open(docs_path, encoding="utf-8") as file:
            documented_commands = set(re.findall(r"`([a-z][a-z0-9]*)`", file.read()))

        self.assertLessEqual(GUBLANCOMMANDS, documented_commands)

    def test_new_commands_are_supported_by_blocks_mode(self):
        source = """vec2 position 10 20
vec3 camera_position 0 0 -6
map inventory
put inventory coins 2
button start 20 20 100 32 start
mousebutton fire left
sphere moon 1 2 -7 0.5
volume 0.5
"""
        parsed = gublanide.GublanStudio.parseblocksource(source)
        self.assertEqual(len(parsed), 8)

    def test_comparisons_and_conditional_branches(self):
        source = """set value = 2
if value = 3
    print wrong
elseif value >= 2
    print elseif
else
    print wrong
end
if value = 0
    print wrong
else
    print else
end
if value = 2
    loop 1
        print nested
    end
else
    print wrong
end
if value == 2
    print equal
end
if value != 1
    print not equal
end
if value > 1
    print greater
end
if value < 3
    print less
end
if value <= 2
    print less or equal
end
"""
        output = []
        runtime = GublanRuntime(onlog=output.append)

        self.assertEqual(analyze_source(source), [])
        runtime.run(source)
        self.assertEqual(
            output,
            ["elseif", "else", "nested", "equal", "not equal", "greater", "less", "less or equal"],
        )

    def test_analyzer_reports_comparison_and_block_errors(self):
        diagnostics = analyze_source("if score => 2\nelse\nelse\nend\nend")

        self.assertTrue(any("comparison" in item["message"] for item in diagnostics))
        self.assertTrue(any("another branch" in item["message"] for item in diagnostics))
        self.assertTrue(any("matching" in item["message"] for item in diagnostics))

    def test_text_and_relative_image_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            image = pygame.Surface((3, 3), pygame.SRCALPHA)
            pygame.image.save(image, os.path.join(directory, "pixel.png"))
            runtime = GublanRuntime(onlog=lambda _: None, base_dir=directory)

            runtime.run("mode 2d\ntext title 10 12 hello world\nimage icon pixel.png 20 24")

            self.assertEqual(runtime.objects["title"]["text"], "hello world")
            self.assertEqual(runtime.objects["icon"]["surface"].get_size(), (3, 3))

    def test_text_created_in_3d_mode_renders_as_pixel_positioned_overlay(self):
        source = """mode 3d
print 3d rotation
set deg = 0
cube core 0 0 -6 1.6
color yellow
text hi 20 24 virus
kill
"""
        runtime = GublanRuntime(onlog=lambda _: None)

        def fake_initstage(mode):
            pygame.init()
            runtime.mode = mode
            runtime.screen = pygame.Surface((540, 420))
            runtime.text_font = pygame.font.Font(None, 24)

        runtime.initstage = fake_initstage
        runtime.pumpevents = lambda: None
        self.assertEqual(analyze_source(source), [])
        runtime.run(source)
        self.assertEqual(runtime.objects["hi"]["text"], "virus")

        with (
            patch("gublancore.glClear"),
            patch("gublancore.glPushAttrib"),
            patch("gublancore.glPopAttrib"),
            patch("gublancore.glDisable"),
            patch("gublancore.glEnable"),
            patch("gublancore.glBlendFunc"),
            patch("gublancore.glMatrixMode"),
            patch("gublancore.glPushMatrix"),
            patch("gublancore.glPopMatrix"),
            patch("gublancore.glLoadIdentity"),
            patch("gublancore.glOrtho"),
            patch("gublancore.glGenTextures", return_value=7),
            patch("gublancore.glBindTexture") as bind_texture,
            patch("gublancore.glTexParameteri"),
            patch("gublancore.glTexImage2D") as upload_texture,
            patch("gublancore.glColor4f"),
            patch("gublancore.glBegin"),
            patch("gublancore.glTexCoord2f"),
            patch("gublancore.glVertex2f") as vertex,
            patch("gublancore.glEnd"),
            patch("gublancore.pygame.display.flip"),
        ):
            pygame.init()
            runtime.screen = pygame.Surface((540, 420))
            runtime.mode = "3d"
            runtime.text_font = pygame.font.Font(None, 24)
            runtime.objects = {
                "hi": {
                    "type": "text", "x": 20, "y": 24, "text": "virus", "color": "yellow"
                }
            }
            runtime.render()
            runtime.render()

        self.assertEqual(vertex.call_args_list[0].args, (20, 24))
        self.assertEqual(vertex.call_count, 8)
        upload_texture.assert_called_once()
        self.assertEqual(bind_texture.call_count, 2)

    def test_expressions_functions_lists_and_random(self):
        source = """set value = 5
calc total 2 + 3 * 4
function double value
    calc doubled value * 2
    return doubled
end
call double 7
set answer = result
list values
append values answer
append values hello world
item values 1 label
length values count
random roll 4 4
"""
        runtime = GublanRuntime(onlog=lambda _: None)

        self.assertEqual(analyze_source(source), [])
        runtime.run(source)

        self.assertEqual(runtime.vars["total"], 14)
        self.assertEqual(runtime.vars["answer"], 14)
        self.assertEqual(runtime.vars["value"], 5)
        self.assertEqual(runtime.vars["label"], "hello world")
        self.assertEqual(runtime.vars["count"], 2)
        self.assertEqual(runtime.vars["roll"], 4)

    def test_string_number_and_comma_concatenation(self):
        output = []
        runtime = GublanRuntime(onlog=output.append)
        source = """first = "hello"
second = "world"
print {first + second}
print first, second, number("3.5")
print {string(17)}, {number("21")}
print max(1, 2), "done, right"
print {"hello", "world"}
"""

        self.assertEqual(analyze_source(source), [])
        runtime.run(source)

        self.assertEqual(output, [
            "helloworld",
            "hello world 3.5",
            "17 21",
            "2 done, right",
            "hello world",
        ])

    def test_vectors_maps_and_mixed_dimension_values(self):
        source = """vec2 start 10 20
vec2 offset 3 4
calc destination start + offset
set horizontal = destination.x
vec3 origin 1 2 3
calc shifted origin + vec3(2, 3, 4)
set depth = shifted.z
vec3 camera_position 0 0 0
camera camera_position
sphere moon 2 0 -7 0.5
box player 10 20 8 8
move player offset
cube core 0 0 -6 1
move core origin
button launch 20 20 100 30 launch
map inventory
put inventory coins 4
lookup inventory coins amount
has inventory gems found
set ready = true
"""
        runtime = GublanRuntime(onlog=lambda _: None)

        self.assertEqual(analyze_source(source), [])
        runtime.run(source)

        self.assertEqual(runtime.vars["destination"].x, 13)
        self.assertEqual(runtime.vars["destination"].y, 24)
        self.assertEqual(runtime.vars["horizontal"], 13)
        self.assertEqual(runtime.vars["depth"], 7)
        self.assertEqual(runtime.camera, runtime.vars["camera_position"])
        self.assertEqual(runtime.objects["moon"]["radius"], 0.5)
        self.assertEqual(runtime.vars["launch"], 0)
        self.assertEqual(runtime.objects["button:launch"]["label"], "launch")
        self.assertEqual((runtime.objects["player"]["x"], runtime.objects["player"]["y"]), (13, 24))
        self.assertEqual(
            (runtime.objects["core"]["x"], runtime.objects["core"]["y"], runtime.objects["core"]["z"]),
            (1, 2, -3),
        )
        self.assertEqual(runtime.vars["amount"], 4)
        self.assertFalse(runtime.vars["found"])
        self.assertIs(runtime.vars["ready"], True)

    def test_input_editor_handles_unicode_cursor_selection_and_delete(self):
        value, cursor, anchor, action = GublanRuntime._edit_input_event(
            "cat", 1, None, SimpleNamespace(type=pygame.TEXTINPUT, text="é")
        )
        self.assertEqual((value, cursor, anchor, action), ("céat", 2, None, None))

        value, cursor, anchor, _ = GublanRuntime._edit_input_event(
            value, cursor, anchor,
            SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_LEFT, mod=pygame.KMOD_SHIFT)
        )
        value, cursor, anchor, _ = GublanRuntime._edit_input_event(
            value, cursor, anchor,
            SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_BACKSPACE, mod=0)
        )
        self.assertEqual(value, "cat")

        value, cursor, anchor, _ = GublanRuntime._edit_input_event(
            value, cursor, anchor,
            SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_a, mod=pygame.KMOD_CTRL)
        )
        value, cursor, anchor, _ = GublanRuntime._edit_input_event(
            value, cursor, anchor, SimpleNamespace(type=pygame.TEXTINPUT, text="hello")
        )
        self.assertEqual((value, cursor, anchor), ("hello", 5, None))

    def test_input_prompt_accepts_unicode_text(self):
        events = iter((
            SimpleNamespace(type=pygame.TEXTINPUT, text="é"),
            SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_RETURN, mod=0),
        ))
        runtime = GublanRuntime(onlog=lambda _: None)
        with (
            patch("gublancore.pygame.event.wait", side_effect=lambda _timeout: next(events)),
            patch("gublancore.pygame.key.start_text_input"),
            patch("gublancore.pygame.key.stop_text_input"),
            patch("gublancore.pygame.key.set_repeat"),
            patch("gublancore.pygame.key.set_text_input_rect", create=True),
        ):
            runtime.run("mode 2d\ninput answer enter text")
        self.assertEqual(runtime.vars["answer"], "é")

    def test_button_and_mouse_button_states(self):
        runtime = GublanRuntime(onlog=lambda _: None)
        runtime.screen = object()
        runtime.objects["button:start"] = {
            "type": "button", "variable": "start", "x": 10, "y": 10,
            "w": 80, "h": 30, "label": "start", "color": "green",
        }
        runtime.vars["start"] = 0
        down = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(20, 20))
        up = SimpleNamespace(type=pygame.MOUSEBUTTONUP, button=1, pos=(20, 20))
        with patch("gublancore.pygame.event.get", return_value=[down]):
            runtime.pumpevents()
        self.assertEqual(runtime.vars["start"], 1)
        with patch("gublancore.pygame.event.get", return_value=[up]):
            runtime.pumpevents()
        self.assertEqual(runtime.vars["start"], 0)

        runtime = GublanRuntime(onlog=lambda _: None)
        with (
            patch("gublancore.pygame.mouse.get_pressed", return_value=(False, True, False)),
            patch("gublancore.pygame.event.get", return_value=[]),
        ):
            runtime.run("mode 2d\nmousebutton pressed middle")
        self.assertIs(runtime.vars["pressed"], True)

    def test_sphere_renderer_applies_camera_offset_and_releases_quadric(self):
        runtime = GublanRuntime(onlog=lambda _: None)
        runtime.mode = "3d"
        runtime.screen = object()
        runtime.objects["moon"] = {
            "type": "sphere", "x": 1, "y": 2, "z": -6, "radius": 0.5, "color": "moss"
        }
        with (
            patch("gublancore.glClear"),
            patch("gublancore.glPushMatrix"),
            patch("gublancore.glTranslatef") as translate,
            patch("gublancore.glColor3f"),
            patch("gublancore.gluNewQuadric", return_value="quadric"),
            patch("gublancore.gluSphere") as draw_sphere,
            patch("gublancore.gluDeleteQuadric") as delete_quadric,
            patch("gublancore.glPopMatrix"),
            patch("gublancore.pygame.display.flip"),
        ):
            runtime.render()

        translate.assert_called_once_with(1, 2, -6)
        draw_sphere.assert_called_once_with("quadric", 0.5, 24, 16)
        delete_quadric.assert_called_once_with("quadric")

    def test_includes_share_functions_and_report_cycles(self):
        with tempfile.TemporaryDirectory() as directory:
            modules = os.path.join(directory, "modules")
            os.makedirs(modules)
            with open(os.path.join(modules, "helpers.gubl"), "w", encoding="utf-8") as file:
                file.write("include common.gubl\nfunction welcome name\nreturn name\nend\n")
            with open(os.path.join(modules, "common.gubl"), "w", encoding="utf-8") as file:
                file.write("set module_loaded = 1\n")

            output = []
            runtime = GublanRuntime(onlog=output.append, base_dir=directory)
            source = "include modules/helpers.gubl\ncall welcome gublan\nprint result"

            self.assertEqual(analyze_source(source), [])
            runtime.run(source)
            self.assertEqual(output, ["gublan"])
            self.assertEqual(runtime.vars["module_loaded"], 1)

            with open(os.path.join(directory, "a.gubl"), "w", encoding="utf-8") as file:
                file.write("include b.gubl\n")
            with open(os.path.join(directory, "b.gubl"), "w", encoding="utf-8") as file:
                file.write("include a.gubl\n")
            output.clear()
            runtime.run("include a.gubl")
            self.assertTrue(any("recursive include" in message for message in output))

    def test_sprite_collision_and_zero_duration_animation(self):
        with tempfile.TemporaryDirectory() as directory:
            image = pygame.Surface((3, 3), pygame.SRCALPHA)
            pygame.image.save(image, os.path.join(directory, "pixel.png"))
            runtime = GublanRuntime(onlog=lambda _: None, base_dir=directory)
            source = """mode 2d
box player 10 10 10 10
circle coin 20 20 3
sprite hero pixel.png 40 40 6 8
touching hit player coin
animate player 30 40 0
"""

            self.assertEqual(analyze_source(source), [])
            runtime.run(source)

            self.assertEqual(runtime.vars["hit"], 1)
            self.assertEqual((runtime.objects["player"]["x"], runtime.objects["player"]["y"]), (30, 40))
            self.assertEqual(runtime.objects["hero"]["surface"].get_size(), (6, 8))

    def test_3d_animation_updates_all_position_components(self):
        source = """mode 3d
cube core 0 0 -6 1.6
animate core 2 3 -8 0
kill
"""
        runtime = GublanRuntime(onlog=lambda _: None)

        def fake_initstage(mode):
            pygame.init()
            runtime.mode = mode
            runtime.screen = pygame.Surface((540, 420))

        runtime.initstage = fake_initstage
        runtime.pumpevents = lambda: None
        runtime.render = Mock()
        self.assertEqual(analyze_source(source), [])
        runtime.run(source)

        self.assertEqual(
            (runtime.objects["core"]["x"], runtime.objects["core"]["y"], runtime.objects["core"]["z"]),
            (2, 3, -8),
        )
        runtime.render.assert_called_once()

    def test_3d_animation_rejects_wrong_arity_or_display_mode(self):
        cases = (
            ("mode 3d\ncube core 0 0 -6 1\nanimate core 2 3 0\n", "animate a 3d shape"),
            (
                "mode 2d\ncube core 0 0 -6 1\nanimate core 2 3 -8 0\n",
                "animate a 3d shape",
            ),
        )

        for source, expected_error in cases:
            with self.subTest(source=source):
                output = []
                runtime = GublanRuntime(onlog=output.append)

                def fake_initstage(mode):
                    runtime.mode = mode
                    runtime.screen = pygame.Surface((540, 420))

                runtime.initstage = fake_initstage
                runtime.pumpevents = lambda: None
                self.assertEqual(analyze_source(source), [])
                runtime.run(source)
                self.assertTrue(any(expected_error in message for message in output))

    def test_sound_and_music_commands_with_mocked_audio_device(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("effect.wav", "Vapor Wave.wav", "theme.ogg"):
                with open(os.path.join(directory, name), "wb") as file:
                    file.write(b"audio")
            channel = Mock()
            channel.get_busy.return_value = True
            sound = Mock()
            sound.play.return_value = channel
            runtime = GublanRuntime(onlog=lambda _: None, base_dir=directory)

            with (
                patch("gublancore.pygame.mixer.get_init", return_value=(22050, -16, 2)),
                patch("gublancore.pygame.mixer.Sound", return_value=sound) as sound_loader,
                patch("gublancore.pygame.mixer.music.load") as music_load,
                patch("gublancore.pygame.mixer.music.play") as music_play,
                patch("gublancore.pygame.mixer.music.stop") as music_stop,
                patch("gublancore.pygame.mixer.music.set_volume") as music_volume,
                patch("gublancore.pygame.mixer.quit") as mixer_quit,
            ):
                runtime.run(
                    f"sound effect.wav\nsound {os.path.join(directory, 'Vapor Wave.wav')}\n"
                    "music theme.ogg\n"
                    "volume 0.5\nstopmusic\nstopsounds"
                )

            self.assertEqual(sound.play.call_count, 2)
            self.assertEqual(
                sound_loader.call_args_list,
                [
                    call(os.path.join(directory, "effect.wav")),
                    call(os.path.join(directory, "Vapor Wave.wav")),
                ],
            )
            self.assertEqual(channel.stop.call_count, 2)
            music_load.assert_called_once_with(os.path.join(directory, "theme.ogg"))
            music_play.assert_called_once_with(-1)
            self.assertEqual(music_volume.call_count, 4)
            music_stop.assert_called_once_with()
            mixer_quit.assert_called_once_with()


class ExportTests(unittest.TestCase):
    def test_export_expands_includes_and_stages_bundled_media(self):
        with tempfile.TemporaryDirectory() as directory:
            asset_dir = os.path.join(directory, "assets")
            os.makedirs(asset_dir)
            assets = {
                "pixel.png": b"image",
                "jump sound.wav": b"sound",
                "theme.ogg": b"music",
            }
            for name, contents in assets.items():
                with open(os.path.join(asset_dir, name), "wb") as file:
                    file.write(contents)
            with open(os.path.join(directory, "helpers.gubl"), "w", encoding="utf-8") as file:
                file.write(
                    "function value\nreturn 3\nend\n"
                    'sound "assets/jump sound.wav"\nmusic assets/theme.ogg\n'
                )

            class Root:
                def after(self, _delay, callback, *args):
                    callback(*args)

            studio = gublanide.GublanStudio.__new__(gublanide.GublanStudio)
            studio.root = Root()
            studio.runtime = GublanRuntime()
            finished = []
            studio.exportfinished = lambda *args: finished.append(args)
            output = os.path.join(directory, "game.exe")

            def fake_pyinstaller(command, **kwargs):
                self.assertEqual(
                    kwargs["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0)
                )
                script_path = next(path for path in command if path.endswith("gublan_program.py"))
                with open(script_path, "r", encoding="utf-8") as file:
                    generated = file.read()
                self.assertIn("function value", generated)
                self.assertNotIn("include helpers.gubl", generated)
                data_args = [
                    command[index + 1] for index, value in enumerate(command[:-1])
                    if value == "--add-data"
                ]
                self.assertEqual(
                    set(data_args),
                    {
                        f"{os.path.join(asset_dir, name)}{os.pathsep}assets"
                        for name in assets
                    },
                )
                dist_path = command[command.index("--distpath") + 1]
                os.makedirs(dist_path)
                with open(os.path.join(dist_path, "game.exe"), "wb") as executable:
                    executable.write(b"built")
                return subprocess.CompletedProcess(command, 0, "", "")

            source = (
                "include helpers.gubl\ncall value\n"
                "mode 2d\nimage icon assets/pixel.png 0 0"
            )
            with patch("gublanide.subprocess.run", side_effect=fake_pyinstaller):
                studio.buildscript_exe(source, output, "python", directory)

            self.assertEqual(finished, [(output, "")])
            with open(output, "rb") as executable:
                self.assertEqual(executable.read(), b"built")


if __name__ == "__main__":
    unittest.main()
