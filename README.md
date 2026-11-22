# Gublan

<p align="center">
  <img src="logo.png" width="100" alt="Gublan logo">
</p>

Gublan is a small programming language and creative studio for making games and programs. Write readable,
English-like commands, then run them in the built-in editor. Gublan Studio includes code and block editing,
2D and 3D graphics, debugging tools, and a converter for Python, JavaScript, and Lua.

[Download for Windows](https://github.com/gublans/gublan/releases) ·
[Language reference](docs/COMMANDS.md) · [Examples](examples/)

## Features

- **A beginner-friendly language:** short commands, helpful errors, live explanations, and guided examples.
- **Code and blocks:** edit in code, blocks, or a split view; both views represent the same program.
- **Make games:** build 2D and 3D projects with keyboard and mouse input, sound, images, shapes, and animation.
- **Learn and debug:** use breakpoints, step-through execution, variable watches, command hints, and a live
  problem checker.
- **Convert existing code:** translate supported Python, JavaScript, and Lua code into Gublan.
- **Export projects:** package a Gublan game as a Windows executable.
- **Save between runs:** `save` and `load` keep high scores and settings after a program closes.
- **Discord status:** show what you're making on Discord. You can change the wording, pictures and
  button, or turn it off. Programs can set their own status with `presence`.

## Install on Windows

Download and run **`GublanStudioSetup.exe`** from the
[GitHub Releases page](https://github.com/gublans/gublan/releases). The installer adds Gublan Studio to your
user account and creates a Start menu shortcut. A desktop shortcut is optional.

The installed app checks for a newer public GitHub release at startup and asks before updating. When you
agree, it downloads the update, closes, installs it, and opens the new version. You can choose to update when
you close the app, skip a version, or turn off update checks in settings.

## Run from source

Install Python 3 and the runtime dependencies:

```powershell
py -m pip install pygame-ce pyopengl
```

Start the editor:

```powershell
py gublanide.py
```

Open a program directly:

```powershell
py gublanide.py hello.gubl
```

You can also double-click `launch_gublan.vbs` on Windows to start the editor without a console window.

## Your first program

```gublan
window 640 480 coin catcher
mode 2d
color moss
box player 300 440 60 16

forever
    if keydown("left")
        move player {-400 * dt} 0
    end
    if keydown("right")
        move player {400 * dt} 0
    end
    frame
end
```

Each line is a command. Expressions go inside braces, `dt` is elapsed frame time, and `frame` ends each game
loop iteration. See [the language reference](docs/COMMANDS.md) for all commands and [the examples](examples/)
for complete programs.

### Text and numbers

Use `+` to join text directly, or commas in `print` to put spaces between values. `string()` converts a value
to text, while `number()` converts numeric text to a number:

```gublan
name = "sam"
print "hello", name
label = "score: " + string(number("12"))
print label
```

## Studio shortcuts

| Shortcut | Action |
| --- | --- |
| `F5` | Run or continue |
| `Shift+F5` | Stop |
| `F6` | Pause |
| `F10` | Step through the program |
| `F9` | Toggle a breakpoint |
| `F1` | Open help |
| `Ctrl+1` / `Ctrl+2` / `Ctrl+3` | Code / blocks / split view |
| `Ctrl+Shift+P` | Open the command palette |
| `Ctrl+Space` | Show suggestions |
| `Ctrl+Shift+C` | Convert code |
| `Ctrl+Shift+B` | Export a program |

## Command line

```powershell
py gublancli.py run game.gubl
py gublancli.py check game.gubl
py gublancli.py convert old.py new.gubl
py gublancli.py docs
```

## Build the Windows installer

From the project directory, install the build dependencies and [Inno Setup 6](https://jrsoftware.org/isdl.php).
Then run the build script:

```powershell
py -m pip install pyinstaller pygame-ce pyopengl
powershell -ExecutionPolicy Bypass -File build.ps1
```

The script reads the version from `VERSION` in [`studio/version.py`](studio/version.py) and runs the tests.
Then it builds the app, checks that the version is built into the exe, and creates
**`dist\GublanStudioSetup.exe`**. To skip the tests, add `-SkipTests`.

To release a new version:

1. Change `VERSION` in [`studio/version.py`](studio/version.py). This is the only place the version is written.
2. Run `build.ps1`.
3. Push the source to GitHub.
4. Create a public release whose tag is exactly the new version, for example `1.0.4`. Don't add a `v` prefix.
5. Attach `dist\GublanStudioSetup.exe` to the release without renaming it.

The installer will not build if its version doesn't match `VERSION`. The updater looks for that exact installer
filename in the latest public release.

When a user updates from inside the app, the installer runs silently. It waits for Gublan Studio to close and
then opens the new version. If an update fails, the app says so the next time it starts and shows the end of
the installer's log.

## Tests

Run the test suite from the project directory:

```powershell
$env:SDL_VIDEODRIVER = "dummy"
py -m unittest discover -s tests
```

## Project layout

| Path | Contents |
| --- | --- |
| `gublancore.py` | Gublan language parser, analyzer, and runtime |
| `gublanconvert.py` | Python, JavaScript, and Lua converter |
| `gublanpresence.py` | Discord status (rich presence) module used by the studio and by programs |
| `gublanide.py`, `studio/` | Gublan Studio editor |
| `gublancli.py` | Command-line interface |
| `GublanStudio.spec`, `GublanStudio.iss`, `build.ps1` | App build, Windows installer, and release build script |
| `docs/`, `examples/`, `tests/` | Reference, sample programs, and tests |
