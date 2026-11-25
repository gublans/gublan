# Gublan

<p align="center">
  <img src="logo.png" width="100" alt="Gublan logo">
</p>

Gublan is a small programming language and creative studio for making games and programs. Write readable,
English-like commands, then run them in the built-in editor. Gublan Studio includes code and block editing,
2D and 3D graphics, debugging tools, live sessions for coding together, and converters to and from Python,
JavaScript, and Lua.

[Website](https://gublan.xyz/) · [Try it in your browser](https://gublan.xyz/playground/) ·
[Download for Windows](https://gublan.xyz/#download) ·
[Language reference](docs/COMMANDS.md) · [Examples](examples/)

## Features

- **A beginner-friendly language:** short commands, helpful errors, live explanations, and guided examples.
- **Code and blocks:** edit in code, blocks, or a split view; both views represent the same program.
- **Make games:** build 2D and 3D projects with keyboard and mouse input, sound, images, shapes, and animation.
- **Build 3D scenes with the mouse:** the 3D scene editor places, drags, sizes, turns, and colours shapes, and
  writes ordinary Gublan lines into your program as you go, so the code and the scene always match.
- **Read and write files:** keep notes, logs, levels, and CSV tables in text files next to your program.
- **Publish to gublan.xyz:** put a program on the website with one click, so anyone can play it, read the code,
  and remix it in their browser.
- **Learn and debug:** use breakpoints, step-through execution, variable watches, command hints, and a live
  problem checker.
- **Buttons, textboxes, sliders, and checkboxes:** build menus and forms that work in both 2D and 3D games.
- **Convert existing code:** translate Python, JavaScript, and Lua code, including pygame, p5.js, LÖVE, and
  canvas games, into Gublan.
- **Export projects:** package a Gublan game as a Windows executable, or export it as Python, JavaScript, or Lua.
- **Code together:** host a live session on your computer so others on your network can edit with you. Guests
  can run shared programs with the host's pictures, sounds, and music.
- **AI helpers:** connect Claude, Copilot, Cursor, or another MCP client to read, write, check, run, test, and
  screenshot your project. Gublan Studio can add itself to Claude Desktop and Cursor for you.
- **Make it yours:** choose a theme or write your own, pick an accent colour, cursor, typing effect, and sound set,
  style your game windows and popups, and add commands with plugins and modules. Themes switch instantly.
- **Your work is safe:** unsaved programs are copied every few seconds and offered back if the studio ever
  closes unexpectedly.
- **Save between runs:** `save` and `load` keep high scores and settings after a program closes.
- **Discord status:** show what you're making on Discord. You can change the wording, pictures and
  button, or turn it off. Programs can set their own status with `presence`.

## What's new in 1.0.9

**The 3D scene editor**

- **Tools > 3D scene editor** (`Ctrl+Shift+D`) shows your program's 3D shapes in a view you can fly around.
  Add a block, cube, sphere, cylinder, cone, or plane, then move, size, turn, and colour it with the mouse, the
  arrow keys, or exact numbers. **Snap** keeps the numbers tidy.
- The program's code is the only copy of the scene. Every change is written straight into the matching line, so
  `Ctrl+Z` works in both places and the program runs the same way with or without the editor.
- **Set game camera here** writes a `camera` line that puts the game's camera where you are looking.

**More 3D**

- New shapes: `block`, `cylinder`, `cone`, and `plane`. Every shape can take a colour at the end of its line.
- `turn` tilts and turns shapes, `lookat` points the camera at a spot or a shape, `walk` moves the camera the way it
  faces for first-person games, and `light` changes where the light comes from and how bright it is.
- `velocity` and `gravity` keep objects moving by themselves, in 2D and 3D.
- New functions: `camerapos()`, `camerayaw()`, `camerapitch()`, `screenpos()`, `distance()`, `normalize()`,
  `dot()`, and `cross()`.

**Files**

- `writefile`, `appendfile`, `readfile`, `deletefile`, `makefolder`, `copyfile`, and `renamefile` work with text
  files in your program's folder. Programs can't reach outside that folder.
- `readfile()`, `readlines()`, `fileexists()`, `isfolder()`, `listfiles()`, `filesize()`, `filename()`, and
  `extension()` work inside expressions. `fromcsv()` and `tocsv()` turn tables into CSV text and back.

**More useful commands and functions**

- `seed` makes random numbers repeat, `swap` swaps two variables, `pop` takes an item out of a list, and
  `screenshot` saves a picture of the game window.
- Dates and times: `year()`, `month()`, `day()`, `hour()`, `minute()`, `second()`, `weekday()`, and `timetext()`.
- Text and lists: `left()`, `right()`, `matches()`, `percent()`, `sample()`, and `findindex()`.
- `clicked()` and `hovering()` make any shape work like a button.

**Publishing and sharing**

- **File > Publish to gublan.xyz** puts a program on the website with a name and a description. Anyone with the
  link can play it, read the code, and remix it, and it is listed on [gublan.xyz/explore](https://gublan.xyz/explore/).
  Data files and included programs go up with it. You can update it later or take it down.
- **File > Copy playground link** (also on each tab's right-click menu) copies a link that has the whole program
  in it, the same kind the playground's **Share** button makes.

**Windows**

- Double-click a `.gubl` file to open it in Gublan Studio, or right-click it and choose **Run with Gublan**. Turn
  this on in the installer or with **Tools > Open .gubl files from Explorer**. Files opened while the studio is
  already running open in a new tab instead of a second window.

**Studio**

- **Find in files** (`Ctrl+Shift+F`) searches every program and text file in the project folder.
- **Rename** (`F2`) renames a variable, function, or object everywhere in the program, without touching the same
  word inside text. One `Ctrl+Z` undoes it.
- **Reopen closed tab** (`Ctrl+Shift+T`) and **Restart** (`Ctrl+Shift+F5`).
- Replacing the whole program (from the block view, a conversion, or a rename) is now one undo step.

**The playground**

- 3D programs and files now run in the browser. Files are kept in your browser and listed in the **files** tab.
- Much better on phones: the code, game, and output views switch with a bar at the bottom, a row of symbol keys
  sits above the keyboard, and games get an on-screen pad for the arrow keys and buttons.
- **Publish** shares a program on gublan.xyz, and the new **explore** page lists what people have made.

## What's new in 1.0.7

**A livelier Gublan Studio**

- Panels slide open and closed. The status bar fades between states, pulses while a program runs, and flashes
  red on an error. Messages type themselves in, and pasted lines and **Go to line** briefly light up. Choose an
  animation speed (slow, normal, or fast) or turn animations off in **Tools > Settings**, under **look**.
- The editor has a smooth text cursor that glides to where you click or type. You can change its shape (line,
  block, or underline), blinking (fade, blink, or none), movement (glide or jump), and thickness. New letters can
  fade in, settle like wet ink, glow, or just appear.
- Soft sounds play when things open, close, run, stop, finish, save, pass a test, or go wrong. Choose a sound set
  (soft, glass, wood, or retro) and a volume, or add a quiet tick as you type. The sounds are generated by the
  studio, so there are no sound files to install. Turn them off under **sounds**.
- More ways to make it yours: six new themes (fern, dusk, glacier, rosewood, terminal, and latte), an accent
  colour, a code font, line spacing, interface size, and rainbow brackets.

**Game windows and popups**

- **Tools > Game window and popups** sets how game windows start: size, title, background, text colour, fps, and
  an fps counter. It also styles popups and `input` questions: colours, border, width, text size, how much they
  dim the game, where they appear, how they open (pop, fade, slide, or none), key hints, and a soft opening
  sound.
- Start from a preset look (moss, paper, night, arcade, or glass) or match your studio theme. A live preview
  updates as you change settings, and **Try it** opens a demo game window.
- A program's own `window`, `background`, and `fps` lines still win. Executable exports and JavaScript web
  exports keep the look you chose. On the command line, set `GUBLAN_STYLE` to a JSON object of the same
  settings.

**The language**

- New commands: `ellipse`, `polygon`, `tween` (with `linear`, `in`, `out`, `inout`, `smooth`, `bounce`,
  `elastic`, and `back` easing), `opacity`, `layer`, `fixed`, `scroll`, `shake`, `particles`, `beep` (a tone
  without a sound file), and `local` (a variable that only exists inside its function).
- New functions for lists (`take`, `drop`, `first`, `last`, `chunk`, `fill`, `without`, `enumerate`, `minby`,
  `maxby`, `groupby`), maps (`entries`, `frompairs`, `merge`, `get`), numbers (`median`, `product`, `gcd`,
  `hypot`, `fract`, `snap`, `between`, `smoothstep`, `ease`), text (`commas`, `ordinal`, `plural`, `wraptext`),
  colours (`mixcolor`, `randomcolor`), timing (`cooldown`, `pulse`, `after`), and the view (`scrollx`,
  `scrolly`).
- Programs translated to Python, JavaScript, and Lua support all of these.
- Fixed: a word in `print` text that is also a function name, such as `max` or `first`, now stays a word in
  translated programs.
- New guides cover each of these features. Press `F1` to open them.

**The playground**

- Projects with several files, in tabs. Use `include` to load one file from another.
- Suggestions as you type, automatic `end` lines and closing brackets, a hint bar for the current line, find and
  replace, a command palette (`Ctrl+Shift+P`), go to line (`Ctrl+G`), and a searchable reference panel (`F1`
  looks up the word under the cursor).
- The same themes, accent colours, cursor and typing effects, sounds, and game window and popup looks as Gublan
  Studio, in a new settings drawer (`Ctrl+,`).
- Save a picture of the game, go full screen, download a program as a web page, and open or drop `.gubl` files
  onto the page. **Share** links can hold a whole project.
- Resizable panes, smoother animations, and a layout that works on phones.

## What's new in 1.0.6

**Fewer crashes**

- Gublan Studio no longer crashes at random while it checks your code, runs tests, exports, converts code, or
  tests the MCP server. Background work used to hand its results to the window in a way Tk doesn't allow from
  other threads. It now goes through a safe queue. Python's memory clean-up also runs only on the window's
  thread, which stops another rare crash.
- Choosing a theme no longer crashes the studio. Themes now switch instantly, without a restart. Restarting
  (for a theme, a plugin change, or an update) also no longer crashes the installed app.
- If the studio ever closes unexpectedly, the next start offers to restore every program you hadn't saved.
  Unsaved programs are copied to the settings folder every 15 seconds.
- **Help > Report a problem** shows the latest entries from `errors.log` and `crash.log`, ready to copy into a bug
  report.

**Opening files**

- Pictures, sounds, archives, and other binary files open in their folder instead of loading into the editor as
  text.
- Files saved as UTF-16 (Notepad's "Unicode") or Windows-1252 now open correctly. They are saved as UTF-8.
- Gublan Studio asks before opening files larger than 2 MB or with very long lines, and offers to show files
  larger than 40 MB in their folder instead.
- Files too large for the blocks view stay in code view instead of freezing the window.
- When another program changes an open file, such as an AI helper, another editor, or git, Gublan Studio
  reloads it. If you also have unsaved changes, it asks which version to keep. **File > Reload from disk**
  reloads a file manually. You can turn off automatic reloading in `settings.json` with `reload_changed_files`.

**Live sessions**

- Guests can run shared programs that use pictures, sounds, music, included files, and modules from the host's
  computer. The studio downloads each file the first time a program needs it and keeps it for the rest of the
  session. If the file changes on the host, the guest downloads it again.
- Only files inside the folder of the host's saved program can be shared, and only pictures, sounds, music,
  fonts, 3D models, and Gublan, text, JSON, or CSV files up to 64 MB. The host can turn file sharing off when
  starting a session.
- Hosts and guests both need 1.0.6 to share files. Editing together still works with 1.0.5.

**AI helpers (MCP)**

- **Tools > Connect an AI helper** has separate choices for Claude Code, Claude Desktop, Cursor, and VS Code.
  **Add it to Claude Desktop** and **Add it to Cursor** write the app's settings file for you, keep everything
  already in it, and save the old file as `.bak`. This includes the Microsoft Store version of Claude Desktop,
  which keeps its settings in a different folder.
- The Claude Code command now uses `--scope user`, so it works from any folder.
- The server starts even when an AI app passes a folder with quotes, a trailing slash, or a folder that doesn't
  exist. If an app starts the server without a folder, it uses the current folder when it contains Gublan
  programs, then the project last opened in Gublan Studio, then `Documents\Gublan`. It no longer uses the
  app's own install folder.
- Output from libraries and programs started by tools can't mix with the server's messages anymore.
- **Test it** shows the server's own error message when it fails to start.

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

## Try it online

The [Gublan playground](https://gublan.xyz/playground/) runs Gublan in a web browser, with nothing to
install. Write a program or open an example, then press **Run** (or `Ctrl+Enter`). Problems show up while you
type. **Share** copies a link that contains your program (or your whole project), and the **JavaScript** tab
shows what your program turns into. Press `Ctrl+Shift+P` to search every action, and `Ctrl+,` for settings.

The playground runs 2D and 3D games, text programs, keyboard and mouse input, buttons, text boxes, `input`,
`save`/`load`, and files (both kept in your browser). On a phone, the code, game, and output views switch with
the bar at the bottom, and games get an on-screen pad. **Publish** puts a program on
[gublan.xyz/explore](https://gublan.xyz/explore/) with a short link. Pictures or sounds from your computer and the
3D scene editor need Gublan Studio.

### Gublan accounts

Sign in with Discord to keep your settings in your Gublan account. In the playground, use the **sign in** button;
in Gublan Studio, use **Tools > account (sync settings)**. The playground also keeps your files there. Your settings then
follow you to any browser or computer where you sign in. When a setting changes in two places, the most recent change
wins. Pane sizes, recent files and other things that belong to one computer stay local. **delete my saved data**
(in the playground's settings, or the studio's account menu) removes everything stored in your account.

Accounts run on [Supabase](https://supabase.com). The project URL and publishable key are in `studio/account.py`,
and `web/build_site.py` copies them into the website's `account.js`. Both are public on purpose. Row-level security
on the `user_data` table keeps each person's row private. Never put a `service_role`/secret key or the Discord
client secret in this repository.

Publishing needs a `creations` table. Run [docs/supabase_creations.sql](docs/supabase_creations.sql) once in the
Supabase **SQL Editor** (running it again is safe). Anyone can read published creations, but only the person who
published one can change or delete it, and each person can publish up to 100.

It uses the same checker and translator as Gublan Studio's JavaScript export, running in the browser through
[Pyodide](https://pyodide.org), so it always matches the current language. The website lives in `web/`: the home
page in `web/home/` (published at <https://gublan.xyz/>) and the playground in `web/playground/` (published at
<https://gublan.xyz/playground/>). To try it locally:

```powershell
py web/build_site.py
py -m http.server -d _site
```

Then open <http://localhost:8000> for the home page, or <http://localhost:8000/playground/>. Every push to `main` that changes the language or the page publishes it
again through `.github/workflows/pages.yml`. To turn this on the first time, open the repository's
**Settings > Pages** and set **Source** to **GitHub Actions**.

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
| `Ctrl+Shift+D` | Open the 3D scene editor |
| `Ctrl+Shift+F` | Find in files |
| `F2` | Rename everywhere in this file |
| `Ctrl+Shift+T` | Reopen a closed tab |
| `Ctrl+Shift+F5` | Restart the program |

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
app can run it with `GublanStudio.exe --mcp <folder>`. The easiest setup is **Tools > Connect an AI helper**,
which writes the configuration for Claude Desktop, Cursor, VS Code, or a Claude Code project for you.

If an AI helper says the server failed to start, open **Tools > Connect an AI helper** and press **Test it**.
For Claude Desktop, quit it completely (including from the system tray) after adding the server, then open it
again.

## Live sessions

One person starts a session with **Tools > Code together > Start a live session**. Then **How to join** copies
the address, port, and join code. Others choose **Join a live session** and enter their name, the address, and
the code. A session holds up to 16 people, including the host, and every open file is shared.

When a guest runs a shared program, the guest's studio downloads each picture, sound, music file, include, and
module the program uses from the folder of the host's saved program. Copies are kept in a temporary folder until
the session ends. Only files inside that folder are shared, and the host can turn this off in the start window.

Live sessions use port 47800 by default. You can change the port when you start a session. Windows may ask
whether to allow Gublan Studio through the firewall. To join from outside your network, the host must forward
the port on their router.

## Themes, plugins, and modules

These files live in the Gublan Studio settings folder (`%APPDATA%\GublanStudio`):

| Folder or file | Contents |
| --- | --- |
| `themes\` | JSON themes. Each theme can extend a built-in theme with `base` and override `colors` and `syntax`. |
| `plugins\` | Python plugins with a `setup(api)` function. `hello.py` is an example. |
| `modules\` | `.gubl` files that any program can load with `use`. |
| `recovery\` | Copies of unsaved programs, used to restore them after a crash. |
| `errors.log`, `crash.log` | Problems the studio recorded. **Help > Report a problem** shows them. |

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
4. Create a public release whose tag is exactly the new version, for example `1.0.6`. Don't add a `v` prefix.
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
| `gublanide.py`, `studio/` | Gublan Studio editor, including live sessions (`collab.py`), plugins (`plugins.py`), crash protection and recovery (`guard.py`), file reading (`textfiles.py`), the 3D scene editor (`scene3d.py`), find in files and rename (`refactor.py`), accounts and publishing (`account.py`), and Explorer integration (`shell.py`) |
| `gublancli.py` | Command-line interface |
| `web/` | The website: home page (`web/home/`), published creations (`web/explore/`), and online playground (`web/playground/`), published to GitHub Pages by `.github/workflows/pages.yml` |
| `GublanStudio.spec`, `GublanStudio.iss`, `build.ps1` | App build, Windows installer, and release build script |
| `docs/`, `examples/`, `tests/` | Reference (including the Supabase setup SQL), sample programs, and tests |
