"""convert python, javascript and lua programs into gublan.

the converter reads a program into a python syntax tree (python directly,
javascript and lua through the small parsers in this file) and then writes
gublan lines from that tree. game libraries are translated as well: pygame,
p5.js, the html canvas and love2d drawing calls become gublan shapes and
frames. anything without a gublan version is kept as a `// todo` comment, so
a large script always converts and nothing is silently lost.
"""

import ast
import copy
import io
import math
import os
import re
import sys
import threading
import tokenize as _pytokenize
from dataclasses import dataclass

from gublancore import EXPRESSION_FUNCTIONS, GUBLANCOMMANDS, analyze_source, is_color, parse_expression

LANGUAGES = ("python", "javascript", "lua")
EXTENSIONS = {
    ".py": "python", ".pyw": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript",
    ".lua": "lua",
}
GUBLAN_FUNCTIONS = set(EXPRESSION_FUNCTIONS) | {"length", "float", "number", "text"}
RESERVED_FIRST = set(GUBLANCOMMANDS) | {"elif"}
INDENT = "    "


class Unsupported(Exception):
    """raised when a piece of code has no gublan version; it becomes a todo comment."""


class ParseError(Unsupported):
    pass


class Todo(ast.stmt):
    _fields = ("text", "reason")


class Comment(ast.stmt):
    _fields = ("text",)


class Raw(ast.stmt):
    _fields = ("text",)


class ArrowFunction(ast.expr):
    _fields = ("params", "body")


@dataclass
class ConversionResult:
    text: str
    language: str
    library: str
    notes: list
    todos: int
    source_lines: int

    @property
    def output_lines(self):
        return self.text.count("\n") + 1


def _name(identifier):
    return ast.Name(id=identifier, ctx=ast.Load())


def _const(value):
    return ast.Constant(value=value)


def _call(name, *args):
    return ast.Call(func=_name(name), args=list(args), keywords=[])


def _func(name, params, body, defaults=()):
    return ast.FunctionDef(
        name=name,
        args=ast.arguments(
            posonlyargs=[], args=[ast.arg(arg=param) for param in params], vararg=None,
            kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=list(defaults),
        ),
        body=body or [], decorator_list=[], returns=None, type_comment=None, type_params=[],
    )


def _assign(target, value):
    if isinstance(target, str):
        target = ast.Name(id=target, ctx=ast.Store())
    return ast.Assign(targets=[target], value=value, type_comment=None)


def _expr_stmt(value):
    return ast.Expr(value=value)


def _is_const(node, *types):
    return isinstance(node, ast.Constant) and (not types or isinstance(node.value, types)) \
        and not isinstance(node.value, bool)


def _is_true(node):
    return (isinstance(node, ast.Constant) and node.value is True) or (
        isinstance(node, ast.Name) and node.id == "true"
    )


def _is_false(node):
    return (isinstance(node, ast.Constant) and node.value is False) or (
        isinstance(node, ast.Name) and node.id == "false"
    )


# --------------------------------------------------------------------------
# language detection
# --------------------------------------------------------------------------

def detect_language(source, filename=None):
    if filename:
        language = EXTENSIONS.get(os.path.splitext(filename)[1].lower())
        if language:
            return language
    scores = {"python": 0, "javascript": 0, "lua": 0}
    patterns = {
        "python": (r"^\s*def \w+\(.*\)\s*:", r"^\s*(?:import|from) \w+", r":\s*$", r"^\s*elif ", r"\bself\.",
                   r"^\s*print\(", r"\bTrue\b|\bFalse\b|\bNone\b", r"^\s*#"),
        "javascript": (r"\bfunction\b.*\{", r"=>", r"^\s*(?:let|const|var) ", r";\s*$", r"console\.log",
                       r"===|!==", r"\{\s*$", r"^\s*\}", r"//"),
        "lua": (r"^\s*local ", r"\bthen\s*$", r"^\s*end\s*$", r"~=", r"^\s*--", r"\bdo\s*$", r"\.\.",
                r"\bnil\b", r"^\s*function [\w.:]+\(.*\)\s*$"),
    }
    for language, rules in patterns.items():
        for rule in rules:
            scores[language] += len(re.findall(rule, source, re.MULTILINE))
    # lines that only one language can start with count extra, so short snippets are still recognised
    strong = {"python": r"^\s*def \w+\(.*\)\s*:", "javascript": r"^\s*(?:let|const) \w+\s*=",
              "lua": r"^\s*local (?:function )?\w+"}
    for language, rule in strong.items():
        scores[language] += 2 * len(re.findall(rule, source, re.MULTILINE))
    return max(scores, key=lambda name: (scores[name], name == "python"))


# --------------------------------------------------------------------------
# tokenizer for javascript and lua
# --------------------------------------------------------------------------

class Token:
    __slots__ = ("kind", "value", "line", "nl")

    def __init__(self, kind, value, line, nl):
        self.kind = kind
        self.value = value
        self.line = line
        self.nl = nl

    def __repr__(self):
        return f"Token({self.kind}, {self.value!r}, {self.line})"


_JS_OPS = sorted(
    "=== !== **= ... >>> <<= >>= => == != <= >= && || ?? ?. ++ -- += -= *= /= %= &= |= ^= ** << >> "
    "{ } ( ) [ ] ; , < > + - * / % & | ^ ! ~ ? : = . @ #".split(),
    key=len, reverse=True,
)
_LUA_OPS = sorted(
    "... .. == ~= <= >= << >> // :: { } ( ) [ ] ; , < > + - * / % ^ # = . : & | ~".split(),
    key=len, reverse=True,
)
_NUM_RE = re.compile(r"0[xX][0-9a-fA-F_]+|(?:\d[\d_]*\.?[\d_]*|\.\d[\d_]*)(?:[eE][+-]?\d+)?n?")
_JS_ID_RE = re.compile(r"[A-Za-z_$][\w$]*")
_LUA_ID_RE = re.compile(r"[A-Za-z_]\w*")
_LONG_BRACKET = re.compile(r"\[(=*)\[")
_LONG_COMMENT = re.compile(r"--\[(=*)\[")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "b": "\b", "f": "\f", "v": "\v", "a": "\a"}


def _number(text):
    text = text.replace("_", "").rstrip("n")
    if text[:2].lower() == "0x":
        return int(text, 16)
    if any(char in text for char in ".eE"):
        value = float(text)
        return int(value) if value.is_integer() and "." not in text and "e" not in text.lower() else value
    return int(text)


def _read_string(source, index, quote):
    out = []
    i = index + 1
    length = len(source)
    lines = 0
    while i < length:
        char = source[i]
        if char == "\\" and i + 1 < length:
            escape = source[i + 1]
            if escape in _ESCAPES:
                out.append(_ESCAPES[escape])
                i += 2
            elif escape == "x" and re.fullmatch(r"[0-9a-fA-F]{2}", source[i + 2:i + 4]):
                out.append(chr(int(source[i + 2:i + 4], 16)))
                i += 4
            elif escape == "u":
                match = re.match(r"u\{([0-9a-fA-F]+)\}|u([0-9a-fA-F]{4})", source[i + 1:])
                if match:
                    out.append(chr(int(match.group(1) or match.group(2), 16)))
                    i += 1 + match.end()
                else:
                    out.append(escape)
                    i += 2
            elif escape == "\n":
                lines += 1
                i += 2
            else:
                out.append(escape)
                i += 2
            continue
        if char == quote:
            return "".join(out), i + 1, lines
        if char == "\n":
            if quote == "`":
                lines += 1
            else:
                return "".join(out), i, lines
        out.append(char)
        i += 1
    return "".join(out), i, lines


def _read_template(source, index):
    parts = []
    text = []
    i = index + 1
    length = len(source)
    lines = 0
    while i < length:
        char = source[i]
        if char == "\\" and i + 1 < length:
            value, _, _ = _read_string(source[i:i + 2] + '"', -1, '"')
            text.append(_ESCAPES.get(source[i + 1], source[i + 1]))
            i += 2
            continue
        if char == "`":
            if text:
                parts.append(("text", "".join(text)))
            return parts, i + 1, lines
        if char == "$" and source.startswith("${", i):
            if text:
                parts.append(("text", "".join(text)))
                text = []
            depth, j, quote = 0, i + 1, None
            while j < length:
                current = source[j]
                if quote:
                    if current == "\\":
                        j += 2
                        continue
                    if current == quote:
                        quote = None
                elif current in "\"'`":
                    quote = current
                elif current == "{":
                    depth += 1
                elif current == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            inner = source[i + 2:j]
            lines += inner.count("\n")
            parts.append(("expr", inner))
            i = j + 1
            continue
        if char == "\n":
            lines += 1
        text.append(char)
        i += 1
    if text:
        parts.append(("text", "".join(text)))
    return parts, i, lines


def tokenize(source, language):
    ops = _JS_OPS if language == "javascript" else _LUA_OPS
    id_re = _JS_ID_RE if language == "javascript" else _LUA_ID_RE
    tokens = []
    i, length, line, newline = 0, len(source), 1, True
    while i < length:
        char = source[i]
        if char == "\n":
            line += 1
            newline = True
            i += 1
            continue
        if char in " \t\r\f\v﻿":
            i += 1
            continue
        if language == "javascript":
            if source.startswith("//", i) or (i == 0 and source.startswith("#!")):
                end = source.find("\n", i)
                i = length if end < 0 else end
                continue
            if source.startswith("/*", i):
                end = source.find("*/", i + 2)
                end = length if end < 0 else end + 2
                count = source.count("\n", i, end)
                line += count
                newline = newline or count > 0
                i = end
                continue
        else:
            if source.startswith("--", i):
                match = _LONG_COMMENT.match(source, i)
                if match:
                    close = "]" + match.group(1) + "]"
                    end = source.find(close, match.end())
                    end = length if end < 0 else end + len(close)
                else:
                    end = source.find("\n", i)
                    end = length if end < 0 else end
                count = source.count("\n", i, end)
                line += count
                newline = newline or count > 0
                i = end
                continue
            match = _LONG_BRACKET.match(source, i)
            if match:
                close = "]" + match.group(1) + "]"
                end = source.find(close, match.end())
                stop = length if end < 0 else end
                text = source[match.end():stop]
                if text.startswith("\n"):
                    text = text[1:]
                tokens.append(Token("string", text, line, newline))
                newline = False
                line += source.count("\n", i, stop)
                i = length if end < 0 else end + len(close)
                continue
        start_line = line
        if char in "\"'":
            value, i, extra = _read_string(source, i, char)
            tokens.append(Token("string", value, start_line, newline))
            line += extra
            newline = False
            continue
        if char == "`" and language == "javascript":
            parts, i, extra = _read_template(source, i)
            tokens.append(Token("template", parts, start_line, newline))
            line += extra
            newline = False
            continue
        if char.isdigit() or (char == "." and i + 1 < length and source[i + 1].isdigit()):
            match = _NUM_RE.match(source, i)
            text = match.group(0)
            if language == "lua" and text.endswith(".") and source.startswith("..", i + len(text) - 1):
                text = text[:-1]
            i += len(text)
            try:
                tokens.append(Token("number", _number(text), start_line, newline))
            except ValueError:
                tokens.append(Token("number", 0, start_line, newline))
            newline = False
            continue
        match = id_re.match(source, i)
        if match:
            tokens.append(Token("name", match.group(0), start_line, newline))
            newline = False
            i = match.end()
            continue
        for op in ops:
            if source.startswith(op, i):
                tokens.append(Token("op", op, start_line, newline))
                i += len(op)
                break
        else:
            tokens.append(Token("op", char, start_line, newline))
            i += 1
        newline = False
    tokens.append(Token("eof", None, line, True))
    return tokens


# --------------------------------------------------------------------------
# shared parser helpers
# --------------------------------------------------------------------------

class _Parser:
    language = ""

    def __init__(self, source):
        self.source = source
        self.lines = source.split("\n")
        self.tokens = tokenize(source, self.language)
        self.pos = 0

    def peek(self, offset=0):
        return self.tokens[min(self.pos + offset, len(self.tokens) - 1)]

    def next(self):
        token = self.tokens[self.pos]
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return token

    def at(self, *values):
        token = self.tokens[self.pos]
        return token.kind in ("op", "name") and token.value in values

    def accept(self, value):
        if self.at(value):
            self.next()
            return True
        return False

    def describe(self, token):
        if token.kind == "eof":
            return "the end of the file"
        if token.kind == "template":
            return "a template string"
        return f"'{token.value}'"

    def expect(self, value):
        if not self.at(value):
            raise ParseError(f"expected '{value}' but found {self.describe(self.peek())}")
        return self.next()

    def name(self):
        token = self.next()
        if token.kind != "name":
            raise ParseError(f"expected a name but found {self.describe(token)}")
        return token.value

    def text_between(self, first, last):
        return "\n".join(self.lines[first - 1:last])

    def statement_safe(self):
        start = self.pos
        first = self.peek()
        try:
            result = self.statement()
        except Unsupported as err:
            self.pos = start
            self.skip_statement()
            if self.pos == start:
                self.next()
            if self.peek().kind == "eof" and self.tokens[max(start, self.pos - 1)].line > first.line:
                # the brackets never balance: only give up on the line that broke
                self.pos = start
                while self.peek().kind != "eof" and self.peek().line == first.line:
                    self.next()
            last = self.tokens[max(start, self.pos - 1)].line
            todo = Todo(text=self.text_between(first.line, max(first.line, last)), reason=str(err))
            todo.lineno, todo.end_lineno = first.line, max(first.line, last)
            return [todo]
        last = self.tokens[max(start, self.pos - 1)].line
        for node in result:
            if getattr(node, "lineno", None) is None:
                node.lineno = first.line
                node.end_lineno = max(first.line, last)
        return result


def _fold_concat(left, right):
    """lua and js '..'/'+' concatenation: make sure numbers are joined as text."""
    textual = (ast.JoinedStr,)
    if any(isinstance(side, textual) or _is_const(side, str) for side in (left, right)):
        node = ast.BinOp(left=left, op=ast.Add(), right=right)
    else:
        node = ast.BinOp(left=_call("str", left), op=ast.Add(), right=right)
    node._concat = True
    return node


# --------------------------------------------------------------------------
# javascript parser -> python ast
# --------------------------------------------------------------------------

_JS_BINARY = {
    "||": (1, "or"), "??": (1, "or"), "&&": (2, "and"),
    "|": (3, ast.BitOr), "^": (4, ast.BitXor), "&": (5, ast.BitAnd),
    "==": (6, ast.Eq), "!=": (6, ast.NotEq), "===": (6, ast.Eq), "!==": (6, ast.NotEq),
    "<": (7, ast.Lt), ">": (7, ast.Gt), "<=": (7, ast.LtE), ">=": (7, ast.GtE),
    "instanceof": (7, None), "in": (7, ast.In),
    "<<": (8, ast.LShift), ">>": (8, ast.RShift), ">>>": (8, None),
    "+": (9, ast.Add), "-": (9, ast.Sub), "*": (10, ast.Mult), "/": (10, ast.Div), "%": (10, ast.Mod),
    "**": (11, ast.Pow),
}
_JS_ASSIGN = {"=": None, "+=": ast.Add, "-=": ast.Sub, "*=": ast.Mult, "/=": ast.Div, "%=": ast.Mod,
              "**=": ast.Pow}


def _combine(op_kind, left, right):
    if op_kind == "or" or op_kind == "and":
        op = ast.Or() if op_kind == "or" else ast.And()
        if isinstance(left, ast.BoolOp) and type(left.op) is type(op):
            left.values.append(right)
            return left
        return ast.BoolOp(op=op, values=[left, right])
    if op_kind in (ast.Eq, ast.NotEq, ast.Lt, ast.Gt, ast.LtE, ast.GtE, ast.In):
        return ast.Compare(left=left, ops=[op_kind()], comparators=[right])
    return ast.BinOp(left=left, op=op_kind(), right=right)


