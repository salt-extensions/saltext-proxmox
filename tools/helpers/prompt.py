import os
import platform
import sys

DARKGREEN = (0, 100, 0)
DARKRED = (139, 0, 0)
YELLOW = (255, 255, 0)


def ensure_utf8():
    """
    On Windows, ensure stdout/stderr output uses UTF-8 encoding.
    """
    if platform.system() != "Windows":
        return
    for stream in (sys.stdout, sys.stderr):
        if stream.encoding != "utf-8":
            stream.reconfigure(encoding="utf-8")


def pprint(msg, bold=False, fg=None, bg=None, stream=None, force_print=False):
    """
    Ugly helper for printing a bit more fancy output.
    Stand-in for questionary/prompt_toolkit.
    """
    if not force_print and os.getenv("TOOLS_SILENT"):
        return
    out = ""
    if bold:
        out += "\033[1m"
    if fg:
        red, green, blue = fg
        out += f"\033[38;2;{red};{green};{blue}m"
    if bg:
        red, green, blue = bg
        out += f"\033[48;2;{red};{green};{blue}m"
    out += msg
    if bold or fg or bg:
        out += "\033[0m"
    print(out, file=stream or sys.stdout)


def status(msg, message=None):
    out = f"\n    → {msg}"
    pprint(out, bold=True, fg=DARKGREEN, stream=sys.stderr)
    if message:
        pprint(message, stream=sys.stderr)


def warn(header, message=None):
    out = f"\n{header}"
    pprint(out, bold=True, bg=DARKRED, stream=sys.stderr, force_print=True)
    if message:
        pprint(message, stream=sys.stderr, force_print=True)
