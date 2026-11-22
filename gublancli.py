"""gublan from the command line.

    py gublancli.py run game.gubl          run a program (same as: py gublancli.py game.gubl)
    py gublancli.py check game.gubl        list problems without running
    py gublancli.py convert old.py [out]   turn python, javascript or lua into gublan
    py gublancli.py docs                   rebuild docs/COMMANDS.md from the language
"""

import os
import sys

USAGE = __doc__.split("\n\n", 1)[1].rstrip()


def _plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


def _read(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return handle.read()


def cmd_run(path):
    from gublancore import GublanRuntime
    runtime = GublanRuntime(base_dir=os.path.dirname(os.path.abspath(path)),
                            oninput=lambda prompt: input(f"{prompt} "), onpopup=lambda text: print(text))
    runtime.run(_read(path))
    return 1 if runtime.last_error else 0


def cmd_check(path):
    from gublancore import analyze_source
    problems = analyze_source(_read(path), warnings=True)
    for item in problems:
        where = f"line {item['line']}" if item.get("line") else "file"
        print(f"{path}: {where}: {item.get('severity', 'error')}: {item['message']}")
    errors = sum(1 for item in problems if item.get("severity", "error") == "error")
    warnings = len(problems) - errors
    print(f"{_plural(errors, 'error')}, {_plural(warnings, 'warning')}")
    return 1 if errors else 0


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
        if command == "convert" and rest:
            return cmd_convert(rest[0], rest[1] if len(rest) > 1 else None)
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
