"""gublan language core: tokenizer, analyzer and runtime.

the runtime compiles a script once (block jump tables, cached expressions) and
then interprets it statement by statement, so games run at full speed while
the studio can still pause, step and inspect every line.
"""

import array
import ast
import colorsys
import csv
import difflib
import http.client
import io
import ipaddress
import json
import math
import os
import random
import re
import socket
import ssl
import sys
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import pygame
from pygame.locals import DOUBLEBUF, OPENGL
from OpenGL.GL import (
    glBegin, glBindTexture, glReadBuffer, glReadPixels, glBlendFunc, glClear, glClearColor, glColor3f, glColor4f,
    glColorMaterial, glDeleteTextures, glDisable, glEnable, glEnd, glGenTextures,
    glLightfv, glLoadIdentity, glMatrixMode, glNormal3f, glOrtho, glPopAttrib,
    glPopMatrix, glPushAttrib, glPushMatrix, glRotatef, glTexCoord2f, glTexImage2D,
    glTexParameteri, glTranslatef, glVertex2f, glVertex3fv,
    GL_AMBIENT, GL_AMBIENT_AND_DIFFUSE, GL_BLEND, GL_COLOR_BUFFER_BIT, GL_COLOR_MATERIAL,
    GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST, GL_DIFFUSE, GL_ENABLE_BIT, GL_FRONT_AND_BACK,
    GL_LIGHT0, GL_LIGHTING, GL_MODELVIEW, GL_NEAREST, GL_NORMALIZE, GL_ONE_MINUS_SRC_ALPHA,
    GL_FRONT, GL_POLYGON, GL_POSITION, GL_PROJECTION, GL_QUADS, GL_RGB, GL_RGBA, GL_SRC_ALPHA, GL_TEXTURE_2D,
    GL_TEXTURE_BIT, GL_TEXTURE_MAG_FILTER, GL_TEXTURE_MIN_FILTER, GL_UNSIGNED_BYTE,
)
from OpenGL.GLU import gluDeleteQuadric, gluNewQuadric, gluPerspective, gluSphere


@dataclass(frozen=True)
class Vector2:
    x: float
    y: float


@dataclass(frozen=True)
class Vector3:
    x: float
    y: float
    z: float


class QuotedText(str):
    """a token that was written inside quotes; always treated as text."""


# --------------------------------------------------------------------------
# command reference: the single source of truth for the analyzer, the
# studio's help, completion and blocks palette, and the documentation test.
# name: (category, usage, minimum parts including the command, summary, example)
# --------------------------------------------------------------------------
COMMAND_SPECS = {
    # basics
    "print": ("basics", "print <values...>", 2,
              "show words, variables or {expressions} in the output panel.", "print score is {score}"),
    "set": ("basics", "set <name> = <value>", 4,
            "create or change a variable. the value can be a number, text, list, map or expression.",
            "set speed = 2.5"),
    "add": ("basics", "add <variable> <amount>", 3, "add an amount to a variable.", "add score 10"),
    "sub": ("basics", "sub <variable> <amount>", 3, "subtract an amount from a variable.", "sub lives 1"),
    "mul": ("basics", "mul <variable> <amount>", 3, "multiply a variable by an amount.", "mul speed 2"),
    "div": ("basics", "div <variable> <amount>", 3, "divide a variable by an amount.", "div speed 2"),
    "calc": ("basics", "calc <variable> <expression>", 3,
             "work out a math expression and store the answer.", "calc area width * height"),
    "random": ("basics", "random <variable> <min> <max>", 4,
               "pick a random number between min and max.", "random roll 1 6"),
    "seed": ("basics", "seed <number>", 2,
             "make random numbers come out the same every run, which helps when testing a game.", "seed 42"),
    "swap": ("basics", "swap <variable-a> <variable-b>", 3, "swap the values of two variables.", "swap a b"),
    "time": ("basics", "time <variable>", 2, "store the seconds since the program started.", "time now"),
    "const": ("basics", "const <name> = <value>", 4,
              "make a value that can't be changed later, like the speed of the game.", "const speed = 4"),
    # control
    "if": ("control", "if <condition>", 2,
           "run the lines below only when the condition is true. close with end.", "if score > 10"),
    "elseif": ("control", "elseif <condition>", 2,
               "check another condition when the ones above were false.", "elseif score > 5"),
    "else": ("control", "else", 1, "run these lines when nothing above matched.", "else"),
    "then": ("control", "then kill", 2, "stop the program when the surrounding if matched.", "then kill"),
    "end": ("control", "end", 1,
            "close an if, loop, forever, while, until, for, match, try, test or function block.", "end"),
    "loop": ("control", "loop <count>", 2, "repeat the lines below a number of times.", "loop 10"),
    "forever": ("control", "forever", 1, "repeat the lines below until the program stops.", "forever"),
    "while": ("control", "while <condition>", 2,
              "repeat the lines below while the condition stays true.", "while lives > 0"),
    "for": ("control", "for <var> = <start> to <end> [step <n>] | for <var> in <list>", 4,
            "count through numbers or go through every item of a list.", "for i = 1 to 10"),
    "until": ("control", "until <condition>", 2,
              "repeat the lines below until the condition becomes true.", "until lives == 0"),
    "match": ("control", "match <value>", 2,
              "compare one value with several cases and run the case that fits. close with end.", "match day"),
    "case": ("control", "case <value> [, more values...]", 2,
             "inside match: run these lines when the value equals one of these.", 'case "sat", "sun"'),
    "try": ("control", "try", 1,
            "run lines that might fail. if one does, the program jumps to catch instead of stopping.", "try"),
    "catch": ("control", "catch [variable]", 1,
              "inside try: run these lines when something failed. the message goes into the variable "
              "(error if you leave it out).", "catch problem"),
    "throw": ("control", "throw <message...>", 2,
              "stop with your own error message. a try around it can catch it.", "throw not enough coins"),
    "break": ("control", "break", 1, "leave the loop you are in right now.", "break"),
    "continue": ("control", "continue", 1, "skip to the next round of the loop.", "continue"),
    "wait": ("control", "wait <seconds>", 2, "pause for a number of seconds.", "wait 0.5"),
    "kill": ("control", "kill", 1, "stop the program.", "kill"),
    # functions
    "function": ("functions", "function <name> [parameters...]", 2,
                 "make a reusable block of lines. close with end.", "function greet name"),
    "call": ("functions", "call <name> [arguments...]", 2,
             "run a function. its answer goes into result.", "call greet world"),
    "return": ("functions", "return [value]", 1, "finish a function, optionally giving back a value.",
               "return total"),
    "local": ("functions", "local <name> [= <value>]", 2,
              "make a variable that only lives inside the function it is in. when the function ends, the "
              "name goes back to what it was before.", "local total = 0"),
    "include": ("functions", "include <script.gubl>", 2, "load another gublan script into this one.",
                "include helpers.gubl"),
    "use": ("functions", "use <module>", 2,
            "load a module: a gublan file from a modules folder (yours, your project's or a built-in one).",
            "use easing"),
    # testing
    "test": ("testing", "test <name...>", 2,
             "a block that checks your code. it is skipped when the program runs and used by run tests (f7).",
             "test adding works"),
    "assert": ("testing", "assert <condition>", 2,
               "stop with an error when the condition is false. use it inside test blocks.",
               "assert 2 + 3 == 5"),
    # lists and maps
    "list": ("lists and maps", "list <name> [values...]", 2, "make a list, optionally with starting values.",
             "list fruit apple pear"),
    "append": ("lists and maps", "append <list> <value...>", 3, "add a value to the end of a list.",
               "append fruit plum"),
    "item": ("lists and maps", "item <list> <index> <variable>", 4,
             "copy one list item into a variable. the first item is 0.", "item fruit 0 first"),
    "length": ("lists and maps", "length <value> <variable>", 3,
               "store how many items or letters something has.", "length fruit count"),
    "map": ("lists and maps", "map <name>", 2, "make a map that stores values under names.", "map inventory"),
    "put": ("lists and maps", "put <map> <key> <value...>", 4, "store a value in a map.",
            "put inventory coins 3"),
    "lookup": ("lists and maps", "lookup <map> <key> <variable>", 4, "copy a map value into a variable.",
               "lookup inventory coins amount"),
    "has": ("lists and maps", "has <map> <key> <variable>", 4,
            "set a variable to true if the map has that key.", "has inventory coins found"),
    "delete": ("lists and maps", "delete <object> | delete <list> <index> | delete <map> <key>", 2,
               "remove an object from the scene, an item from a list or a key from a map.", "delete enemy"),
    "insert": ("lists and maps", "insert <list> <position> <value...>", 4,
               "put a value into a list at a position. the items after it move along by one.",
               "insert fruit 0 lemon"),
    "remove": ("lists and maps", "remove <list> <value...>", 3,
               "take the first matching value out of a list. nothing happens if it isn't there.",
               "remove fruit pear"),
    "shuffle": ("lists and maps", "shuffle <list>", 2, "mix a list into a random order.", "shuffle fruit"),
    "sort": ("lists and maps", "sort <list> [reverse]", 2,
             "put a list in order, smallest first. add reverse for biggest first.", "sort scores reverse"),
    "pop": ("lists and maps", "pop <list> <variable> [position]", 3,
            "take an item out of a list and keep it in a variable. without a position it takes the last one.",
            "pop cards card"),
    # display
    "mode": ("display", "mode 2d|3d", 2, "open the 2d or 3d game window.", "mode 2d"),
    "window": ("display", "window <width> <height> [title...]", 3,
               "set the game window size and title.", "window 800 600 my game"),
    "title": ("display", "title <text...>", 2, "change the game window title.", "title space dodge"),
    "background": ("display", "background <color>", 2, "set the background color.", "background navy"),
    "color": ("display", "color <name> | color #rrggbb | color <r> <g> <b>", 2,
              "choose the color for shapes you make next.", "color green"),
    "paint": ("display", "paint <object|all> <color>", 3, "recolor an existing object.", "paint player red"),
    "clear": ("display", "clear", 1, "redraw the window now.", "clear"),
    "screenshot": ("display", "screenshot <path>", 2,
                   "save a picture of the game window as a .png file next to your program.",
                   "screenshot shots/level1.png"),
    "frame": ("display", "frame", 1,
              "draw the window and wait for the next frame. dt holds the seconds since the last frame.",
              "frame"),
    "fps": ("display", "fps <frames-per-second>", 2, "set how many frames per second frame aims for.",
            "fps 60"),
    "textsize": ("display", "textsize <pixels>", 2, "set the size of text you make next.", "textsize 32"),
    "scroll": ("display", "scroll <x> <y>", 3,
               "look at a bigger world: everything is drawn moved so that x, y is the top-left corner of the "
               "window. ui and fixed objects stay where they are. scrollx() and scrolly() read it back.",
               "scroll 300 0"),
    "shake": ("display", "shake <strength> [seconds]", 2,
              "shake the screen for a moment, for hits and explosions.", "shake 8 0.3"),
    # 2d
    "box": ("2d", "box <name> <x> <y> <width> <height>", 6, "make a rectangle.", "box player 40 40 32 32"),
    "circle": ("2d", "circle <name> <x> <y> <radius>", 5, "make a circle.", "circle coin 200 120 10"),
    "line": ("2d", "line <name> <x1> <y1> <x2> <y2> [thickness]", 6, "make a line.",
             "line floor 0 400 540 400 3"),
    "text": ("2d", "text <name> <x> <y> <content...>", 5, "show text in the window.",
             "text hud 10 10 score {score}"),
    "image": ("2d", "image <name> <path> <x> <y>", 5, "show an image file.", "image logo assets/logo.png 20 20"),
    "sprite": ("2d", "sprite <name> <path> <x> <y> <width> <height>", 7,
               "show a resized image you can move and collide.", "sprite hero assets/hero.png 40 40 48 48"),
    "vec2": ("2d", "vec2 <name> <x> <y>", 4, "make an x/y value for positions and movement.", "vec2 speed 3 0"),
    "ellipse": ("2d", "ellipse <name> <x> <y> <width> <height>", 6, "make an oval that fills a box.",
                "ellipse egg 100 80 40 60"),
    "polygon": ("2d", "polygon <name> <x1> <y1> <x2> <y2> <x3> <y3> [more points...]", 8,
                "make a shape with straight sides from three or more points.",
                "polygon roof 100 100 150 50 200 100"),
    "particles": ("2d", "particles <x> <y> [count] [speed]", 3,
                  "throw out a burst of little squares in the current color. they fly apart and fade away.",
                  "particles 200 150 30"),
    # 3d
    "cube": ("3d", "cube <name> <x> <y> <z> <size> [color]", 6, "make a 3d cube.", "cube crate 0 0 -6 1"),
    "sphere": ("3d", "sphere <name> <x> <y> <z> <radius> [color]", 6, "make a 3d sphere.",
               "sphere moon 2 0 -7 0.5"),
    "block": ("3d", "block <name> <x> <y> <z> <width> <height> <depth> [color]", 8,
              "make a 3d box of any size, like a wall, a floor or a brick. x, y and z are its middle.",
              "block wall 0 0 -8 4 2 0.5 sand"),
    "cylinder": ("3d", "cylinder <name> <x> <y> <z> <radius> <height> [color]", 7,
                 "make a 3d cylinder standing up, like a pillar, a tree trunk or a coin.",
                 "cylinder pillar -2 0 -8 0.4 3 gray"),
    "cone": ("3d", "cone <name> <x> <y> <z> <radius> <height> [color]", 7,
             "make a 3d cone pointing up, like a tree top or a party hat.", "cone treetop 2 1 -8 1 2 forest"),
    "plane": ("3d", "plane <name> <x> <y> <z> <width> <depth> [color]", 7,
              "make a flat 3d floor (or ceiling) that lies level.", "plane ground 0 -1 -8 20 20 moss"),
    "spin": ("3d", "spin <object> <angle>", 3, "rotate a 3d shape, sprite or image (degrees).",
             "spin crate 45"),
    "turn": ("3d", "turn <object> <x-angle> <y-angle> [z-angle]", 4,
             "tilt and turn a 3d shape (degrees). y turns it left and right, x tips it forwards and z rolls it.",
             "turn crate 0 45 0"),
    "camera": ("3d", "camera <x> <y> <z> [yaw] [pitch] | camera <vec3>", 2,
               "move and turn the 3d camera.", "camera 0 1 0"),
    "lookat": ("3d", "lookat <x> <y> <z> | lookat <object>", 2, "turn the 3d camera to face a spot or a shape.",
               "lookat 0 0 -8"),
    "walk": ("3d", "walk <forward> [right] [up]", 2,
             "move the 3d camera the way it is facing (for first person games). use minus numbers to go back.",
             "walk 0.1"),
    "light": ("3d", "light <x> <y> <z> [brightness]", 4,
              "change which way the 3d light shines from, and how bright it is (1 is normal).",
              "light 1 2 1 1.2"),
    "vec3": ("3d", "vec3 <name> <x> <y> <z>", 5, "make an x/y/z value for 3d positions.", "vec3 spot 0 0 -6"),
    # ui: works in 2d, and drawn on top of the scene in 3d
    "button": ("ui", "button <variable> <x> <y> <width> <height> <label...>", 7,
               "make a clickable button. its variable is 1 while pressed.", "button start 20 20 120 40 start"),
    "ui": ("ui", "ui button <label>", 3, "make the quick button in the top-left corner.", "ui button destroy"),
    "textbox": ("ui", "textbox <name> <x> <y> <width> [hint...]", 5,
                "make a box the player can click and type into. name.text is what they typed, and "
                "name.submitted is true once after they press enter.", "textbox username 20 60 240 your name"),
    "slider": ("ui", "slider <name> <x> <y> <width> <min> <max> [start]", 7,
               "make a slider the player can drag. name.value is where it is.", "slider loudness 20 120 200 0 100 50"),
    "checkbox": ("ui", "checkbox <name> <x> <y> <label...>", 5,
                 "make a box the player can tick. name.checked is true while it is ticked.",
                 "checkbox music 20 160 play music"),
    "focus": ("ui", "focus <textbox> | focus none", 2,
              "put the typing cursor in a textbox, or take it out with focus none.", "focus username"),
    # objects
    "move":("objects", "move <object> <dx> <dy> [dz] | move <object> <vector>", 3,
             "move an object by an amount.", "move player 3 0"),
    "place": ("objects", "place <object> <x> <y> [z]", 4, "put an object at an exact position.",
              "place player 40 300"),
    "resize": ("objects", "resize <object> <width> [height]", 3, "change an object's size.",
               "resize player 64 64"),
    "hide": ("objects", "hide <object>", 2, "make an object invisible.", "hide enemy"),
    "show": ("objects", "show <object>", 2, "make a hidden object visible again.", "show enemy"),
    "animate": ("objects", "animate <object> <x> <y> [z] <seconds>", 5,
                "glide an object to a position over time.", "animate player 200 80 0.5"),
    "touching": ("objects", "touching <variable> <object-a> <object-b>", 4,
                 "set a variable to 1 when two objects overlap.", "touching hit player coin"),
    "tween": ("objects", "tween <object> <field> <value> <seconds> [easing]", 5,
              "smoothly change x, y, w, h, r, angle or opacity while the program keeps going. easings: linear, "
              "in, out, inout, smooth, bounce, elastic, back.", "tween coin y 40 0.6 bounce"),
    "opacity": ("objects", "opacity <object|all> <0-to-1>", 3,
                "make an object see-through. 0 is invisible and 1 is solid.", "opacity ghost 0.5"),
    "layer": ("objects", "layer <object> <number>", 3,
              "choose what is drawn on top. higher layers are drawn over lower ones, and everything starts "
              "on layer 0.", "layer player 2"),
    "fixed": ("objects", "fixed <object>", 2,
              "keep an object in the same place on the screen when the view scrolls, like a score.",
              "fixed hud"),
    "velocity": ("objects", "velocity <object> <x-speed> <y-speed> [z-speed]", 4,
                 "keep an object moving by itself, in pixels (or 3d units) a second. 0 0 stops it.",
                 "velocity ball 120 -200"),
    "gravity": ("objects", "gravity <amount>", 2,
                "pull every object that has a velocity downwards. 600 feels like a platformer, 0 turns it off.",
                "gravity 600"),
    # input
    "key": ("input", "key <variable> <key-name>", 3, "set a variable to 1 while a key is held.",
            "key left left"),
    "keypressed": ("input", "keypressed <variable> <key-name>", 3,
                   "set a variable to 1 once each time a key is pressed down.", "keypressed jump space"),
    "mouse": ("input", "mouse <x-variable> <y-variable>", 3, "store the mouse position.", "mouse mx my"),
    "mousebutton": ("input", "mousebutton <variable> left|middle|right", 3,
                    "set a variable to true while a mouse button is held.", "mousebutton firing left"),
    "input": ("input", "input <variable> <question...>", 3, "ask the player to type something.",
              "input name what is your name"),
    "popup": ("input", "popup <message...>", 2, "show a message and wait for a key or click.", "popup you win"),
    "cursor": ("input", "cursor show|hide", 2, "show or hide the mouse pointer over the game window.",
               "cursor hide"),
    # sound
    "sound": ("sound", "sound <path>", 2, "play a sound effect once.", "sound assets/jump.wav"),
    "music": ("sound", "music <path>", 2, "play looping background music.", "music assets/theme.ogg"),
    "stopmusic": ("sound", "stopmusic", 1, "stop the music.", "stopmusic"),
    "stopsounds": ("sound", "stopsounds", 1, "stop all sound effects.", "stopsounds"),
    "volume": ("sound", "volume <0-to-1>", 2, "set the volume from 0 (silent) to 1 (full).", "volume 0.5"),
    "beep": ("sound", "beep <frequency> [seconds] [wave]", 2,
             "play a made-up tone, no sound file needed. waves: square, sine, triangle, saw and noise.",
             "beep 440 0.2"),
    # web
    "get": ("web", "get <https-url> <variable>", 3, "read text from a public https website.",
            "get https://example.com page"),
    # saving
    "save": ("saving", "save <name> <value...>", 3,
             "keep a value on this computer, so it is still there the next time the program runs.",
             "save best score"),
    "load": ("saving", "load <name> <variable> [default...]", 3,
             "read a saved value into a variable. if nothing was saved under that name it gets the default, "
             "or 0.", "load best highscore 0"),
    "forget": ("saving", "forget <name> | forget all", 2, "delete one saved value, or every saved value.",
               "forget best"),
    # files
    "writefile": ("files", "writefile <path> <text...>", 3,
                  "make a text file, or replace what is in it. files are kept next to your program.",
                  "writefile notes.txt hello there"),
    "appendfile": ("files", "appendfile <path> <text...>", 3, "add a line to the end of a text file.",
                   "appendfile log.txt the game started"),
    "readfile": ("files", "readfile <path> <variable>", 3,
                 "read a whole text file into a variable. use lines() on it to go through it line by line.",
                 "readfile notes.txt text"),
    "deletefile": ("files", "deletefile <path>", 2, "delete a file, or a folder that is empty.",
                   "deletefile old.txt"),
    "makefolder": ("files", "makefolder <path>", 2, "make a folder (and the folders it is inside).",
                   "makefolder levels"),
    "copyfile": ("files", "copyfile <from> <to>", 3, "copy a file.", "copyfile notes.txt backup.txt"),
    "renamefile": ("files", "renamefile <from> <to>", 3, "rename a file, or move it into a folder.",
                   "renamefile draft.txt final.txt"),
    # discord
    "presence": ("discord", "presence details|state|image|smallimage|button|party|timer|countdown|app|clear "
                            "[values...]", 2,
                 "show what your program is doing on your discord profile while the discord app is open.",
                 "presence details exploring the caves"),
}

CATEGORY_ORDER = (
    "basics", "control", "functions", "testing", "lists and maps", "display", "2d", "3d", "ui",
    "objects", "input", "sound", "web", "saving", "files", "discord", "plugins",
)

GUBLANCOMMANDS = set(COMMAND_SPECS)
COMMAND_USAGE = {name: spec[1] for name, spec in COMMAND_SPECS.items()}
COMMAND_MIN_ARGS = {name: spec[2] for name, spec in COMMAND_SPECS.items() if spec[2] > 1}
COMMAND_CATEGORY = {name: spec[0] for name, spec in COMMAND_SPECS.items()}
COMMAND_SUMMARY = {name: spec[3] for name, spec in COMMAND_SPECS.items()}
COMMAND_EXAMPLE = {name: spec[4] for name, spec in COMMAND_SPECS.items()}

NO_ARGUMENT_COMMANDS = {
    "clear", "kill", "forever", "end", "else", "stopmusic", "stopsounds", "frame", "break", "continue", "try",
}
BLOCK_OPENERS = {"if", "loop", "forever", "while", "until", "for", "function", "match", "try", "test"}
# lines that end one branch of a block and start the next. each maps to the blocks it can be inside.
BLOCK_MIDDLES = {"elseif": ("if",), "else": ("if", "match"), "case": ("match",), "catch": ("try",)}
LOOP_COMMANDS = {"loop", "forever", "while", "until", "for"}
# blocks that are skipped when the program runs and called on their own
CALLABLE_BLOCKS = {"function", "test"}
COMPARISON_OPERATORS = {"=", "==", "!=", ">", "<", ">=", "<="}

COLORS = {
    "red": (225, 65, 65),
    "blue": (65, 145, 245),
    "green": (65, 205, 105),
    "yellow": (245, 215, 65),
    "white": (240, 240, 240),
    "moss": (148, 182, 108),
    "orange": (245, 145, 65),
    "purple": (170, 115, 225),
    "cyan": (75, 205, 215),
    "black": (12, 12, 12),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "darkgray": (52, 52, 52),
    "pink": (240, 130, 190),
    "brown": (140, 95, 60),
    "lime": (170, 235, 70),
    "teal": (40, 150, 140),
    "navy": (25, 40, 90),
    "gold": (225, 185, 60),
    "sand": (215, 195, 150),
    "sky": (135, 200, 245),
    "forest": (40, 95, 55),
}

EXPRESSION_FUNCTIONS = {
    "abs": "abs(x) the distance of x from zero",
    "min": "min(a, b, ...) the smallest value",
    "max": "max(a, b, ...) the largest value",
    "round": "round(x, digits) round to the nearest whole number",
    "floor": "floor(x) round down",
    "ceil": "ceil(x) round up",
    "sqrt": "sqrt(x) square root",
    "sin": "sin(degrees) sine of an angle in degrees",
    "cos": "cos(degrees) cosine of an angle in degrees",
    "tan": "tan(degrees) tangent of an angle in degrees",
    "atan2": "atan2(y, x) angle in degrees towards a point",
    "rad": "rad(degrees) convert degrees to radians",
    "deg": "deg(radians) convert radians to degrees",
    "clamp": "clamp(x, low, high) keep x between low and high",
    "lerp": "lerp(a, b, t) blend from a to b",
    "sign": "sign(x) -1, 0 or 1",
    "dist": "dist(x1, y1, x2, y2) or dist(a, b) distance between points",
    "len": "len(x) number of items or letters",
    "str": "str(x) turn a value into text",
    "string": "string(x) turn a value into text",
    "num": "num(x) turn text into a number",
    "number": "number(x) turn text into a number",
    "int": "int(x) whole-number part",
    "upper": "upper(text) uppercase letters",
    "lower": "lower(text) lowercase letters",
    "trim": "trim(text) remove spaces at the ends",
    "contains": "contains(list-or-text, value) true if it is inside",
    "join": "join(list, separator) glue list items into text",
    "split": "split(text, separator) cut text into a list",
    "replace": "replace(text, old, new) swap parts of text",
    "random": "random(a, b) random number between a and b",
    "choice": "choice(list) a random item",
    "keydown": "keydown(\"left\") true while a key is held",
    "keypressed": "keypressed(\"space\") true once per key press",
    "mousedown": "mousedown(\"left\") true while a mouse button is held",
    "mousex": "mousex() mouse x position",
    "mousey": "mousey() mouse y position",
    "touching": "touching(\"a\", \"b\") true when two objects overlap",
    "exists": "exists(\"name\") true if an object or variable exists",
    "time": "time() seconds since the program started",
    "vec2": "vec2(x, y) make a 2d vector",
    "vec3": "vec3(x, y, z) make a 3d vector",
    "mag": "mag(vector) length of a vector",
    "type": "type(x) the kind of value as text",
    "range": "range(start, end) list of numbers from start up to end - 1",
    "mousepressed": "mousepressed(\"left\") true once per mouse click",
    "pow": "pow(x, n) x to the power of n",
    "asin": "asin(x) angle in degrees whose sine is x",
    "acos": "acos(x) angle in degrees whose cosine is x",
    "atan": "atan(x) angle in degrees whose tangent is x",
    "sum": "sum(list) add up every number in a list",
    "sort": "sort(list) a sorted copy of a list",
    "reverse": "reverse(list) a reversed copy of a list",
    "keys": "keys(map) list of the names in a map",
    "values": "values(map) list of the values in a map",
    "indexof": "indexof(list, value) position of a value, or -1",
    "overlap": "overlap(a, b) true when two objects or [x, y, w, h] rectangles overlap",
    "chance": "chance(percent) true about that many times out of 100",
    "shuffle": "shuffle(list) a copy of a list in a random order",
    "unique": "unique(list) a copy of a list without repeats",
    "count": "count(list-or-text, value) how many times a value appears",
    "average": "average(list) the average of a list of numbers",
    "startswith": "startswith(text, start) true if the text begins with start",
    "endswith": "endswith(text, ending) true if the text finishes with ending",
    "pad": "pad(value, width, fill) text filled on the left up to a width: pad(7, 3, 0) is 007",
    "decimals": "decimals(x, digits) a number as text with that many digits after the point",
    "wrap": "wrap(x, low, high) wrap x around so it stays from low up to high",
    "remap": "remap(x, low1, high1, low2, high2) move a number from one range into another",
    "approach": "approach(x, target, step) move x towards target by at most step",
    "angleto": "angleto(x1, y1, x2, y2) or angleto(a, b) the angle in degrees from one point to another",
    "hsv": "hsv(hue, saturation, value) a colour from a hue (0 to 360), saturation and value (0 to 1)",
    "isnumber": "isnumber(x) true for a number, or text that looks like one",
    "date": "date() today's date as text, like 2026-11-22",
    "clock": "clock() the time of day as text, like 14:05",
    "now": "now() seconds since 1970, for timing things between runs",
    "saved": "saved(\"name\") true if a value has been saved under that name",
    "load": "load(\"name\", default) a saved value, or the default when nothing was saved",
    # working with lists and functions as values
    "map": "map(list, f) a new list with f done to every item: map(nums, x => x * 2)",
    "filter": "filter(list, f) the items where f is true: filter(nums, x => x > 0)",
    "reduce": "reduce(list, f, start) combine every item into one value: reduce(nums, (a, b) => a + b, 0)",
    "find": "find(list, f) the first item where f is true, or none",
    "any": "any(list) or any(list, f) true when at least one item is true (or makes f true)",
    "every": "every(list) or every(list, f) true when every item is true (or makes f true)",
    "sortby": "sortby(list, f) a copy sorted by what f gives for each item: sortby(people, p => p.age)",
    "zip": "zip(a, b) pairs up two lists: zip([1, 2], [\"a\", \"b\"]) is [[1, \"a\"], [2, \"b\"]]",
    "slice": "slice(list-or-text, start, end) the part from start up to (not including) end",
    "flat": "flat(list) a list of lists joined into one list",
    "repeat": "repeat(text-or-list, times) the value repeated that many times",
    "call": "call(f, values...) run a function value with some values",
    # text
    "capitalize": "capitalize(text) the text with the first letter of each word in capitals",
    "lines": "lines(text) a list of the lines in some text",
    "words": "words(text) a list of the words in some text",
    "char": "char(code) the letter for a character code: char(65) is A",
    "code": "code(letter) the character code of a letter: code(\"A\") is 65",
    "tojson": "tojson(value) a value written as json text",
    "fromjson": "fromjson(text) json text turned into lists, maps, numbers and text",
    "textwidth": "textwidth(text, size) how many pixels wide some text is when shown",
    # math
    "log": "log(x) or log(x, base) the logarithm of a number",
    "exp": "exp(x) e to the power of x",
    "noise": "noise(x) or noise(x, y) smooth random values from 0 to 1, for hills, clouds and wobbles",
    "randint": "randint(low, high) a random whole number from low to high",
    # added in 1.0.7: more math
    "hypot": "hypot(x, y) the length of the long side of a right triangle, sqrt(x*x + y*y)",
    "fract": "fract(x) the part after the decimal point: fract(2.75) is 0.75",
    "smoothstep": "smoothstep(low, high, x) 0 below low, 1 above high and a smooth curve between",
    "snap": "snap(x, step) x rounded to the nearest step: snap(37, 16) is 32, handy for grids",
    "between": "between(x, low, high) true when x is from low up to high",
    "ease": "ease(t, kind) bend a 0-to-1 amount into a curve. kinds: linear, in, out, inout, smooth, bounce, "
            "elastic, back",
    "gcd": "gcd(a, b) the biggest whole number that divides both",
    "median": "median(list) the middle value once the list is sorted",
    "product": "product(list) every number in a list multiplied together",
    # lists and maps
    "first": "first(list) the first item, or none when the list is empty",
    "last": "last(list) the last item, or none when the list is empty",
    "take": "take(list, n) the first n items",
    "drop": "drop(list, n) everything after the first n items",
    "chunk": "chunk(list, size) the list cut into smaller lists: chunk([1, 2, 3], 2) is [[1, 2], [3]]",
    "enumerate": "enumerate(list) each item with its position: enumerate([\"a\", \"b\"]) is [[0, \"a\"], [1, \"b\"]]",
    "minby": "minby(list, f) the item that gives the smallest f: minby(enemies, e => e.x)",
    "maxby": "maxby(list, f) the item that gives the biggest f",
    "groupby": "groupby(list, f) a map that puts items together by what f gives: groupby(words, w => len(w))",
    "without": "without(list, value) a copy of the list with that value taken out everywhere",
    "fill": "fill(value, count) a list with the value repeated: fill(0, 3) is [0, 0, 0]",
    "merge": "merge(map, other) a new map with the names from both (other wins when they clash)",
    "get": "get(map-or-list, key, default) a value, or the default when it isn't there",
    "entries": "entries(map) the map as a list of [name, value] pairs",
    "frompairs": "frompairs(list) a map from a list of [name, value] pairs",
    # text
    "commas": "commas(number) a number with commas every three digits: commas(1234567) is 1,234,567",
    "ordinal": "ordinal(n) a number with st, nd, rd or th: ordinal(2) is 2nd",
    "plural": "plural(count, word) the count and the word, with an s when it isn't 1: plural(3, \"coin\") is 3 coins",
    "wraptext": "wraptext(text, width) a list of lines, each at most width letters long, broken between words",
    # colors
    "mixcolor": "mixcolor(a, b, t) a colour part way from a to b: mixcolor(\"red\", \"blue\", 0.5)",
    "randomcolor": "randomcolor() a random bright colour",
    # timers for games
    "cooldown": "cooldown(\"name\", seconds) true at most once every few seconds, like a gun that needs to reload",
    "pulse": "pulse(\"name\", seconds) true once every few seconds, for spawning enemies on a beat",
    "after": "after(\"name\", seconds) false until that many seconds after the first time you ask, then true",
    # the view
    "scrollx": "scrollx() how far the view is scrolled to the right (see scroll)",
    "scrolly": "scrolly() how far the view is scrolled down (see scroll)",
    # dates and times
    "year": "year() this year, like 2026",
    "month": "month() this month as a number, 1 to 12",
    "day": "day() the day of the month, 1 to 31",
    "hour": "hour() the hour of the day, 0 to 23",
    "minute": "minute() the minute of the hour, 0 to 59",
    "second": "second() the second of the minute, 0 to 59",
    "weekday": "weekday() the day of the week as a word, like monday",
    "timetext": "timetext(seconds) a number of seconds as a clock, like 1:05 (or 1:02:03 for hours)",
    # more text
    "left": "left(text, n) the first n letters of some text",
    "right": "right(text, n) the last n letters of some text",
    "matches": "matches(text, pattern) true when the text fits a pattern, where * is any letters and ? is one",
    # vectors and numbers
    "normalize": "normalize(vector) the same direction with a length of 1",
    "dot": "dot(a, b) the dot product of two vectors (how much they point the same way)",
    "cross": "cross(a, b) a vec3 at right angles to two vec3 values",
    "percent": "percent(part, whole) how many percent part is of whole: percent(1, 4) is 25",
    # more lists
    "sample": "sample(list, n) n different random items from a list",
    "findindex": "findindex(list, function) the position of the first item the function says yes to, or -1",
    # objects on the screen
    "clicked": "clicked(object) true on the frame an object is clicked with the left mouse button",
    "hovering": "hovering(object) true while the mouse is over an object",
    "distance": "distance(a, b) how far apart the middles of two objects are",
    "screenpos": "screenpos(object) where a 3d shape is on the screen as a vec2, or none when it is behind you",
    "camerapos": "camerapos() where the 3d camera is, as a vec3",
    "camerayaw": "camerayaw() how far the 3d camera is turned left or right, in degrees",
    "camerapitch": "camerapitch() how far the 3d camera is tipped up or down, in degrees",
    # files
    "readfile": "readfile(path) all the text in a file",
    "readlines": "readlines(path) the lines of a text file as a list",
    "fileexists": "fileexists(path) true when there is a file (or folder) there",
    "isfolder": "isfolder(path) true when the path is a folder",
    "listfiles": "listfiles(folder) the names of the files and folders in a folder (the program's folder when empty)",
    "filesize": "filesize(path) how big a file is, in bytes",
    "filename": "filename(path) the last part of a path: filename(\"maps/one.txt\") is one.txt",
    "extension": "extension(path) the ending of a file name without the dot: extension(\"a.png\") is png",
    "fromcsv": "fromcsv(text) a list of rows (each a list of values) from comma separated text",
    "tocsv": "tocsv(rows) comma separated text from a list of rows",
}

