"""Your handwriting as data: every character you wrote, as pen strokes in millimetres.

Coordinates are relative to the character's own origin: x from the left edge of
its ink, y from the baseline (positive downwards, as on the page). Keeping the
baseline rather than the ink box is what makes 'g' hang below the line and
'x' sit on it.

Each letter drawn is new. With two or more samples of a character, `make`
blends a random pair in random proportions, so the page gets an 'a' that sits
between two you wrote rather than a copy of either; then a gentle wobble, the
same across the whole letter so joined strokes stay joined. More samples mean
a wider range, which is why learning adds to what is already known instead of
replacing it.
"""
from __future__ import annotations

import itertools
import json
import random
from dataclasses import asdict, dataclass, field

import numpy as np

from . import template
from .strokes import Polyline, clean, trace


@dataclass
class Glyph:
    strokes: list[Polyline]
    width: float  # mm of ink, left to right

    def bounds(self) -> tuple[float, float]:
        ys = [y for s in self.strokes for _, y in s]
        return (min(ys), max(ys)) if ys else (0.0, 0.0)


@dataclass
class Style:
    """How the letters are put together on a line, as fractions of capital height.

    These are the habits a sample sheet cannot show, since every letter sits
    alone in its box. They start at ordinary values and are where learning from
    free-form writing will put what it measures.
    """
    letter_gap: float = 0.12      # space between letters
    word_space: float = 0.55      # space between words
    size_jitter: float = 0.05     # +/- per letter
    baseline_jitter: float = 0.03 # per letter, up or down
    slant_jitter_deg: float = 3.0 # per answer
    line_drift_deg: float = 0.8   # a line rises or falls by up to this much
    wobble: float = 0.025         # per-letter shape wobble
    blend: bool = True


@dataclass
class Hand:
    glyphs: dict[str, list[Glyph]] = field(default_factory=dict)
    cap_height: float = 7.0  # mm, measured from your capitals and digits
    x_height: float = 4.0
    style: Style = field(default_factory=Style)

    def variants(self, ch: str) -> list[Glyph]:
        if ch in self.glyphs:
            return self.glyphs[ch]
        # Fall back across case before giving up: a missing 'Q' can borrow 'q'.
        for alt in (ch.lower(), ch.upper()):
            if alt in self.glyphs:
                return self.glyphs[alt]
        return []

    def pick(self, ch: str, rng: random.Random) -> Glyph | None:
        v = self.variants(ch)
        return rng.choice(v) if v else None

    def make(self, ch: str, rng: random.Random) -> Glyph | None:
        """A fresh instance of ch: a blend of two samples, slightly wobbled."""
        v = self.variants(ch)
        if not v:
            return None
        g = rng.choice(v)
        if self.style.blend and len(v) > 1:
            a, b = rng.sample(v, 2)
            g = blend(a, b, rng.uniform(0.2, 0.8)) or g
        return wobble(g, rng, self.style.wobble * self.cap_height)

    def add(self, ch: str, g: Glyph, known: list[Glyph] | None = None, tol_mm: float = 0.3) -> bool:
        """Keep a new sample unless it repeats one in known (a page scanned twice)."""
        for old in (self.glyphs.get(ch, []) if known is None else known):
            if _distance(old, g) < tol_mm:
                return False
        self.glyphs.setdefault(ch, []).append(g)
        return True

    def measure(self) -> None:
        def tall(chars):
            hs = [-g.bounds()[0] for c in chars for g in self.glyphs.get(c, [])]
            return float(np.median(hs)) if hs else None

        self.cap_height = tall("ABDEFHIKLMNPRTUVWXYZ0123456789") or self.cap_height
        self.x_height = tall("acemnorsuvwxz") or self.cap_height * 0.6

    def missing(self, text: str) -> set[str]:
        return {c for c in text if not c.isspace() and not self.variants(c)}

    def save(self, path: str) -> None:
        data = {
            "cap_height": self.cap_height,
            "x_height": self.x_height,
            "style": asdict(self.style),
            "glyphs": {k: [asdict(g) for g in v] for k, v in self.glyphs.items()},
        }
        with open(path, "w") as f:
            json.dump(data, f)

    @classmethod
    def load(cls, path: str) -> "Hand":
        with open(path) as f:
            data = json.load(f)
        glyphs = {
            k: [Glyph([[tuple(p) for p in s] for s in g["strokes"]], g["width"]) for g in v]
            for k, v in data["glyphs"].items()
        }
        return cls(glyphs, data["cap_height"], data["x_height"], Style(**data.get("style", {})))


def glyph_from_mask(mask, inset_mm: float = 1.0) -> Glyph | None:
    mask = clean(mask)
    lines = trace(mask)
    if not lines:
        return None
    s = template.READ_PX_PER_MM
    baseline_px = (template.BASELINE_FROM_TOP - inset_mm) * s
    xs = [x for l in lines for x, _ in l]
    left = min(xs)
    strokes = [[((x - left) / s, (y - baseline_px) / s) for x, y in l] for l in lines]
    return Glyph(strokes, (max(xs) - left) / s)


