"""Console output for API methods, so the user can follow each executed step."""

import os
import re
import sys
import time

_START = time.time()

_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"

_FALSE = ("0", "false", "no", "off")


def _enable_windows_ansi():
    """Let a legacy Windows console interpret escape codes instead of echoing them."""
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:  # pragma: no cover - console quirk, never worth failing over
        pass


def _want_color():
    """Whether to emit escape codes.

    A tty is the default answer, but it is the wrong one under the test runner:
    a testcase there writes into a pipe, `isatty()` is False, and the whole run
    would arrive colourless. So an explicit AUTOPLAY_COLOR (or the conventional
    FORCE_COLOR / NO_COLOR) overrides the guess, and the runner sets it when its
    own console can display the result.

    AUTOPLAY_COLOR is read before NO_COLOR, and is the one thing that outranks
    it: the runner only sets it from an explicit `--color`, and a flag typed on
    this command line is a narrower instruction than an environment default.
    Were it the other way round, `NO_COLOR=1 ... --color always` would colour
    the runner's own table and leave the testcase logs under it plain.
    """
    value = os.environ.get("AUTOPLAY_COLOR")
    if value is not None:
        return value.strip().lower() not in _FALSE
    if os.environ.get("NO_COLOR"):
        return False
    value = os.environ.get("FORCE_COLOR")
    if value is not None:
        return value.strip().lower() not in _FALSE
    return sys.stdout.isatty()


_COLOR = _want_color()
if _COLOR:
    _enable_windows_ansi()


def _color(text, code):
    if _COLOR:
        return f"{code}{text}{_RESET}"
    return text


# Parts of a step message worth picking out at a glance. One alternation, so a
# single pass covers the line and nothing is ever re-matched inside an escape
# code that an earlier rule just inserted. Order matters: "not found" has to win
# over the "found" inside it.
_HIGHLIGHT = re.compile(
    r"(?P<method>^[A-Za-z_]\w*(?=\())"
    r"|(?P<bad>\bnot found\b|\bno match\b|\btimed out\b|\bnot seen\b)"
    r"|(?P<good>\bfound\b|\bsatisfied\b|\d+ match\(es\))"
    r"|(?P<text>'[^']*'|\"[^\"]*\")"
    r"|(?P<aside>\[[^\]]*since frame\]|\(attempt [^)]*\))"
)

_STYLES = {
    "method": _BOLD,
    "bad": _RED,
    "good": _GREEN,
    "text": _CYAN,
    "aside": _DIM,
}


def _highlight(message):
    """Colour the interesting parts of a step message."""
    if not _COLOR:
        return message

    def paint(match):
        kind = match.lastgroup
        return f"{_STYLES[kind]}{match.group()}{_RESET}"

    return _HIGHLIGHT.sub(paint, message)


def _write(line):
    """Print a line even when the console cannot encode it.

    Screens under test carry text in any language, and a Windows console is
    often cp1252 - printing 'Tiếp tục' there raises UnicodeEncodeError and
    would kill the testcase from inside the logging call.
    """
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(line.encode(encoding, "replace").decode(encoding), flush=True)


# The console is the primary output, but the same lines also make the report's
# timeline, so recording hangs off the logging calls rather than being sprinkled
# through the API. It stays None unless the runner asked for artifacts.
_recorder = None
_recorder_opened = False


def recorder():
    """The artifact recorder for this run, or None when none was asked for."""
    global _recorder, _recorder_opened
    if not _recorder_opened:
        _recorder_opened = True
        try:
            from .report import Recorder

            _recorder = Recorder.open()
        except Exception:  # noqa: BLE001 - a report is never worth a failed run
            _recorder = None
    return _recorder


def _record(kind, text, **extra):
    rec = recorder()
    if rec is not None:
        rec.record(kind, text, **extra)


def step(message):
    """Print a one-line summary of an API action."""
    elapsed = time.time() - _START
    _write(f"{_color(f'[{elapsed:6.2f}s]', _DIM)} {_highlight(message)}")
    _record("step", message)


def result(name, passed, detail=""):
    tag = _color("PASS", _GREEN) if passed else _color("FAIL", _RED)
    suffix = f" - {detail}" if detail else ""
    _write(f"  {tag}  {name}{suffix}")
    _record("pass" if passed else "fail", name, detail=detail)


def skipped(name, detail=""):
    """An optional step that never appeared - not a failure."""
    suffix = f" - {detail}" if detail else ""
    _write(f"  {_color('SKIP', _YELLOW)}  {name}{suffix}")
    _record("skip", name, detail=detail)


def summary(testcase, passed, failed, skips=0, aborted=None):
    total = passed + failed
    ok = failed == 0 and aborted is None
    tag = _color("PASSED", _GREEN) if ok else _color("FAILED", _RED)
    extra = f", {skips} optional step(s) skipped" if skips else ""
    print("", flush=True)
    _write(
        f"TESTCASE {_color(testcase, _BOLD)}: {tag} "
        f" ({passed}/{total} assertions passed{extra})"
    )
    if aborted:
        _write(f"  {_color('aborted:', _RED)} {aborted}")
    rec = recorder()
    if rec is not None:
        rec.testcase = testcase
        rec.finish(passed, failed, skips, aborted)