EASINGS = ("linear", "in", "out", "inout", "smooth", "bounce", "elastic", "back")


def ease_value(t, kind="inout"):
    """bend a 0-to-1 progress into an easing curve (the same numbers in every gublan runtime)."""
    t = 0.0 if t < 0 else 1.0 if t > 1 else float(t)
    kind = str(kind).strip().lower()
    if kind == "linear":
        return t
    if kind == "in":
        return t * t
    if kind == "out":
        return 1 - (1 - t) * (1 - t)
    if kind == "inout":
        return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2
    if kind == "smooth":
        return t * t * (3 - 2 * t)
    if kind == "bounce":
        n, d = 7.5625, 2.75
        if t < 1 / d:
            return n * t * t
        if t < 2 / d:
            t -= 1.5 / d
            return n * t * t + 0.75
        if t < 2.5 / d:
            t -= 2.25 / d
            return n * t * t + 0.9375
        t -= 2.625 / d
        return n * t * t + 0.984375
    if kind == "elastic":
        if t in (0.0, 1.0):
            return t
        return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1
    if kind == "back":
        c1 = 1.70158
        return 1 + (c1 + 1) * (t - 1) ** 3 + c1 * (t - 1) ** 2
    raise ValueError(f"'{kind}' is not an easing. try: {', '.join(EASINGS)}")

PRESENCE_PARTS = ("details", "state", "image", "smallimage", "button", "party", "timer", "countdown", "app",
                  "clear")
_ASSIGNMENT_TOKENS = ("=", "+=", "-=", "*=", "/=")

EXPRESSION_KEYWORDS = {"and", "or", "not", "true", "false", "none", "pi", "to", "step", "in", "all", "dt",
                       "lambda", "if", "else", "for"}

GUBLANWORDS = sorted(
    GUBLANCOMMANDS | set(COLORS) | {"2d", "3d", "true", "false", "button", "to", "step", "in", "and",
                                     "or", "not", "all", "elif"}
)

KEY_ALIASES = {
    "esc": "escape", "enter": "return", "spacebar": "space", "shift": "left shift",
    "lshift": "left shift", "rshift": "right shift", "ctrl": "left ctrl", "control": "left ctrl",
    "lctrl": "left ctrl", "rctrl": "right ctrl", "alt": "left alt", "lalt": "left alt",
    "ralt": "right alt", "del": "delete", "bksp": "backspace", "pgup": "page up", "pgdn": "page down",
    "arrowleft": "left", "arrowright": "right", "arrowup": "up", "arrowdown": "down",
}


class GublanError(Exception):
    """a script error with the statement that caused it."""

    def __init__(self, message, statement=None):
        super().__init__(message)
        self.message = message
        self.statement = statement


class UnknownName(ValueError):
    pass


class _Signal(Exception):
    pass


class _Kill(_Signal):
    def __init__(self, message=""):
        super().__init__(message)
        self.message = message


class _Stop(_Signal):
    pass


class _Return(_Signal):
    def __init__(self, value):
        super().__init__()
        self.value = value


# --------------------------------------------------------------------------
# tokenizing and statement parsing (shared by the analyzer and the runtime)
# --------------------------------------------------------------------------

def split_command(line):
    """split a line into tokens.

    quotes group words ("my file.png"), {braces} keep expressions together and
    an apostrophe inside a word (don't) is just a letter.
    """
    if '"' not in line and "'" not in line and "{" not in line:
        return line.split()
    tokens = []
    index, length = 0, len(line)
    while index < length:
        if line[index].isspace():
            index += 1
            continue
        start = index
        pieces = []
        whole_quote = None
        while index < length and not line[index].isspace():
            char = line[index]
            if char in "\"'" and (char == '"' or index == start):
                closing = line.find(char, index + 1)
                if closing < 0:
                    pieces.append(char)
                    index += 1
                    continue
                if index == start and (closing + 1 >= length or line[closing + 1].isspace()):
                    whole_quote = line[index + 1:closing]
                pieces.append(line[index:closing + 1])
                index = closing + 1
            elif char == "{":
                depth, scan, quote = 0, index, None
                while scan < length:
                    current = line[scan]
                    if quote:
                        if current == quote:
                            quote = None
                    elif current in "\"'":
                        quote = current
                    elif current == "{":
                        depth += 1
                    elif current == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    scan += 1
                if scan >= length:
                    pieces.append(char)
                    index += 1
                    continue
                pieces.append(line[index:scan + 1])
                index = scan + 1
            else:
                pieces.append(char)
                index += 1
        token = "".join(pieces)
        if whole_quote is not None and len(pieces) == 1:
            tokens.append(QuotedText(whole_quote))
        else:
            tokens.append(token)
    return tokens


def _split_top_level_commas(text):
    """split comma-separated values without splitting inside strings or nested expressions."""
    parts = []
    start = 0
    stack = []
    quote = None
    escaped = False
    pairs = {")": "(", "]": "[", "}": "{"}

    for index, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
        elif char in "([{":
            stack.append(char)
        elif char in ")]}":
            if stack and stack[-1] == pairs[char]:
                stack.pop()
        elif char == "," and not stack:
            parts.append(text[start:index].strip())
            start = index + 1

    if not parts:
        return [text]
    parts.append(text[start:].strip())
    return [part for part in parts if part]


_ASSIGN_RE = re.compile(
    r"^([A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\[[^\]]*\])?)\s*(\+=|-=|\*=|/=|=)(?!=)\s*(.*)$"
)
_CALL_RE = re.compile(r"^([A-Za-z_]\w*)\s*\((.*)\)$")
_SET_RE = re.compile(r"^(\S+?)\s*=(?!=)\s*(.*)$")
_FOR_RANGE_RE = re.compile(r"^([A-Za-z_]\w*)\s*=\s*(.+?)\s+to\s+(.+?)(?:\s+step\s+(.+))?$")
_FOR_IN_RE = re.compile(r"^([A-Za-z_]\w*)\s+in\s+(.+)$")


class ParsedLine:
    __slots__ = ("cmd", "parts", "rest", "call_source", "error")

    def __init__(self, cmd, parts, rest, call_source=None, error=None):
        self.cmd = cmd
        self.parts = parts
        self.rest = rest
        self.call_source = call_source
        self.error = error


class ContinuedLine(str):
    """what is left of a line that was joined onto the line above it (a list or call spread over lines)."""


def _bracket_change(text):
    """how many brackets a line leaves open (opened minus closed), not counting ones inside quotes."""
    depth = 0
    quote = None
    previous = " "
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                previous = " "
                continue
            if char == quote:
                quote = None
        elif char == '"' or (char == "'" and not previous.isalnum()):
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        previous = char
        index += 1
    return depth


def join_continued_lines(lines):
    """let a list, map or call carry on over several lines.

    a line that ends with an open bracket or a comma inside brackets is joined with the lines below it until
    the brackets close. the joined lines become empty ContinuedLine markers, so line numbers stay the same.
    if the brackets never close, nothing is joined (and the normal error shows up on the first line).
    """
    lines = list(lines)
    index = 0
    while index < len(lines):
        text = lines[index].rstrip()
        stripped = text.strip()
        if stripped and not stripped.startswith("//") and stripped[-1] in "([{,":
            depth = _bracket_change(stripped)
            if depth > 0:
                pieces = [text]
                end = index + 1
                while end < len(lines) and depth > 0:
                    piece = lines[end].strip()
                    if piece and not piece.startswith("//"):
                        pieces.append(piece)
                        depth += _bracket_change(piece)
                    end += 1
                if depth == 0:
                    lines[index] = " ".join(pieces)
                    for later in range(index + 1, end):
                        lines[later] = ContinuedLine("")
                    index = end
                    continue
        index += 1
    return lines


def split_parameters(text):
    """split the parameters of a function line, keeping defaults whole:
    'a b="hi there" c=[1, 2]' -> ['a', 'b="hi there"', 'c=[1, 2]']"""
    tokens, current, depth, quote = [], [], 0, None
    for char in str(text):
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char.isspace() and depth <= 0:
            if current:
                tokens.append("".join(current))
                current = []
            continue
        current.append(char)
    if current:
        tokens.append("".join(current))
    merged = []
    for token in tokens:
        if merged and (token.startswith("=") or merged[-1].endswith("=")):
            merged[-1] += token
        else:
            merged.append(token)
    return merged


def parameter_parts(token):
    """'name="world"' -> ('name', '"world"'); 'name' -> ('name', None)"""
    name, separator, default = str(token).partition("=")
    return name.strip(), (default.strip() if separator else None)


def function_parameters(parts):
    """the names and defaults of a parsed function line: (['a', 'b'], {'b': '2'})"""
    names, defaults = [], {}
    for token in parts[2:]:
        name, default = parameter_parts(token)
        names.append(name)
        if default is not None:
            defaults[name] = default
    return names, defaults


def parse_line(raw):
    """turn one source line into a ParsedLine, or None for blank lines and comments."""
    text = raw.strip()
    if not text or text.startswith("//"):
        return None
    parts = split_command(text)
    if not parts:
        return None
    first = parts[0]
    if first == "function" and len(parts) > 2 and "=" in text and parts[1] not in _ASSIGNMENT_TOKENS:
        parts = parts[:2] + split_parameters(text.split(None, 2)[2])
    if first == "elif" or (first == "else" and len(parts) > 1 and parts[1] == "if"):
        skip = 1 if first == "elif" else 2
        rest = text.split(None, skip)[skip] if len(parts) > skip else ""
        return ParsedLine("elseif", ["elseif"] + parts[skip:], rest)
    if first not in GUBLANCOMMANDS or (len(parts) > 1 and parts[1] in _ASSIGNMENT_TOKENS and first != "set"
                                       and not isinstance(parts[1], QuotedText)):
        assignment = _ASSIGN_RE.match(text)
        if assignment:
            target, operator, value = assignment.groups()
            value_parts = split_command(value)
            if operator == "=":
                return ParsedLine("set", ["set", target, "="] + value_parts, f"{target} = {value}")
            command = {"+=": "add", "-=": "sub", "*=": "mul", "/=": "div"}[operator]
            return ParsedLine(command, [command, target] + value_parts, f"{target} {value}")
        call = _CALL_RE.match(text)
        if call and call.group(1) not in GUBLANCOMMANDS:
            return ParsedLine("call", ["call", call.group(1)], text, call_source=text)
        if call:
            return ParsedLine(first, parts, "", error=(
                f"write commands with spaces instead of brackets, like: {call.group(1)} "
                f"{call.group(2).replace(',', ' ').strip()}"
            ))
    rest = text[len(first):].strip() if not isinstance(first, QuotedText) else ""
    return ParsedLine(first, parts, rest)


def _normalize_condition(text):
    """accept =, &&, ||, !, <> and ~= in conditions by rewriting them for the evaluator."""
    out = []
    index, length = 0, len(text)
    quote = None
    while index < length:
        char = text[index]
        if quote:
            out.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "\"'":
            quote = char
            out.append(char)
            index += 1
            continue
        pair = text[index:index + 2]
        if pair == "&&":
            out.append(" and ")
            index += 2
        elif pair == "||":
            out.append(" or ")
            index += 2
        elif pair in ("<>", "~="):
            out.append("!=")
            index += 2
        elif pair in ("==", "!=", "<=", ">=", "=>"):
            out.append(pair)
            index += 2
        elif char == "!":
            out.append(" not ")
            index += 1
        elif char == "=":
            out.append("==")
            index += 1
        else:
            out.append(char)
            index += 1
    return "".join(out)


_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp, ast.Call,
    ast.Constant, ast.Name, ast.Load, ast.Attribute, ast.Subscript, ast.List, ast.Dict, ast.Tuple,
    ast.JoinedStr, ast.FormattedValue, ast.Slice,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd,
    ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    # whole-number bit operators (mostly for converted code)
    ast.BitAnd, ast.BitOr, ast.BitXor, ast.LShift, ast.RShift, ast.Invert,
    # little functions (x => x * 2 or lambda x: x * 2) and list building ([x * 2 for x in items])
    ast.Lambda, ast.arguments, ast.arg, ast.ListComp, ast.DictComp, ast.comprehension, ast.Store,
)

_ARROW_GROUP_RE = re.compile(r"\(\s*((?:[A-Za-z_]\w*\s*(?:,\s*[A-Za-z_]\w*\s*)*)?)\)\s*=>")
_ARROW_SINGLE_RE = re.compile(r"(?<![\w.])([A-Za-z_]\w*)\s*=>")
_QUOTED_RE = re.compile(r"(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')")


def _arrows_to_lambdas(text):
    """rewrite javascript-style arrow functions (x => x * 2, (a, b) => a + b) as python lambdas,
    leaving anything inside quotes alone."""
    if "=>" not in text:
        return text
    pieces = _QUOTED_RE.split(text)
    for index in range(0, len(pieces), 2):
        piece = _ARROW_GROUP_RE.sub(lambda m: f"lambda {m.group(1).strip()}:", pieces[index])
        pieces[index] = _ARROW_SINGLE_RE.sub(lambda m: f"lambda {m.group(1)}:", piece)
    return "".join(pieces)

_EXPRESSION_CACHE = {}


def parse_expression(text):
    """parse an expression into an ast node; raises SyntaxError or ValueError."""
    cached = _EXPRESSION_CACHE.get(text)
    if cached is not None:
        if isinstance(cached, Exception):
            raise cached
        return cached
    try:
        tree = ast.parse(_arrows_to_lambdas(text.strip()), mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, _ALLOWED_NODES):
                raise ValueError(f"'{type(node).__name__.lower()}' is not supported in expressions")
            if isinstance(node, ast.arguments) and (node.vararg or node.kwarg or node.kwonlyargs or node.defaults
                                                    or node.posonlyargs):
                raise ValueError("little functions only take plain names, like: x => x * 2")
            if isinstance(node, ast.comprehension) and node.is_async:
                raise ValueError("'async' is not supported in expressions")
        result = tree.body
    except (SyntaxError, ValueError) as err:
        if len(_EXPRESSION_CACHE) > 20000:
            _EXPRESSION_CACHE.clear()
        _EXPRESSION_CACHE[text] = err
        raise
    if len(_EXPRESSION_CACHE) > 20000:
        _EXPRESSION_CACHE.clear()
    _EXPRESSION_CACHE[text] = result
    return result


def parse_condition(text):
    node = parse_expression(_normalize_condition(text))
    if isinstance(node, ast.Lambda):
        # "if score => 2" is almost always a typo for >=, not a little function
        raise ValueError("this condition is not valid. did you mean >= ?")
    return node


def _condition_is_simple(tokens):
    return len(tokens) == 3 and tokens[1] in COMPARISON_OPERATORS


_MISSING = object()

# commands and functions added by studio plugins (see register_command and register_function)
_PLUGIN_COMMANDS = {}
_PLUGIN_FUNCTIONS = {}


def _noise_hash(x, y):
    n = (x * 374761393 + y * 668265263) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def _value_noise(x, y=0.0):
    """smooth value noise from 0 to 1: the same x and y always give the same answer."""
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = x - x0, y - y0
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    top = _noise_hash(x0, y0) + (_noise_hash(x0 + 1, y0) - _noise_hash(x0, y0)) * fx
    bottom = _noise_hash(x0, y0 + 1) + (_noise_hash(x0 + 1, y0 + 1) - _noise_hash(x0, y0 + 1)) * fx
    return top + (bottom - top) * fy


class GublanLambda:
    """a little function value: x => x * 2 (or lambda x: x * 2)."""
    __slots__ = ("params", "body")

    def __init__(self, params, body):
        self.params = params
        self.body = body

    def __repr__(self):
        return f"function({', '.join(self.params)})"


def format_value(value):
    """turn a runtime value into friendly text (lowercase booleans, tidy decimals)."""
    if isinstance(value, GublanLambda):
        return repr(value)
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "none"
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return f"{value:.10g}"
    if isinstance(value, str):
        return value
    if isinstance(value, Vector2):
        return f"vec2({format_value(value.x)}, {format_value(value.y)})"
    if isinstance(value, Vector3):
        return f"vec3({format_value(value.x)}, {format_value(value.y)}, {format_value(value.z)})"
    if isinstance(value, list):
        return "[" + ", ".join(_format_item(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{key}: {_format_item(item)}" for key, item in value.items()) + "}"
    return str(value)


def _format_item(value):
    return f'"{value}"' if isinstance(value, str) else format_value(value)


def kind_of(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "map"
    if isinstance(value, Vector2):
        return "vec2"
    if isinstance(value, Vector3):
        return "vec3"
    if isinstance(value, GublanLambda):
        return "function"
    if value is None:
        return "none"
    return "value"


def color_value(name):
    """resolve a color name, #hex text or rgb tuple to an (r, g, b) tuple."""
    if isinstance(name, tuple):
        return name
    if isinstance(name, str):
        lowered = name.lower()
        if lowered in COLORS:
            return COLORS[lowered]
        if re.fullmatch(r"#[0-9a-fA-F]{6}", name):
            return tuple(int(name[i:i + 2], 16) for i in (1, 3, 5))
        if re.fullmatch(r"#[0-9a-fA-F]{3}", name):
            return tuple(int(c * 2, 16) for c in name[1:])
    return COLORS["white"]


def is_color(name):
    return isinstance(name, str) and (
        name.lower() in COLORS or re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", name) is not None
    )


# ----- the look of game windows and popups ---------------------------------------------------------------
# gublan studio's tools menu edits these (tools > game window and popups). a program's own window,
# background and fps lines still win. GUBLAN_STYLE (json in the environment) sets them for the command line.
GAME_STYLE = {
    "width": 540,
    "height": 420,
    "title": "",
    "background": "#141414",
    "color": "white",
    "fps": 60,
    "show_fps": False,
    "dialog_background": "#262626",
    "dialog_text": "#e5e5e5",
    "dialog_hint": "#aaaaaa",
    "dialog_accent": "#94b66c",
    "dialog_border": "#94b66c",
    "dialog_field": "#171717",
    "dialog_border_width": 2,
    "dialog_shade": 75,
    "dialog_text_size": 26,
    "dialog_width": 450,
    "dialog_position": "center",
    "dialog_animation": "pop",
    "dialog_hints": True,
    "dialog_sound": True,
}
DIALOG_POSITIONS = ("center", "top", "bottom")
DIALOG_ANIMATIONS = ("pop", "fade", "slide", "none")
_STYLE_RANGES = {"width": (120, 4096), "height": (90, 4096), "fps": (1, 240), "dialog_border_width": (0, 12),
                 "dialog_shade": (0, 100), "dialog_text_size": (10, 64), "dialog_width": (160, 1600)}


def wrap_words(text, font, width):
    """split text into lines that fit width pixels in font (long words are cut)."""
    lines = []
    for paragraph in str(text).split("\n"):
        line = ""
        for word in paragraph.split(" "):
            attempt = f"{line} {word}" if line else word
            if font.size(attempt)[0] <= width:
                line = attempt
                continue
            if line:
                lines.append(line)
            while word and font.size(word)[0] > width:
                cut = len(word)
                while cut > 1 and font.size(word[:cut])[0] > width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            line = word
        lines.append(line)
    return lines


def game_style(overrides=None):
    """GAME_STYLE with the environment's GUBLAN_STYLE and then overrides on top. bad values are skipped."""
    style = dict(GAME_STYLE)
    layers = []
    raw = os.environ.get("GUBLAN_STYLE")
    if raw:
        try:
            layers.append(json.loads(raw))
        except ValueError:
            pass
    if overrides:
        layers.append(overrides)
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        for key, value in layer.items():
            if key not in GAME_STYLE:
                continue
            default = GAME_STYLE[key]
            if isinstance(default, bool):
                if isinstance(value, bool):
                    style[key] = value
            elif isinstance(default, int):
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    low, high = _STYLE_RANGES.get(key, (-10 ** 9, 10 ** 9))
                    style[key] = int(max(low, min(high, value)))
            elif key == "dialog_position":
                if value in DIALOG_POSITIONS:
                    style[key] = value
            elif key == "dialog_animation":
                if value in DIALOG_ANIMATIONS:
                    style[key] = value
            elif key == "title":
                style[key] = str(value)[:120]
            elif is_color(value):
                style[key] = value
    return style


# --------------------------------------------------------------------------
# static analysis
# --------------------------------------------------------------------------

def _check_expression(text, condition=False):
    try:
        if condition:
            parse_condition(text)
        else:
            parse_expression(text)
        return None
    except (SyntaxError, ValueError) as err:
        return str(err) if isinstance(err, ValueError) else "syntax"


def _presence_problem(tokens):
    what = str(tokens[0]).lower()
    rest = tokens[1:]
    if what not in PRESENCE_PARTS:
        suggestion = difflib.get_close_matches(what, PRESENCE_PARTS, n=1, cutoff=0.5)
        hint = f" did you mean '{suggestion[0]}'?" if suggestion else ""
        return f"presence can set {', '.join(PRESENCE_PARTS)}.{hint}"
    if what == "button" and rest:
        address = str(rest[0])
        if not (address.startswith(("https://", "http://", "{")) or address.isidentifier()):
            return "the button needs a web address that starts with https://, then its label"
        if len(rest) < 2:
            return "give the button a label after its web address: presence button https://example.com play"
    if what == "party" and len(rest) != 2:
        return "use: presence party <players> <most-players>"
    if what == "countdown" and len(rest) != 1:
        return "use: presence countdown <seconds>"
    if what == "timer" and rest and (len(rest) != 1 or rest[0] != "off"):
        return "use: presence timer  or  presence timer off"
    if what == "app" and (len(rest) != 1 or not (str(rest[0]).isdigit() or str(rest[0]).startswith("{")
                                                 or str(rest[0]).isidentifier())):
        return "use: presence app <discord application id>"
    if what == "clear" and rest:
        return "presence clear does not take anything else"
    return None


# how many words each 1.0.9 command can have (counting the command), and how to write it
_SHAPE_SIZES = {"cube": 6, "sphere": 6, "block": 8, "cylinder": 7, "cone": 7, "plane": 7}
_NAME_RE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?")


def _bad_file_path(token):
    path = str(token)
    if path.startswith("{") or isinstance(token, QuotedText) and "{" in path:
        return False
    cleaned = path.replace("\\", "/")
    return cleaned.startswith("/") or ":" in cleaned or ".." in cleaned.split("/")


def _check_109(command, parts):
    """the checker's rules for the commands added in 1.0.9 (3d shapes, files and the rest)."""
    count = len(parts)
    usage = COMMAND_USAGE.get(command, command)
    if count < COMMAND_MIN_ARGS.get(command, 0):
        return None  # "missing arguments" was already said
    if command in _SHAPE_SIZES:
        base = _SHAPE_SIZES[command]
        if count not in (base, base + 1, base + 3):
            return f"use: {usage}"
        return None
    if command == "turn" and count not in (4, 5):
        return f"use: {usage}"
    if command == "lookat" and count not in (2, 4):
        return f"use: {usage}"
    if command == "walk" and not 2 <= count <= 4:
        return f"use: {usage}"
    if command == "light" and count not in (4, 5):
        return f"use: {usage}"
    if command in ("seed", "gravity", "screenshot", "deletefile", "makefolder") and count != 2:
        return f"use: {usage}"
    if command == "velocity" and count not in (4, 5):
        return f"use: {usage}"
    if command == "swap":
        if count != 3:
            return f"use: {usage}"
        for token in parts[1:]:
            if not re.fullmatch(r"[A-Za-z_]\w*", str(token)):
                return f"'{token}' is not a valid variable name. names start with a letter"
    if command == "pop":
        if count not in (3, 4):
            return f"use: {usage}"
        if not _NAME_RE.fullmatch(str(parts[2])):
            return f"'{parts[2]}' is not a valid variable name. names start with a letter"
    if command == "readfile":
        if count != 3:
            return f"use: {usage}"
        if not _NAME_RE.fullmatch(str(parts[2])):
            return f"'{parts[2]}' is not a valid variable name. names start with a letter"
    if command in ("copyfile", "renamefile") and count != 3:
        return f"use: {usage}"
    if command in ("writefile", "appendfile", "readfile", "deletefile", "makefolder", "copyfile", "renamefile",
                   "screenshot"):
        paths = parts[1:3] if command in ("copyfile", "renamefile") else parts[1:2]
        if any(_bad_file_path(token) for token in paths):
            return "file paths stay inside your program's folder, like notes.txt or saves/one.txt"
    return None


def analyze_source(source, warnings=False):
    """check a script without running it. returns a list of {line, severity, message}."""
    diagnostics = []
    blocks = []
    lines = join_continued_lines(source.splitlines())
    parsed_lines = []
    function_names = set()
    has_include = False
    for raw in lines:
        try:
            parsed = parse_line(raw)
        except ValueError:
            parsed = None
        parsed_lines.append(parsed)
        if parsed and parsed.cmd == "function" and len(parsed.parts) >= 2:
            function_names.add(parsed.parts[1])
        if parsed and parsed.cmd in ("include", "use"):
            has_include = True

    def report(line, message, severity="error"):
        if severity == "error" or warnings:
            diagnostics.append({"line": line, "severity": severity, "message": message})

    defined_functions = set()
    constants = {}
    for lineno, parsed in enumerate(parsed_lines, start=1):
        if parsed is None:
            continue
        command, parts = parsed.cmd, parsed.parts
        if parsed.error:
            report(lineno, parsed.error)
            continue
        if command not in GUBLANCOMMANDS:
            suggestion = difflib.get_close_matches(command, sorted(GUBLANCOMMANDS), n=1, cutoff=0.55)
            hint = f" did you mean '{suggestion[0]}'?" if suggestion else ""
            report(lineno, f"'{command}' is not a command.{hint}")
            continue
        if command == "call" and parsed.call_source:
            error = _check_expression(parsed.call_source)
            if error:
                report(lineno, "this function call is not written correctly. try: name(1, 2)")
            elif parts[1] not in function_names and not has_include:
                report(lineno, f"there is no function named '{parts[1]}'")
            continue
        minimum = COMMAND_MIN_ARGS.get(command)
        if minimum is not None and len(parts) < minimum:
            report(lineno, f"'{command}' is missing arguments. try: {COMMAND_USAGE[command]}")
        if command in NO_ARGUMENT_COMMANDS and len(parts) > 1:
            report(lineno, f"'{command}' does not take arguments")
        if command == "set" and len(parts) >= 2:
            if not _SET_RE.match(parsed.rest):
                report(lineno, "write assignments as: set name = value")
            else:
                target = _SET_RE.match(parsed.rest).group(1)
                if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\[.+\])?", target):
                    report(lineno, f"'{target}' is not a valid variable name. names start with a letter")
        if command in ("const",) and len(parts) >= 2:
            match = _SET_RE.match(parsed.rest)
            if not match or not re.fullmatch(r"[A-Za-z_]\w*", match.group(1)):
                report(lineno, "write constants as: const name = value")
            else:
                constants.setdefault(match.group(1), lineno)
        if command in ("set", "add", "sub", "mul", "div") and len(parts) >= 2:
            assignment = _SET_RE.match(parsed.rest) if command == "set" else None
            target = assignment.group(1) if assignment else str(parts[1])
            if target in constants and constants[target] < lineno:
                report(lineno, f"'{target}' is a constant (line {constants[target]}), so it can't be changed")
        if command in ("until", "assert") and len(parts) >= 2:
            tokens = parts[1:]
            if not _condition_is_simple(tokens) and len(tokens) != 1 and _check_expression(parsed.rest, True):
                report(lineno, "this condition is not valid. use comparisons like x > 3")
        if command == "match" and len(parts) >= 2 and len(parts) > 2 and _check_expression(parsed.rest):
            report(lineno, "match needs one value to compare, like: match day")
        if command == "case" and len(parts) >= 2:
            for piece in _split_top_level_commas(parsed.rest):
                if _check_expression(piece):
                    report(lineno, "write cases as values split by commas, like: case 1, 2, 3")
                    break
        if command == "catch" and (len(parts) > 2 or (len(parts) == 2 and not str(parts[1]).isidentifier())):
            report(lineno, "use: catch  or  catch <variable>")
        if command == "use" and len(parts) != 2:
            report(lineno, "use: use <module-name>")
        if command == "slider" and len(parts) not in (7, 8):
            report(lineno, "use: slider <name> <x> <y> <width> <min> <max> [start]")
        if command == "focus" and len(parts) != 2:
            report(lineno, "use: focus <textbox>  or  focus none")
        if command in ("if", "elseif", "while") and len(parts) >= 2:
            tokens = parts[1:]
            if not _condition_is_simple(tokens) and len(tokens) != 1:
                if _check_expression(parsed.rest, condition=True):
                    report(
                        lineno,
                        "this condition is not valid. use comparisons like x > 3 with "
                        "=, ==, !=, >, <, >=, or <=, and join them with and/or",
                    )
        if command == "calc" and len(parts) >= 3:
            expression = parsed.rest.split(None, 1)[1] if len(parsed.rest.split(None, 1)) > 1 else ""
            if _check_expression(expression):
                report(lineno, "write a valid math expression, like: calc total price * 2")
        if command == "for" and len(parts) >= 2:
            if not (_FOR_RANGE_RE.match(parsed.rest) or _FOR_IN_RE.match(parsed.rest)):
                report(lineno, "write for loops as: for i = 1 to 10  or  for item in items")
        if command == "then" and len(parts) > 1 and parts[1] != "kill":
            report(lineno, "the only supported form is: then kill")
        if command == "then" and not any(block["type"] == "if" for block in blocks):
            report(lineno, "'then kill' only works inside an if block", "warning")
        if command == "mode" and len(parts) > 1 and parts[1] not in ("2d", "3d"):
            report(lineno, "choose either 2d or 3d")
        if command == "ui" and len(parts) > 1 and parts[1] != "button":
            report(lineno, "the only supported form is: ui button <label>")
        if command == "camera" and len(parts) not in (2, 4, 6):
            report(lineno, "use camera <x> <y> <z> [yaw] [pitch] or camera <vec3-variable>")
        problem = _check_109(command, parts)
        if problem:
            report(lineno, problem)
        if command == "vec2" and len(parts) != 4:
            report(lineno, "use: vec2 <name> <x> <y>")
        if command == "vec3" and len(parts) != 5:
            report(lineno, "use: vec3 <name> <x> <y> <z>")
        if command == "move" and len(parts) not in (3, 4, 5):
            report(lineno, "use move <object> <dx> <dy> or move <object> <vector>")
        if command == "place" and len(parts) not in (4, 5):
            report(lineno, "use: place <object> <x> <y> [z]")
        if command == "line" and len(parts) not in (6, 7):
            report(lineno, "use: line <name> <x1> <y1> <x2> <y2> [thickness]")
        if command == "color" and len(parts) not in (2, 4):
            report(lineno, "use color <name>, color #rrggbb or color <r> <g> <b>")
        if command == "color" and len(parts) == 2 and warnings and not str(parts[1]).startswith("{"):
            if not is_color(parts[1]) and not re.fullmatch(r"[A-Za-z_]\w*", parts[1] or ""):
                report(lineno, f"'{parts[1]}' is not a known color; white will be used", "warning")
            elif re.fullmatch(r"[a-z]+", parts[1]) and not is_color(parts[1]):
                report(lineno, f"'{parts[1]}' is not a known color name (unless it is a variable)",
                       "warning")
        if command == "animate" and len(parts) not in (5, 6):
            report(
                lineno,
                "use animate <2d-object> <x> <y> <seconds> or "
                "animate <3d-object> <x> <y> <z> <seconds>",
            )
        if command == "sprite" and len(parts) != 7:
            report(lineno, "use: sprite <name> <path> <x> <y> <width> <height>")
        if command == "cursor" and len(parts) > 1 and parts[1] not in ("show", "hide"):
            report(lineno, "use: cursor show  or  cursor hide")
        if command == "cursor" and len(parts) > 2:
            report(lineno, "use: cursor show  or  cursor hide")
        if command == "shuffle" and len(parts) > 2:
            report(lineno, "use: shuffle <list>")
        if command == "sort" and len(parts) > 2 and (len(parts) != 3 or parts[2] != "reverse"):
            report(lineno, "use: sort <list>  or  sort <list> reverse")
        if command == "load" and len(parts) >= 3 and not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?",
                                                                       str(parts[2])):
            report(lineno, f"'{parts[2]}' is not a valid variable name. names start with a letter")
        if command == "forget" and len(parts) > 2:
            report(lineno, "use: forget <name>  or  forget all")
        if command == "presence" and len(parts) >= 2:
            problem = _presence_problem(parts[1:])
            if problem:
                report(lineno, problem)
        if command == "test" and blocks:
            report(lineno, "test blocks must be written outside other blocks")
        if command == "function":
            if len(parts) >= 2:
                if not parts[1].isidentifier():
                    report(lineno, "function names must start with a letter or underscore")
                if any(block["type"] == "function" for block in blocks):
                    report(lineno, "functions cannot be defined inside another block")
                elif blocks:
                    report(lineno, "functions must be defined outside other blocks")
                if parts[1] in defined_functions:
                    report(lineno, f"function '{parts[1]}' is already defined")
                defined_functions.add(parts[1])
            names = [parameter_parts(token)[0] for token in parts[2:]]
            if len(names) != len(set(names)):
                report(lineno, "function parameters must have unique names")
            seen_default = False
            for token in parts[2:]:
                parameter, default = parameter_parts(token)
                if not parameter.isidentifier():
                    report(lineno, "function parameters must be valid names")
                elif default is not None:
                    seen_default = True
                    if not default:
                        report(lineno, f"give '{parameter}' a value after =, like: {parameter}=1")
                elif seen_default:
                    report(lineno, "parameters with a default (like name=1) must come after the ones without")
        if command == "local" and len(parts) >= 2:
            match = _SET_RE.match(parsed.rest)
            target = match.group(1) if match else parsed.rest.strip()
            if not re.fullmatch(r"[A-Za-z_]\w*", target):
                report(lineno, "write it as: local name = value")
            elif not any(block["type"] in CALLABLE_BLOCKS for block in blocks):
                report(lineno, "local only matters inside a function. out here it works just like set", "warning")
        if command == "return" and not any(block["type"] == "function" for block in blocks):
            report(lineno, "'return' must be inside a function")
        if command in ("break", "continue"):
            inside_loop = False
            for block in reversed(blocks):
                if block["type"] == "function":
                    break
                if block["type"] in LOOP_COMMANDS:
                    inside_loop = True
                    break
            if not inside_loop:
                report(lineno, f"'{command}' must be inside a loop")
        if command in BLOCK_OPENERS:
            blocks.append({"type": command, "line": lineno, "else_seen": False, "waits": False, "branches": 0})
        elif command in BLOCK_MIDDLES:
            parents = BLOCK_MIDDLES[command]
            if not blocks or blocks[-1]["type"] not in parents:
                report(lineno, f"'{command}' must be inside {' or '.join('a ' + p for p in parents)} block")
            elif blocks[-1]["else_seen"]:
                report(lineno, f"a {blocks[-1]['type']} block cannot have another branch after "
                               f"{'catch' if blocks[-1]['type'] == 'try' else 'else'}")
            else:
                blocks[-1]["branches"] += 1
                if command in ("else", "catch"):
                    blocks[-1]["else_seen"] = True
        elif blocks and blocks[-1]["type"] == "match" and blocks[-1]["branches"] == 0 and command != "end":
            report(lineno, "inside match, start with a case line, like: case 1")
        if command == "end":
            if not blocks:
                report(lineno, "'end' does not have a matching block (if, loop, while, for, match, try, function...)")
            else:
                block = blocks.pop()
                if block["type"] in ("forever", "while", "until") and not block["waits"]:
                    report(
                        block["line"],
                        f"this {block['type']} loop never waits (wait or frame), so it will run "
                        "as fast as the computer can",
                        "warning",
                    )
                if block["waits"] and blocks:
                    blocks[-1]["waits"] = True
        if command in ("wait", "frame", "popup", "input", "animate", "call"):
            for block in blocks:
                block["waits"] = True

    for block in blocks:
        report(block["line"], f"'{block['type']}' block is missing end")
    diagnostics.sort(key=lambda item: (item["line"], item["severity"] != "error"))
    return diagnostics


