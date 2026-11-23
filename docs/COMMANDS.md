# gublan commands

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
| `chance(percent)` | true about that many times out of 100 |
| `shuffle(list)` | a copy of a list in a random order |
| `unique(list)` | a copy of a list without repeats |
| `count(list-or-text, value)` | how many times a value appears |
| `average(list)` | the average of a list of numbers |
| `startswith(text, start)` | true if the text begins with start |
| `endswith(text, ending)` | true if the text finishes with ending |
| `pad(value, width, fill)` | text filled on the left up to a width: pad(7, 3, 0) is 007 |
| `decimals(x, digits)` | a number as text with that many digits after the point |
| `wrap(x, low, high)` | wrap x around so it stays from low up to high |
| `remap(x, low1, high1, low2, high2)` | move a number from one range into another |
| `approach(x, target, step)` | move x towards target by at most step |
| `angleto(x1, y1, x2, y2)` | or angleto(a, b) the angle in degrees from one point to another |
| `hsv(hue, saturation, value)` | a colour from a hue (0 to 360), saturation and value (0 to 1) |
| `isnumber(x)` | true for a number, or text that looks like one |
| `date()` | today's date as text, like 2026-11-22 |
| `clock()` | the time of day as text, like 14:05 |
| `now()` | seconds since 1970, for timing things between runs |
| `saved("name")` | true if a value has been saved under that name |
| `load("name", default)` | a saved value, or the default when nothing was saved |
| `map(list, f)` | a new list with f done to every item: map(nums, x => x * 2) |
| `filter(list, f)` | the items where f is true: filter(nums, x => x > 0) |
| `reduce(list, f, start)` | combine every item into one value: reduce(nums, (a, b) => a + b, 0) |
| `find(list, f)` | the first item where f is true, or none |
| `any(list)` | or any(list, f) true when at least one item is true (or makes f true) |
| `every(list)` | or every(list, f) true when every item is true (or makes f true) |
| `sortby(list, f)` | a copy sorted by what f gives for each item: sortby(people, p => p.age) |
| `zip(a, b)` | pairs up two lists: zip([1, 2], ["a", "b"]) is [[1, "a"], [2, "b"]] |
| `slice(list-or-text, start, end)` | the part from start up to (not including) end |
| `flat(list)` | a list of lists joined into one list |
| `repeat(text-or-list, times)` | the value repeated that many times |
| `call(f, values...)` | run a function value with some values |
| `capitalize(text)` | the text with the first letter of each word in capitals |
| `lines(text)` | a list of the lines in some text |
| `words(text)` | a list of the words in some text |
| `char(code)` | the letter for a character code: char(65) is A |
| `code(letter)` | the character code of a letter: code("A") is 65 |
| `tojson(value)` | a value written as json text |
| `fromjson(text)` | json text turned into lists, maps, numbers and text |
| `textwidth(text, size)` | how many pixels wide some text is when shown |
| `log(x)` | or log(x, base) the logarithm of a number |
| `exp(x)` | e to the power of x |
| `noise(x)` | or noise(x, y) smooth random values from 0 to 1, for hills, clouds and wobbles |
| `randint(low, high)` | a random whole number from low to high |
| `hypot(x, y)` | the length of the long side of a right triangle, sqrt(x*x + y*y) |
| `fract(x)` | the part after the decimal point: fract(2.75) is 0.75 |
| `smoothstep(low, high, x)` | 0 below low, 1 above high and a smooth curve between |
| `snap(x, step)` | x rounded to the nearest step: snap(37, 16) is 32, handy for grids |
| `between(x, low, high)` | true when x is from low up to high |
| `ease(t, kind)` | bend a 0-to-1 amount into a curve. kinds: linear, in, out, inout, smooth, bounce, elastic, back |
| `gcd(a, b)` | the biggest whole number that divides both |
| `median(list)` | the middle value once the list is sorted |
| `product(list)` | every number in a list multiplied together |
| `first(list)` | the first item, or none when the list is empty |
| `last(list)` | the last item, or none when the list is empty |
| `take(list, n)` | the first n items |
| `drop(list, n)` | everything after the first n items |
| `chunk(list, size)` | the list cut into smaller lists: chunk([1, 2, 3], 2) is [[1, 2], [3]] |
| `enumerate(list)` | each item with its position: enumerate(["a", "b"]) is [[0, "a"], [1, "b"]] |
| `minby(list, f)` | the item that gives the smallest f: minby(enemies, e => e.x) |
| `maxby(list, f)` | the item that gives the biggest f |
| `groupby(list, f)` | a map that puts items together by what f gives: groupby(words, w => len(w)) |
| `without(list, value)` | a copy of the list with that value taken out everywhere |
| `fill(value, count)` | a list with the value repeated: fill(0, 3) is [0, 0, 0] |
| `merge(map, other)` | a new map with the names from both (other wins when they clash) |
| `get(map-or-list, key, default)` | a value, or the default when it isn't there |
| `entries(map)` | the map as a list of [name, value] pairs |
| `frompairs(list)` | a map from a list of [name, value] pairs |
| `commas(number)` | a number with commas every three digits: commas(1234567) is 1,234,567 |
| `ordinal(n)` | a number with st, nd, rd or th: ordinal(2) is 2nd |
| `plural(count, word)` | the count and the word, with an s when it isn't 1: plural(3, "coin") is 3 coins |
| `wraptext(text, width)` | a list of lines, each at most width letters long, broken between words |
| `mixcolor(a, b, t)` | a colour part way from a to b: mixcolor("red", "blue", 0.5) |
| `randomcolor()` | a random bright colour |
| `cooldown("name", seconds)` | true at most once every few seconds, like a gun that needs to reload |
| `pulse("name", seconds)` | true once every few seconds, for spawning enemies on a beat |
| `after("name", seconds)` | false until that many seconds after the first time you ask, then true |
| `scrollx()` | how far the view is scrolled to the right (see scroll) |
| `scrolly()` | how far the view is scrolled down (see scroll) |

