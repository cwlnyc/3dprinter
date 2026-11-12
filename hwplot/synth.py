"""Characters the writer never wrote, made to look like the ones they did.

Two ways, tried in order:

1. Built from their own letters. 'á' is their 'a' with an accent stroke, 'ñ'
   their 'n' with a tilde, '²' their '2' small and raised, '≤' their '<' over
   their '-', '¿' their '?' upside down. These carry the writer's own shapes.
2. Drawn from a plain single-line shape (√, π, ∞, arrows, Greek) and then given
   the writer's habits: their capital height, their measured slant, and the same
   wobble their own letters get. Not their letterforms, but the same hand.

Shapes below are in capital heights: x to the right, y down, baseline at y = 0,
so the top of a capital is y = -1.
"""
from __future__ import annotations

import math
import random

import numpy as np

from .strokes import Polyline

Shape = list[list[tuple[float, float]]]


def _arc(cx, cy, rx, ry, a0, a1, n=24) -> list[tuple[float, float]]:
    return [(cx + rx * math.cos(a), cy + ry * math.sin(a))
            for a in np.linspace(math.radians(a0), math.radians(a1), n)]


# Plain shapes for symbols with no relative among the letters.
TEMPLATES: dict[str, Shape] = {
    "√": [[(0.0, -0.45), (0.12, -0.52), (0.32, 0.0), (0.55, -1.08), (1.25, -1.08)]],
    "π": [[(0.0, -0.66), (0.95, -0.7)], [(0.28, -0.68), (0.22, 0.0)], [(0.68, -0.69), (0.7, -0.08), (0.82, 0.0)]],
    "∞": [[(0.6 + 0.55 * math.sin(t) / (1 + math.cos(t) ** 2) * 1.0,
             -0.38 + 0.55 * math.sin(t) * math.cos(t) / (1 + math.cos(t) ** 2))
            for t in np.linspace(0, 2 * math.pi, 48)]],
    "θ": [_arc(0.32, -0.5, 0.3, 0.5, -90, 270, 40), [(0.05, -0.5), (0.6, -0.5)]],
    "α": [_arc(0.3, -0.33, 0.28, 0.33, -30, 330, 32)[3:] + [(0.62, -0.62), (0.58, -0.1), (0.75, 0.0)]],
    "β": [[(0.08, 0.35), (0.12, -0.75)] + _arc(0.3, -0.75, 0.2, 0.22, 180, 450, 16)[1:]
          + _arc(0.3, -0.27, 0.27, 0.27, -90, 160, 20)],
    "Δ": [[(0.45, -1.0), (0.0, 0.0), (0.92, 0.0), (0.45, -1.0)]],
    "λ": [[(0.08, -1.0), (0.3, -0.9), (0.85, 0.0)], [(0.47, -0.45), (0.05, 0.0)]],
    "μ": [[(0.08, 0.3), (0.1, -0.62)], [(0.1, -0.2)] + _arc(0.32, -0.2, 0.22, 0.2, 180, 0, 12)[1:] + [(0.55, -0.62)],
          [(0.55, -0.62), (0.56, -0.05), (0.66, 0.0)]],
    "Σ": [[(0.8, -0.95), (0.05, -1.0), (0.45, -0.5), (0.05, 0.0), (0.85, 0.02)]],
    "°": [_arc(0.15, -0.88, 0.14, 0.14, -90, 290, 16)],
    "→": [[(0.0, -0.4), (1.0, -0.42)], [(0.75, -0.6), (1.0, -0.42), (0.74, -0.22)]],
    "←": [[(1.0, -0.4), (0.0, -0.42)], [(0.25, -0.6), (0.0, -0.42), (0.26, -0.22)]],
    "↑": [[(0.3, 0.0), (0.32, -1.0)], [(0.1, -0.75), (0.32, -1.0), (0.52, -0.74)]],
    "↓": [[(0.3, -1.0), (0.32, 0.0)], [(0.1, -0.25), (0.32, 0.0), (0.52, -0.26)]],
    "↔": [[(0.0, -0.42), (1.1, -0.42)], [(0.22, -0.6), (0.0, -0.42), (0.22, -0.24)],
          [(0.88, -0.6), (1.1, -0.42), (0.88, -0.24)]],
    "∠": [[(0.85, -0.85), (0.0, 0.0), (0.95, 0.0)]],
    "⊥": [[(0.45, -0.9), (0.47, 0.0)], [(0.0, 0.0), (0.95, 0.0)]],
    "∥": [[(0.2, -1.0), (0.18, 0.1)], [(0.5, -1.0), (0.48, 0.1)]],
    "~": [[(0.0, -0.33), (0.15, -0.44), (0.32, -0.38), (0.5, -0.3), (0.68, -0.38)]],
    "·": [[(0.1, -0.4), (0.1, -0.4)]],
    "•": [_arc(0.15, -0.4, 0.1, 0.1, 0, 720, 20)],
    "…": [[(0.1, 0.0), (0.1, 0.0)], [(0.4, 0.0), (0.4, 0.0)], [(0.7, 0.0), (0.7, 0.0)]],
    "–": [[(0.0, -0.38), (0.6, -0.4)]],
    "—": [[(0.0, -0.38), (1.0, -0.4)]],
    "∴": [[(0.3, -0.6), (0.3, -0.6)], [(0.1, -0.1), (0.1, -0.1)], [(0.5, -0.1), (0.5, -0.1)]],
}