def learn(images: list[np.ndarray], hand: Hand | None = None) -> tuple[Hand, list[str], int]:
    """Read filled-in sample sheets into hand (a new one if None).

    Returns the hand, warnings, and how many new samples were added. A page
    already learned adds nothing, so uploading the same scan twice is harmless.
    """
    hand = hand or Hand()
    before = {k: list(v) for k, v in hand.glyphs.items()}  # repeats are judged against these only
    warnings: list[str] = []
    seen_pages: set[int] = set()
    added = 0
    for img in images:
        page, flat = template.register(img)
        seen_pages.add(page)
        for cell in (c for c in template.cells() if c.page == page):
            g = glyph_from_mask(template.box_mask(flat, cell))
            if g is not None and hand.add(cell.char, g, before.get(cell.char, [])):
                added += 1
    for p in range(template.page_count()):
        if p not in seen_pages and not hand.glyphs:
            warnings.append(f"sample page {p + 1} was not scanned")
    blank = sorted(set(template.CHARSET) - set(hand.glyphs))
    if blank:
        warnings.append("no sample for: " + " ".join(blank))
    hand.measure()
    return hand, warnings, added


# --- making new letters from the samples -------------------------------------

def _resample(stroke: Polyline, n: int) -> np.ndarray:
    pts = np.asarray(stroke, float)
    if len(pts) == 1:
        return np.repeat(pts, n, axis=0)
    seg = np.hypot(*np.diff(pts, axis=0).T)
    d = np.concatenate([[0.0], np.cumsum(seg)])
    if d[-1] == 0:
        return np.repeat(pts[:1], n, axis=0)
    t = np.linspace(0, d[-1], n)
    return np.column_stack([np.interp(t, d, pts[:, 0]), np.interp(t, d, pts[:, 1])])


def _match(a: Glyph, b: Glyph, n: int = 24) -> list[tuple[np.ndarray, np.ndarray]] | None:
    """Pair each stroke of a with a stroke of b, both resampled and facing the same way.

    Strokes are paired by shape, not by order: two people (or one person on two
    days) write a '+' across-then-down or down-then-across, and a stroke may run
    either way. Centres alone cannot tell the bars of a '+' apart, since they
    share one.
    """
    if len(a.strokes) != len(b.strokes) or not a.strokes:
        return None
    ra = [_resample(s, n) for s in a.strokes]
    rb = [_resample(s, n) for s in b.strokes]

    def cost(sa, sb):
        return min(np.linalg.norm(sa - sb, axis=1).mean(), np.linalg.norm(sa - sb[::-1], axis=1).mean())

    c = np.array([[cost(sa, sb) for sb in rb] for sa in ra])
    if len(ra) <= 6:
        best = min(itertools.permutations(range(len(rb))), key=lambda p: sum(c[i, j] for i, j in enumerate(p)))
    else:  # many strokes: greedy is close enough
        best, left = [], set(range(len(rb)))
        for i in range(len(ra)):
            j = min(left, key=lambda k: c[i, k])
            left.remove(j)
            best.append(j)
    pairs = []
    for i, j in enumerate(best):
        sa, sb = ra[i], rb[j]
        if np.linalg.norm(sa - sb[::-1], axis=1).mean() < np.linalg.norm(sa - sb, axis=1).mean():
            sb = sb[::-1]
        pairs.append((sa, sb))
    return pairs


def _size(g: Glyph) -> float:
    pts = [p for s in g.strokes for p in s]
    if not pts:
        return 1.0
    xs, ys = [x for x, _ in pts], [y for _, y in pts]
    return max(max(xs) - min(xs), max(ys) - min(ys), 1.0)


def _distance(a: Glyph, b: Glyph) -> float:
    pairs = _match(a, b)
    if pairs is None:
        return float("inf")
    return float(np.mean([np.linalg.norm(sa - sb, axis=1).mean() for sa, sb in pairs]))


def blend(a: Glyph, b: Glyph, w: float) -> Glyph | None:
    """A letter between a and b (w = 0 is a, 1 is b). None if their strokes don't correspond."""
    pairs = _match(a, b, n=32)
    if pairs is None:
        return None
    # Two samples whose strokes pair up badly are different ways of writing the
    # letter (a one-stroke 'a' and a two-stroke one); averaging those makes mush.
    if np.mean([np.linalg.norm(sa - sb, axis=1).mean() for sa, sb in pairs]) > 0.35 * max(_size(a), _size(b)):
        return None
    strokes = [(1 - w) * sa + w * sb for sa, sb in pairs]
    left = min(float(s[:, 0].min()) for s in strokes)
    out = [[(float(x) - left, float(y)) for x, y in s] for s in strokes]
    right = max(x for s in out for x, _ in s)
    return Glyph(out, right)


def wobble(g: Glyph, rng: random.Random, amp_mm: float) -> Glyph:
    """Bend the whole letter slightly with one smooth field, so strokes that met still meet."""
    if amp_mm <= 0:
        return g
    k1, k2 = rng.uniform(0.3, 0.9), rng.uniform(0.3, 0.9)
    p1, p2 = rng.uniform(0, 6.28), rng.uniform(0, 6.28)
    strokes = [
        [(x + amp_mm * np.sin(k1 * y + p1), y + amp_mm * np.sin(k2 * x + p2)) for x, y in s]
        for s in g.strokes
    ]
    left = min(x for s in strokes for x, _ in s)
    strokes = [[(float(x - left), float(y)) for x, y in s] for s in strokes]
    return Glyph(strokes, max(x for s in strokes for x, _ in s))
