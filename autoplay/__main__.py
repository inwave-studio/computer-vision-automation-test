"""Command-line runner:  python -m autoplay Tests/test_x.py [more_tests.py ...]

Testcases are plain Python scripts, so they also run directly with
`python Tests/test_x.py`. This runner adds batch execution and an exit code
that reflects whether every testcase passed.
"""

import argparse
import os
import runpy
import sys
import traceback

from .log import step
from .session import TestFailure


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m autoplay",
        description="Run auto-play testcase scripts against a connected Android device.",
    )
    parser.add_argument("testcases", nargs="+", help="testcase script(s) to run")
    parser.add_argument("-s", "--serial", help="adb serial when several devices are attached")
    args = parser.parse_args(argv)

    failures = []
    for path in args.testcases:
        if not os.path.exists(path):
            print(f"no such testcase: {path}", file=sys.stderr)
            failures.append(path)
            continue
        if not _run_one(path, args.serial):
            failures.append(path)

    if len(args.testcases) > 1:
        passed = len(args.testcases) - len(failures)
        print(f"\n{passed}/{len(args.testcases)} testcases passed", flush=True)
    return 1 if failures else 0


def _run_one(path, serial):
    import autoplay

    # Each testcase gets a fresh implicit session.
    autoplay._session = None
    # runpy does not replace sys.modules["__main__"], so the session cannot infer
    # the testcase name or its directory by itself here - pass both explicitly.
    autoplay._config = {
        "testcase": os.path.basename(path),
        "base_dir": os.path.dirname(os.path.abspath(path)),
    }
    if serial:
        autoplay._config["serial"] = serial

    step(f"runner: {path}")
    saved_argv = sys.argv
    sys.argv = [path]
    error = None
    try:
        runpy.run_path(path, run_name="__main__")
    except TestFailure as exc:
        error = exc
        print(f"  {exc}", file=sys.stderr, flush=True)
    except Exception as exc:  # noqa: BLE001 - one bad testcase must not stop the batch
        error = exc
        traceback.print_exc()
    finally:
        sys.argv = saved_argv

    active = autoplay._session
    if active is None:
        return error is None
    active.close(error=error)
    return active.failed == 0 and error is None


if __name__ == "__main__":
    sys.exit(main())
