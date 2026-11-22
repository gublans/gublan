# Gublan

<p align="center">
  <img src="logo.png" width="100" alt="Gublan logo">
</p>

Gublan is a small programming language and creative studio for making games and programs. Write readable,
English-like commands, then run them in the built-in editor. Gublan Studio includes code and block editing,
2D and 3D graphics, debugging tools, live sessions for coding together, and converters to and from Python,
JavaScript, and Lua.

[Download for Windows](https://github.com/gublans/gublan/releases) ·
[Language reference](docs/COMMANDS.md) · [Examples](examples/)

## Features

- **A beginner-friendly language:** short commands, helpful errors, live explanations, and guided examples.
- **Code and blocks:** edit in code, blocks, or a split view; both views represent the same program.
- **Make games:** build 2D and 3D projects with keyboard and mouse input, sound, images, shapes, and animation.
- **Learn and debug:** use breakpoints, step-through execution, variable watches, command hints, and a live
  problem checker.
- **Buttons, textboxes, sliders, and checkboxes:** build menus and forms that work in both 2D and 3D games.
- **Convert existing code:** translate Python, JavaScript, and Lua code, including pygame, p5.js, LÖVE, and
  canvas games, into Gublan.
- **Export projects:** package a Gublan game as a Windows executable, or export it as Python, JavaScript, or Lua.
- **Code together:** host a live session on your computer so others on your network can edit with you.
- **AI helpers:** connect Claude, Copilot, Cursor, or another MCP client to read, write, check, run, test, and
  screenshot your project.
- **Make it yours:** choose a theme or write your own, and add commands with plugins and modules.
- **Save between runs:** `save` and `load` keep high scores and settings after a program closes.
- **Discord status:** show what you're making on Discord. You can change the wording, pictures and
  button, or turn it off. Programs can set their own status with `presence`.

## What's new in 1.0.5

**Language**

- `x => x * 2` creates a function inside an expression. Function names are values too, so you can store them
  in variables and pass them to other functions.
- New list functions: `map`, `filter`, `reduce`, `find`, `sortby`, `zip`, `slice`, `flat`, `any`, `every`,
  and `call`.
- New text and maths functions: `lines`, `words`, `capitalize`, `char`, `code`, `tojson`, `fromjson`,
  `textwidth`, `log`, `exp`, `noise`, and `randint`.
- `match` / `case`, `until`, `const`, and `try` / `catch` / `throw` handle choices and errors.
- `test` blocks and `assert` check your code. Run tests with `F7` in the studio or with `py gublancli.py test`.
- `use` loads a module from a modules folder. Gublan includes the `colors`, `easing`, and `grid` modules.
- `textbox`, `slider`, `checkbox`, and `focus` join `button` for building interfaces.
- Buttons, textboxes, sliders, checkboxes, text, and keyboard and mouse input all work in `mode 3d`. The
  interface is drawn flat on top of the 3D scene.

**Converting code**

- Converted programs need far fewer hand fixes. Key listeners become `keydown` checks,
  `requestAnimationFrame` and pygame loops become `forever` loops with `frame`, and `clock.tick` becomes `fps`.
  The converter also handles lambdas, comprehensions, `*args`, keyword arguments, and bitwise operators.
- **File > Export as another language** (`Ctrl+Shift+L`) turns a Gublan program into Python, JavaScript (a web
  page), or Lua (LÖVE). Each export includes a small runtime file, so the exported program runs on its own.

**Gublan Studio**

- **Tools > Code together** hosts or joins a live session. Everyone must enter a name before joining. Each
  person's cursor appears in their own colour with their name, and you can see who's here and send messages.
  The host shares a join code, and only people with that code can join.
- **Tools > Connect an AI helper (MCP)** shows how to connect an AI helper to the project folder through
  `py gublancli.py mcp`. The server can only access files inside that folder.
- Themes: Moss, Midnight, Ember, Paper (light), and Contrast (high contrast), plus your own JSON themes in the themes
  folder. Pick one under **Settings > Look**.
- Plugins are Python files that add commands, functions, and menu items. Plugins are off by default. You can
  turn them on under **Settings > Plugins**. Install only plugins you trust.
- Smoother interface: buttons glow on hover, dialogs fade in, and short messages slide in at the bottom.
  You can turn animations off in settings.
- Opening or importing a file that can't be read now shows a message instead of closing the studio.
- New guides cover each of these features. Press `F1` to open them.

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
| `F7` | Run the program's tests |
| `F1` | Open help |
| `Ctrl+1` / `Ctrl+2` / `Ctrl+3` | Code / blocks / split view |
| `Ctrl+Shift+P` | Open the command palette |
| `Ctrl+Space` | Show suggestions |
| `Ctrl+Shift+C` | Convert code |
| `Ctrl+Shift+L` | Export as another language |
| `Ctrl+Shift+B` | Export a program |

## Command line

```powershell
py gublancli.py run game.gubl
py gublancli.py check game.gubl
py gublancli.py test game.gubl
py gublancli.py convert old.py new.gubl
py gublancli.py translate game.gubl python out
py gublancli.py mcp my-project
py gublancli.py docs
```

`translate` accepts `python`, `javascript`, or `lua`. `mcp` starts the MCP server for a project folder. To use
it from an MCP client such as Claude Code, add a server that runs `py gublancli.py mcp <folder>`. The installed
app can run it with `GublanStudio.exe --mcp <folder>`.

## Live sessions

One person starts a session with **Tools > Code together > Start a live session**. Then **How to join** copies
the address, port, and join code. Others choose **Join a live session** and enter their name, the address, and
the code. A session holds up to 16 people, including the host, and every open file is shared.

Live sessions use port 47800 by default. You can change the port when you start a session. Windows may ask
whether to allow Gublan Studio through the firewall. To join from outside your network, the host must forward
the port on their router.

## Themes, plugins, and modules

These files live in the Gublan Studio settings folder (`%APPDATA%\GublanStudio`):

| Folder | Contents |
| --- | --- |
| `themes\` | JSON themes. Each theme can extend a built-in theme with `base` and override `colors` and `syntax`. |
| `plugins\` | Python plugins with a `setup(api)` function. `hello.py` is an example. |
| `modules\` | `.gubl` files that any program can load with `use`. |

A program's own `modules` folder takes priority over your settings folder, and both take priority over the
built-in modules.

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
4. Create a public release whose tag is exactly the new version, for example `1.0.5`. Don't add a `v` prefix.
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
| `gublanconvert.py` | Python, JavaScript, and Lua to Gublan converter |
| `gublantranslate.py`, `runtimes/` | Gublan to Python, JavaScript, and Lua, with each language's runtime |
| `gublanmcp.py` | MCP server for AI helpers |
| `modules/` | Built-in modules for `use` |
| `gublanpresence.py` | Discord status (rich presence) module used by the studio and by programs |
| `gublanide.py`, `studio/` | Gublan Studio editor, including live sessions (`collab.py`) and plugins (`plugins.py`) |
| `gublancli.py` | Command-line interface |
| `GublanStudio.spec`, `GublanStudio.iss`, `build.ps1` | App build, Windows installer, and release build script |
| `docs/`, `examples/`, `tests/` | Reference, sample programs, and tests |
