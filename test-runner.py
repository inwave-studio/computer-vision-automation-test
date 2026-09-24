"""Run every testcase in a folder, print a result table, write an HTML report.

    python test-runner.py Tests
    python test-runner.py Tests --report report.html -s emulator-5554
    python test-runner.py Tests --pattern "test_beat*.py"

Each testcase is a plain Python script (see Tests/), so it is run as its own
process: a testcase drives a real device through a scrcpy stream and an OCR
engine, and one that wedges or crashes the interpreter must not take the rest of
the run with it. The subprocess boundary also means the console output the
testcase prints is captured verbatim and can go straight into the report.
"""

import argparse
import datetime
import fnmatch
import html
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from autoplay.log import _enable_windows_ansi  # noqa: E402

# The summary line autoplay/log.py prints when a testcase ends, e.g.
#   TESTCASE test_x.py: PASSED  (2/2 assertions passed, 1 optional step skipped)
_SUMMARY = re.compile(
    r"^TESTCASE\s+(?P<name>.+?):\s+(?P<status>PASSED|FAILED)\s+"
    r"\((?P<passed>\d+)/(?P<total>\d+)\s+assertions passed"
    r"(?:,\s*(?P<skipped>\d+)\s+optional)?",
)
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

PASSED = "PASSED"
FAILED = "FAILED"
ERROR = "ERROR"
TIMEOUT = "TIMEOUT"

_GREEN = "\033[32m"
_RED = "\033[31m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"

COLOR = False  # decided in main(), so the table matches the echoed testcase logs


def _paint(text, code):
    # An empty cell is left bare: wrapping "" would emit a pair of escapes that
    # the trailing rstrip can no longer see through.
    return f"{code}{text}{_RESET}" if COLOR and code and text else text


def _status_color(status):
    return _GREEN if status == PASSED else _RED


class Result:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.status = ERROR
        self.passed = 0
        self.total = 0
        self.skipped = 0
        self.duration = 0.0
        self.detail = ""
        self.output = ""
        self.events = []  # the testcase's own timeline, from its recorder
        self.assets = ""  # folder of its screenshots, relative to the report

    @property
    def ok(self):
        return self.status == PASSED


def discover(folder, pattern="test_*.py"):
    """Testcase scripts in `folder`, recursively, in a stable order."""
    found = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", ".git"))
        for name in sorted(files):
            if fnmatch.fnmatch(name, pattern):
                found.append(os.path.join(root, name))
    return found


