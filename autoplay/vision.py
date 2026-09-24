"""OpenCV template matching and OCR over screen frames."""

import os
import threading
import unicodedata

import cv2
import numpy as np

DEFAULT_MATCH_THRESHOLD = 0.75
DEFAULT_TEXT_THRESHOLD = 0.5
# Edge matching (findLayout) scores outline agreement, not pixel similarity, so
# it needs its own threshold. Measured on a 544x1200 device frame, sweeping the
# whole element database against a screen holding none of it: absent elements
# peaked at 0.54, while regions genuinely present scored 0.94-1.00. 0.75 sits in
# the middle of that gap.
DEFAULT_EDGE_THRESHOLD = 0.75

# Matching modes: MODE_TEMPLATE compares pixels (find), MODE_EDGE compares
# Canny edge maps (findLayout), which ignores colour and fill and keys on the
# element's shape instead (design.md task 8).
MODE_TEMPLATE = "template"
MODE_EDGE = "edge"

# Canny thresholds for edge matching. Deliberately loose: a UI element's outline
# is high-contrast, and a tight pair of thresholds drops the fainter inner
# strokes that tell two similar layouts apart.
EDGE_LOW = 60
EDGE_HIGH = 180
# How far, in pixels, an outline may sit from where the template puts it and
# still count as the same outline.
#
# Correlating two binary edge maps directly does not work, and this is why.
# Canny draws one-pixel-wide strokes, so a template resampled to a slightly
# different scale lands its strokes a pixel off the screen's and the overlap
# collapses - measured, a crop of the frame scored only 0.62 against the very
# frame it was cut from, at its own native scale. Scoring against a distance
# field instead of the raw map makes a near-miss nearly a hit, which is what
# comparing outlines was supposed to mean. 2px is about the misalignment a
# resample introduces; much more and separate strokes start merging.
EDGE_TOLERANCE = 2.0
# Fewest screen edge pixels a window must hold before it can score at all.
#
# The precision half of the score divides by them, so an empty patch of screen
# would otherwise divide by nothing and read as a flawless match - the same
# degeneracy MIN_EDGE_PIXELS guards on the template side.
MIN_WINDOW_EDGE_PIXELS = 20
# Fewest edge pixels an edge template must keep to be matched at all.
#
# This guard is not an optimisation, it is a correctness fix. Shrinking a
# template blurs its strokes away, and past a point Canny returns a frame with
# no edges at all - measured empty at scale 0.12 and below for a 460px-wide
# crop. An outline score divides by the strokes it is comparing, so a blank
# template divides by nothing and scores a perfect 1.0 *everywhere*; being
# perfect it then wins the scale sweep outright, and findLayout would report a
# confident match, at a meaningless size, on any screen at all. Scales that
# degenerate are skipped instead.
MIN_EDGE_PIXELS = 40
# Smallest an edge template may be scaled to, on its *shortest* side.
#
# Both larger than MIN_TEMPLATE_PX and measured against the other side, for the
# same reason. An edge map is mostly empty, so a heavily shrunk one keeps just a
# few strokes - and a few strokes correlate strongly with the first bit of UI
# furniture they meet. Every false positive measured here came from a wide, flat
# template shrunk until it was a sliver: a 951x163 banner at scale 0.1 is
# 95x16, which the blank-template guard above happily passes because a 95px-wide
# strip still holds edge pixels. Flooring the longest side does not catch that
# case at all; flooring the shortest side is what keeps a template recognisable.
# Measured over the element database against a screen holding none of it, 80
# drops the strongest false positive to 0.54 while genuine matches stay at 0.94
# and above - they peak near their natural scale, not at a tenth of it.
MIN_EDGE_TEMPLATE_PX = 80

