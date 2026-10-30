"""Turning a blob of ink into single-line pen strokes.

A pen plotter draws lines, not filled shapes, so a scanned letter has to be
reduced to its centreline. Skeletonising gives one-pixel-wide ink; tracing then
walks that skeleton into ordered polylines, starting from loose ends so a 'c'
comes out as one stroke rather than several fragments.
"""
from __future__ import annotations

import cv2
import numpy as np
from skimage.morphology import skeletonize

Polyline = list[tuple[float, float]]

_NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def clean(mask: np.ndarray, min_area_px: int = 12) -> np.ndarray:
    """Close pen skips and drop specks of dust or paper texture."""
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    keep = np.zeros_like(mask)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area_px:
            keep[labels == i] = 255
    return keep


def trace(mask: np.ndarray, simplify_px: float = 0.8) -> list[Polyline]:
    """Centreline polylines of the ink in mask, in pixel coordinates (x, y)."""
    skel = skeletonize(mask > 0)
    pixels = set(zip(*np.nonzero(skel)))  # (row, col)
    if not pixels:
        return []

    def nbrs(p):
        r, c = p
        return [(r + dr, c + dc) for dr, dc in _NEIGHBOURS if (r + dr, c + dc) in pixels]

    used_edges: set[frozenset] = set()

    def free(p):
        return [q for q in nbrs(p) if frozenset((p, q)) not in used_edges]

    paths: list[list[tuple[int, int]]] = []
    # Endpoints first so open strokes are traced end to end, then whatever loops remain.
    order = sorted(pixels, key=lambda p: (len(nbrs(p)) != 1, p))
    for start in order:
        while free(start):
            path = [start]
            cur = start
            prev_dir = None
            while True:
                options = free(cur)
                if not options:
                    break
                if prev_dir is not None:
                    # Keep going straight through junctions: that is how a pen crosses a 't'.
                    options.sort(key=lambda q: -((q[0] - cur[0]) * prev_dir[0] + (q[1] - cur[1]) * prev_dir[1]))
                nxt = options[0]
                used_edges.add(frozenset((cur, nxt)))
                prev_dir = (nxt[0] - cur[0], nxt[1] - cur[1])
                path.append(nxt)
                cur = nxt
            paths.append(path)

    # Isolated pixels (an i-dot written as a tap) still deserve a pen touch.
    touched = {p for path in paths for p in path}
    for p in pixels - touched:
        paths.append([p, p])

    out: list[Polyline] = []
    for path in paths:
        pts = np.array([(c, r) for r, c in path], np.float32).reshape(-1, 1, 2)
        if len(path) > 2:
            pts = cv2.approxPolyDP(pts, simplify_px, False)
        out.append([(float(x), float(y)) for x, y in pts.reshape(-1, 2)])
    return _join(_drop_spurs(out, min_len_px=3.0))


def length(line: Polyline) -> float:
    return float(sum(np.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(line, line[1:])))


def _drop_spurs(lines: list[Polyline], min_len_px: float) -> list[Polyline]:
    """Skeletonising leaves tiny whiskers at corners; a pen should not draw them."""
    if len(lines) <= 1:
        return lines
    return [l for l in lines if length(l) >= min_len_px or len(lines) == 1] or lines[:1]


def _join(lines: list[Polyline], tol: float = 1.5) -> list[Polyline]:
    """Merge strokes whose ends touch, so the pen lifts only where the writer did."""
    lines = [list(l) for l in lines]
    merged = True
    while merged:
        merged = False
        for i in range(len(lines)):
            for j in range(i + 1, len(lines)):
                a, b = lines[i], lines[j]
                for ra in (False, True):
                    for rb in (False, True):
                        aa = a[::-1] if ra else a
                        bb = b[::-1] if rb else b
                        if np.hypot(aa[-1][0] - bb[0][0], aa[-1][1] - bb[0][1]) <= tol:
                            lines[i] = aa + bb[1:]
                            del lines[j]
                            merged = True
                            break
                    if merged:
                        break
                if merged:
                    break
            if merged:
                break
    return lines


def order_for_plotting(lines: list[Polyline]) -> list[Polyline]:
    """Greedy nearest-neighbour ordering (and flipping) to cut pen-up travel."""
    remaining = [l for l in lines if l]
    out: list[Polyline] = []
    pos = (0.0, 0.0)
    while remaining:
        best, best_d, flip = 0, float("inf"), False
        for i, l in enumerate(remaining):
            for f, end in ((False, l[0]), (True, l[-1])):
                d = (end[0] - pos[0]) ** 2 + (end[1] - pos[1]) ** 2
                if d < best_d:
                    best, best_d, flip = i, d, f
        l = remaining.pop(best)
        l = l[::-1] if flip else l
        out.append(l)
        pos = l[-1]
    return out
