# gublan commands

gublan programs are lists of commands, one per line. the first word says what to do and the rest are
its values. this file is made from the language itself (`py gublancli.py docs`), so every command is here.

## how lines work

- one command per line. blank lines are fine.
- lines starting with `//` are notes for people and are skipped.
- put "quotes" around text or file paths that contain spaces: `sound "assets/jump sound.wav"`.
- anything inside `{braces}` is worked out first: `print you have {coins * 2} coins`.
- blocks (`if`, `loop`, `forever`, `while`, `for`, `function`) end with `end`. indenting the lines inside
  is optional but makes programs much easier to read.

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

## built-in functions

| function | what it gives back |
| --- | --- |
| `abs(x)` | the distance of x from zero |
| `min(a, b, ...)` | the smallest value |
| `max(a, b, ...)` | the largest value |
| `round(x, digits)` | round to the nearest whole number |
| `floor(x)` | round down |
| `ceil(x)` | round up |
| `sqrt(x)` | square root |
| `sin(degrees)` | sine of an angle in degrees |
| `cos(degrees)` | cosine of an angle in degrees |
| `tan(degrees)` | tangent of an angle in degrees |
| `atan2(y, x)` | angle in degrees towards a point |
| `rad(degrees)` | convert degrees to radians |
| `deg(radians)` | convert radians to degrees |
| `clamp(x, low, high)` | keep x between low and high |
| `lerp(a, b, t)` | blend from a to b |
| `sign(x)` | -1, 0 or 1 |
| `dist(x1, y1, x2, y2)` | or dist(a, b) distance between points |
| `len(x)` | number of items or letters |
| `str(x)` | turn a value into text |
| `string(x)` | turn a value into text |
| `num(x)` | turn text into a number |
| `number(x)` | turn text into a number |
| `int(x)` | whole-number part |
| `upper(text)` | uppercase letters |
| `lower(text)` | lowercase letters |
| `trim(text)` | remove spaces at the ends |
| `contains(list-or-text, value)` | true if it is inside |
| `join(list, separator)` | glue list items into text |
| `split(text, separator)` | cut text into a list |
| `replace(text, old, new)` | swap parts of text |
| `random(a, b)` | random number between a and b |
| `choice(list)` | a random item |
| `keydown("left")` | true while a key is held |
| `keypressed("space")` | true once per key press |
| `mousedown("left")` | true while a mouse button is held |
| `mousex()` | mouse x position |
| `mousey()` | mouse y position |
| `touching("a", "b")` | true when two objects overlap |
| `exists("name")` | true if an object or variable exists |
| `time()` | seconds since the program started |
| `vec2(x, y)` | make a 2d vector |
| `vec3(x, y, z)` | make a 3d vector |
| `mag(vector)` | length of a vector |
| `type(x)` | the kind of value as text |
| `range(start, end)` | list of numbers from start up to end - 1 |
| `mousepressed("left")` | true once per mouse click |
| `pow(x, n)` | x to the power of n |
| `asin(x)` | angle in degrees whose sine is x |
| `acos(x)` | angle in degrees whose cosine is x |
| `atan(x)` | angle in degrees whose tangent is x |
| `sum(list)` | add up every number in a list |
| `sort(list)` | a sorted copy of a list |
| `reverse(list)` | a reversed copy of a list |
| `keys(map)` | list of the names in a map |
| `values(map)` | list of the values in a map |
| `indexof(list, value)` | position of a value, or -1 |
| `overlap(a, b)` | true when two objects or [x, y, w, h] rectangles overlap |

## every command

`print` `set` `add` `sub` `mul` `div` `calc` `random` `time` `if` `elseif` `else` `then` `end` `loop` `forever` `while` `for` `break` `continue` `wait` `kill` `function` `call` `return` `include` `list` `append` `item` `length` `map` `put` `lookup` `has` `delete` `mode` `window` `title` `background` `color` `paint` `clear` `frame` `fps` `textsize` `box` `circle` `line` `text` `image` `sprite` `button` `ui` `vec2` `cube` `sphere` `spin` `camera` `vec3` `move` `place` `resize` `hide` `show` `animate` `touching` `key` `keypressed` `mouse` `mousebutton` `input` `popup` `sound` `music` `stopmusic` `stopsounds` `volume` `get`