def run_one(path, serial=None, timeout=600, echo=True, color=None, assets=None, assets_rel=""):
    """Run one testcase in its own process and read its verdict back.

    The testcase's own log is echoed as it arrives when `echo`, so a run that
    takes minutes on a device can be followed live rather than going quiet until
    the table at the end. It is captured either way, for the report.

    `assets` is the folder this testcase may write screenshots into, and
    `assets_rel` the same folder as the report will have to reference it. Both
    are only passed when a report is going to be written, so a `--no-report`
    run does no image work at all.
    """
    result = Result(path)
    env = dict(os.environ)
    if assets:
        result.assets = assets_rel or os.path.basename(assets)
        env["AUTOPLAY_ARTIFACTS"] = os.path.abspath(assets)
    else:
        # The runner's own environment may carry it from an outer run; a
        # testcase must not silently scribble into someone else's folder.
        env.pop("AUTOPLAY_ARTIFACTS", None)
    if serial:
        # A testcase picks the device itself, so the serial is passed the one way
        # that needs no cooperation from the script: ANDROID_SERIAL, which adb
        # honours for every command it runs.
        env["ANDROID_SERIAL"] = serial
    # Testcases print screen text in any language; a cp1252 pipe would otherwise
    # kill them mid-run.
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    # The testcase writes into a pipe, so its own isatty() check says "no colour"
    # however capable this console is. Decide on its behalf from ours.
    if color is not None:
        env["AUTOPLAY_COLOR"] = "1" if color else "0"

    started = time.perf_counter()
    lines = []
    # stderr is merged into stdout rather than read separately: a traceback
    # belongs where it happened in the log, not in a block after it.
    proc = subprocess.Popen(
        [sys.executable, os.path.abspath(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=os.path.dirname(os.path.abspath(path)) or None,
    )
    # The timeout is enforced from a separate thread rather than between lines,
    # because the wedge worth catching is a testcase that stops printing: the
    # read below then blocks, and an in-loop deadline check never runs again.
    expired = threading.Event()

    def watchdog():
        if not finished.wait(timeout):
            expired.set()
            _terminate(proc)

    finished = threading.Event()
    guard = threading.Thread(target=watchdog, daemon=True)
    guard.start()
    try:
        for raw in proc.stdout:
            line = _text(raw).rstrip("\r\n")
            lines.append(line)
            if echo:
                _echo(line)
        proc.wait()
    finally:
        finished.set()
        guard.join(timeout=10)
        proc.stdout.close()

    result.duration = time.perf_counter() - started
    result.output = "\n".join(lines)
    result.events = _read_events(assets)
    if expired.is_set():
        result.status = TIMEOUT
        result.detail = f"no result within {timeout}s"
        return result
    _read_summary(result, result.output, proc.returncode)
    return result


def say(text=""):
    """Print a line even when the console cannot encode it.

    Everything the runner prints can carry text it did not choose: screen text
    quoted in a failure detail, a path, the ellipsis _shorten adds. The
    testcases guard their own prints, but they encode for this process's utf-8
    pipe - this console is often narrower than that.
    """
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(encoding, "replace").decode(encoding), flush=True)


def _echo(line):
    """Reprint a testcase's line under the runner, indented to show the nesting."""
    say(f"    {line}" if line.strip() else "")


def _terminate(proc):
    """Stop a testcase that outstayed its timeout, hard if it ignores the first ask."""
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _read_summary(result, output, returncode):
    """Fill in a result from the testcase's own summary line, or from its crash."""
    for line in reversed(_ANSI.sub("", output).splitlines()):
        match = _SUMMARY.match(line.strip())
        if not match:
            continue
        result.status = PASSED if match.group("status") == PASSED else FAILED
        result.passed = int(match.group("passed"))
        result.total = int(match.group("total"))
        result.skipped = int(match.group("skipped") or 0)
        if result.status == FAILED:
            result.detail = _failure_detail(output) or f"{result.total - result.passed} failed"
        return
    # No summary line at all: the testcase died before it could report - a
    # missing device, an unreadable template, a syntax error.
    result.status = ERROR
    result.detail = _failure_detail(output) or f"exited {returncode} without a summary"


def _failure_detail(output):
    """A one-line reason, taken from the testcase's own output."""
    clean = [_ANSI.sub("", line).strip() for line in output.splitlines()]
    for line in reversed(clean):
        if line.startswith("aborted:"):
            return line[len("aborted:"):].strip()
    for line in reversed(clean):
        if line.startswith("FAIL"):
            return line[len("FAIL"):].strip()
    # A traceback's last line is the exception, which is the useful part.
    for index, line in enumerate(clean):
        if line.startswith("Traceback ("):
            tail = [entry for entry in clean[index:] if entry]
            return tail[-1] if tail else ""
    return ""


def _read_events(directory):
    """The timeline a testcase's recorder left behind, or [] if it left none."""
    if not directory:
        return []
    try:
        with open(os.path.join(directory, "events.json"), encoding="utf-8") as fh:
            return json.load(fh).get("events", [])
    except (OSError, ValueError):
        # A testcase that died before writing one still has its console log.
        return []


def _text(raw):
    if not raw:
        return ""
    if isinstance(raw, str):
        return raw
    return raw.decode("utf-8", "replace")


# -- table ---------------------------------------------------------------


def print_table(results):
    rows = [
        (
            r.name,
            r.status,
            f"{r.passed}/{r.total}" if r.total else "-",
            str(r.skipped) if r.skipped else "-",
            f"{r.duration:.1f}s",
            _shorten(r.detail, 44),
        )
        for r in results
    ]
    headers = ("TESTCASE", "STATUS", "ASSERTS", "SKIP", "TIME", "DETAIL")
    widths = [
        max(len(headers[i]), max((len(row[i]) for row in rows), default=0))
        for i in range(len(headers))
    ]

    def line(cells, styles=()):
        # Padding is measured on the plain text and the colour wrapped around
        # the result, so escape codes never count towards a column's width.
        # The last column is left unpadded: padding it would put a run of
        # trailing spaces inside the escape, which rstrip can no longer reach.
        last = len(cells) - 1
        out = []
        for i, cell in enumerate(cells):
            padded = cell if i == last else cell.ljust(widths[i])
            code = styles[i] if i < len(styles) else None
            out.append(_paint(padded, code) if code else padded)
        return "  ".join(out).rstrip()

    say()
    say(_paint(line(headers), _DIM))
    say(_paint("  ".join("-" * w for w in widths), _DIM))
    for result, row in zip(results, rows):
        say(line(row, (_BOLD, _status_color(result.status), None, None, _DIM, _DIM)))

    failed = [r for r in results if not r.ok]
    say()
    passed = len(results) - len(failed)
    say(
        _paint(f"{passed}/{len(results)} testcases passed", _GREEN if not failed else None)
        + (_paint(f", {len(failed)} failed", _RED) if failed else "")
    )


def _shorten(text, limit):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# -- html report ---------------------------------------------------------


_CSS = """
:root {
  color-scheme: light dark;
  --bg: #ffffff; --fg: #1a1a1a; --muted: #6b7280; --line: #e5e7eb;
  --head: #f6f7f9; --pass: #15803d; --fail: #b91c1c; --warn: #b45309;
  --pass-bg: #eafaf0; --fail-bg: #fdeeee;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14161a; --fg: #e8eaed; --muted: #9aa0a6; --line: #2b2f36;
    --head: #1c1f25; --pass: #4ade80; --fail: #f87171; --warn: #fbbf24;
    --pass-bg: #16261c; --fail-bg: #2a1a1a;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 32px 16px; background: var(--bg); color: var(--fg);
  font: 15px/1.55 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
main { max-width: 1040px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0 0 4px; }
.meta { color: var(--muted); font-size: 13px; margin-bottom: 24px; }
.cards { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }
.card {
  flex: 1 1 130px; border: 1px solid var(--line); border-radius: 10px;
  padding: 12px 14px; background: var(--head);
}
.card b { display: block; font-size: 24px; font-weight: 650; line-height: 1.2; }
.card span { color: var(--muted); font-size: 12px; text-transform: uppercase;
  letter-spacing: .04em; }
.card.pass b { color: var(--pass); }
.card.fail b { color: var(--fail); }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line); }
th { background: var(--head); font-weight: 600; font-size: 12px;
  text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
tr.row-fail { background: var(--fail-bg); }
tr.row-pass { background: var(--pass-bg); }
.tag { font-weight: 650; font-size: 12px; letter-spacing: .03em; }
.tag.PASSED { color: var(--pass); }
.tag.FAILED, .tag.ERROR, .tag.TIMEOUT { color: var(--fail); }
.detail { color: var(--warn); }
details { margin-top: 6px; }
summary { cursor: pointer; color: var(--muted); font-size: 13px; }
pre {
  margin: 8px 0 0; padding: 12px; overflow-x: auto; border-radius: 8px;
  background: var(--head); border: 1px solid var(--line);
  font: 12px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace;
  white-space: pre-wrap; word-break: break-word;
}

/* -- timeline -------------------------------------------------------- */
.steps { list-style: none; margin: 10px 0 0; padding: 0; }
.steps li {
  display: flex; gap: 10px; align-items: baseline; padding: 4px 0 4px 10px;
  border-left: 2px solid var(--line);
}
.steps li.ev-pass { border-left-color: var(--pass); }
.steps li.ev-fail { border-left-color: var(--fail); }
.steps li.ev-skip { border-left-color: var(--warn); }
.steps .at {
  color: var(--muted); font-variant-numeric: tabular-nums; font-size: 12px;
  min-width: 52px; text-align: right; flex: none;
}
.steps .what {
  font: 12.5px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace;
  word-break: break-word;
}
.ev-pass .what, .ev-fail .what, .ev-skip .what {
  font-family: inherit; font-size: 14px; font-weight: 600;
}
.steps .badge {
  flex: none; font-size: 11px; font-weight: 700; letter-spacing: .04em;
  padding: 1px 6px; border-radius: 4px; border: 1px solid currentColor;
}
.ev-pass .badge { color: var(--pass); }
.ev-fail .badge { color: var(--fail); }
.ev-skip .badge { color: var(--warn); }
.steps .why { color: var(--muted); font-size: 13px; }

/* -- screenshots ------------------------------------------------------ */
.shots { display: flex; flex-wrap: wrap; gap: 14px; margin: 8px 0 14px 12px; }
.shots figure { margin: 0; }
.shots figcaption {
  color: var(--muted); font-size: 11px; text-transform: uppercase;
  letter-spacing: .04em; margin-bottom: 4px;
}
.shots img {
  display: block; max-width: 100%; border: 1px solid var(--line);
  border-radius: 6px; background: var(--head);
}
.shots .screen img { width: 300px; }
.shots .close img { max-width: 300px; max-height: 190px; width: auto; }
.shots .want img { max-width: 220px; max-height: 190px; width: auto; }
.shots a { text-decoration: none; }
.shots .want figcaption { color: var(--warn); }

@media (max-width: 640px) {
  body { padding: 20px 12px; }
  th, td { padding: 7px 6px; }
  .shots .screen img { width: 100%; }
}
"""


_BADGE = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}