# --------------------------------------------------------------------------
# https helper
# --------------------------------------------------------------------------

class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, port, address, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        family, socktype, proto, _, sockaddr = self.address
        sock = socket.socket(family, socktype, proto)
        sock.settimeout(self.timeout)
        try:
            sock.connect(sockaddr)
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except (OSError, ssl.SSLError):
            sock.close()
            raise


def public_https_get(url, timeout=5, max_bytes=1_000_000):
    try:
        parsed = urlsplit(url)
        port = parsed.port or 443
    except ValueError as err:
        raise ValueError("that url is not valid") from err
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("use a complete https url to a public website")
    if parsed.username or parsed.password or port != 443:
        raise ValueError("only public https websites on port 443 are supported")

    host = parsed.hostname
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as err:
        raise ValueError("could not find that website; check the url and your connection") from err
    if not addresses:
        raise ValueError("could not find a network address for that website")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0].split("%", 1)[0])
        if not ip.is_global:
            raise ValueError("requests to local, private, or reserved network addresses are not allowed")

    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    connection = _PinnedHTTPSConnection(host, port, addresses[0], timeout)
    try:
        connection.request("GET", path, headers={"User-Agent": "Gublan/1.0", "Accept": "*/*"})
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise ValueError("the website redirected this request; use its final https url")
        if response.status < 200 or response.status >= 300:
            raise ValueError(f"the website returned status {response.status}")
        length = response.getheader("Content-Length")
        if length and int(length) > max_bytes:
            raise ValueError("the response is too large (limit: 1 mb)")
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("the response is too large (limit: 1 mb)")
        return data.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    except (OSError, http.client.HTTPException, ssl.SSLError) as err:
        raise ValueError("the https request failed; check the url and try again") from err
    finally:
        connection.close()


# --------------------------------------------------------------------------
# runtime
# --------------------------------------------------------------------------

class Statement:
    __slots__ = ("index", "line", "file", "cmd", "parts", "rest", "call_source", "end", "next",
                 "owner", "cache")

    def __init__(self, index, line, file, parsed):
        self.index = index
        self.line = line
        self.file = file
        self.cmd = parsed.cmd if parsed else None
        self.parts = parsed.parts if parsed else None
        self.rest = parsed.rest if parsed else ""
        self.call_source = parsed.call_source if parsed else None
        self.end = None
        self.next = None
        self.owner = None
        self.cache = None


class _Scene(dict):
    """the objects on screen. making an object again with the same name keeps its layer, opacity and
    fixed setting, so a score text remade every frame stays on top."""

    STYLE = ("layer", "alpha", "fixed")

    def __setitem__(self, key, value):
        old = self.get(key)
        if isinstance(old, dict) and isinstance(value, dict):
            for style in self.STYLE:
                if style in old and style not in value:
                    value[style] = old[style]
        super().__setitem__(key, value)


class FunctionInfo:
    __slots__ = ("start", "end", "params", "defaults")

    def __init__(self, start, end, params, defaults=None):
        self.start = start
        self.end = end
        self.params = params
        self.defaults = defaults or {}


_NUMBER_RE = re.compile(r"^-?(?:\d+\.?\d*|\.\d+)$")
_BRACE_RE = re.compile(r"\{([^{}]*)\}")
_FLOW_COMMANDS = {
    "if", "elseif", "else", "end", "loop", "forever", "while", "for", "break", "continue",
    "function", "return", "kill", "then", "until", "match", "case", "try", "catch", "test",
}


BUILTIN_MODULES_FOLDER = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))),
                                      "modules")


def user_folder():
    """the folder gublan studio keeps its settings, modules, themes and plugins in."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "GublanStudio")


def module_folders(base_dir=None):
    """where use <module> looks, in order: the program's modules folder, the program's folder,
    your own modules folder, then the modules that come with gublan."""
    folders = []
    if base_dir:
        folders += [os.path.join(base_dir, "modules"), base_dir]
    folders += [os.path.join(user_folder(), "modules"), BUILTIN_MODULES_FOLDER]
    return folders


def find_module(name, base_dir=None):
    if not re.fullmatch(r"[A-Za-z_][\w\-]*(?:/[A-Za-z_][\w\-]*)*", name or ""):
        return None
    for folder in module_folders(base_dir):
        path = os.path.join(folder, *name.split("/")) + ".gubl"
        if os.path.isfile(path):
            return path
    return None


def list_modules(base_dir=None):
    """every module use can find: {name: path}, nearest first."""
    found = {}
    for folder in module_folders(base_dir):
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for filename in names:
            if filename.endswith(".gubl") and filename[:-5] not in found:
                found[filename[:-5]] = os.path.join(folder, filename)
    return found


def saves_folder():
    """where save/load keep their values: one small json file per program."""
    override = os.environ.get("GUBLAN_SAVE_FOLDER")
    if override:
        return override
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Gublan", "saves")
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "gublan", "saves")


def save_file_name(name):
    cleaned = re.sub(r"[^\w\- ]+", "_", os.path.splitext(str(name or ""))[0]).strip(" _")[:80]
    return (cleaned or "untitled").lower() + ".json"


MAX_SAVED_VALUE = 256 * 1024
MAX_SAVED_NAMES = 1000


# ----- 3d shapes (shared by the game window, gublan studio's scene editor and the other runtimes) ----------------
SHAPES_3D = ("cube", "sphere", "block", "cylinder", "cone", "plane")
# the words after a shape's name that are its size, in order
SHAPE_SIZE_FIELDS = {"cube": ("size",), "sphere": ("radius",), "block": ("w", "h", "d"), "cylinder": ("r", "h"),
                     "cone": ("r", "h"), "plane": ("w", "d")}
_ROUND_SIDES = 24


def shape_extents(obj):
    """half of a 3d shape's size along x, y and z, before it is turned."""
    kind = obj["type"]
    if kind == "cube":
        half = abs(float(obj["size"])) / 2
        return half, half, half
    if kind == "sphere":
        radius = abs(float(obj["radius"]))
        return radius, radius, radius
    if kind in ("cylinder", "cone"):
        radius = abs(float(obj["r"]))
        return radius, abs(float(obj["h"])) / 2, radius
    if kind == "plane":
        return abs(float(obj["w"])) / 2, 0.0, abs(float(obj["d"])) / 2
    return abs(float(obj["w"])) / 2, abs(float(obj["h"])) / 2, abs(float(obj["d"])) / 2


def _rotation(axis, degrees):
    x, y, z = axis
    length = math.sqrt(x * x + y * y + z * z) or 1.0
    x, y, z = x / length, y / length, z / length
    angle = math.radians(degrees)
    c, s, t = math.cos(angle), math.sin(angle), 1 - math.cos(angle)
    return ((t * x * x + c, t * x * y - s * z, t * x * z + s * y),
            (t * x * y + s * z, t * y * y + c, t * y * z - s * x),
            (t * x * z - s * y, t * y * z + s * x, t * z * z + c))


def _matrix_times(a, b):
    return tuple(tuple(sum(a[row][k] * b[k][column] for k in range(3)) for column in range(3)) for row in range(3))


def shape_matrix(obj):
    """how a 3d shape is turned, as a 3x3 matrix (the same turn opengl and webgl give it).

    a cube that was only ever spun keeps the old turn about (1, 1, 0). anything that was turned turns about
    y (its angle), then x, then z."""
    if obj["type"] == "cube" and "rx" not in obj:
        return _rotation((1, 1, 0), float(obj.get("angle", 0)))
    matrix = _rotation((0, 1, 0), float(obj.get("angle", 0)))
    if obj.get("rx"):
        matrix = _matrix_times(matrix, _rotation((1, 0, 0), float(obj["rx"])))
    if obj.get("rz"):
        matrix = _matrix_times(matrix, _rotation((0, 0, 1), float(obj["rz"])))
    return matrix


def shape_mesh(kind, sizes, sides=_ROUND_SIDES):
    """the faces of a 3d shape around its middle: a list of (normal, [corner, ...]), each corner (x, y, z)."""
    faces = []

    def box(hx, hy, hz):
        return [
            ((0, 0, 1), [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]),
            ((0, 0, -1), [(hx, -hy, -hz), (-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz)]),
            ((0, 1, 0), [(-hx, hy, hz), (hx, hy, hz), (hx, hy, -hz), (-hx, hy, -hz)]),
            ((0, -1, 0), [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)]),
            ((1, 0, 0), [(hx, -hy, hz), (hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz)]),
            ((-1, 0, 0), [(-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz), (-hx, hy, -hz)]),
        ]

    if kind == "cube":
        half = sizes[0] / 2
        return box(half, half, half)
    if kind == "block":
        return box(sizes[0] / 2, sizes[1] / 2, sizes[2] / 2)
    if kind == "plane":
        hx, hz = sizes[0] / 2, sizes[1] / 2
        # one face: gl draws both of its sides, and a second face in the same place would flicker
        return [((0, 1, 0), [(-hx, 0, hz), (hx, 0, hz), (hx, 0, -hz), (-hx, 0, -hz)])]
    if kind == "sphere":
        radius = sizes[0]
        rings, segments = max(4, sides // 3), sides
        for ring in range(rings):
            top, bottom = math.pi * ring / rings, math.pi * (ring + 1) / rings
            for segment in range(segments):
                left, right = 2 * math.pi * segment / segments, 2 * math.pi * (segment + 1) / segments
                corners = []
                for latitude, longitude in ((bottom, left), (bottom, right), (top, right), (top, left)):
                    corners.append((radius * math.sin(latitude) * math.sin(longitude), radius * math.cos(latitude),
                                    radius * math.sin(latitude) * math.cos(longitude)))
                middle_lat, middle_lon = (top + bottom) / 2, (left + right) / 2
                normal = (math.sin(middle_lat) * math.sin(middle_lon), math.cos(middle_lat),
                          math.sin(middle_lat) * math.cos(middle_lon))
                faces.append((normal, corners))
        return faces
    radius, height = sizes[0], sizes[1]
    half = height / 2
    ring = [(radius * math.sin(2 * math.pi * i / sides), radius * math.cos(2 * math.pi * i / sides))
            for i in range(sides)]
    slope = math.hypot(radius, height) or 1.0
    for i in range(sides):
        (x1, z1), (x2, z2) = ring[i], ring[(i + 1) % sides]
        middle = 2 * math.pi * (i + 0.5) / sides
        if kind == "cylinder":
            faces.append(((math.sin(middle), 0, math.cos(middle)),
                          [(x1, -half, z1), (x2, -half, z2), (x2, half, z2), (x1, half, z1)]))
        else:
            faces.append(((math.sin(middle) * height / slope, radius / slope, math.cos(middle) * height / slope),
                          [(x1, -half, z1), (x2, -half, z2), (0, half, 0)]))
    faces.append(((0, -1, 0), [(x, -half, z) for x, z in reversed(ring)]))
    if kind == "cylinder":
        faces.append(((0, 1, 0), [(x, half, z) for x, z in ring]))
    return faces


def shape_sizes(obj):
    return tuple(abs(float(obj[field])) for field in SHAPE_SIZE_FIELDS[obj["type"]])


def view_point(camera, turn, point):
    """a world point as the 3d camera sees it (x right, y up, z towards you, so in front is minus z)."""
    yaw, pitch = (math.radians(value) for value in turn)
    dx, dy, dz = point[0] - camera[0], point[1] - camera[1], point[2] - camera[2]
    x = dx * math.cos(yaw) + dz * math.sin(yaw)
    z = -dx * math.sin(yaw) + dz * math.cos(yaw)
    y = dy * math.cos(pitch) - z * math.sin(pitch)
    z = dy * math.sin(pitch) + z * math.cos(pitch)
    return x, y, z


def project_point(camera, turn, point, width, height, fov=45.0):
    """where a world point lands in a width x height window, or None when it is behind the camera."""
    x, y, z = view_point(camera, turn, point)
    if z > -0.1:
        return None
    focal = 1 / math.tan(math.radians(fov) / 2)
    aspect = width / height if height else 1.0
    return ((focal / aspect * x / -z + 1) / 2 * width, (1 - focal * y / -z) / 2 * height)


def look_angles(source, target):
    """the camera yaw and pitch (degrees) that look from source towards target."""
    dx, dy, dz = target[0] - source[0], target[1] - source[1], target[2] - source[2]
    return math.degrees(math.atan2(dx, -dz)), math.degrees(math.atan2(-dy, math.hypot(dx, dz)))


_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_FILE_LIMIT = 10 * 1024 * 1024


class _Features109:
    """what gublan 1.0.9 adds to the runtime: more 3d shapes, files, movement and a lot of new functions."""

    # ----- 3d shapes -----------------------------------------------------------------------------------------
    def _shape_color(self, parts, first):
        if len(parts) <= first:
            return self.activecolor
        color = self._color_from(parts[first:])
        if isinstance(color, str) and not is_color(color):
            raise ValueError(f"'{color}' is not a colour. use a name like moss, #ff8800 or three numbers")
        return color

    def _shape_numbers(self, parts, what, count):
        values = [self._num(part, f"{what} {label}") for part, label in
                  zip(parts[2:2 + count], ("x", "y", "z", "size", "size", "size"))]
        if any(value <= 0 for value in values[3:]):
            raise ValueError(f"{what} sizes must be greater than zero")
        return values

    def _make_shape(self, statement, kind):
        parts = statement.parts
        fields = SHAPE_SIZE_FIELDS[kind]
        count = 3 + len(fields)
        if len(parts) not in (count + 2, count + 3, count + 5):
            raise ValueError(f"use: {COMMAND_USAGE[kind]}")
        values = self._shape_numbers(parts, kind, count)
        shape = {"type": kind, "x": values[0], "y": values[1], "z": values[2], "angle": 0, "rx": 0, "rz": 0,
                 "color": self._shape_color(parts, count + 2)}
        shape.update(zip(fields, values[3:]))
        self.objects[self._name(parts[1])] = shape

    def _c_block(self, statement):
        self._make_shape(statement, "block")

    def _c_cylinder(self, statement):
        self._make_shape(statement, "cylinder")

    def _c_cone(self, statement):
        self._make_shape(statement, "cone")

    def _c_plane(self, statement):
        self._make_shape(statement, "plane")

    def _c_turn(self, statement):
        parts = statement.parts
        obj = self._object(parts[1], SHAPES_3D, "turn")
        obj["rx"] = self._num(parts[2], "x angle")
        obj["angle"] = self._num(parts[3], "y angle")
        obj["rz"] = self._num(parts[4], "z angle") if len(parts) > 4 else 0

    def _c_lookat(self, statement):
        parts = statement.parts
        if len(parts) == 2:
            target = self.val(parts[1]) if not self._is_object(parts[1]) else None
            if isinstance(target, Vector3):
                point = (target.x, target.y, target.z)
            else:
                obj = self._object(parts[1], SHAPES_3D, "look at")
                point = (obj["x"], obj["y"], obj["z"])
        elif len(parts) == 4:
            point = tuple(self._num(part, "lookat coordinate") for part in parts[1:4])
        else:
            raise ValueError(f"use: {COMMAND_USAGE['lookat']}")
        camera = (self.camera.x, self.camera.y, self.camera.z)
        if all(abs(a - b) < 1e-9 for a, b in zip(camera, point)):
            return
        self.camera_turn = look_angles(camera, point)

    def _is_object(self, token):
        name = self._name(token)
        return isinstance(self.objects.get(name), dict)

    def _c_walk(self, statement):
        parts = statement.parts
        forward = self._num(parts[1], "walk distance")
        right = self._num(parts[2], "walk sideways") if len(parts) > 2 else 0
        up = self._num(parts[3], "walk up") if len(parts) > 3 else 0
        yaw = math.radians(self.camera_turn[0])
        self.camera = Vector3(self.camera.x + math.sin(yaw) * forward + math.cos(yaw) * right,
                              self.camera.y + up,
                              self.camera.z - math.cos(yaw) * forward + math.sin(yaw) * right)

    def _c_light(self, statement):
        parts = statement.parts
        x, y, z = (self._num(part, "light direction") for part in parts[1:4])
        brightness = self._num(parts[4], "brightness") if len(parts) > 4 else 1
        if not x and not y and not z:
            raise ValueError("the light needs a direction, like light 1 2 1")
        if not 0 <= brightness <= 4:
            raise ValueError("light brightness goes from 0 to 4 (1 is normal)")
        self.light = (x, y, z, brightness)

    def _mesh(self, obj):
        key = (obj["type"],) + shape_sizes(obj)
        mesh = self._mesh_cache.get(key)
        if mesh is None:
            if len(self._mesh_cache) > 400:
                self._mesh_cache.clear()
            mesh = shape_mesh(obj["type"], key[1:])
            self._mesh_cache[key] = mesh
        return mesh

    def _render_shape_gl(self, obj):
        glPushMatrix()
        glTranslatef(obj["x"] - self.camera.x, obj["y"] - self.camera.y, obj["z"] - self.camera.z)
        red, green, blue = color_value(obj["color"])
        glColor3f(red / 255.0, green / 255.0, blue / 255.0)
        kind = obj["type"]
        if kind == "cube" and "rx" not in obj:
            glRotatef(obj["angle"], 1, 1, 0)
        else:
            if obj.get("angle"):
                glRotatef(obj["angle"], 0, 1, 0)
            if obj.get("rx"):
                glRotatef(obj["rx"], 1, 0, 0)
            if obj.get("rz"):
                glRotatef(obj["rz"], 0, 0, 1)
        if kind == "sphere":
            quadric = gluNewQuadric()
            gluSphere(quadric, obj["radius"], 24, 16)
            gluDeleteQuadric(quadric)
        else:
            for normal, corners in self._mesh(obj):
                glBegin(GL_POLYGON)
                glNormal3f(*normal)
                for corner in corners:
                    glVertex3fv(corner)
                glEnd()
        glPopMatrix()

    def _shape_box(self, obj):
        """the smallest level box around a turned 3d shape: (low x, low y, low z, high x, high y, high z)."""
        hx, hy, hz = shape_extents(obj)
        if obj["type"] == "sphere":
            ex, ey, ez = hx, hy, hz
        else:
            matrix = shape_matrix(obj)
            ex, ey, ez = (abs(row[0]) * hx + abs(row[1]) * hy + abs(row[2]) * hz for row in matrix)
        x, y, z = float(obj["x"]), float(obj["y"]), float(obj["z"])
        return x - ex, y - ey, z - ez, x + ex, y + ey, z + ez

    def _touching_3d(self, first, second):
        if first["type"] == "sphere" and second["type"] == "sphere":
            gap = sum((float(first[axis]) - float(second[axis])) ** 2 for axis in "xyz")
            return gap <= (abs(float(first["radius"])) + abs(float(second["radius"]))) ** 2
        if second["type"] == "sphere":
            first, second = second, first
        if first["type"] == "sphere":
            box = self._shape_box(second)
            centre = [float(first[axis]) for axis in "xyz"]
            gap = sum((value - max(box[i], min(box[i + 3], value))) ** 2 for i, value in enumerate(centre))
            return gap <= abs(float(first["radius"])) ** 2
        a, b = self._shape_box(first), self._shape_box(second)
        return all(a[i] <= b[i + 3] and b[i] <= a[i + 3] for i in range(3))

    def _project(self, point):
        width, height = self.screen.get_size() if self.screen else self.window_size
        return project_point((self.camera.x, self.camera.y, self.camera.z), self.camera_turn, point, width, height)

    def _screen_box(self, obj):
        low_x, low_y, low_z, high_x, high_y, high_z = self._shape_box(obj)
        points = [self._project((x, y, z)) for x in (low_x, high_x) for y in (low_y, high_y) for z in (low_z, high_z)]
        points = [point for point in points if point is not None]
        if not points:
            return None
        return (min(p[0] for p in points), min(p[1] for p in points),
                max(p[0] for p in points), max(p[1] for p in points))

    def _point_on(self, obj, mx, my):
        if obj.get("hidden"):
            return False
        if obj["type"] in SHAPES_3D:
            box = self._screen_box(obj)
            return box is not None and box[0] <= mx <= box[2] and box[1] <= my <= box[3]
        if obj["type"] not in self._UI_KINDS and not obj.get("fixed"):
            mx, my = mx + self.scroll[0], my + self.scroll[1]
        try:
            shape = self._collision_shape(obj)
        except ValueError as err:
            raise ValueError("clicked() and hovering() work on shapes, text, pictures and buttons") from err
        if shape[0] == "circle":
            _, cx, cy, radius = shape
            return (mx - cx) ** 2 + (my - cy) ** 2 <= radius ** 2
        _, x, y, w, h = shape
        return x <= mx <= x + w and y <= my <= y + h

    def _centre(self, value):
        if isinstance(value, (Vector2, Vector3)):
            return self._components(value)
        obj = self._object(value, action="measure")
        if obj["type"] in SHAPES_3D:
            return float(obj["x"]), float(obj["y"]), float(obj["z"])
        if obj["type"] == "line":
            return (obj["x"] + obj["x2"]) / 2, (obj["y"] + obj["y2"]) / 2
        shape = self._collision_shape(obj)
        if shape[0] == "circle":
            return shape[1], shape[2]
        _, x, y, w, h = shape
        return x + w / 2, y + h / 2

    # ----- moving by itself ------------------------------------------------------------------------------------
    def _c_velocity(self, statement):
        parts = statement.parts
        obj = self._object(parts[1], action="give a velocity to")
        if "x" not in obj or "y" not in obj:
            raise ValueError(f"a {obj['type']} can't move by itself")
        vx, vy = self._num(parts[2], "x speed"), self._num(parts[3], "y speed")
        vz = self._num(parts[4], "z speed") if len(parts) > 4 else 0
        if vz and obj["type"] not in SHAPES_3D:
            raise ValueError("only 3d shapes can move along z")
        obj["vx"], obj["vy"], obj["vz"] = vx, vy, vz

    def _c_gravity(self, statement):
        self.gravity = self._num(statement.parts[1], "gravity")

    def _tick_motion(self, step):
        if step <= 0:
            return
        for obj in list(self.objects.values()):
            if not isinstance(obj, dict) or "vx" not in obj:
                continue
            three = obj["type"] in SHAPES_3D
            if self.gravity:
                obj["vy"] += (-self.gravity if three else self.gravity) * step
            dx, dy = obj["vx"] * step, obj["vy"] * step
            obj["x"] += dx
            obj["y"] += dy
            if obj["type"] == "line":
                obj["x2"] += dx
                obj["y2"] += dy
            if three and obj.get("vz"):
                obj["z"] += obj["vz"] * step

    # ----- small helpers ---------------------------------------------------------------------------------------
    def _c_seed(self, statement):
        value = self.val(statement.parts[1])
        random.seed(format_value(value) if not isinstance(value, (int, float)) or isinstance(value, bool)
                    else value)

    def _c_swap(self, statement):
        first, second = (str(part) for part in statement.parts[1:3])
        for name in (first, second):
            if name not in self.vars:
                raise ValueError(f"'{name}' has no value yet, so it can't be swapped")
            if name in self.constants:
                raise ValueError(f"'{name}' is a constant (made with const), so it can't be changed")
        self.vars[first], self.vars[second] = self.vars[second], self.vars[first]

    def _c_pop(self, statement):
        parts = statement.parts
        items = self.vars.get(str(parts[1]))
        if not isinstance(items, list):
            raise ValueError(f"'{parts[1]}' is not a list")
        if not items:
            raise ValueError(f"'{parts[1]}' is empty, so there is nothing to take")
        if len(parts) > 3:
            position = self.val(parts[3])
            if isinstance(position, bool) or not isinstance(position, int):
                raise ValueError("list positions must be whole numbers")
            if not -len(items) <= position < len(items):
                raise ValueError(f"position {position} is past the end (length {len(items)})")
            value = items.pop(position)
        else:
            value = items.pop()
        self._set_target(str(parts[2]), value)

    def _c_screenshot(self, statement):
        if not self.screen:
            raise ValueError("add 'mode 2d' or 'mode 3d' before you take a screenshot")
        path = self._file_path(self._name(statement.parts[1]), "screenshot")
        if not path.lower().endswith(".png"):
            path += ".png"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if self.mode == "3d":
            width, height = self.screen.get_size()
            glReadBuffer(GL_FRONT)
            data = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE)
            picture = pygame.transform.flip(pygame.image.frombuffer(bytes(data), (width, height), "RGB"), False, True)
        else:
            picture = self.screen
        try:
            pygame.image.save(picture, path)
        except (OSError, pygame.error) as err:
            raise ValueError(f"could not save the screenshot: {str(err).lower()}") from err

    # ----- files -----------------------------------------------------------------------------------------------
    def _file_path(self, relative, what="file"):
        relative = format_value(relative).strip() if not isinstance(relative, str) else relative.strip()
        if not relative:
            raise ValueError(f"give the {what} a name, like notes.txt")
        cleaned = relative.replace("\\", "/")
        if cleaned.startswith("/") or ":" in cleaned or ".." in cleaned.split("/"):
            raise ValueError("file paths stay inside your program's folder, like notes.txt or saves/one.txt")
        pieces = [piece for piece in cleaned.split("/") if piece not in ("", ".")]
        path = os.path.abspath(os.path.join(self.base_dir, *pieces)) if pieces else self.base_dir
        try:
            inside = os.path.commonpath([path, self.base_dir]) == self.base_dir
        except ValueError:
            inside = False
        if not inside:
            raise ValueError("file paths stay inside your program's folder, like notes.txt or saves/one.txt")
        return path

    def _read_text(self, relative):
        path = self._file_path(relative)
        if os.path.isdir(path):
            raise ValueError(f"'{relative}' is a folder, not a file")
        if not os.path.isfile(path):
            path = self._fetched(relative) or path
        if not os.path.isfile(path):
            raise ValueError(f"file '{relative}' was not found")
        if os.path.getsize(path) > _FILE_LIMIT:
            raise ValueError(f"file '{relative}' is too big to read (the most is 10 mb)")
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace", newline=None) as handle:
                return handle.read()
        except OSError as err:
            raise ValueError(f"could not read '{relative}': {err.strerror or err}".lower()) from err

    def _write_text(self, relative, text, append=False):
        path = self._file_path(relative)
        if os.path.isdir(path):
            raise ValueError(f"'{relative}' is a folder, not a file")
        if len(text) > _FILE_LIMIT:
            raise ValueError("that is too much to write at once (the most is 10 mb)")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if append and os.path.isfile(path) and os.path.getsize(path):
                with open(path, "rb") as handle:
                    handle.seek(-1, os.SEEK_END)
                    if handle.read(1) not in (b"\n", b"\r"):
                        text = "\n" + text
            with open(path, "a" if append else "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        except OSError as err:
            raise ValueError(f"could not write '{relative}': {err.strerror or err}".lower()) from err

    def _file_text(self, tokens):
        if len(tokens) == 1:
            token = tokens[0]
            raw = str(token)
            whole = not isinstance(token, QuotedText) and (
                raw in self.vars or (raw.startswith("{") and raw.endswith("}") and raw.count("{") == 1))
            if whole:
                value = self.vars[raw] if raw in self.vars else self.val(token)
                if isinstance(value, list):
                    return "\n".join(format_value(item) for item in value)
        return self._text(tokens)

    def _c_writefile(self, statement):
        parts = statement.parts
        self._write_text(self._name(parts[1]), self._file_text(parts[2:]))

    def _c_appendfile(self, statement):
        parts = statement.parts
        self._write_text(self._name(parts[1]), self._file_text(parts[2:]) + "\n", append=True)

    def _c_readfile(self, statement):
        parts = statement.parts
        self._set_target(str(parts[2]), self._read_text(self._name(parts[1])))

    def _c_deletefile(self, statement):
        relative = self._name(statement.parts[1])
        path = self._file_path(relative)
        if path == self.base_dir:
            raise ValueError("gublan won't delete your program's own folder")
        try:
            if os.path.isdir(path):
                if os.listdir(path):
                    raise ValueError(f"folder '{relative}' is not empty. delete the files in it first")
                os.rmdir(path)
            elif os.path.exists(path):
                os.remove(path)
        except OSError as err:
            raise ValueError(f"could not delete '{relative}': {err.strerror or err}".lower()) from err

    def _c_makefolder(self, statement):
        relative = self._name(statement.parts[1])
        path = self._file_path(relative, "folder")
        if os.path.isfile(path):
            raise ValueError(f"'{relative}' is already a file")
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as err:
            raise ValueError(f"could not make '{relative}': {err.strerror or err}".lower()) from err

    def _move_file(self, statement, keep):
        source_name, target_name = self._name(statement.parts[1]), self._name(statement.parts[2])
        source, target = self._file_path(source_name), self._file_path(target_name)
        if not os.path.isfile(source):
            raise ValueError(f"file '{source_name}' was not found")
        if os.path.isdir(target):
            target = os.path.join(target, os.path.basename(source))
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if keep:
                if os.path.getsize(source) > _FILE_LIMIT * 10:
                    raise ValueError(f"file '{source_name}' is too big to copy")
                with open(source, "rb") as reading, open(target, "wb") as writing:
                    writing.write(reading.read())
            else:
                os.replace(source, target)
        except OSError as err:
            raise ValueError(f"could not {'copy' if keep else 'rename'} '{source_name}': "
                             f"{err.strerror or err}".lower()) from err

    def _c_copyfile(self, statement):
        self._move_file(statement, keep=True)

    def _c_renamefile(self, statement):
        self._move_file(statement, keep=False)

    # ----- the functions added in 1.0.9 --------------------------------------------------------------------------
    def _builtin_109(self, name, args, number, need):
        def whole(value, label="count"):
            value = number(value, label)
            if value != int(value):
                raise ValueError(f"{name}() needs a whole number for its {label}")
            return int(value)

        def text(value):
            return value if isinstance(value, str) else format_value(value)

        def vector(value):
            if isinstance(value, (Vector2, Vector3)):
                return list(self._components(value)), type(value)
            if isinstance(value, list) and len(value) in (2, 3) and all(
                    not isinstance(item, bool) and isinstance(item, (int, float)) for item in value):
                return [float(item) for item in value], list
            raise ValueError(f"{name}() needs a vec2, a vec3 or a list of numbers, got '{format_value(value)}'")

        def rebuilt(values, kind):
            if kind is list:
                return [int(v) if v == int(v) else v for v in values]
            return kind(*values)

        if name in ("year", "month", "day", "hour", "minute", "second", "weekday"):
            need(0)
            now = time.localtime()
            if name == "weekday":
                return _WEEKDAYS[now.tm_wday]
            return {"year": now.tm_year, "month": now.tm_mon, "day": now.tm_mday, "hour": now.tm_hour,
                    "minute": now.tm_min, "second": now.tm_sec}[name]
        if name == "timetext":
            need(1)
            seconds = number(args[0], "seconds")
            sign = "-" if seconds < 0 else ""
            seconds = int(math.floor(abs(seconds)))
            hours, rest = divmod(seconds, 3600)
            minutes, seconds = divmod(rest, 60)
            if hours:
                return f"{sign}{hours}:{minutes:02d}:{seconds:02d}"
            return f"{sign}{minutes}:{seconds:02d}"
        if name in ("left", "right"):
            need(2)
            value, count = text(args[0]), whole(args[1])
            if count <= 0:
                return ""
            return value[:count] if name == "left" else value[-count:]
        if name == "matches":
            need(2)
            pattern = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in text(args[1]))
            return re.fullmatch(pattern, text(args[0]), re.IGNORECASE | re.DOTALL) is not None
        if name == "normalize":
            need(1)
            values, kind = vector(args[0])
            length = math.sqrt(sum(v * v for v in values))
            return rebuilt([v / length for v in values] if length else values, kind)
        if name == "dot":
            need(2)
            first, second = vector(args[0])[0], vector(args[1])[0]
            if len(first) != len(second):
                raise ValueError("dot() needs two vectors of the same size")
            total = sum(a * b for a, b in zip(first, second))
            return int(total) if total == int(total) else total
        if name == "cross":
            need(2)
            first, second = vector(args[0])[0], vector(args[1])[0]
            ax, ay, az = first + [0.0] * (3 - len(first))
            bx, by, bz = second + [0.0] * (3 - len(second))
            return Vector3(ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)
        if name == "percent":
            need(2)
            part, all_of = number(args[0], "part"), number(args[1], "whole")
            if not all_of:
                return 0
            value = part / all_of * 100
            return int(value) if value == int(value) else value
        if name == "sample":
            need(2)
            items = list(args[0]) if isinstance(args[0], (list, str)) else None
            if items is None:
                raise ValueError(f"sample() needs a list, got '{format_value(args[0])}'")
            count = whole(args[1])
            return random.sample(items, max(0, min(count, len(items))))
        if name == "findindex":
            need(2)
            if not isinstance(args[0], (list, str)):
                raise ValueError(f"findindex() needs a list, got '{format_value(args[0])}'")
            for index, item in enumerate(args[0]):
                if self._truthy(self._call_value(args[1], [item])):
                    return index
            return -1
        if name in ("clicked", "hovering"):
            need(1)
            self._require_screen("check the mouse")
            obj = self._object(text(args[0]), action="check the mouse on")
            if name == "hovering":
                self.pumpevents()
                return self._point_on(obj, *pygame.mouse.get_pos())
            if self._frames_drawn == 0:
                self.pumpevents()
                for click in list(self._clicks):
                    if self._point_on(obj, *click):
                        self._clicks.remove(click)
                        return True
                return False
            return any(self._point_on(obj, *click) for click in self._frame_clicks)
        if name == "distance":
            need(2)
            first = self._centre(args[0] if isinstance(args[0], (Vector2, Vector3)) else text(args[0]))
            second = self._centre(args[1] if isinstance(args[1], (Vector2, Vector3)) else text(args[1]))
            size = min(len(first), len(second))
            value = math.sqrt(sum((a - b) ** 2 for a, b in zip(first[:size], second[:size])))
            return int(value) if value == int(value) else value
        if name == "screenpos":
            need(1)
            obj = self._object(text(args[0]), action="find")
            if obj["type"] in SHAPES_3D:
                point = self._project((float(obj["x"]), float(obj["y"]), float(obj["z"])))
                return None if point is None else Vector2(round(point[0], 2), round(point[1], 2))
            x, y = self._centre(text(args[0]))[:2]
            if obj["type"] not in self._UI_KINDS and not obj.get("fixed"):
                x, y = x - self.scroll[0], y - self.scroll[1]
            return Vector2(x, y)
        if name == "camerapos":
            need(0)
            return self.camera
        if name in ("camerayaw", "camerapitch"):
            need(0)
            value = self.camera_turn[0 if name == "camerayaw" else 1]
            return int(value) if value == int(value) else round(value, 6)
        if name == "readfile":
            need(1)
            return self._read_text(text(args[0]))
        if name == "readlines":
            need(1)
            return self._read_text(text(args[0])).splitlines()
        if name in ("fileexists", "isfolder", "filesize", "listfiles"):
            if name == "listfiles":
                if len(args) > 1:
                    raise ValueError("listfiles() needs one folder, or nothing for the program's folder")
                path = self._file_path(text(args[0]), "folder") if args and text(args[0]).strip() else self.base_dir
                if not os.path.isdir(path):
                    raise ValueError(f"'{text(args[0]) if args else '.'}' is not a folder")
                return sorted(os.listdir(path), key=str.lower)
            need(1)
            path = self._file_path(text(args[0]))
            if name == "fileexists":
                return os.path.exists(path)
            if name == "isfolder":
                return os.path.isdir(path)
            if not os.path.isfile(path):
                raise ValueError(f"file '{text(args[0])}' was not found")
            return os.path.getsize(path)
        if name == "filename":
            need(1)
            return text(args[0]).replace("\\", "/").rstrip("/").split("/")[-1]
        if name == "extension":
            need(1)
            base = text(args[0]).replace("\\", "/").split("/")[-1]
            return base.rsplit(".", 1)[1] if "." in base.strip(".") else ""
        if name == "fromcsv":
            need(1)
            rows = []
            for row in csv.reader(io.StringIO(text(args[0]))):
                rows.append([_csv_value(cell) for cell in row])
            return rows
        if name == "tocsv":
            need(1)
            rows = args[0]
            if not isinstance(rows, list):
                raise ValueError(f"tocsv() needs a list of rows, got '{format_value(rows)}'")
            if rows and not all(isinstance(row, list) for row in rows):
                rows = [rows]
            out = io.StringIO()
            writer = csv.writer(out, lineterminator="\n")
            for row in rows:
                writer.writerow([format_value(cell) for cell in row])
            return out.getvalue().rstrip("\n")
        return _MISSING