# Templates are often captured on a differently-sized screen, so every pattern
# is searched across a range of scales. The winning scale is cached per element
# because a full sweep costs seconds, while a single scale costs milliseconds.
SCALE_MIN = 0.4
SCALE_MAX = 2.6
# The sweep is geometric, not linear: a fixed 0.1 step is a 6% change at scale
# 1.6 but a 33% jump at scale 0.3, which steps clean over the peak on a
# reduced-resolution stream. A constant ratio samples every scale equally well.
#
# It runs coarse-then-fine. Sampling the whole range finely enough to land on
# the peak costs ~47 matchTemplate calls per variant - seconds of work, longer
# than the timeout the caller is waiting inside. A wide ratio locates the peak
# in ~19, then a narrow sweep around the winner pins it down, for the same
# answer at a fraction of the cost (design.md task 3).
COARSE_RATIO = 1.15
PEAK_RATIO = 1.03
# How far either side of the coarse winner the fine pass looks. One coarse step
# each way, so the true peak is inside the window wherever it fell.
PEAK_SPAN = COARSE_RATIO
REFINE_STEP = 0.025
REFINE_SPAN = 0.15
# Fraction of each side trimmed off the border-trimmed template variant.
BORDER_TRIM = 0.18
# Smallest a template may be scaled to, on its *shortest* side. The sweep floor
# is derived from this rather than fixed, so a reduced-resolution stream can
# still reach the scale its templates need (design.md task 3).
#
# Measured on the shortest side, for the reason MIN_EDGE_TEMPLATE_PX already
# gives: flooring the longest side leaves a wide template free to collapse into
# a sliver. A 951x163 banner was being matched at 24x4 pixels, and four pixels
# of height fit anywhere on any screen. 40 is what the database can afford -
# every element here stays reachable on a 760x344 frame, the widest templates
# with room to spare - while the two that were degenerating (a 736x934 full
# screen at 19x24, that banner at 24x4) are held at 40x50 and 233x40.
MIN_TEMPLATE_PX = 40


class Element:
    """A rectangle found on screen, with the info needed to tap it."""

    def __init__(self, x, y, width, height, score=1.0, label="", text=""):
        self.x = int(x)
        self.y = int(y)
        self.width = int(width)
        self.height = int(height)
        self.score = float(score)
        self.label = label
        self.text = text

    @property
    def center(self):
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def bounds(self):
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    def __repr__(self):
        name = self.label or (f"text {self.text!r}" if self.text else "element")
        cx, cy = self.center
        return f"<Element {name} at ({cx},{cy}) score={self.score:.2f}>"

    def __bool__(self):
        return True


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    iw = max(0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / float(area_a + area_b - inter)


def _non_max_suppress(elements, overlap=0.3):
    """Drop boxes that mostly cover a better-scoring one.

    Vectorised over numpy rather than comparing every pair in Python. A weak
    threshold on a busy screen puts six figures of boxes in here - a full-screen
    template matched at every position clears 160k - and the pairwise form is
    quadratic in that: the same frame that takes 0.2s to match spent 103s being
    suppressed.
    """
    if len(elements) < 2:
        return list(elements)
    order = sorted(range(len(elements)), key=lambda i: -elements[i].score)
    boxes = np.array([elements[i].bounds for i in order], dtype=np.float64)
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)

    kept = []
    alive = np.ones(len(order), dtype=bool)
    for position in range(len(order)):
        if not alive[position]:
            continue
        kept.append(elements[order[position]])
        rest = alive.copy()
        rest[: position + 1] = False
        if not rest.any():
            break
        # Everything still standing is compared to this box in one pass.
        iw = np.maximum(0.0, np.minimum(x2[position], x2[rest]) - np.maximum(x1[position], x1[rest]))
        ih = np.maximum(0.0, np.minimum(y2[position], y2[rest]) - np.maximum(y1[position], y1[rest]))
        inter = iw * ih
        union = areas[position] + areas[rest] - inter
        with np.errstate(divide="ignore", invalid="ignore"):
            iou = np.where(union > 0, inter / union, 0.0)
        alive[rest] = iou <= overlap
    return kept


