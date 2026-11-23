"""build docs/COMMANDS.md from the command table in gublancore, so the docs can't drift from the language.

    py gublancli.py docs
"""

import os

from gublancore import CATEGORY_ORDER, COLORS, COMMAND_SPECS, EXPRESSION_FUNCTIONS

CATEGORY_TITLES = {
    "basics": "basics: printing, variables and maths",
    "control": "control: choices and loops",
    "functions": "functions, modules and other files",
    "testing": "testing your code",
    "lists and maps": "lists and maps",
    "display": "the window and colours",
    "2d": "2d shapes, text and pictures",
    "3d": "3d",
    "ui": "buttons, textboxes, sliders and checkboxes",
    "objects": "moving and changing shapes",
    "input": "keyboard, mouse and questions",
    "sound": "sound and music",
    "web": "the web",
    "saving": "saving values between runs",
    "discord": "your discord status",
    "plugins": "commands from plugins",
}

# a few words under a category heading, for ideas that need more than one command's summary
CATEGORY_NOTES = {
    "ui": "these work in `mode 2d` and in `mode 3d`, where they are drawn flat on top of the 3d scene. click a "
          "textbox to type in it; the game's own keys pause while someone is typing. `name.text`, `name.value`, "
          "`name.checked`, `name.focused` and `name.submitted` read them, and `name.text = \"hi\"` changes them.",
    "testing": "a `test` block is skipped when the program runs. run tests (f7 in the studio, or "
               "`py gublancli.py test game.gubl`) runs each test on its own with a fresh start, and lists which "
               "passed. tests can use every function in the file.",
    "saving": "saved values are kept in a small file for each program (on windows in `%APPDATA%\\Gublan\\saves`), "
              "so a high score or the level someone reached is still there next time. inside expressions, "
              "`load(\"name\", default)` gives a saved value and `saved(\"name\")` checks for one.",
    "discord": """while the discord app is open, `presence` lines change the status on your discord profile. in gublan
studio they replace the studio's own status while the program runs (settings, under discord, turns this off).
exported games show it too. discord updates every few seconds, so setting it often is fine.

| line | what it shows |
| --- | --- |
| `presence details <text...>` | the first line of the status |
| `presence state <text...>` | the second line |
| `presence image <picture> [hover text...]` | the big picture: a picture's https address, or the name of one uploaded to your discord application |
| `presence smallimage <picture> [hover text...]` | the small round picture in the corner of the big one |
| `presence button <https-address> <label...>` | a button other people can click. two at most |
| `presence party <players> <most-players>` | how full the group is, like (1 of 4) |
| `presence timer` | how long since this line ran. `presence timer off` hides it |
| `presence countdown <seconds>` | the time left |
| `presence app <application id>` | use your own discord application instead of gublan studio's |
| `presence clear` | remove everything the program set |

a part written without values is removed, like `presence state`. the status says the program is playing gublan
studio unless you make your own application at https://discord.com/developers/applications and use its id with
`presence app`: then it shows your game's name and the pictures you upload there.""",
}

INTRO = """# gublan commands

gublan programs are lists of commands, one per line. the first word says what to do and the rest are
its values. this file is made from the language itself (`py gublancli.py docs`), so every command is here.

## how lines work

- one command per line. blank lines are fine.
- lines starting with `//` are notes for people and are skipped.
- put "quotes" around text or file paths that contain spaces: `sound "assets/jump sound.wav"`.
- anything inside `{braces}` is worked out first: `print you have {coins * 2} coins`.
- blocks (`if`, `loop`, `forever`, `while`, `until`, `for`, `match`, `try`, `test`, `function`) end with
  `end`. indenting the lines inside is optional but makes programs much easier to read.

## variables

```gublan
score = 0
score += 10
speed = 2
speed = speed * 1.5
name = "sam"
player = {"x": 10, "y": 20}
player.x += 5
items = ["sword", "shield"]
print {items[0]} and {len(items)} things
```

`=` sets a variable. `+=`, `-=`, `*=` and `/=` change it. `set name = value`, `add`, `sub`, `mul`, `div`
and `calc` do the same in command form. answers typed into `input` become numbers when they look like
numbers.

## choices and loops

```gublan
score = 7
if score > 10
    print you win
else if score > 5
    print close!
else
    print try again
end

for i = 1 to 10 step 2
    print {i}
end

for fruit in ["apple", "pear"]
    print {fruit}
end

lives = 3
while lives > 0
    print {lives} lives left
    lives -= 1
end
```

`elseif` and `elif` mean the same as `else if`. compare with `==`, `!=`, `<`, `>`, `<=` and `>=`, and join
conditions with `and`, `or` and `not`. `break` leaves a loop and `continue` skips to its next round.

## expressions

expressions are used after `=`, in `if`, `while`, `return` and `for`, and inside `{braces}` anywhere.

- maths: `+ - * / // % **` and brackets. text joins directly with `+`; comma-separated print values join with spaces.
- conversions: `string(value)` (also `str(value)`) converts to text; `number(value)` (also `num(value)`) converts numeric text to a number.
- lists: `[1, 2, 3]`, items with `list[0]`. maps: `{"name": "sam"}`, values with `map.name` or `map["name"]`.
- vectors: `vec2(x, y)` and `vec3(x, y, z)` can be added, subtracted and multiplied by numbers.
- `true`, `false`, `none` and `pi`. `dt` is the seconds since the last `frame` (0 before the first one).
- functions you make with `function` can be used in expressions: `{double(21)}`.
- little functions: `x => x * 2` (or `lambda x: x * 2`) is a value you can keep in a variable and pass to
  `map`, `filter`, `reduce`, `find`, `sortby`, `any` and `every`: `doubled = map(scores, s => s * 2)`.
- build lists with a `for` inside brackets: `[x * x for x in numbers if x > 0]`.
- any function can be written after a value: `name.upper()` is `upper(name)`, `items.sort()` is `sort(items)`.
- whole numbers also have `&`, `|`, `^`, `<<`, `>>` and `~` for working with bits.

## functions

```gublan
function greet name="world" times=1
    local message = "hi " + name
    loop times
        print {message}
    end
end

greet()
greet("sam", 2)
```

parameters can have a default (`name="world"`), used when the call leaves that value out. defaults come
after the parameters without one. `local` makes a variable that only lives inside the function, so it can't
clash with one of the same name somewhere else.

## long lines

```gublan
levels = [
    "grass",
    "caves",
    "castle",
]
print {len(levels)} levels
```

a line that ends with an open `[`, `(` or `{` (or a comma inside one) carries on over the next lines until the
brackets close. that makes long lists, maps and function calls easier to read.

## when things go wrong

```gublan
try
    coins = number("lots")
catch problem
    print that didn't work: {problem}
end
```

lines between `try` and `catch` that fail jump to `catch` instead of stopping the program. `throw` makes your
own error, and `assert` throws one when a condition is false.
"""