## basics: printing, variables and maths

### `print`

show words, variables or {expressions} in the output panel.

```text
print <values...>
```

```gublan
score = 3
print score is {score}
```

### `set`

create or change a variable. the value can be a number, text, list, map or expression.

```text
set <name> = <value>
```

```gublan
set speed = 2.5
```

### `add`

add an amount to a variable.

```text
add <variable> <amount>
```

```gublan
score = 0
add score 10
```

### `sub`

subtract an amount from a variable.

```text
sub <variable> <amount>
```

```gublan
lives = 3
sub lives 1
```

### `mul`

multiply a variable by an amount.

```text
mul <variable> <amount>
```

```gublan
speed = 2
mul speed 2
```

### `div`

divide a variable by an amount.

```text
div <variable> <amount>
```

```gublan
speed = 8
div speed 2
```

### `calc`

work out a math expression and store the answer.

```text
calc <variable> <expression>
```

```gublan
width = 4
height = 3
calc area width * height
```

### `random`

pick a random number between min and max.

```text
random <variable> <min> <max>
```

```gublan
random roll 1 6
```

### `time`

store the seconds since the program started.

```text
time <variable>
```

```gublan
time now
```

## control: choices and loops

### `if`

run the lines below only when the condition is true. close with end.

```text
if <condition>
```

```gublan
score = 12
if score > 10
    print you win
end
```

### `elseif`

check another condition when the ones above were false.

```text
elseif <condition>
```

```gublan
score = 7
if score > 10
    print great
elseif score > 5
    print good
end
```

### `else`

run these lines when nothing above matched.

```text
else
```

```gublan
lives = 0
if lives > 0
    print keep going
else
    print game over
end
```

### `then`

stop the program when the surrounding if matched.

```text
then kill
```

```gublan
lives = 0
if lives < 1
    then kill
end
```

### `end`

close an if, loop, forever, while, for or function block.

```text
end
```

```gublan
loop 3
    print hi
end
```

### `loop`

repeat the lines below a number of times.

```text
loop <count>
```

```gublan
loop 3
    print hip hip hooray
end
```

### `forever`

repeat the lines below until the program stops.

```text
forever
```

```gublan
mode 2d
forever
    frame
end
```

### `while`

repeat the lines below while the condition stays true.

```text
while <condition>
```

```gublan
lives = 3
while lives > 0
    print {lives} lives left
    lives -= 1
end
```

### `for`

count through numbers or go through every item of a list.

```text
for <var> = <start> to <end> [step <n>]
for <var> in <list>
```

```gublan
for i = 1 to 10 step 3
    print {i}
end
for fruit in ["apple", "pear"]
    print {fruit}
end
```

### `break`

leave the loop you are in right now.

```text
break
```

```gublan
for i = 1 to 100
    if i > 3
        break
    end
    print {i}
end
```

### `continue`

skip to the next round of the loop.

```text
continue
```

```gublan
for i = 1 to 6
    if i % 2 == 0
        continue
    end
    print {i} is odd
end
```

### `wait`

pause for a number of seconds.

```text
wait <seconds>
```

```gublan
wait 0.5
```

### `kill`

stop the program.

```text
kill
```

```gublan
kill
```

## functions and other files

### `function`

make a reusable block of lines. close with end.

```text
function <name> [parameters...]
```

```gublan
function greet name
    print hello {name}
end
call greet world
```

### `call`

run a function. its answer goes into result.

```text
call <name> [arguments...]
```

```gublan
function add_up a b
    return a + b
end
call add_up 2 3
print {result}
```

### `return`

finish a function, optionally giving back a value.

```text
return [value]
```

```gublan
function double n
    return n * 2
end
print {double(21)}
```

### `include`

load another gublan script into this one.

```text
include <script.gubl>
```

```gublan
include helpers.gubl
```

## lists and maps

### `list`

make a list, optionally with starting values.

```text
list <name> [values...]
```