def _timeline(result):
    """The testcase's steps and assertions, with the pictures each one left."""
    if not result.events:
        return ""
    items = []
    shown = None
    for event in result.events:
        kind = event.get("kind", "step")
        if kind == "end":
            continue
        badge = _BADGE.get(kind)
        why = event.get("detail")
        # An assertion shares its frame with the lookup logged just above it, so
        # the pictures go under whichever came first and the other one just
        # points at it.
        pictures = _pictures(event)
        figures = "" if pictures == shown else _shots(result, event)
        if pictures:
            shown = pictures
        items.append(
            f'<li class="ev-{html.escape(kind)}">'
            f'<span class="at">{event.get("t", 0):.2f}s</span>'
            + (f'<span class="badge">{badge}</span>' if badge else "")
            + f'<span class="what">{html.escape(str(event.get("text", "")))}'
            + (f' <span class="why">- {html.escape(str(why))}</span>' if why else "")
            + "</span></li>"
            + figures
        )
    if not items:
        return ""
    # Open on a failure: the run worth reading step by step is the broken one.
    state = " open" if not result.ok else ""
    return (
        f"<details{state}><summary>steps &amp; screenshots "
        f"({len(items)})</summary><ol class=\"steps\">"
        + "".join(items)
        + "</ol></details>"
    )


