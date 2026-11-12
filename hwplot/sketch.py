"""Drawing by hand: lines, shapes and graphs with a person's small imperfections.

A plotter draws a perfect line, which is exactly what gives it away. People
don't: a ruled-by-eye line bows a little and wanders, it starts and stops a
fraction off target and runs past its end, corners overshoot, a circle is a bit
oval and its ends overlap rather than meet. Each shape here gets those, scaled
to its size so a long line isn't wilder than a short one, and kept small enough
that a graph still reads correctly.

Shapes are dicts in page millimetres (origin top-left, y down):
  {"type": "line",     "points": [[x0, y0], [x1, y1]]}
  {"type": "arrow",    "points": [[x0, y0], [x1, y1]]}           head at the second point
  {"type": "polyline", "points": [[x, y], ...], "closed": false} straight segments
  {"type": "polygon",  "points": [[x, y], ...]}                  closed polyline
  {"type": "rect",     "points": [[x0, y0], [x1, y1]]}           two opposite corners
  {"type": "curve",    "points": [[x, y], ...]}                  smooth, through every point (graphs)
  {"type": "circle",   "points": [[cx, cy]], "r": 5}
  {"type": "ellipse",  "points": [[cx, cy]], "rx": 8, "ry": 4}
  {"type": "dot",      "points": [[x, y], ...]}                  a small filled dot at each point
"""
from __future__ import annotations

import math
import random

import numpy as np

from .strokes import Polyline

KINDS = ("line", "arrow", "polyline", "polygon", "rect", "curve", "circle", "ellipse", "dot")


def _noise(n: int, rng: random.Random, amp: float) -> np.ndarray:
    """Smooth, low-frequency wander along a stroke: two sine waves at random phase."""
    t = np.linspace(0, 1, n)
    f1, f2 = rng.uniform(0.6, 1.4), rng.uniform(1.8, 3.2)
    p1, p2 = rng.uniform(0, 2 * math.pi), rng.uniform(0, 2 * math.pi)
    return amp * (0.7 * np.sin(2 * math.pi * f1 * t + p1) + 0.3 * np.sin(2 * math.pi * f2 * t + p2))


def _wander(pts: np.ndarray, rng: random.Random, amp: float) -> np.ndarray:
    """Push each point sideways (along the stroke's normal) by a smooth wander."""
    if len(pts) < 3 or amp <= 0:
        return pts
    d = np.gradient(pts, axis=0)
    norm = np.linalg.norm(d, axis=1, keepdims=True)
    norm[norm == 0] = 1
    normal = np.column_stack([-d[:, 1], d[:, 0]]) / norm
    return pts + normal * _noise(len(pts), rng, amp)[:, None]