def template_paths(entry):
    """The image path(s) a database entry names.

    An element may look several different ways - the same close button drawn as
    a bare x on one popup and a circled x on another - so an entry is either one
    path or a list of paths, each a variant of the same element
    (design.md task 7).
    """
    if isinstance(entry, str):
        return [entry]
    if isinstance(entry, dict):
        # {"variants": [...]} keeps room for per-element options later.
        return template_paths(entry.get("variants") or entry.get("path") or [])
    if isinstance(entry, (list, tuple)):
        paths = []
        for item in entry:
            paths.extend(template_paths(item))
        return paths
    raise TypeError(f"element database entry must be a path or a list of paths, got {entry!r}")


class TemplateMatcher:
    def __init__(self, database, base_dir=".", threshold=DEFAULT_MATCH_THRESHOLD):
        self.database = database
        self.base_dir = base_dir
        self.threshold = threshold
        self._images_cache = {}
        self._variants_cache = {}
        self._scale_cache = {}

    def variant_count(self, element_id):
        """How many images the database lists for this element."""
        return len(template_paths(self._entry(element_id)))

    def template_files(self, element_id):
        """Absolute paths of the images this element is matched against.

        The report shows them beside the screen when a lookup fails, which is
        the comparison that answers "is the template wrong, or the screen?".
        """
        try:
            paths = template_paths(self._entry(element_id))
        except (KeyError, TypeError):
            return []
        return [
            p if os.path.isabs(p) else os.path.join(self.base_dir, p) for p in paths
        ]

    # -- templates -------------------------------------------------------

    def _entry(self, element_id):
        if element_id not in self.database:
            raise KeyError(
                f"element id {element_id!r} is not in the element database "
                f"(known: {sorted(self.database)})"
            )
        return self.database[element_id]

    def _images(self, element_id):
        """Every variant image the database lists for this element, as (bgr, mask)."""
        if element_id in self._images_cache:
            return self._images_cache[element_id]
        images = []
        for path in template_paths(self._entry(element_id)):
            images.append(self._read(path, element_id))
        if not images:
            raise FileNotFoundError(f"element {element_id!r} lists no template image")
        self._images_cache[element_id] = images
        return images

    def _read(self, path, element_id):
        if not os.path.isabs(path):
            path = os.path.join(self.base_dir, path)
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise FileNotFoundError(f"cannot read template image {path!r} for {element_id!r}")
        mask = None
        if img.ndim == 3 and img.shape[2] == 4:
            alpha = img[:, :, 3]
            img = img[:, :, :3]
            if alpha.min() < 255:
                # Only build a mask when the template is genuinely transparent.
                mask = cv2.cvtColor(alpha, cv2.COLOR_GRAY2BGR)
        return img, mask

    def _variants(self, element_id, mode=MODE_TEMPLATE):
        """Everything worth matching for this element: each database variant,
        plus a border-trimmed copy of it.

        Two different things are both called a variant here, and both end up in
        this flat list because the matcher picks between them the same way:

        - Database variants (design.md task 7): genuinely different artwork for
          the same element, listed by the user.
        - A border-trimmed copy of each. Templates are usually cropped from a
          screenshot, so they carry a rim of whatever background sat behind the
          element. Against a different background that rim drags the correlation
          score down - badly enough to lose real matches. Trimming the border
          removes the contamination.

        In MODE_EDGE the images are reduced to greyscale here and to Canny edges
        after scaling; edges survive a resize far worse than the greyscale they
        are computed from. Edge mode also skips the border-trimmed copies: the
        rim they exist to remove is a *colour* problem, while the element's
        outline - the one thing edge matching has to work with - runs right
        along that border, so trimming throws away the signal and keeps the
        noise - and when it was still in, the trimmed copies produced the single
        worst false positive in the database.
        """
        cache_key = (element_id, mode)
        if cache_key in self._variants_cache:
            return self._variants_cache[cache_key]
        variants = []
        for image, mask in self._images(element_id):
            if mode == MODE_EDGE:
                variants.append((_to_gray(image), _to_gray(mask)))
                continue
            variants.append((image, mask))
            # A masked template is not trimmed. The trim exists to remove a rim
            # of background the crop caught by accident, but an alpha channel
            # has already said which pixels count - and on the one template
            # here that has a real one, the transparency *was* the border, so
            # trimming handed back a 472x598 block that was 99.8% opaque and
            # scored 0.918 on a screen the element is not on, against 0.825 on
            # the screen it is. The trimmed copy was the false positive, not
            # the cure for one.
            if mask is not None:
                continue
            trimmed = _border_trim(image, mask)
            if trimmed is not None:
                variants.append(trimmed)
        self._variants_cache[cache_key] = variants
        return variants

    # -- scales ----------------------------------------------------------

    def _scale_bounds(self, template_shape, screen_shape, mode=MODE_TEMPLATE):
        """Scale range worth sweeping for this template against this frame.

        A fixed floor breaks reduced-resolution streams: a 140px template
        captured at 1080 has to shrink to ~0.27 to match a 640-wide frame,
        which a 0.4 floor can never reach. So the floor follows the frame -
        while keeping the template big enough to still carry detail.

        The two modes measure "big enough" on different sides of the template;
        see MIN_EDGE_TEMPLATE_PX. When the floor a mode asks for is above the
        ceiling the frame allows, the range collapses and the element simply
        cannot be matched on a frame this size - which is the right answer, not
        a reason to relax the floor.
        """
        th, tw = template_shape[:2]
        sh, sw = screen_shape[:2]
        # Never shrink a template below this many pixels on its shortest side;
        # past that there is not enough structure left to match reliably. Edge
        # matching needs far more of the template left than pixel matching.
        if mode == MODE_EDGE:
            floor = MIN_EDGE_TEMPLATE_PX / float(min(th, tw))
        else:
            floor = MIN_TEMPLATE_PX / float(min(th, tw))
        # No point scaling a template past the frame that has to contain it.
        ceiling = min(SCALE_MAX, min(sh / float(th), sw / float(tw)))
        if floor > ceiling:
            return None
        return max(min(SCALE_MIN, floor), floor), ceiling

    def _scales(self, cache_key, screen_shape, template_shape, mode=MODE_TEMPLATE):
        """Scales to try when the cached one missed - a wide geometric sweep."""
        bounds = self._scale_bounds(template_shape, screen_shape, mode)
        if bounds is None:
            return []
        lo_bound, hi_bound = bounds
        entry = self._scale_cache.get(cache_key)
        if entry is not None:
            cached = entry[1]
            lo = max(lo_bound, cached - REFINE_SPAN)
            hi = min(hi_bound, cached + REFINE_SPAN)
            fine = list(np.arange(lo, hi + 1e-9, REFINE_STEP))
            # Try the cached scale first so a hit costs one matchTemplate call.
            return [cached] + [s for s in fine if abs(s - cached) > 1e-9]
        return _geometric(lo_bound, hi_bound, COARSE_RATIO)

    def _around(self, scale, screen_shape, template_shape, mode=MODE_TEMPLATE):
        """Fine scales bracketing a coarse winner, to pin down the real peak."""
        bounds = self._scale_bounds(template_shape, screen_shape, mode)
        if bounds is None:
            return []
        lo_bound, hi_bound = bounds
        lo = max(lo_bound, scale / PEAK_SPAN)
        hi = min(hi_bound, scale * PEAK_SPAN)
        return [s for s in _geometric(lo, hi, PEAK_RATIO) if abs(s - scale) > 1e-9]

    # -- matching --------------------------------------------------------

    def find(self, screen, element_id, threshold=None, max_results=0, mode=MODE_TEMPLATE):
        """Return all on-screen matches of a database element, best score first.

        `mode` picks what is compared: MODE_TEMPLATE correlates pixels,
        MODE_EDGE correlates Canny edge maps of both sides, which keys on the
        element's outline rather than its colours (design.md task 8).
        """
        if threshold is None:
            threshold = DEFAULT_EDGE_THRESHOLD if mode == MODE_EDGE else self.threshold
        variants = self._variants(element_id, mode)
        haystack = _haystack(screen, mode)
        key = (element_id, mode, haystack.shape[:2])
        cached = self._scale_cache.get(key)

        # A cached (variant, scale) pair usually still holds; try it before sweeping.
        if cached is not None:
            index, scale = cached
            elements = self._collect(haystack, variants[index], scale, threshold, element_id, mode)
            if elements:
                return self._finish(elements, max_results)

        best = None  # (score, variant index, scale)
        swept = 0
        for index, variant in enumerate(variants):
            scales = self._scales(key, haystack.shape[:2], variant[0].shape, mode)
            swept = max(swept, len(scales))
            for scale in scales:
                peak = self._peak(haystack, variant, scale, mode)
                if peak is not None and (best is None or peak > best[0]):
                    best = (peak, index, float(scale))

        # The coarse pass only gets near the peak; walk in around the winner so
        # the cached scale is the real best rather than whichever sample landed
        # closest to it.
        if best is not None and swept > 1:
            _, index, scale = best
            variant = variants[index]
            for fine in self._around(scale, haystack.shape[:2], variant[0].shape, mode):
                peak = self._peak(haystack, variant, fine, mode)
                if peak is not None and peak > best[0]:
                    best = (peak, index, float(fine))

        if best is None or best[0] < threshold:
            return []

        _, index, scale = best
        self._scale_cache[key] = (index, scale)
        elements = self._collect(haystack, variants[index], scale, threshold, element_id, mode)
        return self._finish(elements, max_results)

    def find_layout(self, screen, element_id, threshold=None, max_results=0):
        """find() by outline instead of by pixels - see design.md task 8."""
        return self.find(
            screen, element_id, threshold=threshold, max_results=max_results, mode=MODE_EDGE
        )

    def _peak(self, screen, variant, scale, mode=MODE_TEMPLATE):
        """Best correlation this variant reaches at this scale, or None if unusable."""
        scaled, scaled_mask = self._prepare(variant, scale, mode)
        if not self._fits(scaled, screen):
            return None
        return float(self._match(screen, scaled, scaled_mask).max())

    def _collect(self, screen, variant, scale, threshold, element_id, mode=MODE_TEMPLATE):
        scaled, scaled_mask = self._prepare(variant, scale, mode)
        if not self._fits(scaled, screen):
            return []
        result = self._match(screen, scaled, scaled_mask)
        h, w = scaled.shape[:2]
        return [
            Element(x, y, w, h, score=float(result[y, x]), label=element_id)
            for y, x in zip(*np.where(result >= threshold))
        ]

    def _prepare(self, variant, scale, mode):
        """Scale a variant to size, then reduce it to what `mode` compares.

        Returns (None, None) for a scale this variant cannot be matched at.
        """
        scaled, scaled_mask = self._resize(variant[0], variant[1], scale)
        if scaled is None or mode != MODE_EDGE:
            return scaled, scaled_mask
        edges = cv2.Canny(scaled, EDGE_LOW, EDGE_HIGH)
        if scaled_mask is not None:
            # Edges along the cut-out boundary are an artefact of the crop, not
            # of the element, so drop everything the alpha channel excludes.
            edges = cv2.bitwise_and(edges, edges, mask=(scaled_mask > 0).astype(np.uint8))
        if cv2.countNonZero(edges) < MIN_EDGE_PIXELS:
            return None, None  # too little structure left to mean anything
        # A masked matchTemplate over binary edges divides by near-zero energy
        # and returns noise, so the mask has done its job here and stops.
        return edges, None

    @staticmethod
    def _fits(template, screen):
        return (
            template is not None
            and template.shape[0] <= screen.shape[0]
            and template.shape[1] <= screen.shape[1]
        )

    @staticmethod
    def _finish(elements, max_results):
        kept = _non_max_suppress(elements)
        kept.sort(key=lambda e: -e.score)
        return kept[:max_results] if max_results else kept

    @staticmethod
    def _resize(template, mask, scale):
        if abs(scale - 1.0) < 1e-9:
            return template, mask
        interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        scaled = cv2.resize(template, None, fx=scale, fy=scale, interpolation=interp)
        if scaled.shape[0] < 4 or scaled.shape[1] < 4:
            return None, None
        scaled_mask = None
        if mask is not None:
            scaled_mask = cv2.resize(mask, (scaled.shape[1], scaled.shape[0]), interpolation=interp)
        return scaled, scaled_mask

    @staticmethod
    def _match(screen, template, mask):
        if isinstance(screen, EdgeField):
            return screen.score(template)
        if mask is not None:
            # CCOEFF, not CCORR, for the same reason the unmasked path uses it:
            # CCORR is not mean-subtracted, so it scores on raw brightness and
            # saturates near 0.87 against any bright region. The one template
            # in the database with real transparency scored 0.965 on the splash
            # screen - a screen it does not appear on - and returned 1485
            # "matches", while the screen it does appear on scored 0.985. A
            # 0.02 margin is not a match, it is a coin toss that happened to
            # land right. Mean-subtracted, the same pair reads 0.374 against
            # 0.184: still not a high score, but a real gap.
            result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED, mask=mask)
            result = np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)
            # A masked correlation divides by the energy under the mask, and
            # where that is near zero OpenCV returns FLT_MAX rather than inf -
            # 3.4e38, which nan_to_num passes through untouched because it is a
            # perfectly finite number. It then wins every scale sweep it is in.
            # A correlation coefficient cannot exceed 1, so anything that does
            # is a division artefact, not a match.
            return np.where(np.abs(result) <= 1.0, result, 0.0)
        return cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)