## every command

`print` `set` `add` `sub` `mul` `div` `calc` `random` `time` `const` `if` `elseif` `else` `then` `end` `loop` `forever` `while` `for` `until` `match` `case` `try` `catch` `throw` `break` `continue` `wait` `kill` `function` `call` `return` `local` `include` `use` `test` `assert` `list` `append` `item` `length` `map` `put` `lookup` `has` `delete` `insert` `remove` `shuffle` `sort` `mode` `window` `title` `background` `color` `paint` `clear` `frame` `fps` `textsize` `scroll` `shake` `box` `circle` `line` `text` `image` `sprite` `vec2` `ellipse` `polygon` `particles` `cube` `sphere` `spin` `camera` `vec3` `button` `ui` `textbox` `slider` `checkbox` `focus` `move` `place` `resize` `hide` `show` `animate` `touching` `tween` `opacity` `layer` `fixed` `key` `keypressed` `mouse` `mousebutton` `input` `popup` `cursor` `sound` `music` `stopmusic` `stopsounds` `volume` `beep` `get` `save` `load` `forget` `presence`

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

### `const`

make a value that can't be changed later, like the speed of the game.

```text
const <name> = <value>
```

```gublan
const speed = 4
x = 0
x += speed
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

close an if, loop, forever, while, until, for, match, try, test or function block.

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

### `until`

repeat the lines below until the condition becomes true.

```text
until <condition>
```

```gublan
lives = 3
until lives == 0
    print {lives} lives left
    lives -= 1
end
```

### `match`

compare one value with several cases and run the case that fits. close with end.

```text
match <value>
```

```gublan
day = "sat"
match day
case "mon", "tue", "wed", "thu", "fri"
    print school
case "sat", "sun"
    print weekend!
