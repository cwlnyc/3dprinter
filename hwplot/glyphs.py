"""Your handwriting as data: every character you wrote, as pen strokes in millimetres.

Coordinates are relative to the character's own origin: x from the left edge of
its ink, y from the baseline (positive downwards, as on the page). Keeping the
baseline rather than the ink box is what makes 'g' hang below the line and
'x' sit on it.
"""
from __future__ import annotations

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
class Hand:
    glyphs: dict[str, list[Glyph]] = field(default_factory=dict)
    cap_height: float = 7.0  # mm, measured from your capitals and digits
    x_height: float = 4.0

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

    def missing(self, text: str) -> set[str]:
        return {c for c in text if not c.isspace() and not self.variants(c)}

    def save(self, path: str) -> None:
        data = {
            "cap_height": self.cap_height,
            "x_height": self.x_height,
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
        return cls(glyphs, data["cap_height"], data["x_height"])


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


def learn(images: list[np.ndarray]) -> tuple[Hand, list[str]]:
    """Read filled-in sample sheets. Returns the hand and a list of warnings."""
    hand = Hand()
    warnings: list[str] = []
    seen_pages: set[int] = set()
    for img in images:
        page, flat = template.register(img)
        seen_pages.add(page)
        for cell in (c for c in template.cells() if c.page == page):
            g = glyph_from_mask(template.box_mask(flat, cell))
            if g is not None:
                hand.glyphs.setdefault(cell.char, []).append(g)
    for p in range(template.page_count()):
        if p not in seen_pages:
            warnings.append(f"sample page {p + 1} was not scanned")
    blank = sorted(set(template.CHARSET) - set(hand.glyphs))
    if blank:
        warnings.append("no sample for: " + " ".join(blank))

    def tall(chars):
        hs = [-g.bounds()[0] for c in chars for g in hand.glyphs.get(c, [])]
        return float(np.median(hs)) if hs else None

    hand.cap_height = tall("ABDEFHIKLMNPRTUVWXYZ0123456789") or hand.cap_height
    hand.x_height = tall("acemnorsuvwxz") or hand.cap_height * 0.6
    return hand, warnings