class JSParser(_Parser):
    language = "javascript"

    def parse_program(self):
        body = []
        while self.peek().kind != "eof":
            if self.at("}", ")", "]"):
                self.next()
                continue
            body.extend(self.statement_safe())
        return body

    def _prev_continues(self):
        if self.pos == 0:
            return False
        previous = self.tokens[self.pos - 1]
        return previous.kind == "op" and previous.value not in (")", "]", "}", "++", "--", ";")

    def skip_statement(self):
        depth = 0
        consumed = 0
        while True:
            token = self.peek()
            if token.kind == "eof":
                return
            if consumed and depth == 0 and token.nl and not self._prev_continues() and not (
                token.kind == "op" and token.value in (".", "?.", "&&", "||", "?", ":", ",")
            ) and not (token.kind == "name" and token.value in ("else", "catch", "finally")):
                return
            if token.kind == "op":
                if token.value in ("(", "[", "{"):
                    depth += 1
                elif token.value in (")", "]", "}"):
                    if depth == 0:
                        if not consumed:
                            self.next()
                        return
                    depth -= 1
                elif token.value == ";" and depth == 0:
                    self.next()
                    return
            self.next()
            consumed += 1

    def block_or_statement(self):
        if self.at("{"):
            return self.block()
        return self.statement_safe()

    def block(self):
        self.expect("{")
        body = []
        while not self.at("}"):
            if self.peek().kind == "eof":
                raise ParseError("a block is missing its closing }")
            body.extend(self.statement_safe())
        self.expect("}")
        return body

    def end_statement(self):
        if self.accept(";"):
            return
        token = self.peek()
        if token.kind == "eof" or token.nl or self.at("}"):
            return
        raise ParseError(f"unexpected {self.describe(token)}")

    def statement(self):
        token = self.peek()
        word = token.value if token.kind == "name" else None
        if self.at(";"):
            self.next()
            return []
        if self.at("{"):
            return self.block()
        if word in ("let", "const", "var"):
            self.next()
            out = self.declarations()
            self.end_statement()
            return out
        if word == "async" and self.peek(1).value == "function":
            self.next()
            word = "function"
        if word == "function":
            return [self.function_declaration()]
        if word == "class":
            return [self.class_declaration()]
        if word == "if":
            self.next()
            self.expect("(")
            test = self.expression()
            self.expect(")")
            body = self.block_or_statement()
            orelse = []
            if self.accept("else"):
                orelse = self.block_or_statement()
            return [ast.If(test=test, body=body, orelse=orelse)]
        if word == "for":
            return self.for_statement()
        if word == "while":
            self.next()
            self.expect("(")
            test = self.expression()
            self.expect(")")
            return [ast.While(test=test, body=self.block_or_statement(), orelse=[])]
        if word == "do":
            self.next()
            body = self.block_or_statement()
            self.expect("while")
            self.expect("(")
            test = self.expression()
            self.expect(")")
            self.end_statement()
            stop = ast.If(test=ast.UnaryOp(op=ast.Not(), operand=test), body=[ast.Break()], orelse=[])
            return [ast.While(test=_const(True), body=body + [stop], orelse=[])]
        if word == "return":
            self.next()
            value = None
            if not (self.at(";", "}") or self.peek().nl or self.peek().kind == "eof"):
                value = self.expression()
            self.end_statement()
            return [ast.Return(value=value)]
        if word in ("break", "continue"):
            self.next()
            if self.peek().kind == "name" and not self.peek().nl:
                raise Unsupported("loop labels have no gublan version")
            self.end_statement()
            return [ast.Break() if word == "break" else ast.Continue()]
        if word == "switch":
            return self.switch_statement()
        if word == "try":
            return self.try_statement()
        if word == "throw":
            raise Unsupported("throw has no gublan version; use print and kill")
        if word == "import" and self.peek(1).value != "(":
            self.skip_statement()
            return []
        if word == "export":
            self.next()
            self.accept("default")
            return self.statement()
        if token.kind == "name" and self.peek(1).value == ":" and not self.peek(1).nl:
            raise Unsupported("labels have no gublan version")
        statement = self.simple_statement()
        self.end_statement()
        return [statement]

    def declarations(self):
        out = []
        while True:
            if self.at("{", "["):
                raise Unsupported("destructuring has no gublan version; assign each value on its own line")
            name = self.name()
            value = self.expression() if self.accept("=") else _const(None)
            declaration = _assign(name, value)
            declaration._declared = True
            out.append(declaration)
            if not self.accept(","):
                return out

    def parameters(self):
        self.expect("(")
        names, defaults = [], []
        while not self.at(")"):
            if self.accept("..."):
                raise Unsupported("rest parameters have no gublan version")
            if self.at("{", "["):
                raise Unsupported("destructured parameters have no gublan version")
            names.append(self.name())
            if self.accept("="):
                defaults.append(self.ternary())
            elif defaults:
                defaults.append(_const(None))
            if not self.accept(","):
                break
        self.expect(")")
        return names, defaults

    def function_declaration(self):
        self.expect("function")
        self.accept("*")
        name = self.name()
        params, defaults = self.parameters()
        return _func(name, params, self.block(), defaults)

    def class_declaration(self):
        self.expect("class")
        name = self.name()
        bases = []
        if self.accept("extends"):
            bases.append(self.postfix(self.primary()))
        self.expect("{")
        body = []
        fields = []
        while not self.at("}"):
            if self.peek().kind == "eof":
                raise ParseError("a class is missing its closing }")
            if self.accept(";"):
                continue
            start = self.pos
            first_line = self.peek().line
            try:
                if self.at("static") and self.peek(1).value not in ("(", "="):
                    self.next()
                if self.at("get", "set", "async") and self.peek(1).kind == "name":
                    raise Unsupported("getters, setters and async methods have no gublan version")
                member = self.name()
                if self.at("("):
                    params, defaults = self.parameters()
                    method_body = self.block()
                    if member == "constructor":
                        member = "__init__"
                    method = _func(member, ["self"] + params, method_body, defaults)
                    method.lineno = first_line
                    body.append(method)
                else:
                    value = self.expression() if self.accept("=") else _const(None)
                    self.end_statement()
                    fields.append(_assign(ast.Attribute(value=_name("self"), attr=member, ctx=ast.Store()), value))
            except Unsupported as err:
                self.pos = start
                self._skip_member()
                body.append(Todo(text=self.text_between(first_line, self.tokens[self.pos - 1].line), reason=str(err)))
        self.expect("}")
        if fields:
            init = next((item for item in body if isinstance(item, ast.FunctionDef) and item.name == "__init__"), None)
            if init is None:
                init = _func("__init__", ["self"], [])
                body.insert(0, init)
            init.body[0:0] = fields
        return ast.ClassDef(name=name, bases=bases, keywords=[], body=body, decorator_list=[], type_params=[])

    def _skip_member(self):
        depth = 0
        while self.peek().kind != "eof":
            token = self.next()
            if token.value in ("{", "(", "["):
                depth += 1
            elif token.value in ("}", ")", "]"):
                depth -= 1
                if depth == 0 and token.value == "}":
                    return
                if depth < 0:
                    self.pos -= 1
                    return
            elif token.value == ";" and depth == 0:
                return

    def for_statement(self):
        self.expect("for")
        if self.at("await"):
            raise Unsupported("for await has no gublan version")
        self.expect("(")
        save = self.pos
        if self.at("let", "const", "var"):
            self.next()
        if self.peek().kind == "name" and self.peek(1).value in ("of", "in"):
            target = self.name()
            kind = self.next().value
            iterable = self.expression()
            self.expect(")")
            body = self.block_or_statement()
            if kind == "in":
                iterable = _call("__keys", iterable)
            return [ast.For(target=ast.Name(id=target, ctx=ast.Store()), iter=iterable, body=body, orelse=[])]
        self.pos = save
        init = []
        if not self.at(";"):
            if self.at("let", "const", "var"):
                self.next()
                init = self.declarations()
            else:
                init = [self.simple_statement()]
        self.expect(";")
        test = _const(True) if self.at(";") else self.expression()
        self.expect(";")
        update = []
        while not self.at(")"):
            update.append(self.simple_statement())
            if not self.accept(","):
                break
        self.expect(")")
        body = self.block_or_statement()
        counted = self._counting_loop(init, test, update, body)
        if counted:
            return [counted]
        for node in body:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Continue):
                    raise Unsupported("this for loop uses continue with a custom update step")
        return init + [ast.While(test=test, body=body + update, orelse=[])]

    @staticmethod
    def _counting_loop(init, test, update, body):
        if len(init) != 1 or len(update) != 1 or not isinstance(init[0], ast.Assign):
            return None
        target = init[0].targets[0]
        if not isinstance(target, ast.Name):
            return None
        name = target.id
        step_node = update[0]
        if not (isinstance(step_node, ast.AugAssign) and isinstance(step_node.target, ast.Name)
                and step_node.target.id == name and _is_const(step_node.value, int)):
            return None
        step = step_node.value.value if isinstance(step_node.op, ast.Add) else (
            -step_node.value.value if isinstance(step_node.op, ast.Sub) else None)
        if not step:
            return None
        if not (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.left, ast.Name)
                and test.left.id == name):
            return None
        for node in body:
            for inner in ast.walk(node):
                if isinstance(inner, (ast.Assign, ast.AugAssign)):
                    targets = inner.targets if isinstance(inner, ast.Assign) else [inner.target]
                    if any(isinstance(item, ast.Name) and item.id == name for item in targets):
                        return None
        bound = test.comparators[0]
        op = test.ops[0]
        if isinstance(op, ast.Lt) and step > 0:
            end = _minus(bound, 1)
        elif isinstance(op, ast.LtE) and step > 0:
            end = bound
        elif isinstance(op, ast.Gt) and step < 0:
            end = _minus(bound, -1)
        elif isinstance(op, ast.GtE) and step < 0:
            end = bound
        else:
            return None
        return ast.For(
            target=ast.Name(id=name, ctx=ast.Store()),
            iter=_call("__inclusive_range", init[0].value, end, _const(step)), body=body, orelse=[],
        )

    def switch_statement(self):
        self.expect("switch")
        self.expect("(")
        subject = self.expression()
        self.expect(")")
        self.expect("{")
        cases = []
        while not self.at("}"):
            if self.peek().kind == "eof":
                raise ParseError("a switch is missing its closing }")
            if self.accept("case"):
                test = self.expression()
                self.expect(":")
                if cases and not cases[-1][1] and cases[-1][0] is not None:
                    cases[-1][0].append(test)
                else:
                    cases.append(([test], []))
            elif self.accept("default"):
                self.expect(":")
                cases.append((None, []))
            else:
                if not cases:
                    raise ParseError("switch statements must start with case")
                cases[-1][1].extend(self.statement_safe())
        self.expect("}")
        chain = []
        default = None
        for tests, body in cases:
            if body and isinstance(body[-1], ast.Break):
                body = body[:-1]
            if tests is None:
                default = body
                continue
            conditions = [ast.Compare(left=copy.deepcopy(subject), ops=[ast.Eq()], comparators=[test]) for test in tests]
            condition = conditions[0] if len(conditions) == 1 else ast.BoolOp(op=ast.Or(), values=conditions)
            chain.append((condition, body))
        if not chain:
            return default or []
        root = ast.If(test=chain[0][0], body=chain[0][1], orelse=[])
        node = root
        for condition, body in chain[1:]:
            branch = ast.If(test=condition, body=body, orelse=[])
            node.orelse = [branch]
            node = branch
        if default:
            node.orelse = default
        return [root]

    def try_statement(self):
        self.expect("try")
        body = self.block()
        out = [Comment(text="try: errors stop the program in gublan")] + body
        if self.accept("catch"):
            if self.accept("("):
                while not self.at(")"):
                    self.next()
                self.expect(")")
            handler = self.block()
            if handler:
                out.append(Comment(text="the catch block was removed (it only ran after an error)"))
        if self.accept("finally"):
            out.extend(self.block())
        return out

    def simple_statement(self):
        if self.at("++", "--"):
            op = ast.Add() if self.next().value == "++" else ast.Sub()
            return ast.AugAssign(target=self.unary(), op=op, value=_const(1))
        expression = self.expression()
        token = self.peek()
        if token.kind == "op" and token.value in _JS_ASSIGN:
            self.next()
            targets = [expression]
            value = self.expression()
            while self.at("=") and token.value == "=":
                self.next()
                targets.append(value)
                value = self.expression()
            for target in targets:
                if not isinstance(target, (ast.Name, ast.Attribute, ast.Subscript)):
                    raise Unsupported("this assignment target has no gublan version")
            if token.value == "=":
                return ast.Assign(targets=targets, value=value, type_comment=None)
            return ast.AugAssign(target=expression, op=_JS_ASSIGN[token.value](), value=value)
        if token.kind == "op" and token.value in ("??=", "||=", "&&=", "<<=", ">>=", "&=", "|=", "^="):
            raise Unsupported(f"'{token.value}' has no gublan version")
        if self.at("++", "--") and not self.peek().nl:
            op = ast.Add() if self.next().value == "++" else ast.Sub()
            return ast.AugAssign(target=expression, op=op, value=_const(1))
        if self.at(","):
            raise Unsupported("comma expressions have no gublan version")
        return _expr_stmt(expression)

    # expressions -------------------------------------------------------
    def expression(self):
        return self.ternary()

    def ternary(self):
        test = self.binary(1)
        if self.accept("?"):
            body = self.ternary()
            self.expect(":")
            orelse = self.ternary()
            return ast.IfExp(test=test, body=body, orelse=orelse)
        return test

    def binary(self, minimum):
        left = self.unary()
        while True:
            token = self.peek()
            if token.kind not in ("op", "name"):
                return left
            info = _JS_BINARY.get(token.value)
            if info is None or info[0] < minimum:
                return left
            precedence, kind = info
            if kind is None:
                raise Unsupported(f"the '{token.value}' operator has no gublan version")
            self.next()
            right = self.binary(precedence if token.value == "**" else precedence + 1)
            if token.value == "+" and (isinstance(left, ast.JoinedStr) or isinstance(right, ast.JoinedStr)):
                left = _fold_concat(left, right)
            else:
                left = _combine(kind, left, right)

    def unary(self):
        token = self.peek()
        if token.kind == "op":
            if token.value == "!":
                self.next()
                return ast.UnaryOp(op=ast.Not(), operand=self.unary())
            if token.value in ("-", "+"):
                self.next()
                operand = self.unary()
                if token.value == "+":
                    return _call("num", operand)
                if _is_const(operand, int, float):
                    return _const(-operand.value)
                return ast.UnaryOp(op=ast.USub(), operand=operand)
            if token.value in ("++", "--"):
                raise Unsupported("++ and -- inside expressions have no gublan version")
            if token.value == "~":
                self.next()
                return ast.UnaryOp(op=ast.Invert(), operand=self.unary())
        if token.kind == "name":
            if token.value in ("typeof", "void", "delete"):
                raise Unsupported(f"'{token.value}' has no gublan version")
            if token.value == "await":
                self.next()
                return self.unary()
            if token.value == "new":
                self.next()
                callee = self.primary()
                while self.at("."):
                    self.next()
                    callee = ast.Attribute(value=callee, attr=self.name(), ctx=ast.Load())
                args = self.arguments() if self.at("(") else []
                return self.postfix(ast.Call(func=callee, args=args, keywords=[]))
        return self.postfix(self.primary())

    def postfix(self, expression):
        while True:
            if self.at(".", "?."):
                self.next()
                token = self.next()
                if token.kind != "name":
                    raise ParseError(f"expected a property name after '.' but found {self.describe(token)}")
                expression = ast.Attribute(value=expression, attr=token.value, ctx=ast.Load())
            elif self.at("(") and not self.peek().nl:
                expression = ast.Call(func=expression, args=self.arguments(), keywords=[])
            elif self.at("["):
                self.next()
                index = self.expression()
                self.expect("]")
                expression = ast.Subscript(value=expression, slice=index, ctx=ast.Load())
            elif self.peek().kind == "template" and not self.peek().nl:
                raise Unsupported("tagged templates have no gublan version")
            else:
                return expression

    def arguments(self):
        self.expect("(")
        args = []
        while not self.at(")"):
            if self.accept("..."):
                raise Unsupported("spread arguments have no gublan version")
            args.append(self.expression())
            if not self.accept(","):
                break
        self.expect(")")
        return args

    def _arrow_ahead(self):
        depth, index = 1, self.pos
        while index < len(self.tokens):
            token = self.tokens[index]
            if token.kind == "op":
                if token.value in ("(", "[", "{"):
                    depth += 1
                elif token.value in (")", "]", "}"):
                    depth -= 1
                    if depth == 0:
                        following = self.tokens[min(index + 1, len(self.tokens) - 1)]
                        return following.kind == "op" and following.value == "=>"
            elif token.kind == "eof":
                return False
            index += 1
        return False

    def arrow_body(self):
        if self.at("{"):
            return self.block()
        return [ast.Return(value=self.ternary())]

    def template(self, parts):
        values = []
        for kind, text in parts:
            if kind == "text":
                values.append(_const(text))
            else:
                inner = JSParser(text)
                node = inner.expression()
                if inner.peek().kind != "eof":
                    raise ParseError("this template expression could not be read")
                values.append(ast.FormattedValue(value=node, conversion=-1, format_spec=None))
        return ast.JoinedStr(values=values)

    def primary(self):
        token = self.next()
        if token.kind == "number":
            return _const(token.value)
        if token.kind == "string":
            return _const(token.value)
        if token.kind == "template":
            return self.template(token.value)
        if token.kind == "name":
            word = token.value
            if word == "true":
                return _const(True)
            if word == "false":
                return _const(False)
            if word in ("null", "undefined"):
                return _const(None)
            if word == "this":
                return _name("self")
            if word in ("NaN", "Infinity", "super", "arguments", "yield"):
                raise Unsupported(f"'{word}' has no gublan version")
            if word == "async" and (self.at("(") or self.peek().kind == "name"):
                return self.primary()
            if word == "function":
                if self.peek().kind == "name":
                    self.next()
                params, _ = self.parameters()
                return ArrowFunction(params=params, body=self.block())
            if self.at("=>"):
                self.next()
                return ArrowFunction(params=[word], body=self.arrow_body())
            return _name(word)
        if token.value == "(":
            if self._arrow_ahead():
                self.pos -= 1
                params, _ = self.parameters()
                self.expect("=>")
                return ArrowFunction(params=params, body=self.arrow_body())
            inner = self.expression()
            if self.at(","):
                raise Unsupported("comma expressions have no gublan version")
            self.expect(")")
            return inner
        if token.value == "[":
            items = []
            while not self.at("]"):
                if self.accept("..."):
                    raise Unsupported("spread in lists has no gublan version")
                if self.at(","):
                    raise Unsupported("lists with holes have no gublan version")
                items.append(self.expression())
                if not self.accept(","):
                    break
            self.expect("]")
            return ast.List(elts=items, ctx=ast.Load())
        if token.value == "{":
            keys, values = [], []
            while not self.at("}"):
                if self.accept("..."):
                    raise Unsupported("spread in objects has no gublan version")
                key_token = self.next()
                if key_token.kind in ("name", "string", "number"):
                    key = str(key_token.value)
                elif key_token.value == "[":
                    raise Unsupported("computed object keys have no gublan version")
                else:
                    raise ParseError(f"unexpected {self.describe(key_token)} in an object")
                if self.at("("):
                    raise Unsupported("methods inside objects have no gublan version; use a class or a function")
                value = self.expression() if self.accept(":") else _name(key)
                keys.append(_const(key))
                values.append(value)
                if not self.accept(","):
                    break
            self.expect("}")
            return ast.Dict(keys=keys, values=values)
        raise ParseError(f"unexpected {self.describe(token)}")


# --------------------------------------------------------------------------
# lua parser -> python ast
# --------------------------------------------------------------------------

_LUA_BINARY = {
    "or": (1, "or"), "and": (2, "and"),
    "<": (3, ast.Lt), ">": (3, ast.Gt), "<=": (3, ast.LtE), ">=": (3, ast.GtE), "~=": (3, ast.NotEq),
    "==": (3, ast.Eq),
    "|": (4, ast.BitOr), "~": (5, ast.BitXor), "&": (6, ast.BitAnd), "<<": (7, ast.LShift), ">>": (7, ast.RShift),
    "..": (8, "concat"),
    "+": (9, ast.Add), "-": (9, ast.Sub),
    "*": (10, ast.Mult), "/": (10, ast.Div), "//": (10, ast.FloorDiv), "%": (10, ast.Mod),
    "^": (12, ast.Pow),
}
_LUA_UNARY = 11  # not, #, - and ~ bind tighter than * but looser than ^
_LUA_BLOCK_END = ("end", "else", "elseif", "until")


class LuaParser(_Parser):
    language = "lua"

    def parse_program(self):
        body = []
        while self.peek().kind != "eof":
            if self.at(*_LUA_BLOCK_END):
                self.next()
                continue
            body.extend(self.statement_safe())
        return body

    def skip_statement(self):
        depth = 0
        paren = 0
        consumed = 0
        while True:
            token = self.peek()
            if token.kind == "eof":
                return
            continuing = self.pos > 0 and (
                (self.tokens[self.pos - 1].kind == "op" and self.tokens[self.pos - 1].value not in (")", "]", "}"))
                or (self.tokens[self.pos - 1].kind == "name"
                    and self.tokens[self.pos - 1].value in ("and", "or", "not", "local", "return", "in"))
            )
            if consumed and depth == 0 and paren == 0 and token.nl and not continuing:
                return
            if token.kind == "name":
                if token.value in ("function", "if", "do", "repeat"):
                    depth += 1
                elif token.value in ("end", "until"):
                    if depth == 0:
                        if not consumed:
                            self.next()
                        return
                    depth -= 1
                elif token.value in ("else", "elseif") and depth == 0:
                    if not consumed:
                        self.next()
                    return
            elif token.kind == "op":
                if token.value in ("(", "[", "{"):
                    paren += 1
                elif token.value in (")", "]", "}"):
                    paren = max(0, paren - 1)
            self.next()
            consumed += 1

    def block(self, *stops):
        body = []
        while True:
            token = self.peek()
            if token.kind == "eof":
                if stops and stops != ("eof",):
                    raise ParseError(f"expected '{stops[0]}' before the end of the file")
                return body
            if token.kind == "name" and token.value in stops:
                return body
            body.extend(self.statement_safe())

    def statement(self):
        token = self.peek()
        word = token.value if token.kind == "name" else None
        if self.accept(";"):
            return []
        if word == "local":
            self.next()
            if self.accept("function"):
                name = self.name()
                return [self.function_body(name)]
            names = [self.name()]
            self._attrib()
            while self.accept(","):
                names.append(self.name())
                self._attrib()
            values = self.expression_list() if self.accept("=") else [_const(None)] * len(names)
            result = self.assignment([ast.Name(id=name, ctx=ast.Store()) for name in names], values)
            for declaration in result:
                declaration._declared = True
            return result
        if word == "function":
            self.next()
            parts = [self.name()]
            method = False
            while self.at(".", ":"):
                method = self.next().value == ":"
                parts.append(self.name())
                if method:
                    break
            function = self.function_body("_".join(parts), method=method)
            function._dotted = ".".join(parts)
            function._owner = parts[0] if len(parts) > 1 else None
            function._method = method
            return [function]
        if word == "if":
            self.next()
            test = self.expression()
            self.expect("then")
            root = ast.If(test=test, body=self.block("elseif", "else", "end"), orelse=[])
            node = root
            while True:
                if self.accept("elseif"):
                    test = self.expression()
                    self.expect("then")
                    branch = ast.If(test=test, body=self.block("elseif", "else", "end"), orelse=[])
                    node.orelse = [branch]
                    node = branch
                elif self.accept("else"):
                    node.orelse = self.block("end")
                else:
                    break
            self.expect("end")
            return [root]
        if word == "while":
            self.next()
            test = self.expression()
            self.expect("do")
            body = self.block("end")
            self.expect("end")
            return [ast.While(test=test, body=body, orelse=[])]
        if word == "repeat":
            self.next()
            body = self.block("until")
            self.expect("until")
            test = self.expression()
            return [ast.While(test=_const(True), body=body + [ast.If(test=test, body=[ast.Break()], orelse=[])],
                              orelse=[])]
        if word == "for":
            self.next()
            first = self.name()
            if self.accept("="):
                start = self.expression()
                self.expect(",")
                end = self.expression()
                step = self.expression() if self.accept(",") else _const(1)
                self.expect("do")
                body = self.block("end")
                self.expect("end")
                return [ast.For(target=ast.Name(id=first, ctx=ast.Store()),
                                iter=_call("__inclusive_range", start, end, step), body=body, orelse=[])]
            names = [first]
            while self.accept(","):
                names.append(self.name())
            self.expect("in")
            iterators = self.expression_list()
            self.expect("do")
            body = self.block("end")
            self.expect("end")
            iterator = iterators[0]
            target = ast.Name(id=names[0], ctx=ast.Store()) if len(names) == 1 else ast.Tuple(
                elts=[ast.Name(id=name, ctx=ast.Store()) for name in names[:2]], ctx=ast.Store())
            if isinstance(iterator, ast.Call) and isinstance(iterator.func, ast.Name) and \
                    iterator.func.id in ("ipairs", "pairs") and len(iterator.args) == 1:
                return [ast.For(target=target, iter=_call("__" + iterator.func.id, iterator.args[0]), body=body,
                                orelse=[])]
            raise Unsupported("this kind of for loop has no gublan version; use ipairs or pairs")
        if word == "do":
            self.next()
            body = self.block("end")
            self.expect("end")
            return body
        if word == "return":
            self.next()
            if self.at(*_LUA_BLOCK_END, ";") or self.peek().kind == "eof":
                self.accept(";")
                return [ast.Return(value=None)]
            values = self.expression_list()
            self.accept(";")
            value = values[0] if len(values) == 1 else ast.List(elts=values, ctx=ast.Load())
            return [ast.Return(value=value)]
        if word == "break":
            self.next()
            return [ast.Break()]
        if word == "goto" or self.at("::"):
            raise Unsupported("goto and labels have no gublan version")
        targets = [self.suffixed()]
        if self.at(",", "="):
            while self.accept(","):
                targets.append(self.suffixed())
            self.expect("=")
            return self.assignment(targets, self.expression_list())
        if isinstance(targets[0], ast.Call):
            return [_expr_stmt(targets[0])]
        raise ParseError("expected a function call or an assignment")

    def _attrib(self):
        if self.accept("<"):
            self.name()
            self.expect(">")

    @staticmethod
    def assignment(targets, values):
        for target in targets:
            if isinstance(target, (ast.Name, ast.Attribute, ast.Subscript)):
                target.ctx = ast.Store()
            else:
                raise Unsupported("this assignment target has no gublan version")
        if len(targets) == 1:
            return [_assign(targets[0], values[0])]
        if len(values) == 1 and isinstance(values[0], ast.Call):
            raise Unsupported("functions that return several values have no gublan version")
        while len(values) < len(targets):
            values.append(_const(None))
        return [_assign(ast.Tuple(elts=targets, ctx=ast.Store()),
                        ast.Tuple(elts=values[:len(targets)], ctx=ast.Load()))]

    def function_body(self, name, method=False):
        self.expect("(")
        params = ["self"] if method else []
        while not self.at(")"):
            if self.accept("..."):
                raise Unsupported("functions with ... have no gublan version")
            params.append(self.name())
            if not self.accept(","):
                break
        self.expect(")")
        body = self.block("end")
        self.expect("end")
        return _func(name, params, body)

    def expression_list(self):
        values = [self.expression()]
        while self.accept(","):
            values.append(self.expression())
        return values

    def expression(self, minimum=1):
        token = self.peek()
        if token.kind == "name" and token.value == "not":
            self.next()
            left = ast.UnaryOp(op=ast.Not(), operand=self.expression(_LUA_UNARY))
        elif token.kind == "op" and token.value == "#":
            self.next()
            left = _call("len", self.expression(_LUA_UNARY))
        elif token.kind == "op" and token.value == "-":
            self.next()
            operand = self.expression(_LUA_UNARY)
            left = _const(-operand.value) if _is_const(operand, int, float) else ast.UnaryOp(op=ast.USub(),
                                                                                             operand=operand)
        elif token.kind == "op" and token.value == "~":
            self.next()
            left = ast.UnaryOp(op=ast.Invert(), operand=self.expression(_LUA_UNARY))
        else:
            left = self.simple()
        while True:
            token = self.peek()
            if token.kind not in ("op", "name"):
                return left
            info = _LUA_BINARY.get(token.value)
            if info is None or info[0] < minimum:
                return left
            precedence, kind = info
            if kind is None:
                raise Unsupported(f"the '{token.value}' operator has no gublan version")
            self.next()
            right_assoc = token.value in ("..", "^")
            right = self.expression(precedence if right_assoc else precedence + 1)
            left = _fold_concat(left, right) if kind == "concat" else _combine(kind, left, right)

    def simple(self):
        token = self.peek()
        if token.kind == "number":
            self.next()
            return _const(token.value)
        if token.kind == "string":
            self.next()
            return _const(token.value)
        if token.kind == "name":
            if token.value == "nil":
                self.next()
                return _const(None)
            if token.value in ("true", "false"):
                self.next()
                return _const(token.value == "true")
            if token.value == "function":
                self.next()
                function = self.function_body("anonymous")
                return ArrowFunction(params=[arg.arg for arg in function.args.args], body=function.body)
        if self.at("..."):
            raise Unsupported("'...' has no gublan version")
        if self.at("{"):
            return self.table()
        return self.suffixed()

    def table(self):
        self.expect("{")
        positional, keys, values = [], [], []
        while not self.at("}"):
            if self.accept("["):
                key = self.expression()
                self.expect("]")
                self.expect("=")
                keys.append(key)
                values.append(self.expression())
            elif self.peek().kind == "name" and self.peek(1).value == "=" and self.peek(1).kind == "op":
                keys.append(_const(self.name()))
                self.next()
                values.append(self.expression())
            else:
                positional.append(self.expression())
            if not (self.accept(",") or self.accept(";")):
                break
        self.expect("}")
        if not keys and not positional:
            return _call("__table")
        if not keys:
            return ast.List(elts=positional, ctx=ast.Load())
        for index, value in enumerate(positional, start=1):
            keys.append(_const(index))
            values.append(value)
        return ast.Dict(keys=keys, values=values)

    def suffixed(self):
        token = self.next()
        if token.kind == "name":
            expression = _name(token.value)
        elif token.value == "(":
            expression = self.expression()
            self.expect(")")
        else:
            raise ParseError(f"unexpected {self.describe(token)}")
        while True:
            if self.at("."):
                self.next()
                expression = ast.Attribute(value=expression, attr=self.name(), ctx=ast.Load())
            elif self.at("["):
                self.next()
                index = self.expression()
                self.expect("]")
                expression = ast.Subscript(value=expression, slice=index, ctx=ast.Load())
            elif self.at(":"):
                self.next()
                method = self.name()
                call = ast.Call(func=ast.Attribute(value=expression, attr=method, ctx=ast.Load()),
                                args=self.call_arguments(), keywords=[])
                call._colon = True
                expression = call
            elif (self.at("(") or self.at("{") or self.peek().kind == "string") and not (
                    self.at("(") and self.peek().nl):
                expression = ast.Call(func=expression, args=self.call_arguments(), keywords=[])
            else:
                return expression

    def call_arguments(self):
        if self.peek().kind == "string":
            return [_const(self.next().value)]
        if self.at("{"):
            return [self.table()]
        self.expect("(")
        args = []
        while not self.at(")"):
            args.append(self.expression())
            if not self.accept(","):
                break
        self.expect(")")
        return args


