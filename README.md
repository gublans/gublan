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

## Install on Windows

Download and run **`GublanStudioSetup.exe`** from the
[GitHub Releases page](https://github.com/gublans/gublan/releases). The installer adds Gublan Studio to your
user account and creates a Start menu shortcut. A desktop shortcut is optional.

The installed app checks for a newer public GitHub release at startup and asks before downloading and running
the update installer.

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

From the project directory, install the build dependencies and Inno Setup 6. Then build the app and installer:

```powershell
py -m pip install pyinstaller pygame-ce pyopengl
$version = "1.0.1"
py -m PyInstaller --noconfirm --distpath dist --workpath build\GublanStudio GublanStudio.spec
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" "/DMyAppVersion=$version" GublanStudio.iss
```

This creates **`dist\GublanStudioSetup.exe`**. Keep `$version` in sync with `VERSION` in
[`studio/version.py`](studio/version.py).

To publish a release, push the source to GitHub, create a public release tagged `v$version`, and attach
`dist\GublanStudioSetup.exe` without renaming it. The release tag, `VERSION`, and installer version must match.
The updater looks for that exact installer filename in the latest public release. The first release must be
published before the updater can find an update.

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
| `gublanide.py`, `studio/` | Gublan Studio editor |
| `gublancli.py` | Command-line interface |
| `GublanStudio.iss` | Windows installer definition |
| `docs/`, `examples/`, `tests/` | Reference, sample programs, and tests |