def segment(p0, p1, rng: random.Random, overshoot: bool = True) -> np.ndarray:
    """One hand-ruled straight stroke from p0 to p1."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    length = float(np.linalg.norm(p1 - p0))
    if length < 1e-6:
        return np.array([p0, p0])
    u = (p1 - p0) / length
    # start a hair off, finish a hair past (people overshoot more than they undershoot)
    p0 = p0 + rng.gauss(0, 0.12) * np.array([-u[1], u[0]]) - u * rng.uniform(0, 0.25)
    p1 = p1 + rng.gauss(0, 0.12) * np.array([-u[1], u[0]]) + u * (rng.uniform(0.1, 0.6) if overshoot else 0)
    n = max(4, int(length / 1.2))
    t = np.linspace(0, 1, n)[:, None]
    pts = p0 + (p1 - p0) * t
    # a gentle bow: the hand swings in an arc, not along a ruler
    bow = rng.choice((-1, 1)) * rng.uniform(0.4, 1.0) * min(1.6, 0.016 * length)
    pts = pts + np.array([-u[1], u[0]]) * (4 * bow * t * (1 - t))
    return _wander(pts, rng, min(0.45, 0.006 * length + 0.1))


def _polyline(points, rng: random.Random, closed: bool) -> list[np.ndarray]:
    pts = [np.asarray(p, float) for p in points]
    if closed:
        pts = pts + [pts[0]]
    strokes, current = [], None
    for a, b in zip(pts, pts[1:]):
        seg = segment(a, b, rng, overshoot=False)
        if current is None:
            current = seg
        elif rng.random() < 0.5:  # often the pen lifts at a corner and starts the next side fresh
            # finish the side just past the corner, as a hand does
            u = b - a
            u = u / (np.linalg.norm(u) or 1)
            prev = current[-1] - current[-2]
            prev = prev / (np.linalg.norm(prev) or 1)
            current = np.vstack([current, current[-1] + prev * rng.uniform(0.4, 1.2)])
            strokes.append(current)
            current = segment(a, b, rng, overshoot=True)
        else:
            current = np.vstack([current, seg[1:]])
    if current is not None:
        if closed:  # run a little past the starting corner, as a hand closing a shape does
            u = pts[1] - pts[0]
            u = u / (np.linalg.norm(u) or 1)
            current = np.vstack([current, current[-1] + u * rng.uniform(0.5, 1.5)])
        strokes.append(current)
    return strokes


def _catmull_rom(points, per_seg: int = 12) -> np.ndarray:
    p = np.asarray(points, float)
    if len(p) < 3:
        return p
    p = np.vstack([p[0] * 2 - p[1], p, p[-1] * 2 - p[-2]])
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for t in np.linspace(0, 1, per_seg, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(p[-2])
    return np.asarray(out)


def _ellipse(c, rx: float, ry: float, rng: random.Random) -> np.ndarray:
    """Not quite round, and the ends overlap rather than meet."""
    rx, ry = rx * rng.uniform(0.94, 1.06), ry * rng.uniform(0.94, 1.06)
    start = rng.uniform(0, 2 * math.pi)
    sweep = 2 * math.pi + rng.uniform(0.3, 0.7)
    tilt = rng.uniform(-0.12, 0.12)
    n = max(24, int(max(rx, ry) * 6))
    a = start + np.linspace(0, sweep, n)
    # the end comes round a little inside or outside the start, so the overlap shows
    r = 1 + 0.035 * np.sin(2 * a + rng.uniform(0, 6.28)) + rng.uniform(-0.06, 0.06) * np.linspace(0, 1, n)
    x, y = rx * r * np.cos(a), ry * r * np.sin(a)
    x, y = x * math.cos(tilt) - y * math.sin(tilt), x * math.sin(tilt) + y * math.cos(tilt)
    return np.column_stack([c[0] + x, c[1] + y])


def _dot(c, rng: random.Random, r: float = 0.35) -> np.ndarray:
    a = np.linspace(0, 4 * math.pi, 14)
    rr = np.linspace(r, 0.05, 14)
    return np.column_stack([c[0] + rr * np.cos(a), c[1] + rr * np.sin(a)])


def draw(shape: dict, rng: random.Random) -> list[Polyline]:
    """Strokes for one shape (see the module docstring)."""
    kind = shape.get("type")
    pts = [tuple(map(float, p)) for p in shape.get("points", [])]
    out: list[np.ndarray] = []
    if kind == "line" and len(pts) >= 2:
        out = [segment(pts[0], pts[1], rng)]
    elif kind == "arrow" and len(pts) >= 2:
        shaft = segment(pts[0], pts[1], rng, overshoot=False)
        tip = shaft[-1]
        d = np.asarray(pts[1]) - np.asarray(pts[0])
        ang = math.atan2(d[1], d[0])
        size = min(3.0, 0.25 * float(np.hypot(*d))) * rng.uniform(0.9, 1.1)
        wing = math.radians(rng.uniform(24, 32))
        left = tip - size * np.array([math.cos(ang - wing), math.sin(ang - wing)])
        right = tip - size * np.array([math.cos(ang + wing), math.sin(ang + wing)])
        out = [shaft, np.vstack([segment(left, tip, rng, False), segment(tip, right, rng, False)[1:]])]
    elif kind in ("polyline", "polygon") and len(pts) >= 2:
        out = _polyline(pts, rng, closed=kind == "polygon" or bool(shape.get("closed")))
    elif kind == "rect" and len(pts) >= 2:
        (x0, y0), (x1, y1) = pts[0], pts[1]
        out = _polyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], rng, closed=True)
    elif kind == "curve" and len(pts) >= 2:
        smooth = _catmull_rom(pts)
        length = float(np.sum(np.hypot(*np.diff(smooth, axis=0).T)))
        out = [_wander(smooth, rng, min(0.35, 0.005 * length + 0.08))]
    elif kind == "circle" and pts:
        r = float(shape.get("r", 3))
        out = [_ellipse(pts[0], r, r, rng)]
    elif kind == "ellipse" and pts:
        out = [_ellipse(pts[0], float(shape.get("rx", 4)), float(shape.get("ry", 2)), rng)]
    elif kind == "dot":
        out = [_dot(p, rng) for p in pts]
    return [[(float(x), float(y)) for x, y in s] for s in out if len(s)]


def bounds(shapes: list[dict]) -> tuple[float, float, float, float] | None:
    """The page area the shapes cover, roughly, for placing and reach checks."""
    xs, ys = [], []
    for s in shapes:
        pts = s.get("points", [])
        r = float(s.get("r", 0) or max(float(s.get("rx", 0)), float(s.get("ry", 0))))
        for x, y in pts:
            xs += [x - r, x + r]
            ys += [y - r, y + r]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None
