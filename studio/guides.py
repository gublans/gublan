"""short guides shown in the help panel. code lines start with four spaces."""

GUIDES = [
    ("first steps", """gublan programs are lists of commands, one per line. the first word says what to do.

    print hello
    input name what is your name?
    print hi {name}

press f5 (or the run button) to run. text programs talk to you in the output panel at the bottom.
anything in {braces} is worked out first, so {name} becomes the answer you typed.
lines that start with // are notes for people. the computer skips them."""),

    ("variables and maths", """a variable is a name that holds a value. set it with =.

    score = 0
    score += 10
    speed = speed * 1.5
    name = "sam"

+= adds, -= takes away, *= multiplies and /= divides. numbers you type as answers to input are numbers,
so you can do maths with them straight away. inside {braces} and after = you can use maths and
functions like round(), random(1, 6), min(), max(), sqrt() and len()."""),

    ("choices", """if runs lines only when a condition is true. every if needs an end.

    if score > 10
        print you win
    else if score > 5
        print close!
    else
        print try again
    end

compare with ==, !=, <, >, <= and >=. join conditions with and, or and not.
elif and elseif work too."""),

    ("loops", """loops repeat lines. every loop needs an end.

    loop 3
        print hip hip hooray
    end

    for i = 1 to 10
        print {i}
    end

    for fruit in ["apple", "pear"]
        print {fruit}
    end

    while lives > 0
        frame
    end

forever repeats until the program stops. break leaves a loop early and continue skips to the next turn."""),

    ("functions", """a function is a named group of lines you can use again. it can take values and give one back.

    function double n
        return n * 2
    end

    print {double(21)}
    call double 5
    print {result}

call puts the answer in result. ctrl+click a function name to jump to it.

a function's name is a value too, so it can be kept in a variable or given to another function.
x => x * 2 makes a small function right where you need it:

    nums = [3, 1, 2]
    print {map(nums, x => x * 10)}
    print {filter(nums, x => x > 1)}
    print {reduce(nums, (a, b) => a + b, 0)}
    chosen = double
    print {chosen(4)}"""),

    ("more ways to choose and repeat", """match picks one case by value. until repeats while something is false.
try runs lines and catch handles a mistake instead of stopping the program.

    day = "sat"
    match day
    case "sat", "sun"
        print weekend!
    else
        print school
    end

    try
        total = 10 / 0
    catch problem
        print {problem}
    end

const makes a variable that can't be changed by mistake. throw makes your own error."""),

    ("lists and maps", """lists hold values in order. maps hold values by name.

    items = ["sword", "shield"]
    append items potion
    print {items[0]} and {len(items)} things

    player = {"x": 10, "y": 20}
    player.x += 5
    print {player.x}

useful functions: len(), sum(), sort(), reverse(), keys(), values(), indexof(), contains(),
map(), filter(), reduce(), find(), sortby(), zip(), slice(), flat(), any() and every()."""),

    ("making a game", """games open a window with mode 2d, make shapes, then loop forever.
each turn of the loop moves things and calls frame to draw.

    window 640 480 my game
    mode 2d
    color moss
    box player 300 400 40 20
    forever
        if keydown("left")
            move player {-300 * dt} 0
        end
        if keydown("right")
            move player {300 * dt} 0
        end
        frame
    end

dt is the time since the last frame in seconds. multiplying speeds by dt keeps the game smooth on
any computer. file > new from template has finished games to learn from."""),

    ("keyboard and mouse", """keydown("left") is true while a key is held. keypressed("space") is true once per press.
mousex(), mousey(), mousedown() and mousepressed() read the mouse.

    mode 2d
    box target 100 100 20 20
    forever
        if keypressed("space")
            print jump!
        end
        if mousepressed()
            place target {mousex()} {mousey()}
        end
        frame
    end

touching("player", "coin") is true when two shapes overlap."""),

    ("buttons, textboxes and sliders", """button, textbox, slider and checkbox make things the player can click and type into.
they work the same in 2d and 3d: in 3d they are drawn flat on top of the scene.

    mode 2d
    textbox username 20 60 240 your name
    slider loudness 20 120 200 0 100 50
    checkbox music 20 160 play music
    button go 20 200 120 40 start
    forever
        if username.submitted
            print hello {username.text}
        end
        if go
            print volume {loudness.value} music {music.checked}
        end
        frame
    end

name.text is what was typed and name.submitted is true once after enter. focus username puts the
cursor in a textbox. a button's variable is 1 while it is pressed."""),

    ("shapes and pictures", """make shapes with box, circle, line, text, image and sprite. each one gets a name.
change them later with move, place, resize, hide, show, paint, animate and delete.

    mode 2d
    color gold
    circle coin 200 120 10
    image hero assets/hero.png 40 40
    paint coin red
    animate coin 400 120 0.5

pictures and sounds live in an assets folder next to your program. the assets panel can import
files, paint new sprites and insert the code for you."""),

    ("3d", """mode 3d opens a 3d window. make cubes and spheres at x, y, z and move the camera.

    mode 3d
    color moss
    cube crate 0 0 -6 1
    angle = 0
    forever
        angle += 90 * dt
        spin crate {angle}
        frame
    end

negative z is in front of the camera. camera x y z moves it. keyboard and mouse checks, text,
buttons, textboxes, sliders and checkboxes all work in 3d too, drawn flat over the scene."""),

    ("sound", """sound plays a sound effect. music loops a song until stopmusic.

    sound assets/jump.wav
    music assets/theme.ogg
    volume 0.5

wav, ogg and mp3 files work."""),

    ("saving", """save keeps a value on this computer, so it is still there the next time the program runs.
load reads it back, with a value to use when nothing was saved yet.

    load best best 0
    // the game goes here
    if score > best
        save best score
    end

forget best deletes one saved value and forget all deletes every one. inside expressions,
load("best", 0) and saved("best") work too. each program keeps its own saved values."""),

    ("your discord status", """while the discord app is open, gublan studio shows what you are making on your discord
profile. tools > settings, under discord, changes the words, the picture and the button, or turns it off.

your programs can show their own status with presence while they run:

    presence details exploring the caves
    presence state level {level} of 5
    presence timer
    presence button https://example.com play it too

exported games do the same for everyone who plays them. presence clear removes it."""),

    ("finding mistakes", """problems are underlined while you type and listed in the problems panel.
hover a line to read what is wrong.

to watch a program work, click the left edge of a line to add a breakpoint, then run.
the program pauses there and the variables panel shows every value.
step (f10) runs one line at a time and continue (f5) carries on."""),

    ("testing your code", """a test block checks that your code does what you expect. assert stops the test when
something is false. f5 skips tests: run > run tests (f7) runs every test block instead.

    function add a b
        return a + b
    end

    test adding works
        assert add(2, 3) == 5
    end

each test starts fresh, so set up what it needs inside it. failed tests show in the problems panel.
on the command line: py gublancli.py test game.gubl"""),

    ("modules", """use loads functions from a module: a .gubl file in a modules folder.

    use easing
    print {easeout(0.5)}

gublan comes with colors, easing and grid. use looks in your program's modules folder, then your
program's folder, then your own modules folder (next to gublan studio's settings), then the built-in ones.
any .gubl file of functions can be a module."""),

    ("sharing your game", """file > export program makes a .exe that runs on other windows computers without gublan.
the export window lists every picture and sound it found. files from outside your project folder
are copied in automatically, and the whole assets folder can be included too.

text programs get a console window. games get just their game window.

file > export as another language (ctrl+shift+l) turns your program into python, javascript (a web page)
or lua (love2d), with a small runtime file next to it so it works on its own."""),

    ("bringing code from other languages", """tools > convert code turns python, javascript or lua into gublan.
it understands variables, maths, if, loops, functions, lists, maps and classes, and it turns
pygame, p5.js, love2d and canvas drawing into gublan shapes.

it also turns game code into gublan: key listeners become keydown checks, game loops become
forever loops with frame, and clock.tick becomes fps. the rare line it can't convert becomes
a // todo line so you can finish it by hand."""),

    ("code together", """tools > code together starts a live session. other people on your network join it from their
own gublan studio and everyone types in the same files at once.

to host: start a live session, type your name, then tools > code together > how to join copies the
address and the code to send to your friends.
to join: join a live session, type your name (you need one to join), the address and the code.

everyone's cursor shows in their own colour with their name. who is here lists everyone and send a
message chats with them. when the session ends, everyone's tabs stay open, so nothing is lost.
people outside your network need the port (47800 unless you changed it) let through the router.

pictures, sounds and music come from the host's computer. when a guest runs a shared program, every
image, sound, music and include file it needs is fetched from the folder the host's program is saved
in, and kept until the session ends. only files inside that folder are shared, and the host can turn
it off when starting the session. the host has to save the program first, so it has a folder."""),

    ("ai helpers", """tools > connect an ai helper (mcp) shows how to connect claude, copilot, cursor and other ai
helpers to your project. they can read and write files, check code, run programs and tests, take
screenshots of the game window and look up commands.

for claude desktop and cursor, choose the app and press "add it to ...": gublan studio puts itself in
that app's settings file (it keeps a .bak copy of the old one). then quit the app completely and
open it again. for claude code and vs code, "save in the project" writes the project's settings file.
"test it" starts the server the same way the ai app does and tells you if it works.

the server only works inside the project folder. you can start it yourself with:
py gublancli.py mcp my project folder

when the helper changes a file you have open, gublan studio loads the new version by itself. if you
changed it too, it asks which one to keep."""),

    ("themes and plugins", """tools > settings, under look, picks a theme: moss, midnight, ember, paper or contrast.
the new colours show straight away, no restart needed. themes are json files, so you can make your
own in the themes folder. the same section turns the animations off.

plugins are python files that add commands, functions and menu items. switch them on in settings,
then put them in the plugins folder. hello.py shows how one works. only use plugins you trust,
because they can do anything a program on your computer can."""),

    ("when something goes wrong", """gublan studio copies your unsaved programs every few seconds. if it ever closes without
asking, the next time it opens it offers to bring them back.

help > report a problem shows the last errors and crashes it wrote down, ready to copy into a bug
report. the files are errors.log and crash.log in the settings folder.

files: pictures, sounds and other files that are not text open in their folder instead of the
editor. very big files ask first, and files saved as utf-16 (notepad's "unicode") or windows-1252
open correctly and are saved as utf-8. when another program changes a file you have open, it is
loaded again (file > reload from disk does it by hand)."""),

    ("moving things smoothly", """tween changes an object bit by bit while the program keeps going. easings change how it moves:
linear, in, out, inout, smooth, bounce, elastic and back.

    mode 2d
    circle coin 270 300 16
    tween coin y 80 0.8 bounce
    ellipse egg 100 80 40 60
    polygon roof 400 200 450 150 500 200
    layer coin 2
    opacity roof 0.5
    forever
        if keypressed("space")
            particles {coin.x} {coin.y} 20
            shake 6 0.2
            beep 660 0.08
        end
        frame
    end

scroll x y moves the view over a bigger world. fixed keeps a score or a health bar still while it
scrolls. cooldown("shoot", 0.3) is true at most once every 0.3 seconds, pulse("spawn", 2) is true
once every 2 seconds and after("start", 3) turns true 3 seconds after you first ask."""),

    ("handy functions", """lists: take(xs, 2), drop(xs, 2), first(xs), last(xs), chunk(xs, 3), fill(0, 5), without(xs, 0),
enumerate(xs), minby(xs, n => n.y), maxby(...) and groupby(words, w => len(w)).
maps: entries(m), frompairs(pairs), merge(a, b) and get(m, "name", fallback).
numbers: median, product, gcd, hypot, fract, snap(37, 16), between(x, 1, 10), smoothstep and
ease(t, "out").
text: commas(1234567) is 1,234,567, ordinal(2) is 2nd, plural(3, "coin") is 3 coins and
wraptext(text, 20) splits text into lines.
colours: mixcolor("red", "blue", 0.5) and randomcolor().

local makes a variable that only lives inside its function:

    function shout word
        local loud = upper(word)
        return loud
    end"""),

    ("game window and popups", """tools > game window and popups sets how game windows start (size, title, background, fps and an
fps counter) and how popups and questions look: their colours, border, width, text size, how much
they dim the game, where they sit, how they open (pop, fade, slide or none) and their soft sound.
pick a look like paper, night, arcade or glass, or start from the studio's own theme.

a program's own window, background and fps lines still win. exported programs and the web keep
the look you chose."""),

    ("cursor, typing and sounds", """tools > settings, under cursor and typing, changes the editor's text cursor: its shape (line,
block or underline), how it blinks, whether it glides or jumps and how thick it is. new letters
can fade in, settle like wet ink, glow or just appear.

under sounds, gublan studio plays soft sounds when things open, run, finish, save or go wrong.
pick a set (soft, glass, wood or retro), a volume, and a tiny tick while you type if you like it.
the listen buttons play each one."""),

    ("keyboard shortcuts", """f5 run or continue      shift+f5 stop        f10 step         f9 breakpoint
ctrl+s save            ctrl+o open          ctrl+n new       ctrl+w close tab
ctrl+f find            ctrl+h replace       ctrl+g go to line
ctrl+space ideas       ctrl+/ comment       ctrl+d duplicate line
alt+up/down move line  ctrl+shift+k delete line   ctrl+enter new line below
ctrl+shift+p every action          ctrl+b blocks          ctrl+= / ctrl+- zoom
ctrl+shift+c convert code          ctrl+shift+l export as another language
f12 or ctrl+click go to a function"""),
]