else
    print that isn't a day
end
```

### `case`

inside match: run these lines when the value equals one of these.

```text
case <value> [, more values...]
```

```gublan
roll = 6
match roll
case 6
    print you rolled the top number
case 1
    print unlucky
end
```

### `try`

run lines that might fail. if one does, the program jumps to catch instead of stopping.

```text
try
```

```gublan
try
    total = 10 / 0
catch problem
    print {problem}
end
```

### `catch`

inside try: run these lines when something failed. the message goes into the variable (error if you leave it out).

```text
catch [variable]
```

```gublan
try
    throw the door is locked
catch reason
    print could not go in: {reason}
end
```

### `throw`

stop with your own error message. a try around it can catch it.

```text
throw <message...>
```

```gublan
function buy price coins
    if price > coins
        throw not enough coins
    end
    return coins - price
end
print {buy(3, 10)}
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

## functions, modules and other files

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

### `local`

make a variable that only lives inside the function it is in. when the function ends, the name goes back to what it was before.

```text
local <name> [= <value>]
```

```gublan
function total_of items
    local total = 0
    for item in items
        total += item
    end
    return total
end
print {total_of([1, 2, 3])}
```

### `include`

load another gublan script into this one.

```text
include <script.gubl>
```

```gublan
include helpers.gubl
```

### `use`