class TextFinder:
    """OCR wrapper. The engine is loaded lazily so import stays cheap."""

    def __init__(self, threshold=DEFAULT_TEXT_THRESHOLD):
        self.threshold = threshold
        self._engine = None
        self._lock = threading.Lock()

    def _get_engine(self):
        with self._lock:
            if self._engine is None:
                try:
                    from rapidocr_onnxruntime import RapidOCR
                except ImportError as exc:  # pragma: no cover - environment issue
                    raise RuntimeError(
                        "OCR engine missing. Install it with: "
                        "pip install rapidocr-onnxruntime"
                    ) from exc
                self._engine = RapidOCR()
            return self._engine

    def read_all(self, screen):
        """Return every text Element the OCR engine sees on screen."""
        engine = self._get_engine()
        raw, _ = engine(screen)
        elements = []
        for box, text, score in raw or []:
            if score < self.threshold:
                continue
            pts = np.array(box, dtype=np.float32)
            x1, y1 = pts.min(axis=0)
            x2, y2 = pts.max(axis=0)
            elements.append(
                Element(x1, y1, x2 - x1, y2 - y1, score=float(score), text=str(text))
            )
        return elements

    def find(self, screen, needle, case_sensitive=False):
        """Find text on screen, ignoring surrounding text.

        Case is ignored unless `case_sensitive`.
        """
        return self._pick(self.read_all(screen), needle, case_sensitive)

    def find_any(self, screen, needles, case_sensitive=False):
        """Find the first of several texts that is on screen (design.md task 5).

        'First' is by the order of `needles`, not by position on screen: the
        caller lists the labels in the order they would accept them, so an
        English label can be listed before its localised twin.

        One OCR pass serves every needle. Re-running find() per string would
        re-read the same screen - about a second each on a phone frame - and
        make a three-label lookup three times slower than a one-label lookup
        for no new information (design.md task 3).
        """
        texts = self.read_all(screen)
        for needle in needles:
            element = self._pick(texts, needle, case_sensitive)
            if element:
                return element
        return None

    def _pick(self, texts, needle, case_sensitive=False):
        target = _normalize(needle, case_sensitive)
        candidates = []
        for el in texts:
            hay = _normalize(el.text, case_sensitive)
            if hay == target:
                candidates.append((0, el))
            elif target and target in hay:
                candidates.append((1, el))
        if not candidates:
            return None
        # Prefer an exact match, then the most confident one.
        candidates.sort(key=lambda pair: (pair[0], -pair[1].score))
        return candidates[0][1]