# --------------------------------------------------------------------------
# python fallback parsing
# --------------------------------------------------------------------------

def _parse_python(source):
    try:
        return ast.parse(source).body
    except SyntaxError:
        pass
    lines = source.split("\n")
    chunks = []
    start = 0
    for index in range(1, len(lines)):
        line = lines[index]
        if not line or line[0].isspace() or line.startswith(("else", "elif", "except", "finally", ")", "]", "}")):
            continue
        previous = lines[index - 1].rstrip()
        if previous.endswith(("\\", ",", "(", "[", "{")) or previous.startswith("@"):
            continue
        chunks.append((start, index))
        start = index
    chunks.append((start, len(lines)))
    body = []
    for first, last in chunks:
        text = "\n".join(lines[first:last])
        if not text.strip():
            continue
        try:
            body.extend(ast.parse("\n" * first + text).body)
        except SyntaxError as err:
            todo = Todo(text=text.strip("\n"), reason=f"python could not read this part ({(err.msg or '').lower()})")
            todo.lineno = first + 1 + (len(text) - len(text.lstrip("\n")))
            todo.end_lineno = last
            body.append(todo)
    return body


# --------------------------------------------------------------------------
# library tables
# --------------------------------------------------------------------------

PYGAME_KEYS = {
    "LEFT": "left", "RIGHT": "right", "UP": "up", "DOWN": "down", "SPACE": "space", "RETURN": "return",
    "ESCAPE": "escape", "LSHIFT": "left shift", "RSHIFT": "right shift", "LCTRL": "left ctrl",
    "RCTRL": "right ctrl", "LALT": "left alt", "RALT": "right alt", "BACKSPACE": "backspace", "TAB": "tab",
    "DELETE": "delete", "KP_ENTER": "enter", "HOME": "home", "END": "end", "PAGEUP": "page up",
    "PAGEDOWN": "page down",
}
P5_KEYS = {
    "LEFT_ARROW": "left", "RIGHT_ARROW": "right", "UP_ARROW": "up", "DOWN_ARROW": "down", "ENTER": "return",
    "RETURN": "return", "ESCAPE": "escape", "SHIFT": "left shift", "CONTROL": "left ctrl", "ALT": "left alt",
    "BACKSPACE": "backspace", "DELETE": "delete", "TAB": "tab", "OPTION": "left alt",
}
JS_KEY_CODES = {37: "left", 38: "up", 39: "right", 40: "down", 32: "space", 13: "return", 27: "escape",
                16: "left shift", 17: "left ctrl", 18: "left alt", 8: "backspace", 9: "tab", 46: "delete"}
JS_KEY_NAMES = {"arrowleft": "left", "arrowright": "right", "arrowup": "up", "arrowdown": "down", " ": "space",
                "enter": "return", "escape": "escape", "shift": "left shift", "control": "left ctrl"}
LOVE_KEYS = {"lshift": "left shift", "rshift": "right shift", "lctrl": "left ctrl", "rctrl": "right ctrl",
             "lalt": "left alt", "ralt": "right alt", "kpenter": "enter"}

PYGAME_EVENTS_FALSE = {"QUIT", "KEYUP", "MOUSEBUTTONUP", "MOUSEMOTION", "VIDEORESIZE", "WINDOWRESIZED",
                       "ACTIVEEVENT", "JOYBUTTONDOWN", "JOYAXISMOTION", "MOUSEWHEEL", "TEXTINPUT"}

SKIP_CALLS = {
    "pygame.init", "pygame.font.init", "pygame.mixer.init", "pygame.mixer.pre_init", "pygame.quit",
    "pygame.event.pump", "pygame.mouse.set_visible", "random.seed", "pygame.key.set_repeat",
    "pygame.display.init", "pygame.event.set_allowed", "pygame.event.set_blocked", "math.randomseed",
    "noStroke", "noFill", "stroke", "strokeWeight", "textAlign", "textFont", "angleMode", "rectMode",
    "ellipseMode", "smooth", "noSmooth", "imageMode", "colorMode", "cursor", "noCursor", "pixelDensity",
    "love.graphics.setFont", "love.graphics.setLineWidth", "love.graphics.setDefaultFilter",
    "love.graphics.origin", "love.mouse.setVisible", "love.keyboard.setKeyRepeat", "collectgarbage",
    "console.clear", "pygame.display.set_icon", "love.graphics.setLineStyle", "pygame.mixer.set_num_channels",
}
KILL_CALLS = {"sys.exit", "exit", "quit", "os._exit", "love.event.quit", "os.exit", "process.exit", "noLoop"}
PRINT_CALLS = {"print", "console.log", "console.info", "console.warn", "console.error", "console.debug"}

MATH_SIMPLE = {
    "math.sqrt": "sqrt", "math.floor": "floor", "math.ceil": "ceil", "math.fabs": "abs", "math.abs": "abs",
    "math.radians": "rad", "math.degrees": "deg", "math.rad": "rad", "math.deg": "deg", "math.max": "max",
    "math.min": "min", "math.pow": "pow",
    "Math.floor": "floor", "Math.ceil": "ceil", "Math.round": "round", "Math.abs": "abs", "Math.sqrt": "sqrt",
    "Math.min": "min", "Math.max": "max", "Math.sign": "sign", "Math.trunc": "int", "Math.pow": "pow",
    "abs": "abs", "min": "min", "max": "max", "round": "round", "len": "len", "str": "str", "int": "int",
    "float": "num", "parseInt": "int", "parseFloat": "num", "Number": "num", "String": "str",
    "tostring": "str", "tonumber": "num", "random.choice": "choice", "sorted": "sort", "sum": "sum",
    "Object.keys": "keys", "Object.values": "values", "JSON.stringify": "str", "math.trunc": "int",
    "constrain": "clamp", "lerp": "lerp", "dist": "dist", "sqrt": "sqrt", "floor": "floor", "ceil": "ceil",
    "radians": "rad", "degrees": "deg", "pow": "pow", "string.upper": "upper", "string.lower": "lower",
    "string.len": "len", "table.concat": "join", "bool": "__bool",
}
TRIG = {"sin", "cos", "tan"}
TIME_SECONDS = {"time.time", "time.perf_counter", "time.monotonic", "love.timer.getTime", "os.clock",
                "os.time", "performance.now", "pygame.time.get_ticks", "Date.now", "millis"}
TIME_MILLIS = {"pygame.time.get_ticks", "Date.now", "millis", "performance.now"}


TYPE_NAMES = {"int": "number", "float": "number", "complex": "number", "numbers.Number": "number",
              "numbers.Real": "number", "numbers.Integral": "number", "str": "text", "bool": "boolean",
              "list": "list", "tuple": "list", "dict": "map"}


JS_KEY_NAMES = {"ArrowLeft": "left", "ArrowRight": "right", "ArrowUp": "up", "ArrowDown": "down", " ": "space",
                "Space": "space", "Enter": "return", "Escape": "escape", "Shift": "left shift",
                "ShiftLeft": "left shift", "ShiftRight": "right shift", "Control": "left ctrl",
                "ControlLeft": "left ctrl", "Tab": "tab", "Backspace": "backspace"}


def _js_key(name):
    """a javascript key name (e.key or e.code) as a gublan key name."""
    if name in JS_KEY_NAMES:
        return JS_KEY_NAMES[name]
    match = re.fullmatch(r"(?:Key|Digit)?([A-Za-z0-9])", name)
    if match:
        return match.group(1).lower()
    return name.lower()


def _key_state_map(call):
    """document.addEventListener("keydown", e => { keys[e.key] = true }) -> "keys" (the map that holds which keys
    are down), or None when the listener does anything else."""
    if not (isinstance(call.func, ast.Attribute) and call.func.attr == "addEventListener" and len(call.args) >= 2
            and _is_const(call.args[0], str) and call.args[0].value in ("keydown", "keyup")
            and isinstance(call.args[1], ArrowFunction) and len(call.args[1].params) == 1):
        return None
    param = call.args[1].params[0]
    body = call.args[1].body if isinstance(call.args[1].body, list) else [call.args[1].body]
    found = None
    for statement in body:
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call) and \
                isinstance(statement.value.func, ast.Attribute) and statement.value.func.attr == "preventDefault":
            continue
        if not (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Subscript)
                and isinstance(statement.targets[0].value, ast.Name)
                and isinstance(statement.targets[0].slice, ast.Attribute)
                and isinstance(statement.targets[0].slice.value, ast.Name)
                and statement.targets[0].slice.value.id == param
                and statement.targets[0].slice.attr in ("key", "code")
                and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, bool)):
            return None
        found = statement.targets[0].value.id
    return found


def _all_params(args):
    """every parameter in order: plain ones, then *args, then keyword-only ones, then **kwargs."""
    found = list(args.posonlyargs) + list(args.args)
    if args.vararg:
        found.append(args.vararg)
    found.extend(args.kwonlyargs)
    if args.kwarg:
        found.append(args.kwarg)
    return found


def _default_map(args):
    plain = [arg.arg for arg in list(args.posonlyargs) + list(args.args)]
    defaults = args.defaults
    found = dict(zip(plain[len(plain) - len(defaults):], defaults)) if defaults else {}
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        if default is not None:
            found[arg.arg] = default
    return found


def _is_variadic(args):
    return bool(args.vararg or args.kwarg or args.kwonlyargs)


def _variadic_info(args):
    return (args.vararg.arg if args.vararg else None, args.kwarg.arg if args.kwarg else None,
            len(args.posonlyargs) + len(args.args))


def _key_from_pygame(attr):
    key = attr[2:]
    return PYGAME_KEYS.get(key.upper(), key.lower())


def _minus(node, amount):
    """node - amount, folding constants: (len(t) + 1) - 1 -> len(t)."""
    if _is_const(node, int, float):
        return _const(node.value - amount)
    if isinstance(node, ast.BinOp) and _is_const(node.right, int) and isinstance(node.op, (ast.Add, ast.Sub)):
        offset = node.right.value if isinstance(node.op, ast.Add) else -node.right.value
        offset -= amount
        if offset == 0:
            return node.left
        return ast.BinOp(left=node.left, op=ast.Add() if offset > 0 else ast.Sub(), right=_const(abs(offset)))
    if amount < 0:
        return ast.BinOp(left=node, op=ast.Add(), right=_const(-amount))
    return ast.BinOp(left=node, op=ast.Sub(), right=_const(amount))


def _format_to_fstring(pattern, args, style):
    """turn '%d of %s' % (a, b) or '{} of {}'.format(a, b) into an f-string node."""
    values = []
    args = list(args)
    position = 0
    if style == "percent":
        tokens = re.split(r"(%[-+ 0#]*\d*(?:\.\d+)?[sdifgxXeEcr%])", pattern)
    else:
        tokens = re.split(r"(\{[^{}]*\})", pattern.replace("{{", "\0").replace("}}", "\1"))
    for piece in tokens:
        if not piece:
            continue
        if style == "percent" and piece.startswith("%") and len(piece) > 1:
            if piece == "%%":
                values.append(_const("%"))
                continue
            if position >= len(args):
                raise Unsupported("this text formatting has fewer values than placeholders")
            node = args[position]
            position += 1
            precision = re.search(r"\.(\d+)f", piece)
            if precision:
                node = _call("round", node, _const(int(precision.group(1))))
            elif piece.endswith(("d", "i")):
                node = _call("int", node)
            values.append(ast.FormattedValue(value=node, conversion=-1, format_spec=None))
        elif style == "brace" and piece.startswith("{") and piece.endswith("}"):
            inner = piece[1:-1]
            field, _, spec = inner.partition(":")
            if field.isdigit():
                index = int(field)
            elif field == "":
                index = position
                position += 1
            else:
                raise Unsupported("named format fields have no gublan version")
            if index >= len(args):
                raise Unsupported("this text formatting has fewer values than placeholders")
            node = args[index]
            precision = re.fullmatch(r"\.(\d+)f", spec or "")
            if precision:
                node = _call("round", node, _const(int(precision.group(1))))
            values.append(ast.FormattedValue(value=node, conversion=-1, format_spec=None))
        else:
            values.append(_const(piece.replace("\0", "{").replace("\1", "}")))
    return ast.JoinedStr(values=values)


_DESCRIBE = {
    ast.Lambda: "lambda functions", ast.ListComp: "list comprehensions", ast.DictComp: "dict comprehensions",
    ast.SetComp: "set comprehensions", ast.GeneratorExp: "generator expressions", ast.Await: "await",
    ast.Yield: "yield", ast.YieldFrom: "yield", ast.NamedExpr: "the := operator", ast.Starred: "* unpacking",
}
_ALLOWED_INPUT = (
    ast.expr_context, ast.operator, ast.unaryop, ast.boolop, ast.cmpop, ast.Constant, ast.Name, ast.BinOp,
    ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp, ast.Call, ast.Attribute, ast.Subscript, ast.List,
    ast.Tuple, ast.Dict, ast.Set, ast.JoinedStr, ast.FormattedValue, ast.Slice, ast.keyword,
)


# --------------------------------------------------------------------------
# expression mapping
# --------------------------------------------------------------------------