```gublan
list fruit apple pear
```

### `append`

add a value to the end of a list.

```text
append <list> <value...>
```

```gublan
list fruit apple pear
append fruit plum
```

### `item`

copy one list item into a variable. the first item is 0.

```text
item <list> <index> <variable>
```

```gublan
list fruit apple pear
item fruit 0 first
```

### `length`

store how many items or letters something has.

```text
length <value> <variable>
```

```gublan
list fruit apple pear
length fruit count
```

### `map`

make a map that stores values under names.

```text
map <name>
```

```gublan
map inventory
```

### `put`

store a value in a map.

```text
put <map> <key> <value...>
```

```gublan
map inventory
put inventory coins 3
```

### `lookup`

copy a map value into a variable.

```text
lookup <map> <key> <variable>
```

```gublan
map inventory
put inventory coins 3
lookup inventory coins amount
```

### `has`

set a variable to true if the map has that key.

```text
has <map> <key> <variable>
```

```gublan
map inventory
put inventory coins 3
has inventory coins found
```

### `delete`

remove an object from the scene, an item from a list or a key from a map.

```text
delete <object>
delete <list> <index>
delete <map> <key>
```

```gublan
mode 2d
box enemy 200 40 32 32
delete enemy
```

## the window and colours

### `mode`

open the 2d or 3d game window.

```text
mode 2d|3d
```

```gublan
mode 2d
```

### `window`

set the game window size and title.

```text
window <width> <height> [title...]
```

```gublan
window 800 600 my game
```

### `title`

change the game window title.

```text
title <text...>
```

```gublan
title space dodge
```

### `background`

set the background color.

```text
background <color>
```

```gublan
background navy
```

### `color`

choose the color for shapes you make next.

```text
color <name>
color #rrggbb
color <r> <g> <b>
```

```gublan
color green
```

### `paint`

recolor an existing object.

```text
paint <object|all> <color>
```

```gublan
mode 2d
box player 40 40 32 32
paint player red
```

### `clear`

redraw the window now.

```text
clear
```

```gublan
clear
```

### `frame`

draw the window and wait for the next frame. dt holds the seconds since the last frame.

```text
frame
```

```gublan
frame
```

### `fps`

set how many frames per second frame aims for.

```text
fps <frames-per-second>
```

```gublan
fps 60
```

### `textsize`

set the size of text you make next.

```text
textsize <pixels>
```

```gublan
textsize 32
```

## 2d shapes, text and pictures

### `box`

make a rectangle.

```text
box <name> <x> <y> <width> <height>
```

```gublan
box player 40 40 32 32
```

### `circle`

make a circle.

```text
circle <name> <x> <y> <radius>
```

```gublan
circle coin 200 120 10
```

### `line`

make a line.

```text
line <name> <x1> <y1> <x2> <y2> [thickness]
```

```gublan
line floor 0 400 540 400 3
```

### `text`

show text in the window.

```text
text <name> <x> <y> <content...>
```

```gublan
mode 2d
score = 0
text hud 10 10 score {score}
```

### `image`

show an image file.

```text
image <name> <path> <x> <y>
```

```gublan
mode 2d
image logo assets/logo.png 20 20
```

### `sprite`

show a resized image you can move and collide.

```text
sprite <name> <path> <x> <y> <width> <height>
```

```gublan
mode 2d
sprite hero assets/hero.png 40 40 48 48
```

### `button`

make a clickable button. its variable is 1 while pressed.

```text
button <variable> <x> <y> <width> <height> <label...>
```

```gublan
button start 20 20 120 40 start
```

### `ui`

make the quick button in the top-left corner.

```text
ui button <label>
```

```gublan
ui button destroy
```

### `vec2`

make an x/y value for positions and movement.

```text
vec2 <name> <x> <y>
```

```gublan
vec2 speed 3 0
```

## 3d

### `cube`

make a 3d cube.

```text
cube <name> <x> <y> <z> <size>
```

```gublan
cube crate 0 0 -6 1
```

### `sphere`

make a 3d sphere.

```text
sphere <name> <x> <y> <z> <radius>
```