def _pictures(event):
    """What this event would show, or None when it has nothing to show."""
    key = (event.get("shot"), event.get("crop"), tuple(event.get("wanted") or ()))
    return key if any(key) else None


def _shots(result, event):
    """The figures for one event: the screen, the close-up, the template."""
    shot, crop = event.get("shot"), event.get("crop")
    wanted = event.get("wanted") or []
    if not (shot or crop or wanted):
        return ""
    figures = []
    if shot:
        figures.append(_figure(result, shot, "screen", "screen"))
    if crop:
        figures.append(_figure(result, crop, "detected element", "close"))
    for index, path in enumerate(wanted):
        label = "looking for" if len(wanted) == 1 else f"looking for #{index + 1}"
        figures.append(_figure(result, path, label, "want"))
    return f'<li><div class="shots">{"".join(figures)}</div></li>'


def _figure(result, path, caption, css):
    src = html.escape(f"{result.assets}/{path}".replace(os.sep, "/"))
    return (
        f'<figure class="{css}"><figcaption>{html.escape(caption)}</figcaption>'
        f'<a href="{src}" target="_blank"><img src="{src}" alt="{html.escape(caption)}" '
        'loading="lazy"></a></figure>'
    )


def write_report(results, path, serial=None, folder=""):
    finished = datetime.datetime.now()
    total = len(results)
    failed = sum(1 for r in results if not r.ok)
    seconds = sum(r.duration for r in results)
    subtitle = " · ".join(
        part
        for part in (
            html.escape(folder) if folder else "",
            f"device {html.escape(serial)}" if serial else "",
            finished.strftime("%Y-%m-%d %H:%M:%S"),
            f"{seconds:.1f}s total",
        )
        if part
    )

    rows = []
    for r in results:
        detail = f'<div class="detail">{html.escape(_shorten(r.detail, 160))}</div>' if r.detail else ""
        log = (
            "<details><summary>console output</summary>"
            f"<pre>{html.escape(_ANSI.sub('', r.output).strip())}</pre></details>"
            if r.output.strip()
            else ""
        )
        rows.append(
            f'<tr class="row-{"pass" if r.ok else "fail"}">'
            f"<td><code>{html.escape(r.name)}</code>{detail}{_timeline(r)}{log}</td>"
            f'<td><span class="tag {r.status}">{r.status}</span></td>'
            f'<td class="num">{f"{r.passed}/{r.total}" if r.total else "-"}</td>'
            f'<td class="num">{r.skipped or "-"}</td>'
            f'<td class="num">{r.duration:.1f}s</td>'
            "</tr>"
        )

    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>auto-play test report</title>
