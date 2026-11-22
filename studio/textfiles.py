"""reading files into the editor without surprises.

notepad saves "unicode" as utf-16, old programs use windows-1252, and sometimes a picture or a zip ends up
in the files panel. 1.0.5 read everything as utf-8 (or latin-1), which showed utf-16 files as garbage full of
invisible zero characters and loaded binary files that then made tk crawl. this module works out what a
file really is first.
"""

import codecs
import os

ASK_ABOVE = 2 * 1024 * 1024        # bigger than this: ask first, the editor gets slow
REFUSE_ABOVE = 40 * 1024 * 1024    # bigger than this: not a program. offer to show it in the folder instead
LONG_LINE = 20000                  # tk slows right down on lines longer than this
BLOCKS_LIMIT = 400 * 1024          # the blocks view is for programs, not for huge files
BLOCKS_LINES = 6000

_BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)


class NotText(Exception):
    """the file is a picture, a program, a zip... something the code editor can't show."""


def sniff(data):
    """(encoding, bytes to skip) for the start of a file, or raise NotText."""
    for bom, encoding in _BOMS:
        if data.startswith(bom):
            return encoding, len(bom)
    sample = data[:8192]
    if b"\x00" in sample:
        # utf-16 without a byte order mark: every other byte of plain english text is zero
        even, odd = sample[0::2], sample[1::2]
        if len(sample) >= 4 and odd.count(0) > len(odd) * 0.4 and even.count(0) < len(even) * 0.05:
            return "utf-16-le", 0
        if len(sample) >= 4 and even.count(0) > len(even) * 0.4 and odd.count(0) < len(odd) * 0.05:
            return "utf-16-be", 0
    if _binary_share(sample) > 0.1:
        raise NotText("it has binary data in it (it is not a text file)")
    try:
        sample.decode("utf-8")
        return "utf-8", 0
    except UnicodeDecodeError as err:
        # a character cut in half by the 8 kb sample is still utf-8
        if err.start >= len(sample) - 4:
            return "utf-8", 0
        return None, 0


def decode(data):
    """(text, encoding name) with windows line endings turned into \\n."""
    encoding, skip = sniff(data)
    body = data[skip:]
    if encoding is None or encoding == "utf-8":
        try:
            text, encoding = body.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            try:
                text, encoding = body.decode("cp1252"), "windows-1252"
            except UnicodeDecodeError:
                text, encoding = body.decode("latin-1"), "latin-1"
    else:
        text = body.decode(encoding, errors="replace")
    if "\x00" in text:
        # a few stray zero characters in a real program: drop them (tk and the language can't use them)
        if text.count("\x00") > max(16, len(text) // 100):
            raise NotText("it has zero characters in it (it is not a text file)")
        text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text, encoding


_TEXT_CONTROLS = {9, 10, 12, 13, 27}


def _binary_share(sample):
    """how much of the sample is control bytes that never appear in text files (0.0 to 1.0)."""
    if not sample:
        return 0.0
    odd = sum(1 for byte in sample if byte < 32 and byte not in _TEXT_CONTROLS)
    return odd / len(sample)


def size_of(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def describe_size(size):
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} mb"
    if size >= 1024:
        return f"{size / 1024:.0f} kb"
    return f"{size} bytes"


def longest_line(text, stop=LONG_LINE):
    """the longest line, but stops counting as soon as one passes `stop` (fast for huge files)."""
    longest = 0
    start = 0
    while True:
        end = text.find("\n", start)
        length = (len(text) if end < 0 else end) - start
        if length > longest:
            longest = length
            if longest > stop:
                return longest
        if end < 0:
            return longest
        start = end + 1


def read(path):
    """(text, encoding) or raise NotText / OSError."""
    with open(path, "rb") as handle:
        data = handle.read()
    return decode(data)


def too_big_for_blocks(text):
    return len(text) > BLOCKS_LIMIT or text.count("\n") > BLOCKS_LINES
