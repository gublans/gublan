"""gublan studio entry point.

the editor itself lives in the studio package. this file keeps the old name working:
    py gublanide.py [program.gubl ...]
"""

import os
import subprocess  # noqa: F401 - kept here so tools and tests can patch gublanide.subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    # show the splash before the heavy imports (pygame, opengl) happen
    from studio.launch import launch
    sys.exit(launch())

from gublancore import GUBLANCOMMANDS, analyze_source, split_command  # noqa: E402
from studio.app import GublanStudio, main  # noqa: E402

BLOCK_COMMANDS = set(GUBLANCOMMANDS)

__all__ = ["BLOCK_COMMANDS", "GublanStudio", "analyze_source", "main", "split_command"]
