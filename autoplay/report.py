"""Artifacts for the HTML report: what a testcase did, and what the screen
looked like where it went wrong.

Recording is off unless AUTOPLAY_ARTIFACTS names a directory. The test runner
sets it per testcase when it is going to write a report, so a testcase run by
hand pays nothing - no frame copies, no JPEG encoding, no folder appearing
beside the script.

Nothing here may change a verdict. A screenshot that cannot be written is a
missing picture in the report, not a failed testcase, so every entry point
swallows its own errors.
"""

import json
import os
import shutil
import time

import cv2

# The long edge of a saved screen. Full frames are ~1200px and a report holds
# one per assertion; half that is still readable at a glance and clicks through
# to the original at the size it was matched on.
SHOT_WIDTH = 760
JPEG_QUALITY = 82

# A close-up is kept at the size it was matched on, which is the point of it -
# but an element covering most of the screen would then be a second full frame,
# and as lossless PNG the larger of the two files. Past this it is a picture of
# the screen, not of an element, so it is saved like one.
CROP_LIMIT = 560

_FOUND = (80, 220, 90)  # BGR - the box drawn round what was matched


class Recorder:
    """Collects one testcase's steps and screenshots into a directory."""

    def __init__(self, directory, testcase=""):
        self.directory = directory
        self.testcase = testcase
        self.started = time.time()
        self.events = []
        self._count = 0
        self._last = None  # (frame, key, paths) - see `snapshot`
        self._shots = os.path.join(directory, "shots")
        os.makedirs(self._shots, exist_ok=True)

    @classmethod
    def open(cls, testcase=""):
        """A Recorder if the runner asked for artifacts, otherwise None."""
        directory = os.environ.get("AUTOPLAY_ARTIFACTS")
        if not directory:
            return None
        try:
            return cls(directory, testcase)
        except OSError:  # pragma: no cover - unwritable path, keep the run going
            return None

    # -- events ----------------------------------------------------------

    def record(self, kind, text, **extra):
        """Add one entry to the timeline. `kind` is step/pass/fail/skip/end."""
        try:
            event = {"t": round(time.time() - self.started, 2), "kind": kind, "text": text}
            event.update({k: v for k, v in extra.items() if v})
            self.events.append(event)
            self._flush()
        except Exception:  # noqa: BLE001 - never break a testcase over a log
            pass

    def attach(self, **paths):
        """Hang pictures on the event just recorded."""
        if self.events and paths:
            self.events[-1].update(paths)
            self._flush()

    def finish(self, passed, failed, skips, aborted=None):
        self.record(
            "end",
            self.testcase,
            passed=passed,
            failed=failed,
            skipped=skips,
            aborted=aborted,
        )

    def _flush(self):
        payload = {
            "testcase": self.testcase,
            "started": self.started,
            "events": self.events,
        }
        # Rewritten after every event rather than once at the end: a testcase
        # that dies mid-run is exactly the one whose timeline is worth having.
        with open(os.path.join(self.directory, "events.json"), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)

    # -- pictures --------------------------------------------------------

    def snapshot(self, frame, boxes=(), templates=(), tag="shot"):
        """Save the screen, a close-up of what was matched, and what was sought.

        Returns the paths as a dict to hand to `record`, relative to this
        testcase's directory so the report can reference them wherever it is
        written.

        Consecutive identical shots are written once and referenced twice. An
        assertion is usually made on the lookup logged immediately above it -
        `alert(findText("Continue"))` - and re-encoding the same frame would
        cost a second and put the same picture in the report twice.
        """
        try:
            key = (_key(boxes), tuple(templates))
            if self._last is not None:
                previous, last_key, paths = self._last
                if last_key == key and previous is frame:
                    return dict(paths)
            paths = self._snapshot(frame, boxes, templates, tag)
            # The frame is kept alive by this reference, so the `is` test above
            # cannot be fooled by a new array landing on a freed address.
            self._last = (frame, key, paths)
            return dict(paths)
        except Exception:  # noqa: BLE001
            return {}

    def _snapshot(self, frame, boxes, templates, tag):
        if frame is None:
            return {}
        self._count += 1
        stem = f"{self._count:03d}-{_slug(tag)}"
        out = {}

        boxes = [_ints(b) for b in boxes if b]
        out["shot"] = self._write(f"{stem}.jpg", _fit(_draw(frame, boxes), SHOT_WIDTH))
        # The close-up is the answer to "what did it actually match?", so it is
        # kept at the size it was matched on rather than scaled with the screen.
        if boxes:
            close = _crop(frame, boxes[0])
            if max(close.shape[:2]) > CROP_LIMIT:
                out["crop"] = self._write(f"{stem}-crop.jpg", _fit(close, CROP_LIMIT))
            else:
                out["crop"] = self._write(f"{stem}-crop.png", close)
        wanted = [p for p in (self._copy(path, stem, i) for i, path in enumerate(templates)) if p]
        if wanted:
            out["wanted"] = wanted
        return out

    def _write(self, name, image):
        path = os.path.join(self._shots, name)
        params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY] if name.endswith(".jpg") else []
        if not cv2.imwrite(path, image, params):
            return None
        return f"shots/{name}"

    def _copy(self, source, stem, index):
        """Put the template image that was being looked for beside the screen."""
        try:
            name = f"{stem}-want{index + 1}{os.path.splitext(source)[1] or '.png'}"
            shutil.copyfile(source, os.path.join(self._shots, name))
            return f"shots/{name}"
        except OSError:
            return None


# -- image helpers -------------------------------------------------------


def _key(boxes):
    return tuple(_ints(b) for b in boxes if b)


def _ints(bounds):
    x1, y1, x2, y2 = bounds
    return int(x1), int(y1), int(x2), int(y2)


def _draw(image, boxes):
    """Outline what was matched, so the screen shows where the step landed."""
    if not boxes:
        return image
    out = image.copy()
    thickness = max(2, round(max(out.shape[:2]) / 350))
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(out, (x1, y1), (x2, y2), _FOUND, thickness)
    return out


def _fit(image, longest):
    h, w = image.shape[:2]
    if max(h, w) <= longest:
        return image
    scale = longest / float(max(h, w))
    size = (max(1, int(w * scale)), max(1, int(h * scale)))
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA)


def _crop(image, bounds, margin=0.3):
    """The element plus a rim of its surroundings.

    A crop cut exactly to the match is hard to place on the screen it came
    from; a margin proportional to the element keeps enough context to
    recognise it, with a floor for the ones only a few pixels tall.
    """
    h, w = image.shape[:2]
    x1, y1, x2, y2 = bounds
    mx = int(max(14, (x2 - x1) * margin))
    my = int(max(14, (y2 - y1) * margin))
    x1 = max(0, x1 - mx)
    y1 = max(0, y1 - my)
    x2 = min(w, x2 + mx)
    y2 = min(h, y2 + my)
    if x2 <= x1 or y2 <= y1:
        return image
    return image[y1:y2, x1:x2]


def _slug(text):
    keep = [c if c.isalnum() or c in "-_" else "-" for c in str(text).strip().lower()]
    return "".join(keep).strip("-")[:40] or "shot"
