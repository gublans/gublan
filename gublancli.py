"""gublan from the command line.

    py gublancli.py run game.gubl                  run a program (same as: py gublancli.py game.gubl)
    py gublancli.py check game.gubl                list problems without running
    py gublancli.py test game.gubl [name...]       run the program's test blocks (or just one of them)
    py gublancli.py convert old.py [out]           turn python, javascript or lua into gublan
    py gublancli.py translate game.gubl <language> [folder]
                                                   turn gublan into python, javascript or lua
    py gublancli.py mcp [project folder]           start the mcp server so ai helpers can work on a project
    py gublancli.py docs                           rebuild docs/COMMANDS.md from the language
"""

import os
import sys

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
USAGE = __doc__.split("\n\n", 1)[1].rstrip()


def _plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


def _read(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return handle.read()


def _load_plugins():
    """plugins that are switched on in gublan studio's settings work here too."""
    try:
        from studio import plugins
    except ImportError:
        return
    for info in plugins.load_plugins():
        if info.status == "error":
            print(f"plugin {info.describe()}", file=sys.stderr)


def cmd_run(path):
    _load_plugins()
    from gublancore import GublanRuntime
    runtime = GublanRuntime(base_dir=os.path.dirname(os.path.abspath(path)),
                            oninput=lambda prompt: input(f"{prompt} "), onpopup=lambda text: print(text),
                            save_name=os.path.splitext(os.path.basename(path))[0])
    runtime.run(_read(path))
    return 1 if runtime.last_error else 0


def cmd_check(path):
    _load_plugins()
    from gublancore import analyze_source
    problems = analyze_source(_read(path), warnings=True)
    for item in problems:
        where = f"line {item['line']}" if item.get("line") else "file"
        print(f"{path}: {where}: {item.get('severity', 'error')}: {item['message']}")
    errors = sum(1 for item in problems if item.get("severity", "error") == "error")
    warnings = len(problems) - errors
    print(f"{_plural(errors, 'error')}, {_plural(warnings, 'warning')}")
    return 1 if errors else 0


def cmd_test(path, only=None):
    _load_plugins()
    from gublancore import GublanRuntime
    runtime = GublanRuntime(base_dir=os.path.dirname(os.path.abspath(path)), onlog=lambda *_: None,
                            oninput=lambda prompt: "", onpopup=lambda text: None,
                            save_name=os.path.splitext(os.path.basename(path))[0] + "_tests")
    results = runtime.run_tests(_read(path), only=only)
    if not results:
        print("this program has no test blocks. add one like:\n\n    test adding works\n        assert 1 + 1 == 2\n"
              "    end")
        return 0
    for result in results:
        if result["passed"]:
            print(f"pass: {result['name']} ({result['seconds']:.2f}s)")
        else:
            where = f" (line {result['line']})" if result.get("line") else ""
            print(f"fail: {result['name']}{where}: {result['message']}")
    failed = sum(1 for result in results if not result["passed"])
    print(f"{len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


def cmd_convert(path, output=None):
    import gublanconvert
    result = gublanconvert.convert(_read(path), filename=path)
    if output:
        with open(output, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(result.text)
        print(f"wrote {output}")
    else:
        sys.stdout.write(result.text + ("\n" if not result.text.endswith("\n") else ""))
    print(f"// {result.language}: {result.source_lines} lines in, {result.output_lines} out, "
          f"{_plural(result.todos, 'todo')}", file=sys.stderr)
    for note in result.notes:
        print(f"// note: {note}", file=sys.stderr)
    return 0


def cmd_translate(path, language, folder=None):
    import gublantranslate
    try:
        language = gublantranslate.language_of(language)
        stem = os.path.splitext(os.path.basename(path))[0]
        result = gublantranslate.translate(_read(path), language, name=stem,
                                           base_dir=os.path.dirname(os.path.abspath(path)))
    except gublantranslate.TranslateError as err:
        print(f"could not translate: {err}", file=sys.stderr)
        return 1
    folder = folder or os.path.join(os.path.dirname(os.path.abspath(path)), f"{stem}_{language}")
    for written in gublantranslate.write_files(result, folder):
        print(f"wrote {os.path.normpath(written)}")
    print(f"{result.source_lines} gublan lines -> {result.output_lines} {language} lines, "
          f"{_plural(result.todos, 'todo')} (marked with 'todo' comments)")
    for note in result.notes:
        print(f"  note: {note}")
    print(gublantranslate.LANGUAGES[language]["how"].format(main=result.main))
    return 0


def cmd_mcp(folder=None):
    import gublanmcp
    return gublanmcp.serve(folder)


def cmd_docs():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from studio import docsgen
    print(f"wrote {docsgen.write()}")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    command, rest = argv[0], argv[1:]
    try:
        if command == "run" and rest:
            return cmd_run(rest[0])
        if command == "check" and rest:
            return cmd_check(rest[0])
        if command == "test" and rest:
            return cmd_test(rest[0], " ".join(rest[1:]) or None)
        if command == "convert" and rest:
            return cmd_convert(rest[0], rest[1] if len(rest) > 1 else None)
        if command in ("translate", "export") and len(rest) >= 2:
            return cmd_translate(rest[0], rest[1], rest[2] if len(rest) > 2 else None)
        if command == "mcp":
            return cmd_mcp(rest[0] if rest else None)
        if command == "docs":
            return cmd_docs()
        if os.path.isfile(command):
            return cmd_run(command)
    except OSError as err:
        print(f"could not open the file: {err}", file=sys.stderr)
        return 1
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