load a module: a gublan file from a modules folder (yours, your project's or a built-in one).

```text
use <module>
```

```gublan
use easing
print {easeout(0.5)}
```

## testing your code

a `test` block is skipped when the program runs. run tests (f7 in the studio, or `py gublancli.py test game.gubl`) runs each test on its own with a fresh start, and lists which passed. tests can use every function in the file.

### `test`

a block that checks your code. it is skipped when the program runs and used by run tests (f7).

```text
test <name...>
```

```gublan
function add a b
    return a + b
end

test adding works
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
end
```

### `assert`

stop with an error when the condition is false. use it inside test blocks.

```text
assert <condition>
```

```gublan
lives = 3
assert lives > 0
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

### `insert`

put a value into a list at a position. the items after it move along by one.

```text
insert <list> <position> <value...>
```

```gublan
list fruit apple pear
insert fruit 0 lemon
```

### `remove`

take the first matching value out of a list. nothing happens if it isn't there.

```text
remove <list> <value...>
```

```gublan
list fruit apple pear
remove fruit pear
```

### `shuffle`

mix a list into a random order.

```text
shuffle <list>
```

```gublan
list fruit apple pear
shuffle fruit
```

### `sort`

put a list in order, smallest first. add reverse for biggest first.

```text
sort <list> [reverse]
```

```gublan
list scores 30 10 20
sort scores reverse
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

### `scroll`

look at a bigger world: everything is drawn moved so that x, y is the top-left corner of the window. ui and fixed objects stay where they are. scrollx() and scrolly() read it back.

```text
scroll <x> <y>
```

```gublan
mode 2d
scroll 300 0
```

### `shake`

shake the screen for a moment, for hits and explosions.

```text
shake <strength> [seconds]
```

```gublan
mode 2d
shake 8 0.3
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

### `vec2`

make an x/y value for positions and movement.

```text
vec2 <name> <x> <y>
```

```gublan
vec2 speed 3 0
```

### `ellipse`

make an oval that fills a box.

```text
ellipse <name> <x> <y> <width> <height>
```

```gublan
mode 2d
ellipse egg 100 80 40 60
```

### `polygon`

make a shape with straight sides from three or more points.

```text
polygon <name> <x1> <y1> <x2> <y2> <x3> <y3> [more points...]
```

```gublan
mode 2d
polygon roof 100 100 150 50 200 100
```

### `particles`

throw out a burst of little squares in the current color. they fly apart and fade away.

```text
particles <x> <y> [count] [speed]
```

```gublan
mode 2d
color gold
particles 200 150 30
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

## buttons, textboxes, sliders and checkboxes

these work in `mode 2d` and in `mode 3d`, where they are drawn flat on top of the 3d scene. click a textbox to type in it; the game's own keys pause while someone is typing. `name.text`, `name.value`, `name.checked`, `name.focused` and `name.submitted` read them, and `name.text = "hi"` changes them.

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

### `textbox`

make a box the player can click and type into. name.text is what they typed, and name.submitted is true once after they press enter.

```text
textbox <name> <x> <y> <width> [hint...]
```

```gublan
mode 2d
textbox username 20 60 240 your name
forever
    if username.submitted
        print hello {username.text}
    end
    frame
end
```

### `slider`

make a slider the player can drag. name.value is where it is.

```text
slider <name> <x> <y> <width> <min> <max> [start]
```

```gublan
mode 2d
slider loudness 20 120 200 0 100 50
text shown 20 160 volume
forever
    shown.text = "volume " + str(loudness.value)
    frame
end
```

### `checkbox`

make a box the player can tick. name.checked is true while it is ticked.

```text
checkbox <name> <x> <y> <label...>
```

```gublan
mode 2d
checkbox music 20 160 play music
forever
    if music.checked
        title music on
    end
    frame
end
```

### `focus`

put the typing cursor in a textbox, or take it out with focus none.

```text
focus <textbox>
focus none
```

```gublan
mode 2d
textbox answer 20 60 240 type here
focus answer
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

### `tween`

smoothly change x, y, w, h, r, angle or opacity while the program keeps going. easings: linear, in, out, inout, smooth, bounce, elastic, back.

```text
tween <object> <field> <value> <seconds> [easing]
```

```gublan
mode 2d
circle coin 200 120 10
tween coin y 40 0.6 bounce
```

### `opacity`

make an object see-through. 0 is invisible and 1 is solid.

```text
opacity <object|all> <0-to-1>
```

```gublan
mode 2d
box ghost 40 40 32 32
opacity ghost 0.5
```

### `layer`

choose what is drawn on top. higher layers are drawn over lower ones, and everything starts on layer 0.

```text
layer <object> <number>
```

```gublan
mode 2d
box player 40 40 32 32
layer player 2
```

### `fixed`

keep an object in the same place on the screen when the view scrolls, like a score.

```text
fixed <object>
```

```gublan
mode 2d
text hud 10 10 score 0
fixed hud
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

### `cursor`

show or hide the mouse pointer over the game window.

```text
cursor show|hide
```

```gublan
mode 2d
cursor hide
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

### `beep`

play a made-up tone, no sound file needed. waves: square, sine, triangle, saw and noise.

```text
beep <frequency> [seconds] [wave]
```

```gublan
beep 440 0.2
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

## saving values between runs

saved values are kept in a small file for each program (on windows in `%APPDATA%\Gublan\saves`), so a high score or the level someone reached is still there next time. inside expressions, `load("name", default)` gives a saved value and `saved("name")` checks for one.

### `save`

keep a value on this computer, so it is still there the next time the program runs.

```text
save <name> <value...>
```

```gublan
score = 120
save best score
```

### `load`

read a saved value into a variable. if nothing was saved under that name it gets the default, or 0.

```text
load <name> <variable> [default...]
```

```gublan
load best highscore 0
print the best score so far is {highscore}
```

### `forget`

delete one saved value, or every saved value.

```text
forget <name>
forget all
```

```gublan
forget best
```

## your discord status

while the discord app is open, `presence` lines change the status on your discord profile. in gublan
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
`presence app`: then it shows your game's name and the pictures you upload there.

### `presence`

show what your program is doing on your discord profile while the discord app is open.

```text
presence details|state|image|smallimage|button|party|timer|countdown|app|clear [values...]
```

```gublan
presence details exploring the caves
presence state level 1 of 5
presence timer
presence button https://github.com/gublans/gublan get gublan
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