# Characters that are simply another character the writer did write.
SAME = {"−": "-", "‐": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "„": '"', "´": "'", "‚": ",",
        "×": None, "÷": None}  # the last two are built below, not borrowed

ACCENTS = {"á": "a´", "é": "e´", "í": "i´", "ó": "o´", "ú": "u´", "ý": "y´",
           "Á": "A´", "É": "E´", "Í": "I´", "Ó": "O´", "Ú": "U´",
           "à": "a`", "è": "e`", "ì": "i`", "ò": "o`", "ù": "u`",
           "â": "a^", "ê": "e^", "î": "i^", "ô": "o^", "û": "u^",
           "ä": "a¨", "ë": "e¨", "ï": "i¨", "ö": "o¨", "ü": "u¨", "Ä": "A¨", "Ö": "O¨", "Ü": "U¨",
           "ñ": "n~", "Ñ": "N~", "ã": "a~", "õ": "o~", "ç": "c¸", "Ç": "C¸"}


def _mark(kind: str, cx: float, top: float, cap: float) -> Shape:
    """An accent mark centred at cx, sitting just above `top` (all in mm)."""
    g = 0.14 * cap   # gap above the letter
    h = 0.3 * cap    # height of the mark
    if kind == "´":
        return [[(cx - 0.08 * cap, top - g), (cx + 0.14 * cap, top - g - h)]]
    if kind == "`":
        return [[(cx + 0.08 * cap, top - g), (cx - 0.14 * cap, top - g - h)]]
    if kind == "^":
        return [[(cx - 0.18 * cap, top - g), (cx, top - g - h), (cx + 0.18 * cap, top - g)]]
    if kind == "¨":
        y = top - g - 0.12 * cap
        return [[(cx - 0.15 * cap, y), (cx - 0.15 * cap, y)], [(cx + 0.15 * cap, y), (cx + 0.15 * cap, y)]]
    if kind == "~":
        y = top - g - 0.12 * cap
        return [[(cx - 0.25 * cap, y + 0.03 * cap), (cx - 0.1 * cap, y - 0.08 * cap),
                 (cx + 0.08 * cap, y + 0.04 * cap), (cx + 0.25 * cap, y - 0.07 * cap)]]
    return []


def _cedilla(cx: float, cap: float) -> Shape:
    return [[(cx, 0.0), (cx - 0.02 * cap, 0.12 * cap), (cx + 0.12 * cap, 0.2 * cap),
             (cx + 0.05 * cap, 0.32 * cap), (cx - 0.1 * cap, 0.3 * cap)]]


def _bounds(strokes: Shape) -> tuple[float, float, float, float]:
    xs = [x for s in strokes for x, _ in s]
    ys = [y for s in strokes for _, y in s]
    return min(xs), min(ys), max(xs), max(ys)


def _transform(strokes: Shape, scale: float = 1.0, dx: float = 0.0, dy: float = 0.0,
               rotate: bool = False) -> Shape:
    if rotate:  # 180 degrees about the shape's centre (for ¿ and ¡)
        x0, y0, x1, y1 = _bounds(strokes)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        strokes = [[(2 * cx - x, 2 * cy - y) for x, y in s] for s in strokes]
    return [[(x * scale + dx, y * scale + dy) for x, y in s] for s in strokes]


def _glyph(strokes: Shape):
    from .glyphs import Glyph
    strokes = [s for s in strokes if s]
    if not strokes:
        return None
    left = min(x for s in strokes for x, _ in s)
    out = [[(float(x - left), float(y)) for x, y in s] for s in strokes]
    return Glyph(out, max(x for s in out for x, _ in s))


def can_make(ch: str, hand) -> bool:
    return make(ch, hand, random.Random(0)) is not None