def _csv_value(cell):
    cleaned = cell.strip()
    if re.fullmatch(r"-?(?:0|[1-9][0-9]*)", cleaned):
        return int(cleaned)
    if re.fullmatch(r"-?(?:0|[1-9][0-9]*)[.][0-9]+", cleaned):
        return float(cleaned)
    return cell


class GublanRuntime(_Features109):
    def __init__(self, onlog=None, ondebug=None, shouldstop=None, waitstep=None, base_dir=None,
                 onerror=None, hold_window=False, oninput=None, onpopup=None, onpresence=None, save_name=None,
                 fetchfile=None, style=None):
        self.onlog = onlog or print
        # fetchfile(relative path) -> a local path or None. gublan studio sets it for a program shared in a live
        # session, so pictures, sounds and included files come from the host's computer
        self.fetchfile = fetchfile
        self.ondebug = ondebug
        self.onerror = onerror
        self.oninput = oninput
        self.onpopup = onpopup
        # onpresence(application_id, activity) receives the program's discord status. without it the runtime
        # talks to discord itself (exported games and the command line)
        self.onpresence = onpresence
        self.save_name = save_name
        self._presence_client = None
        self.shouldstop = shouldstop or (lambda: False)
        self.waitstep = waitstep
        self.hold_window = hold_window
        self.style = game_style(style)
        self.base_dir = os.path.abspath(base_dir or os.getcwd())
        self._handlers = {
            name[3:]: getattr(self, name) for name in dir(self) if name.startswith("_c_")
        }
        for name, run in _PLUGIN_COMMANDS.items():
            self._handlers[name] = lambda statement, run=run: run(CommandContext(self, statement))
        self.reset()

    # ----- state ---------------------------------------------------------
    def reset(self):
        self.vars = {}
        self.objects = _Scene()
        self.functions = {}
        self.tests = []
        self.constants = set()
        self._focus = None
        self._dragging = None
        self._overlay_texture = None
        self.mode = "2d"
        style = getattr(self, "style", None) or game_style()
        self.activecolor = style["color"]
        self.background = color_value(style["background"])
        self.camera = Vector3(0, 0, 0)
        self.camera_turn = (0.0, 0.0)
        self.screen = None
        self.running = False
        self.http_requests = 0
        self.last_http_request = 0.0
        self.started_at = time.monotonic()
        self.audio_volume = 1.0
        self.button_label = "destroy"
        self.text_font = None
        self.text_size = 24
        self.audio_initialized = False
        self.audio_channels = []
        self.window_size = (style["width"], style["height"])
        self.window_title = style["title"] or None
        self.target_fps = style["fps"]
        self._fps_times = []
        self.current = None
        self.last_error = None
        self.finished = False
        self._prog = []
        self._depth = 0
        self._fonts = {}
        self._image_cache = {}
        self._sound_cache = {}
        self._key_cache = {}
        self._key_presses = set()
        self._mouse_presses = set()
        self._last_pump = 0.0
        self._last_frame = time.perf_counter()
        self._gl_clear = (20, 20, 20)
        self.cursor_visible = True
        self.presence = {}
        self.presence_app = ""
        self._presence_sent = None
        self._presence_warned = False
        self._saves = None
        self._saves_dirty = False
        self._saves_written = 0.0
        self._local_frames = []
        self._timers = {}
        self.scroll = (0.0, 0.0)
        self._shake = None
        self._shake_offset = (0.0, 0.0)
        self._particles = []
        self._tweens = []
        self._effects_time = time.perf_counter()
        self._alpha_layer = None
        self.gravity = 0.0
        self.light = None
        self._clicks = []
        self._frame_clicks = []
        self._frames_drawn = 0
        self._mesh_cache = {}
        self._gl_turned = False

    # ----- values ----------------------------------------------------------
    def val(self, token):
        """evaluate a single token: a variable, number, quoted text or compact expression."""
        if isinstance(token, QuotedText):
            return self._interpolate(str(token))
        if token in self.vars:
            return self.vars[token]
        if token == "true":
            return True
        if token == "false":
            return False
        if token == "none":
            return None
        if _NUMBER_RE.match(token):
            return float(token) if "." in token else int(token)
        if token.startswith("{") and token.endswith("}") and len(token) > 2:
            try:
                inner = parse_expression(token[1:-1])
            except (SyntaxError, ValueError):
                inner = None
            if inner is not None:
                return self._eval(inner, lenient=False)
        try:
            node = parse_expression(token)
        except (SyntaxError, ValueError):
            return self._interpolate(token)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                return self._interpolate(node.value)
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return node.value
            return token
        if isinstance(node, ast.Name):
            return self.vars.get(node.id, token)
        if isinstance(node, (ast.List, ast.Dict)) and not token.startswith(("[", "{")):
            return token
        return self._eval(node, lenient=True)

    def _val_text(self, token):
        """like val, but words that are not variables become plain text instead of errors."""
        try:
            value = self.val(token)
        except (UnknownName, ValueError, TypeError):
            return self._interpolate(str(token))
        return value

    def _text(self, tokens):
        """print/text arguments.

        a line that uses {braces} is a template: words stay words and only the
        braces are filled in. otherwise each word that names a variable shows
        its value (print score).
        """
        if any("{" in token and not isinstance(token, QuotedText) for token in tokens):
            return " ".join(
                self._interpolate(str(token)) for token in tokens
            )
        return " ".join(format_value(self._val_text(token)) for token in tokens)

    def _label(self, tokens):
        """literal words with {expression} interpolation (button labels, titles)."""
        return self._interpolate(" ".join(str(token) for token in tokens))

    def _num(self, token, what="value"):
        value = self.val(token)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{what} must be a number, but got '{format_value(value)}'")
        if not math.isfinite(value):
            raise ValueError(f"{what} must be a finite number")
        return value

    def _interpolate(self, text):
        if "{" not in text:
            return text

        def replace(match):
            inner = match.group(1).strip()
            if not inner:
                return match.group(0)
            try:
                node = parse_expression(inner)
            except (SyntaxError, ValueError):
                return match.group(0)  # not an expression, so the braces are just text
            # a real expression that fails (a typo'd name, dividing by zero) is reported, not printed as-is
            return format_value(self._eval(node, lenient=False))

        return _BRACE_RE.sub(replace, text)

    def _eval_value(self, raw, tokens):
        """evaluate the right-hand side of set/return: an expression, or plain text."""
        raw = raw.strip()
        if len(tokens) == 1:
            return self.val(tokens[0])
        if not tokens:
            return None
        try:
            node = parse_expression(_normalize_condition(raw) if ("&&" in raw or "||" in raw) else raw)
        except (SyntaxError, ValueError):
            return self._interpolate(" ".join(str(token) for token in tokens))
        return self._eval(node, lenient=True)

    def _lookup(self, name, lenient):
        if name in self.vars:
            return self.vars[name]
        if name == "true":
            return True
        if name == "false":
            return False
        if name in ("none", "nil", "null"):
            return None
        if name == "pi":
            return math.pi
        if name == "dt":
            return 0
        if lenient:
            return name
        if name in self.objects:
            raise UnknownName(f"'{name}' is an object, not a variable. use {name}.x or {name}.y")
        raise UnknownName(f"'{name}' is not a variable yet. set it first, like: set {name} = 0")

    def _eval(self, node, lenient=False):
        kind = type(node)
        if kind is ast.Constant:
            value = node.value
            if isinstance(value, (int, float, str)) or value is None:
                return value
            raise ValueError("that kind of value is not supported")
        if kind is ast.Name:
            return self._lookup(node.id, lenient)
        if kind is ast.BinOp:
            return self._binary(node.op, self._eval(node.left), self._eval(node.right))
        if kind is ast.UnaryOp:
            value = self._eval(node.operand, lenient=isinstance(node.op, ast.Not))
            if isinstance(node.op, ast.Not):
                return not self._truthy(value)
            if isinstance(node.op, ast.Invert):
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValueError("~ needs a whole number")
                return ~value
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                if isinstance(value, (Vector2, Vector3)) and isinstance(node.op, ast.USub):
                    return self._binary(ast.Mult(), value, -1)
                raise ValueError("a + or - sign needs a number")
            return value if isinstance(node.op, ast.UAdd) else -value
        if kind is ast.BoolOp:
            if isinstance(node.op, ast.And):
                value = True
                for item in node.values:
                    value = self._eval(item, lenient=True)
                    if not self._truthy(value):
                        return value
                return value
            value = False
            for item in node.values:
                value = self._eval(item, lenient=True)
                if self._truthy(value):
                    return value
            return value
        if kind is ast.Compare:
            left = self._eval(node.left, lenient=isinstance(node.left, ast.Name))
            for operator, comparator in zip(node.ops, node.comparators):
                right = self._eval(comparator, lenient=isinstance(comparator, ast.Name))
                if not self._compare_op(operator, left, right):
                    return False
                left = right
            return True
        if kind is ast.IfExp:
            branch = node.body if self._truthy(self._eval(node.test, lenient=True)) else node.orelse
            return self._eval(branch, lenient)
        if kind is ast.Attribute:
            return self._attribute(node)
        if kind is ast.Subscript:
            container = self._eval(node.value)
            if isinstance(node.slice, ast.Slice):
                lower = self._eval(node.slice.lower) if node.slice.lower else None
                upper = self._eval(node.slice.upper) if node.slice.upper else None
                return container[lower:upper]
            index = self._eval(node.slice, lenient=isinstance(container, dict))
            return self._index(container, index)
        if kind is ast.Call:
            return self._call_expression(node)
        if kind is ast.Lambda:
            return GublanLambda([argument.arg for argument in node.args.args], node.body)
        if kind is ast.ListComp or kind is ast.DictComp:
            return self._comprehension(node)
        if kind is ast.List:
            return [self._eval(item, lenient=True) for item in node.elts]
        if kind is ast.Dict:
            return {
                format_value(self._eval(key, lenient=True)): self._eval(value, lenient=True)
                for key, value in zip(node.keys, node.values)
            }
        if kind is ast.Tuple:
            return " ".join(format_value(self._eval(item, lenient=lenient)) for item in node.elts)
        if kind is ast.JoinedStr:
            out = []
            for piece in node.values:
                if isinstance(piece, ast.Constant):
                    out.append(str(piece.value))
                else:
                    value = self._eval(piece.value)
                    spec = self._eval(piece.format_spec) if piece.format_spec else ""
                    out.append(format(value, spec) if spec else format_value(value))
            return "".join(out)
        raise ValueError("use numbers, variables, text and + - * / in expressions")

    def _binary(self, operator, left, right):
        vector = (Vector2, Vector3)
        if isinstance(operator, ast.Add):
            if isinstance(left, str) or isinstance(right, str):
                return format_value(left) + format_value(right)
            if isinstance(left, list) and isinstance(right, list):
                return left + right
        if isinstance(left, vector) or isinstance(right, vector):
            return self._vector_math(operator, left, right)
        if isinstance(operator, ast.Mult) and isinstance(left, (str, list)) and isinstance(right, int):
            if len(left) * max(right, 0) > 1_000_000:
                raise ValueError("that text or list would be too large")
            return left * right
        numbers = (int, float)
        if not isinstance(left, numbers) or not isinstance(right, numbers):
            raise ValueError(
                f"can't do math with {kind_of(left)} '{format_value(left)}' and "
                f"{kind_of(right)} '{format_value(right)}'"
            )
        if isinstance(operator, ast.Pow) and abs(right) > 1000:
            raise ValueError("use an exponent between -1000 and 1000")
        if isinstance(operator, (ast.BitAnd, ast.BitOr, ast.BitXor, ast.LShift, ast.RShift)):
            if isinstance(left, float) and left.is_integer():
                left = int(left)
            if isinstance(right, float) and right.is_integer():
                right = int(right)
            if isinstance(left, bool) or isinstance(right, bool) or not isinstance(left, int) \
                    or not isinstance(right, int):
                raise ValueError("&, |, ^, << and >> need whole numbers")
            if isinstance(operator, (ast.LShift, ast.RShift)) and not 0 <= right <= 64:
                raise ValueError("shift by 0 to 64 places")
            if isinstance(operator, ast.BitAnd):
                return left & right
            if isinstance(operator, ast.BitOr):
                return left | right
            if isinstance(operator, ast.BitXor):
                return left ^ right
            return left << right if isinstance(operator, ast.LShift) else left >> right
        try:
            if isinstance(operator, ast.Add):
                result = left + right
            elif isinstance(operator, ast.Sub):
                result = left - right
            elif isinstance(operator, ast.Mult):
                result = left * right
            elif isinstance(operator, ast.Div):
                result = left / right
            elif isinstance(operator, ast.FloorDiv):
                result = left // right
            elif isinstance(operator, ast.Mod):
                result = left % right
            elif isinstance(operator, ast.Pow):
                result = left ** right
            else:
                raise ValueError("that operator is not supported")
        except ZeroDivisionError as err:
            raise ValueError("cannot divide by zero") from err
        except OverflowError as err:
            raise ValueError("the expression result is too large") from err
        if isinstance(result, float) and not math.isfinite(result):
            raise ValueError("the expression result is too large")
        if isinstance(result, complex):
            raise ValueError("that math has no real answer")
        return result

    @staticmethod
    def _components(value):
        return (value.x, value.y) if isinstance(value, Vector2) else (value.x, value.y, value.z)

    def _vector_math(self, operator, left, right):
        vector = (Vector2, Vector3)
        if isinstance(operator, (ast.Add, ast.Sub)):
            if type(left) is not type(right):
                raise ValueError("vector addition and subtraction need matching vec2 or vec3 values")
            sign = 1 if isinstance(operator, ast.Add) else -1
            return type(left)(*(a + sign * b for a, b in zip(self._components(left), self._components(right))))
        if isinstance(operator, ast.Mult):
            if isinstance(left, vector) and isinstance(right, (int, float)) and not isinstance(right, bool):
                return type(left)(*(component * right for component in self._components(left)))
            if isinstance(right, vector) and isinstance(left, (int, float)) and not isinstance(left, bool):
                return type(right)(*(component * left for component in self._components(right)))
        if isinstance(operator, ast.Div) and isinstance(left, vector):
            if not isinstance(right, (int, float)) or right == 0:
                raise ValueError("a vector can only be divided by a nonzero number")
            return type(left)(*(component / right for component in self._components(left)))
        raise ValueError("use matching numbers or vectors in this expression")

    def _compare_op(self, operator, left, right):
        if isinstance(operator, ast.Eq):
            return self._equal(left, right)
        if isinstance(operator, ast.NotEq):
            return not self._equal(left, right)
        if isinstance(operator, (ast.In, ast.NotIn)):
            if isinstance(right, (list, dict)):
                found = left in right
            elif isinstance(right, str):
                found = format_value(left) in right
            else:
                raise ValueError("'in' needs a list, map or text on the right")
            return found if isinstance(operator, ast.In) else not found
        numbers = (int, float)
        if not ((isinstance(left, numbers) and isinstance(right, numbers))
                or (isinstance(left, str) and isinstance(right, str))):
            raise ValueError(
                f"can't compare {kind_of(left)} '{format_value(left)}' with "
                f"{kind_of(right)} '{format_value(right)}'"
            )
        if isinstance(operator, ast.Lt):
            return left < right
        if isinstance(operator, ast.LtE):
            return left <= right
        if isinstance(operator, ast.Gt):
            return left > right
        return left >= right

    @staticmethod
    def _equal(left, right):
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left == right
        return type(left) is type(right) and left == right

    def _compare(self, left, operator, right):
        if operator in ("=", "==", "!="):
            same = self._equal(left, right)
            return same if operator != "!=" else not same
        if type(left) is not type(right) and not (
            type(left) in (int, float) and type(right) in (int, float)
        ):
            raise ValueError(
                f"can't compare {kind_of(left)} '{format_value(left)}' with "
                f"{kind_of(right)} '{format_value(right)}'. compare values of the same kind"
            )
        if operator in ("=", "=="):
            return left == right
        if operator == "!=":
            return left != right
        if operator == ">":
            return left > right
        if operator == "<":
            return left < right
        if operator == ">=":
            return left >= right
        if operator == "<=":
            return left <= right
        raise ValueError("use =, ==, !=, >, <, >=, or <= for comparisons")

    @staticmethod
    def _truthy(value):
        if isinstance(value, (Vector2, Vector3)):
            return True
        return bool(value)

    def _attribute(self, node):
        field = node.attr
        if isinstance(node.value, ast.Name):
            name = node.value.id
            if name in self.vars:
                base = self.vars[name]
            elif name in self.objects or ("button:" + name) in self.objects:
                return self._object_field(name, field)
            else:
                raise UnknownName(f"'{name}' is not a variable or object yet")
        else:
            base = self._eval(node.value)
        if isinstance(base, (Vector2, Vector3)):
            if field not in ("x", "y", "z") or not hasattr(base, field):
                raise ValueError(f"this vector has no '{field}' part")
            return getattr(base, field)
        if isinstance(base, dict):
            if field not in base:
                raise ValueError(f"the map has no key '{field}'")
            return base[field]
        if isinstance(base, list) and field in ("length", "size", "count"):
            return len(base)
        if isinstance(base, str) and field == "length":
            return len(base)
        if isinstance(base, str) and (base in self.objects or ("button:" + base) in self.objects):
            # a variable that holds an object's name: for rock in rocks ... rock.y
            return self._object_field(base, field)
        raise ValueError(f"'{format_value(base)}' has no '{field}'")

    _FIELD_ALIASES = {"width": "w", "height": "h", "radius": "r", "rotation": "angle", "depth": "d"}

    def _object_field(self, name, field):
        obj = self.objects.get(name) or self.objects.get("button:" + name)
        if obj is None or not isinstance(obj, dict):
            raise ValueError(f"there is no object named '{name}'")
        field = self._FIELD_ALIASES.get(field, field)
        if field == "visible":
            return not obj.get("hidden", False)
        if field == "focused":
            return self._focus == name
        if field == "submitted" and obj["type"] == "textbox":
            was, obj["submitted"] = obj["submitted"], False
            return was
        if field in ("cursor", "anchor", "whole"):
            raise ValueError(f"object '{name}' has no '{field}'")
        if field in ("w", "h") and "surface" in obj and field not in obj:
            width, height = obj["surface"].get_size()
            return width if field == "w" else height
        if obj["type"] == "sphere" and field == "r":
            return obj["radius"]
        if obj["type"] == "cube" and field in ("w", "h", "d"):
            return obj["size"]
        if obj["type"] == "circle" and field in ("w", "h"):
            return obj["r"] * 2
        if obj["type"] in ("cylinder", "cone") and field in ("w", "d"):
            return obj["r"] * 2
        if field in ("vx", "vy", "vz") and "x" in obj:
            return obj.get(field, 0)
        if field in ("rx", "rz") and obj["type"] in SHAPES_3D:
            return obj.get(field, 0)
        if field in obj and field not in ("surface", "source", "texture"):
            return obj[field]
        raise ValueError(f"object '{name}' has no '{field}'")

    def _index(self, container, index):
        if isinstance(container, dict):
            key = format_value(index)
            if key not in container:
                raise ValueError(f"the map has no key '{key}'")
            return container[key]
        if isinstance(container, (list, str)):
            if isinstance(index, bool) or not isinstance(index, (int, float)) or int(index) != index:
                raise ValueError("list positions must be whole numbers")
            try:
                return container[int(index)]
            except IndexError as err:
                raise ValueError(f"position {format_value(index)} is past the end (length {len(container)})") from err
        raise ValueError(f"can't take an item from {kind_of(container)} '{format_value(container)}'")

    def _call_expression(self, node):
        if node.keywords:
            raise ValueError("call functions by name, like: max(a, b)")
        func = node.func
        if isinstance(func, ast.Attribute):
            # name.upper() is the same as upper(name), and a map can hold little functions: tools.double(3)
            base = self._eval(func.value, lenient=False)
            args = [self._eval(argument, lenient=isinstance(argument, ast.Name)) for argument in node.args]
            if isinstance(base, dict) and func.attr in base:
                return self._call_value(base[func.attr], args)
            return self._call_named(func.attr, [base] + args)
        if not isinstance(func, ast.Name):
            value = self._eval(func)
            return self._call_value(value, [self._eval(argument, lenient=isinstance(argument, ast.Name))
                                            for argument in node.args])
        name = func.id
        args = [self._eval(argument, lenient=isinstance(argument, ast.Name)) for argument in node.args]
        held = self.vars.get(name)
        if isinstance(held, GublanLambda):
            return self._call_value(held, args)
        if isinstance(held, str) and name not in self.functions and held in self.functions:
            # a function handed over by name: function apply f v / return f(v) / end ... apply(double, 3)
            return self._call_value(held, args)
        return self._call_named(name, args)

    def _call_named(self, name, args):
        if name in self.functions:
            return self._call_function(name, args)
        return self._builtin(name, args)

    def _call_value(self, value, args):
        """call a function value: a little function, or the name of a function."""
        if isinstance(value, GublanLambda):
            if len(args) != len(value.params):
                raise ValueError(f"{value!r} needs {len(value.params)} value(s), got {len(args)}")
            if self._depth >= 180:
                raise ValueError("functions are calling each other too deeply (limit 180)")
            saved = {name: (name in self.vars, self.vars.get(name)) for name in value.params}
            self.vars.update(zip(value.params, args))
            self._depth += 1
            try:
                return self._eval(value.body, lenient=False)
            finally:
                self._depth -= 1
                self._restore_names(saved)
        if isinstance(value, str) and (value in self.functions or value in EXPRESSION_FUNCTIONS
                                       or value in _PLUGIN_FUNCTIONS):
            return self._call_named(value, list(args))
        raise ValueError(f"'{format_value(value)}' is not a function. use a name, or a little function like "
                         "x => x * 2")

    def _restore_names(self, saved):
        for name, (was_defined, old_value) in saved.items():
            if was_defined:
                self.vars[name] = old_value
            else:
                self.vars.pop(name, None)

    def _comprehension(self, node):
        """[x * 2 for x in items if x > 0] and {k: v for k in keys}"""
        names = set()
        for generator in node.generators:
            for target in ast.walk(generator.target):
                if isinstance(target, ast.Name):
                    names.add(target.id)
                elif not isinstance(target, (ast.Tuple, ast.List, ast.Store)):
                    raise ValueError("use plain names in a for inside brackets, like: [x * 2 for x in items]")
        saved = {name: (name in self.vars, self.vars.get(name)) for name in names}
        out = {} if isinstance(node, ast.DictComp) else []
        made = [0]

        def bind(target, value):
            if isinstance(target, ast.Name):
                self.vars[target.id] = value
                return
            items = list(value) if isinstance(value, (list, str)) else None
            if items is None or len(items) != len(target.elts):
                raise ValueError(f"can't split '{format_value(value)}' into {len(target.elts)} names")
            for part, item in zip(target.elts, items):
                bind(part, item)

        def walk(level):
            if level == len(node.generators):
                made[0] += 1
                if made[0] > 1_000_000:
                    raise ValueError("that list would be too large")
                if isinstance(node, ast.DictComp):
                    out[format_value(self._eval(node.key, lenient=True))] = self._eval(node.value, lenient=True)
                else:
                    out.append(self._eval(node.elt, lenient=True))
                return
            generator = node.generators[level]
            source = self._eval(generator.iter)
            if isinstance(source, dict):
                items = list(source.keys())
            elif isinstance(source, (list, str)):
                items = list(source)
            elif isinstance(source, (int, float)) and not isinstance(source, bool):
                items = list(range(int(source)))
            else:
                raise ValueError(f"can't go through {kind_of(source)} '{format_value(source)}' with for")
            for item in items:
                bind(generator.target, item)
                if all(self._truthy(self._eval(test, lenient=True)) for test in generator.ifs):
                    walk(level + 1)

        try:
            walk(0)
        finally:
            self._restore_names(saved)
        return out

    def _builtin(self, name, args):
        def number(value, label="value"):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name}() needs a number for its {label}, got '{format_value(value)}'")
            return value

        def need(count):
            if len(args) != count:
                raise ValueError(f"{name}() needs {count} value(s), got {len(args)}")

        if name in ("vec2", "vec3"):
            size = 2 if name == "vec2" else 3
            if len(args) != size:
                raise ValueError("use vec2(x, y) or vec3(x, y, z)")
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in args):
                raise ValueError("vector components must be finite numbers")
            return (Vector2 if size == 2 else Vector3)(*args)
        if name == "abs":
            need(1)
            if isinstance(args[0], (Vector2, Vector3)):
                return math.sqrt(sum(c * c for c in self._components(args[0])))
            return abs(number(args[0]))
        if name in ("min", "max"):
            values = args[0] if len(args) == 1 and isinstance(args[0], list) else args
            if not values:
                raise ValueError(f"{name}() needs at least one value")
            return (min if name == "min" else max)(values)
        if name == "round":
            value = number(args[0]) if args else 0
            digits = int(number(args[1], "digits")) if len(args) > 1 else 0
            if digits:
                return round(value, digits)
            return int(math.floor(value + 0.5))
        if name in ("floor", "ceil"):
            need(1)
            return (math.floor if name == "floor" else math.ceil)(number(args[0]))
        if name == "sqrt":
            need(1)
            if number(args[0]) < 0:
                raise ValueError("sqrt() needs a number that is zero or more")
            return math.sqrt(args[0])
        if name in ("sin", "cos", "tan"):
            need(1)
            radians = math.radians(number(args[0], "angle"))
            return {"sin": math.sin, "cos": math.cos, "tan": math.tan}[name](radians)
        if name in ("asin", "acos", "atan"):
            need(1)
            return math.degrees({"asin": math.asin, "acos": math.acos, "atan": math.atan}[name](number(args[0])))
        if name == "atan2":
            need(2)
            return math.degrees(math.atan2(number(args[0], "y"), number(args[1], "x")))
        if name == "rad":
            need(1)
            return math.radians(number(args[0]))
        if name == "deg":
            need(1)
            return math.degrees(number(args[0]))
        if name == "clamp":
            need(3)
            return max(number(args[1], "low"), min(number(args[2], "high"), number(args[0])))
        if name == "lerp":
            need(3)
            return args[0] + (args[1] - args[0]) * number(args[2], "amount")
        if name == "sign":
            need(1)
            value = number(args[0])
            return (value > 0) - (value < 0)
        if name == "dist":
            if len(args) == 2 and all(isinstance(v, (Vector2, Vector3)) for v in args):
                return math.dist(self._components(args[0]), self._components(args[1]))
            need(4)
            return math.dist((number(args[0]), number(args[1])), (number(args[2]), number(args[3])))
        if name == "mag":
            need(1)
            if not isinstance(args[0], (Vector2, Vector3)):
                raise ValueError("mag() needs a vec2 or vec3")
            return math.sqrt(sum(c * c for c in self._components(args[0])))
        if name in ("len", "length"):
            need(1)
            if not isinstance(args[0], (str, list, dict)):
                raise ValueError("len() needs text, a list or a map")
            return len(args[0])
        if name in ("str", "string", "text"):
            need(1)
            return format_value(args[0])
        if name in ("num", "float", "number"):
            need(1)
            if isinstance(args[0], (int, float)) and not isinstance(args[0], bool):
                return args[0]
            try:
                text = str(args[0]).strip()
                return int(text) if re.fullmatch(r"-?\d+", text) else float(text)
            except ValueError as err:
                raise ValueError(f"'{format_value(args[0])}' is not a number") from err
        if name == "int":
            need(1)
            value = self._builtin("num", args) if isinstance(args[0], str) else number(args[0])
            return int(value)
        if name in ("upper", "lower", "trim"):
            need(1)
            text = format_value(args[0])
            return text.upper() if name == "upper" else text.lower() if name == "lower" else text.strip()
        if name == "contains":
            need(2)
            container, item = args
            if isinstance(container, str):
                return format_value(item) in container
            if isinstance(container, (list, dict)):
                return item in container
            raise ValueError("contains() needs a list, map or text first")
        if name == "join":
            items = args[0] if args else []
            separator = format_value(args[1]) if len(args) > 1 else " "
            if not isinstance(items, list):
                raise ValueError("join() needs a list first")
            return separator.join(format_value(item) for item in items)
        if name == "split":
            text = format_value(args[0]) if args else ""
            separator = format_value(args[1]) if len(args) > 1 else None
            return text.split(separator) if separator else text.split()
        if name == "replace":
            need(3)
            return format_value(args[0]).replace(format_value(args[1]), format_value(args[2]))
        if name == "random":
            if not args:
                return random.random()
            need(2)
            low, high = number(args[0], "minimum"), number(args[1], "maximum")
            if low > high:
                low, high = high, low
            if isinstance(low, int) and isinstance(high, int):
                return random.randint(low, high)
            return random.uniform(low, high)
        if name == "choice":
            need(1)
            if not isinstance(args[0], list) or not args[0]:
                raise ValueError("choice() needs a list with items")
            return random.choice(args[0])
        if name == "range":
            if len(args) == 1:
                start, stop, step = 0, int(number(args[0])), 1
            elif len(args) in (2, 3):
                start, stop = int(number(args[0])), int(number(args[1]))
                step = int(number(args[2])) if len(args) == 3 else 1
            else:
                raise ValueError("use range(end), range(start, end) or range(start, end, step)")
            if step == 0:
                raise ValueError("range() step cannot be zero")
            if abs((stop - start) // step) > 1_000_000:
                raise ValueError("that range is too large")
            return list(range(start, stop, step))
        if name == "keydown":
            need(1)
            self._require_screen("check the keyboard")
            return bool(pygame.key.get_pressed()[self._keycode(args[0])])
        if name == "keypressed":
            need(1)
            self._require_screen("check the keyboard")
            return self._consume_press(self._keycode(args[0]))
        if name == "mousedown":
            self._require_screen("check the mouse")
            button = {"left": 0, "middle": 1, "right": 2}.get(format_value(args[0]).lower() if args else "left")
            if button is None:
                raise ValueError("mousedown() expects left, middle, or right")
            return bool(pygame.mouse.get_pressed(3)[button])
        if name == "mousepressed":
            self._require_screen("check the mouse")
            button = {"left": 1, "middle": 2, "right": 3}.get(format_value(args[0]).lower() if args else "left")
            if button is None:
                raise ValueError("mousepressed() expects left, middle, or right")
            self.pumpevents()
            if button in self._mouse_presses:
                self._mouse_presses.discard(button)
                return True
            return False
        if name in ("mousex", "mousey"):
            self._require_screen("check the mouse")
            return pygame.mouse.get_pos()[0 if name == "mousex" else 1]
        if name == "touching":
            need(2)
            return self._objects_touching(format_value(args[0]), format_value(args[1]))
        if name == "exists":
            need(1)
            key = format_value(args[0])
            return key in self.objects or key in self.vars or ("button:" + key) in self.objects
        if name == "time":
            return time.monotonic() - self.started_at
        if name == "type":
            need(1)
            return kind_of(args[0])
        if name == "pow":
            need(2)
            return self._binary(ast.Pow(), number(args[0]), number(args[1]))
        if name in ("sum", "sort", "reverse"):
            need(1)
            if not isinstance(args[0], list):
                raise ValueError(f"{name}() needs a list")
            if name == "sum":
                return sum(number(item, "items") for item in args[0])
            if name == "reverse":
                return list(reversed(args[0]))
            try:
                return sorted(args[0])
            except TypeError as err:
                raise ValueError("sort() needs a list of all numbers or all text") from err
        if name in ("keys", "values"):
            need(1)
            if not isinstance(args[0], dict):
                raise ValueError(f"{name}() needs a map")
            return list(args[0].keys() if name == "keys" else args[0].values())
        if name == "indexof":
            need(2)
            container, item = args
            if isinstance(container, str):
                return container.find(format_value(item))
            if not isinstance(container, list):
                raise ValueError("indexof() needs a list or text first")
            return container.index(item) if item in container else -1
        if name == "overlap":
            need(2)
            first, second = (self._rect_of(value) for value in args)
            return (first[0] < second[0] + second[2] and second[0] < first[0] + first[2]
                    and first[1] < second[1] + second[3] and second[1] < first[1] + first[3])
        if name == "chance":
            need(1)
            return random.random() * 100 < number(args[0], "percent")
        if name in ("shuffle", "unique", "average"):
            need(1)
            if not isinstance(args[0], list):
                raise ValueError(f"{name}() needs a list")
            if name == "shuffle":
                mixed = list(args[0])
                random.shuffle(mixed)
                return mixed
            if name == "unique":
                kept = []
                for item in args[0]:
                    if item not in kept:
                        kept.append(item)
                return kept
            if not args[0]:
                raise ValueError("average() needs a list with numbers in it")
            values = [number(item, "items") for item in args[0]]
            return sum(values) / len(values)
        if name == "count":
            need(2)
            container, item = args
            if isinstance(container, str):
                part = format_value(item)
                return container.count(part) if part else 0
            if isinstance(container, list):
                return sum(1 for value in container if value == item)
            raise ValueError("count() needs a list or text first")
        if name in ("startswith", "endswith"):
            need(2)
            text, part = format_value(args[0]), format_value(args[1])
            return text.startswith(part) if name == "startswith" else text.endswith(part)
        if name == "pad":
            if len(args) not in (2, 3):
                raise ValueError("use pad(value, width) or pad(value, width, fill)")
            width = int(number(args[1], "width"))
            if width > 1000:
                raise ValueError("pad() can make text up to 1000 letters long")
            fill = format_value(args[2]) if len(args) == 3 else " "
            if len(fill) != 1:
                raise ValueError("pad() fills with a single letter or digit")
            text = format_value(args[0])
            if fill == "0" and text.startswith("-"):
                return "-" + text[1:].rjust(width - 1, "0")
            return text.rjust(width, fill)
        if name == "decimals":
            need(2)
            digits = int(number(args[1], "digits"))
            if not 0 <= digits <= 20:
                raise ValueError("decimals() can show from 0 to 20 digits")
            return f"{number(args[0]):.{digits}f}"
        if name == "wrap":
            need(3)
            value, low, high = number(args[0]), number(args[1], "low"), number(args[2], "high")
            if high <= low:
                raise ValueError("wrap() needs high to be bigger than low")
            return low + (value - low) % (high - low)
        if name == "remap":
            need(5)
            value, low1, high1, low2, high2 = (number(item) for item in args)
            if low1 == high1:
                raise ValueError("remap() needs the first range to have two different ends")
            return low2 + (value - low1) * (high2 - low2) / (high1 - low1)
        if name == "approach":
            need(3)
            value, target, step = number(args[0]), number(args[1], "target"), abs(number(args[2], "step"))
            return min(value + step, target) if value < target else max(value - step, target)
        if name == "angleto":
            if len(args) == 2 and all(isinstance(v, (Vector2, Vector3)) for v in args):
                (x1, y1), (x2, y2) = self._components(args[0])[:2], self._components(args[1])[:2]
            else:
                need(4)
                x1, y1, x2, y2 = (number(item) for item in args)
            return math.degrees(math.atan2(y2 - y1, x2 - x1))
        if name == "hsv":
            need(3)
            hue = number(args[0], "hue") % 360
            saturation = max(0.0, min(1.0, number(args[1], "saturation")))
            brightness = max(0.0, min(1.0, number(args[2], "value")))
            return [int(round(channel * 255)) for channel in colorsys.hsv_to_rgb(hue / 360, saturation, brightness)]
        if name == "isnumber":
            need(1)
            value = args[0]
            if isinstance(value, bool):
                return False
            if isinstance(value, (int, float)):
                return True
            return isinstance(value, str) and bool(re.fullmatch(r"\s*-?(?:\d+\.?\d*|\.\d+)\s*", value))
        if name in ("date", "clock", "now"):
            if args:
                raise ValueError(f"{name}() does not take any values")
            if name == "now":
                return time.time()
            return time.strftime("%Y-%m-%d" if name == "date" else "%H:%M")
        if name == "saved":
            need(1)
            return self._save_key(args[0]) in self._saves_data()
        if name == "load":
            if len(args) not in (1, 2):
                raise ValueError('use load("name") or load("name", default)')
            saves = self._saves_data()
            key = self._save_key(args[0])
            if key in saves:
                return self._restored(saves[key])
            return args[1] if len(args) == 2 else 0
        extra = self._builtin_extra(name, args, number, need)
        if extra is not _MISSING:
            return extra
        if name in _PLUGIN_FUNCTIONS:
            try:
                return _PLUGIN_FUNCTIONS[name](*args)
            except (ValueError, TypeError) as err:
                raise ValueError(f"{name}(): {err}") from err
        raise ValueError(f"there is no function named '{name}'")

    def _builtin_extra(self, name, args, number, need):
        """the functions added in 1.0.5: lists and functions as values, text helpers and a little more math."""
        def sequence(value, label="list"):
            if isinstance(value, dict):
                return list(value.keys())
            if not isinstance(value, (list, str)):
                raise ValueError(f"{name}() needs a {label}, got '{format_value(value)}'")
            return list(value)

        def between(low, high):
            if not low <= len(args) <= high:
                raise ValueError(f"{name}() needs {low} to {high} values, got {len(args)}")

        if name in ("map", "filter", "find", "sortby"):
            need(2)
            items, function = sequence(args[0]), args[1]
            if name == "map":
                return [self._call_value(function, [item]) for item in items]
            if name == "filter":
                return [item for item in items if self._truthy(self._call_value(function, [item]))]
            if name == "find":
                for item in items:
                    if self._truthy(self._call_value(function, [item])):
                        return item
                return None
            keyed = [(self._call_value(function, [item]), index, item) for index, item in enumerate(items)]
            try:
                keyed.sort(key=lambda entry: (entry[0], entry[1]))
            except TypeError as err:
                raise ValueError("sortby() needs the function to give values of the same kind") from err
            return [item for _key, _index, item in keyed]
        if name == "reduce":
            between(2, 3)
            items = sequence(args[0])
            if len(args) == 2:
                if not items:
                    raise ValueError("reduce() of an empty list needs a start value")
                total, items = items[0], items[1:]
            else:
                total = args[2]
            for item in items:
                total = self._call_value(args[1], [total, item])
            return total
        if name in ("any", "every"):
            between(1, 2)
            items = sequence(args[0])
            test = (lambda item: self._truthy(self._call_value(args[1], [item]))) if len(args) == 2 \
                else self._truthy
            return any(test(item) for item in items) if name == "any" else all(test(item) for item in items)
        if name == "zip":
            if len(args) < 2:
                raise ValueError("zip() needs at least two lists")
            return [list(group) for group in zip(*(sequence(arg) for arg in args))]
        if name == "slice":
            between(2, 3)
            if not isinstance(args[0], (list, str)):
                raise ValueError(f"slice() needs a list or text, got '{format_value(args[0])}'")
            start = int(number(args[1], "start"))
            end = int(number(args[2], "end")) if len(args) == 3 else None
            return args[0][start:end]
        if name == "flat":
            need(1)
            out = []
            for item in sequence(args[0]):
                out.extend(item if isinstance(item, list) else [item])
            return out
        if name == "repeat":
            need(2)
            times = int(number(args[1], "times"))
            value = args[0] if isinstance(args[0], (list, str)) else format_value(args[0])
            if len(value) * max(times, 0) > 1_000_000:
                raise ValueError("that text or list would be too large")
            return value * max(times, 0)
        if name == "call":
            if not args:
                raise ValueError("call() needs a function, then its values")
            return self._call_value(args[0], args[1:])
        if name == "capitalize":
            need(1)
            return re.sub(r"\b([a-z])", lambda match: match.group(1).upper(), format_value(args[0]))
        if name == "lines":
            need(1)
            return format_value(args[0]).splitlines()
        if name == "words":
            need(1)
            return format_value(args[0]).split()
        if name == "char":
            need(1)
            code = int(number(args[0], "code"))
            if not 0 <= code <= 0x10FFFF:
                raise ValueError("char() needs a code from 0 to 1114111")
            return chr(code)
        if name == "code":
            need(1)
            text = format_value(args[0])
            if len(text) != 1:
                raise ValueError("code() needs exactly one letter")
            return ord(text)
        if name == "tojson":
            need(1)
            return json.dumps(self._storable(args[0]))
        if name == "fromjson":
            need(1)
            try:
                return self._restored(json.loads(format_value(args[0])))
            except (json.JSONDecodeError, RecursionError) as err:
                raise ValueError("fromjson() got text that isn't json") from err
        if name == "textwidth":
            between(1, 2)
            size = int(number(args[1], "size")) if len(args) == 2 else self.text_size
            if not pygame.font.get_init():
                pygame.font.init()
            return self._font(size).size(format_value(args[0]))[0]
        if name == "log":
            between(1, 2)
            value = number(args[0])
            if value <= 0:
                raise ValueError("log() needs a number above 0")
            if len(args) == 2:
                base = number(args[1], "base")
                if base <= 0 or base == 1:
                    raise ValueError("log() needs a base above 0 that isn't 1")
                return math.log(value, base)
            return math.log(value)
        if name == "exp":
            need(1)
            try:
                return math.exp(number(args[0]))
            except OverflowError as err:
                raise ValueError("the expression result is too large") from err
        if name == "noise":
            between(1, 2)
            x = number(args[0], "x")
            y = number(args[1], "y") if len(args) == 2 else 0.0
            return _value_noise(x, y)
        if name == "randint":
            need(2)
            low, high = int(number(args[0], "low")), int(number(args[1], "high"))
            if low > high:
                low, high = high, low
            return random.randint(low, high)
        return self._builtin_more(name, args, number, need)

    def _builtin_more(self, name, args, number, need):
        """the functions added in 1.0.7: more math, list and map helpers, text formatting, colours and timers."""
        def between(low, high):
            if not low <= len(args) <= high:
                raise ValueError(f"{name}() needs {low} to {high} values, got {len(args)}")

        def listed(value, label="list"):
            if isinstance(value, str):
                return list(value)
            if not isinstance(value, list):
                raise ValueError(f"{name}() needs a {label}, got '{format_value(value)}'")
            return value

        def mapping(value):
            if not isinstance(value, dict):
                raise ValueError(f"{name}() needs a map, got '{format_value(value)}'")
            return value

        def whole(value, label="count"):
            value = number(value, label)
            if value != int(value):
                raise ValueError(f"{name}() needs a whole number for its {label}")
            return int(value)

        if name == "hypot":
            need(2)
            return math.hypot(number(args[0], "x"), number(args[1], "y"))
        if name == "fract":
            need(1)
            value = number(args[0])
            return value - math.floor(value)
        if name == "smoothstep":
            need(3)
            low, high, value = (number(arg) for arg in args)
            if high == low:
                return 0.0 if value < low else 1.0
            t = max(0.0, min(1.0, (value - low) / (high - low)))
            return t * t * (3 - 2 * t)
        if name == "snap":
            need(2)
            value, step = number(args[0]), number(args[1], "step")
            if step == 0:
                return value
            snapped = math.floor(value / step + 0.5) * step
            return int(snapped) if isinstance(value, int) and isinstance(step, int) else snapped
        if name == "between":
            need(3)
            value, low, high = (number(arg) for arg in args)
            return low <= value <= high
        if name == "ease":
            between(1, 2)
            return ease_value(number(args[0], "amount"), args[1] if len(args) > 1 else "inout")
        if name == "gcd":
            need(2)
            return math.gcd(whole(args[0], "first number"), whole(args[1], "second number"))
        if name in ("median", "product"):
            need(1)
            items = [number(item, "items") for item in listed(args[0])]
            if name == "product":
                return math.prod(items)
            if not items:
                raise ValueError("median() of an empty list has no middle")
            items = sorted(items)
            middle = len(items) // 2
            return items[middle] if len(items) % 2 else (items[middle - 1] + items[middle]) / 2
        if name in ("first", "last"):
            need(1)
            items = listed(args[0])
            return (items[0] if name == "first" else items[-1]) if items else None
        if name in ("take", "drop"):
            need(2)
            items, count = args[0], max(0, whole(args[1]))
            if not isinstance(items, (list, str)):
                raise ValueError(f"{name}() needs a list or text, got '{format_value(items)}'")
            return items[:count] if name == "take" else items[count:]
        if name == "chunk":
            need(2)
            items, size = listed(args[0]), whole(args[1], "size")
            if size < 1:
                raise ValueError("chunk() needs a size of 1 or more")
            return [items[index:index + size] for index in range(0, len(items), size)]
        if name == "enumerate":
            need(1)
            return [[index, item] for index, item in enumerate(listed(args[0]))]
        if name in ("minby", "maxby"):
            need(2)
            items = listed(args[0])
            if not items:
                return None
            best, best_key = items[0], self._call_value(args[1], [items[0]])
            for item in items[1:]:
                key = self._call_value(args[1], [item])
                try:
                    better = key < best_key if name == "minby" else key > best_key
                except TypeError as err:
                    raise ValueError(f"{name}() needs the function to give values of the same kind") from err
                if better:
                    best, best_key = item, key
            return best
        if name == "groupby":
            need(2)
            groups = {}
            for item in listed(args[0]):
                groups.setdefault(format_value(self._call_value(args[1], [item])), []).append(item)
            return groups
        if name == "without":
            need(2)
            return [item for item in listed(args[0]) if not self._equal(item, args[1])]
        if name == "fill":
            need(2)
            count = whole(args[1])
            if not 0 <= count <= 1_000_000:
                raise ValueError("fill() can make lists of up to a million items")
            value = args[0]
            return [list(value) if isinstance(value, list) else dict(value) if isinstance(value, dict) else value
                    for _ in range(count)]
        if name == "merge":
            need(2)
            merged = dict(mapping(args[0]))
            merged.update(mapping(args[1]))
            return merged
        if name == "get":
            between(2, 3)
            container, key = args[0], args[1]
            default = args[2] if len(args) > 2 else None
            if isinstance(container, dict):
                if key in container:
                    return container[key]
                text = format_value(key)
                return container.get(text, default)
            if isinstance(container, (list, str)):
                if isinstance(key, bool) or not isinstance(key, (int, float)) or key != int(key):
                    return default
                index = int(key)
                return container[index] if -len(container) <= index < len(container) else default
            raise ValueError(f"get() needs a map or a list, got '{format_value(container)}'")
        if name == "entries":
            need(1)
            return [[key, value] for key, value in mapping(args[0]).items()]
        if name == "frompairs":
            need(1)
            made = {}
            for pair in listed(args[0]):
                if not isinstance(pair, list) or len(pair) != 2:
                    raise ValueError("frompairs() needs a list of [name, value] pairs")
                made[pair[0] if isinstance(pair[0], str) else format_value(pair[0])] = pair[1]
            return made
        if name == "commas":
            need(1)
            value = number(args[0])
            text = format_value(value)
            sign = "-" if text.startswith("-") else ""
            digits, dot, rest = text.lstrip("-").partition(".")
            if not digits.isdigit():
                return text
            grouped = f"{int(digits):,}"
            return sign + grouped + (dot + rest if dot else "")
        if name == "ordinal":
            need(1)
            value = whole(args[0], "number")
            last_two = abs(value) % 100
            suffix = "th" if 11 <= last_two <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(abs(value) % 10, "th")
            return f"{value}{suffix}"
        if name == "plural":
            between(2, 3)
            count = number(args[0])
            word = format_value(args[1])
            many = format_value(args[2]) if len(args) > 2 else word + "s"
            return f"{format_value(count)} {word if count == 1 else many}"
        if name == "wraptext":
            need(2)
            width = whole(args[1], "width")
            if width < 1:
                raise ValueError("wraptext() needs a width of 1 or more")
            lines = []
            for paragraph in format_value(args[0]).split("\n"):
                line = ""
                for word in paragraph.split():
                    while len(word) > width:
                        if line:
                            lines.append(line)
                            line = ""
                        lines.append(word[:width])
                        word = word[width:]
                    if not word:
                        continue
                    if not line:
                        line = word
                    elif len(line) + 1 + len(word) <= width:
                        line += " " + word
                    else:
                        lines.append(line)
                        line = word
                lines.append(line)
            return lines
        if name == "mixcolor":
            need(3)
            first = self._color_channels(args[0])
            second = self._color_channels(args[1])
            t = max(0.0, min(1.0, number(args[2], "amount")))
            return [int(math.floor(a + (b - a) * t + 0.5)) for a, b in zip(first, second)]
        if name == "randomcolor":
            need(0)
            return [int(round(channel * 255)) for channel in colorsys.hsv_to_rgb(random.random(), 0.65, 0.95)]
        if name in ("cooldown", "pulse", "after"):
            need(2)
            key = (name, format_value(args[0]))
            seconds = number(args[1], "seconds")
            now = time.monotonic()
            started = self._timers.get(key)
            if name == "cooldown":
                if started is None or now - started >= seconds:
                    self._timers[key] = now
                    return True
                return False
            if started is None:
                self._timers[key] = now
                return seconds <= 0 if name == "after" else False
            if now - started >= seconds:
                if name == "pulse":
                    self._timers[key] = now
                return True
            return False
        if name in ("scrollx", "scrolly"):
            need(0)
            value = self.scroll[0 if name == "scrollx" else 1]
            return int(value) if value == int(value) else value
        return self._builtin_109(name, args, number, need)

    def _color_channels(self, value):
        if isinstance(value, (list, tuple)) and len(value) in (3, 4):
            return [max(0, min(255, int(channel))) for channel in value[:3]]
        if isinstance(value, str) and is_color(value):
            return list(color_value(value))
        raise ValueError(f"'{format_value(value)}' is not a colour. use a name like red, #ff8800 or [255, 136, 0]")

    def _rect_of(self, value):
        if isinstance(value, str) and (value in self.objects or ("button:" + value) in self.objects):
            shape = self._collision_shape(self._object(value))
            if shape[0] == "circle":
                _, x, y, radius = shape
                return (x - radius, y - radius, radius * 2, radius * 2)
            return shape[1:]
        if isinstance(value, dict):
            try:
                return tuple(float(value[key]) for key in ("x", "y", "w", "h"))
            except (KeyError, TypeError, ValueError):
                pass
        if isinstance(value, list) and len(value) == 4:
            return tuple(float(item) for item in value)
        raise ValueError("overlap() needs object names, [x, y, w, h] lists or maps with x, y, w and h")

    # ----- includes and compiling --------------------------------------------
    def _expand_includes_mapped(self, source, base_dir, include_stack=(), depth=0, budget=None, label=None,
                                modules=None):
        if budget is None:
            budget = [len(source)]
        if modules is None:
            modules = set()
        if depth > 16:
            raise ValueError("include nesting is limited to 16 files")
        expanded = []
        for lineno, raw in enumerate(join_continued_lines(source.splitlines()), start=1):
            stripped = raw.strip()
            if not stripped.startswith(("include", "use")) or stripped.startswith("//"):
                expanded.append((raw, label, lineno))
                continue
            parts = split_command(stripped)
            if not parts or parts[0] not in ("include", "use") or (len(parts) > 1 and parts[1] in _ASSIGNMENT_TOKENS):
                expanded.append((raw, label, lineno))
                continue
            where = f"{label} line {lineno}" if label else f"line {lineno}"
            if parts[0] == "use":
                if len(parts) != 2:
                    raise ValueError(f"{where}: write it as use <module-name>")
                path = find_module(str(parts[1]), base_dir)
                if path is None and self.fetchfile is not None:
                    for candidate in (f"modules/{parts[1]}.gubl", f"{parts[1]}.gubl"):
                        path = self._fetched(candidate, base_dir)
                        if path:
                            break
                if path is None:
                    raise ValueError(f"{where}: there is no module named '{parts[1]}'. modules are .gubl files in "
                                     "a modules folder")
                path = os.path.realpath(path)
                if path in modules or path in include_stack:
                    continue
                modules.add(path)
                include_path = str(parts[1])
            else:
                if len(parts) < 2:
                    raise ValueError(f"{where}: use include <relative-script-path>")
                include_path = " ".join(parts[1:])
                path = os.path.realpath(os.path.join(base_dir, include_path))
                fetched = self._fetched(include_path.strip('"').strip("'"), base_dir)
                if fetched:
                    path = os.path.realpath(fetched)
            if path in include_stack:
                raise ValueError(f"{where}: '{include_path}' creates a recursive include")
            try:
                with open(path, "r", encoding="utf-8") as included_file:
                    included_source = included_file.read()
            except OSError as err:
                raise ValueError(f"{where}: could not read include '{include_path}': {str(err).lower()}") from err
            budget[0] += len(included_source)
            if budget[0] > 2_000_000:
                raise ValueError("combined included scripts are limited to 2 mb")
            expanded.extend(self._expand_includes_mapped(
                included_source, os.path.dirname(path), include_stack + (path,), depth + 1, budget,
                label=os.path.basename(path), modules=modules,
            ))
        return expanded

    def _expand_includes(self, source, base_dir, include_stack=(), depth=0, budget=None):
        mapped = self._expand_includes_mapped(source, base_dir, include_stack, depth, budget)
        return "\n".join(text for text, _, _ in mapped)

    def _compile(self, mapped):
        program = []
        for index, (raw, label, lineno) in enumerate(mapped):
            parsed = parse_line(raw)
            statement = Statement(index, lineno, label, parsed)
            if parsed and parsed.error:
                raise GublanError(parsed.error, statement)
            if parsed and parsed.cmd not in GUBLANCOMMANDS:
                suggestion = difflib.get_close_matches(parsed.cmd, sorted(GUBLANCOMMANDS), n=1, cutoff=0.55)
                hint = f" did you mean '{suggestion[0]}'?" if suggestion else ""
                raise GublanError(f"'{parsed.cmd}' is not a command.{hint}", statement)
            program.append(statement)

        stack = []
        functions = {}
        tests = []
        for statement in program:
            cmd = statement.cmd
            if cmd is None:
                continue
            if cmd in BLOCK_OPENERS:
                if cmd in CALLABLE_BLOCKS:
                    if stack:
                        raise GublanError(f"{cmd} blocks must be written outside other blocks", statement)
                    if len(statement.parts) < 2:
                        raise GublanError(f"give the {cmd} a name: {cmd} <name>", statement)
                stack.append([statement, statement])
            elif cmd in BLOCK_MIDDLES:
                parents = BLOCK_MIDDLES[cmd]
                if not stack or stack[-1][0].cmd not in parents:
                    raise GublanError(f"'{cmd}' must be inside {' or '.join('a ' + p for p in parents)} block",
                                      statement)
                if stack[-1][1].cmd in ("else", "catch"):
                    raise GublanError(f"'{cmd}' can't come after {stack[-1][1].cmd}", statement)
                stack[-1][1].next = statement.index
                stack[-1][1] = statement
                stack[-1].append(statement)
            elif cmd == "end":
                if not stack:
                    raise GublanError("'end' does not have a matching block", statement)
                entry = stack.pop()
                opener = entry[0]
                opener.end = statement.index
                statement.owner = opener.index
                if opener.cmd in ("if", "match", "try"):
                    entry[1].next = statement.index
                    for branch in entry[2:]:
                        branch.end = statement.index
                if opener.cmd == "function":
                    names, defaults = function_parameters(opener.parts)
                    functions[opener.parts[1]] = FunctionInfo(opener.index, statement.index, names, defaults)
                if opener.cmd == "test":
                    tests.append((" ".join(str(part) for part in opener.parts[1:]), opener.index, statement.index))
        if stack:
            raise GublanError(f"'{stack[-1][0].cmd}' block is missing end", stack[-1][0])
        self._prog = program
        self.functions = functions
        self.tests = tests

    # ----- running ---------------------------------------------------------------
    def run(self, source, base_dir=None):
        if base_dir is not None:
            self.base_dir = os.path.abspath(base_dir)
        self.reset()
        self.running = True
        try:
            try:
                mapped = self._expand_includes_mapped(source, self.base_dir)
            except ValueError as err:
                self.onlog(f"include error: {err}")
                self.last_error = {"line": None, "file": None, "message": str(err)}
                return
            self._compile(mapped)
            self._exec(0, len(self._prog))
            self.finished = True
            if self.hold_window and self.screen and self.running and not self.shouldstop():
                self._hold_window()
        except _Kill as signal:
            if signal.message:
                self.onlog(signal.message)
        except _Stop:
            pass
        except _Return:
            self._report(GublanError("'return' can only be used inside a called function", self.current))
        except GublanError as err:
            self._report(err)
        except RecursionError:
            self._report(GublanError("functions are calling each other too deeply", self.current))
        finally:
            self._flush_saves(quiet=True)
            self._close_presence()
            if self.screen:
                pygame.quit()
                self.screen = None
            elif self.audio_initialized:
                pygame.mixer.quit()
            self.running = False

    def _report(self, err):
        statement = err.statement
        line = statement.line if statement else None
        label = statement.file if statement else None
        where = f"{label} line {line}" if label else f"line {line}" if line else "error"
        self.last_error = {"line": line, "file": label, "message": err.message}
        if self.onerror:
            self.onerror(err.message, label, line)
        else:
            self.onlog(f"{where}: {err.message}")

    def _hold_window(self):
        caption = (self.window_title or f"gublan {self.mode} runtime") + " - finished"
        try:
            pygame.display.set_caption(caption)
        except pygame.error:
            return
        while self.running and not self.shouldstop():
            self.pumpevents()
            if not self.running:
                break
            self.render()
            time.sleep(1 / 30)

    def _before(self, statement):
        if not self.running or self.shouldstop():
            raise _Stop()
        self.current = statement
        if self.waitstep:
            self.waitstep(statement.line)
            if not self.running or self.shouldstop():
                raise _Stop()
        if self.ondebug:
            self.ondebug(statement.line, dict(self.vars), dict(self.objects), self.mode)
        if self.screen is not None:
            now = time.perf_counter()
            if now - self._last_pump > 0.02:
                self._last_pump = now
                self.pumpevents()
                if not self.running:
                    raise _Stop()

    def _exec(self, start, stop):
        program = self._prog
        stack = []
        pc = start
        handlers = self._handlers
        while pc < stop:
            statement = program[pc]
            cmd = statement.cmd
            if cmd is None:
                pc += 1
                continue
            self._before(statement)
            try:
                if cmd in _FLOW_COMMANDS:
                    pc = self._flow(statement, stack, pc)
                    continue
                handlers[cmd](statement)
            except _Signal:
                raise
            except RecursionError:
                raise
            except GublanError as err:
                pc = self._catch(stack, err)
                continue
            except Exception as err:
                error = GublanError(self._describe(cmd, err), statement)
                error.__cause__ = err
                pc = self._catch(stack, error)
                continue
            pc += 1

    def _catch(self, stack, error):
        """send an error to the nearest try block (inside this function), or let it stop the program."""
        for position in range(len(stack) - 1, -1, -1):
            if stack[position][0] != "try":
                continue
            opener = stack[position][1]
            del stack[position:]
            catch = self._prog[opener.next] if opener.next is not None else None
            if catch is None or catch.cmd != "catch":
                return opener.end + 1
            name = str(catch.parts[1]) if len(catch.parts) > 1 else "error"
            self.vars[name] = error.message
            stack.append(["catch", catch])
            return catch.index + 1
        raise error

    @staticmethod
    def _describe(cmd, err):
        if isinstance(err, ValueError):
            return str(err)
        if isinstance(err, TypeError):
            return f"the values used by '{cmd}' do not match its expected types: {str(err).lower()}"
        if isinstance(err, pygame.error):
            return f"'{cmd}' failed: {str(err).lower()}"
        return f"could not run '{cmd}'. check its arguments: {str(err).lower()}"

    def _condition(self, statement):
        tokens = statement.parts[1:]
        if _condition_is_simple(tokens):
            return self._compare(self.val(tokens[0]), tokens[1], self.val(tokens[2]))
        if len(tokens) == 1:
            return self._truthy(self.val(tokens[0]))
        if statement.cache is None:
            try:
                statement.cache = parse_condition(statement.rest)
            except (SyntaxError, ValueError) as err:
                raise ValueError("this condition is not valid. use comparisons like x > 3") from err
        return self._truthy(self._eval(statement.cache, lenient=True))

    def _flow(self, statement, stack, pc):
        cmd = statement.cmd
        if cmd == "if":
            matched = bool(self._condition(statement))
            stack.append(["if", statement, matched])
            return pc + 1 if matched else statement.next
        if cmd == "elseif":
            frame = stack[-1]
            if frame[2]:
                return statement.end
            if self._condition(statement):
                frame[2] = True
                return pc + 1
            return statement.next
        if cmd == "else":
            frame = stack[-1]
            if frame[2]:
                return statement.end
            frame[2] = True
            return pc + 1
        if cmd == "until":
            if not self._condition(statement):
                stack.append(["until", statement])
                return pc + 1
            return statement.end + 1
        if cmd == "match":
            value = self._eval_value(statement.rest, statement.parts[1:])
            stack.append(["match", statement, False, value])
            return statement.next
        if cmd == "case":
            frame = stack[-1]
            if frame[2]:
                return statement.end
            if statement.cache is None:
                try:
                    statement.cache = [parse_expression(part) for part in _split_top_level_commas(statement.rest)]
                except (SyntaxError, ValueError) as err:
                    raise ValueError("write cases as values split by commas, like: case 1, 2, 3") from err
            for node in statement.cache:
                if self._equal(frame[3], self._eval(node, lenient=isinstance(node, ast.Name))):
                    frame[2] = True
                    return pc + 1
            return statement.next
        if cmd == "try":
            stack.append(["try", statement])
            return pc + 1
        if cmd == "catch":
            # reached by finishing the try part without a problem: skip the catch part
            stack.pop()
            return statement.end + 1
        if cmd == "test":
            return statement.end + 1
        if cmd == "end":
            frame = stack[-1]
            kind = frame[0]
            if kind in ("if", "match", "try", "catch"):
                stack.pop()
                return pc + 1
            if kind == "loop":
                frame[2] -= 1
                if frame[2] > 0:
                    return frame[1].index + 1
                stack.pop()
                return pc + 1
            if kind == "forever":
                return frame[1].index + 1
            if kind in ("while", "until"):
                stack.pop()
                return frame[1].index
            if kind == "for":
                return self._for_next(frame, stack, pc)
            stack.pop()
            return pc + 1
        if cmd == "loop":
            count = self.val(statement.parts[1])
            if isinstance(count, bool) or not isinstance(count, (int, float)):
                raise ValueError(f"loop needs a number of times, got '{format_value(count)}'")
            count = int(count)
            if count <= 0:
                return statement.end + 1
            stack.append(["loop", statement, count])
            return pc + 1
        if cmd == "forever":
            stack.append(["forever", statement])
            return pc + 1
        if cmd == "while":
            if self._condition(statement):
                stack.append(["while", statement])
                return pc + 1
            return statement.end + 1
        if cmd == "for":
            return self._for_start(statement, stack, pc)
        if cmd == "break":
            while stack:
                frame = stack.pop()
                if frame[0] in LOOP_COMMANDS:
                    return frame[1].end + 1
            raise ValueError("'break' can only be used inside a loop")
        if cmd == "continue":
            while stack:
                if stack[-1][0] in LOOP_COMMANDS:
                    return stack[-1][1].end
                stack.pop()
            raise ValueError("'continue' can only be used inside a loop")
        if cmd == "function":
            return statement.end + 1
        if cmd == "return":
            if self._depth == 0:
                raise ValueError("'return' can only be used inside a called function")
            raw = statement.rest
            value = self._eval_value(raw, statement.parts[1:]) if len(statement.parts) > 1 else None
            raise _Return(value)
        if cmd == "kill":
            raise _Kill("program killed")
        if cmd == "then":
            if len(statement.parts) >= 2 and statement.parts[1] == "kill" and any(f[0] == "if" for f in stack):
                raise _Kill("triggered then kill")
            return pc + 1
        raise ValueError(f"'{cmd}' is not supported here")

    def _for_start(self, statement, stack, pc):
        if statement.cache is None:
            match = _FOR_RANGE_RE.match(statement.rest)
            if match:
                name, start, end, step = match.groups()
                statement.cache = ("range", name, parse_expression(start), parse_expression(end),
                                   parse_expression(step) if step else None)
            else:
                match = _FOR_IN_RE.match(statement.rest)
                if not match:
                    raise ValueError("write for loops as: for i = 1 to 10  or  for item in items")
                statement.cache = ("in", match.group(1), parse_expression(match.group(2)))
        spec = statement.cache
        if spec[0] == "range":
            _, name, start_node, end_node, step_node = spec
            values = []
            for node, label in ((start_node, "start"), (end_node, "end"), (step_node, "step")):
                if node is None:
                    values.append(1)
                    continue
                value = self._eval(node, lenient=False)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"the for loop {label} must be a number, got '{format_value(value)}'")
                values.append(value)
            start, end, step = values
            if step == 0:
                raise ValueError("a for loop step cannot be zero")
            if (step > 0 and start > end) or (step < 0 and start < end):
                return statement.end + 1
            self.vars[name] = start
            stack.append(["for", statement, "range", name, start, end, step, 0])
            return pc + 1
        _, name, iterable_node = spec
        iterable = self._eval(iterable_node, lenient=False)
        if isinstance(iterable, dict):
            items = list(iterable.keys())
        elif isinstance(iterable, (list, str)):
            items = list(iterable)
        elif isinstance(iterable, (int, float)) and not isinstance(iterable, bool):
            items = list(range(int(iterable)))
        else:
            raise ValueError(f"can't go through {kind_of(iterable)} '{format_value(iterable)}' with for")
        if not items:
            return statement.end + 1
        self.vars[name] = items[0]
        stack.append(["for", statement, "in", name, items, 0])
        return pc + 1

    def _for_next(self, frame, stack, pc):
        if frame[2] == "range":
            _, opener, _, name, start, end, step, count = frame
            count += 1
            value = start + step * count
            if (step > 0 and value <= end + 1e-9) or (step < 0 and value >= end - 1e-9):
                frame[7] = count
                self.vars[name] = value
                return opener.index + 1
            stack.pop()
            return pc + 1
        _, opener, _, name, items, position = frame
        position += 1
        if position < len(items):
            frame[5] = position
            self.vars[name] = items[position]
            return opener.index + 1
        stack.pop()
        return pc + 1

    def _call_function(self, name, arguments):
        function = self.functions.get(name)
        if function is None:
            raise ValueError(f"there is no function named '{name}'")
        parameters = function.params
        required = sum(1 for parameter in parameters if parameter not in function.defaults)
        if not required <= len(arguments) <= len(parameters):
            wanted = str(required) if required == len(parameters) else f"{required} to {len(parameters)}"
            raise ValueError(f"function '{name}' needs {wanted} argument(s), got {len(arguments)}")
        if self._depth >= 180:
            raise ValueError("functions are calling each other too deeply (limit 180)")
        saved = {parameter: (parameter in self.vars, self.vars.get(parameter)) for parameter in parameters}
        self.vars.update(zip(parameters, arguments))
        try:
            for parameter in parameters[len(arguments):]:
                raw = function.defaults[parameter]
                self.vars[parameter] = self._eval_value(raw, split_command(raw))
        except BaseException:
            self._restore_names(saved)
            raise
        self.vars["result"] = None
        self._depth += 1
        self._local_frames.append(saved)
        value = None
        try:
            self._exec(function.start + 1, function.end)
        except _Return as signal:
            value = signal.value
        finally:
            self._depth -= 1
            self._local_frames.pop()
            self._restore_names(saved)
        self.vars["result"] = value
        return value

    # ----- display -------------------------------------------------------------
    def initstage(self, mode):
        self.mode = mode
        pygame.init()
        width, height = self.window_size
        caption = self.window_title or f"gublan {mode} runtime"
        if mode == "2d":
            self.screen = pygame.display.set_mode((width, height))
        else:
            self.screen = pygame.display.set_mode((width, height), DOUBLEBUF | OPENGL)
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            gluPerspective(45, width / height, 0.1, 100.0)
            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()
            glEnable(GL_DEPTH_TEST)
            glEnable(GL_LIGHTING)
            glEnable(GL_LIGHT0)
            glEnable(GL_NORMALIZE)
            glEnable(GL_COLOR_MATERIAL)
            glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
            glLightfv(GL_LIGHT0, GL_POSITION, (0.35, 0.8, 1.0, 0.0))
            glLightfv(GL_LIGHT0, GL_AMBIENT, (0.32, 0.32, 0.32, 1.0))
            glLightfv(GL_LIGHT0, GL_DIFFUSE, (0.85, 0.85, 0.85, 1.0))
            self._gl_clear = None
        self._overlay_texture = None
        pygame.display.set_caption(caption)
        pygame.mouse.set_visible(self.cursor_visible)
        self.text_font = self._font(self.text_size)
        self.vars["screen_width"], self.vars["screen_height"] = width, height
        self._last_frame = time.perf_counter()

    def _font(self, size):
        size = max(6, min(int(size), 300))
        font = self._fonts.get(size)
        if font is None:
            font = pygame.font.Font(None, size)
            self._fonts[size] = font
        return font

    def _require_screen(self, action):
        if not self.screen:
            raise ValueError(f"add 'mode 2d' or 'mode 3d' before you {action}")

    def _render_3d_text(self):
        labels = [obj for obj in self.objects.values() if obj["type"] == "text" and not obj.get("hidden")]
        if not labels:
            return
        width, height = self.screen.get_size()
        glPushAttrib(GL_ENABLE_BIT | GL_TEXTURE_BIT | GL_COLOR_BUFFER_BIT)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, width, height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        try:
            for obj in labels:
                color = color_value(obj["color"])
                texture_key = (obj["text"], color, obj.get("size", 24))
                if obj.get("texture_key") != texture_key:
                    old_texture = obj.pop("texture", None)
                    if old_texture is not None:
                        glDeleteTextures([old_texture])
                    font = self._font(obj.get("size", 24)) if obj.get("size", 24) != 24 or self.text_font is None \
                        else self.text_font
                    label = font.render(obj["text"], True, color)
                    texture = glGenTextures(1)
                    glBindTexture(GL_TEXTURE_2D, texture)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
                    glTexImage2D(
                        GL_TEXTURE_2D, 0, GL_RGBA, label.get_width(), label.get_height(),
                        0, GL_RGBA, GL_UNSIGNED_BYTE, pygame.image.tobytes(label, "RGBA", True)
                    )
                    obj["texture"] = texture
                    obj["texture_size"] = label.get_size()
                    obj["texture_key"] = texture_key
                else:
                    glBindTexture(GL_TEXTURE_2D, obj["texture"])

                text_width, text_height = obj["texture_size"]
                x, y = obj["x"], obj["y"]
                glColor4f(1, 1, 1, 1)
                glBegin(GL_QUADS)
                glTexCoord2f(0, 1)
                glVertex2f(x, y)
                glTexCoord2f(1, 1)
                glVertex2f(x + text_width, y)
                glTexCoord2f(1, 0)
                glVertex2f(x + text_width, y + text_height)
                glTexCoord2f(0, 0)
                glVertex2f(x, y + text_height)
                glEnd()
        finally:
            glPopMatrix()
            glMatrixMode(GL_PROJECTION)
            glPopMatrix()
            glMatrixMode(GL_MODELVIEW)
            glPopAttrib()

    def pumpevents(self):
        if not self.screen:
            return
        if self._focus is not None and self._focus not in self.objects:
            self._set_focus(None)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if self._focus is not None:
                    self._type_into_textbox(event)
                    continue
                self._key_presses.add(event.key)
                if len(self._key_presses) > 64:
                    self._key_presses.clear()
            elif event.type == pygame.TEXTINPUT:
                if self._focus is not None:
                    self._type_into_textbox(event)
                continue
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._mouse_presses.add(getattr(event, "button", 1))
                if getattr(event, "button", 1) == 1:
                    self._clicks.append(tuple(getattr(event, "pos", None) or pygame.mouse.get_pos()))
                    del self._clicks[:-16]
            elif event.type == pygame.MOUSEMOTION and self._dragging is not None:
                self._drag_slider(getattr(event, "pos", None) or pygame.mouse.get_pos())
            # buttons and the other ui work the same in 2d and 3d (in 3d they are drawn on top of the scene)
            if event.type == pygame.MOUSEBUTTONDOWN and getattr(event, "button", 1) == 1:
                position = getattr(event, "pos", None)
                mx, my = position if position is not None else pygame.mouse.get_pos()
                if "uibtn" in self.objects:
                    bx, by, bw, bh = self.objects["uibtn"]
                    if bx <= mx <= bx + bw and by <= my <= by + bh:
                        self.vars["ui"] = self.button_label
                focus = None
                for name, obj in list(self.objects.items()):
                    if not isinstance(obj, dict) or obj.get("hidden"):
                        continue
                    kind = obj.get("type")
                    if kind not in ("button", "textbox", "slider", "checkbox"):
                        continue
                    if kind == "checkbox":
                        width = obj["w"] + 8 + self._font(obj.get("size", 24)).size(obj["label"])[0]
                        inside = pygame.Rect(obj["x"], obj["y"], width, obj["h"]).collidepoint(mx, my)
                    else:
                        inside = pygame.Rect(obj["x"], obj["y"] - (6 if kind == "slider" else 0), obj["w"],
                                             obj["h"] + (12 if kind == "slider" else 0)).collidepoint(mx, my)
                    if not inside:
                        continue
                    if kind == "button":
                        self.vars[obj["variable"]] = 1
                    elif kind == "textbox":
                        focus = name
                        obj["cursor"], obj["anchor"] = self._textbox_index(obj, mx), None
                    elif kind == "checkbox":
                        obj["checked"] = not obj["checked"]
                    elif kind == "slider":
                        self._dragging = name
                        self._drag_slider((mx, my))
                self._set_focus(focus)
            if event.type == pygame.MOUSEBUTTONUP:
                self._dragging = None
                for obj in self.objects.values():
                    if isinstance(obj, dict) and obj.get("type") == "button":
                        self.vars[obj["variable"]] = 0

    def _drag_slider(self, position):
        obj = self.objects.get(self._dragging)
        if not isinstance(obj, dict) or obj.get("type") != "slider":
            self._dragging = None
            return
        share = max(0.0, min(1.0, (position[0] - obj["x"]) / max(1, obj["w"])))
        value = obj["min"] + (obj["max"] - obj["min"]) * share
        obj["value"] = int(round(value)) if obj.get("whole") else round(value, 4)

    def _textbox_index(self, obj, mouse_x):
        font = self._font(obj.get("size", 24))
        text = obj["text"]
        offset = obj.get("_offset", 0)
        target = mouse_x - (obj["x"] + 8) + offset
        best, best_distance = 0, abs(target)
        for index in range(1, len(text) + 1):
            distance = abs(font.size(text[:index])[0] - target)
            if distance < best_distance:
                best, best_distance = index, distance
        return best

    def _type_into_textbox(self, event):
        obj = self.objects.get(self._focus)
        if not isinstance(obj, dict) or obj.get("type") != "textbox":
            self._set_focus(None)
            return
        value, cursor, anchor, action = self._edit_input_event(obj["text"], obj["cursor"], obj["anchor"], event)
        obj["text"], obj["cursor"], obj["anchor"] = value, cursor, anchor
        obj["_blink"] = time.monotonic()
        if action == "accept":
            obj["submitted"] = True
        elif action == "cancel":
            self._set_focus(None)

    def _consume_press(self, keycode):
        self.pumpevents()
        if keycode in self._key_presses:
            self._key_presses.discard(keycode)
            return True
        return False

    def _keycode(self, name):
        key = format_value(name).strip().lower()
        if key in self._key_cache:
            return self._key_cache[key]
        lookup = KEY_ALIASES.get(key, key)
        code = None
        try:
            code = pygame.key.key_code(lookup)
        except (ValueError, pygame.error, AttributeError):
            code = getattr(pygame, "K_" + lookup.replace(" ", "_"), None) or getattr(
                pygame, "K_" + lookup.upper().replace(" ", "_"), None
            )
        if code is None:
            raise ValueError(f"'{format_value(name)}' is not a key name. try left, right, up, down, space, a, 1")
        self._key_cache[key] = code
        return code

    def render(self):
        self._tick_effects()
        if not self.screen:
            return
        if self.mode == "2d":
            self._render_2d()
            pygame.display.flip()
        elif self.mode == "3d":
            self._render_3d()
            pygame.display.flip()

    def _render_2d(self):
        self.screen.fill(self.background)
        self._draw_objects(self.screen)
        if self.style.get("show_fps"):
            self._draw_fps(self.screen)

    def _draw_fps(self, screen):
        now = time.perf_counter()
        times = [stamp for stamp in self._fps_times if now - stamp < 1.0]
        times.append(now)
        self._fps_times = times
        label = self._font(18).render(f"fps {len(times)}", True, color_value(self.style["dialog_accent"]))
        backing = pygame.Surface((label.get_width() + 10, label.get_height() + 4), pygame.SRCALPHA)
        backing.fill((0, 0, 0, 150))
        screen.blit(backing, (screen.get_width() - backing.get_width() - 6, 6))
        screen.blit(label, (screen.get_width() - backing.get_width() + -1, 8))

    _FLAT_KINDS = ("box", "circle", "line", "text", "image", "sprite", "button", "textbox", "slider", "checkbox",
                   "ellipse", "polygon")
    _UI_KINDS = ("button", "textbox", "slider", "checkbox")

    def _alpha_surface(self, screen):
        size = screen.get_size()
        layer = self._alpha_layer
        if layer is None or layer.get_size() != size:
            layer = self._alpha_layer = pygame.Surface(size, pygame.SRCALPHA)
        layer.set_alpha(255)
        layer.fill((0, 0, 0, 0))
        return layer

    def _draw_objects(self, screen, overlay=False):
        """draw every 2d object onto a surface. in 3d (overlay=True) text is left to _render_3d_text."""
        if "uibtn" in self.objects:
            bx, by, bw, bh = self.objects["uibtn"]
            pygame.draw.rect(screen, (109, 137, 79), (bx, by, bw, bh))
            label = self._font(20).render(self.button_label, True, (240, 240, 240))
            screen.blit(label, (bx + 12, by + 10))
        items = [(name, obj) for name, obj in self.objects.items()
                 if name != "uibtn" and isinstance(obj, dict) and not obj.get("hidden")]
        if any(obj.get("layer") for _name, obj in items):
            items.sort(key=lambda item: item[1].get("layer", 0))
        world_x = world_y = 0.0
        if not overlay:
            world_x = self._shake_offset[0] - self.scroll[0]
            world_y = self._shake_offset[1] - self.scroll[1]
        for name, obj in items:
            kind = obj["type"]
            if kind not in self._FLAT_KINDS or (overlay and kind == "text"):
                continue
            alpha = obj.get("alpha", 1)
            if alpha <= 0:
                continue
            offset = (0.0, 0.0) if kind in self._UI_KINDS or obj.get("fixed") else (world_x, world_y)
            if alpha < 1:
                layer = self._alpha_surface(screen)
                self._draw_flat(layer, name, obj, offset)
                layer.set_alpha(int(alpha * 255))
                screen.blit(layer, (0, 0))
            else:
                self._draw_flat(screen, name, obj, offset)
        if self._particles and not overlay:
            layer = self._alpha_surface(screen)
            for x, y, _vx, _vy, life, total, color, size in self._particles:
                fade = max(0.0, min(1.0, life / total))
                side = max(1, int(size * (0.4 + 0.6 * fade)))
                pygame.draw.rect(layer, (*color[:3], int(255 * fade)),
                                 (int(x + world_x - side / 2), int(y + world_y - side / 2), side, side))
            screen.blit(layer, (0, 0))

    def _draw_flat(self, screen, name, obj, offset):
        kind = obj["type"]
        ox, oy = offset
        color = color_value(obj["color"])
        if kind in ("textbox", "slider", "checkbox"):
            self._draw_widget(screen, name, obj, color)
        elif kind == "box":
            pygame.draw.rect(screen, color, (obj["x"] + ox, obj["y"] + oy, obj["w"], obj["h"]))
        elif kind == "circle":
            pygame.draw.circle(screen, color, (int(obj["x"] + ox), int(obj["y"] + oy)), int(obj["r"]))
        elif kind == "ellipse":
            pygame.draw.ellipse(screen, color, (obj["x"] + ox, obj["y"] + oy, max(1, obj["w"]), max(1, obj["h"])))
        elif kind == "polygon":
            scale_x = obj["w"] / obj["pw"] if obj["pw"] else 1
            scale_y = obj["h"] / obj["ph"] if obj["ph"] else 1
            points = [(obj["x"] + ox + px * scale_x, obj["y"] + oy + py * scale_y) for px, py in obj["points"]]
            pygame.draw.polygon(screen, color, points)
        elif kind == "line":
            pygame.draw.line(screen, color, (obj["x"] + ox, obj["y"] + oy), (obj["x2"] + ox, obj["y2"] + oy),
                             int(obj["width"]))
        elif kind == "text":
            key = (obj["text"], color, obj.get("size", 24))
            if obj.get("_label_key") != key:
                obj["_label"] = self._font(obj.get("size", 24)).render(obj["text"], True, color)
                obj["_label_key"] = key
            screen.blit(obj["_label"], (obj["x"] + ox, obj["y"] + oy))
        elif kind in ("image", "sprite"):
            surface = obj["surface"]
            angle = obj.get("angle", 0)
            if angle:
                if obj.get("_rotated_key") != (angle, id(surface)):
                    obj["_rotated"] = pygame.transform.rotate(surface, -angle)
                    obj["_rotated_key"] = (angle, id(surface))
                rotated = obj["_rotated"]
                width, height = surface.get_size()
                rect = rotated.get_rect(center=(obj["x"] + ox + width / 2, obj["y"] + oy + height / 2))
                screen.blit(rotated, rect)
            else:
                screen.blit(surface, (obj["x"] + ox, obj["y"] + oy))
        elif kind == "button":
            rect = pygame.Rect(obj["x"], obj["y"], obj["w"], obj["h"])
            hovered = rect.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(screen, (148, 182, 108) if hovered else (82, 105, 61), rect)
            label = self._font(24).render(obj["label"], True, (240, 240, 240))
            screen.blit(label, label.get_rect(center=rect.center))

    def _draw_widget(self, screen, name, obj, color):
        kind = obj["type"]
        font = self._font(obj.get("size", 24))
        accent = (148, 182, 108)
        if kind == "textbox":
            rect = pygame.Rect(obj["x"], obj["y"], obj["w"], obj["h"])
            focused = self._focus == name
            pygame.draw.rect(screen, (23, 23, 23), rect)
            pygame.draw.rect(screen, accent if focused else (90, 90, 90), rect, 2)
            text, cursor = obj["text"], obj["cursor"]
            inner = rect.inflate(-16, 0)
            prefix = font.size(text[:cursor])[0]
            offset = max(0, prefix - inner.width + 2) if focused else 0
            obj["_offset"] = offset
            text_y = rect.y + (rect.height - font.get_height()) // 2
            previous_clip = screen.get_clip()
            screen.set_clip(inner.clip(previous_clip) if previous_clip else inner)
            if obj.get("anchor") is not None and obj["anchor"] != cursor and focused:
                start, end = sorted((obj["anchor"], cursor))
                left = inner.x + font.size(text[:start])[0] - offset
                right = inner.x + font.size(text[:end])[0] - offset
                pygame.draw.rect(screen, (75, 96, 57), (left, text_y, right - left, font.get_height()))
            if text:
                screen.blit(font.render(text, True, color), (inner.x - offset, text_y))
            elif obj.get("hint") and not focused:
                screen.blit(font.render(obj["hint"], True, (120, 120, 120)), (inner.x, text_y))
            if focused and int((time.monotonic() - obj.get("_blink", 0)) * 2) % 2 == 0:
                caret = inner.x + prefix - offset
                pygame.draw.line(screen, accent, (caret, text_y + 2), (caret, text_y + font.get_height() - 2), 2)
            screen.set_clip(previous_clip)
        elif kind == "slider":
            low, high = obj["min"], obj["max"]
            share = 0.0 if high == low else (obj["value"] - low) / (high - low)
            middle = obj["y"] + obj["h"] // 2
            pygame.draw.rect(screen, (60, 60, 60), (obj["x"], middle - 3, obj["w"], 6))
            pygame.draw.rect(screen, color, (obj["x"], middle - 3, int(obj["w"] * share), 6))
            knob = (int(obj["x"] + obj["w"] * share), middle)
            pygame.draw.circle(screen, (240, 240, 240) if self._dragging == name else color, knob, 9)
            label = self._font(20).render(format_value(obj["value"]), True, (200, 200, 200))
            screen.blit(label, (obj["x"] + obj["w"] + 12, middle - label.get_height() // 2))
        elif kind == "checkbox":
            rect = pygame.Rect(obj["x"], obj["y"], obj["w"], obj["h"])
            pygame.draw.rect(screen, (23, 23, 23), rect)
            pygame.draw.rect(screen, color if obj["checked"] else (110, 110, 110), rect, 2)
            if obj["checked"]:
                pygame.draw.lines(screen, color, False, [(rect.x + 5, rect.centery), (rect.x + 10, rect.bottom - 6),
                                                         (rect.right - 5, rect.y + 6)], 3)
            label = font.render(obj["label"], True, (229, 229, 229))
            screen.blit(label, (rect.right + 8, rect.centery - label.get_height() // 2))

    def _render_overlay(self):
        """draw 2d objects (shapes, pictures, buttons, textboxes...) flat on top of the 3d scene."""
        if not any(name == "uibtn" or (isinstance(obj, dict) and obj.get("type") in self._FLAT_KINDS
                                       and obj["type"] != "text" and not obj.get("hidden"))
                   for name, obj in self.objects.items()):
            return
        surface = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        self._draw_objects(surface, overlay=True)
        self._blit_gl_surface(surface)

    def _blit_gl_surface(self, surface):
        """show a see-through pygame surface over the whole 3d window."""
        width, height = surface.get_size()
        if self._overlay_texture is None:
            self._overlay_texture = glGenTextures(1)
        glPushAttrib(GL_ENABLE_BIT | GL_TEXTURE_BIT | GL_COLOR_BUFFER_BIT)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, width, height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        try:
            glBindTexture(GL_TEXTURE_2D, self._overlay_texture)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE,
                         pygame.image.tobytes(surface, "RGBA", True))
            glColor4f(1, 1, 1, 1)
            glBegin(GL_QUADS)
            glTexCoord2f(0, 1)
            glVertex2f(0, 0)
            glTexCoord2f(1, 1)
            glVertex2f(width, 0)
            glTexCoord2f(1, 0)
            glVertex2f(width, height)
            glTexCoord2f(0, 0)
            glVertex2f(0, height)
            glEnd()
        finally:
            glPopMatrix()
            glMatrixMode(GL_PROJECTION)
            glPopMatrix()
            glMatrixMode(GL_MODELVIEW)
            glPopAttrib()

    def _render_3d(self):
        if self._gl_clear != self.background:
            red, green, blue = (channel / 255.0 for channel in self.background)
            glClearColor(red, green, blue, 1.0)
            self._gl_clear = self.background
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        yaw, pitch = self.camera_turn
        turned = bool(yaw or pitch or self.light is not None)
        if turned or self._gl_turned:
            glLoadIdentity()  # forget last frame's turn (the view goes back to straight ahead)
        self._gl_turned = turned
        if self.light is not None:
            # the light keeps its direction in the world while the camera turns
            x, y, z, brightness = self.light
            glRotatef(pitch, 1, 0, 0)
            glRotatef(yaw, 0, 1, 0)
            glLightfv(GL_LIGHT0, GL_POSITION, (x, y, z, 0.0))
            glLightfv(GL_LIGHT0, GL_DIFFUSE, (0.85 * brightness, 0.85 * brightness, 0.85 * brightness, 1.0))
            glLightfv(GL_LIGHT0, GL_AMBIENT, (0.32 * min(brightness, 1.5),) * 3 + (1.0,))
        elif yaw or pitch:
            glRotatef(pitch, 1, 0, 0)
            glRotatef(yaw, 0, 1, 0)
        for obj in self.objects.values():
            if not isinstance(obj, dict) or obj["type"] not in SHAPES_3D or obj.get("hidden"):
                continue
            self._render_shape_gl(obj)
        self._render_overlay()
        self._render_3d_text()

    @staticmethod
    def _cube_faces(s):
        return (
            ((0, 0, 1), ((-s, -s, s), (s, -s, s), (s, s, s), (-s, s, s))),
            ((0, 0, -1), ((-s, -s, -s), (-s, s, -s), (s, s, -s), (s, -s, -s))),
            ((0, 1, 0), ((-s, s, -s), (-s, s, s), (s, s, s), (s, s, -s))),
            ((0, -1, 0), ((-s, -s, -s), (s, -s, -s), (s, -s, s), (-s, -s, s))),
            ((1, 0, 0), ((s, -s, -s), (s, s, -s), (s, s, s), (s, -s, s))),
            ((-1, 0, 0), ((-s, -s, -s), (-s, -s, s), (-s, s, s), (-s, s, -s))),
        )

    # ----- collisions and animation -------------------------------------------
    @staticmethod
    def _collision_shape(obj):
        kind = obj["type"]
        if kind == "circle":
            return ("circle", float(obj["x"]), float(obj["y"]), abs(float(obj["r"])))
        if kind == "sphere":
            return ("circle", float(obj["x"]), float(obj["y"]), abs(float(obj["radius"])))
        if kind in ("box", "button", "textbox", "slider", "checkbox", "ellipse", "polygon"):
            return ("rect", float(obj["x"]), float(obj["y"]), float(obj["w"]), float(obj["h"]))
        if kind == "cube":
            size = float(obj["size"])
            return ("rect", float(obj["x"]), float(obj["y"]), size, size)
        if kind in ("image", "sprite"):
            width, height = obj["surface"].get_size()
            return ("rect", float(obj["x"]), float(obj["y"]), width, height)
        if kind == "text" and "_label" in obj:
            width, height = obj["_label"].get_size()
            return ("rect", float(obj["x"]), float(obj["y"]), width, height)
        if kind in SHAPES_3D:
            raise ValueError("3d shapes can only touch other 3d shapes")
        raise ValueError("touching supports boxes, circles, cubes, spheres, buttons and sprites")

    def _objects_touching(self, first, second):
        for name in (first, second):
            if name not in self.objects and ("button:" + name) not in self.objects:
                raise ValueError(f"object '{name}' does not exist yet")
        first_obj = self.objects.get(first) or self.objects["button:" + first]
        second_obj = self.objects.get(second) or self.objects["button:" + second]
        if first_obj.get("hidden") or second_obj.get("hidden"):
            return False
        if first_obj["type"] in SHAPES_3D and second_obj["type"] in SHAPES_3D:
            return self._touching_3d(first_obj, second_obj)
        first_shape = self._collision_shape(first_obj)
        second_shape = self._collision_shape(second_obj)
        if first_shape[0] == "circle" and second_shape[0] == "circle":
            _, x1, y1, r1 = first_shape
            _, x2, y2, r2 = second_shape
            return (x1 - x2) ** 2 + (y1 - y2) ** 2 <= (r1 + r2) ** 2
        if first_shape[0] == "circle":
            circle, rect = first_shape, second_shape
        elif second_shape[0] == "circle":
            circle, rect = second_shape, first_shape
        else:
            _, x1, y1, w1, h1 = first_shape
            _, x2, y2, w2, h2 = second_shape
            return x1 <= x2 + w2 and x2 <= x1 + w1 and y1 <= y2 + h2 and y2 <= y1 + h1
        _, cx, cy, radius = circle
        _, rx, ry, width, height = rect
        nearest_x = min(max(cx, rx), rx + width)
        nearest_y = min(max(cy, ry), ry + height)
        return (cx - nearest_x) ** 2 + (cy - nearest_y) ** 2 <= radius ** 2

    def _animate_object(self, obj, target_position, duration):
        if not self.screen:
            raise ValueError("add a display mode before animating an object")
        if duration < 0:
            raise ValueError("animation time cannot be negative")
        dimensions = ("x", "y", "z") if len(target_position) == 3 else ("x", "y")
        start_position = tuple(float(obj[key]) for key in dimensions)
        line_offset = (obj["x2"] - obj["x"], obj["y2"] - obj["y"]) if obj["type"] == "line" else None
        started = time.monotonic()
        clock = pygame.time.Clock()
        while self.running and not self.shouldstop():
            progress = 1.0 if duration == 0 else min(1.0, (time.monotonic() - started) / duration)
            eased = progress * progress * (3 - 2 * progress)
            for key, start, target in zip(dimensions, start_position, target_position):
                obj[key] = start + (target - start) * eased
            if line_offset:
                obj["x2"], obj["y2"] = obj["x"] + line_offset[0], obj["y"] + line_offset[1]
            self.pumpevents()
            self.render()
            if progress >= 1:
                break
            clock.tick(60)

    # ----- dialogs ---------------------------------------------------------------
    def _draw_dialog(self, message, value="", is_input=False, cursor=None, anchor=None, caret_visible=True,
                     progress=1.0):
        """draw a popup (or an ask box) over the game. progress below 1 is part of its opening animation."""
        style = self.style
        shade = int(255 * style["dialog_shade"] / 100 * min(1.0, progress * 1.4))
        if self.mode == "3d":
            # 3d windows can't be drawn on directly: draw the dialog on a see-through layer over the scene
            self._render_3d()
            target = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            target.fill((0, 0, 0, shade))
        else:
            self._render_2d()
            target = self.screen
            overlay = pygame.Surface(target.get_size(), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, shade))
            target.blit(overlay, (0, 0))
        width, height = target.get_size()
        size = style["dialog_text_size"]
        font = self._font(size)
        hint_font = self._font(max(12, size - 4))
        line_height = font.get_linesize()
        box_width = min(style["dialog_width"], width - 20)
        lines = wrap_words(message, font, box_width - 40)[:6] or [""]
        box_height = 25 + line_height * len(lines) + (line_height + 24 if is_input else 0) + \
            (hint_font.get_linesize() + 20 if style["dialog_hints"] else 10)
        box_height = min(box_height, height - 20)
        box = pygame.Surface((box_width, box_height), pygame.SRCALPHA)
        box.fill(color_value(style["dialog_background"]))
        border = style["dialog_border_width"]
        if border:
            pygame.draw.rect(box, color_value(style["dialog_border"]), box.get_rect(), border)
        text_color = color_value(style["dialog_text"])
        y = 22
        for line in lines:
            box.blit(font.render(line, True, text_color), (20, y))
            y += line_height
        if is_input:
            entry_rect = pygame.Rect(20, y + 10, box_width - 40, line_height + 12)
            pygame.draw.rect(box, color_value(style["dialog_field"]), entry_rect)
            cursor = len(value) if cursor is None else cursor
            text_left = entry_rect.x + 8
            visible_width = entry_rect.width - 16
            prefix_width = font.size(value[:cursor])[0]
            offset = max(0, prefix_width - visible_width)
            accent = color_value(style["dialog_accent"])
            if anchor is not None and anchor != cursor:
                first, last = sorted((anchor, cursor))
                selection_left = text_left + font.size(value[:first])[0] - offset
                selection_right = text_left + font.size(value[:last])[0] - offset
                selection = pygame.Rect(
                    max(text_left, selection_left), entry_rect.y + 6,
                    max(0, min(entry_rect.right - 2, selection_right) - max(text_left, selection_left)),
                    line_height,
                )
                pygame.draw.rect(box, tuple(int(a * 0.5 + b * 0.5) for a, b in
                                            zip(accent, color_value(style["dialog_field"]))), selection)
            box.set_clip(entry_rect)
            box.blit(font.render(value, True, text_color), (text_left - offset, entry_rect.y + 6))
            caret_x = text_left + prefix_width - offset
            if caret_visible:
                pygame.draw.line(box, accent, (caret_x, entry_rect.y + 4), (caret_x, entry_rect.bottom - 5), 2)
            box.set_clip(None)
            y = entry_rect.bottom
            hint = "enter to accept  |  esc to cancel  |  ctrl+a selects all"
        else:
            hint = "press any key or click to continue"
        if style["dialog_hints"]:
            box.blit(hint_font.render(hint, True, color_value(style["dialog_hint"])), (20, y + 12))
        left = (width - box_width) // 2
        place = style["dialog_position"]
        top = 20 if place == "top" else (height - box_height - 20 if place == "bottom" else (height - box_height) // 2)
        top = max(10, top)
        animation = style["dialog_animation"]
        if progress < 1.0 and animation != "none":
            eased = 1 - (1 - progress) ** 3
            if animation == "pop":
                scale = 0.86 + 0.14 * (1 + 2.70158 * (progress - 1) ** 3 + 1.70158 * (progress - 1) ** 2)
                scaled = pygame.transform.smoothscale(box, (max(1, int(box_width * scale)),
                                                            max(1, int(box_height * scale))))
                scaled.set_alpha(int(255 * min(1.0, progress * 1.6)))
                target.blit(scaled, (left + (box_width - scaled.get_width()) // 2,
                                     top + (box_height - scaled.get_height()) // 2))
            elif animation == "slide":
                distance = 40 if place != "top" else -40
                box.set_alpha(int(255 * eased))
                target.blit(box, (left, top + int(distance * (1 - eased))))
            else:
                box.set_alpha(int(255 * eased))
                target.blit(box, (left, top))
        else:
            target.blit(box, (left, top))
        self._dialog_rect = pygame.Rect(left, top, box_width, box_height)
        if target is not self.screen:
            self._blit_gl_surface(target)
        pygame.display.flip()

    def _open_dialog(self, message, is_input=False):
        """play the popup's opening animation and its soft sound."""
        style = self.style
        if style["dialog_sound"]:
            try:
                self._soft_tone(880, 0.09)
            except (ValueError, pygame.error):
                pass
        if style["dialog_animation"] == "none":
            return
        started = time.monotonic()
        while self.running and not self.shouldstop():
            progress = min(1.0, (time.monotonic() - started) / 0.2)
            pygame.event.pump()
            self._draw_dialog(message, "", is_input=is_input, progress=progress)
            if progress >= 1.0:
                break
            pygame.time.wait(12)

    def _soft_tone(self, frequency, seconds):
        """a quiet sine blip (popups use it)."""
        self._ensure_audio()
        sound = self._beep_sound(frequency, seconds, "sine")
        channel = sound.play()
        if channel:
            channel.set_volume(self.audio_volume * 0.35)

    def _show_popup(self, message):
        if not self.screen:
            if self.onpopup:
                self.onpopup(message)
                if not self.running or self.shouldstop():
                    raise _Stop()
                return
            raise ValueError("add 'mode 2d' or 'mode 3d' before showing a popup")
        pygame.event.clear()
        self._open_dialog(message)
        self._draw_dialog(message)
        while self.running and not self.shouldstop():
            event = pygame.event.wait(100)
            if event.type == pygame.QUIT:
                self.running = False
                return
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                return

    @staticmethod
    def _edit_input_event(value, cursor, anchor, event):
        if event.type == pygame.TEXTINPUT:
            text = event.text
            start, end = sorted((anchor, cursor)) if anchor is not None else (cursor, cursor)
            text = text[:max(0, 2000 - (len(value) - (end - start)))]
            value = value[:start] + text + value[end:]
            cursor = start + len(text)
            return value, cursor, None, None
        if event.type != pygame.KEYDOWN:
            return value, cursor, anchor, None

        key = event.key
        modifiers = getattr(event, "mod", 0)
        selecting = bool(modifiers & pygame.KMOD_SHIFT)
        control = bool(modifiers & pygame.KMOD_CTRL)
        if control and key == pygame.K_a:
            return value, len(value), 0, None
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return value, cursor, anchor, "accept"
        if key == pygame.K_ESCAPE:
            return value, cursor, anchor, "cancel"
        if key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_HOME, pygame.K_END):
            if not selecting and anchor is not None and key in (pygame.K_LEFT, pygame.K_RIGHT):
                cursor = min(anchor, cursor) if key == pygame.K_LEFT else max(anchor, cursor)
                return value, cursor, None, None
            if selecting and anchor is None:
                anchor = cursor
            if key == pygame.K_LEFT:
                cursor = max(0, cursor - 1)
            elif key == pygame.K_RIGHT:
                cursor = min(len(value), cursor + 1)
            elif key == pygame.K_HOME:
                cursor = 0
            else:
                cursor = len(value)
            return value, cursor, anchor if selecting else None, None

        start, end = sorted((anchor, cursor)) if anchor is not None else (cursor, cursor)
        if key == pygame.K_BACKSPACE:
            if start == end and start:
                start -= 1
            value = value[:start] + value[end:]
            cursor = start
            anchor = None
        elif key == pygame.K_DELETE:
            if start == end and end < len(value):
                end += 1
            value = value[:start] + value[end:]
            cursor = start
            anchor = None
        return value, cursor, anchor, None

    def _ask_input(self, message):
        if not self.screen:
            if self.oninput:
                answer = self.oninput(message)
                if not self.running or self.shouldstop():
                    raise _Stop()
                return "" if answer is None else str(answer)
            raise ValueError("add 'mode 2d' or 'mode 3d' before asking for input")
        pygame.event.clear()
        value = ""
        cursor = 0
        anchor = None
        caret_visible = True
        last_blink = time.monotonic()
        try:
            pygame.key.start_text_input()
            pygame.key.set_repeat(400, 35)
            self._open_dialog(message, is_input=True)
            self._draw_dialog(message, value, is_input=True, cursor=cursor)
            if hasattr(pygame.key, "set_text_input_rect") and getattr(self, "_dialog_rect", None):
                pygame.key.set_text_input_rect(self._dialog_rect)
            while self.running and not self.shouldstop():
                event = pygame.event.wait(100)
                if event.type == pygame.QUIT:
                    self.running = False
                    return ""
                value, cursor, anchor, action = self._edit_input_event(value, cursor, anchor, event)
                if action == "accept":
                    return value
                if action == "cancel":
                    return ""
                now = time.monotonic()
                if now - last_blink >= 0.5:
                    caret_visible = not caret_visible
                    last_blink = now
                if event.type != pygame.NOEVENT or now - last_blink < 0.01:
                    self._draw_dialog(
                        message, value, is_input=True, cursor=cursor, anchor=anchor,
                        caret_visible=caret_visible
                    )
            return ""
        finally:
            if self._focus is None:  # a textbox that has the typing cursor keeps getting letters
                pygame.key.stop_text_input()
                pygame.key.set_repeat()

    # ----- helpers for commands ---------------------------------------------------
    def _name(self, token):
        """object names may contain {expressions}: box enemy{i} 0 0 10 10"""
        name = str(token)
        if "{" in name:
            name = self._interpolate(name)
        return name

    def _object(self, name, kinds=None, action="use"):
        name = self._name(name)
        obj = self.objects.get(name)
        if obj is None:
            obj = self.objects.get("button:" + name)
        if not isinstance(obj, dict):
            raise ValueError(f"object '{name}' does not exist yet")
        if kinds and obj["type"] not in kinds:
            raise ValueError(f"can't {action} a {obj['type']}")
        return obj

    def _color_from(self, tokens):
        if len(tokens) == 3:
            channels = tuple(int(self._num(token, "color channel")) for token in tokens)
            if any(not 0 <= channel <= 255 for channel in channels):
                raise ValueError("color channels go from 0 to 255")
            return channels
        token = tokens[0]
        braced = isinstance(token, str) and token.startswith("{") and token.endswith("}")
        if not isinstance(token, QuotedText) and (token in self.vars or braced):
            value = self.vars[token] if token in self.vars else self.val(token)
            if isinstance(value, list) and len(value) in (3, 4):
                return tuple(max(0, min(255, int(channel))) for channel in value[:3])
            return format_value(value)
        return str(token)

    def _fetched(self, relative_path, base_dir=None):
        """ask fetchfile for a file (a live session guest gets it from the host). None when there is no copy."""
        if self.fetchfile is None:
            return None
        relative = str(relative_path)
        if base_dir is not None and os.path.abspath(base_dir) != self.base_dir:
            relative = os.path.relpath(os.path.join(base_dir, relative), self.base_dir)
        try:
            path = self.fetchfile(relative.replace(os.sep, "/"))
        except Exception:  # noqa: BLE001 - a network problem is reported as "not found"
            return None
        return path if path and os.path.isfile(path) else None

    def _media_path(self, relative_path, what):
        path = os.path.abspath(os.path.join(self.base_dir, relative_path))
        path = self._fetched(relative_path) or path
        if not os.path.isfile(path):
            raise ValueError(f"{what} file '{relative_path}' was not found")
        return path

    def _load_audio_path(self, relative_path):
        return self._media_path(relative_path, "audio")

    def _load_image(self, relative_path, what):
        path = self._media_path(relative_path, what)
        surface = self._image_cache.get(path)
        if surface is None:
            try:
                surface = pygame.image.load(path)
                try:
                    surface = surface.convert_alpha()
                except pygame.error:  # a 3d (opengl) window has no 2d pixel format to convert to
                    surface = surface.convert_alpha(pygame.Surface((1, 1), pygame.SRCALPHA))
            except (OSError, pygame.error) as err:
                raise ValueError(f"could not load {what} '{relative_path}': {str(err).lower()}") from err
            self._image_cache[path] = surface
        return surface

    def _ensure_audio(self):
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init()
            except pygame.error as err:
                raise ValueError("audio could not start; check that an audio device is available") from err
        pygame.mixer.music.set_volume(self.audio_volume)
        self.audio_initialized = True

    def _sleep(self, seconds):
        deadline = time.perf_counter() + max(0.0, seconds)
        while True:
            if not self.running or self.shouldstop():
                raise _Stop()
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return
            if self.screen is not None:
                self.pumpevents()
            time.sleep(min(remaining, 0.01))

    def _set_target(self, target, value):
        if re.fullmatch(r"[A-Za-z_]\w*", target):
            if target in self.constants:
                raise ValueError(f"'{target}' is a constant (made with const), so it can't be changed")
            self.vars[target] = value
            return
        node = parse_expression(target)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            name, field = node.value.id, node.attr
            if name in self.vars:
                base = self.vars[name]
                if isinstance(base, (Vector2, Vector3)):
                    parts = dict(zip(("x", "y", "z"), self._components(base)))
                    if field not in parts:
                        raise ValueError(f"this vector has no '{field}' part")
                    parts[field] = value
                    self.vars[name] = type(base)(*parts.values())
                    return
                if isinstance(base, dict):
                    base[field] = value
                    return
                if not (isinstance(base, str) and (base in self.objects or ("button:" + base) in self.objects)):
                    raise ValueError(f"'{name}' has no parts to set")
                name = base  # the variable holds an object's name
            obj = self._object(name)
            field = self._FIELD_ALIASES.get(field, field)
            if field == "visible":
                obj["hidden"] = not self._truthy(value)
                return
            if field == "color":
                obj["color"] = value
                return
            if field == "text" and obj["type"] in ("text", "textbox"):
                obj["text"] = format_value(value)
                if obj["type"] == "textbox":
                    obj["cursor"], obj["anchor"] = len(obj["text"]), None
                return
            if field in ("hint", "label") and field in obj:
                obj[field] = format_value(value)
                return
            if field == "value" and obj["type"] == "slider":
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{name}.value must be a number")
                low, high = sorted((obj["min"], obj["max"]))
                obj["value"] = max(low, min(high, value))
                return
            if field == "checked" and obj["type"] == "checkbox":
                obj["checked"] = self._truthy(value)
                return
            if field in ("vx", "vy", "vz") and "x" in obj:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{name}.{field} must be a number")
                if field == "vz" and value and obj["type"] not in SHAPES_3D:
                    raise ValueError("only 3d shapes can move along z")
                for key in ("vx", "vy", "vz"):
                    obj.setdefault(key, 0)
                obj[field] = value
                return
            if obj["type"] in ("block", "cylinder", "cone", "plane") and field in ("w", "h", "d", "r"):
                if field not in obj:
                    raise ValueError(f"a {obj['type']} has no '{field}'")
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                    raise ValueError("sizes must be numbers greater than zero")
                obj[field] = value
                return
            if field in ("rx", "rz") and obj["type"] in SHAPES_3D:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{name}.{field} must be a number")
                obj[field] = value
                return
            if field in ("w", "h", "r", "size") or (field == "r" and obj["type"] == "sphere"):
                current = {f: self._object_field(name, f) for f in ("w", "h") if obj["type"] in ("sprite", "image", "box", "button")}
                current[field] = value
                self._resize(obj, current.get("w", value), current.get("h", value))
                return
            if field in ("x", "y", "z", "angle") and field in obj:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{name}.{field} must be a number")
                if obj["type"] == "line" and field in ("x", "y"):
                    obj[field + "2"] += value - obj[field]
                obj[field] = value
                return
            raise ValueError(f"can't set '{field}' on {obj['type']} '{name}'")
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            container = self.vars.get(node.value.id)
            index = self._eval(node.slice, lenient=isinstance(container, dict))
            if isinstance(container, dict):
                container[format_value(index)] = value
                return
            if isinstance(container, list):
                if isinstance(index, bool) or not isinstance(index, int):
                    raise ValueError("list positions must be whole numbers")
                if index == len(container):
                    container.append(value)
                    return
                try:
                    container[index] = value
                except IndexError as err:
                    raise ValueError(f"position {index} is past the end (length {len(container)})") from err
                return
            raise ValueError(f"'{node.value.id}' is not a list or map")
        raise ValueError("write assignments as: set name = value")

    def _resize(self, obj, width, height):
        for value in (width, height):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ValueError("sizes must be numbers greater than zero")
        kind = obj["type"]
        if kind in ("box", "button", "ellipse", "polygon"):
            obj["w"], obj["h"] = width, height
        elif kind in ("textbox", "slider"):
            obj["w"] = width
        elif kind == "circle":
            obj["r"] = width
        elif kind == "cube":
            obj["size"] = width
        elif kind == "sphere":
            obj["radius"] = width
        elif kind == "block":
            obj["w"], obj["h"] = width, height
        elif kind in ("cylinder", "cone"):
            obj["r"], obj["h"] = width, height
        elif kind == "plane":
            obj["w"], obj["d"] = width, height
        elif kind == "text":
            obj["size"] = width
        elif kind in ("sprite", "image"):
            source = obj.get("source", obj["surface"])
            obj["source"] = source
            obj["surface"] = pygame.transform.scale(source, (int(width), int(height)))
        else:
            raise ValueError(f"can't resize a {kind}")

    # ----- commands --------------------------------------------------------------
    def _c_print(self, statement):
        arguments = _split_top_level_commas(statement.rest)
        if len(arguments) > 1:
            values = [self._eval_value(argument, split_command(argument)) for argument in arguments]
            self.onlog(" ".join(format_value(value) for value in values))
            return
        self.onlog(self._text(statement.parts[1:]))

    def _c_local(self, statement):
        rest = statement.rest.strip()
        match = _SET_RE.match(rest)
        if match:
            name, raw = match.groups()
            value = self._eval_value(raw, split_command(raw))
        else:
            name, value = rest, None
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            raise ValueError("write it as: local name = value")
        if name in self.constants:
            raise ValueError(f"'{name}' is a constant (made with const), so it can't be changed")
        if self._local_frames:
            frame = self._local_frames[-1]
            if name not in frame:
                frame[name] = (name in self.vars, self.vars.get(name))
        self.vars[name] = value

    def _c_set(self, statement):
        match = _SET_RE.match(statement.rest)
        if not match or len(statement.parts) < 3:
            raise ValueError("write assignments as: set name = value")
        target, raw_value = match.groups()
        tokens = split_command(raw_value)
        self._set_target(target, self._eval_value(raw_value, tokens))

    def _arithmetic(self, statement, operator):
        name = statement.parts[1]
        compound = "." in name or "[" in name
        if compound:
            try:
                left = self._eval(parse_expression(name))
            except (SyntaxError, ValueError, KeyError, IndexError, TypeError) as err:
                raise ValueError(f"can't read '{name}': {err}") from err
        elif name not in self.vars:
            raise ValueError(f"'{name}' doesn't exist yet. start it with: set {name} = 0")
        else:
            left = self.vars[name]
        raw = statement.rest.split(None, 1)[1] if len(statement.rest.split(None, 1)) > 1 else ""
        amount = self._eval_value(raw, statement.parts[2:])

        def store(value):
            if compound or name in self.constants:
                self._set_target(name, value)
            else:
                self.vars[name] = value

        if isinstance(left, bool) or isinstance(amount, bool):
            raise ValueError(f"{statement.cmd} needs numbers, not true/false")
        if operator is ast.Add and isinstance(left, str):
            store(left + format_value(amount))
            return
        if operator is ast.Add and isinstance(left, list):
            left.append(amount)
            return
        numeric = (int, float)
        if not (isinstance(left, numeric) or isinstance(left, (Vector2, Vector3))):
            raise ValueError(f"{statement.cmd} needs a number variable, but '{name}' is {kind_of(left)}")
        if not isinstance(amount, numeric) and not isinstance(amount, (Vector2, Vector3)):
            raise ValueError(f"{statement.cmd} needs a numeric value, got '{format_value(amount)}'")
        store(self._binary(operator(), left, amount))

    def _c_add(self, statement):
        self._arithmetic(statement, ast.Add)

    def _c_sub(self, statement):
        self._arithmetic(statement, ast.Sub)

    def _c_mul(self, statement):
        self._arithmetic(statement, ast.Mult)

    def _c_div(self, statement):
        self._arithmetic(statement, ast.Div)

    def _c_calc(self, statement):
        pieces = statement.rest.split(None, 1)
        if len(pieces) < 2:
            raise ValueError("write a math expression, like: calc total price * 2")
        try:
            node = parse_expression(pieces[1])
        except (SyntaxError, ValueError) as err:
            raise ValueError("write a valid math expression") from err
        self._set_target(statement.parts[1], self._eval(node))

    def _c_random(self, statement):
        minimum, maximum = self.val(statement.parts[2]), self.val(statement.parts[3])
        if type(minimum) not in (int, float) or type(maximum) not in (int, float):
            raise ValueError("random needs numeric minimum and maximum values")
        if minimum > maximum:
            raise ValueError("random minimum cannot be greater than its maximum")
        self.vars[statement.parts[1]] = (
            random.randint(minimum, maximum)
            if type(minimum) is int and type(maximum) is int
            else random.uniform(minimum, maximum)
        )

    def _c_time(self, statement):
        self.vars[statement.parts[1]] = time.monotonic() - self.started_at

    def _c_wait(self, statement):
        self._sleep(float(self._num(statement.parts[1], "wait time")))

    def _c_call(self, statement):
        if statement.call_source:
            if statement.cache is None:
                statement.cache = parse_expression(statement.call_source)
            self._eval(statement.cache)
            return
        arguments = [self.val(argument) for argument in statement.parts[2:]]
        self._call_function(statement.parts[1], arguments)

    def _c_include(self, statement):
        raise ValueError("include must be at the start of a line in a saved script")

    def _c_list(self, statement):
        self.vars[statement.parts[1]] = [self.val(token) for token in statement.parts[2:]]

    def _c_append(self, statement):
        items = self.vars.get(statement.parts[1])
        if not isinstance(items, list):
            raise ValueError(f"list '{statement.parts[1]}' does not exist yet")
        tokens = statement.parts[2:]
        items.append(self.val(tokens[0]) if len(tokens) == 1 else self._val_text(" ".join(tokens)))

    def _c_item(self, statement):
        items = self.vars.get(statement.parts[1])
        if not isinstance(items, list):
            raise ValueError(f"list '{statement.parts[1]}' does not exist yet")
        index = self.val(statement.parts[2])
        if not isinstance(index, int) or isinstance(index, bool):
            raise ValueError("list indexes must be whole numbers")
        try:
            self.vars[statement.parts[3]] = items[index]
        except IndexError as err:
            raise ValueError(f"list index {index} is out of range") from err

    def _c_length(self, statement):
        value = self.val(statement.parts[1])
        if not isinstance(value, (str, list, dict)):
            raise ValueError("length needs a text value, list or map")
        self.vars[statement.parts[2]] = len(value)

    def _c_map(self, statement):
        self.vars[statement.parts[1]] = {}

    def _c_put(self, statement):
        values = self.vars.get(statement.parts[1])
        if not isinstance(values, dict):
            raise ValueError(f"map '{statement.parts[1]}' does not exist yet")
        tokens = statement.parts[3:]
        values[str(statement.parts[2])] = self.val(tokens[0]) if len(tokens) == 1 else self._val_text(" ".join(tokens))

    def _c_lookup(self, statement):
        values = self.vars.get(statement.parts[1])
        if not isinstance(values, dict):
            raise ValueError(f"map '{statement.parts[1]}' does not exist yet")
        key = str(statement.parts[2])
        if key not in values:
            raise ValueError(f"map '{statement.parts[1]}' has no key '{key}'")
        self.vars[statement.parts[3]] = values[key]

    def _c_has(self, statement):
        values = self.vars.get(statement.parts[1])
        if not isinstance(values, dict):
            raise ValueError(f"map '{statement.parts[1]}' does not exist yet")
        self.vars[statement.parts[3]] = str(statement.parts[2]) in values

    def _c_delete(self, statement):
        name = self._name(statement.parts[1])
        if len(statement.parts) == 2:
            if name in self.objects and name != "uibtn":
                obj = self.objects.pop(name)
                if self._focus == name:
                    self._set_focus(None)
                if isinstance(obj, dict) and obj.get("texture") is not None and self.mode == "3d":
                    try:
                        glDeleteTextures([obj["texture"]])
                    except Exception:
                        pass
                return
            if "button:" + name in self.objects:
                del self.objects["button:" + name]
                return
            if name in self.vars:
                del self.vars[name]
                return
            raise ValueError(f"there is no object named '{name}' to delete")
        container = self.vars.get(name)
        if isinstance(container, list):
            index = self.val(statement.parts[2])
            if not isinstance(index, int) or isinstance(index, bool):
                raise ValueError("list positions must be whole numbers")
            try:
                del container[index]
            except IndexError as err:
                raise ValueError(f"list index {index} is out of range") from err
        elif isinstance(container, dict):
            key = str(statement.parts[2])
            if key not in container:
                raise ValueError(f"map '{name}' has no key '{key}'")
            del container[key]
        else:
            raise ValueError(f"'{name}' is not a list or map")

    def _list_named(self, token):
        name = str(token)
        items = self.vars.get(name)
        if not isinstance(items, list):
            raise ValueError(f"list '{name}' does not exist yet")
        return items

    def _value_from(self, tokens):
        return self.val(tokens[0]) if len(tokens) == 1 else self._val_text(" ".join(str(t) for t in tokens))

    def _c_insert(self, statement):
        items = self._list_named(statement.parts[1])
        index = self.val(statement.parts[2])
        if isinstance(index, bool) or not isinstance(index, int):
            raise ValueError("list positions must be whole numbers")
        if not -len(items) <= index <= len(items):
            raise ValueError(f"position {index} is past the end (length {len(items)})")
        items.insert(index, self._value_from(statement.parts[3:]))

    def _c_remove(self, statement):
        items = self._list_named(statement.parts[1])
        value = self._value_from(statement.parts[2:])
        if value in items:
            items.remove(value)

    def _c_shuffle(self, statement):
        random.shuffle(self._list_named(statement.parts[1]))

    def _c_sort(self, statement):
        items = self._list_named(statement.parts[1])
        extra = statement.parts[2:]
        if extra and (len(extra) != 1 or extra[0] != "reverse"):
            raise ValueError("use: sort <list>  or  sort <list> reverse")
        try:
            items.sort(reverse=bool(extra))
        except TypeError as err:
            raise ValueError("sort needs a list of all numbers or all text") from err

    # ----- saving --------------------------------------------------------------------------------------------
    def _save_path(self):
        return os.path.join(saves_folder(), save_file_name(self.save_name))

    def _save_key(self, value):
        key = value if isinstance(value, str) else format_value(value)
        key = key.strip()
        if not key:
            raise ValueError("give the saved value a name")
        if len(key) > 100:
            raise ValueError("saved names can be at most 100 letters long")
        return key

    def _saves_data(self):
        if self._saves is None:
            self._saves = {}
            try:
                with open(self._save_path(), "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    self._saves = data
            except (OSError, ValueError):
                pass
        return self._saves

    def _flush_saves(self, quiet=False):
        if not self._saves_dirty or self._saves is None:
            return
        path = self._save_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            temporary = path + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(self._saves, handle, indent=1, ensure_ascii=False)
            os.replace(temporary, path)
        except OSError as err:
            if not quiet:
                raise ValueError(f"could not save: {str(err).lower()}") from err
            self.onlog(f"could not save: {str(err).lower()}")
            return
        self._saves_dirty = False
        self._saves_written = time.monotonic()

    def _saves_changed(self):
        self._saves_dirty = True
        # write at most once a second; whatever is left is written when the program ends
        if time.monotonic() - self._saves_written >= 1.0:
            self._flush_saves()

    def _storable(self, value, depth=0):
        if depth > 32:
            raise ValueError("that value is nested too deeply to save")
        if value is None or isinstance(value, (bool, str)):
            return value
        if isinstance(value, (int, float)):
            if not math.isfinite(value):
                raise ValueError("only finite numbers can be saved")
            return value
        if isinstance(value, list):
            return [self._storable(item, depth + 1) for item in value]
        if isinstance(value, dict):
            return {str(key): self._storable(item, depth + 1) for key, item in value.items()}
        if isinstance(value, Vector2):
            return {"$vec2": [value.x, value.y]}
        if isinstance(value, Vector3):
            return {"$vec3": [value.x, value.y, value.z]}
        raise ValueError(f"can't save {kind_of(value)} values")

    def _restored(self, value):
        if isinstance(value, list):
            return [self._restored(item) for item in value]
        if isinstance(value, dict):
            if len(value) == 1 and ("$vec2" in value or "$vec3" in value):
                parts = value.get("$vec2") or value.get("$vec3")
                if isinstance(parts, list) and len(parts) in (2, 3):
                    return (Vector2 if len(parts) == 2 else Vector3)(*parts)
            return {key: self._restored(item) for key, item in value.items()}
        return value

    def _c_save(self, statement):
        key = self._save_key(self._name(statement.parts[1]))
        stored = self._storable(self._value_from(statement.parts[2:]))
        if len(json.dumps(stored)) > MAX_SAVED_VALUE:
            raise ValueError("a saved value can be at most 256 kb")
        saves = self._saves_data()
        if key not in saves and len(saves) >= MAX_SAVED_NAMES:
            raise ValueError(f"a program can save at most {MAX_SAVED_NAMES} names")
        saves[key] = stored
        self._saves_changed()

    def _c_load(self, statement):
        key = self._save_key(self._name(statement.parts[1]))
        saves = self._saves_data()
        if key in saves:
            value = self._restored(saves[key])
        elif len(statement.parts) > 3:
            value = self._value_from(statement.parts[3:])
        else:
            value = 0
        self._set_target(statement.parts[2], value)

    def _c_forget(self, statement):
        saves = self._saves_data()
        if len(statement.parts) == 2 and statement.parts[1] == "all":
            if not saves:
                return
            saves.clear()
        else:
            key = self._save_key(self._name(statement.parts[1]))
            if key not in saves:
                return
            del saves[key]
        self._saves_changed()

    # ----- discord status ------------------------------------------------------------------------------------
    def presence_activity(self):
        """the discord activity built from the presence lines that have run, or None."""
        state = self.presence
        activity = {key: state[key] for key in ("details", "state") if state.get(key)}
        assets = {key: state[key] for key in ("large_image", "large_text", "small_image", "small_text")
                  if state.get(key)}
        if assets:
            activity["assets"] = assets
        timestamps = {key: state[key] for key in ("start", "end") if state.get(key)}
        if timestamps:
            activity["timestamps"] = timestamps
        if state.get("party"):
            activity["party"] = {"id": "gublan-party", "size": list(state["party"])}
        if state.get("buttons"):
            activity["buttons"] = [dict(button) for button in state["buttons"]]
        return activity or None

    def _c_presence(self, statement):
        parts = statement.parts
        problem = _presence_problem(parts[1:])
        if problem:
            raise ValueError(problem)
        what, rest = str(parts[1]).lower(), parts[2:]
        state = self.presence
        if what in ("details", "state"):
            text = self._text(rest).strip() if rest else ""
            if text:
                state[what] = text[:128]
            else:
                state.pop(what, None)
        elif what in ("image", "smallimage"):
            size = "large" if what == "image" else "small"
            if not rest:
                state.pop(f"{size}_image", None)
                state.pop(f"{size}_text", None)
            else:
                state[f"{size}_image"] = format_value(self._val_text(rest[0])).strip()
                hover = self._text(rest[1:]).strip() if len(rest) > 1 else ""
                if hover:
                    state[f"{size}_text"] = hover[:128]
                else:
                    state.pop(f"{size}_text", None)
        elif what == "button":
            if not rest:
                state.pop("buttons", None)
            else:
                address = format_value(self._val_text(rest[0])).strip()
                if not address.lower().startswith(("https://", "http://")) or " " in address:
                    raise ValueError("the button needs a web address that starts with https://")
                label = self._text(rest[1:]).strip()[:32]
                buttons = [button for button in state.get("buttons", []) if button["label"] != label]
                if len(buttons) >= 2:
                    raise ValueError("discord shows at most two buttons. use presence button to remove them")
                buttons.append({"label": label, "url": address})
                state["buttons"] = buttons
        elif what == "party":
            players, most = int(self._num(rest[0], "players")), int(self._num(rest[1], "most players"))
            if players < 1 or most < players:
                raise ValueError("use presence party <players> <most-players>, like presence party 1 4")
            state["party"] = (players, most)
        elif what == "timer":
            state.pop("end", None)
            if rest:
                state.pop("start", None)
            else:
                state["start"] = int(time.time())
        elif what == "countdown":
            seconds = self._num(rest[0], "countdown seconds")
            state.pop("start", None)
            if seconds > 0:
                state["end"] = int(time.time() + seconds)
            else:
                state.pop("end", None)
        elif what == "app":
            application = format_value(self._val_text(rest[0])).strip()
            if not (application.isdigit() and 15 <= len(application) <= 22):
                raise ValueError("a discord application id is a long number from the discord developer portal")
            self.presence_app = application
        elif what == "clear":
            state.clear()
        self._send_presence()

    def _send_presence(self):
        activity = self.presence_activity()
        sent = (self.presence_app, activity)
        if sent == self._presence_sent:
            return
        self._presence_sent = sent
        if self.onpresence is not None:
            self.onpresence(self.presence_app, activity)
            return
        client = self._presence_client
        if client is None:
            if activity is None:
                return
            try:
                from gublanpresence import DEFAULT_APPLICATION_ID, PresenceClient
            except ImportError:
                if not self._presence_warned:
                    self._presence_warned = True
                    self.onlog("discord status is not available in this copy of gublan")
                return
            client = self._presence_client = PresenceClient(self.presence_app or DEFAULT_APPLICATION_ID)
        if self.presence_app:
            client.set_application(self.presence_app)
        client.update(activity)

    def _close_presence(self):
        client, self._presence_client = self._presence_client, None
        if client is not None:
            try:
                client.close(timeout=1.5)
            except Exception:  # noqa: BLE001 - discord going away never stops a program from closing
                pass

    def _c_cursor(self, statement):
        choice = str(statement.parts[1]).lower()
        if choice not in ("show", "hide") or len(statement.parts) > 2:
            raise ValueError("use: cursor show  or  cursor hide")
        self.cursor_visible = choice == "show"
        if self.screen is not None:
            pygame.mouse.set_visible(self.cursor_visible)

    def _c_mode(self, statement):
        if statement.parts[1] not in ("2d", "3d"):
            raise ValueError("choose either 2d or 3d")
        self.initstage(statement.parts[1])

    def _c_window(self, statement):
        width = int(self._num(statement.parts[1], "window width"))
        height = int(self._num(statement.parts[2], "window height"))
        if not (120 <= width <= 4000 and 90 <= height <= 4000):
            raise ValueError("window size must be between 120x90 and 4000x4000")
        self.window_size = (width, height)
        if len(statement.parts) > 3:
            self.window_title = self._label(statement.parts[3:])
        if self.screen:
            self.initstage(self.mode)
        else:
            self.vars["screen_width"], self.vars["screen_height"] = width, height

    def _c_title(self, statement):
        self.window_title = self._label(statement.parts[1:])
        if self.screen:
            pygame.display.set_caption(self.window_title)

    def _c_background(self, statement):
        self.background = color_value(self._color_from(statement.parts[1:]))

    def _c_color(self, statement):
        self.activecolor = self._color_from(statement.parts[1:])

    def _c_paint(self, statement):
        color = self._color_from(statement.parts[2:])
        if statement.parts[1] == "all":  # paint all <color>
            for name, obj in self.objects.items():
                if name != "uibtn":
                    obj["color"] = color
            return
        self._object(statement.parts[1])["color"] = color

    def _c_clear(self, statement):
        self.render()

    def _c_frame(self, statement):
        if self.screen:
            self.pumpevents()
            self.render()
        else:
            self._tick_effects()
        self._frame_clicks, self._clicks = self._clicks, []
        self._frames_drawn += 1
        target = 1.0 / max(1, self.target_fps)
        deadline = self._last_frame + target
        now = time.perf_counter()
        if deadline > now:
            self._sleep(deadline - now)
        now = time.perf_counter()
        self.vars["dt"] = min(0.25, now - self._last_frame)
        self._last_frame = now if now - deadline > target else max(deadline, now - target)

    def _c_fps(self, statement):
        value = self._num(statement.parts[1], "fps")
        if not 1 <= value <= 1000:
            raise ValueError("fps must be between 1 and 1000")
        self.target_fps = value

    def _c_textsize(self, statement):
        value = self._num(statement.parts[1], "text size")
        if not 6 <= value <= 300:
            raise ValueError("text size must be between 6 and 300")
        self.text_size = int(value)

    def _c_scroll(self, statement):
        self.scroll = (float(self._num(statement.parts[1], "scroll x")),
                       float(self._num(statement.parts[2], "scroll y")))

    def _c_shake(self, statement):
        strength = self._num(statement.parts[1], "shake strength")
        seconds = self._num(statement.parts[2], "shake time") if len(statement.parts) > 2 else 0.3
        if strength < 0 or seconds < 0:
            raise ValueError("shake strength and time can't be negative")
        self._shake = [float(strength), float(seconds), float(seconds)] if strength and seconds else None
        if not self._shake:
            self._shake_offset = (0.0, 0.0)

    def _c_ellipse(self, statement):
        parts = statement.parts
        self.objects[self._name(parts[1])] = {
            "type": "ellipse",
            "x": self._num(parts[2], "ellipse x"), "y": self._num(parts[3], "ellipse y"),
            "w": self._num(parts[4], "ellipse width"), "h": self._num(parts[5], "ellipse height"),
            "color": self.activecolor,
        }

    def _c_polygon(self, statement):
        parts = statement.parts
        values = [self._num(part, "polygon point") for part in parts[2:]]
        if len(values) % 2:
            raise ValueError("polygon points come in pairs: x y x y x y")
        if len(values) < 6:
            raise ValueError("a polygon needs at least three points")
        if len(values) > 512:
            raise ValueError("a polygon can have up to 256 points")
        xs, ys = values[0::2], values[1::2]
        left, top = min(xs), min(ys)
        width, height = max(1.0, max(xs) - left), max(1.0, max(ys) - top)
        self.objects[self._name(parts[1])] = {
            "type": "polygon", "x": left, "y": top, "w": width, "h": height,
            "points": [(x - left, y - top) for x, y in zip(xs, ys)], "pw": width, "ph": height,
            "color": self.activecolor,
        }

    def _c_particles(self, statement):
        parts = statement.parts
        x, y = self._num(parts[1], "particles x"), self._num(parts[2], "particles y")
        count = int(self._num(parts[3], "particle count")) if len(parts) > 3 else 20
        speed = self._num(parts[4], "particle speed") if len(parts) > 4 else 160
        if not 0 <= count <= 500:
            raise ValueError("particles can make from 0 to 500 at a time")
        color = color_value(self.activecolor)
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            velocity = speed * random.uniform(0.25, 1.0)
            life = random.uniform(0.45, 1.0)
            self._particles.append([float(x), float(y), math.cos(angle) * velocity, math.sin(angle) * velocity,
                                    life, life, color, random.uniform(3, 6)])
        if len(self._particles) > 2000:
            del self._particles[:len(self._particles) - 2000]

    _TWEEN_FIELDS = {"x": "x", "y": "y", "z": "z", "w": "w", "width": "w", "h": "h", "height": "h", "r": "r",
                     "radius": "r", "angle": "angle", "rotation": "angle", "opacity": "alpha", "alpha": "alpha",
                     "size": "size", "d": "d", "depth": "d", "rx": "rx", "rz": "rz"}

    def _c_tween(self, statement):
        parts = statement.parts
        obj = self._object(parts[1], action="tween")
        field = str(parts[2]).lower()
        key = self._TWEEN_FIELDS.get(field)
        sized = obj["type"] in ("sprite", "image") and key in ("w", "h")
        allowed = key is not None and (key in obj or key == "alpha" or sized
                                       or (key == "angle" and obj["type"] in ("sprite", "image")))
        if not allowed:
            raise ValueError(f"tween can change x, y, w, h, r, angle or opacity of a {obj['type']}, not '{field}'")
        target = self._num(parts[3], "tween value")
        seconds = self._num(parts[4], "tween time")
        if seconds < 0:
            raise ValueError("tween time can't be negative")
        easing = str(parts[5]).lower() if len(parts) > 5 else "inout"
        if easing not in EASINGS:
            raise ValueError(f"'{easing}' is not an easing. try: {', '.join(EASINGS)}")
        if sized:
            start = obj["surface"].get_size()[0 if key == "w" else 1]
        else:
            start = obj.get(key, 1.0 if key == "alpha" else 0.0)
        self._tweens = [tween for tween in self._tweens if not (tween[0] is obj and tween[1] == key)]
        if seconds == 0:
            self._apply_tween(obj, key, float(target))
        else:
            self._tweens.append([obj, key, float(start), float(target), float(seconds), 0.0, easing])

    def _apply_tween(self, obj, key, value):
        if key in ("x", "y") and obj["type"] == "line":
            obj[key + "2"] += value - obj[key]
        if key in ("w", "h") and obj["type"] in ("sprite", "image"):
            width, height = obj["surface"].get_size()
            width, height = (value, height) if key == "w" else (width, value)
            if width >= 1 and height >= 1:
                self._resize(obj, width, height)
            return
        if key == "alpha":
            value = max(0.0, min(1.0, value))
        elif key in ("w", "h", "r", "size"):
            value = max(0.0, value)
        obj[key] = value

    def _c_opacity(self, statement):
        value = max(0.0, min(1.0, float(self._num(statement.parts[2], "opacity"))))
        if statement.parts[1] == "all":
            for obj in self.objects.values():
                if isinstance(obj, dict):
                    obj["alpha"] = value
            return
        self._object(statement.parts[1], action="change the opacity of")["alpha"] = value

    def _c_layer(self, statement):
        self._object(statement.parts[1], action="layer")["layer"] = self._num(statement.parts[2], "layer")

    def _c_fixed(self, statement):
        self._object(statement.parts[1], action="fix")["fixed"] = True

    def _tick_effects(self):
        """move tweens, particles and the screen shake on by the time since they last moved."""
        now = time.perf_counter()
        step = min(0.1, max(0.0, now - self._effects_time))
        self._effects_time = now
        self._tick_motion(step)
        if self._tweens:
            for tween in list(self._tweens):
                obj, key, start, target, duration, elapsed, easing = tween
                elapsed += step
                tween[5] = elapsed
                progress = min(1.0, elapsed / duration) if duration > 0 else 1.0
                self._apply_tween(obj, key, start + (target - start) * ease_value(progress, easing))
                if progress >= 1:
                    self._tweens.remove(tween)
        if self._particles:
            alive = []
            for particle in self._particles:
                particle[4] -= step
                if particle[4] <= 0:
                    continue
                particle[0] += particle[2] * step
                particle[1] += particle[3] * step
                particle[3] += 240 * step
                alive.append(particle)
            self._particles = alive
        if self._shake:
            self._shake[1] -= step
            if self._shake[1] <= 0:
                self._shake = None
                self._shake_offset = (0.0, 0.0)
            else:
                strength = self._shake[0] * self._shake[1] / self._shake[2]
                self._shake_offset = (random.uniform(-strength, strength), random.uniform(-strength, strength))

    def _c_box(self, statement):
        parts = statement.parts
        self.objects[self._name(parts[1])] = {
            "type": "box",
            "x": self._num(parts[2], "box x"), "y": self._num(parts[3], "box y"),
            "w": self._num(parts[4], "box width"), "h": self._num(parts[5], "box height"),
            "color": self.activecolor,
        }

    def _c_circle(self, statement):
        parts = statement.parts
        self.objects[self._name(parts[1])] = {
            "type": "circle",
            "x": self._num(parts[2], "circle x"), "y": self._num(parts[3], "circle y"),
            "r": self._num(parts[4], "circle radius"),
            "color": self.activecolor,
        }

    def _c_line(self, statement):
        parts = statement.parts
        self.objects[self._name(parts[1])] = {
            "type": "line",
            "x": self._num(parts[2], "line x1"), "y": self._num(parts[3], "line y1"),
            "x2": self._num(parts[4], "line x2"), "y2": self._num(parts[5], "line y2"),
            "width": max(1, self._num(parts[6], "line thickness")) if len(parts) > 6 else 1,
            "color": self.activecolor,
        }

    def _c_cube(self, statement):
        parts = statement.parts
        if len(parts) not in (6, 7, 9):
            raise ValueError("use: cube <name> <x> <y> <z> <size> [color]")
        self.objects[self._name(parts[1])] = {
            "type": "cube",
            "x": self._num(parts[2], "cube x"), "y": self._num(parts[3], "cube y"),
            "z": self._num(parts[4], "cube z"), "size": self._num(parts[5], "cube size"),
            "angle": 0, "color": self._shape_color(parts, 6),
        }

    def _c_sphere(self, statement):
        parts = statement.parts
        if len(parts) not in (6, 7, 9):
            raise ValueError("use: sphere <name> <x> <y> <z> <radius> [color]")
        x, y, z, radius = (self.val(part) for part in parts[2:6])
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in (x, y, z, radius)):
            raise ValueError("sphere position and radius must be finite numbers")
        if radius <= 0:
            raise ValueError("sphere radius must be a positive number")
        self.objects[self._name(parts[1])] = {
            "type": "sphere", "x": x, "y": y, "z": z, "radius": radius, "angle": 0,
            "color": self._shape_color(parts, 6),
        }

    def _c_camera(self, statement):
        parts = statement.parts
        if len(parts) == 2:
            position = self.val(parts[1])
            if not isinstance(position, Vector3):
                raise ValueError("camera needs a vec3 variable")
            self.camera = position
            return
        if len(parts) not in (4, 6):
            raise ValueError("use camera <x> <y> <z> [yaw] [pitch] or camera <vec3-variable>")
        values = tuple(self._num(part, "camera coordinate") for part in parts[1:4])
        self.camera = Vector3(*values)
        if len(parts) == 6:
            self.camera_turn = (self._num(parts[4], "camera yaw"), self._num(parts[5], "camera pitch"))

    def _c_vec2(self, statement):
        x, y = (self.val(part) for part in statement.parts[2:4])
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in (x, y)):
            raise ValueError("vec2 components must be finite numbers")
        self.vars[statement.parts[1]] = Vector2(x, y)

    def _c_vec3(self, statement):
        x, y, z = (self.val(part) for part in statement.parts[2:5])
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in (x, y, z)):
            raise ValueError("vec3 components must be finite numbers")
        self.vars[statement.parts[1]] = Vector3(x, y, z)

    def _c_text(self, statement):
        parts = statement.parts
        self.objects[self._name(parts[1])] = {
            "type": "text",
            "x": self._num(parts[2], "text x"), "y": self._num(parts[3], "text y"),
            "text": self._text(parts[4:]),
            "size": self.text_size,
            "color": self.activecolor,
        }

    def _c_image(self, statement):
        parts = statement.parts
        if not self.screen:
            raise ValueError("add 'mode 2d' or 'mode 3d' before showing an image")
        self.objects[self._name(parts[1])] = {
            "type": "image",
            "x": self._num(parts[3], "image x"), "y": self._num(parts[4], "image y"),
            "surface": self._load_image(parts[2], "image"),
            "color": self.activecolor,
        }

    def _c_sprite(self, statement):
        parts = statement.parts
        if len(parts) != 7:
            raise ValueError("use: sprite <name> <path> <x> <y> <width> <height>")
        if not self.screen:
            raise ValueError("add 'mode 2d' or 'mode 3d' before showing a sprite")
        source = self._load_image(parts[2], "sprite")
        width, height = int(self._num(parts[5], "sprite width")), int(self._num(parts[6], "sprite height"))
        if width <= 0 or height <= 0:
            raise ValueError("sprite width and height must be greater than zero")
        key = (id(source), width, height)
        scaled = self._image_cache.get(key)
        if scaled is None:
            scaled = pygame.transform.scale(source, (width, height))
            self._image_cache[key] = scaled
        previous = self.objects.get(self._name(parts[1]))
        self.objects[self._name(parts[1])] = {
            "type": "sprite",
            "x": self._num(parts[3], "sprite x"), "y": self._num(parts[4], "sprite y"),
            "surface": scaled, "source": source,
            "angle": previous.get("angle", 0) if isinstance(previous, dict) and previous.get("type") == "sprite" else 0,
            "color": self.activecolor,
        }

    def _c_spin(self, statement):
        obj = self._object(statement.parts[1], SHAPES_3D + ("sprite", "image"), "spin")
        obj["angle"] = self._num(statement.parts[2], "angle")

    def _c_button(self, statement):
        parts = statement.parts
        x, y, width, height = (self.val(part) for part in parts[2:6])
        if any(type(value) not in (int, float) for value in (x, y, width, height)):
            raise ValueError("button position and size must be numbers")
        if width <= 0 or height <= 0:
            raise ValueError("button width and height must be greater than zero")
        key = "button:" + parts[1]
        if key not in self.objects:
            self.vars[parts[1]] = 0
        self.objects[key] = {
            "type": "button", "variable": parts[1], "x": x, "y": y, "w": width, "h": height,
            "label": self._label(parts[6:]), "color": self.activecolor,
        }
        self.vars.setdefault(parts[1], 0)

    def _c_ui(self, statement):
        if statement.parts[1] != "button":
            raise ValueError("the only supported form is: ui button <label>")
        self.button_label = self._label(statement.parts[2:])
        self.objects["uibtn"] = (20, 20, 180, 38)

    def _c_move(self, statement):
        parts = statement.parts
        obj = self._object(parts[1], SHAPES_3D + ("box", "circle", "text", "image", "sprite", "line", "button",
                                                  "textbox", "slider", "checkbox", "ellipse", "polygon"), "move")
        if len(parts) == 3:
            offset = self.val(parts[2])
            if isinstance(offset, Vector2):
                dx, dy, dz = offset.x, offset.y, 0
            elif isinstance(offset, Vector3) and obj["type"] in SHAPES_3D:
                dx, dy, dz = offset.x, offset.y, offset.z
            else:
                raise ValueError("use a vec2 for 2D objects or a vec3 for 3D objects")
        else:
            dx, dy = self.val(parts[2]), self.val(parts[3])
            dz = self.val(parts[4]) if len(parts) > 4 else 0
            if any(isinstance(v, bool) or type(v) not in (int, float) for v in (dx, dy, dz)):
                raise ValueError("move needs numeric x and y amounts")
            if dz and obj["type"] not in SHAPES_3D:
                raise ValueError("only 3d objects can move along z")
        obj["x"] += dx
        obj["y"] += dy
        if dz:
            obj["z"] += dz
        if obj["type"] == "line":
            obj["x2"] += dx
            obj["y2"] += dy

    def _c_place(self, statement):
        parts = statement.parts
        obj = self._object(parts[1], action="place")
        x, y = self._num(parts[2], "x"), self._num(parts[3], "y")
        if obj["type"] == "line":
            obj["x2"] += x - obj["x"]
            obj["y2"] += y - obj["y"]
        obj["x"], obj["y"] = x, y
        if len(parts) > 4:
            if "z" not in obj:
                raise ValueError("only 3d objects have a z position")
            obj["z"] = self._num(parts[4], "z")

    def _c_resize(self, statement):
        parts = statement.parts
        obj = self._object(parts[1], action="resize")
        width = self._num(parts[2], "width")
        height = self._num(parts[3], "height") if len(parts) > 3 else width
        self._resize(obj, width, height)

    def _c_hide(self, statement):
        self._object(statement.parts[1])["hidden"] = True

    def _c_show(self, statement):
        self._object(statement.parts[1])["hidden"] = False

    def _c_animate(self, statement):
        parts = statement.parts
        obj = self.objects.get(self._name(parts[1]))
        if not isinstance(obj, dict):
            raise ValueError(f"object '{self._name(parts[1])}' does not exist yet")
        if obj["type"] in SHAPES_3D:
            if self.mode != "3d" or len(parts) != 6:
                raise ValueError("animate a 3d shape with: animate <object> <x> <y> <z> <seconds>")
            target_position = tuple(self.val(part) for part in parts[2:5])
            duration = self.val(parts[5])
        else:
            if obj["type"] not in ("box", "circle", "text", "image", "sprite", "line", "button", "textbox",
                                   "slider", "checkbox"):
                raise ValueError(f"object '{parts[1]}' cannot be animated")
            if len(parts) != 5:
                raise ValueError("animate a 2d object with: animate <object> <x> <y> <seconds>")
            target_position = tuple(self.val(part) for part in parts[2:4])
            duration = self.val(parts[4])
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in (*target_position, duration)):
            raise ValueError("animate needs finite numeric coordinates and duration")
        self._animate_object(obj, target_position, duration)

    def _c_touching(self, statement):
        self.vars[statement.parts[1]] = int(
            self._objects_touching(self._name(statement.parts[2]), self._name(statement.parts[3]))
        )

    def _c_key(self, statement):
        self._require_screen("check the keyboard")
        keycode = self._keycode(statement.parts[2])
        self.vars[statement.parts[1]] = 1 if pygame.key.get_pressed()[keycode] and not self._typing() else 0

    def _c_keypressed(self, statement):
        self._require_screen("check the keyboard")
        self.vars[statement.parts[1]] = 1 if self._consume_press(self._keycode(statement.parts[2])) else 0

    def _c_mouse(self, statement):
        self._require_screen("check the mouse")
        self.vars[statement.parts[1]], self.vars[statement.parts[2]] = pygame.mouse.get_pos()

    def _c_mousebutton(self, statement):
        self._require_screen("check the mouse")
        button = {"left": 0, "middle": 1, "right": 2}.get(statement.parts[2].lower())
        if button is None:
            raise ValueError("mousebutton expects left, middle, or right")
        self.vars[statement.parts[1]] = bool(pygame.mouse.get_pressed(3)[button])

    _NUMBER_ANSWER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:[.][0-9]+)?")

    def _c_input(self, statement):
        answer = self._ask_input(self._text(statement.parts[2:]))
        cleaned = answer.strip()
        if self._NUMBER_ANSWER.fullmatch(cleaned):
            answer = float(cleaned) if "." in cleaned else int(cleaned)
        self._set_target(statement.parts[1], answer)

    def _c_popup(self, statement):
        self._show_popup(self._text(statement.parts[1:]))

    def _c_sound(self, statement):
        relative = " ".join(statement.parts[1:])
        path = self._load_audio_path(relative)
        self._ensure_audio()
        try:
            sound = self._sound_cache.get(path)
            if sound is None:
                sound = pygame.mixer.Sound(path)
                self._sound_cache[path] = sound
            channel = sound.play()
        except pygame.error as err:
            raise ValueError(f"could not play sound '{relative}': {str(err).lower()}") from err
        self.audio_channels = [
            (active_channel, active_sound)
            for active_channel, active_sound in self.audio_channels
            if active_channel.get_busy()
        ]
        if channel:
            channel.set_volume(self.audio_volume)
            self.audio_channels.append((channel, sound))

    BEEP_WAVES = ("square", "sine", "triangle", "saw", "noise")

    def _c_beep(self, statement):
        parts = statement.parts
        frequency = self._num(parts[1], "beep frequency")
        seconds = self._num(parts[2], "beep length") if len(parts) > 2 else 0.15
        wave = str(parts[3]).lower() if len(parts) > 3 else "square"
        if not 20 <= frequency <= 20000:
            raise ValueError("beep frequency must be from 20 to 20000 (440 is the a above middle c)")
        if not 0 < seconds <= 5:
            raise ValueError("a beep can last from just above 0 up to 5 seconds")
        if wave not in self.BEEP_WAVES:
            raise ValueError(f"'{wave}' is not a wave. try: {', '.join(self.BEEP_WAVES)}")
        self._ensure_audio()
        sound = self._beep_sound(frequency, seconds, wave)
        channel = sound.play()
        self.audio_channels = [(c, a) for c, a in self.audio_channels if c.get_busy()]
        if channel:
            channel.set_volume(self.audio_volume)
            self.audio_channels.append((channel, sound))

    def _beep_sound(self, frequency, seconds, wave):
        key = ("beep", round(frequency, 2), round(seconds, 3), wave)
        sound = self._sound_cache.get(key)
        if sound is None:
            rate, size, channels = pygame.mixer.get_init()
            if abs(size) != 16:
                raise ValueError("beep needs 16-bit audio")
            channels = max(1, channels)
            count = max(1, int(rate * seconds))
            fade_in, fade_out = rate * 0.003, rate * 0.02
            samples = array.array("h")
            amplitude = 0.22 * 32767
            for index in range(count):
                phase = (index * frequency / rate) % 1.0
                if wave == "sine":
                    value = math.sin(2 * math.pi * phase)
                elif wave == "square":
                    value = 1.0 if phase < 0.5 else -1.0
                elif wave == "triangle":
                    value = 4 * abs(phase - 0.5) - 1
                elif wave == "saw":
                    value = 2 * phase - 1
                else:
                    value = random.uniform(-1, 1)
                envelope = min(1.0, index / fade_in, (count - index) / fade_out)
                samples.extend([int(value * amplitude * envelope)] * channels)
            try:
                sound = pygame.mixer.Sound(buffer=samples.tobytes())
            except pygame.error as err:
                raise ValueError(f"could not make the beep: {str(err).lower()}") from err
            self._sound_cache[key] = sound
        return sound

    def _c_music(self, statement):
        relative = " ".join(statement.parts[1:])
        path = self._load_audio_path(relative)
        self._ensure_audio()
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play(-1)
        except pygame.error as err:
            raise ValueError(f"could not play music '{relative}': {str(err).lower()}") from err

    def _c_stopmusic(self, statement):
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()

    def _c_stopsounds(self, statement):
        for channel, _ in self.audio_channels:
            channel.stop()
        self.audio_channels.clear()

    def _c_volume(self, statement):
        volume = self.val(statement.parts[1])
        if type(volume) not in (int, float) or not 0 <= volume <= 1:
            raise ValueError("volume must be a number from 0 to 1")
        self.audio_volume = volume
        if pygame.mixer.get_init():
            pygame.mixer.music.set_volume(volume)
            for channel, _ in self.audio_channels:
                channel.set_volume(volume)

    def _c_get(self, statement):
        now = time.monotonic()
        if self.http_requests >= 5:
            raise ValueError("a script can make at most five https requests per run")
        if now - self.last_http_request < 1:
            raise ValueError("wait at least one second between https requests")
        self.http_requests += 1
        self.last_http_request = now
        self.vars[statement.parts[2]] = public_https_get(statement.parts[1])

    # ----- 1.0.5: constants, errors, tests ---------------------------------------------
    def _c_const(self, statement):
        match = _SET_RE.match(statement.rest)
        if not match or not re.fullmatch(r"[A-Za-z_]\w*", match.group(1)):
            raise ValueError("write constants as: const name = value")
        name, raw_value = match.groups()
        self.constants.discard(name)
        self.vars[name] = self._eval_value(raw_value, split_command(raw_value))
        self.constants.add(name)

    def _c_throw(self, statement):
        raise ValueError(self._text(statement.parts[1:]))

    def _c_assert(self, statement):
        if self._condition(statement):
            return
        details = []
        try:
            node = parse_condition(statement.rest)
            for name in sorted({item.id for item in ast.walk(node) if isinstance(item, ast.Name)}):
                if name in self.vars and not isinstance(self.vars[name], GublanLambda):
                    details.append(f"{name} is {format_value(self.vars[name])[:60]}")
        except (SyntaxError, ValueError):
            pass
        raise ValueError(f"assert failed: {statement.rest}" + (f" ({', '.join(details)})" if details else ""))

    def _c_use(self, statement):
        """use lines are swapped for the module's code before the program starts."""

    def run_tests(self, source, base_dir=None, only=None):
        """run every test block on its own, each with a fresh start. returns a list of results:
        {"name", "passed", "message", "line", "file", "seconds"}."""
        if base_dir is not None:
            self.base_dir = os.path.abspath(base_dir)
        self.reset()
        results = []
        try:
            mapped = self._expand_includes_mapped(source, self.base_dir)
            self._compile(mapped)
        except ValueError as err:
            return [{"name": "loading the program", "passed": False, "message": str(err), "line": None,
                     "file": None, "seconds": 0.0}]
        except GublanError as err:
            statement = err.statement
            return [{"name": "loading the program", "passed": False, "message": err.message,
                     "line": statement.line if statement else None, "file": statement.file if statement else None,
                     "seconds": 0.0}]
        program, functions, tests = self._prog, self.functions, self.tests
        for name, start, end in tests:
            if only and name != only:
                continue
            self.reset()
            self._prog, self.functions, self.tests = program, functions, tests
            self.running = True
            started = time.perf_counter()
            result = {"name": name, "passed": True, "message": "", "line": program[start].line,
                      "file": program[start].file}
            try:
                self._exec(start + 1, end)
            except GublanError as err:
                result.update(passed=False, message=err.message)
                if err.statement is not None:
                    result.update(line=err.statement.line, file=err.statement.file)
            except _Return:
                pass
            except _Kill:
                pass
            except _Stop:
                result.update(passed=False, message="stopped")
                results.append(result)
                break
            except RecursionError:
                result.update(passed=False, message="functions are calling each other too deeply")
            finally:
                result["seconds"] = round(time.perf_counter() - started, 4)
                if self.screen:
                    pygame.quit()
                    self.screen = None
            results.append(result)
        self.running = False
        return results

    # ----- 1.0.5: textboxes, sliders and checkboxes --------------------------------------
    def _c_textbox(self, statement):
        parts = statement.parts
        name = self._name(parts[1])
        x, y = self._num(parts[2], "textbox x"), self._num(parts[3], "textbox y")
        width = self._num(parts[4], "textbox width")
        if width <= 0:
            raise ValueError("textbox width must be greater than zero")
        size = self.text_size
        previous = self.objects.get(name)
        keep = isinstance(previous, dict) and previous.get("type") == "textbox"
        self.objects[name] = {
            "type": "textbox", "x": x, "y": y, "w": width, "h": max(24, int(size * 1.25) + 8), "size": size,
            "hint": self._label(parts[5:]) if len(parts) > 5 else "",
            "text": previous["text"] if keep else "", "cursor": previous["cursor"] if keep else 0,
            "anchor": None, "submitted": False, "color": self.activecolor,
        }

    def _c_slider(self, statement):
        parts = statement.parts
        if len(parts) not in (7, 8):
            raise ValueError("use: slider <name> <x> <y> <width> <min> <max> [start]")
        name = self._name(parts[1])
        x, y = self._num(parts[2], "slider x"), self._num(parts[3], "slider y")
        width = self._num(parts[4], "slider width")
        low, high = self._num(parts[5], "slider min"), self._num(parts[6], "slider max")
        if width <= 0:
            raise ValueError("slider width must be greater than zero")
        if low == high:
            raise ValueError("a slider needs a min and max that are different")
        previous = self.objects.get(name)
        if len(parts) == 8:
            value = self._num(parts[7], "slider start")
        elif isinstance(previous, dict) and previous.get("type") == "slider":
            value = previous["value"]
        else:
            value = low
        self.objects[name] = {
            "type": "slider", "x": x, "y": y, "w": width, "h": 24, "min": low, "max": high,
            "value": max(min(low, high), min(max(low, high), value)), "color": self.activecolor,
            "whole": all(isinstance(v, int) and not isinstance(v, bool) for v in (low, high)),
        }

    def _c_checkbox(self, statement):
        parts = statement.parts
        name = self._name(parts[1])
        previous = self.objects.get(name)
        self.objects[name] = {
            "type": "checkbox", "x": self._num(parts[2], "checkbox x"), "y": self._num(parts[3], "checkbox y"),
            "w": 24, "h": 24, "label": self._label(parts[4:]), "size": self.text_size,
            "checked": bool(previous.get("checked")) if isinstance(previous, dict) and
            previous.get("type") == "checkbox" else False, "color": self.activecolor,
        }

    def _c_focus(self, statement):
        target = self._name(statement.parts[1])
        if target == "none":
            self._set_focus(None)
            return
        self._object(target, ("textbox",), "focus")
        self._set_focus(target)

    def _set_focus(self, name):
        if name == self._focus:
            return
        self._focus = name
        if self.screen is None:
            return
        try:
            if name:
                pygame.key.start_text_input()
                pygame.key.set_repeat(400, 35)
            else:
                pygame.key.stop_text_input()
                pygame.key.set_repeat()
        except pygame.error:
            pass

    def _typing(self):
        """true while the player is typing into a textbox, so keys don't also move the game."""
        return self._focus is not None and self._focus in self.objects