def _geometric(lo, hi, ratio):
    """Scales from lo to hi stepping by a constant ratio."""
    scales, scale = [], lo
    while scale <= hi + 1e-9:
        scales.append(float(scale))
        scale *= ratio
    return scales or [lo]


def _haystack(screen, mode):
    """What the templates are scored against, for this mode.

    Pixel mode hands back the frame itself. Edge mode hands back an EdgeField,
    which is the frame's outlines plus the precomputed maps the outline score
    needs - built once per find() rather than once per scale.
    """
    if mode != MODE_EDGE:
        return screen
    return EdgeField(cv2.Canny(_to_gray(screen), EDGE_LOW, EDGE_HIGH))


class EdgeField:
    """A frame's outlines, prepared for tolerant outline matching.

    Holds three views of the same Canny map: the edges themselves, a proximity
    field that fades from 1 on an edge to 0 at EDGE_TOLERANCE away, and a
    dilation kernel sized to that tolerance. See EDGE_TOLERANCE for why
    scoring against a fuzzed field rather than the raw map is the whole trick.
    """

    def __init__(self, edges):
        self.edges = edges
        self.binary = (edges > 0).astype(np.float32)
        distance = cv2.distanceTransform((edges == 0).astype(np.uint8), cv2.DIST_L2, 3)
        self.nearness = np.maximum(0.0, 1.0 - distance / EDGE_TOLERANCE)
        span = int(EDGE_TOLERANCE) * 2 + 1
        self.kernel = np.ones((span, span), np.uint8)

    @property
    def shape(self):
        return self.edges.shape

    def score(self, template):
        """How well `template`'s outline sits on this frame, per position.

        The two halves answer different questions, and a match has to satisfy
        both. Coverage asks how much of the template's outline landed on or
        near a screen edge - on its own it rewards a sparse template dropped
        anywhere busy. Precision asks the reverse, how much of the screen's
        own edging in that window the template accounts for - on its own it
        rewards a template that draws over everything. Their harmonic mean is
        high only where the two outlines actually correspond.
        """
        binary = (template > 0).astype(np.float32)
        strokes = float(binary.sum())
        coverage = cv2.matchTemplate(self.nearness, binary, cv2.TM_CCORR) / strokes
        widened = (cv2.dilate(template, self.kernel) > 0).astype(np.float32)
        explained = cv2.matchTemplate(self.binary, widened, cv2.TM_CCORR)
        present = cv2.matchTemplate(self.binary, np.ones_like(binary), cv2.TM_CCORR)
        precision = np.where(
            present >= MIN_WINDOW_EDGE_PIXELS, explained / np.maximum(present, 1e-6), 0.0
        )
        return 2 * coverage * precision / np.maximum(coverage + precision, 1e-6)