class _ExprMapper(ast.NodeTransformer):
    def __init__(self, writer):
        self.w = writer

    def generic_visit(self, node):
        if not isinstance(node, _ALLOWED_INPUT):
            label = _DESCRIBE.get(type(node), type(node).__name__.lower())
            raise Unsupported(f"{label} have no gublan version")
        return super().generic_visit(node)

    def visit_ArrowFunction(self, node):
        # a javascript or lua function written as a value: x => x * 2 works in gublan when it gives back one value
        body = node.body if isinstance(node.body, list) else [node.body]
        if len(body) == 1 and isinstance(body[0], ast.Return) and body[0].value is not None:
            return self._lambda([str(param) for param in node.params], body[0].value)
        if len(body) == 1 and isinstance(body[0], ast.Expr):
            return self._lambda([str(param) for param in node.params], body[0].value)
        raise Unsupported("functions written as values only work in gublan when they give back one value "
                          "(x => x * 2); make this a named function")

    def visit_Lambda(self, node):
        args = node.args
        if args.vararg or args.kwarg or args.kwonlyargs or args.defaults or args.posonlyargs:
            raise Unsupported("little functions with default or * parameters have no gublan version")
        return self._lambda([arg.arg for arg in args.args], node.body)

    def _lambda(self, params, body):
        names = []
        for param in params:
            if not isinstance(param, str) or not param.isidentifier():
                raise Unsupported("this little function's parameters have no gublan version")
            names.append(ast.arg(arg=self.w.variable(param)))
        return ast.Lambda(args=ast.arguments(posonlyargs=[], args=names, vararg=None, kwonlyargs=[],
                                             kw_defaults=[], kwarg=None, defaults=[]),
                          body=self.visit(body))

    def _comprehension(self, generators):
        out = []
        for generator in generators:
            if generator.is_async:
                raise Unsupported("async comprehensions have no gublan version")
            out.append(ast.comprehension(target=self._loop_target(generator.target),
                                         iter=self._iterable(generator.iter),
                                         ifs=[self.visit(test) for test in generator.ifs], is_async=0))
        return out

    def _loop_target(self, node):
        if isinstance(node, ast.Name):
            mapped = self.visit(ast.Name(id=node.id, ctx=ast.Load()))
            if not isinstance(mapped, ast.Name):
                raise Unsupported("this loop variable has no gublan version")
            return ast.Name(id=mapped.id, ctx=ast.Store())
        if isinstance(node, (ast.Tuple, ast.List)) and all(isinstance(item, (ast.Name, ast.Tuple, ast.List))
                                                           for item in node.elts):
            return ast.Tuple(elts=[self._loop_target(item) for item in node.elts], ctx=ast.Store())
        raise Unsupported("this loop variable has no gublan version")

    def _iterable(self, node):
        """what a comprehension walks over. d.items() becomes zip(keys(d), values(d))."""
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and not node.args and \
                node.func.attr == "items" and self.w.language == "python":
            receiver = self.visit(node.func.value)
            return _call("zip", _call("keys", receiver), _call("values", copy.deepcopy(receiver)))
        return self.visit(node)

    def visit_ListComp(self, node):
        generators = self._comprehension(node.generators)
        return ast.ListComp(elt=self.visit(node.elt), generators=generators)

    def visit_GeneratorExp(self, node):
        generators = self._comprehension(node.generators)
        return ast.ListComp(elt=self.visit(node.elt), generators=generators)

    def visit_SetComp(self, node):
        self.w.note("sets became lists")
        generators = self._comprehension(node.generators)
        return _call("unique", ast.ListComp(elt=self.visit(node.elt), generators=generators))

    def visit_DictComp(self, node):
        generators = self._comprehension(node.generators)
        return ast.DictComp(key=self.visit(node.key), value=self.visit(node.value), generators=generators)

    def visit_Constant(self, node):
        value = node.value
        if value is True:
            return _name("true")
        if value is False:
            return _name("false")
        if value is None:
            return _name("none")
        if isinstance(value, float) and not math.isfinite(value):
            raise Unsupported("infinite numbers have no gublan version")
        if isinstance(value, bytes):
            self.w.note("bytes (b\"...\") became text")
            return _const(value.decode("latin-1"))
        if isinstance(value, complex) or value is Ellipsis:
            raise Unsupported("this kind of value has no gublan version")
        return node

    def visit_Tuple(self, node):
        return ast.List(elts=[self.visit(item) for item in node.elts], ctx=ast.Load())

    def visit_Set(self, node):
        self.w.note("sets became lists")
        return ast.List(elts=[self.visit(item) for item in node.elts], ctx=ast.Load())

    def visit_Name(self, node):
        w = self.w
        identifier = node.id
        if identifier in w.star_names:
            return self.visit(w.star_names[identifier]())
        if w.library == "p5" and identifier not in w.assigned:
            p5 = {
                "mouseX": _call("mousex"), "mouseY": _call("mousey"), "width": _name("screen_width"),
                "height": _name("screen_height"), "mouseIsPressed": _call("mousedown", _const("left")),
                "PI": _name("pi"), "TWO_PI": ast.BinOp(left=_name("pi"), op=ast.Mult(), right=_const(2)),
                "HALF_PI": ast.BinOp(left=_name("pi"), op=ast.Div(), right=_const(2)),
                "QUARTER_PI": ast.BinOp(left=_name("pi"), op=ast.Div(), right=_const(4)),
                "deltaTime": ast.BinOp(left=_name("dt"), op=ast.Mult(), right=_const(1000)),
            }
            if identifier in p5:
                return p5[identifier]
            if identifier in P5_KEYS:
                return _const(P5_KEYS[identifier])
            if identifier in ("frameCount", "keyIsPressed", "pmouseX", "pmouseY"):
                raise Unsupported(f"'{identifier}' has no gublan version")
        if w.library == "canvas" and identifier in ("innerWidth", "innerHeight"):
            return _name("screen_width" if identifier == "innerWidth" else "screen_height")
        if identifier in w.renames:
            return _name(w.renames[identifier])
        if identifier in w.functions and identifier not in w.assigned and identifier not in w.parameters:
            return _name(w.functions[identifier])  # a function used as a value: map(items, double)
        return _name(w.variable(identifier))

    def visit_Attribute(self, node):
        w = self.w
        dotted = w.dotted(node)
        constants = {
            "math.pi": _name("pi"), "Math.PI": _name("pi"), "math.e": _const(math.e), "Math.E": _const(math.e),
            "math.tau": ast.BinOp(left=_name("pi"), op=ast.Mult(), right=_const(2)),
            "math.huge": _const(1e15), "math.inf": _const(1e15), "Number.MAX_VALUE": _const(1e15),
            "Number.MAX_SAFE_INTEGER": _const(9007199254740991), "math.maxinteger": _const(9007199254740991),
            "Math.SQRT2": _const(math.sqrt(2)),
        }
        if dotted in constants:
            if dotted in ("math.huge", "math.inf", "Number.MAX_VALUE"):
                w.note("infinity became the large number 1000000000000000")
            return constants[dotted]
        if dotted and dotted.startswith("pygame.K_"):
            return _const(_key_from_pygame(dotted[len("pygame."):]))
        if dotted and w.event_var and dotted.startswith(w.event_var + "."):
            field = dotted[len(w.event_var) + 1:]
            if field == "pos":
                return ast.List(elts=[_call("mousex"), _call("mousey")], ctx=ast.Load())
            if field == "button":
                return _const(1)
            raise Unsupported(f"reading event.{field} has no gublan version; use keypressed(\"key\")")
        if dotted in ("love.timer.getDelta",):
            return _name("dt")
        if dotted and dotted.split(".")[0] in w.canvas_vars and node.attr in ("width", "height"):
            return _name("screen_width" if node.attr == "width" else "screen_height")
        if node.attr == "length" and w.language == "javascript":
            return _call("len", self.visit(node.value))
        if w.library == "pygame" and not (dotted and dotted.split(".")[0] in w.modules):
            rect_fields = {"width": "w", "height": "h", "left": "x", "top": "y"}
            base = self.visit(node.value)
            if node.attr in rect_fields:
                return ast.Attribute(value=base, attr=rect_fields[node.attr], ctx=ast.Load())
            if node.attr in ("right", "bottom", "centerx", "centery"):
                origin = "x" if node.attr in ("right", "centerx") else "y"
                size = "w" if origin == "x" else "h"
                extent = ast.Attribute(value=copy.deepcopy(base), attr=size, ctx=ast.Load())
                if node.attr.startswith("center"):
                    extent = ast.BinOp(left=extent, op=ast.Div(), right=_const(2))
                return ast.BinOp(left=ast.Attribute(value=base, attr=origin, ctx=ast.Load()), op=ast.Add(),
                                 right=extent)
            return ast.Attribute(value=base, attr=node.attr, ctx=ast.Load())
        if dotted and dotted.split(".")[0] in w.modules:
            raise Unsupported(f"{dotted} has no gublan version")
        return ast.Attribute(value=self.visit(node.value), attr=node.attr, ctx=ast.Load())

    def visit_Subscript(self, node):
        w = self.w
        container = node.value
        index = node.slice
        if isinstance(container, ast.Name) and container.id in w.key_maps and _is_const(index, str):
            return _call("keydown", _const(_js_key(index.value)))
        dotted_index = w.dotted(index) if isinstance(index, (ast.Attribute, ast.Name)) else None
        if dotted_index and (dotted_index.startswith("pygame.K_") or (
                isinstance(container, ast.Name) and container.id in w.keys_vars)):
            key = _key_from_pygame(dotted_index.split(".")[-1]) if "K_" in dotted_index else None
            if key:
                return _call("keydown", _const(key))
        if isinstance(container, ast.Call) and w.dotted(container.func) == "pygame.mouse.get_pressed" and \
                _is_const(index, int):
            return _call("mousedown", _const(("left", "middle", "right")[min(2, index.value)]))
        if isinstance(container, ast.Call) and w.dotted(container.func) == "pygame.mouse.get_pos" and \
                _is_const(index, int):
            return _call("mousex" if index.value == 0 else "mousey")
        if isinstance(container, ast.Name) and container.id in w.keys_vars and w.language == "javascript":
            if _is_const(index, str):
                return _call("keydown", _const(JS_KEY_NAMES.get(index.value.lower(), index.value.lower())))
        value = self.visit(container)
        if isinstance(index, ast.Slice):
            if index.step is not None:
                raise Unsupported("slices with a step have no gublan version")
            new_slice = ast.Slice(lower=self.visit(index.lower) if index.lower else None,
                                  upper=self.visit(index.upper) if index.upper else None, step=None)
            return ast.Subscript(value=value, slice=new_slice, ctx=ast.Load())
        new_index = self.visit(index)
        if w.language == "lua" and not _is_const(index, str) and not w.is_map(container):
            new_index = _minus(new_index, 1)
        return ast.Subscript(value=value, slice=new_index, ctx=ast.Load())

    def visit_BinOp(self, node):
        if isinstance(node.op, ast.MatMult):
            raise Unsupported("the @ operator has no gublan version")
        if isinstance(node.op, ast.Mod) and _is_const(node.left, str):
            args = node.right.elts if isinstance(node.right, (ast.Tuple, ast.List)) else [node.right]
            return self.visit(_format_to_fstring(node.left.value, args, "percent"))
        return ast.BinOp(left=self.visit(node.left), op=node.op, right=self.visit(node.right))

    def _key_test(self, subject, value, negate=False):
        """event.key == K_SPACE, key == 'a', keyCode === LEFT_ARROW -> keypressed("...")"""
        w = self.w
        names = []
        values = value.elts if isinstance(value, (ast.Tuple, ast.List)) else [value]
        for item in values:
            dotted = w.dotted(item) if isinstance(item, (ast.Attribute, ast.Name)) else None
            if dotted and "K_" in dotted:
                names.append(_key_from_pygame(dotted.split(".")[-1]))
            elif isinstance(item, ast.Name) and item.id in P5_KEYS:
                names.append(P5_KEYS[item.id])
            elif _is_const(item, int):
                code = item.value
                names.append(JS_KEY_CODES.get(code) or (chr(code).lower() if 48 <= code <= 90 else None))
            elif _is_const(item, str):
                text = item.value.lower()
                names.append(JS_KEY_NAMES.get(text) or LOVE_KEYS.get(text) or text)
            else:
                return None
        if not names or any(name is None for name in names):
            return None
        function = "keypressed" if w.key_events else "keydown"
        calls = [_call(function, _const(name)) for name in names]
        result = calls[0] if len(calls) == 1 else ast.BoolOp(op=ast.Or(), values=calls)
        return ast.UnaryOp(op=ast.Not(), operand=result) if negate else result

    def visit_Compare(self, node):
        w = self.w
        if len(node.ops) == 1:
            left, op, right = node.left, node.ops[0], node.comparators[0]
            equal = isinstance(op, (ast.Eq, ast.Is, ast.In))
            negate = isinstance(op, (ast.NotEq, ast.IsNot, ast.NotIn))
            if equal or negate:
                left_dotted = w.dotted(left) if isinstance(left, (ast.Attribute, ast.Name)) else None
                if w.event_var and left_dotted == w.event_var + ".type":
                    event = (w.dotted(right) or "").split(".")[-1]
                    if event in PYGAME_EVENTS_FALSE:
                        result = _name("false")
                    elif event == "KEYDOWN":
                        result = _name("true")
                    elif event == "MOUSEBUTTONDOWN":
                        result = _call("mousepressed", _const("left"))
                    else:
                        raise Unsupported(f"checking for {event.lower()} events has no gublan version")
                    if negate:
                        result = _name("true" if _is_false(result) else "false") if isinstance(result, ast.Name) \
                            else ast.UnaryOp(op=ast.Not(), operand=result)
                    return result
                if (w.event_var and left_dotted in (w.event_var + ".key", w.event_var + ".code")) or (
                        isinstance(left, ast.Name) and left.id in w.key_names):
                    test = self._key_test(left, right, negate)
                    if test is not None:
                        return test
        ops = [ast.Eq() if isinstance(op, ast.Is) else ast.NotEq() if isinstance(op, ast.IsNot) else op
               for op in node.ops]
        return ast.Compare(left=self.visit(node.left), ops=ops,
                           comparators=[self.visit(item) for item in node.comparators])

    def visit_JoinedStr(self, node):
        values = []
        for piece in node.values:
            if isinstance(piece, ast.FormattedValue):
                value = self.visit(piece.value)
                spec = None
                if piece.format_spec is not None:
                    text = "".join(part.value for part in piece.format_spec.values if isinstance(part, ast.Constant))
                    precision = re.fullmatch(r"[,]?\.(\d+)f", text)
                    if precision:
                        value = _call("round", value, _const(int(precision.group(1))))
                    elif text in ("d", "n"):
                        value = _call("int", value)
                    elif text:
                        self.w.note("some text formats (like :>5) were removed")
                values.append(ast.FormattedValue(value=value, conversion=-1, format_spec=spec))
            else:
                values.append(piece)
        return ast.JoinedStr(values=values)

    def visit_Dict(self, node):
        if any(key is None for key in node.keys):
            raise Unsupported("** unpacking has no gublan version")
        return ast.Dict(keys=[self.visit(key) for key in node.keys], values=[self.visit(v) for v in node.values])

    # calls ---------------------------------------------------------------
    def visit_Call(self, node):
        w = self.w
        if any(isinstance(arg, ast.Starred) for arg in node.args):
            raise Unsupported("* arguments have no gublan version")
        dotted = w.dotted(node.func) if isinstance(node.func, (ast.Name, ast.Attribute)) else None
        args = node.args
        if dotted in w.dotted_functions:
            return self._user_call(w.dotted_functions[dotted], node)
        if isinstance(node.func, ast.Name):
            name = node.func.id
            if name in w.star_names and dotted:
                pass
            elif name in w.functions:
                return self._user_call(w.functions[name], node)
            elif name in w.classes:
                return self._constructor(name, node)
        mapped = self._library_call(dotted, args, node) if dotted else None
        if mapped is not None:
            return mapped
        if isinstance(node.func, ast.Attribute):
            method = self._method_call(node)
            if method is not None:
                return method
        if isinstance(node.func, ast.Name):
            name = node.func.id
            if name in GUBLAN_FUNCTIONS:
                return ast.Call(func=_name(name), args=[self.visit(arg) for arg in args], keywords=[])
            if (name in w.assigned or name in w.parameters) and not node.keywords:
                # a variable holding a function (a lambda, or a function passed in)
                return ast.Call(func=self.visit(node.func), args=[self.visit(arg) for arg in args], keywords=[])
            raise Unsupported(f"{name}() has no gublan version")
        raise Unsupported(f"{dotted or 'this call'}() has no gublan version")

    def _user_call(self, gublan_name, node, prefix=()):
        w = self.w
        signature = w.signatures.get(gublan_name)
        if gublan_name in w.variadic and signature is not None:
            return self._variadic_call(gublan_name, node, prefix, signature, w.variadic[gublan_name])
        args = list(prefix) + [self.visit(arg) for arg in node.args]
        if node.keywords:
            if signature is None or any(keyword.arg is None for keyword in node.keywords):
                raise Unsupported("named arguments to this function have no gublan version")
            params = signature[0]
            filled = dict(enumerate(args))
            for keyword in node.keywords:
                if keyword.arg not in params:
                    raise Unsupported(f"'{keyword.arg}' is not a parameter of {gublan_name}")
                filled[params.index(keyword.arg)] = self.visit(keyword.value)
            args = [filled.get(index) for index in range(max(filled) + 1)]
            if any(arg is None for arg in args):
                defaults = signature[1]
                for index, arg in enumerate(args):
                    if arg is None:
                        default = defaults.get(params[index])
                        if default is None:
                            raise Unsupported(f"call to {gublan_name} is missing '{params[index]}'")
                        args[index] = self.visit(copy.deepcopy(default))
        if signature is not None:
            params, defaults = signature
            for index in range(len(args), len(params)):
                default = defaults.get(params[index])
                if default is None:
                    break
                args.append(self.visit(copy.deepcopy(default)))
        return ast.Call(func=_name(gublan_name), args=args, keywords=[])

    def _variadic_call(self, gublan_name, node, prefix, signature, variadic):
        """a call to a function with *args, keyword-only parameters or **kwargs: gublan passes the extra values as
        a list and the extra named values as a map."""
        params, defaults = signature
        vararg, kwarg, positional = variadic
        values = list(prefix) + [self.visit(arg) for arg in node.args]
        slots = {}
        for index, value in enumerate(values[:positional]):
            slots[params[index]] = value
        extra = values[positional:]
        if extra and not vararg:
            raise Unsupported(f"{gublan_name} is given more values than it takes")
        if vararg:
            slots[vararg] = ast.List(elts=extra, ctx=ast.Load())
        loose_keys, loose_values = [], []
        for keyword in node.keywords:
            if keyword.arg is None:
                raise Unsupported("** arguments have no gublan version")
            if keyword.arg in params and keyword.arg not in (vararg, kwarg):
                slots[keyword.arg] = self.visit(keyword.value)
            elif kwarg:
                loose_keys.append(_const(keyword.arg))
                loose_values.append(self.visit(keyword.value))
            else:
                raise Unsupported(f"'{keyword.arg}' is not a parameter of {gublan_name}")
        if kwarg:
            slots[kwarg] = ast.Dict(keys=loose_keys, values=loose_values)
        args = []
        for param in params:
            if param in slots:
                args.append(slots[param])
                continue
            default = defaults.get(param)
            if default is None:
                raise Unsupported(f"call to {gublan_name} is missing '{param}'")
            args.append(self.visit(copy.deepcopy(default)))
        return ast.Call(func=_name(gublan_name), args=args, keywords=[])

    def _builtin_call(self, name, args, node):
        """python built-ins that gublan has in another shape."""
        visit = self.visit
        keywords = {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg}
        if any(keyword.arg is None for keyword in node.keywords):
            return None
        if name == "isinstance" and len(args) == 2 and not keywords:
            kinds = args[1].elts if isinstance(args[1], (ast.Tuple, ast.List)) else [args[1]]
            names = []
            for kind in kinds:
                label = TYPE_NAMES.get(self.w.dotted(kind) if isinstance(kind, (ast.Name, ast.Attribute)) else None)
                if label is None:
                    raise Unsupported("isinstance() only has a gublan version for numbers, text, lists and maps; "
                                      "use type(x) == \"number\"")
                if label not in names:
                    names.append(label)
            checks = [ast.Compare(left=_call("type", visit(args[0])), ops=[ast.Eq()], comparators=[_const(label)])
                      for label in names]
            return checks[0] if len(checks) == 1 else ast.BoolOp(op=ast.Or(), values=checks)
        if name in ("sorted", "min", "max") and keywords and set(keywords) <= {"key", "reverse", "default"} \
                and len(args) == 1:
            items = visit(args[0])
            if "key" in keywords and not _is_const(keywords["key"], type(None)):
                # sortby keeps ties in order; max walks the list backwards so the first of equal items wins
                source = _call("reverse", items) if name == "max" else items
                ordered = _call("sortby", source, visit(keywords["key"]))
            else:
                ordered = _call("sort", items)
            if "reverse" in keywords:
                if _is_true(keywords["reverse"]):
                    ordered = _call("reverse", ordered)
                elif not _is_false(keywords["reverse"]):
                    return None
            if name == "sorted":
                if "default" in keywords:
                    return None
                return ordered
            picked = ast.Subscript(value=ordered, slice=_const(0 if name == "min" else -1), ctx=ast.Load())
            if "default" in keywords:
                return ast.IfExp(test=_call("len", copy.deepcopy(items)), body=picked, orelse=visit(keywords["default"]))
            return picked
        if keywords:
            return None
        if name in ("map", "filter") and len(args) == 2:
            function = args[0]
            if name == "filter" and _is_const(function, type(None)):
                return _call("filter", visit(args[1]), self._lambda(["item"], ast.Name(id="item", ctx=ast.Load())))
            return _call(name, visit(args[1]), visit(function))
        if name == "all" and len(args) == 1:
            return _call("every", visit(args[0]))
        if name in ("set", "frozenset") and len(args) <= 1:
            self.w.note("sets became lists")
            return _call("unique", visit(args[0])) if args else ast.List(elts=[], ctx=ast.Load())
        if name == "tuple" and len(args) <= 1:
            return visit(args[0]) if args else ast.List(elts=[], ctx=ast.Load())
        if name == "repr" and len(args) == 1:
            return _call("str", visit(args[0]))
        if name == "divmod" and len(args) == 2:
            return ast.List(elts=[ast.BinOp(left=visit(args[0]), op=ast.FloorDiv(), right=visit(args[1])),
                                  ast.BinOp(left=visit(args[0]), op=ast.Mod(), right=visit(args[1]))],
                            ctx=ast.Load())
        if name == "reversed" and len(args) == 1:
            return _call("reverse", visit(args[0]))
        if name in ("getattr", "hasattr") and len(args) in (2, 3) and _is_const(args[1], str) and \
                args[1].value.isidentifier():
            field = args[1].value
            owner = visit(args[0])
            has = ast.Compare(left=_const(field), ops=[ast.In()], comparators=[owner])
            if name == "hasattr":
                return has if len(args) == 2 else None
            read = ast.Attribute(value=copy.deepcopy(owner), attr=field, ctx=ast.Load())
            if len(args) == 2:
                return read
            return ast.IfExp(test=has, body=read, orelse=visit(args[2]))
        if name == "chr" and len(args) == 1:
            return _call("char", visit(args[0]))
        if name == "ord" and len(args) == 1:
            return _call("code", visit(args[0]))
        if name == "callable" and len(args) == 1:
            return ast.Compare(left=_call("type", visit(args[0])), ops=[ast.Eq()], comparators=[_const("function")])
        return None

    def _constructor(self, class_name, node):
        info = self.w.classes[class_name]
        empty = ast.Dict(keys=[], values=[])
        if not info["init"]:
            return empty
        return self._user_call(f"{class_name}__init__", node, prefix=[empty])

    def _method_call(self, node):
        w = self.w
        attr = node.func.attr
        receiver = node.func.value
        args = node.args
        receiver_dotted = w.dotted(receiver) if isinstance(receiver, (ast.Name, ast.Attribute)) else None
        if attr in w.methods and not (receiver_dotted and receiver_dotted.split(".")[0] in w.modules):
            owners = w.methods[attr]
            owner = None
            if isinstance(receiver, ast.Name) and receiver.id == "self" and w.current_class in owners:
                owner = w.current_class
            elif isinstance(receiver, ast.Name) and receiver.id in w.classes and receiver.id in owners:
                return self._user_call(f"{receiver.id}_{attr}", node)
            elif len(owners) == 1:
                owner = next(iter(owners))
            if owner is None:
                raise Unsupported(f"'{attr}' is defined in more than one class; call it as Class_{attr}(object)")
            if w.static_methods.get((owner, attr)):
                return self._user_call(f"{owner}_{attr}", node)
            return self._user_call(f"{owner}_{attr}", node, prefix=[self.visit(receiver)])
        value = lambda: self.visit(receiver)  # noqa: E731
        call = lambda name, *extra: ast.Call(func=_name(name), args=list(extra), keywords=[])  # noqa: E731
        if attr == "tick" and w.library == "pygame" and len(args) <= 1:
            return ast.BinOp(left=_name("dt"), op=ast.Mult(), right=_const(1000))
        callback = len(args) >= 1 and isinstance(args[0], (ArrowFunction, ast.Lambda))
        if callback and w.language == "javascript":
            function = self.visit(args[0])
            simple = {"map": "map", "filter": "filter", "find": "find", "some": "any", "every": "every"}
            if attr in simple and len(args) == 1:
                return call(simple[attr], value(), function)
            if attr == "reduce" and len(args) == 2:
                return call("reduce", value(), function, self.visit(args[1]))
            if attr == "findIndex" and len(args) == 1:
                found = call("find", value(), function)
                return call("indexof", value(), found)
        visited = [self.visit(arg) for arg in args]
        if attr in ("endswith", "endsWith") and len(args) == 1:
            return call("endswith", value(), visited[0])
        if attr in ("title", "capitalize") and not args and w.language == "python":
            return call("capitalize", value())
        if attr == "count" and len(args) == 1 and w.language == "python":
            return call("count", value(), visited[0])
        if attr == "isdigit" and not args:
            return call("isnumber", value())
        if attr in ("lstrip", "rstrip") and not args:
            return call("trim", value())
        if attr == "concat" and len(args) == 1 and w.language == "javascript":
            return ast.BinOp(left=value(), op=ast.Add(), right=visited[0])
        if attr == "items" and not args and w.language == "python":
            return call("zip", call("keys", value()), call("values", value()))
        if attr in ("upper", "toUpperCase") and not args:
            return call("upper", value())
        if attr in ("lower", "toLowerCase") and not args:
            return call("lower", value())
        if attr in ("strip", "trim") and not args:
            return call("trim", value())
        if attr == "split" and len(args) <= 1:
            return call("split", value(), *visited)
        if attr in ("replace", "replaceAll") and len(args) == 2:
            return call("replace", value(), *visited)
        if attr == "join" and len(args) <= 1:
            if w.language == "python" and _is_const(receiver, str):
                return call("join", visited[0], value()) if visited else call("join", value())
            return call("join", value(), *visited)
        if attr in ("includes", "contains") and len(args) == 1:
            return call("contains", value(), visited[0])
        if attr in ("indexOf", "index", "find") and len(args) == 1:
            return call("indexof", value(), visited[0])
        if attr == "keys" and not args:
            return call("keys", value())
        if attr == "values" and not args:
            return call("values", value())
        if attr == "get" and len(args) in (1, 2) and w.language == "python":
            default = visited[1] if len(args) == 2 else _name("none")
            return ast.IfExp(test=call("contains", value(), visited[0]),
                             body=ast.Subscript(value=value(), slice=visited[0], ctx=ast.Load()), orelse=default)
        if attr == "toString" and not args:
            return call("str", value())
        if attr == "toFixed" and len(args) == 1:
            return call("str", call("round", value(), visited[0]))
        if attr == "colliderect" and len(args) == 1:
            return call("overlap", value(), visited[0])
        if attr == "format" and _is_const(receiver, str):
            return self.visit(_format_to_fstring(receiver.value, args, "brace"))
        if attr == "copy" and not args:
            return ast.BinOp(left=value(), op=ast.Add(), right=ast.List(elts=[], ctx=ast.Load()))
        if attr in ("convert", "convert_alpha") and not args:
            return value()
        if attr == "len" and getattr(node, "_colon", False):
            return call("len", value())
        if attr == "sub" and getattr(node, "_colon", False):
            return self._lua_sub(value(), visited)
        if attr == "rep" and getattr(node, "_colon", False) and len(visited) == 1:
            return ast.BinOp(left=value(), op=ast.Mult(), right=visited[0])
        if attr == "get_width" and receiver_dotted in w.screen_vars:
            return _name("screen_width")
        if attr == "get_height" and receiver_dotted in w.screen_vars:
            return _name("screen_height")
        if attr in ("startswith", "startsWith") and len(args) == 1:
            return ast.Compare(left=call("indexof", value(), visited[0]), ops=[ast.Eq()], comparators=[_const(0)])
        return None

    @staticmethod
    def _lua_sub(text, args):
        start = _minus(args[0], 1) if args else _const(0)
        if isinstance(start, ast.UnaryOp) or (_is_const(start, int) and start.value < 0):
            raise Unsupported("negative positions in string.sub have no gublan version")
        upper = args[1] if len(args) > 1 else None
        if upper is not None and _is_const(upper, int) and upper.value < 0:
            raise Unsupported("negative positions in string.sub have no gublan version")
        return ast.Subscript(value=text, slice=ast.Slice(lower=start, upper=upper, step=None), ctx=ast.Load())

    def _library_call(self, dotted, args, node):
        w = self.w
        visit = self.visit
        lib = w.library
        name = dotted
        if w.language == "python" and name in ("sorted", "min", "max") and node.keywords:
            mapped = self._builtin_call(name, args, node)
            if mapped is None:
                raise Unsupported(f"{name}() with these named values has no gublan version")
            return mapped
        if name in MATH_SIMPLE:
            target = MATH_SIMPLE[name]
            if target == "__bool":
                return ast.UnaryOp(op=ast.Not(), operand=ast.UnaryOp(op=ast.Not(), operand=visit(args[0])))
            if target == "join" and name == "table.concat":
                return _call("join", *[visit(arg) for arg in args])
            if name in ("float", "Number", "parseFloat") and args and _is_const(args[0], str):
                return _const(float(args[0].value))
            if name == "parseInt" and len(args) == 2:
                raise Unsupported("parseInt with a base has no gublan version")
            if target == "round" and name == "Math.round":
                return _call("round", visit(args[0]))
            return ast.Call(func=_name(target), args=[visit(arg) for arg in args], keywords=[])
        short = name.split(".")[-1]
        prefix = name.rsplit(".", 1)[0] if "." in name else ""
        if prefix in ("math", "Math") or (lib == "p5" and not prefix):
            if short in TRIG and len(args) == 1:
                inner = args[0]
                if isinstance(inner, ast.Call) and w.dotted(inner.func) in ("math.radians", "radians",
                                                                            "math.rad") and inner.args:
                    return _call(short, visit(inner.args[0]))
                return _call(short, _call("deg", visit(inner)))
            if short in ("asin", "acos", "atan") and len(args) == 1:
                return _call("rad", _call(short, visit(args[0])))
            if short == "atan2" or (short == "atan" and len(args) == 2):
                return _call("rad", _call("atan2", visit(args[0]), visit(args[1])))
            if short == "hypot" and len(args) == 2:
                return _call("dist", _const(0), _const(0), visit(args[0]), visit(args[1]))
            if short == "random" and prefix == "Math":
                return _call("random")
            if short == "random" and prefix == "math":
                if not args:
                    return _call("random")
                if len(args) == 1:
                    return _call("random", _const(1), visit(args[0]))
                return _call("random", visit(args[0]), visit(args[1]))
            if short == "map" and lib == "p5" and len(args) == 5:
                value, a1, b1, a2, b2 = (visit(arg) for arg in args)
                return ast.BinOp(left=a2, op=ast.Add(), right=ast.BinOp(
                    left=ast.BinOp(left=ast.BinOp(left=value, op=ast.Sub(), right=a1), op=ast.Mult(),
                                   right=ast.BinOp(left=copy.deepcopy(b2), op=ast.Sub(), right=copy.deepcopy(a2))),
                    op=ast.Div(), right=ast.BinOp(left=b1, op=ast.Sub(), right=copy.deepcopy(a1))))
            if short == "random" and lib == "p5":
                if not args:
                    return _call("random")
                if len(args) == 1:
                    if isinstance(args[0], (ast.List, ast.Name)) and not _is_const(args[0]):
                        if isinstance(args[0], ast.List):
                            return _call("choice", visit(args[0]))
                    return _call("lerp", _const(0), visit(args[0]), _call("random"))
                return _call("lerp", visit(args[0]), visit(args[1]), _call("random"))
            if short == "color" and lib == "p5":
                values = [visit(arg) for arg in args]
                if len(values) == 1:
                    values = values * 3
                return ast.List(elts=values[:3], ctx=ast.Load())
            if short in ("int",) and lib == "p5":
                return _call("int", visit(args[0]))
        if name == "random.random" or name == "love.math.random" and not args:
            return _call("random")
        if name in ("random.randint", "love.math.random") and len(args) == 2:
            return _call("random", visit(args[0]), visit(args[1]))
        if name == "random.randrange":
            if len(args) == 1:
                return _call("random", _const(0), _minus(visit(args[0]), 1))
            if len(args) == 2:
                return _call("random", visit(args[0]), _minus(visit(args[1]), 1))
        if name == "random.uniform" and len(args) == 2:
            return _call("lerp", visit(args[0]), visit(args[1]), _call("random"))
        if name in TIME_SECONDS:
            if name in TIME_MILLIS:
                return ast.BinOp(left=_call("time"), op=ast.Mult(), right=_const(1000))
            return _call("time")
        if name in ("keyIsDown", "love.keyboard.isDown", "love.keyboard.isScancodeDown"):
            names = []
            for arg in args:
                if isinstance(arg, ast.Name) and arg.id in P5_KEYS:
                    names.append(P5_KEYS[arg.id])
                elif _is_const(arg, int):
                    names.append(JS_KEY_CODES.get(arg.value) or chr(arg.value).lower())
                elif _is_const(arg, str):
                    names.append(LOVE_KEYS.get(arg.value, arg.value))
                else:
                    return _call("keydown", visit(arg))
            calls = [_call("keydown", _const(key)) for key in names]
            return calls[0] if len(calls) == 1 else ast.BoolOp(op=ast.Or(), values=calls)
        if name in ("love.mouse.getX", "pygame.mouse.get_x"):
            return _call("mousex")
        if name in ("love.mouse.getY",):
            return _call("mousey")
        if name in ("love.mouse.getPosition", "pygame.mouse.get_pos"):
            return ast.List(elts=[_call("mousex"), _call("mousey")], ctx=ast.Load())
        if name == "love.mouse.isDown":
            button = args[0].value if args and _is_const(args[0], int) else 1
            return _call("mousedown", _const({1: "left", 2: "right", 3: "middle"}.get(button, "left")))
        if name == "pygame.mouse.get_pressed":
            return ast.List(elts=[_call("mousedown", _const(b)) for b in ("left", "middle", "right")],
                            ctx=ast.Load())
        if name in ("love.graphics.getWidth", "windowWidth"):
            return _name("screen_width")
        if name in ("love.graphics.getHeight", "windowHeight"):
            return _name("screen_height")
        if name in ("pygame.Rect", "pygame.rect.Rect", "Rect"):
            values = args[0].elts if len(args) == 1 and isinstance(args[0], (ast.Tuple, ast.List)) else args
            if len(values) == 2 and all(isinstance(v, (ast.Tuple, ast.List)) for v in values):
                values = list(values[0].elts) + list(values[1].elts)
            if len(values) != 4:
                raise Unsupported("pygame.Rect needs x, y, width and height")
            return ast.Dict(keys=[_const(k) for k in ("x", "y", "w", "h")], values=[visit(v) for v in values])
        if name == "pygame.Color" and args:
            if len(args) == 1:
                return visit(args[0])
            return ast.List(elts=[visit(arg) for arg in args[:3]], ctx=ast.Load())
        if name in ("list", "Array.from") and len(args) <= 1:
            return visit(args[0]) if args else ast.List(elts=[], ctx=ast.Load())
        if name in ("dict",) and not args:
            return ast.Dict(keys=[], values=[])
        if name == "setmetatable" and args:
            return visit(args[0])
        if name == "__table":
            return ast.List(elts=[], ctx=ast.Load())
        if name == "__keys" and args:
            return _call("keys", visit(args[0])) if w.is_map(args[0]) else _call(
                "range", _call("len", visit(args[0])))
        if name in ("string.format",) and args and _is_const(args[0], str):
            return visit(_format_to_fstring(args[0].value, args[1:], "percent"))
        if name == "string.sub" and args:
            return self._lua_sub(visit(args[0]), [visit(arg) for arg in args[1:]])
        if name == "string.rep" and len(args) == 2:
            return ast.BinOp(left=visit(args[0]), op=ast.Mult(), right=visit(args[1]))
        if w.language == "python" and "." not in name and name not in w.functions:
            mapped = self._builtin_call(name, args, node)
            if mapped is not None:
                return mapped
        if name == "isinstance":
            raise Unsupported("isinstance() has no gublan version; use type(x) == \"number\"")
        if name in ("input", "prompt"):
            raise Unsupported("input() has to be on its own line: name = input(\"question\")")
        if name in ("Math.random",):
            return _call("random")
        return None