<style>{_CSS}</style>
</head>
<body>
<main>
  <h1>auto-play test report</h1>
  <p class="meta">{subtitle}</p>
  <div class="cards">
    <div class="card"><b>{total}</b><span>testcases</span></div>
    <div class="card pass"><b>{total - failed}</b><span>passed</span></div>
    <div class="card fail"><b>{failed}</b><span>failed</span></div>
  </div>
  <table>
    <thead><tr>
      <th>Testcase</th><th>Status</th><th>Asserts</th><th>Skip</th><th>Time</th>
    </tr></thead>
    <tbody>
{os.linesep.join("      " + row for row in rows)}
    </tbody>
  </table>
</main>
</body>
</html>
"""
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(document)
    return path


# -- cli -----------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python test-runner.py",
        description="Run every testcase in a folder and report the results.",
    )
    parser.add_argument("folder", nargs="?", default="Tests", help="folder of testcase scripts")
    parser.add_argument("-p", "--pattern", default="test_*.py", help="testcase filename pattern")
    parser.add_argument("-s", "--serial", help="adb serial when several devices are attached")
    parser.add_argument("-r", "--report", default="report.html", help="HTML report path")
    parser.add_argument("--no-report", action="store_true", help="skip the HTML report")
    parser.add_argument(
        "-t", "--timeout", type=int, default=600, help="per-testcase timeout in seconds"
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="only the per-testcase verdict, not each testcase's own log",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="colourise output (default: auto, on when writing to a terminal)",
    )
    args = parser.parse_args(argv)

    # Testcase logs carry screen text in any language and arrive here decoded as
    # utf-8; a cp1252 console would replace most of it. Ask stdout to re-encode
    # as utf-8 where it can, and fall back to say()'s replacement where it
    # cannot (a console that genuinely has no glyph for it).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - older/odd streams
        pass

    global COLOR
    # --color is explicit, so it outranks NO_COLOR; auto defers to it. Either
    # way the decision is passed down to the testcases, so the table and the
    # logs under it never disagree.
    COLOR = args.color == "always" or (
        args.color == "auto" and sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    )
    if COLOR:
        _enable_windows_ansi()

    # Screenshots live in a folder beside the report and named after it, so
    # report.html + report_files/ move together and a second report in the same
    # folder cannot overwrite the first one's pictures.
    assets_root = ""
    if not args.no_report:
        assets_root = os.path.splitext(os.path.abspath(args.report))[0] + "_files"

    if not os.path.isdir(args.folder):
        parser.error(f"no such folder: {args.folder}")
    testcases = discover(args.folder, args.pattern)
    if not testcases:
        parser.error(f"no testcases matching {args.pattern!r} in {args.folder}")

    if assets_root:
        # Cleared rather than merged: leftovers from a previous run would show
        # up in this report as steps that never happened.
        shutil.rmtree(assets_root, ignore_errors=True)

    say(f"running {len(testcases)} testcase(s) from {args.folder}")
    results = []
    used = {}
    for index, path in enumerate(testcases, 1):
        say()
        say(_paint(f"[{index}/{len(testcases)}]", _DIM) + " " + _paint(path, _BOLD))
        assets = assets_rel = ""
        if assets_root:
            # Two folders can hold a testcase of the same name, so a repeat gets
            # a suffix rather than quietly overwriting the first one's shots.
            name = os.path.splitext(os.path.basename(path))[0]
            used[name] = used.get(name, 0) + 1
            if used[name] > 1:
                name = f"{name}-{used[name]}"
            assets = os.path.join(assets_root, name)
            assets_rel = f"{os.path.basename(assets_root)}/{name}"
        result = run_one(
            path,
            serial=args.serial,
            timeout=args.timeout,
            echo=not args.quiet,
            color=COLOR,
            assets=assets,
            assets_rel=assets_rel,
        )
        tag = _paint(result.status, _status_color(result.status))
        if not result.ok and result.detail:
            tag += f"  {_shorten(result.detail, 70)}"
        say(f"    -> {tag}  {_paint(f'({result.duration:.1f}s)', _DIM)}")
        results.append(result)

    print_table(results)
    if not args.no_report:
        path = write_report(results, args.report, serial=args.serial, folder=args.folder)
        say(f"report: {os.path.abspath(path)}")
    return 1 if any(not r.ok for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