def _to_gray(image):
    if image is None or image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _border_trim(image, mask):
    """A copy of the template with BORDER_TRIM cut off each side, or None."""
    h, w = image.shape[:2]
    dy, dx = int(h * BORDER_TRIM), int(w * BORDER_TRIM)
    if h - 2 * dy < 8 or w - 2 * dx < 8:
        return None
    trimmed = image[dy : h - dy, dx : w - dx]
    trimmed_mask = mask[dy : h - dy, dx : w - dx] if mask is not None else None
    return trimmed, trimmed_mask


def _normalize(text, case_sensitive=False):
    """Fold text for comparison: whitespace, accents, and optionally case.

    OCR reads Vietnamese diacritics unreliably - "gửi thông báo" often comes
    back as "gui thong bao" - so accents are stripped on both sides rather
    than letting a needle miss the text that is plainly on screen. That holds
    whichever way case is treated: a caller asking for exact case is asking
    about A vs a, not about whether the engine resolved a tone mark.

    Case is folded unless `case_sensitive`, which keeps "OK" from matching an
    "ok" elsewhere on screen.
    """
    folded = " ".join(str(text).split()).strip()
    if not case_sensitive:
        folded = folded.lower()
    # 'd' with stroke has no combining form, so map it before decomposing.
    folded = folded.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", folded)
    return "".join(c for c in decomposed if not unicodedata.combining(c))