# --------------------------------------------------------------------------
# plugins: extra commands and functions
# --------------------------------------------------------------------------

class CommandContext:
    """what a plugin command gets when it runs."""

    def __init__(self, runtime, statement):
        self.runtime = runtime
        self.words = [str(part) for part in statement.parts[1:]]
        self.rest = statement.rest

    @property
    def values(self):
        """each word after the command, as a value (variables are looked up, numbers become numbers)."""
        return [self.runtime._val_text(part) for part in self.words]

    @property
    def text(self):
        """the words after the command as text, with {braces} filled in."""
        return self.runtime._label(self.words)

    def get(self, name, default=None):
        return self.runtime.vars.get(name, default)

    def set(self, name, value):
        self.runtime._set_target(name, value)

    def print(self, *values):
        self.runtime.onlog(" ".join(format_value(value) for value in values))


def register_command(name, run, usage=None, summary="", example=None, category="plugins", min_parts=1):
    """add a command. run(context) is called with a CommandContext each time a line uses it."""
    if not re.fullmatch(r"[a-z][a-z0-9]{1,30}", name or ""):
        raise ValueError("command names are 2 to 31 lowercase letters or digits, starting with a letter")
    if name in COMMAND_SPECS and name not in _PLUGIN_COMMANDS:
        raise ValueError(f"'{name}' is already a gublan command")
    if not callable(run):
        raise ValueError("run must be a function")
    if category not in CATEGORY_ORDER:
        category = "plugins"
    spec = (category, usage or name, max(1, int(min_parts)), summary or "a command added by a plugin.",
            example or name)
    COMMAND_SPECS[name] = spec
    GUBLANCOMMANDS.add(name)
    COMMAND_USAGE[name] = spec[1]
    if spec[2] > 1:
        COMMAND_MIN_ARGS[name] = spec[2]
    COMMAND_CATEGORY[name], COMMAND_SUMMARY[name], COMMAND_EXAMPLE[name] = spec[0], spec[3], spec[4]
    _PLUGIN_COMMANDS[name] = run