def make(ch: str, hand, rng: random.Random):
    """A glyph for ch in this hand's style, or None if there's no way to make one."""
    cap = hand.cap_height

    def own(c):
        return hand.make(c, rng) if hand.variants(c) else None

    if ch in SAME and SAME[ch]:
        return own(SAME[ch])

    if ch in ACCENTS:
        base_ch, mark = ACCENTS[ch]
        base = own(base_ch)
        if base is None:
            return None
        strokes = [list(s) for s in base.strokes]
        x0, top, x1, _ = _bounds(strokes)
        cx = (x0 + x1) / 2 + 0.05 * cap
        if base_ch in "ij":  # the dot goes, the accent takes its place
            strokes = [s for s in strokes if _bounds([s])[3] - _bounds([s])[1] > 0.15 * cap] or strokes
            top = -hand.x_height
        if mark == "¸":
            strokes += _cedilla(cx, cap)
        else:
            strokes += _mark(mark, cx, top, cap)
        return _glyph(strokes)

    if ch in "¿¡":
        base = own("?" if ch == "¿" else "!")
        if base is None:
            return None
        flipped = _transform(base.strokes, rotate=True)
        x0, y0, x1, y1 = _bounds(flipped)
        return _glyph(_transform(flipped, dy=-y1 + 0.25 * cap))  # hangs a little below the line, as written

    if ch in "²³¹⁰⁴⁵⁶⁷⁸⁹":
        digit = "0123456789"["⁰¹²³⁴⁵⁶⁷⁸⁹".index(ch)]
        base = own(digit)
        if base is None:
            return None
        return _glyph(_transform(base.strokes, scale=0.6, dy=-0.5 * cap))

    if ch == "×":
        base = own("x")
        if base is not None:
            x0, y0, x1, y1 = _bounds(base.strokes)
            s = 0.55 * cap / max(y1 - y0, 1e-6)
            return _glyph(_transform(base.strokes, scale=s, dy=-0.35 * cap - (y0 + y1) / 2 * s))
        return _styled([[(0.0, -0.6), (0.5, -0.1)], [(0.5, -0.6), (0.0, -0.1)]], hand, rng)

    if ch in "÷±≤≥≠≈":
        parts = {"÷": ("-", None), "±": ("+", "-"), "≤": ("<", "-"), "≥": (">", "-"), "≠": ("=", "/"),
                 "≈": ("~", "~")}[ch]
        first = own(parts[0]) or make(parts[0], hand, rng)
        if first is None:
            return None
        strokes = [list(s) for s in first.strokes]
        x0, y0, x1, y1 = _bounds(strokes)
        if ch == "÷":
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            strokes += [[(cx, cy - 0.25 * cap)] * 2, [(cx, cy + 0.25 * cap)] * 2]
        elif ch in "±≤≥":
            lift = 0.18 * cap
            strokes = [[(x, y - lift) for x, y in s] for s in strokes]
            strokes += [[(x0, y1 - lift + 0.28 * cap), (x1, y1 - lift + 0.27 * cap)]]
        elif ch == "≠":
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            # long and steep, so it reads as a strike-through and not as part of a ≥
            strokes += [[(cx - 0.16 * cap, cy + 0.5 * cap), (cx + 0.16 * cap, cy - 0.5 * cap)]]
        elif ch == "≈":
            strokes = [[(x, y - 0.1 * cap) for x, y in s] for s in strokes] + \
                      [[(x, y + 0.12 * cap) for x, y in s] for s in strokes]
        return _glyph(strokes)

    if ch in TEMPLATES:
        return _styled(TEMPLATES[ch], hand, rng)
    return None


def _styled(shape: Shape, hand, rng: random.Random):
    """A plain shape given this hand's size, slant and wobble."""
    from .glyphs import wobble
    cap = hand.cap_height
    slant = math.tan(math.radians(hand.style.slant_deg))
    strokes = [[(x * cap - y * cap * slant, y * cap) for x, y in s] for s in shape]
    g = _glyph(strokes)
    return wobble(g, rng, hand.style.wobble * cap * 1.5) if g else None


def measure_slant(hand) -> float:
    """The writer's slant in degrees (positive leans right), from their upright strokes."""
    angles = []
    for ch in "lItdhkbfLTHE1|":
        for g in hand.glyphs.get(ch, []):
            for s in g.strokes:
                if len(s) < 2:
                    continue
                top = min(s, key=lambda p: p[1])
                bottom = max(s, key=lambda p: p[1])
                dy = bottom[1] - top[1]
                if dy < 0.4 * hand.cap_height:
                    continue
                a = math.degrees(math.atan2(top[0] - bottom[0], dy))
                if abs(a) < 35:
                    angles.append(a)
    return float(np.median(angles)) if angles else 0.0