_FOLD_OPS = {
    ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b, ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b,
}


class _Folder(ast.NodeTransformer):
    """simplify the converted expression: 40 / 2 -> 20, x and true -> x, not false -> true."""

    def visit_BinOp(self, node):
        self.generic_visit(node)
        left, right = node.left, node.right
        operation = _FOLD_OPS.get(type(node.op))
        if operation and _is_const(left, int, float) and _is_const(right, int, float):
            try:
                value = operation(left.value, right.value)
            except (ZeroDivisionError, OverflowError):
                return node
            if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
                value = int(value)
            if isinstance(value, float) and len(repr(value)) > 12:
                return node
            return _const(value)
        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        operand = node.operand
        if isinstance(node.op, ast.Not):
            if _is_true(operand):
                return _name("false")
            if _is_false(operand):
                return _name("true")
        if isinstance(node.op, ast.USub) and _is_const(operand, int, float):
            return _const(-operand.value)
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        values = node.values
        if isinstance(node.op, ast.And):
            if any(_is_false(value) for value in values):
                return _name("false")
            values = [value for value in values if not _is_true(value)]
            if not values:
                return _name("true")
        else:
            if any(_is_true(value) for value in values):
                return _name("true")
            values = [value for value in values if not _is_false(value)]
            if not values:
                return _name("false")
        return values[0] if len(values) == 1 else ast.BoolOp(op=node.op, values=values)


try:  # python 3.14 keeps the unparser in its own module; older versions keep it inside ast
    from _ast_unparse import Unparser as _BaseUnparser, _Precedence
except ImportError:  # pragma: no cover - depends on the python version
    _BaseUnparser, _Precedence = getattr(ast, "_Unparser", None), getattr(ast, "_Precedence", None)
if _BaseUnparser is not None and _Precedence is not None:
    class _GublanUnparser(_BaseUnparser):
        """writes lambdas as arrows (x => x * 2, (a, b) => a + b), the way gublan's guide shows them."""

        def visit_Lambda(self, node):
            with self.require_parens(_Precedence.TEST, node):
                names = [arg.arg for arg in node.args.args]
                self.write(names[0] if len(names) == 1 else f"({', '.join(names)})")
                self.write(" => ")
                self.set_precedence(_Precedence.TEST, node.body)
                self.traverse(node.body)
else:  # pragma: no cover - older or newer pythons without the private unparser
    _GublanUnparser = None


def _plain_unparse(node):
    if _GublanUnparser is not None and any(isinstance(item, ast.Lambda) for item in ast.walk(node)):
        try:
            return _GublanUnparser().visit(node)
        except Exception:  # noqa: BLE001 - fall back to python's spelling, which gublan also reads
            pass
    return ast.unparse(node)


def _unparse(node):
    """ast.unparse, but text uses "double quotes" the way gublan examples do."""
    text = _plain_unparse(node)
    if "'" not in text:
        return text
    try:
        tokens = list(_pytokenize.generate_tokens(io.StringIO(text).readline))
    except (_pytokenize.TokenError, SyntaxError, IndentationError):
        return text
    replacements = []
    for token in tokens:
        if token.type == _pytokenize.STRING and token.string.startswith("'") and token.start[0] == token.end[0] == 1:
            try:
                value = ast.literal_eval(token.string)
            except (ValueError, SyntaxError):
                continue
            if isinstance(value, str) and '"' not in value and "\\" not in value and value.isprintable():
                replacements.append((token.start[1], token.end[1], f'"{value}"'))
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


class _TickRemover(ast.NodeTransformer):
    """clock.tick(60) -> clock.tick() so the frame rate is only set once (the fps line above it)."""

    def visit_Call(self, node):
        self.generic_visit(node)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "tick":
            node.args = []
        return node


class _Renamer(ast.NodeTransformer):
    def __init__(self, renames):
        self.renames = renames

    def visit_Name(self, node):
        if node.id in self.renames:
            return ast.copy_location(ast.Name(id=self.renames[node.id], ctx=node.ctx), node)
        return node


def _strip_ctx(node):
    node = copy.deepcopy(node)
    for item in ast.walk(node):
        if hasattr(item, "ctx"):
            item.ctx = ast.Load()
    return node


def _stored_names(node):
    names = set()
    for item in ast.walk(node):
        if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store):
            names.add(item.id)
    return names


# --------------------------------------------------------------------------
# writer: python ast -> gublan
# --------------------------------------------------------------------------

_QUOTED_RE = re.compile(r'"[^"]*"')
_TARGET_RE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\[[^\]]*\])")
_TOKEN_RE = re.compile(r"-?[A-Za-z_0-9.]+")
_DRAW_CALLS = {
    "pygame.draw.rect", "pygame.draw.circle", "pygame.draw.line", "pygame.draw.aaline", "pygame.draw.ellipse",
    "rect", "square", "ellipse", "circle", "line", "point", "text",
    "love.graphics.rectangle", "love.graphics.circle", "love.graphics.line", "love.graphics.print",
    "love.graphics.printf", "love.graphics.draw", "image",
}