GAME_EXAMPLE = """## a whole small game

```gublan
window 640 480 coin catcher
mode 2d
background navy
color moss
box player 300 440 60 16
color gold
circle coin 320 0 10
score = 0
text hud 10 10 score 0
forever
    if keydown("left")
        move player {-400 * dt} 0
    end
    if keydown("right")
        move player {400 * dt} 0
    end
    move coin 0 {200 * dt}
    if touching("player", "coin")
        score += 1
        place coin {random(20, 620)} 0
    end
    text hud 10 10 score {score}
    frame
end
```
"""


# block commands need their whole block to make sense, so they get complete examples
FULL_EXAMPLES = {
    "if": """score = 12
if score > 10
    print you win
end""",
    "elseif": """score = 7
if score > 10
    print great
elseif score > 5
    print good
end""",
    "else": """lives = 0
if lives > 0
    print keep going
else
    print game over
end""",
    "then": """lives = 0
if lives < 1
    then kill
end""",
    "end": """loop 3
    print hi
end""",
    "loop": """loop 3
    print hip hip hooray
end""",
    "forever": """mode 2d
forever
    frame
end""",
    "while": """lives = 3
while lives > 0
    print {lives} lives left
    lives -= 1
end""",
    "for": """for i = 1 to 10 step 3
    print {i}
end
for fruit in ["apple", "pear"]
    print {fruit}
end""",
    "break": """for i = 1 to 100
    if i > 3
        break
    end
    print {i}
end""",
    "continue": """for i = 1 to 6
    if i % 2 == 0
        continue
    end
    print {i} is odd
end""",
    "function": """function greet name
    print hello {name}
end
call greet world""",
    "return": """function double n
    return n * 2
end
print {double(21)}""",
    "call": """function add_up a b
    return a + b
end
call add_up 2 3
print {result}""",
    "until": """lives = 3
until lives == 0
    print {lives} lives left
    lives -= 1
end""",
    "match": """day = "sat"
match day
case "mon", "tue", "wed", "thu", "fri"
    print school
case "sat", "sun"
    print weekend!
else
    print that isn't a day
end""",
    "case": """roll = 6
match roll
case 6
    print you rolled the top number
case 1
    print unlucky
end""",
    "try": """try
    total = 10 / 0
catch problem
    print {problem}
end""",
    "catch": """try
    throw the door is locked
catch reason
    print could not go in: {reason}
end""",
    "throw": """function buy price coins
    if price > coins
        throw not enough coins
    end
    return coins - price
end
print {buy(3, 10)}""",
    "test": """function add a b
    return a + b
end

test adding works
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
end""",
    "assert": """lives = 3
assert lives > 0""",
    "const": """const speed = 4
x = 0
x += speed""",
    "textbox": """mode 2d
textbox username 20 60 240 your name
forever
    if username.submitted
        print hello {username.text}
    end
    frame
end""",
    "slider": """mode 2d
slider loudness 20 120 200 0 100 50
text shown 20 160 volume
forever
    shown.text = "volume " + str(loudness.value)
    frame
end""",
    "checkbox": """mode 2d
checkbox music 20 160 play music
forever
    if music.checked
        title music on
    end
    frame
end""",
    "focus": """mode 2d
textbox answer 20 60 240 type here
focus answer""",
    "use": """use easing
print {easeout(0.5)}""",
    "presence": """presence details exploring the caves
presence state level 1 of 5
presence timer
presence button https://github.com/gublans/gublan get gublan""",
    "load": """load best highscore 0
print the best score so far is {highscore}""",
    "local": """function total_of items
    local total = 0
    for item in items
        total += item
    end
    return total
end
print {total_of([1, 2, 3])}""",
}


