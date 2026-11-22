"""starter programs offered on the welcome screen and in file > new from template."""

BLANK = """// my program
// press f5 to run it. type a command and a list of ideas appears.

print hello
"""

HELLO = """// hello: your first program. press f5 to run it.
// answers are typed in the output panel at the bottom.

print hello there!
input name what is your name?
print nice to meet you, {name}

input age how old are you?
if age > 12
    print {age} is a great age for making games
else
    print it's never too early to start making games
end

for i = 1 to 3
    print counting {i}
end
"""

QUIZ = """// quiz: questions and answers in the output panel, no window needed.

score = 0
questions = ["what is 3 + 4?", "what do blue and yellow make?", "how many legs does a spider have?"]
answers = [7, "green", 8]

for i = 0 to len(questions) - 1
    input reply {questions[i]}
    if lower(str(reply)) == lower(str(answers[i]))
        print correct!
        score += 1
    else
        print not quite, it was {answers[i]}
    end
end

print you got {score} out of {len(questions)}
"""

DODGE = """// dodge: move with the left and right arrow keys and stay away from the rocks.

window 640 480 dodge
mode 2d
background #141414
fps 60

score = 0
lives = 3
rocks = 6
// the best score is saved on this computer, so it is still there next time
load best best 0
// shows on your discord profile while the discord app is open
presence details dodging rocks
presence timer

color moss
box player 300 440 40 14

color gray
xs = []
ys = []
for i = 0 to rocks - 1
    append xs {random(20, 620)}
    append ys {random(-500, -20)}
    circle rock{i} {xs[i]} {ys[i]} 12
end

color white
text hud 12 10 score 0   lives 3   best {best}

while lives > 0
    if keydown("left")
        move player {-320 * dt} 0
    end
    if keydown("right")
        move player {320 * dt} 0
    end
    place player {clamp(player.x, 0, 600)} 440

    for i = 0 to rocks - 1
        ys[i] += (160 + score * 4) * dt
        if ys[i] > 500
            ys[i] = random(-200, -20)
            xs[i] = random(20, 620)
            score += 1
        end
        place rock{i} {xs[i]} {ys[i]}
        if touching("player", "rock" + str(i))
            lives -= 1
            ys[i] = -40
        end
    end

    text hud 12 10 score {score}   lives {lives}   best {max(best, score)}
    presence state score {score}, {lives} lives left
    frame
end

if score > best
    save best score
    popup a new best score: {score}!
else
    popup game over! you scored {score}. your best is {best}
end
"""

PLATFORMER = """// platformer: run with the arrow keys and jump with space. grab the coins.

window 640 400 platformer
mode 2d
background #141414
fps 60

gravity = 1400
vy = 0
on_ground = false
coins = 0

color moss
box ground 0 370 640 30
box ledge1 120 290 140 16
box ledge2 360 220 140 16
box ledge3 200 140 120 16
tops = {"ground": 370, "ledge1": 290, "ledge2": 220, "ledge3": 140}

color gold
circle coin 260 110 10

color white
box hero 40 300 24 32
text hud 10 10 coins 0

forever
    if keydown("left")
        move hero {-240 * dt} 0
    end
    if keydown("right")
        move hero {240 * dt} 0
    end
    if keypressed("space") and on_ground
        vy = -620
    end

    vy += gravity * dt
    move hero 0 {vy * dt}
    on_ground = false
    for name in keys(tops)
        if touching("hero", name) and vy >= 0
            place hero {hero.x} {tops[name] - 32}
            vy = 0
            on_ground = true
        end
    end
    place hero {clamp(hero.x, 0, 616)} {hero.y}

    if touching("hero", "coin")
        coins += 1
        place coin {random(40, 600)} {random(80, 320)}
        text hud 10 10 coins {coins}
    end
    frame
end
"""

CLICKER = """// clicker: click to earn points, then spend them on upgrades.

window 480 300 clicker
mode 2d
background #141414

points = 0
per_click = 1
cost = 10
was_clicked = false
was_upgrade = false

textsize 30
color moss
text score 20 20 points 0
textsize 18
color white
button clicked 20 90 200 48 click me
button upgrade 20 160 200 48 upgrade
text info 240 174 costs 10, gives +1

forever
    if clicked and not was_clicked
        points += per_click
    end
    if upgrade and not was_upgrade and points >= cost
        points -= cost
        per_click += 1
        cost = round(cost * 1.8)
    end
    was_clicked = clicked
    was_upgrade = upgrade
    text score 20 20 points {points}
    text info 240 174 costs {cost}, gives +1
    frame
end
"""

BALLS = """// bouncing balls: lists, maps and a game loop.

window 640 420 bouncing balls
mode 2d
background #101410

balls = []
for i = 0 to 9
    ball = {"x": random(40, 600), "y": random(40, 380), "dx": random(-180, 180), "dy": random(-180, 180)}
    append balls {ball}
    color {choice(["moss", "lime", "sand", "teal", "gold"])}
    circle ball{i} {ball.x} {ball.y} 14
end

forever
    for i = 0 to len(balls) - 1
        b = balls[i]
        b.x += b.dx * dt
        b.y += b.dy * dt
        if b.x < 14 or b.x > 626
            b.dx = -b.dx
        end
        if b.y < 14 or b.y > 406
            b.dy = -b.dy
        end
        place ball{i} {b.x} {b.y}
    end
    frame
end
"""

SCENE_3D = """// 3d scene: spinning shapes and a swaying camera.

mode 3d
background #101410

color moss
cube crate 0 0 -6 1
color sand
cube small -2 0.5 -7 0.6
color lime
sphere moon 2 0 -7 0.5

angle = 0
forever
    angle += 60 * dt
    spin crate {angle}
    spin small {-angle * 2}
    camera {sin(angle) * 0.8} 0.3 0
    frame
end
"""

TEMPLATES = [
    {"key": "blank", "title": "blank", "level": "any", "icon": "new",
     "about": "an empty program to start from scratch.", "source": BLANK},
    {"key": "hello", "title": "hello", "level": "beginner", "icon": "learn",
     "about": "print, ask questions and make choices. a good first program.", "source": HELLO},
    {"key": "quiz", "title": "quiz", "level": "beginner", "icon": "help",
     "about": "a question game with lists and a loop. runs in the output panel.", "source": QUIZ},
    {"key": "dodge", "title": "dodge", "level": "beginner", "icon": "game",
     "about": "a 2d arcade game: arrow keys, falling rocks, score and lives.", "source": DODGE},
    {"key": "platformer", "title": "platformer", "level": "standard", "icon": "game",
     "about": "gravity, jumping, platforms and coins.", "source": PLATFORMER},
    {"key": "clicker", "title": "clicker", "level": "beginner", "icon": "game",
     "about": "buttons, points and upgrades.", "source": CLICKER},
    {"key": "balls", "title": "bouncing balls", "level": "standard", "icon": "palette",
     "about": "lists of maps moving every frame.", "source": BALLS},
    {"key": "3d", "title": "3d scene", "level": "standard", "icon": "blocks",
     "about": "cubes, a sphere and a moving camera.", "source": SCENE_3D},
]


def template(key):
    for item in TEMPLATES:
        if item["key"] == key:
            return item
    return TEMPLATES[0]