class _Writer:
    def __init__(self, language, source):
        self.language = language
        self.source = source
        self.source_lines = source.split("\n")
        self.out = []
        self.notes = []
        self.todos = 0
        self.library = "none"
        self.aliases = {}
        self.modules = set()
        self.star_modules = set()
        self.star_names = {}
        self.functions = {}
        self.dotted_functions = {}
        self.signatures = {}
        self.variadic = {}  # gublan name -> (*args name, **kwargs name, how many plain parameters)
        self.parameters = set()  # every parameter name, so calling one (a function passed in) works
        self.key_maps = set()  # javascript maps filled by keydown and keyup listeners
        self.loop_conditional = set()  # requestAnimationFrame loops that can stop
        self.classes = {}
        self.methods = {}
        self.static_methods = {}
        self.assigned = set()
        self.renames = {}
        self.surfaces = {}
        self.keys_vars = set()
        self.screen_vars = set()
        self.canvas_vars = set()
        self.ctx_vars = set()
        self.map_names = set()
        self.event_var = None
        self.key_names = set()
        self.key_events = False
        self.current_class = None
        self.in_init = False
        self.counters = {}
        self.shape_names = {}
        self.used_shape_names = set()
        self.shape_index = 0
        self.temp_index = 0
        self.mode_emitted = False
        self.window = {}
        self.music_path = None
        self.text_size = None
        self.loop_functions = set()
        self.pending_functions = []
        self.defined_functions = set()
        self.function_depth = 0
        self.mapper = _ExprMapper(self)

    # bookkeeping -------------------------------------------------------
    def note(self, message):
        if message not in self.notes:
            self.notes.append(message)

    def emit(self, depth, text):
        if "\n" in text or "\r" in text:
            text = text.replace("\r", " ").replace("\n", " ")
        self.out.append(INDENT * depth + text)

    def temp(self, label="t"):
        self.temp_index += 1
        return f"_{label}{self.temp_index}"

    def variable(self, name):
        if "$" in name:
            return name.replace("$", "_s")
        return name

    def is_map(self, node):
        if isinstance(node, ast.Name):
            return node.id in self.map_names or node.id == "self"
        return False

    def dotted(self, node):
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            return None
        root = node.id
        if root in self.aliases:
            root = self.aliases[root]
        parts.append(root)
        return ".".join(reversed(parts))

    def original_text(self, node):
        if isinstance(node, Todo):
            return node.text
        start = getattr(node, "lineno", None)
        if start is None:
            try:
                return ast.unparse(node)
            except Exception:
                return type(node).__name__.lower()
        end = getattr(node, "end_lineno", None) or start
        lines = self.source_lines[start - 1:end]
        indent = min((len(line) - len(line.lstrip()) for line in lines if line.strip()), default=0)
        return "\n".join(line[indent:] for line in lines)

    def todo(self, node, depth, reason):
        text = self.original_text(node).rstrip()
        lines = [line for line in text.split("\n")] or [""]
        reason = reason.lower().rstrip(".")
        self.todos += 1
        self.emit(depth, f"// todo: {reason}")
        for line in lines[:400]:
            self.emit(depth, f"//   {line}" if line.strip() else "//")
        if len(lines) > 400:
            self.emit(depth, f"//   ... {len(lines) - 400} more lines")

    # expressions -------------------------------------------------------
    def expr(self, node, whole=False):
        mapped = self.mapper.visit(copy.deepcopy(node))
        mapped = self.fold(mapped)
        ast.fix_missing_locations(mapped)
        if whole:
            quoted = self.quoted_template(mapped)
            if quoted is not None:
                return quoted
        try:
            text = _unparse(mapped)
        except Exception as err:
            raise Unsupported("this expression has no gublan version") from err
        try:
            parse_expression(text)
        except (SyntaxError, ValueError) as err:
            raise Unsupported("this expression has no gublan version") from err
        if "\n" in text:
            raise Unsupported("multi-line text has no gublan version here")
        return text

    @staticmethod
    def fold(node):
        return _Folder().visit(node)

    def condition(self, node):
        """returns True, False or the condition text."""
        mapped = self.fold(self.mapper.visit(copy.deepcopy(node)))
        if _is_true(mapped):
            return True
        if _is_false(mapped):
            return False
        ast.fix_missing_locations(mapped)
        text = _unparse(mapped)
        try:
            parse_expression(text)
        except (SyntaxError, ValueError) as err:
            raise Unsupported("this condition has no gublan version") from err
        return text

    def token(self, node):
        """an argument for a gublan command: bare when simple, {expression} otherwise."""
        if _is_const(node, str):
            return self.quote(node.value)
        text = self.expr(node, whole=True)
        if _TOKEN_RE.fullmatch(text) or _QUOTED_RE.fullmatch(text):
            return text
        return "{" + text + "}"

    @staticmethod
    def quoted_template(node):
        """a whole value that is an f-string becomes gublan's "text {value}" form."""
        if _is_const(node, str) and "{" in node.value and '"' not in node.value and "\n" not in node.value:
            return f'"{node.value}" + ""'
        if not isinstance(node, ast.JoinedStr):
            return None
        text = ""
        for piece in node.values:
            if isinstance(piece, ast.Constant):
                chunk = str(piece.value)
                if any(char in chunk for char in '"{}\n'):
                    return None
                text += chunk
            else:
                inner = _unparse(piece.value)
                if any(char in inner for char in '"{}'):
                    return None
                text += "{" + inner + "}"
        return f'"{text}"'

    @staticmethod
    def quote(text):
        text = text.replace("\n", " ")
        if '"' not in text:
            return f'"{text}"'
        if "'" not in text:
            return f"'{text}'"
        return '"' + text.replace('"', "'") + '"'

    def template(self, nodes, depth):
        """build print/text content; returns (text, has_expressions)."""
        pieces = []
        dynamic = False
        for node in nodes:
            if _is_const(node, str):
                pieces.append(node.value)
            elif isinstance(node, ast.Constant) and not isinstance(node.value, str):
                pieces.append({True: "true", False: "false", None: "none"}.get(node.value, str(node.value))
                              if isinstance(node.value, bool) or node.value is None else str(node.value))
            elif isinstance(node, ast.JoinedStr) or (
                    isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and _is_const(node.left, str)) or (
                    isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and
                    node.func.attr == "format" and _is_const(node.func.value, str)) or (
                    isinstance(node, ast.Call) and self.dotted(node.func) == "string.format"):
                mapped = self.mapper.visit(copy.deepcopy(node))
                if not isinstance(mapped, ast.JoinedStr):
                    pieces.append("{" + self.interpolated(mapped, depth) + "}")
                    dynamic = True
                    continue
                text = ""
                for piece in mapped.values:
                    if isinstance(piece, ast.Constant):
                        text += str(piece.value)
                    else:
                        text += "{" + self.interpolated(piece.value, depth) + "}"
                        dynamic = True
                pieces.append(text)
            elif self.is_concat(node):
                text = ""
                for leaf in self.concat_leaves(node):
                    if _is_const(leaf, str):
                        text += leaf.value
                    else:
                        if isinstance(leaf, ast.Call) and isinstance(leaf.func, ast.Name) and                                 leaf.func.id in ("str", "String", "tostring") and len(leaf.args) == 1:
                            leaf = leaf.args[0]
                        piece, has = self.template([leaf], depth)
                        text += piece
                        dynamic = dynamic or has
                pieces.append(text)
            else:
                pieces.append("{" + self.interpolated(node, depth, mapped=False) + "}")
                dynamic = True
        return " ".join(pieces), dynamic

    @staticmethod
    def is_concat(node):
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)):
            return False
        if getattr(node, "_concat", False):
            return True
        leftmost = node
        while isinstance(leftmost, ast.BinOp) and isinstance(leftmost.op, ast.Add):
            leftmost = leftmost.left
        return _is_const(leftmost, str) or isinstance(leftmost, ast.JoinedStr)

    def concat_leaves(self, node):
        if self.is_concat(node):
            return self.concat_leaves(node.left) + self.concat_leaves(node.right)
        return [node]

    def interpolated(self, node, depth, mapped=True):
        if mapped:
            mapped_node = self.fold(node)
            ast.fix_missing_locations(mapped_node)
            text = _unparse(mapped_node)
            try:
                parse_expression(text)
            except (SyntaxError, ValueError) as err:
                raise Unsupported("this expression has no gublan version") from err
        else:
            text = self.expr(node)
        if "{" in text or "}" in text:
            temp = self.temp("text")
            self.emit(depth, f"{temp} = {text}")
            return temp
        return text

    def emit_print(self, nodes, depth, command="print"):
        text, dynamic = self.template(nodes, depth)
        lines = text.split("\n") if text else [""]
        for line in lines:
            if dynamic and "{" in line:
                self.emit(depth, f"{command} {line}")
            else:
                self.emit(depth, f"{command} {self.quote(line)}")

    def color_tokens(self, args, scale=False):
        if not args:
            raise Unsupported("this color has no value")
        if len(args) == 1:
            node = args[0]
            if _is_const(node, str):
                text = node.value.strip()
                match = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+).*\)", text)
                if match:
                    return list(match.groups())
                if is_color(text):
                    return [text.lower()]
                if is_color(text.replace(" ", "")):
                    return [text.replace(" ", "").lower()]
                self.note(f"the color '{text}' is not a gublan color, so white is used")
                return ["white"]
            if isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) in (3, 4):
                return self.color_tokens(node.elts[:3], scale)
            if _is_const(node, int, float):
                return [self.channel(node, scale)] * 3
            if isinstance(node, ast.Call) and self.dotted(node.func) == "color" and self.library == "p5":
                return self.color_tokens(node.args)
            return [self.token(node)]
        if len(args) in (3, 4):
            return [self.channel(arg, scale) for arg in args[:3]]
        if len(args) == 2:
            return [self.channel(args[0], scale)] * 3
        raise Unsupported("this color has no gublan version")

    def channel(self, node, scale):
        if scale:
            if _is_const(node, int, float):
                value = node.value
                return str(int(round(value * 255))) if value <= 1 else str(int(value))
            return "{round(" + self.expr(node) + " * 255)}"
        if _is_const(node, int, float):
            return str(int(node.value))
        return self.token(node)

    # shapes --------------------------------------------------------------
    def shape_name(self, call, hint=None):
        key = id(call)
        if key in self.counters:
            base, counter = self.counters[key]
            return f"{base}_{{{counter}}}", counter
        if key not in self.shape_names:
            if hint:
                base = re.sub(r"\W", "_", hint)
                name = base if base.endswith(("_shape", "_label", "_image")) else base
            else:
                self.shape_index += 1
                name = f"shape{self.shape_index}"
            unique = name
            index = 2
            while unique in self.used_shape_names:
                unique = f"{name}{index}"
                index += 1
            self.used_shape_names.add(unique)
            self.shape_names[key] = unique
        return self.shape_names[key], None

    def ensure_mode(self, depth):
        if not self.mode_emitted:
            self.mode_emitted = True
            self.emit(depth, "mode 2d")

    def emit_shape(self, call, depth, kind, tokens, color=None, hint=None):
        name, counter = self.shape_name(call, hint)
        if color:
            self.emit(depth, "color " + " ".join(color))
        self.emit(depth, f"{kind} {name} " + " ".join(tokens))
        if counter:
            self.emit(depth, f"{counter} += 1")

    def hint_for(self, node, suffix):
        if isinstance(node, ast.Name):
            base = node.id
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            base = f"{node.value.id}_{node.attr}"
        else:
            return None
        known = ("label", "text", "image", "img", "shape", "rect", "sprite", "pic", "surface", "surf")
        if base.lower().endswith(known):
            return base
        return base + suffix

    def rect_tokens(self, node):
        if isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) == 4:
            return [self.token(item) for item in node.elts]
        if isinstance(node, ast.Call) and self.dotted(node.func) in ("pygame.Rect", "pygame.rect.Rect", "Rect"):
            values = node.args
            if len(values) == 4:
                return [self.token(item) for item in values]
        text = self.expr(node)
        return ["{" + f"{text}.{field}" + "}" if not re.fullmatch(r"\w+", text) else f"{text}.{field}"
                for field in ("x", "y", "w", "h")]

    def point_tokens(self, node):
        if isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) >= 2:
            return [self.token(node.elts[0]), self.token(node.elts[1])]
        text = self.expr(node)
        return ["{" + text + "[0]}", "{" + text + "[1]}"]

    # prescan -----------------------------------------------------------
    def prescan(self, body):
        module = ast.Module(body=body, type_ignores=[])
        top_names = {node.name for node in body if isinstance(node, ast.FunctionDef)}
        self.scope_of = {}
        self.name_scopes = {}
        scopes = []
        for node in body:
            if isinstance(node, ast.FunctionDef):
                scopes.append((node.name, node))
            elif isinstance(node, ast.ClassDef):
                scopes.extend((f"{node.name}.{item.name}", item) for item in node.body
                              if isinstance(item, ast.FunctionDef))
            else:
                scopes.append(("<top>", node))
        for scope, node in scopes:
            if isinstance(node, ast.FunctionDef):
                self.scope_of[id(node)] = scope
            for item in ast.walk(node):
                if isinstance(item, ast.Name):
                    self.name_scopes.setdefault(item.id, set()).add(scope)
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    self.aliases[alias.asname or root] = alias.name if alias.asname else root
                    self.modules.add(alias.asname or root)
                    self.modules.add(root)
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                self.modules.add(root)
                for alias in node.names:
                    if alias.name == "*":
                        self.star_modules.add(node.module)
                    else:
                        self.aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
            elif isinstance(node, ast.FunctionDef):
                dotted = getattr(node, "_dotted", None)
                if dotted and "." in dotted and not getattr(node, "_method", False):
                    self.dotted_functions[dotted] = node.name
                if getattr(node, "_method", False):
                    owner = node._owner
                    method = dotted.split(".")[-1]
                    self.classes.setdefault(owner, {"init": False, "methods": set(), "lua": True})
                    self.classes[owner]["methods"].add(method)
                    self.methods.setdefault(method, set()).add(owner)
            elif isinstance(node, ast.ClassDef):
                methods = {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
                self.classes[node.name] = {"init": "__init__" in methods or any(
                    isinstance(item, (ast.Assign, ast.AnnAssign)) for item in node.body), "methods": methods}
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name != "__init__":
                        self.methods.setdefault(item.name, set()).add(node.name)
                        decorators = {self.dotted(dec) for dec in item.decorator_list
                                      if isinstance(dec, (ast.Name, ast.Attribute))}
                        params = [arg.arg for arg in item.args.args]
                        if decorators & {"staticmethod", "classmethod"} or not params or params[0] not in (
                                "self", "cls"):
                            self.static_methods[(node.name, item.name)] = True
            elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for item in ast.walk(target):
                        if isinstance(item, ast.Name):
                            self.assigned.add(item.id)
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                        self.map_names.add(target.value.id)
                    if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and \
                            _is_const(target.slice, str):
                        self.map_names.add(target.value.id)
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            self.map_names.add(target.id)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__pairs" \
                    and node.args and isinstance(node.args[0], ast.Name):
                self.map_names.add(node.args[0].id)
        for node in ast.walk(module):
            if isinstance(node, ast.FunctionDef) and not getattr(node, "_method", False):
                self.functions.setdefault(node.name, node.name)
        for name in list(self.functions):
            if name in RESERVED_FIRST or name in ("true", "false", "none", "pi", "dt", "result"):
                self.functions[name] = f"{name}_fn"
                self.renames[name] = f"{name}_fn"
            elif "$" in name:
                self.functions[name] = name.replace("$", "_s")
        for module_name in self.star_modules:
            if module_name.startswith("pygame"):
                for event in list(PYGAME_EVENTS_FALSE) + ["KEYDOWN", "MOUSEBUTTONDOWN"]:
                    self.star_names[event] = (lambda e=event: ast.Attribute(value=_name("pygame"), attr=e,
                                                                            ctx=ast.Load()))
        if any(module_name.startswith("pygame") for module_name in self.star_modules):
            self.aliases.setdefault("pygame", "pygame")
            self.modules.add("pygame")
        calls = {self.dotted(node.func) for node in ast.walk(module)
                 if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))}
        if self.language == "python" and "pygame" in self.modules:
            self.library = "pygame"
        elif self.language == "javascript":
            canvas = any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                         and node.func.attr == "getContext" for node in ast.walk(module))
            if "createCanvas" in calls or (top_names & {"setup", "draw"} and not canvas):
                self.library = "p5"
            elif canvas:
                self.library = "canvas"
        elif self.language == "lua" and (any(call and call.startswith("love.") for call in calls) or any(
                name.startswith("love_") for name in self.functions)):
            self.library = "love"
            self.modules.add("love")
        if self.language == "lua":
            self.modules.update({"math", "string", "table", "os"})
        if self.language == "javascript":
            self.modules.update({"Math", "console", "document", "window", "JSON", "Object"})
        for node in ast.walk(module):
            if isinstance(node, ast.FunctionDef):
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Call) and self.dotted(inner.func) == "requestAnimationFrame" and \
                            inner.args and isinstance(inner.args[0], ast.Name) and inner.args[0].id == node.name:
                        self.loop_functions.add(node.name)
                        if not any(isinstance(statement, ast.Expr) and statement.value is inner
                                   for statement in node.body):
                            # only asks for the next frame sometimes (inside an if): the loop stops when it doesn't
                            self.loop_conditional.add(node.name)
        for node in ast.walk(module):
            if isinstance(node, ast.Call):
                held = _key_state_map(node)
                if held:
                    self.key_maps.add(held)
            if isinstance(node, (ast.FunctionDef, ast.Lambda)):
                self.parameters.update(arg.arg for arg in _all_params(node.args))
            if isinstance(node, ast.FunctionDef):
                params = [arg.arg for arg in _all_params(node.args)]
                default_map = _default_map(node.args)
                default_map = {key: value for key, value in default_map.items()
                               if not (isinstance(value, ast.Constant) and value.value is None and
                                       self.language == "javascript")}
                gublan_name = self.functions.get(node.name, node.name)
                self.signatures.setdefault(gublan_name, (params, default_map))
                if _is_variadic(node.args):
                    self.variadic.setdefault(gublan_name, _variadic_info(node.args))
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        params = [arg.arg for arg in _all_params(item.args)]
                        default_map = _default_map(item.args)
                        self.signatures[f"{node.name}_{item.name}"] = (params, default_map)
                        if _is_variadic(item.args):
                            self.variadic[f"{node.name}_{item.name}"] = _variadic_info(item.args)

    # layout ----------------------------------------------------------------
    def layout(self, body):
        top = {node.name: node for node in body if isinstance(node, ast.FunctionDef)}
        if self.library == "p5" and ("draw" in top or "setup" in top):
            handlers = {"keyPressed", "keyReleased", "keyTyped", "mousePressed", "mouseClicked", "mouseReleased",
                        "windowResized", "mouseDragged", "mouseMoved", "mouseWheel"}
            out = [node for node in body]
            loop = []
            if "preload" in top:
                out.append(_expr_stmt(_call(self.functions["preload"])))
            creates_canvas = any(isinstance(n, ast.Call) and self.dotted(n.func) == "createCanvas"
                                 for n in ast.walk(top.get("setup", ast.Pass())))
            if not creates_canvas:
                out.append(Raw(text="mode 2d"))
                self.mode_emitted = True
            if "setup" in top:
                out.append(_expr_stmt(_call(self.functions["setup"])))
            if "draw" in top:
                loop.append(_expr_stmt(_call(self.functions["draw"])))
            for name in ("keyPressed", "keyTyped"):
                if name in top:
                    loop.append(_expr_stmt(_call(self.functions[name])))
                    top[name]._key_handler = {"key", "keyCode"}
            for name in ("mousePressed", "mouseClicked"):
                if name in top:
                    loop.append(ast.If(test=_call("mousepressed", _const("left")),
                                       body=[_expr_stmt(_call(self.functions[name]))], orelse=[]))
            for name in handlers - {"keyPressed", "keyTyped", "mousePressed", "mouseClicked"}:
                if name in top:
                    self.note(f"p5 runs {name}() by itself; gublan does not, so it is never called")
            if loop:
                out.append(Comment(text="the game loop: p5 calls draw() every frame"))
                out.append(ast.While(test=_const(True), body=loop + [Raw(text="frame")], orelse=[]))
            return out
        if self.library == "love":
            names = {node.name for node in body if isinstance(node, ast.FunctionDef)}
            out = list(body)
            out.append(Raw(text="mode 2d"))
            self.mode_emitted = True
            if "love_load" in names:
                out.append(_expr_stmt(_call("love_load")))
            loop = []
            out.append(Raw(text="dt = 0"))
            if "love_update" in names:
                update = top["love_update"]
                args = [_name("dt")] if update.args.args else []
                loop.append(_expr_stmt(ast.Call(func=_name("love_update"), args=args, keywords=[])))
            if "love_draw" in names:
                loop.append(_expr_stmt(_call("love_draw")))
            if "love_keypressed" in names:
                handler = top["love_keypressed"]
                params = [arg.arg for arg in handler.args.args]
                if params:
                    handler._key_handler = {params[0]}
                    handler.args.args = []
                loop.append(_expr_stmt(_call("love_keypressed")))
            if "love_mousepressed" in names:
                handler = top["love_mousepressed"]
                count = len(handler.args.args)
                args = [_call("mousex"), _call("mousey"), _const(1)][:count]
                loop.append(ast.If(test=_call("mousepressed", _const("left")),
                                   body=[_expr_stmt(ast.Call(func=_name("love_mousepressed"), args=args,
                                                             keywords=[]))], orelse=[]))
            for name in names:
                if name.startswith("love_") and name not in ("love_load", "love_update", "love_draw",
                                                             "love_keypressed", "love_mousepressed"):
                    self.note(f"love runs {name.replace('_', '.', 1)}() by itself; gublan does not, so it is "
                              "never called")
            if loop:
                out.append(Comment(text="the game loop: love calls update and draw every frame"))
                out.append(ast.While(test=_const(True), body=loop + [Raw(text="frame")], orelse=[]))
            return out
        return body

    # statements ------------------------------------------------------------
    def write(self, body):
        self.prescan(body)
        program = self.layout(body)
        for node in program:
            self.stmt(node, 0)
        while self.pending_functions:
            self.stmt(self.pending_functions.pop(0), 0, hoisted=True)
        lines = self.safety_net(self.out)
        header = [f"// converted from {self.language} by the gublan converter"]
        if self.library != "none":
            header.append(f"// game library: {self.library}")
        if self.notes:
            header.append("// notes:")
            header.extend(f"// - {note}" for note in self.notes)
        if self.todos:
            header.append(f"// {self.todos} part(s) need a look: search for 'todo'")
        return "\n".join(header + [""] + lines).rstrip() + "\n"

    def safety_net(self, lines):
        structural = re.compile(r"^\s*(if|elseif|else|end|loop|forever|while|for|function)\b")
        for _ in range(3):
            problems = {item["line"]: item["message"] for item in analyze_source("\n".join(lines))}
            fixed = False
            for line_number, message in problems.items():
                index = line_number - 1
                if 0 <= index < len(lines) and not structural.match(lines[index]) and \
                        not lines[index].lstrip().startswith("//"):
                    indent = lines[index][:len(lines[index]) - len(lines[index].lstrip())]
                    lines[index] = f"{indent}// todo: {message.lower()}: {lines[index].strip()}"
                    self.todos += 1
                    fixed = True
            if not fixed:
                break
        return lines

    def stmt(self, node, depth, hoisted=False):
        mark = len(self.out)
        handler = getattr(self, "s_" + type(node).__name__, None)
        try:
            if handler is None:
                raise Unsupported(f"{type(node).__name__.lower()} statements have no gublan version")
            if isinstance(node, ast.FunctionDef):
                handler(node, depth, hoisted=hoisted)
            else:
                handler(node, depth)
        except Unsupported as err:
            del self.out[mark:]
            self.todo(node, depth, str(err))
        except RecursionError:
            del self.out[mark:]
            self.todo(node, depth, "this part is nested too deeply to convert")
        except Exception as err:  # noqa: BLE001 - one odd statement must never stop the whole file
            del self.out[mark:]
            self.todo(node, depth, f"the converter could not read this part ({type(err).__name__.lower()})")

    def body(self, statements, depth):
        for node in statements:
            self.stmt(node, depth)

    def s_Todo(self, node, depth):
        self.todo(node, depth, node.reason)

    def s_Comment(self, node, depth):
        self.emit(depth, f"// {node.text}")

    def s_Raw(self, node, depth):
        if node.text == "mode 2d":
            self.mode_emitted = True
        self.emit(depth, node.text)

    def s_Pass(self, node, depth):
        pass

    def s_Import(self, node, depth):
        pass

    s_ImportFrom = s_Import

    def s_Global(self, node, depth):
        pass

    s_Nonlocal = s_Global

    def s_Expr(self, node, depth):
        value = node.value
        if _is_const(value, str):
            for line in value.value.strip().split("\n"):
                self.emit(depth, f"// {line.strip()}" if line.strip() else "//")
            return
        if isinstance(value, ast.Call):
            self.call_statement(value, depth)
            return
        if isinstance(value, ArrowFunction):
            return
        if isinstance(value, (ast.Constant, ast.Name)):
            return
        if isinstance(value, (ast.Yield, ast.YieldFrom)):
            raise Unsupported("yield (generator functions) has no gublan version; build a list and return it")
        if isinstance(value, ast.Await) and isinstance(value.value, ast.Call):
            self.call_statement(value.value, depth)
            return
        if isinstance(value, (ast.ListComp, ast.SetComp, ast.GeneratorExp)) and len(value.generators) == 1 and \
                not value.generators[0].is_async:
            # [draw(x) for x in things] used only for what it does: a for loop
            generator = value.generators[0]
            inner = [ast.Expr(value=value.elt)]
            for test in reversed(generator.ifs):
                inner = [ast.If(test=test, body=inner, orelse=[])]
            self.stmt(ast.For(target=generator.target, iter=generator.iter, body=inner, orelse=[],
                              lineno=getattr(node, "lineno", None)), depth)
            return
        if isinstance(value, ast.BoolOp) and len(value.values) == 2 and isinstance(value.values[1], ast.Call):
            # ready and start()  /  done or finish()
            test = value.values[0] if isinstance(value.op, ast.And) else ast.UnaryOp(op=ast.Not(),
                                                                                    operand=value.values[0])
            self.stmt(ast.If(test=test, body=[ast.Expr(value=value.values[1])], orelse=[],
                             lineno=getattr(node, "lineno", None)), depth)
            return
        if isinstance(value, ast.IfExp) and isinstance(value.body, ast.Call) and isinstance(value.orelse, ast.Call):
            self.stmt(ast.If(test=value.test, body=[ast.Expr(value=value.body)],
                             orelse=[ast.Expr(value=value.orelse)], lineno=getattr(node, "lineno", None)), depth)
            return
        if not any(isinstance(item, (ast.Call, ast.Yield, ast.YieldFrom, ast.Await, ast.NamedExpr))
                   for item in ast.walk(value)):
            self.note("lines that only worked out a value (and did nothing with it) were left out")
            return
        raise Unsupported("this line only works out a value and does nothing with it")

    def s_FunctionDef(self, node, depth, hoisted=False, name=None, method_of=None):
        if depth > 0 and not hoisted:
            self.pending_functions.append(node)
            self.note("functions defined inside other blocks were moved to the end of the file")
            return
        gublan_name = name or self.functions.get(node.name, node.name)
        if gublan_name in self.defined_functions:
            raise Unsupported(f"a function called {gublan_name} was already made earlier; gublan needs a "
                              "different name for each function")
        args = node.args
        params = [self.variable(arg.arg) for arg in _all_params(args)]
        if args.vararg:
            self.note(f"*{args.vararg.arg} became a list parameter called {args.vararg.arg}")
        if args.kwarg:
            self.note(f"**{args.kwarg.arg} became a map parameter called {args.kwarg.arg}")
        if node.decorator_list:
            self.note("decorators like @property were removed")
        previous = (self.current_class, self.in_init, self.key_names, self.key_events)
        self.current_class = method_of or getattr(node, "_owner", None) if (
            method_of or getattr(node, "_method", False)) else self.current_class
        self.in_init = node.name == "__init__" and method_of is not None
        handler_keys = getattr(node, "_key_handler", None)
        if handler_keys:
            self.key_names = set(handler_keys)
            self.key_events = True
        elif self.library == "p5":
            self.key_names = {"key", "keyCode"}
            self.key_events = False
        self.defined_functions.add(gublan_name)
        renames = self.check_locals(node, gublan_name, params) if self.function_depth == 0 else {}
        self.emit(depth, "function " + " ".join([gublan_name] + params))
        self.function_depth += 1
        try:
            statements = node.body
            if renames:
                statements = [_Renamer(renames).visit(copy.deepcopy(item)) for item in statements]
            self.body(statements, depth + 1)
            if self.in_init:
                self.emit(depth + 1, "return self")
        finally:
            self.function_depth -= 1
            self.current_class, self.in_init, self.key_names, self.key_events = previous
        self.emit(depth, "end")

    def check_locals(self, node, gublan_name, params):
        """rename variables that were local in the original but share a name with one outside.

        gublan only keeps parameters local, so without this a helper could overwrite the
        caller's variable of the same name.
        """
        scope = self.scope_of.get(id(node))
        if scope is None:
            return {}
        if self.language == "python":
            declared_global = {name for item in ast.walk(node) if isinstance(item, (ast.Global, ast.Nonlocal))
                               for name in item.names}
            local = set()
            for item in ast.walk(node):
                if isinstance(item, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                    targets = item.targets if isinstance(item, ast.Assign) else [item.target]
                    local.update(target.id for target in targets if isinstance(target, ast.Name))
            local -= declared_global
        else:
            local = {target.id for item in ast.walk(node) if isinstance(item, ast.Assign)
                     and getattr(item, "_declared", False) for target in item.targets
                     if isinstance(target, ast.Name)}
        local -= set(params)
        clashes = sorted(name for name in local if self.name_scopes.get(name, set()) - {scope})
        renames = {}
        for name in clashes:
            new = f"{gublan_name}_{name}"
            while new in self.name_scopes:
                new += "_"
            renames[name] = new
            self.name_scopes[new] = {scope}
            if name in self.map_names or name == "self":
                self.map_names.add(new)
        if renames:
            listed = ", ".join(f"{old} -> {new}" for old, new in list(renames.items())[:6])
            self.note(f"local variables in {gublan_name} were renamed so they can't clash with the rest of the "
                      f"program ({listed})")
        return renames

    s_AsyncFunctionDef = s_FunctionDef

    def s_ClassDef(self, node, depth):
        if depth > 0:
            raise Unsupported("classes inside other blocks have no gublan version")
        if node.bases:
            names = ", ".join(ast.unparse(base) for base in node.bases)
            if names not in ("object",):
                self.note(f"class {node.name} inherits from {names}; inherited methods were not copied")
        self.emit(depth, f"// class {node.name}: objects are maps, methods are functions named {node.name}_method")
        fields = [item for item in node.body if isinstance(item, (ast.Assign, ast.AnnAssign))]
        init = next((item for item in node.body if isinstance(item, ast.FunctionDef) and item.name == "__init__"),
                    None)
        if fields and init is None:
            init = _func("__init__", ["self"], [])
        if init is not None and fields:
            moved = []
            for field in fields:
                target = field.targets[0] if isinstance(field, ast.Assign) else field.target
                value = field.value if field.value is not None else _const(None)
                if isinstance(target, ast.Name):
                    moved.append(_assign(ast.Attribute(value=_name("self"), attr=target.id, ctx=ast.Store()), value))
            init.body = moved + list(init.body)
        methods = [item for item in node.body if isinstance(item, ast.FunctionDef) and item is not init]
        if init is not None:
            self.stmt_function(init, depth, f"{node.name}__init__", node.name)
        for method in methods:
            self.stmt_function(method, depth, f"{node.name}_{method.name}", node.name)
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.Assign, ast.AnnAssign, ast.Pass, ast.Expr)):
                self.todo(item, depth, "this part of the class has no gublan version")

    def stmt_function(self, node, depth, name, owner):
        mark = len(self.out)
        try:
            self.s_FunctionDef(node, depth, hoisted=True, name=name, method_of=owner)
        except Unsupported as err:
            del self.out[mark:]
            self.todo(node, depth, str(err))

    def s_Return(self, node, depth):
        if self.in_init:
            self.emit(depth, "return self")
            return
        if node.value is None:
            self.emit(depth, "return")
            return
        self.emit(depth, f"return {self.expr(node.value, whole=True)}")

    def assign_text(self, target, value_text, depth):
        if isinstance(target, ast.Name):
            name = self.variable(target.id)
            line = f"set {name} = {value_text}" if name in RESERVED_FIRST else f"{name} = {value_text}"
            self.emit(depth, line)
            return
        if isinstance(target, (ast.Attribute, ast.Subscript)):
            load = copy.deepcopy(target)
            load.ctx = ast.Load()
            text = self.expr(load)
            if _TARGET_RE.fullmatch(text):
                head = re.match(r"\w+", text).group(0)
                self.emit(depth, f"set {text} = {value_text}" if head in RESERVED_FIRST else f"{text} = {value_text}")
                return
            if isinstance(load, (ast.Attribute, ast.Subscript)):
                temp = self.temp()
                base = load.value
                self.emit(depth, f"{temp} = {self.expr(base)}")
                load.value = _name(temp)
                if self.language == "lua" and isinstance(load, ast.Subscript):
                    if self.is_map(base):
                        self.map_names.add(temp)
                text = self.expr(load)
                if _TARGET_RE.fullmatch(text):
                    self.emit(depth, f"{text} = {value_text}")
                    return
        raise Unsupported("this kind of assignment has no gublan version")

    def s_Assign(self, node, depth):
        value = node.value
        targets = node.targets
        ticks = [item for item in ast.walk(value) if isinstance(item, ast.Call) and
                 isinstance(item.func, ast.Attribute) and item.func.attr == "tick" and len(item.args) == 1]
        if ticks and self.library == "pygame":
            # dt = clock.tick(60) / 1000: gublan keeps the frame rate with fps and gives dt by itself
            self.emit(depth, f"fps {self.token(ticks[0].args[0])}")
            if len(targets) == 1 and isinstance(targets[0], ast.Name) and targets[0].id == "dt":
                self.note("clock.tick() became fps, and gublan's own dt")
                return
            node = ast.Assign(targets=targets, value=_TickRemover().visit(copy.deepcopy(value)),
                              lineno=getattr(node, "lineno", None))
            value = node.value
        if len(targets) > 1:
            first = targets[0]
            self.s_Assign(_assign(first, value), depth)
            for other in targets[1:]:
                self.s_Assign(_assign(other, copy.deepcopy(first)), depth)
            return
        target = targets[0]
        if isinstance(value, ArrowFunction) and isinstance(target, ast.Name):
            function = _func(target.id, value.params, value.body)
            function.lineno = getattr(node, "lineno", None)
            self.functions.setdefault(target.id, target.id)
            self.s_FunctionDef(function, depth, hoisted=depth == 0)
            return
        if isinstance(value, ArrowFunction):
            raise Unsupported("functions stored inside objects have no gublan version")
        if self.special_assign(target, value, depth):
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            self.unpack(target.elts, value, depth)
            return
        while isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and                 value.func.id == "setmetatable" and value.args:
            value = value.args[0]
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "__table":
            empty = "{}" if self.is_map(target) or (isinstance(target, ast.Name) and target.id in
                                                     self.map_names) else "[]"
            self.assign_text(target, empty, depth)
            return
        if self.is_self_update(target, value):
            self.s_AugAssign(ast.AugAssign(target=target, op=value.op, value=value.right), depth)
            return
        self.assign_text(target, self.expr(value, whole=True), depth)

    def is_self_update(self, target, value):
        """x = x + 1 -> x += 1, but only when it can't be list joining (l = l + [4] must stay)."""
        if not (isinstance(value, ast.BinOp) and isinstance(value.op, (ast.Add, ast.Sub, ast.Mult, ast.Div))):
            return False
        if getattr(value, "_concat", False) or not isinstance(target, (ast.Name, ast.Attribute, ast.Subscript)):
            return False
        try:
            same = ast.dump(_strip_ctx(target)) == ast.dump(_strip_ctx(value.left))
        except Exception:
            return False
        if not same:
            return False
        if self.language == "lua" or not isinstance(value.op, ast.Add):
            return True
        return _is_const(value.right, int, float)

    def unpack(self, targets, value, depth):
        names = {item.id for target in targets for item in ast.walk(target) if isinstance(item, ast.Name)}
        if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(targets):
            used = {item.id for element in value.elts for item in ast.walk(element) if isinstance(item, ast.Name)}
            if not (names & used):
                for target, element in zip(targets, value.elts):
                    self.s_Assign(_assign(target, element), depth)
                return
        temp = self.temp()
        self.emit(depth, f"{temp} = {self.expr(value)}")
        for index, target in enumerate(targets):
            if isinstance(target, ast.Starred):
                raise Unsupported("* unpacking has no gublan version")
            self.assign_text(target, f"{temp}[{index}]", depth)

    def s_AugAssign(self, node, depth):
        target = node.target
        commands = {ast.Add: ("+=", "add"), ast.Sub: ("-=", "sub"), ast.Mult: ("*=", "mul"), ast.Div: ("/=", "div")}
        if isinstance(target, ast.Name) and type(node.op) in commands:
            name = self.variable(target.id)
            symbol, command = commands[type(node.op)]
            value = self.expr(node.value)
            if name in RESERVED_FIRST:
                self.emit(depth, f"{command} {name} {value}")
            else:
                self.emit(depth, f"{name} {symbol} {value}")
            return
        load = copy.deepcopy(target)
        load.ctx = ast.Load()
        if type(node.op) in commands and isinstance(target, (ast.Attribute, ast.Subscript)):
            text = self.expr(load)
            head = re.match(r"\w+", text)
            if _TARGET_RE.fullmatch(text) and head and head.group(0) not in RESERVED_FIRST:
                self.emit(depth, f"{text} {commands[type(node.op)][0]} {self.expr(node.value)}")
                return
        combined = ast.BinOp(left=load, op=node.op, right=node.value)
        self.assign_text(target, self.expr(combined), depth)

    def s_AnnAssign(self, node, depth):
        if node.value is not None:
            self.s_Assign(_assign(node.target, node.value), depth)

    def s_Delete(self, node, depth):
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.emit(depth, f"delete {target.id}")
            elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
                index = self.expr(target.slice)
                if not _TOKEN_RE.fullmatch(index):
                    temp = self.temp("i")
                    self.emit(depth, f"{temp} = {index}")
                    index = temp
                self.emit(depth, f"delete {target.value.id} {index}")
            else:
                raise Unsupported("this delete has no gublan version")

    def s_If(self, node, depth):
        test = node.test
        if isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "__name__":
            self.body(node.body, depth)
            return
        condition = self.condition(test)
        if condition is True:
            self.body(node.body, depth)
            return
        if condition is False:
            self.body(node.orelse, depth)
            return
        self.emit(depth, f"if {condition}")
        self.body(node.body, depth + 1)
        orelse = node.orelse
        while orelse:
            if len(orelse) == 1 and isinstance(orelse[0], ast.If):
                branch = orelse[0]
                result = self.condition(branch.test)
                if result is True:
                    self.emit(depth, "else")
                    self.body(branch.body, depth + 1)
                    break
                if result is False:
                    orelse = branch.orelse
                    continue
                self.emit(depth, f"elseif {result}")
                self.body(branch.body, depth + 1)
                orelse = branch.orelse
                continue
            self.emit(depth, "else")
            self.body(orelse, depth + 1)
            break
        self.emit(depth, "end")

    def is_game_loop(self, statements):
        for node in statements:
            for inner in ast.walk(node):
                if isinstance(inner, Raw) and inner.text == "frame":
                    return True
                if isinstance(inner, ast.Call):
                    name = self.dotted(inner.func) if isinstance(inner.func, (ast.Name, ast.Attribute)) else None
                    if name in ("pygame.display.flip", "pygame.display.update", "requestAnimationFrame"):
                        return True
                    if isinstance(inner.func, ast.Attribute) and inner.func.attr == "tick":
                        return True
        return False

    def draw_calls(self, statements):
        found = []
        for node in statements:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and isinstance(inner.func, (ast.Name, ast.Attribute)):
                    name = self.dotted(inner.func)
                    attr = inner.func.attr if isinstance(inner.func, ast.Attribute) else None
                    if name in _DRAW_CALLS or attr in ("blit", "fillRect", "fillText", "drawImage", "strokeRect",
                                                       "arc"):
                        found.append(inner)
        return found

    def loop_with_counters(self, statements, depth, emit_loop):
        allocated = []
        if not self.counters and not self.is_game_loop(statements):
            for call in self.draw_calls(statements):
                self.shape_index += 1
                base = f"shape{self.shape_index}"
                counter = f"_n{self.shape_index}"
                self.counters[id(call)] = (base, counter)
                allocated.append((base, counter, call))
        for _, counter, _ in allocated:
            self.emit(depth, f"{counter} = 0")
        try:
            emit_loop()
        finally:
            for _, _, call in allocated:
                self.counters.pop(id(call), None)
        for base, counter, _ in allocated:
            spare = counter.replace("_n", "_k")
            self.emit(depth, f"{spare} = {counter}")
            self.emit(depth, f"while exists(\"{base}_\" + str({spare}))")
            self.emit(depth + 1, f"delete {base}_{{{spare}}}")
            self.emit(depth + 1, f"{spare} += 1")
            self.emit(depth, "end")

    def s_While(self, node, depth):
        if node.orelse:
            raise Unsupported("while ... else has no gublan version")
        condition = self.condition(node.test)
        if condition is False:
            return

        def emit_loop():
            self.emit(depth, "forever" if condition is True else f"while {condition}")
            self.body(node.body, depth + 1)
            self.emit(depth, "end")

        self.loop_with_counters(node.body, depth, emit_loop)

    def s_For(self, node, depth):
        if node.orelse:
            raise Unsupported("for ... else has no gublan version")
        iterator = node.iter
        target = node.target
        name = self.dotted(iterator.func) if isinstance(iterator, ast.Call) and isinstance(
            iterator.func, (ast.Name, ast.Attribute)) else None
        if name == "pygame.event.get":
            if not isinstance(target, ast.Name):
                raise Unsupported("this event loop has no gublan version")
            previous = (self.event_var, self.key_events)
            self.event_var = target.id
            self.key_events = True
            try:
                self.body(node.body, depth)
            finally:
                self.event_var, self.key_events = previous
            return
        prefix = []
        header = None
        before = []
        if name == "__inclusive_range" and isinstance(target, ast.Name):
            start, end, step = iterator.args
            header = f"for {target.id} = {self.expr(start)} to {self.expr(end)}"
            if not (_is_const(step, int) and step.value == 1):
                header += f" step {self.expr(step)}"
        elif name == "range" and isinstance(target, ast.Name) and 1 <= len(iterator.args) <= 3 and \
                not iterator.keywords:
            args = iterator.args
            start = args[0] if len(args) > 1 else _const(0)
            stop = args[1] if len(args) > 1 else args[0]
            step = args[2] if len(args) == 3 else _const(1)
            if _is_const(step, int) and step.value != 0:
                end = _minus(stop, 1 if step.value > 0 else -1)
                header = f"for {target.id} = {self.expr(start)} to {self.expr(end)}"
                if step.value != 1:
                    header += f" step {step.value}"
            else:
                header = f"for {target.id} in {self.expr(iterator)}"
        elif name == "enumerate" and isinstance(target, ast.Tuple) and len(target.elts) == 2:
            index, item = target.elts
            if not isinstance(index, ast.Name):
                raise Unsupported("this loop variable has no gublan version")
            start = iterator.args[1] if len(iterator.args) > 1 else _const(0)
            before.append(f"{index.id} = {self.expr(_minus(start, 1))}")
            prefix.append(f"{index.id} += 1")
            header = f"for {self.loop_target(item, prefix)} in {self.expr(iterator.args[0])}"
        elif name in ("__ipairs", "__pairs"):
            table = iterator.args[0]
            as_map = name == "__pairs" and self.is_map(table)
            names = target.elts if isinstance(target, ast.Tuple) else [target]
            table_text = self.expr(table)
            if as_map:
                key = names[0].id if names[0].id != "_" else self.temp("key")
                header = f"for {key} in {table_text}"
                if len(names) > 1:
                    prefix.append(f"{names[1].id} = {table_text}[{key}]")
            elif len(names) == 1:
                header = f"for {names[0].id} = 1 to len({table_text})"
            else:
                index, item = names
                if index.id != "_":
                    before.append(f"{index.id} = 0")
                    prefix.append(f"{index.id} += 1")
                header = f"for {item.id} in {table_text}"
        elif isinstance(iterator, ast.Call) and isinstance(iterator.func, ast.Attribute) and \
                iterator.func.attr == "items" and isinstance(target, ast.Tuple) and len(target.elts) == 2:
            key, value = target.elts
            table_text = self.expr(iterator.func.value)
            key_name = key.id if isinstance(key, ast.Name) else self.temp("key")
            header = f"for {key_name} in {table_text}"
            if isinstance(value, ast.Name):
                prefix.append(f"{value.id} = {table_text}[{key_name}]")
            else:
                pair = self.temp("value")
                prefix.append(f"{pair} = {table_text}[{key_name}]")
                for index, part in enumerate(value.elts if isinstance(value, (ast.Tuple, ast.List)) else []):
                    if not isinstance(part, ast.Name):
                        raise Unsupported("this loop variable has no gublan version")
                    prefix.append(f"{part.id} = {pair}[{index}]")
                if not isinstance(value, (ast.Tuple, ast.List)):
                    raise Unsupported("this loop variable has no gublan version")
            if not isinstance(key, ast.Name):
                for index, part in enumerate(key.elts if isinstance(key, (ast.Tuple, ast.List)) else []):
                    if not isinstance(part, ast.Name):
                        raise Unsupported("this loop variable has no gublan version")
                    prefix.insert(0, f"{part.id} = {key_name}[{index}]")
                if not isinstance(key, (ast.Tuple, ast.List)):
                    raise Unsupported("this loop variable has no gublan version")
        else:
            header = f"for {self.loop_target(target, prefix)} in {self.expr(iterator)}"

        def emit_loop():
            for line in before:
                self.emit(depth, line)
            self.emit(depth, header)
            for line in prefix:
                self.emit(depth + 1, line)
            self.body(node.body, depth + 1)
            self.emit(depth, "end")

        self.loop_with_counters(node.body, depth, emit_loop)

    def loop_target(self, target, prefix):
        if isinstance(target, ast.Name):
            return self.variable(target.id)
        if isinstance(target, (ast.Tuple, ast.List)):
            temp = self.temp("item")
            for index, item in enumerate(target.elts):
                if not isinstance(item, ast.Name):
                    raise Unsupported("this loop variable has no gublan version")
                prefix.append(f"{item.id} = {temp}[{index}]")
            return temp
        raise Unsupported("this loop variable has no gublan version")

    def s_Break(self, node, depth):
        self.emit(depth, "break")

    def s_Continue(self, node, depth):
        self.emit(depth, "continue")

    def s_Try(self, node, depth):
        self.emit(depth, "// try: errors stop the program in gublan")
        self.body(node.body, depth)
        if node.handlers:
            self.note("try/except blocks became plain code; the except parts were removed")
        self.body(getattr(node, "orelse", []), depth)
        self.body(node.finalbody, depth)

    s_TryStar = s_Try

    def s_With(self, node, depth):
        self.note("with blocks became plain code")
        self.body(node.body, depth)

    def s_Assert(self, node, depth):
        condition = self.condition(node.test)
        if condition is True:
            return
        self.emit(depth, f"if not ({condition})" if condition is not False else "if true")
        self.emit(depth + 1, 'print "assertion failed"')
        self.emit(depth + 1, "kill")
        self.emit(depth, "end")

    def s_Raise(self, node, depth):
        message = None
        if isinstance(node.exc, ast.Call) and node.exc.args:
            message = node.exc.args[0]
        if message is not None:
            self.emit_print([message], depth)
        else:
            self.emit(depth, 'print "error"')
        self.emit(depth, "kill")

    # special assignments ----------------------------------------------------
    def special_assign(self, target, value, depth):
        if not isinstance(value, ast.Call):
            if isinstance(target, ast.Attribute):
                return self.special_attribute(target, value, depth)
            return False
        func = value.func
        name = self.dotted(func) if isinstance(func, (ast.Name, ast.Attribute)) else None
        target_name = target.id if isinstance(target, ast.Name) else None
        args = value.args
        if name == "pygame.display.set_mode":
            if target_name:
                self.screen_vars.add(target_name)
            self.call_statement(value, depth)
            return True
        if name in ("pygame.time.Clock", "pygame.init", "document.getElementById", "document.querySelector",
                    "document.createElement", "document.body.appendChild"):
            if target_name and name.startswith("document"):
                self.canvas_vars.add(target_name)
            return True
        if isinstance(func, ast.Attribute) and func.attr == "getContext":
            if target_name:
                self.ctx_vars.add(target_name)
            self.ensure_mode(depth)
            return True
        if name in ("pygame.font.Font", "pygame.font.SysFont", "love.graphics.newFont", "love.graphics.setNewFont"):
            size = next((arg for arg in reversed(args) if _is_const(arg, int, float)), None)
            if len(args) >= 2 and name.startswith("pygame"):
                size = args[1]
            elif name.startswith("love") and args:
                size = args[-1]
            if target_name:
                self.surfaces[target_name] = ("font", size)
            if size is not None:
                self.emit(depth, f"textsize {self.token(size)}")
            return True
        if isinstance(func, ast.Attribute) and func.attr == "render" and isinstance(func.value, ast.Name) and \
                self.surfaces.get(func.value.id, ("",))[0] == "font" and target_name:
            color = args[2] if len(args) > 2 else None
            self.surfaces[target_name] = ("text", args[0] if args else _const(""), color)
            return True
        image_loaders = ("pygame.image.load", "loadImage", "love.graphics.newImage")
        inner = value
        while isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) and \
                inner.func.attr in ("convert", "convert_alpha"):
            inner = inner.func.value
        inner_name = self.dotted(inner.func) if isinstance(inner, ast.Call) and isinstance(
            inner.func, (ast.Name, ast.Attribute)) else None
        if inner_name in image_loaders and inner.args and target_name:
            self.surfaces[target_name] = ("image", inner.args[0], None)
            return True
        if name == "pygame.transform.scale" and len(args) >= 2 and isinstance(args[0], ast.Name) and target_name:
            source = self.surfaces.get(args[0].id)
            if source and source[0] in ("image", "sprite"):
                self.surfaces[target_name] = ("sprite", source[1], args[1])
                return True
        if name in ("pygame.mixer.Sound", "loadSound", "love.audio.newSource", "Audio") and args and target_name:
            self.surfaces[target_name] = ("sound", args[0], None)
            return True
        if name == "pygame.key.get_pressed" and target_name:
            self.keys_vars.add(target_name)
            self.emit(depth, f"{target_name} = none")
            return True
        if name in ("input", "prompt", "raw_input") or (
                name in ("int", "float", "parseInt", "parseFloat", "Number", "tonumber") and args and
                isinstance(args[0], ast.Call) and self.dotted(args[0].func) in ("input", "prompt", "io.read")):
            numeric = name not in ("input", "prompt", "raw_input")
            question_call = args[0] if numeric else value
            question = question_call.args[0] if question_call.args else _const("?")
            if not target_name:
                raise Unsupported("input() can only store the answer in a plain variable")
            text, _ = self.template([question], depth)
            self.emit(depth, f"input {target_name} {text.strip() or '?'}")
            if numeric:
                self.emit(depth, f"{target_name} = num({target_name})")
            return True
        if name == "io.read" and target_name:
            self.emit(depth, f"input {target_name} ?")
            return True
        return False

    def special_attribute(self, target, value, depth):
        base = target.value.id if isinstance(target.value, ast.Name) else None
        if base in self.ctx_vars:
            if target.attr in ("fillStyle", "strokeStyle"):
                if target.attr == "fillStyle":
                    self.emit(depth, "color " + " ".join(self.color_tokens([value])))
                return True
            if target.attr == "font" and _is_const(value, str):
                size = re.search(r"(\d+)px", value.value)
                if size:
                    self.emit(depth, f"textsize {size.group(1)}")
                return True
            return True
        if base in self.canvas_vars and target.attr in ("width", "height"):
            self.window[target.attr] = value
            if "width" in self.window and "height" in self.window:
                self.emit(depth, f"window {self.token(self.window['width'])} {self.token(self.window['height'])}")
            return True
        if base and target.attr == "src" and _is_const(value, str):
            self.surfaces[base] = ("image", value, None)
            return True
        if target.attr == "__index" or (target.attr == "length" and _is_const(value, int) and value.value == 0):
            if target.attr == "length" and base:
                self.emit(depth, f"{base} = []")
            return True
        return False

    # call statements --------------------------------------------------------
    def call_statement(self, call, depth):
        func = call.func
        name = self.dotted(func) if isinstance(func, (ast.Name, ast.Attribute)) else None
        args = call.args
        attr = func.attr if isinstance(func, ast.Attribute) else None
        receiver = func.value if isinstance(func, ast.Attribute) else None
        receiver_name = receiver.id if isinstance(receiver, ast.Name) else None
        lib = self.library

        if name == "setattr" and len(args) == 3 and _is_const(args[1], str) and args[1].value.isidentifier() \
                and self.language == "python":
            target = ast.Attribute(value=args[0], attr=args[1].value, ctx=ast.Store())
            self.stmt(ast.Assign(targets=[target], value=args[2], lineno=getattr(call, "lineno", None)), depth)
            return
        if name in SKIP_CALLS:
            if name in ("stroke", "noFill"):
                self.note("outlines (stroke, nofill) are drawn as filled shapes")
            return
        if name in KILL_CALLS:
            self.emit(depth, "kill")
            return
        if name in PRINT_CALLS:
            self.emit_print([arg for arg in args], depth)
            return
        if name == "alert":
            self.emit_print(args, depth, "popup")
            return
        if name in ("input", "prompt"):
            self.special_assign(ast.Name(id=self.temp("answer"), ctx=ast.Store()), call, depth)
            return
        if name in ("time.sleep",) and args:
            self.emit(depth, f"wait {self.token(args[0])}")
            return
        if name in ("pygame.time.delay", "pygame.time.wait") and args:
            self.emit(depth, f"wait {self.token(ast.BinOp(left=args[0], op=ast.Div(), right=_const(1000)))}")
            return
        if name in ("pygame.display.set_mode", "createCanvas", "resizeCanvas", "love.window.setMode",
                    "size"):
            size = args[0].elts if args and isinstance(args[0], (ast.Tuple, ast.List)) else args[:2]
            if len(size) >= 2 and not (_is_const(size[0], int) and size[0].value == 0):
                self.emit(depth, f"window {self.token(size[0])} {self.token(size[1])}")
            if name in ("createCanvas", "pygame.display.set_mode"):
                self.ensure_mode(depth)
            return
        if name in ("pygame.display.set_caption", "love.window.setTitle") and args:
            text, _ = self.template(args[:1], depth)
            self.emit(depth, f"title {text}")
            return
        if name in ("pygame.display.flip", "pygame.display.update"):
            self.emit(depth, "frame")
            return
        if name in ("frameRate",) and args:
            self.emit(depth, f"fps {self.token(args[0])}")
            return
        if attr == "tick" and args:
            self.emit(depth, f"fps {self.token(args[0])}")
            return
        if name == "requestAnimationFrame":
            if args and isinstance(args[0], ast.Name) and args[0].id in self.loop_functions:
                if self.function_depth:
                    if args[0].id in self.loop_conditional:
                        self.emit(depth, f"{self.functions.get(args[0].id, args[0].id)}_again = true")
                    return
                self.emit_game_loop(args[0].id, depth)
                return
            raise Unsupported("requestAnimationFrame needs a named function")
        if name in ("setInterval",) and len(args) == 2 and isinstance(args[0], ast.Name) and \
                args[0].id in self.functions:
            self.emit(depth, "forever")
            self.emit(depth + 1, f"{self.functions[args[0].id]}()")
            self.emit(depth + 1, f"wait {self.token(ast.BinOp(left=args[1], op=ast.Div(), right=_const(1000)))}")
            self.emit(depth, "end")
            return
        if isinstance(func, ast.Name) and func.id in self.loop_functions and self.function_depth == 0:
            self.emit_game_loop(func.id, depth)
            return
        # backgrounds
        if (attr == "fill" and (receiver_name in self.screen_vars or lib == "pygame") and len(args) >= 1) or \
                name in ("background", "love.graphics.setBackgroundColor", "love.graphics.clear"):
            if name == "love.graphics.clear" and not args:
                return
            self.emit(depth, "background " + " ".join(self.color_tokens(args, scale=lib == "love")))
            return
        if name in ("fill", "love.graphics.setColor"):
            self.emit(depth, "color " + " ".join(self.color_tokens(args, scale=lib == "love")))
            return
        if name in ("textSize",) and args:
            self.emit(depth, f"textsize {self.token(args[0])}")
            return
        if self.draw_statement(call, name, attr, receiver_name, args, depth):
            return
        # sound
        if attr == "play" and receiver_name and self.surfaces.get(receiver_name, ("",))[0] == "sound":
            self.emit(depth, f"sound {self.path(self.surfaces[receiver_name][1])}")
            return
        if name == "love.audio.play" and args and isinstance(args[0], ast.Name) and \
                self.surfaces.get(args[0].id, ("",))[0] == "sound":
            self.emit(depth, f"sound {self.path(self.surfaces[args[0].id][1])}")
            return
        if name == "pygame.mixer.music.load" and args:
            self.music_path = args[0]
            return
        if name == "pygame.mixer.music.play":
            if self.music_path is None:
                raise Unsupported("music.play() without music.load()")
            self.emit(depth, f"music {self.path(self.music_path)}")
            return
        if name == "pygame.mixer.music.stop":
            self.emit(depth, "stopmusic")
            return
        if name in ("pygame.mixer.stop",):
            self.emit(depth, "stopsounds")
            return
        if name == "pygame.mixer.music.set_volume" and args:
            self.emit(depth, f"volume {self.token(args[0])}")
            return
        # list helpers
        if attr in ("append", "push") and len(args) == 1 and receiver is not None and not (
                receiver_name in self.modules):
            self.emit_append(receiver, args[0], depth)
            return
        if name == "table.insert" and len(args) == 2:
            self.emit_append(args[0], args[1], depth)
            return
        if name == "table.insert" and len(args) == 3:
            raise Unsupported("table.insert at a position has no gublan version")
        if (attr == "pop" and receiver is not None and len(args) <= 1) or (
                name == "table.remove" and 1 <= len(args) <= 2):
            container = args[0] if name == "table.remove" else receiver
            index = (args[1] if len(args) > 1 else None) if name == "table.remove" else (args[0] if args else None)
            container_text = self.expr(container)
            if not re.fullmatch(r"\w+", container_text):
                raise Unsupported("removing from this list has no gublan version")
            if index is None:
                index_text = self.expr(_minus(_call("len", container), 1))
            else:
                index_text = self.expr(_minus(index, 1) if name == "table.remove" else index)
            temp = self.temp("i")
            self.emit(depth, f"{temp} = {index_text}")
            self.emit(depth, f"delete {container_text} {temp}")
            return
        if attr == "shift" and receiver is not None and not args:
            self.emit(depth, f"delete {self.expr(receiver)} 0")
            return
        if attr == "splice" and receiver is not None and len(args) == 2 and _is_const(args[1], int) and \
                args[1].value == 1:
            temp = self.temp("i")
            self.emit(depth, f"{temp} = {self.expr(args[0])}")
            self.emit(depth, f"delete {self.expr(receiver)} {temp}")
            return
        if attr == "clear" and receiver is not None and not args:
            self.assign_text(receiver, "[]", depth)
            return
        if attr == "extend" and receiver is not None and len(args) == 1:
            self.assign_text(receiver, self.expr(ast.BinOp(left=receiver, op=ast.Add(), right=args[0])), depth)
            return
        if attr in ("sort", "reverse") and receiver is not None and not args and not call.keywords:
            self.assign_text(receiver, f"{attr}({self.expr(receiver)})", depth)
            return
        if attr == "update" and receiver is not None and len(args) == 1 and isinstance(args[0], ast.Dict):
            for key, item in zip(args[0].keys, args[0].values):
                self.assign_text(ast.Subscript(value=receiver, slice=key, ctx=ast.Store()), self.expr(item), depth)
            return
        if attr == "forEach" and receiver is not None and len(args) == 1 and isinstance(args[0], ArrowFunction):
            params = args[0].params
            loop = ast.For(target=ast.Name(id=params[0] if params else "_item", ctx=ast.Store()),
                           iter=receiver, body=args[0].body, orelse=[])
            if len(params) > 1:
                loop = ast.For(target=ast.Tuple(elts=[ast.Name(id=params[1], ctx=ast.Store()),
                                                      ast.Name(id=params[0], ctx=ast.Store())], ctx=ast.Store()),
                               iter=_call("enumerate", receiver), body=args[0].body, orelse=[])
            self.s_For(loop, depth)
            return
        if attr == "addEventListener" and _key_state_map(call):
            self.note("keys[e.key] listeners became keydown(\"left\") checks")
            return
        if name in ("document.addEventListener", "window.addEventListener", "addEventListener") or \
                attr == "addEventListener":
            self.note("event listeners were not converted; check keys with keydown(\"left\") or "
                      "keypressed(\"space\") inside the game loop")
            raise Unsupported("event listeners have no gublan version")
        if name in ("setTimeout", "setInterval"):
            raise Unsupported(f"{name} has no gublan version; use wait inside a loop")
        if any(isinstance(arg, ArrowFunction) for arg in args):
            raise Unsupported("passing functions as values has no gublan version")
        text = self.expr(call)
        called = re.match(r"(\w+)\(", text)
        known = set(self.functions.values()) | set(self.dotted_functions.values()) | {
            f"{owner}_{method}" for owner, info in self.classes.items() for method in info["methods"]} | {
            f"{owner}__init__" for owner in self.classes}
        if called and called.group(1) in known:
            self.emit(depth, text)
            return
        raise Unsupported(f"{name or 'this call'}() has no gublan version")

    def emit_game_loop(self, function, depth):
        self.ensure_mode(depth)
        gublan_name = self.functions.get(function, function)
        if function in self.loop_conditional:
            self.emit(depth, f"{gublan_name}_again = true")
            self.emit(depth, f"while {gublan_name}_again")
            self.emit(depth + 1, f"{gublan_name}_again = false")
        else:
            self.emit(depth, "forever")
        self.emit(depth + 1, f"{gublan_name}()")
        self.emit(depth + 1, "frame")
        self.emit(depth, "end")

    def emit_append(self, container, item, depth):
        container_text = self.expr(container)
        if not re.fullmatch(r"\w+", container_text):
            temp = self.temp()
            self.emit(depth, f"{temp} = {container_text}")
            container_text = temp
        self.emit(depth, f"append {container_text} {self.token(item)}")

    def path(self, node):
        if _is_const(node, str):
            return node.value.replace("\\", "/")
        raise Unsupported("file paths must be written as text, like \"jump.wav\"")

    def draw_statement(self, call, name, attr, receiver_name, args, depth):
        lib = self.library
        if name in ("pygame.draw.rect",) and len(args) >= 3:
            if len(args) > 3:
                self.note("outlined pygame rectangles are drawn filled")
            self.ensure_mode(depth)
            self.emit_shape(call, depth, "box", self.rect_tokens(args[2]), self.color_tokens([args[1]]),
                            hint=self.hint_for(args[2], "_shape"))
            return True
        if name == "pygame.draw.circle" and len(args) >= 4:
            self.ensure_mode(depth)
            self.emit_shape(call, depth, "circle", self.point_tokens(args[2]) + [self.token(args[3])],
                            self.color_tokens([args[1]]))
            return True
        if name in ("pygame.draw.line", "pygame.draw.aaline") and len(args) >= 4:
            self.ensure_mode(depth)
            width = [self.token(args[4])] if len(args) > 4 else []
            self.emit_shape(call, depth, "line", self.point_tokens(args[2]) + self.point_tokens(args[3]) + width,
                            self.color_tokens([args[1]]))
            return True
        if name == "pygame.draw.ellipse" and len(args) >= 3:
            self.ensure_mode(depth)
            rect = args[2]
            if isinstance(rect, (ast.Tuple, ast.List)) and len(rect.elts) == 4:
                x, y, w, h = rect.elts
                center_x = ast.BinOp(left=x, op=ast.Add(), right=ast.BinOp(left=w, op=ast.Div(), right=_const(2)))
                center_y = ast.BinOp(left=y, op=ast.Add(), right=ast.BinOp(left=h, op=ast.Div(), right=_const(2)))
                radius = ast.BinOp(left=copy.deepcopy(w), op=ast.Div(), right=_const(2))
                self.note("ellipses became circles")
                self.emit_shape(call, depth, "circle", [self.token(center_x), self.token(center_y),
                                                        self.token(radius)], self.color_tokens([args[1]]))
                return True
            raise Unsupported("this ellipse has no gublan version")
        if attr == "blit" and len(args) >= 2:
            self.ensure_mode(depth)
            surface = args[0]
            position = args[1]
            pos = self.point_tokens(position) if isinstance(position, (ast.Tuple, ast.List)) else [
                self.token(ast.Attribute(value=position, attr="x", ctx=ast.Load())),
                self.token(ast.Attribute(value=position, attr="y", ctx=ast.Load()))]
            info = None
            if isinstance(surface, ast.Name):
                info = self.surfaces.get(surface.id)
            elif isinstance(surface, ast.Call) and isinstance(surface.func, ast.Attribute) and \
                    surface.func.attr == "render":
                info = ("text", surface.args[0] if surface.args else _const(""),
                        surface.args[2] if len(surface.args) > 2 else None)
            if info is None:
                raise Unsupported("blit needs a picture loaded with pygame.image.load or text from font.render")
            if info[0] == "text":
                text, _ = self.template([info[1]], depth)
                color = self.color_tokens([info[2]]) if info[2] is not None else None
                content = text if "{" in text else self.quote(text)
                self.emit_shape(call, depth, "text", pos + [content], color,
                                hint=self.hint_for(surface, "_label") if isinstance(surface, ast.Name) else None)
                return True
            if info[0] == "image":
                self.emit_shape(call, depth, "image", [self.quote(self.path(info[1]))] + pos,
                                hint=self.hint_for(surface, "_image"))
                return True
            if info[0] == "sprite":
                size = info[2]
                size_tokens = self.point_tokens(size)
                self.emit_shape(call, depth, "sprite", [self.quote(self.path(info[1]))] + pos + size_tokens,
                                hint=self.hint_for(surface, "_image"))
                return True
            return False
        if lib == "p5" or lib == "canvas" or lib == "love":
            mode_args = args
            if lib == "love" and name in ("love.graphics.rectangle", "love.graphics.circle") and args and \
                    _is_const(args[0], str):
                if args[0].value == "line":
                    self.note("outlined shapes are drawn filled")
                mode_args = args[1:]
            shape = None
            if name in ("rect", "love.graphics.rectangle") or attr in ("fillRect", "strokeRect"):
                if attr in ("fillRect", "strokeRect") and receiver_name not in self.ctx_vars:
                    return False
                if len(mode_args) >= 4:
                    shape = ("box", [self.token(arg) for arg in mode_args[:4]])
            elif name == "square" and len(args) >= 3:
                shape = ("box", [self.token(args[0]), self.token(args[1]), self.token(args[2]), self.token(args[2])])
            elif name in ("ellipse", "circle", "love.graphics.circle", "point"):
                if name == "ellipse" and len(args) >= 3:
                    shape = ("circle", [self.token(args[0]), self.token(args[1]),
                                        self.token(ast.BinOp(left=args[2], op=ast.Div(), right=_const(2)))])
                elif name == "circle" and len(args) >= 3:
                    shape = ("circle", [self.token(args[0]), self.token(args[1]),
                                        self.token(ast.BinOp(left=args[2], op=ast.Div(), right=_const(2)))])
                elif name == "love.graphics.circle" and len(mode_args) >= 3:
                    shape = ("circle", [self.token(arg) for arg in mode_args[:3]])
                elif name == "point" and len(args) >= 2:
                    shape = ("circle", [self.token(args[0]), self.token(args[1]), "1"])
            elif name in ("line", "love.graphics.line") and len(args) >= 4:
                shape = ("line", [self.token(arg) for arg in args[:4]])
            elif (name in ("text", "love.graphics.print", "love.graphics.printf") or attr == "fillText") and \
                    len(args) >= 3:
                if attr == "fillText" and receiver_name not in self.ctx_vars:
                    return False
                text, _ = self.template([args[0]], depth)
                content = text if "{" in text else self.quote(text)
                shape = ("text", [self.token(args[1]), self.token(args[2]), content])
            elif (name in ("image", "love.graphics.draw") or attr == "drawImage") and len(args) >= 3:
                if attr == "drawImage" and receiver_name not in self.ctx_vars:
                    return False
                info = self.surfaces.get(args[0].id) if isinstance(args[0], ast.Name) else None
                if not info or info[0] != "image":
                    raise Unsupported("this picture was not loaded with loadImage/newImage")
                path = self.quote(self.path(info[1]))
                if len(args) >= 5 and name != "love.graphics.draw":
                    shape = ("sprite", [path] + [self.token(arg) for arg in args[1:5]])
                else:
                    shape = ("image", [path, self.token(args[1]), self.token(args[2])])
            elif attr == "arc" and receiver_name in self.ctx_vars and len(args) >= 3:
                shape = ("circle", [self.token(arg) for arg in args[:3]])
            elif attr in ("clearRect", "beginPath", "closePath", "fill", "stroke", "save", "restore",
                          "moveTo", "lineTo") and receiver_name in self.ctx_vars:
                return True
            if shape:
                self.ensure_mode(depth)
                self.emit_shape(call, depth, shape[0], shape[1])
                return True
        return False


