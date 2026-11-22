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

call puts the answer in result. ctrl+click a function name to jump to it."""),

    ("lists and maps", """lists hold values in order. maps hold values by name.

    items = ["sword", "shield"]
    append items potion
    print {items[0]} and {len(items)} things

    player = {"x": 10, "y": 20}
    player.x += 5
    print {player.x}

useful functions: len(), sum(), sort(), reverse(), keys(), values(), indexof(), contains()."""),

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

negative z is in front of the camera. camera x y z moves it."""),

    ("sound", """sound plays a sound effect. music loops a song until stopmusic.

    sound assets/jump.wav
    music assets/theme.ogg
    volume 0.5

wav, ogg and mp3 files work."""),

    ("finding mistakes", """problems are underlined while you type and listed in the problems panel.
hover a line to read what is wrong.

to watch a program work, click the left edge of a line to add a breakpoint, then run.
the program pauses there and the variables panel shows every value.
step (f10) runs one line at a time and continue (f5) carries on."""),

    ("sharing your game", """file > export program makes a .exe that runs on other windows computers without gublan.
the export window lists every picture and sound it found. files from outside your project folder
are copied in automatically, and the whole assets folder can be included too.

text programs get a console window. games get just their game window."""),

    ("bringing code from other languages", """tools > convert code turns python, javascript or lua into gublan.
it understands variables, maths, if, loops, functions, lists, maps and classes, and it turns
pygame, p5.js, love2d and canvas drawing into gublan shapes.

anything it can't convert becomes a // todo line so you can finish it by hand."""),

    ("keyboard shortcuts", """f5 run or continue      shift+f5 stop        f10 step         f9 breakpoint
ctrl+s save            ctrl+o open          ctrl+n new       ctrl+w close tab
ctrl+f find            ctrl+h replace       ctrl+g go to line
ctrl+space ideas       ctrl+/ comment       ctrl+d duplicate line
alt+up/down move line  ctrl+shift+k delete line   ctrl+enter new line below
ctrl+shift+p every action          ctrl+b blocks          ctrl+= / ctrl+- zoom
f12 or ctrl+click go to a function"""),
]
