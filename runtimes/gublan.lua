-- the gublan runtime for programs turned into lua by gublan studio.
--
-- it is made for love2d (https://love2d.org): run the folder with love (love .), and a window opens as soon as
-- the program draws something. programs that only print also run with plain lua 5.2+ or luajit (lua main.lua).
-- it gives a translated program everything gublan has built in: its functions (sin works in degrees, round goes
-- half up...), shapes, text, pictures, buttons and text boxes, keys, the mouse, sound and saving.
local G = {}

local unpack = table.unpack or unpack
local floor, abs, sqrt, huge = math.floor, math.abs, math.sqrt, math.huge
local concat = table.concat
local has_love = type(love) == "table"

pcall(function() io.stdout:setvbuf("no") end)
math.randomseed(os.time())
math.random()

local function now()
    if has_love and love.timer then
        return love.timer.getTime()
    end
    return os.clock()
end
local started = now()

G.pi = math.pi
G.dt = 0
G.screen_width = 800
G.screen_height = 600
G.buttons = {}
G.ui = ""
G.tests = {}

-- ----- markers and errors ---------------------------------------------------------------------------------------
local function marker(name)
    return setmetatable({}, {__tostring = function() return name end})
end
-- return, break and continue inside a try have to pass through pcall: the try gives back one of these
G.RETURN, G.BREAK, G.CONTINUE = marker("return"), marker("break"), marker("continue")
local KILL = marker("kill")
G.KILL = KILL

local Problem = {__tostring = function(problem) return problem.message end}
local function fail(text)
    error(setmetatable({message = text}, Problem), 0)
end
G.fail = fail

local function problem_text(problem)
    if getmetatable(problem) == Problem then
        return problem.message
    end
    -- "main.lua:12: attempt to..." -> "attempt to..."
    return (tostring(problem):gsub("^[^\n]-:%d+: ", ""))
end

function G.message(problem)
    if problem == KILL then
        error(KILL, 0)
    end
    return problem_text(problem)
end

function G.missing(name)
    return function()
        fail("'" .. name .. "' is not available outside gublan")
    end
end

-- ----- maps (they keep their keys in order, like gublan's) ---------------------------------------------------------
local Map = {}
local ORDER = setmetatable({}, {__mode = "k"})
Map.__newindex = function(map, key, value)
    if value == nil then
        return
    end
    local order = ORDER[map]
    order[#order + 1] = key
    rawset(map, key, value)
end

local function new_map()
    local map = setmetatable({}, Map)
    ORDER[map] = {}
    return map
end

local function is_map(value)
    return getmetatable(value) == Map
end

local function map_keys(map)
    local out, seen = {}, {}
    for _, key in ipairs(ORDER[map]) do
        if not seen[key] and rawget(map, key) ~= nil then
            seen[key] = true
            out[#out + 1] = key
        end
    end
    return out
end

function G.dict(...)
    local map, count = new_map(), select("#", ...)
    for index = 1, count - 1, 2 do
        local key, value = select(index, ...)
        if key ~= nil and value ~= nil then
            map[key] = value
        end
    end
    return map
end

-- ----- vectors ------------------------------------------------------------------------------------------------------
local Vec = {}
local function vec(size, x, y, z)
    return setmetatable({n = size, x = x or 0, y = y or 0, z = z or 0}, Vec)
end
local function is_vec(value)
    return getmetatable(value) == Vec
end
local function vector_math(a, b, op)
    local va, vb = is_vec(a), is_vec(b)
    local size = va and a.n or b.n
    local function part(value, is_vector, key)
        if is_vector then
            return value[key]
        end
        return value
    end
    return vec(size, op(part(a, va, "x"), part(b, vb, "x")), op(part(a, va, "y"), part(b, vb, "y")),
        size == 3 and op(part(a, va, "z"), part(b, vb, "z")) or 0)
end
Vec.__add = function(a, b) return vector_math(a, b, function(x, y) return x + y end) end
Vec.__sub = function(a, b) return vector_math(a, b, function(x, y) return x - y end) end
Vec.__mul = function(a, b) return vector_math(a, b, function(x, y) return x * y end) end
Vec.__div = function(a, b)
    return vector_math(a, b, function(x, y)
        if y == 0 then
            fail("cannot divide by zero")
        end
        return x / y
    end)
end
Vec.__unm = function(a) return vec(a.n, -a.x, -a.y, -a.z) end
Vec.__eq = function(a, b) return a.n == b.n and a.x == b.x and a.y == b.y and a.z == b.z end

function G.vec2(x, y) return vec(2, x, y) end
function G.vec3(x, y, z) return vec(3, x, y, z) end

local function is_list(value)
    return type(value) == "table" and getmetatable(value) == nil
end

-- ----- text from values ----------------------------------------------------------------------------------------------
local CHAR = "[%z\1-\127\194-\244][\128-\191]*"
local function chars(text)
    local out = {}
    for char in string.gmatch(text, CHAR) do
        out[#out + 1] = char
    end
    return out
end

local function number_text(x)
    if x ~= x then
        return "nan"
    end
    if x == huge then
        return "inf"
    end
    if x == -huge then
        return "-inf"
    end
    if x == floor(x) and abs(x) < 1e15 then
        return string.format("%d", x)
    end
    return string.format("%.10g", x)
end

local str
local function item(value)
    if type(value) == "string" then
        return '"' .. value .. '"'
    end
    return str(value)
end

str = function(value)
    if value == nil then
        return "none"
    end
    local kind = type(value)
    if kind == "boolean" then
        return value and "true" or "false"
    elseif kind == "number" then
        return number_text(value)
    elseif kind == "string" then
        return value
    elseif kind == "function" then
        return "function"
    elseif kind == "table" then
        local meta = getmetatable(value)
        if meta == Vec then
            if value.n == 2 then
                return "vec2(" .. str(value.x) .. ", " .. str(value.y) .. ")"
            end
            return "vec3(" .. str(value.x) .. ", " .. str(value.y) .. ", " .. str(value.z) .. ")"
        elseif meta == Map then
            local parts = {}
            for _, key in ipairs(map_keys(value)) do
                parts[#parts + 1] = str(key) .. ": " .. item(rawget(value, key))
            end
            return "{" .. concat(parts, ", ") .. "}"
        elseif meta == Problem then
            return value.message
        elseif meta == nil then
            local parts = {}
            for index = 1, #value do
                parts[index] = item(value[index])
            end
            return "[" .. concat(parts, ", ") .. "]"
        end
    end
    return tostring(value)
end
G.str, G.string = str, str

local screen_log = {}
function G.print(text)
    local line = str(text)
    io.write(line, "\n")
    screen_log[#screen_log + 1] = line
    if #screen_log > 30 then
        table.remove(screen_log, 1)
    end
end

-- ----- values -----------------------------------------------------------------------------------------------------------
function G.truthy(value)
    if value == nil or value == false then
        return false
    end
    local kind = type(value)
    if kind == "number" then
        return value ~= 0
    elseif kind == "string" then
        return value ~= ""
    elseif kind == "table" then
        if is_map(value) then
            return #map_keys(value) > 0
        elseif is_list(value) then
            return #value > 0
        end
    end
    return true
end

local function eq(a, b)
    if a == b then
        return true
    end
    if type(a) ~= "table" or type(b) ~= "table" or getmetatable(a) ~= getmetatable(b) then
        return false
    end
    if is_map(a) then
        local ka, kb = map_keys(a), map_keys(b)
        if #ka ~= #kb then
            return false
        end
        for _, key in ipairs(ka) do
            if not eq(rawget(a, key), rawget(b, key)) then
                return false
            end
        end
        return true
    end
    if is_list(a) then
        if #a ~= #b then
            return false
        end
        for index = 1, #a do
            if not eq(a[index], b[index]) then
                return false
            end
        end
        return true
    end
    return false
end
G.eq = eq

function G.contains(container, value)
    if type(container) == "string" then
        return string.find(container, str(value), 1, true) ~= nil
    elseif is_map(container) then
        return value ~= nil and rawget(container, value) ~= nil
    elseif is_list(container) then
        for _, entry in ipairs(container) do
            if eq(entry, value) then
                return true
            end
        end
        return false
    end
    fail("'in' needs a list, map or text on the right")
end

function G.flag(value)
    return G.truthy(value) and 1 or 0
end

function G.pick(test, yes, no)
    if test then
        return yes()
    end
    return no()
end

function G.unpack(list)
    return unpack(list)
end

-- lists start at 0 in gublan (and at 1 in lua): these take gublan's numbers
local function out_of_range(index)
    fail("list index " .. str(index) .. " is out of range")
end

function G.at(container, index)
    if type(container) == "string" then
        local letters = chars(container)
        if type(index) ~= "number" then
            fail("text positions are numbers")
        end
        if index < 0 then
            index = index + #letters
        end
        local letter = letters[index + 1]
        if letter == nil then
            out_of_range(index)
        end
        return letter
    elseif is_map(container) then
        local value = index ~= nil and rawget(container, index) or nil
        if value == nil then
            fail("the map has no key '" .. str(index) .. "'")
        end
        return value
    elseif is_list(container) then
        if type(index) ~= "number" then
            fail("list positions are numbers")
        end
        if index < 0 then
            index = index + #container
        end
        local value = container[index + 1]
        if value == nil then
            out_of_range(index)
        end
        return value
    elseif is_vec(container) then
        return container[({"x", "y", "z"})[index + 1] or "x"]
    end
    fail("can't use [] on '" .. str(container) .. "'")
end

function G.put(container, key, value)
    if is_map(container) then
        if value == nil then
            rawset(container, key, nil)
        else
            container[key] = value
        end
    elseif is_list(container) then
        local size = #container
        if key < 0 then
            key = key + size
        end
        if key < 0 or key >= size then
            out_of_range(key)
        end
        container[key + 1] = value
    elseif is_vec(container) then
        container[({"x", "y", "z"})[key + 1] or "x"] = value
    else
        fail("can't change '" .. str(container) .. "' with []")
    end
end

function G.append(list, value)
    if not is_list(list) then
        fail("append needs a list")
    end
    list[#list + 1] = value
end

function G.slice(value, first, last)
    local items = type(value) == "string" and chars(value) or value
    local size = #items
    local function fix(index, default)
        if index == nil then
            return default
        end
        index = floor(index)
        if index < 0 then
            index = math.max(0, size + index)
        end
        return math.min(index, size)
    end
    local out = {}
    for index = fix(first, 0) + 1, fix(last, size) do
        out[#out + 1] = items[index]
    end
    if type(value) == "string" then
        return concat(out)
    end
    return out
end

function G.each(value)
    if type(value) == "string" then
        return chars(value)
    elseif type(value) == "number" then
        return G.range(value)
    elseif is_map(value) then
        return map_keys(value)
    elseif is_list(value) then
        local out = {}
        for index = 1, #value do
            out[index] = value[index]
        end
        return out
    end
    fail("can't go through '" .. str(value) .. "' with for")
end

-- [x * 2 for x in items if x > 1] and {key: value for ...}
function G.comp(items, make, keep)
    local out = {}
    for _, value in ipairs(items) do
        if keep == nil or keep(value) then
            out[#out + 1] = make(value)
        end
    end
    return out
end

function G.dcomp(items, make, keep)
    local out = new_map()
    for _, value in ipairs(items) do
        if keep == nil or keep(value) then
            local key, entry = make(value)
            if key ~= nil and entry ~= nil then
                out[key] = entry
            end
        end
    end
    return out
end

-- ----- maths on any values ------------------------------------------------------------------------------------------------
function G.add(a, b)
    if type(a) == "string" or type(b) == "string" then
        return str(a) .. str(b)
    end
    if is_list(a) and is_list(b) then
        local out = {}
        for _, value in ipairs(a) do out[#out + 1] = value end
        for _, value in ipairs(b) do out[#out + 1] = value end
        return out
    end
    if type(a) == "number" and type(b) == "number" or is_vec(a) or is_vec(b) then
        return a + b
    end
    fail("can't do math with '" .. str(a) .. "' and '" .. str(b) .. "'")
end

function G.mul(a, b)
    if (type(a) == "string" or is_list(a)) and type(b) == "number" then
        return G["repeat"](a, b)
    end
    if (type(b) == "string" or is_list(b)) and type(a) == "number" then
        return G["repeat"](b, a)
    end
    return a * b
end

function G.div(a, b)
    if b == 0 then
        fail("cannot divide by zero")
    end
    return a / b
end

function G.idiv(a, b)
    return floor(G.div(a, b))
end

function G.mod(a, b)
    if b == 0 then
        fail("cannot divide by zero")
    end
    return a - b * floor(a / b)
end

-- whole-number bit maths, the way gublan (python) does it
local bitlib
do
    local ok, found = pcall(require, "bit")
    bitlib = ok and found or rawget(_G, "bit32")
end
local function bits(a, b, rule)
    if bitlib and a >= -2147483648 and a < 2147483648 and b >= -2147483648 and b < 2147483648 then
        return bitlib[rule](a, b)
    end
    local result, place = 0, 1
    a, b = floor(a) % 4294967296, floor(b) % 4294967296
    while a > 0 or b > 0 do
        local x, y = a % 2, b % 2
        local on = (rule == "band" and x + y == 2) or (rule == "bor" and x + y > 0) or (rule == "bxor" and x + y == 1)
        if on then
            result = result + place
        end
        a, b, place = (a - x) / 2, (b - y) / 2, place * 2
    end
    return result
end
function G.band(a, b) return bits(a, b, "band") end
function G.bor(a, b) return bits(a, b, "bor") end
function G.bxor(a, b) return bits(a, b, "bxor") end
function G.shl(a, n) return floor(a) * 2 ^ n end
function G.shr(a, n) return floor(floor(a) / 2 ^ n) end
function G.bnot(a) return -floor(a) - 1 end

-- ----- lists that change ------------------------------------------------------------------------------------------------------
function G.remove_at(container, key)
    if is_map(container) then
        if rawget(container, key) == nil then
            fail("the map has no key '" .. str(key) .. "'")
        end
        rawset(container, key, nil)
        ORDER[container] = map_keys(container)
        return
    end
    local size = #container
    if key < 0 then
        key = key + size
    end
    if key < 0 or key >= size then
        out_of_range(key)
    end
    table.remove(container, key + 1)
end

function G.insert(items, position, value)
    local size = #items
    if position < 0 then
        position = math.max(0, size + position)
    end
    table.insert(items, math.min(position, size) + 1, value)
end

function G.remove(items, value)
    for index, entry in ipairs(items) do
        if eq(entry, value) then
            table.remove(items, index)
            return
        end
    end
end

local function shuffle_in_place(items)
    for index = #items, 2, -1 do
        local other = math.random(index)
        items[index], items[other] = items[other], items[index]
    end
end
G.shuffle_list = shuffle_in_place

local function before(a, b)
    if type(a) ~= type(b) then
        fail("can't sort '" .. str(a) .. "' and '" .. str(b) .. "' together")
    end
    return a < b
end

function G.sort_list(items, backwards)
    table.sort(items, before)
    if backwards then
        local size = #items
        for index = 1, floor(size / 2) do
            items[index], items[size - index + 1] = items[size - index + 1], items[index]
        end
    end
end

function G.check(passed, source)
    if not passed then
        fail("assert failed: " .. source)
    end
end

function G.throw(text)
    fail(str(text))
end

function G.kill()
    error(KILL, 0)
end

function G.time()
    return now() - started
end

-- ----- maths ------------------------------------------------------------------------------------------------------------------
local function radians(degrees) return degrees * math.pi / 180 end
local function degrees(rad) return rad * 180 / math.pi end
local function list_or(...)
    local first = ...
    if select("#", ...) == 1 and is_list(first) then
        return first
    end
    return {...}
end
local function clamp(x, low, high) return math.max(low, math.min(high, x)) end

function G.abs(x)
    if is_vec(x) then
        return G.mag(x)
    end
    return abs(x)
end
function G.min(...)
    local items, best = list_or(...), nil
    for _, value in ipairs(items) do
        if best == nil or value < best then best = value end
    end
    return best
end
function G.max(...)
    local items, best = list_or(...), nil
    for _, value in ipairs(items) do
        if best == nil or value > best then best = value end
    end
    return best
end
function G.round(x, digits)
    if digits == nil or digits == 0 then
        return floor(x + 0.5)
    end
    local scale = 10 ^ digits
    return floor(x * scale + 0.5) / scale
end
G.floor, G.ceil, G.sqrt, G.exp = floor, math.ceil, sqrt, math.exp
function G.sin(d) return math.sin(radians(d)) end
function G.cos(d) return math.cos(radians(d)) end
function G.tan(d) return math.tan(radians(d)) end
function G.asin(x) return degrees(math.asin(x)) end
function G.acos(x) return degrees(math.acos(x)) end
function G.atan(x) return degrees(math.atan(x)) end
function G.atan2(y, x) return degrees((math.atan2 or math.atan)(y, x)) end
G.rad, G.deg, G.clamp = radians, degrees, clamp
function G.lerp(a, b, t) return a + (b - a) * t end
function G.sign(x)
    if x > 0 then return 1 elseif x < 0 then return -1 end
    return 0
end
function G.mag(v)
    return sqrt(v.x * v.x + v.y * v.y + v.z * v.z)
end
function G.dist(a, b, c, d)
    if is_vec(a) then
        return G.mag(a - b)
    end
    return sqrt((c - a) ^ 2 + (d - b) ^ 2)
end
function G.pow(x, n) return x ^ n end
function G.log(x, base)
    if base == nil then
        return math.log(x)
    end
    return math.log(x) / math.log(base)
end
function G.wrap(x, low, high) return low + G.mod(x - low, high - low) end
function G.remap(x, l1, h1, l2, h2) return l2 + (x - l1) * (h2 - l2) / (h1 - l1) end
function G.approach(x, target, step)
    step = abs(step)
    if x < target then
        return math.min(x + step, target)
    end
    return math.max(x - step, target)
end
function G.angleto(a, b, c, d)
    if is_vec(a) then
        a, b, c, d = a.x, a.y, b.x, b.y
    end
    return degrees((math.atan2 or math.atan)(d - b, c - a))
end
local function whole(x) return x == floor(x) end
function G.random(low, high)
    if low == nil then
        return math.random()
    end
    if low > high then
        low, high = high, low
    end
    if whole(low) and whole(high) then
        return math.random(low, high)
    end
    return low + math.random() * (high - low)
end
function G.randint(low, high)
    low, high = floor(low), floor(high)
    if low > high then
        low, high = high, low
    end
    return math.random(low, high)
end
function G.chance(percent) return math.random() * 100 < percent end
function G.hsv(hue, saturation, value)
    local h, s, v = G.mod(hue, 360) / 60, clamp(saturation, 0, 1), clamp(value, 0, 1)
    local i, f = floor(h) % 6, h - floor(h)
    local p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    local rgb = ({{v, t, p}, {q, v, p}, {p, v, t}, {p, q, v}, {t, p, v}, {v, p, q}})[i + 1]
    return {G.round(rgb[1] * 255), G.round(rgb[2] * 255), G.round(rgb[3] * 255)}
end

-- noise: the same numbers gublan gives (32-bit maths done with exact halves)
local function mul32(a, b)
    a, b = a % 4294967296, b % 4294967296
    local ah, al = floor(a / 65536), a % 65536
    local bh, bl = floor(b / 65536), b % 65536
    return (((ah * bl + al * bh) % 65536) * 65536 + al * bl) % 4294967296
end
local function xor32(a, b)
    local result, place = 0, 1
    while a > 0 or b > 0 do
        local x, y = a % 2, b % 2
        if x ~= y then
            result = result + place
        end
        a, b, place = (a - x) / 2, (b - y) / 2, place * 2
    end
    return result
end
local function noise_hash(x, y)
    local n = (mul32(x, 374761393) + mul32(y, 668265263)) % 4294967296
    n = mul32(xor32(n, floor(n / 8192)), 1274126177)
    return xor32(n % 65536, floor(n / 65536) % 65536) / 65535
end
function G.noise(x, y)
    y = y or 0
    local x0, y0 = floor(x), floor(y)
    local fx, fy = x - x0, y - y0
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    local top = noise_hash(x0, y0) + (noise_hash(x0 + 1, y0) - noise_hash(x0, y0)) * fx
    local bottom = noise_hash(x0, y0 + 1) + (noise_hash(x0 + 1, y0 + 1) - noise_hash(x0, y0 + 1)) * fx
    return top + (bottom - top) * fy
end

-- ----- text -----------------------------------------------------------------------------------------------------------------------
local function trim(text)
    return (str(text):gsub("^%s+", ""):gsub("%s+$", ""))
end

local function plain_split(text, separator)
    local out, start = {}, 1
    while true do
        local first, last = string.find(text, separator, start, true)
        if not first then
            out[#out + 1] = text:sub(start)
            return out
        end
        out[#out + 1] = text:sub(start, first - 1)
        start = last + 1
    end
end

local function words(text)
    local out = {}
    for word in str(text):gmatch("%S+") do
        out[#out + 1] = word
    end
    return out
end

local function utf8_char(code)
    if code < 128 then
        return string.char(code)
    elseif code < 2048 then
        return string.char(192 + floor(code / 64), 128 + code % 64)
    elseif code < 65536 then
        return string.char(224 + floor(code / 4096), 128 + floor(code / 64) % 64, 128 + code % 64)
    end
    return string.char(240 + floor(code / 262144), 128 + floor(code / 4096) % 64, 128 + floor(code / 64) % 64,
        128 + code % 64)
end

local function utf8_code(letter)
    local first = letter:byte(1) or 0
    if first < 128 then
        return first
    elseif first < 224 then
        return (first - 192) * 64 + letter:byte(2) - 128
    elseif first < 240 then
        return (first - 224) * 4096 + (letter:byte(2) - 128) * 64 + letter:byte(3) - 128
    end
    return (first - 240) * 262144 + (letter:byte(2) - 128) * 4096 + (letter:byte(3) - 128) * 64 + letter:byte(4) - 128
end

local function looks_like_number(text)
    return text:match("^%s*%-?%d+%.?%d*%s*$") ~= nil or text:match("^%s*%-?%.%d+%s*$") ~= nil
end

function G.num(value)
    if type(value) == "number" then
        return value
    end
    local text = trim(value)
    local number = not text:lower():find("^%-?0x") and tonumber(text) or nil
    if number == nil then
        fail("'" .. str(value) .. "' is not a number")
    end
    return number
end
G.number = G.num
function G.int(value)
    if type(value) == "string" then
        value = G.num(value)
    end
    if value < 0 then
        return math.ceil(value)
    end
    return floor(value)
end
function G.len(value)
    if type(value) == "string" then
        return #chars(value)
    elseif is_map(value) then
        return #map_keys(value)
    elseif is_list(value) then
        return #value
    end
    fail("'" .. str(value) .. "' has no length")
end
G["type"] = function(value)
    local kind = type(value)
    if kind == "boolean" or kind == "number" or kind == "function" then
        return kind
    elseif kind == "string" then
        return "text"
    elseif value == nil then
        return "none"
    elseif is_vec(value) then
        return "vec" .. value.n
    elseif is_map(value) then
        return "map"
    end
    return "list"
end
function G.upper(text) return str(text):upper() end
function G.lower(text) return str(text):lower() end
G.trim = trim
function G.capitalize(text)
    return (str(text):gsub("%f[%w_]%l", string.upper))
end
function G.join(items, separator)
    local parts = {}
    for index, value in ipairs(items) do
        parts[index] = str(value)
    end
    return concat(parts, separator == nil and " " or str(separator))
end
function G.split(text, separator)
    if separator == nil or separator == "" then
        return words(text)
    end
    return plain_split(str(text), str(separator))
end
function G.replace(text, old, new)
    text, old = str(text), str(old)
    if old == "" then
        return text
    end
    return concat(plain_split(text, old), str(new))
end
function G.startswith(text, start)
    start = str(start)
    return str(text):sub(1, #start) == start
end
function G.endswith(text, ending)
    ending = str(ending)
    return ending == "" or str(text):sub(-#ending) == ending
end
function G.pad(value, width, fill)
    local text = str(value)
    fill = fill == nil and " " or str(fill)
    if fill == "0" and text:sub(1, 1) == "-" then
        return "-" .. G.pad(text:sub(2), width - 1, "0")
    end
    local missing = floor(width) - #chars(text)
    if missing <= 0 then
        return text
    end
    return string.rep(fill, missing) .. text
end
function G.decimals(x, digits)
    return string.format("%." .. floor(digits) .. "f", x)
end
function G.isnumber(value)
    if type(value) == "number" then
        return true
    end
    return type(value) == "string" and looks_like_number(value)
end
function G.lines(text)
    text = str(text):gsub("\r\n", "\n"):gsub("\r", "\n")
    if text == "" then
        return {}
    end
    local out = plain_split(text, "\n")
    if out[#out] == "" then
        out[#out] = nil
    end
    return out
end
G.words = words
function G.char(code) return utf8_char(floor(code)) end
function G.code(letter) return utf8_code(str(letter)) end
function G.date() return os.date("%Y-%m-%d") end
function G.clock() return os.date("%H:%M") end
function G.now() return os.time() end

-- ----- lists and little functions -------------------------------------------------------------------------------------------------
local function sequence(value)
    if is_map(value) then
        return map_keys(value)
    elseif type(value) == "string" then
        return chars(value)
    end
    return value
end

function G.call(f, ...) return f(...) end
function G.map(items, f)
    local out = {}
    for index, value in ipairs(sequence(items)) do
        out[index] = f(value)
    end
    return out
end
function G.filter(items, f)
    local out = {}
    for _, value in ipairs(sequence(items)) do
        if G.truthy(f(value)) then
            out[#out + 1] = value
        end
    end
    return out
end
function G.reduce(items, f, start)
    items = sequence(items)
    local first = 1
    if start == nil then
        start, first = items[1], 2
    end
    for index = first, #items do
        start = f(start, items[index])
    end
    return start
end
function G.find(items, f)
    for _, value in ipairs(sequence(items)) do
        if G.truthy(f(value)) then
            return value
        end
    end
    return nil
end
function G.any(items, f)
    for _, value in ipairs(sequence(items)) do
        if G.truthy(f and f(value) or (not f and value)) then
            return true
        end
    end
    return false
end
function G.every(items, f)
    for _, value in ipairs(sequence(items)) do
        if not G.truthy(f and f(value) or (not f and value)) then
            return false
        end
    end
    return true
end
function G.sortby(items, f)
    local marked = {}
    for index, value in ipairs(sequence(items)) do
        marked[index] = {f(value), index, value}
    end
    table.sort(marked, function(a, b)
        if a[1] == b[1] then
            return a[2] < b[2]
        end
        return before(a[1], b[1])
    end)
    local out = {}
    for index, entry in ipairs(marked) do
        out[index] = entry[3]
    end
    return out
end
function G.zip(...)
    local lists, size = {...}, huge
    for index, list in ipairs(lists) do
        lists[index] = sequence(list)
        size = math.min(size, #lists[index])
    end
    local out = {}
    for index = 1, (size == huge and 0 or size) do
        local row = {}
        for which, list in ipairs(lists) do
            row[which] = list[index]
        end
        out[index] = row
    end
    return out
end
function G.flat(items)
    local out = {}
    for _, value in ipairs(items) do
        if is_list(value) then
            for _, inner in ipairs(value) do
                out[#out + 1] = inner
            end
        else
            out[#out + 1] = value
        end
    end
    return out
end
G["repeat"] = function(value, times)
    times = math.max(0, floor(times))
    if is_list(value) then
        local out = {}
        for _ = 1, times do
            for _, entry in ipairs(value) do
                out[#out + 1] = entry
            end
        end
        return out
    end
    return string.rep(str(value), times)
end
function G.range(first, last, step)
    if last == nil then
        first, last = 0, first
    end
    step = step or 1
    if step == 0 then
        fail("range() step cannot be zero")
    end
    local out, value = {}, floor(first)
    while (step > 0 and value < last) or (step < 0 and value > last) do
        out[#out + 1] = value
        value = value + step
    end
    return out
end
function G.sum(items)
    local total = 0
    for _, value in ipairs(items) do
        total = total + value
    end
    return total
end
function G.sort(items)
    local copy = G.slice(sequence(items))
    table.sort(copy, before)
    return copy
end
function G.reverse(items)
    if type(items) == "string" then
        return concat(G.reverse(chars(items)))
    end
    local out = {}
    for index = #items, 1, -1 do
        out[#out + 1] = items[index]
    end
    return out
end
function G.keys(map)
    return map_keys(map)
end
function G.values(map)
    local out = {}
    for index, key in ipairs(map_keys(map)) do
        out[index] = rawget(map, key)
    end
    return out
end
function G.indexof(container, value)
    if type(container) == "string" then
        local found = string.find(container, str(value), 1, true)
        return found and #chars(container:sub(1, found - 1)) or -1
    end
    for index, entry in ipairs(container) do
        if eq(entry, value) then
            return index - 1
        end
    end
    return -1
end
function G.choice(items)
    items = sequence(items)
    if #items == 0 then
        fail("choice() needs a list with something in it")
    end
    return items[math.random(#items)]
end
function G.shuffle(items)
    local copy = G.slice(sequence(items))
    shuffle_in_place(copy)
    return copy
end
function G.unique(items)
    local out = {}
    for _, value in ipairs(items) do
        if not G.contains(out, value) then
            out[#out + 1] = value
        end
    end
    return out
end
function G.count(container, value)
    if type(container) == "string" then
        value = str(value)
        if value == "" then
            return 0
        end
        return #plain_split(container, value) - 1
    end
    local total = 0
    for _, entry in ipairs(container) do
        if eq(entry, value) then
            total = total + 1
        end
    end
    return total
end
function G.average(items)
    return G.sum(items) / #items
end

-- ----- added in 1.0.7: more math, lists and maps, text, colours and timers -----------------------------------------------
local EASINGS = {"linear", "in", "out", "inout", "smooth", "bounce", "elastic", "back"}
function G.ease(t, kind)
    t = t < 0 and 0 or (t > 1 and 1 or t)
    kind = trim(str(kind == nil and "inout" or kind)):lower()
    if kind == "linear" then return t end
    if kind == "in" then return t * t end
    if kind == "out" then return 1 - (1 - t) * (1 - t) end
    if kind == "inout" then
        if t < 0.5 then return 2 * t * t end
        return 1 - (-2 * t + 2) ^ 2 / 2
    end
    if kind == "smooth" then return t * t * (3 - 2 * t) end
    if kind == "bounce" then
        local n, d = 7.5625, 2.75
        if t < 1 / d then return n * t * t end
        if t < 2 / d then t = t - 1.5 / d; return n * t * t + 0.75 end
        if t < 2.5 / d then t = t - 2.25 / d; return n * t * t + 0.9375 end
        t = t - 2.625 / d
        return n * t * t + 0.984375
    end
    if kind == "elastic" then
        if t == 0 or t == 1 then return t end
        return 2 ^ (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1
    end
    if kind == "back" then
        local c = 1.70158
        return 1 + (c + 1) * (t - 1) ^ 3 + c * (t - 1) ^ 2
    end
    fail("'" .. kind .. "' is not an easing. try: " .. concat(EASINGS, ", "))
end
function G.hypot(x, y) return math.sqrt(x * x + y * y) end
function G.fract(x) return x - floor(x) end
function G.smoothstep(low, high, x)
    if high == low then
        return x < low and 0 or 1
    end
    local t = clamp((x - low) / (high - low), 0, 1)
    return t * t * (3 - 2 * t)
end
function G.snap(x, step)
    if step == 0 then return x end
    return floor(x / step + 0.5) * step
end
function G.between(x, low, high) return low <= x and x <= high end
function G.gcd(a, b)
    a, b = abs(floor(a)), abs(floor(b))
    while b ~= 0 do a, b = b, a % b end
    return a
end
function G.median(items)
    if #items == 0 then fail("median() of an empty list has no middle") end
    local sorted = G.sort(items)
    local middle = floor(#sorted / 2)
    if #sorted % 2 == 1 then return sorted[middle + 1] end
    return (sorted[middle] + sorted[middle + 1]) / 2
end
function G.product(items)
    local total = 1
    for _, value in ipairs(items) do total = total * value end
    return total
end
function G.first(items)
    items = sequence(items)
    return items[1]
end
function G.last(items)
    items = sequence(items)
    return items[#items]
end
function G.take(items, n) return G.slice(items, 0, math.max(0, floor(n))) end
function G.drop(items, n) return G.slice(items, math.max(0, floor(n))) end
function G.chunk(items, size)
    size = floor(size)
    if size < 1 then fail("chunk() needs a size of 1 or more") end
    items = sequence(items)
    local out = {}
    for start = 1, #items, size do
        local piece = {}
        for index = start, math.min(#items, start + size - 1) do piece[#piece + 1] = items[index] end
        out[#out + 1] = piece
    end
    return out
end
function G.enumerate(items)
    local out = {}
    for index, value in ipairs(sequence(items)) do out[index] = {index - 1, value} end
    return out
end
local function best_by(items, f, better)
    items = sequence(items)
    if #items == 0 then return nil end
    local best, key = items[1], f(items[1])
    for index = 2, #items do
        local value = f(items[index])
        if better(value, key) then best, key = items[index], value end
    end
    return best
end
function G.minby(items, f) return best_by(items, f, function(a, b) return a < b end) end
function G.maxby(items, f) return best_by(items, f, function(a, b) return a > b end) end
function G.groupby(items, f)
    local groups = new_map()
    for _, value in ipairs(sequence(items)) do
        local key = str(f(value))
        local group = rawget(groups, key)
        if group == nil then
            group = {}
            groups[key] = group
        end
        group[#group + 1] = value
    end
    return groups
end
function G.without(items, value)
    local out = {}
    for _, entry in ipairs(sequence(items)) do
        if not eq(entry, value) then out[#out + 1] = entry end
    end
    return out
end
function G.fill(value, count)
    local out = {}
    for index = 1, math.max(0, floor(count)) do
        if is_list(value) then
            out[index] = G.slice(value)
        elseif is_map(value) then
            out[index] = G.merge(value, new_map())
        else
            out[index] = value
        end
    end
    return out
end
function G.merge(first, second)
    local merged = new_map()
    for _, source_map in ipairs({first, second}) do
        for _, key in ipairs(map_keys(source_map)) do merged[key] = rawget(source_map, key) end
    end
    return merged
end
function G.get(container, key, default)
    if is_map(container) then
        local found = rawget(container, key)
        if found == nil then found = rawget(container, str(key)) end
        if found == nil then return default end
        return found
    end
    if type(key) ~= "number" or key ~= floor(key) then return default end
    local items = sequence(container)
    local index = key < 0 and #items + key + 1 or key + 1
    if index >= 1 and index <= #items then return items[index] end
    return default
end
function G.entries(map)
    local out = {}
    for _, key in ipairs(map_keys(map)) do out[#out + 1] = {key, rawget(map, key)} end
    return out
end
function G.frompairs(pairs_list)
    local made = new_map()
    for _, pair in ipairs(pairs_list) do
        if not is_list(pair) or #pair ~= 2 then fail("frompairs() needs a list of [name, value] pairs") end
        made[type(pair[1]) == "string" and pair[1] or str(pair[1])] = pair[2]
    end
    return made
end
function G.commas(x)
    local text = str(x)
    local sign, rest = text:match("^(%-?)(.*)$")
    local digits, tail = rest:match("^(%d+)(.*)$")
    if not digits or (tail ~= "" and tail:sub(1, 1) ~= ".") then return text end
    local grouped = digits:reverse():gsub("(%d%d%d)", "%1,"):reverse():gsub("^,", "")
    return sign .. grouped .. tail
end
function G.ordinal(n)
    n = floor(n)
    local last_two, last = abs(n) % 100, abs(n) % 10
    local suffix = "th"
    if last_two < 11 or last_two > 13 then
        suffix = ({[1] = "st", [2] = "nd", [3] = "rd"})[last] or "th"
    end
    return str(n) .. suffix
end
function G.plural(count, word, many)
    if count == 1 then return str(count) .. " " .. str(word) end
    return str(count) .. " " .. (many == nil and (str(word) .. "s") or str(many))
end
function G.wraptext(text, width)
    width = floor(width)
    if width < 1 then fail("wraptext() needs a width of 1 or more") end
    local found = {}
    for _, paragraph in ipairs(plain_split(str(text), "\n")) do
        local line = ""
        for _, word in ipairs(words(paragraph)) do
            while #chars(word) > width do
                if line ~= "" then found[#found + 1] = line; line = "" end
                local letters = chars(word)
                found[#found + 1] = concat(letters, "", 1, width)
                word = concat(letters, "", width + 1, #letters)
            end
            if word ~= "" then
                if line == "" then
                    line = word
                elseif #chars(line) + 1 + #chars(word) <= width then
                    line = line .. " " .. word
                else
                    found[#found + 1] = line
                    line = word
                end
            end
        end
        found[#found + 1] = line
    end
    return found
end
local timers = {}
function G.cooldown(name, seconds)
    local key, time_now = "cooldown:" .. str(name), now()
    if timers[key] == nil or time_now - timers[key] >= seconds then
        timers[key] = time_now
        return true
    end
    return false
end
function G.pulse(name, seconds)
    local key, time_now = "pulse:" .. str(name), now()
    if timers[key] == nil then
        timers[key] = time_now
        return false
    end
    if time_now - timers[key] >= seconds then
        timers[key] = time_now
        return true
    end
    return false
end
function G.after(name, seconds)
    local key, time_now = "after:" .. str(name), now()
    if timers[key] == nil then
        timers[key] = time_now
        return seconds <= 0
    end
    return time_now - timers[key] >= seconds
end

-- ----- json -------------------------------------------------------------------------------------------------------------------------
local function storable(value, depth)
    depth = depth or 0
    if depth > 32 then
        fail("that value is nested too deeply to save")
    end
    if is_vec(value) then
        local out = new_map()
        out["$vec" .. value.n] = value.n == 2 and {value.x, value.y} or {value.x, value.y, value.z}
        return out
    elseif type(value) == "number" and (value ~= value or value == huge or value == -huge) then
        fail("only finite numbers can be saved")
    elseif type(value) == "function" then
        fail("can't save function values")
    end
    return value
end

local function json_number(x)
    if x == floor(x) and abs(x) < 1e15 then
        return string.format("%d", x)
    end
    for digits = 15, 17 do
        local text = string.format("%." .. digits .. "g", x)
        if tonumber(text) == x then
            return text
        end
    end
    return string.format("%.17g", x)
end

local ESCAPES = {['"'] = '\\"', ["\\"] = "\\\\", ["\n"] = "\\n", ["\r"] = "\\r", ["\t"] = "\\t", ["\b"] = "\\b",
    ["\f"] = "\\f"}
local function json_string(text)
    return '"' .. text:gsub('[%c"\\]', function(char)
        return ESCAPES[char] or string.format("\\u%04x", char:byte())
    end) .. '"'
end

local function to_json(value, depth)
    value = storable(value, depth)
    depth = depth or 0
    local kind = type(value)
    if value == nil then
        return "null"
    elseif kind == "boolean" then
        return value and "true" or "false"
    elseif kind == "number" then
        return json_number(value)
    elseif kind == "string" then
        return json_string(value)
    elseif is_map(value) then
        local parts = {}
        for _, key in ipairs(map_keys(value)) do
            parts[#parts + 1] = json_string(str(key)) .. ": " .. to_json(rawget(value, key), depth + 1)
        end
        return "{" .. concat(parts, ", ") .. "}"
    elseif is_list(value) then
        local parts = {}
        for index = 1, #value do
            parts[index] = to_json(value[index], depth + 1)
        end
        return "[" .. concat(parts, ", ") .. "]"
    end
    fail("can't save " .. G["type"](value) .. " values")
end

local function from_json(text)
    local position = 1
    local function bad()
        fail("fromjson() got text that isn't json")
    end
    local function space()
        position = text:find("[^ \t\r\n]", position) or #text + 1
    end
    local read
    local function read_string()
        local out = {}
        position = position + 1
        while true do
            local char = text:sub(position, position)
            if char == "" then
                bad()
            elseif char == '"' then
                position = position + 1
                return concat(out)
            elseif char == "\\" then
                local code = text:sub(position + 1, position + 1)
                if code == "u" then
                    local hex = text:sub(position + 2, position + 5)
                    if not hex:match("^%x%x%x%x$") then bad() end
                    out[#out + 1] = utf8_char(tonumber(hex, 16))
                    position = position + 6
                else
                    local simple = ({b = "\b", f = "\f", n = "\n", r = "\r", t = "\t"})[code]
                    out[#out + 1] = simple or code
                    position = position + 2
                end
            else
                out[#out + 1] = char
                position = position + 1
            end
        end
    end
    read = function()
        space()
        local char = text:sub(position, position)
        if char == "{" then
            local map = new_map()
            position = position + 1
            space()
            if text:sub(position, position) == "}" then
                position = position + 1
                return map
            end
            while true do
                space()
                if text:sub(position, position) ~= '"' then bad() end
                local key = read_string()
                space()
                if text:sub(position, position) ~= ":" then bad() end
                position = position + 1
                local value = read()
                if value ~= nil then
                    map[key] = value
                end
                space()
                local next_char = text:sub(position, position)
                position = position + 1
                if next_char == "}" then
                    break
                elseif next_char ~= "," then
                    bad()
                end
            end
            local keys = map_keys(map)
            if #keys == 1 and (keys[1] == "$vec2" or keys[1] == "$vec3") then
                local parts = rawget(map, keys[1])
                if is_list(parts) and (#parts == 2 or #parts == 3) then
                    return vec(#parts, parts[1], parts[2], parts[3])
                end
            end
            return map
        elseif char == "[" then
            local list = {}
            position = position + 1
            space()
            if text:sub(position, position) == "]" then
                position = position + 1
                return list
            end
            while true do
                list[#list + 1] = read()
                space()
                local next_char = text:sub(position, position)
                position = position + 1
                if next_char == "]" then
                    return list
                elseif next_char ~= "," then
                    bad()
                end
            end
        elseif char == '"' then
            return read_string()
        end
        for word, value in pairs({["true"] = true, ["false"] = false, null = nil}) do
            if text:sub(position, position + #word - 1) == word then
                position = position + #word
                return value
            end
        end
        if text:sub(position, position + 3) == "null" then
            position = position + 4
            return nil
        end
        local number = text:match("^-?%d+%.?%d*[eE]?[-+]?%d*", position)
        if not number or number == "" or tonumber(number) == nil then
            bad()
        end
        position = position + #number
        return tonumber(number)
    end
    local value = read()
    space()
    if position <= #text then
        bad()
    end
    return value
end

function G.tojson(value) return to_json(value) end
function G.fromjson(text) return from_json(str(text)) end

-- ----- saving ------------------------------------------------------------------------------------------------------------------------
local save_name = "program"
local function save_file()
    local name = save_name:gsub("[^%w.-]+", "_")
    return "gublan_" .. name .. "_saves.json"
end
local function read_saves()
    local text
    if has_love and love.filesystem then
        text = love.filesystem.read(save_file())
    else
        local handle = io.open(save_file(), "r")
        if handle then
            text = handle:read("*a")
            handle:close()
        end
    end
    if text then
        local ok, data = pcall(from_json, text)
        if ok and is_map(data) then
            return data
        end
    end
    return new_map()
end
local function write_saves(data)
    local text = to_json(data)
    if has_love and love.filesystem then
        local ok, problem = love.filesystem.write(save_file(), text)
        if not ok then
            fail("could not save: " .. tostring(problem))
        end
        return
    end
    local handle, problem = io.open(save_file(), "w")
    if not handle then
        fail("could not save: " .. tostring(problem))
    end
    handle:write(text)
    handle:close()
end
function G.save(name, value)
    local data = read_saves()
    data[str(name)] = from_json(to_json(value))
    write_saves(data)
end
function G.load(name, fallback)
    local value = rawget(read_saves(), str(name))
    if value == nil then
        if fallback == nil then
            return 0
        end
        return fallback
    end
    return value
end
function G.saved(name)
    return rawget(read_saves(), str(name)) ~= nil
end
function G.forget(name)
    local data = read_saves()
    if str(name) == "all" then
        data = new_map()
    else
        rawset(data, str(name), nil)
    end
    write_saves(data)
end

function G.fetch(url)
    url = str(url)
    if url:sub(1, 8) ~= "https://" then
        fail("get only works with https:// addresses")
    end
    local ok, https = pcall(require, "https")
    if ok and type(https) == "table" and https.request then
        local code, body = https.request(url)
        if type(code) == "number" and code >= 200 and code < 300 then
            return body or ""
        end
        fail("get could not reach " .. url .. " (" .. tostring(code) .. ")")
    end
    fail("get needs love2d 12 (its https module) in lua")
end

-- ----- the window ------------------------------------------------------------------------------------------------------------------
local COLORS = {
    red = {225, 65, 65}, blue = {65, 145, 245}, green = {65, 205, 105}, yellow = {245, 215, 65},
    white = {240, 240, 240}, moss = {148, 182, 108}, orange = {245, 145, 65}, purple = {170, 115, 225},
    cyan = {75, 205, 215}, black = {12, 12, 12}, gray = {128, 128, 128}, grey = {128, 128, 128},
    darkgray = {52, 52, 52}, pink = {240, 130, 190}, brown = {140, 95, 60}, lime = {170, 235, 70},
    teal = {40, 150, 140}, navy = {25, 40, 90}, gold = {225, 185, 60}, sand = {215, 195, 150},
    sky = {135, 200, 245}, forest = {40, 95, 55},
}
local KEY_ALIASES = {
    esc = "escape", enter = "return", spacebar = "space", shift = "left shift", lshift = "left shift",
    rshift = "right shift", ctrl = "left ctrl", control = "left ctrl", lctrl = "left ctrl", rctrl = "right ctrl",
    alt = "left alt", lalt = "left alt", ralt = "right alt", del = "delete", bksp = "backspace", pgup = "page up",
    pgdn = "page down", arrowleft = "left", arrowright = "right", arrowup = "up", arrowdown = "down",
}
-- love2d's key names -> gublan's
local LOVE_KEYS = {
    lshift = "left shift", rshift = "right shift", lctrl = "left ctrl", rctrl = "right ctrl", lalt = "left alt",
    ralt = "right alt", pageup = "page up", pagedown = "page down", kpenter = "enter", capslock = "caps lock",
    lgui = "left meta", rgui = "right meta",
}

local window_open = false
local objects, order = {}, {}
local title, background, color, text_size, fps_limit = "", {12, 12, 12}, "white", 24, 60
local fonts, pictures = {}, {}
local held, presses, mouse_held, clicks = {}, {}, {}, {}
local mouse_x, mouse_y = 0, 0
local focused, dragging, ui_label = nil, nil, nil
local overlay, shown_error = nil, nil

local function rgb(value)
    if is_list(value) then
        return clamp(value[1] or 0, 0, 255) / 255, clamp(value[2] or 0, 0, 255) / 255, clamp(value[3] or 0, 0, 255) / 255
    end
    local text = str(value):lower()
    local named = COLORS[text]
    if named then
        return named[1] / 255, named[2] / 255, named[3] / 255
    end
    local hex = text:match("^#(%x+)$")
    if hex and #hex == 3 then
        hex = hex:gsub("%x", "%0%0")
    end
    if hex and #hex == 6 then
        return tonumber(hex:sub(1, 2), 16) / 255, tonumber(hex:sub(3, 4), 16) / 255, tonumber(hex:sub(5, 6), 16) / 255
    end
    return 240 / 255, 240 / 255, 240 / 255
end

local function channels(value)
    if is_list(value) then return {clamp(floor(value[1]), 0, 255), clamp(floor(value[2]), 0, 255), clamp(floor(value[3]), 0, 255)} end
    local text = str(value):lower()
    if COLORS[text] then return {COLORS[text][1], COLORS[text][2], COLORS[text][3]} end
    local hex = text:match("^#(%x+)$")
    if hex and #hex == 3 then hex = hex:gsub("%x", "%0%0") end
    if hex and #hex == 6 then
        return {tonumber(hex:sub(1, 2), 16), tonumber(hex:sub(3, 4), 16), tonumber(hex:sub(5, 6), 16)}
    end
    fail("'" .. str(value) .. "' is not a colour. use a name like red, #ff8800 or [255, 136, 0]")
end
function G.mixcolor(a, b, t)
    local one, two = channels(a), channels(b)
    t = clamp(t, 0, 1)
    return {floor(one[1] + (two[1] - one[1]) * t + 0.5), floor(one[2] + (two[2] - one[2]) * t + 0.5),
        floor(one[3] + (two[3] - one[3]) * t + 0.5)}
end
function G.randomcolor() return G.hsv(math.random() * 360, 0.65, 0.95) end

local function font(size)
    local pixels = math.max(6, floor(size * 0.72 + 0.5))
    if not fonts[pixels] then
        fonts[pixels] = love.graphics.newFont(pixels)
    end
    return fonts[pixels]
end

local function open_window()
    if not has_love then
        fail("drawing needs love2d: run this folder with love")
    end
    if not window_open then
        love.window.setMode(G.screen_width, G.screen_height, {vsync = 1})
        love.window.setTitle(title ~= "" and title or save_name)
        love.keyboard.setKeyRepeat(true)
        window_open = true
    end
end

function G.mode(kind)
    if kind ~= nil and kind ~= "2d" then
        fail("only 2d windows can be used outside gublan")
    end
    open_window()
end
function G.window(width, height, text)
    G.screen_width, G.screen_height = floor(width), floor(height)
    if text ~= nil then
        title = str(text)
    end
    if window_open then
        love.window.setMode(G.screen_width, G.screen_height, {vsync = 1})
        love.window.setTitle(title ~= "" and title or save_name)
    else
        open_window()
    end
end
function G.title(text)
    title = str(text)
    if window_open then
        love.window.setTitle(title)
    end
end
local function color_value(...)
    if select("#", ...) >= 3 then
        return {...}
    end
    return (...)
end
function G.background(...) background = color_value(...) end
function G.color(...) color = color_value(...) end
function G.fps(value) fps_limit = value end
function G.textsize(value) text_size = floor(value) end
function G.clear() end

local function add(name, kind, parts)
    name = str(name)
    open_window()
    local old = objects[name]
    if old == nil then
        order[#order + 1] = name
    else
        for _, key in ipairs({"layer", "alpha", "fixed"}) do
            if parts[key] == nil then parts[key] = old[key] end
        end
    end
    parts.type = kind
    parts.color = parts.color or color
    objects[name] = parts
    return parts
end

function G.ellipse(name, x, y, w, h) add(name, "ellipse", {x = x, y = y, w = w, h = h}) end
function G.polygon(name, points)
    if #points % 2 == 1 then fail("polygon points come in pairs: x y x y x y") end
    if #points < 6 then fail("a polygon needs at least three points") end
    local left, top, right, bottom = huge, huge, -huge, -huge
    for index = 1, #points, 2 do
        left, right = math.min(left, points[index]), math.max(right, points[index])
        top, bottom = math.min(top, points[index + 1]), math.max(bottom, points[index + 1])
    end
    local w, h = math.max(1, right - left), math.max(1, bottom - top)
    local relative = {}
    for index = 1, #points, 2 do
        relative[#relative + 1] = points[index] - left
        relative[#relative + 1] = points[index + 1] - top
    end
    add(name, "polygon", {x = left, y = top, w = w, h = h, pw = w, ph = h, points = relative})
end


local function object(name)
    name = str(name)
    local found = objects[name] or objects["button:" .. name]
    if not found then
        fail("there is no object named '" .. name .. "'")
    end
    return found
end

function G.paint(name, ...)
    local chosen = color_value(...)
    if name == "all" then
        for _, entry in pairs(objects) do
            entry.color = chosen
        end
    else
        object(name).color = chosen
    end
end

function G.box(name, x, y, w, h) add(name, "box", {x = x, y = y, w = w, h = h}) end
function G.circle(name, x, y, r) add(name, "circle", {x = x, y = y, r = r}) end
function G.line(name, x, y, x2, y2, width)
    add(name, "line", {x = x, y = y, x2 = x2, y2 = y2, width = math.max(1, width or 1)})
end
function G.text(name, x, y, text) add(name, "text", {x = x, y = y, text = str(text), size = text_size}) end

local function picture(path)
    if not pictures[path] then
        local ok, image = pcall(love.graphics.newImage, path)
        if not ok then
            fail("can't open the picture '" .. path .. "'")
        end
        pictures[path] = image
    end
    return pictures[path]
end
function G.image(name, path, x, y)
    open_window()
    add(name, "image", {x = x, y = y, picture = picture(str(path))})
end
function G.sprite(name, path, x, y, w, h)
    open_window()
    local previous = objects[str(name)]
    add(name, "sprite", {x = x, y = y, w = w, h = h, picture = picture(str(path)),
        angle = previous and previous.angle or 0})
end
function G.spin(name, angle) object(name).angle = angle end

function G.button(variable, x, y, w, h, label)
    if G.buttons[variable] == nil then
        G.buttons[variable] = 0
    end
    add("button:" .. variable, "button", {x = x, y = y, w = w, h = h, label = str(label), variable = variable})
end
function G.ui_button(label)
    open_window()
    ui_label = str(label)
end
function G.textbox(name, x, y, w, hint)
    local old = objects[str(name)] or {}
    add(name, "textbox", {x = x, y = y, w = w, h = 36, hint = hint == nil and "" or str(hint), text = old.text or "",
        cursor = old.cursor or 0, submitted = false})
end
function G.slider(name, x, y, w, low, high, start)
    local value = start == nil and low or clamp(start, math.min(low, high), math.max(low, high))
    add(name, "slider", {x = x, y = y, w = w, h = 20, min = low, max = high, value = value,
        whole = whole(low) and whole(high)})
end
function G.checkbox(name, x, y, label)
    add(name, "checkbox", {x = x, y = y, w = 22, h = 22, label = str(label), checked = false})
end
function G.focus(name)
    focused = name ~= nil and str(name) or nil
end

local FIELD_ALIASES = {width = "w", height = "h", radius = "r", rotation = "angle"}
-- ----- the view, effects and tweens ---------------------------------------------------------------------------------------------
local scroll_x, scroll_y, shake, shake_x, shake_y = 0, 0, nil, 0, 0
local particles, tweens = {}, {}
local effects_time = now()
local draw_alpha = 1
function G.scroll(x, y) scroll_x, scroll_y = x, y end
function G.scrollx() return scroll_x end
function G.scrolly() return scroll_y end
function G.shake(strength, seconds)
    seconds = seconds == nil and 0.3 or seconds
    if strength < 0 or seconds < 0 then fail("shake strength and time can't be negative") end
    if strength > 0 and seconds > 0 then
        shake = {strength, seconds, seconds}
    else
        shake, shake_x, shake_y = nil, 0, 0
    end
end
function G.particles(x, y, count, speed)
    count, speed = floor(count or 20), speed or 160
    if count < 0 or count > 500 then fail("particles can make from 0 to 500 at a time") end
    local r, g, b = rgb(color)
    for _ = 1, count do
        local angle = math.random() * math.pi * 2
        local velocity = speed * (0.25 + math.random() * 0.75)
        local life = 0.45 + math.random() * 0.55
        particles[#particles + 1] = {x, y, math.cos(angle) * velocity, math.sin(angle) * velocity, life, life, r, g, b,
            3 + math.random() * 3}
    end
    while #particles > 2000 do table.remove(particles, 1) end
end
local TWEEN_FIELDS = {x = "x", y = "y", z = "z", w = "w", width = "w", h = "h", height = "h", r = "r", radius = "r",
    angle = "angle", rotation = "angle", opacity = "alpha", alpha = "alpha", size = "size"}
local function apply_tween(found, key, value)
    if (key == "x" or key == "y") and found.type == "line" then
        found[key .. "2"] = found[key .. "2"] + value - found[key]
    end
    if key == "alpha" then
        value = clamp(value, 0, 1)
    elseif key == "w" or key == "h" or key == "r" or key == "size" then
        value = math.max(0, value)
    end
    found[key] = value
end
function G.tween(name, field, value, seconds, easing)
    local found = object(name)
    local key = TWEEN_FIELDS[str(field):lower()]
    local pictured = found.picture ~= nil
    if key == nil or not (found[key] ~= nil or key == "alpha" or (pictured and (key == "w" or key == "h" or key == "angle"))) then
        fail("tween can change x, y, w, h, r, angle or opacity of a " .. found.type .. ", not '" .. str(field) .. "'")
    end
    if seconds < 0 then fail("tween time can't be negative") end
    easing = str(easing or "inout"):lower()
    G.ease(0, easing)
    local start = found[key]
    if key == "alpha" and start == nil then start = 1 end
    if start == nil and pictured then
        start = key == "w" and found.picture:getWidth() or (key == "h" and found.picture:getHeight() or 0)
    end
    for index = #tweens, 1, -1 do
        if tweens[index][1] == found and tweens[index][2] == key then table.remove(tweens, index) end
    end
    if seconds == 0 then
        apply_tween(found, key, value)
    else
        tweens[#tweens + 1] = {found, key, start or 0, value, seconds, 0, easing}
    end
end
function G.opacity(name, value)
    value = clamp(value, 0, 1)
    if name == "all" then
        for _, found in pairs(objects) do found.alpha = value end
        return
    end
    object(name).alpha = value
end
function G.layer(name, value) object(name).layer = value end
function G.fixed(name) object(name).fixed = true end
local function tick_effects()
    local time_now = now()
    local step = math.min(0.1, math.max(0, time_now - effects_time))
    effects_time = time_now
    for index = #tweens, 1, -1 do
        local tween = tweens[index]
        tween[6] = tween[6] + step
        local progress = tween[5] > 0 and math.min(1, tween[6] / tween[5]) or 1
        apply_tween(tween[1], tween[2], tween[3] + (tween[4] - tween[3]) * G.ease(progress, tween[7]))
        if progress >= 1 then table.remove(tweens, index) end
    end
    local alive = {}
    for _, particle in ipairs(particles) do
        particle[5] = particle[5] - step
        if particle[5] > 0 then
            particle[1] = particle[1] + particle[3] * step
            particle[2] = particle[2] + particle[4] * step
            particle[4] = particle[4] + 240 * step
            alive[#alive + 1] = particle
        end
    end
    particles = alive
    if shake then
        shake[2] = shake[2] - step
        if shake[2] <= 0 then
            shake, shake_x, shake_y = nil, 0, 0
        else
            local strength = shake[1] * shake[2] / shake[3]
            shake_x, shake_y = (math.random() * 2 - 1) * strength, (math.random() * 2 - 1) * strength
        end
    end
end

local function object_field(name, key)
    local found = object(name)
    key = FIELD_ALIASES[key] or key
    if key == "visible" then
        return not found.hidden
    elseif key == "focused" then
        return focused == str(name)
    elseif key == "submitted" then
        local was = found.submitted == true
        found.submitted = false
        return was
    elseif (key == "w" or key == "h") and found[key] == nil and found.picture then
        return key == "w" and found.picture:getWidth() or found.picture:getHeight()
    end
    local value = found[key]
    if value == nil or key == "type" or key == "picture" then
        fail("object '" .. str(name) .. "' has no '" .. key .. "'")
    end
    return value
end
local function set_object_field(name, key, value)
    local found = object(name)
    key = FIELD_ALIASES[key] or key
    if key == "visible" then
        found.hidden = not G.truthy(value)
    elseif key == "text" and found.type == "textbox" then
        found.text = str(value)
        found.cursor = #chars(found.text)
    else
        found[key] = value
    end
end

function G.field(base, key)
    if type(base) == "string" then
        return object_field(base, key)
    elseif is_vec(base) then
        if key == "x" or key == "y" or key == "z" then
            return base[key]
        end
    elseif is_map(base) then
        local value = rawget(base, key)
        if value == nil then
            fail("the map has no key '" .. key .. "'")
        end
        return value
    elseif is_list(base) and (key == "length" or key == "size" or key == "count") then
        return #base
    end
    fail("'" .. str(base) .. "' has no '" .. key .. "'")
end

function G.set_field(base, key, value)
    if type(base) == "string" then
        return set_object_field(base, key, value)
    elseif is_vec(base) then
        base[key] = value
        return
    elseif is_map(base) then
        return G.put(base, key, value)
    end
    fail("'" .. str(base) .. "' has no '" .. key .. "' to change")
end

function G.move(name, dx, dy)
    local found = object(name)
    if is_vec(dx) then
        dx, dy = dx.x, dx.y
    end
    found.x, found.y = found.x + dx, found.y + dy
    if found.type == "line" then
        found.x2, found.y2 = found.x2 + dx, found.y2 + dy
    end
end
function G.place(name, x, y)
    local found = object(name)
    if found.type == "line" then
        found.x2, found.y2 = found.x2 + x - found.x, found.y2 + y - found.y
    end
    found.x, found.y = x, y
end
function G.resize(name, w, h)
    local found = object(name)
    if found.type == "ellipse" or found.type == "polygon" then
        found.w, found.h = w, h or w
    elseif found.type == "circle" then
        found.r = w
    elseif found.type == "text" then
        found.size = floor(w)
    else
        found.w, found.h = w, h or w
    end
end
function G.hide(name) object(name).hidden = true end
function G.show(name) object(name).hidden = false end
G["delete"] = function(name)
    name = str(name)
    local key = objects[name] and name or "button:" .. name
    if objects[key] then
        objects[key] = nil
        for index, entry in ipairs(order) do
            if entry == key then
                table.remove(order, index)
                break
            end
        end
    end
    if focused == name then
        focused = nil
    end
end
function G.exists(name)
    name = str(name)
    return objects[name] ~= nil or objects["button:" .. name] ~= nil
end

local function measure(text, size)
    if not window_open then
        return #chars(str(text)) * size * 0.5
    end
    return font(size):getWidth(str(text))
end
function G.textwidth(text, size)
    return G.round(measure(text, size or text_size))
end

local function shape(found)
    if found.type == "circle" then
        return {"circle", found.x, found.y, abs(found.r)}
    elseif found.type == "text" then
        return {"rect", found.x, found.y, measure(found.text, found.size), found.size * 0.72}
    elseif found.picture and found.w == nil then
        return {"rect", found.x, found.y, found.picture:getWidth(), found.picture:getHeight()}
    end
    return {"rect", found.x, found.y, found.w or 0, found.h or 0}
end
function G.touching(first, second)
    local a, b = object(first), object(second)
    if a.hidden or b.hidden then
        return false
    end
    a, b = shape(a), shape(b)
    if a[1] == "circle" and b[1] == "circle" then
        return (a[2] - b[2]) ^ 2 + (a[3] - b[3]) ^ 2 <= (a[4] + b[4]) ^ 2
    elseif a[1] == "rect" and b[1] == "rect" then
        return a[2] <= b[2] + b[4] and b[2] <= a[2] + a[4] and a[3] <= b[3] + b[5] and b[3] <= a[3] + a[5]
    end
    local c, r = a, b
    if a[1] ~= "circle" then
        c, r = b, a
    end
    local nx, ny = clamp(c[2], r[2], r[2] + r[4]), clamp(c[3], r[3], r[3] + r[5])
    return (c[2] - nx) ^ 2 + (c[3] - ny) ^ 2 <= c[4] ^ 2
end
function G.overlap(first, second)
    local function rect(value)
        if type(value) == "string" then
            local s = shape(object(value))
            if s[1] == "circle" then
                return {s[2] - s[4], s[3] - s[4], s[4] * 2, s[4] * 2}
            end
            return {s[2], s[3], s[4], s[5]}
        elseif is_map(value) then
            return {rawget(value, "x"), rawget(value, "y"), rawget(value, "w"), rawget(value, "h")}
        end
        return value
    end
    local a, b = rect(first), rect(second)
    return a[1] < b[1] + b[3] and b[1] < a[1] + a[3] and a[2] < b[2] + b[4] and b[2] < a[2] + a[4]
end

-- ----- drawing ---------------------------------------------------------------------------------------------------------------------
local function set(r, g, b)
    love.graphics.setColor(r / 255, g / 255, b / 255, draw_alpha)
end
local function tint(r, g, b)
    love.graphics.setColor(r, g, b, draw_alpha)
end

local function draw_object(name, found)
    local lg = love.graphics
    tint(rgb(found.color))
    local kind = found.type
    if kind == "box" then
        lg.rectangle("fill", found.x, found.y, found.w, found.h)
    elseif kind == "circle" then
        lg.circle("fill", found.x, found.y, abs(found.r))
    elseif kind == "ellipse" then
        lg.ellipse("fill", found.x + found.w / 2, found.y + found.h / 2, abs(found.w / 2), abs(found.h / 2))
    elseif kind == "polygon" then
        local sx, sy = found.w / found.pw, found.h / found.ph
        local points = {}
        for index = 1, #found.points, 2 do
            points[index] = found.x + found.points[index] * sx
            points[index + 1] = found.y + found.points[index + 1] * sy
        end
        local ok, triangles = pcall(love.math.triangulate, points)
        if ok then
            for _, triangle in ipairs(triangles) do lg.polygon("fill", triangle) end
        else
            lg.polygon("fill", points)
        end
    elseif kind == "line" then
        lg.setLineWidth(found.width)
        lg.line(found.x, found.y, found.x2, found.y2)
    elseif kind == "text" then
        lg.setFont(font(found.size))
        lg.print(found.text, found.x, found.y)
    elseif kind == "image" or kind == "sprite" then
        local image = found.picture
        local iw, ih = image:getWidth(), image:getHeight()
        local w, h = found.w or iw, found.h or ih
        lg.setColor(1, 1, 1, draw_alpha)
        lg.draw(image, found.x + w / 2, found.y + h / 2, math.rad(found.angle or 0), w / iw, h / ih, iw / 2, ih / 2)
    elseif kind == "button" then
        local over = mouse_x >= found.x and mouse_x <= found.x + found.w and mouse_y >= found.y and
            mouse_y <= found.y + found.h
        if over then set(148, 182, 108) else set(82, 105, 61) end
        lg.rectangle("fill", found.x, found.y, found.w, found.h, 6)
        set(240, 240, 240)
        local f = font(24)
        lg.setFont(f)
        lg.print(found.label, found.x + (found.w - f:getWidth(found.label)) / 2, found.y + (found.h - f:getHeight()) / 2)
    elseif kind == "textbox" then
        set(23, 23, 23)
        lg.rectangle("fill", found.x, found.y, found.w, found.h)
        if focused == name then set(148, 182, 108) else set(90, 90, 90) end
        lg.setLineWidth(2)
        lg.rectangle("line", found.x, found.y, found.w, found.h)
        local f = font(24)
        lg.setFont(f)
        if found.text ~= "" then
            tint(rgb(found.color))
            lg.print(found.text, found.x + 8, found.y + (found.h - f:getHeight()) / 2)
        elseif focused ~= name then
            set(120, 120, 120)
            lg.print(found.hint, found.x + 8, found.y + (found.h - f:getHeight()) / 2)
        end
        if focused == name and floor(now() * 2) % 2 == 0 then
            local before_cursor = concat(chars(found.text), "", 1, math.min(found.cursor, #chars(found.text)))
            set(148, 182, 108)
            lg.rectangle("fill", found.x + 8 + f:getWidth(before_cursor), found.y + 7, 2, found.h - 14)
        end
    elseif kind == "slider" then
        local share = found.max == found.min and 0 or (found.value - found.min) / (found.max - found.min)
        local middle = found.y + found.h / 2
        set(60, 60, 60)
        lg.rectangle("fill", found.x, middle - 3, found.w, 6)
        tint(rgb(found.color))
        lg.rectangle("fill", found.x, middle - 3, found.w * share, 6)
        lg.circle("fill", found.x + found.w * share, middle, 9)
        set(200, 200, 200)
        local f = font(20)
        lg.setFont(f)
        lg.print(str(found.value), found.x + found.w + 12, middle - f:getHeight() / 2)
    elseif kind == "checkbox" then
        set(23, 23, 23)
        lg.rectangle("fill", found.x, found.y, found.w, found.h)
        if found.checked then tint(rgb(found.color)) else set(110, 110, 110) end
        lg.setLineWidth(2)
        lg.rectangle("line", found.x, found.y, found.w, found.h)
        if found.checked then
            lg.setLineWidth(3)
            lg.line(found.x + 5, found.y + found.h / 2, found.x + 10, found.y + found.h - 6, found.x + found.w - 5,
                found.y + 6)
        end
        set(229, 229, 229)
        local f = font(24)
        lg.setFont(f)
        lg.print(found.label, found.x + found.w + 8, found.y + (found.h - f:getHeight()) / 2)
    end
end

local function draw_overlay()
    local lg = love.graphics
    local w, h = G.screen_width, G.screen_height
    lg.setColor(0, 0, 0, 0.6)
    lg.rectangle("fill", 0, 0, w, h)
    local box_w, box_h = math.min(w - 40, 520), overlay.kind == "ask" and 150 or 120
    local x, y = (w - box_w) / 2, (h - box_h) / 2
    set(30, 30, 30)
    lg.rectangle("fill", x, y, box_w, box_h, 8)
    set(148, 182, 108)
    lg.setLineWidth(2)
    lg.rectangle("line", x, y, box_w, box_h, 8)
    lg.setFont(font(24))
    set(235, 235, 235)
    lg.printf(overlay.text, x + 16, y + 16, box_w - 32)
    if overlay.kind == "ask" then
        set(18, 18, 18)
        lg.rectangle("fill", x + 16, y + box_h - 56, box_w - 32, 36)
        set(240, 240, 240)
        local caret = floor(now() * 2) % 2 == 0 and "|" or ""
        lg.print(overlay.answer .. caret, x + 24, y + box_h - 48)
    else
        set(150, 150, 150)
        lg.setFont(font(20))
        lg.print("press enter or click to go on", x + 16, y + box_h - 30)
    end
end

local function draw()
    if not window_open then
        return
    end
    local lg = love.graphics
    lg.clear(rgb(background))
    if ui_label then
        set(109, 137, 79)
        lg.rectangle("fill", 20, 20, 180, 38, 6)
        set(240, 240, 240)
        lg.setFont(font(20))
        lg.print(ui_label, 32, 30)
    end
    tick_effects()
    local shown = {}
    for index, name in ipairs(order) do
        local found = objects[name]
        if found and not found.hidden and (found.alpha == nil or found.alpha > 0) then
            shown[#shown + 1] = {name, found, index}
        end
    end
    table.sort(shown, function(a, b)
        local la, lb = a[2].layer or 0, b[2].layer or 0
        if la == lb then return a[3] < b[3] end
        return la < lb
    end)
    local ui_kinds = {button = true, textbox = true, slider = true, checkbox = true}
    for _, entry in ipairs(shown) do
        local name, found = entry[1], entry[2]
        draw_alpha = found.alpha or 1
        lg.push()
        if not ui_kinds[found.type] and not found.fixed then
            lg.translate(shake_x - scroll_x, shake_y - scroll_y)
        end
        draw_object(name, found)
        lg.pop()
    end
    draw_alpha = 1
    if #particles > 0 then
        lg.push()
        lg.translate(shake_x - scroll_x, shake_y - scroll_y)
        for _, p in ipairs(particles) do
            local fade = clamp(p[5] / p[6], 0, 1)
            local side = math.max(1, p[10] * (0.4 + 0.6 * fade))
            lg.setColor(p[7], p[8], p[9], fade)
            lg.rectangle("fill", p[1] - side / 2, p[2] - side / 2, side, side)
        end
        lg.pop()
    end
    if overlay then
        draw_overlay()
    end
    if shown_error then
        set(60, 16, 16)
        lg.rectangle("fill", 0, G.screen_height - 60, G.screen_width, 60)
        set(255, 200, 200)
        lg.setFont(font(22))
        lg.printf(shown_error, 12, G.screen_height - 50, G.screen_width - 24)
    end
end

-- ----- keys and the mouse ------------------------------------------------------------------------------------------------------
local function wanted(name)
    name = trim(name):lower()
    return KEY_ALIASES[name] or name
end
local function typing()
    return focused ~= nil and objects[focused] ~= nil and objects[focused].type == "textbox"
end
function G.keydown(name) return held[wanted(name)] == true and not typing() end
function G.keypressed(name)
    local key = wanted(name)
    local was = presses[key] == true
    presses[key] = nil
    return was
end
function G.mousex() return mouse_x end
function G.mousey() return mouse_y end
local MOUSE_BUTTONS = {left = 1, right = 2, middle = 3}
function G.mousedown(which) return mouse_held[MOUSE_BUTTONS[str(which or "left")]] == true end
function G.mousepressed(which)
    local number = MOUSE_BUTTONS[str(which or "left")]
    local was = clicks[number] == true
    if number then
        clicks[number] = nil
    end
    return was
end
function G.cursor(visible)
    if has_love and love.mouse then
        love.mouse.setVisible(G.truthy(visible))
    end
end

local function slide(found, x)
    local value = found.min + (found.max - found.min) * clamp((x - found.x) / math.max(1, found.w), 0, 1)
    found.value = found.whole and G.round(value) or G.round(value, 4)
end

local function edit_text(entry, key)
    local letters = chars(entry.text)
    local cursor = math.min(entry.cursor or #letters, #letters)
    if key == "backspace" and cursor > 0 then
        table.remove(letters, cursor)
        cursor = cursor - 1
    elseif key == "delete" and cursor < #letters then
        table.remove(letters, cursor + 1)
    elseif key == "left" then
        cursor = math.max(0, cursor - 1)
    elseif key == "right" then
        cursor = math.min(#letters, cursor + 1)
    elseif key == "home" then
        cursor = 0
    elseif key == "end" then
        cursor = #letters
    end
    entry.text, entry.cursor = concat(letters), cursor
end

local function on_key(key, repeated)
    if overlay then
        if overlay.kind == "ask" and key == "backspace" then
            local letters = chars(overlay.answer)
            letters[#letters] = nil
            overlay.answer = concat(letters)
        elseif key == "return" or key == "kpenter" or (overlay.kind == "popup" and key == "escape") then
            overlay.done = true
        end
        return
    end
    local box = focused and objects[focused]
    if box and box.type == "textbox" then
        if key == "return" or key == "kpenter" then
            box.submitted = true
        elseif key == "escape" then
            focused = nil
        else
            edit_text(box, key)
        end
        return
    end
    if repeated then
        return
    end
    local name = LOVE_KEYS[key] or key
    if not held[name] then
        presses[name] = true
    end
    held[name] = true
end

local function on_text(text)
    if overlay and overlay.kind == "ask" then
        overlay.answer = overlay.answer .. text
        return
    end
    local box = focused and objects[focused]
    if box and box.type == "textbox" then
        local letters = chars(box.text)
        local cursor = math.min(box.cursor or #letters, #letters)
        for _, letter in ipairs(chars(text)) do
            cursor = cursor + 1
            table.insert(letters, cursor, letter)
        end
        box.text, box.cursor = concat(letters), cursor
    end
end

local function on_press(x, y, button)
    mouse_x, mouse_y = x, y
    mouse_held[button], clicks[button] = true, true
    if overlay then
        if overlay.kind == "popup" then
            overlay.done = true
        end
        return
    end
    if button ~= 1 then
        return
    end
    if ui_label and x >= 20 and x <= 200 and y >= 20 and y <= 58 then
        G.ui = ui_label
    end
    local chosen = nil
    for _, name in ipairs(order) do
        local found = objects[name]
        local kind = found and not found.hidden and found.type
        if kind == "button" or kind == "textbox" or kind == "slider" or kind == "checkbox" then
            local width = found.w + (kind == "checkbox" and 8 + measure(found.label, 24) or 0)
            local grow = kind == "slider" and 6 or 0
            if x >= found.x and x <= found.x + width and y >= found.y - grow and y <= found.y + found.h + grow then
                if kind == "button" then
                    G.buttons[found.variable] = 1
                elseif kind == "textbox" then
                    chosen = name
                elseif kind == "checkbox" then
                    found.checked = not found.checked
                else
                    dragging = name
                    slide(found, x)
                end
            end
        end
    end
    focused = chosen
end

local function on_release(button)
    mouse_held[button] = nil
    dragging = nil
    for _, found in pairs(objects) do
        if found.type == "button" then
            G.buttons[found.variable] = 0
        end
    end
end

local function on_move(x, y)
    mouse_x, mouse_y = x, y
    if dragging and objects[dragging] then
        slide(objects[dragging], x)
    end
end

-- ----- waiting: the program runs in a coroutine that gives way to love2d every frame ------------------------------------------------
local program = nil
local wake = nil -- nil: next frame, a number: that time, a function: when it says true
local last_frame = now()

local function inside()
    return program ~= nil and coroutine.running() == program
end

local function pause(condition)
    if not inside() then
        return false
    end
    wake = condition
    coroutine.yield()
    return true
end

function G.frame()
    pause(nil)
end

function G.wait(seconds)
    local target = now() + seconds
    if not pause(target) then
        while now() < target do end
    end
end

function G.animate(name, x, y, seconds)
    local found = object(name)
    local sx, sy, begin = found.x, found.y, now()
    while true do
        local progress = seconds <= 0 and 1 or math.min(1, (now() - begin) / seconds)
        local eased = progress * progress * (3 - 2 * progress)
        G.place(name, sx + (x - sx) * eased, sy + (y - sy) * eased)
        if progress >= 1 or not pause(nil) then
            G.place(name, x, y)
            return
        end
    end
end

local function number_answer(text)
    local whole_part, fraction = text:match("^%-?(%d+)(%.?%d*)$")
    if not whole_part or (#whole_part > 1 and whole_part:sub(1, 1) == "0") or fraction == "." then
        return nil
    end
    return tonumber(text)
end

function G.ask(question)
    local answer
    if window_open and inside() then
        overlay = {kind = "ask", text = str(question), answer = "", done = false}
        local asking = overlay
        pause(function() return asking.done end)
        answer, overlay = asking.answer, nil
    else
        io.write(str(question), " ")
        answer = io.read("*l") or ""
    end
    return number_answer(trim(answer)) or answer
end

function G.popup(text)
    if window_open and inside() then
        overlay = {kind = "popup", text = str(text), done = false}
        local showing = overlay
        pause(function() return showing.done end)
        overlay = nil
    else
        print(str(text))
    end
end

-- ----- sound -------------------------------------------------------------------------------------------------------------------------
local sound_volume, song, playing = 1, nil, {}
local function source(path, kind)
    local ok, found = pcall(love.audio.newSource, str(path), kind)
    if not ok then
        fail("can't play '" .. str(path) .. "'")
    end
    return found
end
function G.sound(path)
    if not has_love then
        return
    end
    local effect = source(path, "static")
    effect:setVolume(sound_volume)
    effect:play()
    playing[#playing + 1] = effect
end
function G.music(path)
    if not has_love then
        return
    end
    if song then
        song:stop()
    end
    song = source(path, "stream")
    song:setLooping(true)
    song:setVolume(sound_volume)
    song:play()
end
function G.stopmusic()
    if song then
        song:stop()
    end
    song = nil
end
function G.stopsounds()
    for _, effect in ipairs(playing) do
        effect:stop()
    end
    playing = {}
end
function G.volume(value)
    sound_volume = clamp(value, 0, 1)
    if song then
        song:setVolume(sound_volume)
    end
end
local WAVES = {square = true, sine = true, triangle = true, saw = true, noise = true}
local beeps = {}
function G.beep(frequency, seconds, wave)
    seconds, wave = seconds or 0.15, str(wave or "square"):lower()
    if frequency < 20 or frequency > 20000 then
        fail("beep frequency must be from 20 to 20000 (440 is the a above middle c)")
    end
    if seconds <= 0 or seconds > 5 then fail("a beep can last from just above 0 up to 5 seconds") end
    if not WAVES[wave] then fail("'" .. wave .. "' is not a wave. try: square, sine, triangle, saw, noise") end
    if not has_love then return end
    local key = frequency .. ":" .. seconds .. ":" .. wave
    if not beeps[key] then
        local rate = 44100
        local count = math.max(1, floor(rate * seconds))
        local data = love.sound.newSoundData(count, rate, 16, 1)
        for index = 0, count - 1 do
            local phase = (index * frequency / rate) % 1
            local value
            if wave == "sine" then value = math.sin(2 * math.pi * phase)
            elseif wave == "square" then value = phase < 0.5 and 1 or -1
            elseif wave == "triangle" then value = 4 * abs(phase - 0.5) - 1
            elseif wave == "saw" then value = 2 * phase - 1
            else value = math.random() * 2 - 1 end
            local envelope = math.min(1, index / (rate * 0.003), (count - index) / (rate * 0.02))
            data:setSample(index, value * 0.22 * envelope)
        end
        beeps[key] = love.audio.newSource(data, "static")
    end
    local effect = beeps[key]:clone()
    effect:setVolume(sound_volume)
    effect:play()
    playing[#playing + 1] = effect
end

-- ----- starting ------------------------------------------------------------------------------------------------------------------------
local function wants_tests()
    for _, value in ipairs(rawget(_G, "arg") or {}) do
        if value == "--test" then
            return true
        end
    end
    return false
end

local function run_tests()
    -- G.tests is a list of {name, function} so the tests run in the order they were written
    local passed, failed = 0, 0
    for _, entry in ipairs(G.tests) do
        local name = entry[1]
        local ok, problem = pcall(entry[2])
        local label = name:gsub("^test_", ""):gsub("_", " ")
        if ok then
            passed = passed + 1
            print("pass: " .. label)
        else
            failed = failed + 1
            print("fail: " .. label .. ": " .. problem_text(problem))
        end
    end
    print(passed .. " passed, " .. failed .. " failed")
    return failed == 0
end

local function quit(code)
    if has_love and love.event then
        love.event.quit(code)
    else
        os.exit(code)
    end
end

function G.start(main, name)
    save_name = name or "program"
    if has_love and love.filesystem then
        pcall(love.filesystem.setIdentity, "gublan_" .. save_name:gsub("[^%w_-]+", "_"))
    end
    if wants_tests() then
        local good = run_tests()
        if has_love then
            love.load = function() quit(good and 0 or 1) end
            return
        end
        os.exit(good and 0 or 1)
    end
    local function finish(problem)
        local failed = problem ~= nil and problem ~= KILL
        if failed then
            local text = "error: " .. problem_text(problem)
            io.stderr:write(text, "\n")
            shown_error = text
        end
        if not window_open or problem == KILL then
            quit(failed and 1 or 0)
        end
    end
    if not has_love then
        local ok, problem = pcall(main)
        finish(not ok and problem or nil)
        return
    end
    program = coroutine.create(main)
    love.update = function()
        if program == nil or coroutine.status(program) == "dead" then
            return
        end
        local time = now()
        if type(wake) == "number" and time < wake then
            return
        elseif type(wake) == "function" and not wake() then
            return
        elseif wake == nil and time - last_frame < 1 / math.max(1, fps_limit) - 0.002 then
            return
        end
        G.dt = math.min(0.25, time - last_frame)
        last_frame, wake = time, nil
        local ok, problem = coroutine.resume(program)
        if not ok then
            finish(problem)
        elseif coroutine.status(program) == "dead" then
            finish(nil)
        end
    end
    love.draw = draw
    love.keypressed = function(key, _, repeated) on_key(key, repeated) end
    love.keyreleased = function(key) held[LOVE_KEYS[key] or key] = nil end
    love.textinput = on_text
    love.mousepressed = function(x, y, button) on_press(x, y, button) end
    love.mousereleased = function(_, _, button) on_release(button) end
    love.mousemoved = function(x, y) on_move(x, y) end
    love.focus = function(visible)
        if not visible then
            held = {}
        end
    end
end

-- names that lua keeps for itself end in _ in translated programs (type -> G.type_)
for _, name in ipairs({"type", "repeat", "load", "string", "print", "error", "select", "next", "unpack", "assert",
    "tostring", "tonumber", "pairs", "ipairs", "table", "math", "os", "io", "delete"}) do
    if G[name] ~= nil then
        G[name .. "_"] = G[name]
    end
end

return G