# --------------------------------------------------------------------------
# entry points
# --------------------------------------------------------------------------

_DEEP_LOCK = threading.Lock()


def convert(source, language=None, filename=None):
    """convert source code to gublan. returns a ConversionResult.

    the work runs on a helper thread with a big stack, so deeply nested code converts instead of
    stopping the whole file with a recursion error."""
    box = {}

    def work():
        try:
            box["result"] = _convert(source, language, filename)
        except BaseException as err:  # noqa: BLE001 - handed back to the caller below
            box["error"] = err

    with _DEEP_LOCK:
        old_limit = sys.getrecursionlimit()
        old_stack = threading.stack_size()
        try:
            threading.stack_size(64 * 1024 * 1024)
            sys.setrecursionlimit(max(old_limit, 20000))
            helper = threading.Thread(target=work, name="gublan-convert", daemon=True)
            helper.start()
        finally:
            threading.stack_size(old_stack)
        helper.join()
        sys.setrecursionlimit(old_limit)
    if "error" in box:
        error = box["error"]
        if isinstance(error, RecursionError):
            raise ValueError("this code is nested too deeply to convert") from error
        raise error
    return box["result"]


def _convert(source, language=None, filename=None):
    source = source.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4)
    language = (language or detect_language(source, filename)).lower()
    if language not in LANGUAGES:
        raise ValueError(f"the converter supports {', '.join(LANGUAGES)}")
    if language == "python":
        tree = _parse_python(source)
    elif language == "javascript":
        tree = JSParser(source).parse_program()
    else:
        tree = LuaParser(source).parse_program()
    writer = _Writer(language, source)
    text = writer.write(tree)
    return ConversionResult(
        text=text, language=language, library=writer.library, notes=writer.notes,
        todos=sum(1 for line in text.split("\n") if line.lstrip().startswith("// todo")),
        source_lines=source.count("\n") + 1,
    )


def convert_file(path, language=None):
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return convert(handle.read(), language, filename=path)