def register_function(name, function, description=""):
    """add an expression function: name(values...) calls function(*values)."""
    if not re.fullmatch(r"[a-z_][a-z0-9_]{1,30}", name or ""):
        raise ValueError("function names are 2 to 31 lowercase letters, digits or _")
    if name in EXPRESSION_FUNCTIONS and name not in _PLUGIN_FUNCTIONS:
        raise ValueError(f"'{name}' is already a gublan function")
    if not callable(function):
        raise ValueError("function must be callable")
    EXPRESSION_FUNCTIONS[name] = description or f"{name}(...) a function added by a plugin"
    _PLUGIN_FUNCTIONS[name] = function


def plugin_names():
    return sorted(_PLUGIN_COMMANDS), sorted(_PLUGIN_FUNCTIONS)


def remove_plugin_command(name):
    """take away a command a plugin added. built-in commands can't be removed."""
    if name not in _PLUGIN_COMMANDS:
        return False
    del _PLUGIN_COMMANDS[name]
    for table in (COMMAND_SPECS, COMMAND_USAGE, COMMAND_MIN_ARGS, COMMAND_CATEGORY, COMMAND_SUMMARY,
                  COMMAND_EXAMPLE):
        table.pop(name, None)
    GUBLANCOMMANDS.discard(name)
    return True