```gublan
sphere moon 2 0 -7 0.5
```

### `spin`

rotate a cube, sphere, sprite or image (degrees).

```text
spin <object> <angle>
```

```gublan
mode 3d
cube crate 0 0 -5 1
spin crate 45
```

### `camera`

move and turn the 3d camera.

```text
camera <x> <y> <z> [yaw] [pitch]
camera <vec3>
```

```gublan
camera 0 1 0
```

### `vec3`

make an x/y/z value for 3d positions.

```text
vec3 <name> <x> <y> <z>
```

```gublan
vec3 spot 0 0 -6
```

## moving and changing shapes

### `move`

move an object by an amount.

```text
move <object> <dx> <dy> [dz]
move <object> <vector>
```

```gublan
mode 2d
box player 40 40 32 32
move player 3 0
```

### `place`

put an object at an exact position.

```text
place <object> <x> <y> [z]
```

```gublan
mode 2d
box player 40 40 32 32
place player 40 300
```

### `resize`

change an object's size.

```text
resize <object> <width> [height]
```

```gublan
mode 2d
box player 40 40 32 32
resize player 64 64
```

### `hide`

make an object invisible.

```text
hide <object>
```

```gublan
mode 2d
box enemy 200 40 32 32
hide enemy
```

### `show`

make a hidden object visible again.

```text
show <object>
```

```gublan
mode 2d
box enemy 200 40 32 32
hide enemy
show enemy
```

### `animate`

glide an object to a position over time.

```text
animate <object> <x> <y> [z] <seconds>
```

```gublan
mode 2d
box player 40 40 32 32
animate player 200 80 0.5
```

### `touching`

set a variable to 1 when two objects overlap.

```text
touching <variable> <object-a> <object-b>
```

```gublan
mode 2d
box player 40 40 32 32
circle coin 50 50 8
touching hit player coin
```

## keyboard, mouse and questions

### `key`

set a variable to 1 while a key is held.

```text
key <variable> <key-name>
```

```gublan
mode 2d
key left left
```

### `keypressed`

set a variable to 1 once each time a key is pressed down.

```text
keypressed <variable> <key-name>
```

```gublan
mode 2d
keypressed jump space
```

### `mouse`

store the mouse position.

```text
mouse <x-variable> <y-variable>
```

```gublan
mode 2d
mouse mx my
```

### `mousebutton`

set a variable to true while a mouse button is held.

```text
mousebutton <variable> left|middle|right
```

```gublan
mode 2d
mousebutton firing left
```

### `input`

ask the player to type something.

```text
input <variable> <question...>
```

```gublan
input name what is your name
```

### `popup`

show a message and wait for a key or click.

```text
popup <message...>
```

```gublan
popup you win
```

## sound and music

### `sound`

play a sound effect once.

```text
sound <path>
```

```gublan
sound assets/jump.wav
```

### `music`

play looping background music.

```text
music <path>
```

```gublan
music assets/theme.ogg
```

### `stopmusic`

stop the music.

```text
stopmusic
```

```gublan
stopmusic
```

### `stopsounds`

stop all sound effects.

```text
stopsounds
```

```gublan
stopsounds
```

### `volume`

set the volume from 0 (silent) to 1 (full).

```text
volume <0-to-1>
```

```gublan
volume 0.5
```

## the web

### `get`

read text from a public https website.

```text
get <https-url> <variable>
```

```gublan
get https://example.com page
```

## colours

use these names with `color`, `background` and `paint`, or `#rrggbb`, or three numbers from 0 to 255:

`red`, `blue`, `green`, `yellow`, `white`, `moss`, `orange`, `purple`, `cyan`, `black`, `gray`, `grey`, `darkgray`, `pink`, `brown`, `lime`, `teal`, `navy`, `gold`, `sand`, `sky`, `forest`

## key names

letters (`a` to `z`), digits, `space`, `enter`, `escape`, `tab`, `backspace`, `left`, `right`, `up`, `down`, `shift`, `ctrl`, `alt` and `f1` to `f12`. short forms like `esc`, `spacebar` and `arrowleft` work too.

## a whole small game

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