_PLAYER = "mode 2d\nbox player 40 40 32 32"
_ENEMY = "mode 2d\nbox enemy 200 40 32 32"
# the one-line examples in the command table rely on things made earlier. in the docs each example gets the
# lines it needs first, so every example can be copied into an empty program and run as it is.
SETUP = {
    "print": "score = 3",
    "add": "score = 0",
    "sub": "lives = 3",
    "mul": "speed = 2",
    "div": "speed = 8",
    "calc": "width = 4\nheight = 3",
    "append": "list fruit apple pear",
    "item": "list fruit apple pear",
    "length": "list fruit apple pear",
    "put": "map inventory",
    "lookup": "map inventory\nput inventory coins 3",
    "has": "map inventory\nput inventory coins 3",
    "delete": _ENEMY,
    "hide": _ENEMY,
    "show": _ENEMY + "\nhide enemy",
    "paint": _PLAYER,
    "move": _PLAYER,
    "place": _PLAYER,
    "resize": _PLAYER,
    "animate": _PLAYER,
    "touching": _PLAYER + "\ncircle coin 50 50 8",
    "text": "mode 2d\nscore = 0",
    "image": "mode 2d",
    "sprite": "mode 2d",
    "spin": "mode 3d\ncube crate 0 0 -5 1",
    "key": "mode 2d",
    "keypressed": "mode 2d",
    "mouse": "mode 2d",
    "mousebutton": "mode 2d",
    "insert": "list fruit apple pear",
    "remove": "list fruit apple pear",
    "shuffle": "list fruit apple pear",
    "sort": "list scores 30 10 20",
    "cursor": "mode 2d",
    "save": "score = 120",
    "tween": "mode 2d\ncircle coin 200 120 10",
    "opacity": "mode 2d\nbox ghost 40 40 32 32",
    "layer": _PLAYER,
    "fixed": "mode 2d\ntext hud 10 10 score 0",
    "scroll": "mode 2d",
    "shake": "mode 2d",
    "ellipse": "mode 2d",
    "polygon": "mode 2d",
    "particles": "mode 2d\ncolor gold",
}


def _escape_usage(usage):
    return usage.replace("|", " | ").replace("  ", " ")


def commands_markdown():
    lines = [INTRO.rstrip(), ""]
    lines.append("## built-in functions")
    lines.append("")
    lines.append("| function | what it gives back |")
    lines.append("| --- | --- |")
    for about in EXPRESSION_FUNCTIONS.values():
        call, _space, rest = about.partition(") ")
        call = call + ")" if rest else about
        lines.append(f"| `{call}` | {rest} |")
    lines.append("")
    by_category = {}
    for name, spec in COMMAND_SPECS.items():
        by_category.setdefault(spec[0], []).append((name, spec))
    lines.append("## every command")
    lines.append("")
    lines.append(" ".join(f"`{name}`" for name in COMMAND_SPECS))
    lines.append("")
    for category in CATEGORY_ORDER:
        entries = by_category.get(category, [])
        if not entries:
            continue
        lines.append(f"## {CATEGORY_TITLES.get(category, category)}")
        lines.append("")
        if category in CATEGORY_NOTES:
            lines.append(CATEGORY_NOTES[category])
            lines.append("")
        for name, (_cat, usage, _min_args, summary, example) in entries:
            lines.append(f"### `{name}`")
            lines.append("")
            lines.append(summary)
            lines.append("")
            lines.append("```text")
            for form in usage.split(" | "):
                lines.append(form.strip())
            lines.append("```")
            lines.append("")
            example = FULL_EXAMPLES.get(name) or (f"{SETUP[name]}\n{example}" if name in SETUP and example
                                                  else example)
            if example:
                lines.append("```gublan")
                lines.append(example)
                lines.append("```")
                lines.append("")
    lines.append("## colours")
    lines.append("")
    lines.append("use these names with `color`, `background` and `paint`, or `#rrggbb`, or three numbers from 0 "
                 "to 255:")
    lines.append("")
    lines.append(", ".join(f"`{name}`" for name in COLORS))
    lines.append("")
    lines.append("## key names")
    lines.append("")
    lines.append("letters (`a` to `z`), digits, `space`, `enter`, `escape`, `tab`, `backspace`, `left`, `right`, "
                 "`up`, `down`, `shift`, `ctrl`, `alt` and `f1` to `f12`. short forms like `esc`, `spacebar` and "
                 "`arrowleft` work too.")
    lines.append("")
    lines.append(GAME_EXAMPLE.rstrip())
    lines.append("")
    return "\n".join(lines)


def write(path=None):
    path = path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "COMMANDS.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(commands_markdown())
    return path