def remove_plugin_function(name):
    if name not in _PLUGIN_FUNCTIONS:
        return False
    del _PLUGIN_FUNCTIONS[name]
    EXPRESSION_FUNCTIONS.pop(name, None)
    return True


def run_standalone(source, base_dir, title=None, console=False, save_name=None, style=None):
    """entry point for exported executables.

    window programs show errors in a message box. console programs (exported with a
    console window) print output as it happens, ask input questions in the terminal and
    wait for enter at the end so the window doesn't vanish.
    """
    errors = []
    output = []

    def log(message):
        if console:
            print(message, flush=True)
            return
        output.append(message)
        if len(output) > 200:
            del output[:100]

    def error(message, label, line):
        where = f"{label} line {line}" if label else f"line {line}" if line else ""
        errors.append(f"{where}: {message}" if where else message)

    def ask(message):
        try:
            return input(f"{message} ")
        except EOFError:
            return ""

    def popup(message):
        print(message, flush=True)

    runtime = GublanRuntime(
        onlog=log, onerror=error, base_dir=base_dir, hold_window=True,
        oninput=ask if console else None, onpopup=popup if console else None,
        save_name=save_name or title or os.path.basename(os.path.abspath(base_dir)), style=style,
    )
    if title:
        runtime.window_title = title
        original_reset = runtime.reset

        def reset_with_title():
            original_reset()
            runtime.window_title = title

        runtime.reset = reset_with_title
    try:
        runtime.run(source)
    except Exception as err:  # pragma: no cover - last-resort safety for exported games
        errors.append(f"internal error: {str(err).lower()}")
    if errors:
        message = "the program stopped because of an error:\n\n" + "\n".join(errors)
        if console:
            print("\n" + message, flush=True)
        else:
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, message, (title or "gublan program").lower(), 0x10)
            except Exception:
                print(message)
    if console:
        try:
            input("\npress enter to close ")
        except EOFError:
            pass
    return 1 if errors else 0
