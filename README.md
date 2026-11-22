# gublan

gublan is a small language for making games and programs. each line is one command, so a first program
can be a single line, and the same language grows into 2d and 3d games with keyboard, mouse, sound, lists,
maps and functions.

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

## get started

```powershell
py -m pip install pygame-ce pyopengl
py gublanide.py
```

`py gublanide.py hello.gubl` opens a program straight away. on windows, `launch_gublan.vbs` starts the studio
without a console window.

## gublan studio

- **welcome page**: start a new program, open one, or pick a template (hello, quiz, dodge, platformer,
  clicker, bouncing balls, 3d scene).
- **three ways to edit**: code, blocks, or both side by side (`ctrl+1`, `ctrl+2`, `ctrl+3`). blocks and code
  are the same program, so you can switch at any time.
- **beginner, standard and expert levels**: beginners get each line explained as they type and the
  variables panel when they run; experts get a quieter editor. change it from the top bar or settings.
- **help while typing**: suggestions, a hint bar with each command's parts, hover help, live problem
  checking with "did you mean" fixes, and a help panel with guides and every command.
- **run and debug**: run (`f5`), stop (`shift+f5`), pause (`f6`), step line by line (`f10`), breakpoints
  (`f9` or click the line number), a variables panel with a watch box, and a quick console under the output
  for trying a line or a sum.
- **media**: the assets panel previews pictures and plays sounds, inserts the right command for a file, and
  has a small pixel painter for sprites.
- **convert code**: tools > convert turns python, javascript or lua into gublan, including pygame, p5.js
  and love2d games. anything it can't convert stays as a `// todo` note so nothing is lost silently.
- **export**: file > export program builds a `.exe` that runs without python. it lists every picture and
  sound the program uses, flags missing ones, and bundles them so the paths in your code still work.
- **command palette** (`ctrl+shift+p`): every action by name, `:42` jumps to a line, `@name` jumps to a
  function or shape.

### keys

| key | does |
| --- | --- |
| `f5` | run, or continue when paused |
| `shift+f5` / `f6` / `f10` | stop / pause / step |
| `f8` | check for problems |
| `f9` | breakpoint on this line |
| `f1` | help |
| `ctrl+shift+p` | command palette |
| `ctrl+space` | suggestions |
| `ctrl+f` / `ctrl+h` / `ctrl+g` | find / replace / go to line |
| `ctrl+b` | switch code and blocks |
| `ctrl+shift+b` | export |
| `ctrl+shift+c` | convert code |
| `ctrl+=` / `ctrl+-` / `ctrl+0` | text size |
| `ctrl+,` | settings |

## the language

everything is in [docs/COMMANDS.md](docs/COMMANDS.md), which is generated from the language itself so it
always lists every command. the short version:

```gublan
score = 0                       // variables
score += 10
items = ["sword", "shield"]     // lists and maps
player = {"name": "sam", "hp": 3}
print {player.name} has {len(items)} things

if score > 5                    // choices
    print well done
else if score > 0
    print nearly
end

for i = 1 to 3                  // loops: loop, for, while, forever
    print {i}
end

function double n               // functions
    return n * 2
end
print {double(21)}

include helpers.gubl            // other files
```

games use `window`, `mode 2d` or `mode 3d`, shapes (`box`, `circle`, `image`, `text`, `cube`, `sphere`),
`move`, `place`, `paint`, `touching(...)`, `keydown(...)`, `sound`, `music` and a `forever` loop that ends
each round with `frame`. `dt` holds the seconds since the last frame, so `move player {200 * dt} 0` runs at
the same speed on every computer.

runnable examples are in [examples/](examples/).

## command line

```powershell
py gublancli.py run game.gubl          # run a program (also: py gublancli.py game.gubl)
py gublancli.py check game.gubl        # list problems without running
py gublancli.py convert old.py new.gubl
py gublancli.py docs                   # rebuild docs/COMMANDS.md
```

## building gublan studio itself

```powershell
py -m pip install pyinstaller
build_exe.bat
```

this makes `dist\GublanStudio.exe`. exporting games from that exe still needs python with pygame-ce,
pyopengl and pyinstaller installed, because each game is built by pyinstaller.

## tests

```powershell
$env:SDL_VIDEODRIVER = "dummy"; py -m unittest discover -s tests
```

## layout

| path | what |
| --- | --- |
| `gublancore.py` | the language: parser, checker and runtime |
| `gublanconvert.py` | python, javascript and lua to gublan |
| `gublanide.py`, `studio/` | the studio |
| `gublancli.py` | the command line |
| `docs/`, `examples/`, `tests/` | docs, example programs, tests |
