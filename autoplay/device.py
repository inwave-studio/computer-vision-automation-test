"""ADB device control: app lifecycle, touch input, screen geometry."""

import os
import re
import subprocess
import time

# `mCurrentFocus=Window{acf7a3a u0 com.pkg/com.pkg.SomeActivity}` -> "com.pkg/com.pkg.SomeActivity".
# The line reads `mCurrentFocus=null` when that display has no focused window,
# which this deliberately does not match - see `focused_activity`.
_FOCUS = re.compile(r"mCurrentFocus=Window\{[^}]*\s(\S+/\S+?)\}")


class AdbError(RuntimeError):
    pass


class Device:
    def __init__(self, serial=None, adb="adb"):
        self.adb = adb
        self.serial = serial or self._pick_serial()
        self.width, self.height = self._screen_size()

    # -- adb plumbing ----------------------------------------------------

    def _base_cmd(self):
        cmd = [self.adb]
        if self.serial:
            cmd += ["-s", self.serial]
        return cmd

    def run(self, *args, binary=False, timeout=30):
        """Run an adb subcommand and return its output."""
        proc = subprocess.run(
            self._base_cmd() + list(args),
            capture_output=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", "replace").strip()
            raise AdbError(f"adb {' '.join(args)} failed: {err}")
        return proc.stdout if binary else proc.stdout.decode("utf-8", "replace")

    def shell(self, *args, **kwargs):
        return self.run("shell", *args, **kwargs)

    def popen(self, *args):
        return subprocess.Popen(
            self._base_cmd() + list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def forward(self, local, remote):
        self.run("forward", local, remote)

    def forward_remove(self, local):
        try:
            self.run("forward", "--remove", local)
        except AdbError:
            pass

    def push(self, local, remote):
        self.run("push", local, remote)

    # -- discovery -------------------------------------------------------

    def _pick_serial(self):
        # adb itself honours ANDROID_SERIAL, so respect it here too rather than
        # refusing to choose when several devices are attached. It is how the
        # test runner tells a testcase subprocess which device to drive.
        from_env = os.environ.get("ANDROID_SERIAL", "").strip()
        if from_env:
            return from_env
        out = subprocess.run(
            [self.adb, "devices"], capture_output=True, timeout=30
        ).stdout.decode("utf-8", "replace")
        serials = [
            line.split("\t")[0]
            for line in out.splitlines()[1:]
            if line.strip() and line.endswith("\tdevice")
        ]
        if not serials:
            raise AdbError("no adb device connected (check `adb devices`)")
        if len(serials) > 1:
            raise AdbError(
                f"multiple devices connected: {serials}. Pass serial= to select one."
            )
        return serials[0]

    def _screen_size(self):
        out = self.shell("wm", "size")
        # "Physical size: 1080x1920" (possibly followed by an Override size line)
        size = None
        for line in out.splitlines():
            if ":" in line and "x" in line:
                value = line.split(":", 1)[1].strip()
                try:
                    w, h = (int(v) for v in value.split("x"))
                except ValueError:
                    continue
                size = (w, h)
                if line.strip().startswith("Override"):
                    break  # override wins when present
        if size is None:
            raise AdbError(f"cannot parse screen size from: {out!r}")
        return size

    # -- app lifecycle ---------------------------------------------------

    def open_app(self, app_id):
        self.shell(
            "monkey", "-p", app_id, "-c", "android.intent.category.LAUNCHER", "1"
        )

    def kill_app(self, app_id):
        self.shell("am", "force-stop", app_id)

    def clear_app(self, app_id):
        out = self.shell("pm", "clear", app_id)
        if "Success" not in out:
            raise AdbError(f"pm clear {app_id} failed: {out.strip()}")

    def home(self):
        self.shell("input", "keyevent", "3")

    # -- input -----------------------------------------------------------

    def tap(self, x, y):
        self.shell("input", "tap", str(int(x)), str(int(y)))

    def double_tap(self, x, y, gap=0.08):
        self.tap(x, y)
        time.sleep(gap)
        self.tap(x, y)

    def multi_tap(self, x, y, count, interval=0.0):
        """Tap the same point `count` times, `interval` seconds apart.

        Returns the measured span in ms. The taps are chained inside one adb
        shell so the sequence pays the ~50ms round-trip once instead of per
        tap; the device's own `sleep` does the spacing, which also keeps the
        gaps off the host's clock. `input` is a Java binary and takes tens of
        ms to start, so a very short requested interval cannot be honoured -
        hence returning what actually happened rather than what was asked.
        """
        x, y = int(x), int(y)
        count = max(1, int(count))
        tap = f"input tap {x} {y}"
        gap = f" && sleep {interval:.3f} && " if interval > 0 else " && "
        started = time.perf_counter()
        # Long chains are split up: a single adb shell command line has a
        # practical length limit, and one 20-tap batch per call stays well
        # inside it while still amortising the round-trip.
        for batch in _batches(count, 20):
            self.shell(gap.join([tap] * batch), timeout=60)
            if interval > 0 and batch != count:
                time.sleep(interval)
        return (time.perf_counter() - started) * 1000.0

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        self.shell(
            "input",
            "swipe",
            str(int(x1)),
            str(int(y1)),
            str(int(x2)),
            str(int(y2)),
            str(int(duration_ms)),
        )

    def screencap(self):
        """Fallback single-frame capture (PNG bytes) when no video stream is up."""
        return self.run("exec-out", "screencap", "-p", binary=True)

    # -- what is on top --------------------------------------------------

    def focused_activity(self):
        """The `package/activity` that currently has window focus, or "".

        The grep runs on the device rather than here: the full `dumpsys window`
        is ~90KB and this is polled in a loop, while the two lines that matter
        come back in about a hundred bytes.

        A device with more than one display reports a focus line per display,
        and the ones for displays with nothing on them read `null` - on the
        measured device the *first* line is null and the real answer is further
        down. So the last line that names a window wins; taking the first would
        read `null` and conclude nothing is on screen.
        """
        try:
            out = self.shell("dumpsys window | grep mCurrentFocus", timeout=15)
        except (AdbError, subprocess.SubprocessError):
            # Ad detection must never be the thing that fails a testcase: a
            # dropped adb call means "cannot tell", which reads as no ad.
            return ""
        found = ""
        for line in out.splitlines():
            match = _FOCUS.search(line)
            if match:
                found = match.group(1)
        return found


def _batches(total, size):
    """Split `total` into chunks of at most `size`."""
    while total > 0:
        chunk = min(size, total)
        yield chunk
        total -= chunk
