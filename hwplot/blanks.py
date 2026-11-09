"""Finding where answers are meant to go, and snapping Claude's boxes onto them.

Claude reads a worksheet well but places boxes by eye, so an answer can land a
few millimetres off its line. The page itself says exactly where the blanks
are: an answer line is a long, thin horizontal stroke, and an answer box is an
empty rectangle. This finds both on the flattened scan and moves each answer
onto the nearest one, so it sits on the line rather than near it.

Each blank takes one answer. Two answers never share a line: the second one
keeps Claude's box, which is the safer mistake.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .page import PX_PER_MM, ink_mask
from .solve import Answer

MIN_LINE_MM = 10.0     # shorter than this is a dash or a letter, not a blank
MAX_LINE_THICK_MM = 1.4
MIN_BOX_MM = (8.0, 5.0)
SNAP_MM = 9.0          # how far an answer may move to reach a blank
LINE_ROOM_MM = (6.0, 12.0)  # writing height above a line: at least, at most


@dataclass(frozen=True)
class Blank:
    kind: str  # "line" or "box"
    x: float   # mm; for a line, y is the line itself and h is 0
    y: float
    w: float
    h: float

    def region(self) -> tuple[float, float, float, float]:
        """The area an answer written here occupies."""
        if self.kind == "line":
            return (self.x, self.y - LINE_ROOM_MM[1], self.w, LINE_ROOM_MM[1])
        return (self.x, self.y, self.w, self.h)


def _mm(v: float) -> float:
    return v / PX_PER_MM


def _px(v: float) -> int:
    return max(1, round(v * PX_PER_MM))


def find_blanks(flat: np.ndarray) -> list[Blank]:
    mask = ink_mask(flat)
    H, W = mask.shape
    horiz = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (_px(MIN_LINE_MM), 1)))
    vert = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, _px(MIN_BOX_MM[1]))))

    boxes: list[Blank] = []
    # Rectangles are the pockets of paper fully enclosed by ruled lines.
    grid = cv2.dilate(horiz | vert, np.ones((3, 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(255 - grid, connectivity=4)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if x == 0 or y == 0 or x + w >= W or y + h >= H:
            continue  # touches the page edge: open paper, not a box
        if _mm(w) < MIN_BOX_MM[0] or _mm(h) < MIN_BOX_MM[1] or w > 0.9 * W:
            continue
        if area < 0.85 * w * h:
            continue  # not rectangular
        inset = _px(1.0)
        inner = mask[y + inset : y + h - inset, x + inset : x + w - inset]
        if inner.size and (inner > 0).mean() > 0.02:
            continue  # has printed text in it: a label cell, not somewhere to write
        boxes.append(Blank("box", _mm(x), _mm(y), _mm(w), _mm(h)))

    lines: list[Blank] = []
    n, _, stats, _ = cv2.connectedComponentsWithStats(horiz, connectivity=8)
    for i in range(1, n):
        x, y, w, h, _ = stats[i]
        if _mm(w) < MIN_LINE_MM or _mm(h) > MAX_LINE_THICK_MM or w > 0.9 * W:
            continue
        ly = _mm(y + h / 2)
        lx, lw = _mm(x), _mm(w)
        # Box edges are ruled lines too; the box already covers them.
        if any(abs(ly - b.y) < 1.5 or abs(ly - (b.y + b.h)) < 1.5 for b in boxes
               if lx < b.x + b.w and b.x < lx + lw):
            continue
        lines.append(Blank("line", lx, ly, lw, 0.0))
    return lines + boxes


def _gap(a, b) -> float:
    """Distance between two rectangles (x, y, w, h); 0 when they overlap."""
    dx = max(0.0, max(a[0], b[0]) - min(a[0] + a[2], b[0] + b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[1] + a[3], b[1] + b[3]))
    return float(np.hypot(dx, dy))


def _centre_dist(a, b) -> float:
    return float(np.hypot(a[0] + a[2] / 2 - (b[0] + b[2] / 2), a[1] + a[3] / 2 - (b[1] + b[3] / 2)))


def _tighten_circle(mask: np.ndarray, box) -> tuple[float, float, float, float]:
    """Shrink a multiple-choice box to the printed option it surrounds."""
    x, y, w, h = box
    pad = 2.0
    x0, y0 = max(0, _px(x - pad)), max(0, _px(y - pad))
    x1, y1 = min(mask.shape[1], _px(x + w + pad)), min(mask.shape[0], _px(y + h + pad))
    if x1 <= x0 or y1 <= y0:
        return box
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask[y0:y1, x0:x1], connectivity=8)
    picked = []
    for i in range(1, n):
        cx, cy = _mm(cents[i][0] + x0), _mm(cents[i][1] + y0)
        if x <= cx <= x + w and y <= cy <= y + h and stats[i][4] >= 4:
            picked.append(stats[i])
    if not picked:
        return box
    ax0 = min(s[0] for s in picked) + x0
    ay0 = min(s[1] for s in picked) + y0
    ax1 = max(s[0] + s[2] for s in picked) + x0
    ay1 = max(s[1] + s[3] for s in picked) + y0
    m = 0.5
    return (_mm(ax0) - m, _mm(ay0) - m, _mm(ax1 - ax0) + 2 * m, _mm(ay1 - ay0) + 2 * m)


def snap(answers: list[Answer], flat: np.ndarray, blanks: list[Blank] | None = None) -> int:
    """Move answers onto the page's own blanks, in place. Returns how many moved."""
    blanks = find_blanks(flat) if blanks is None else blanks
    writes = [a for a in answers if a.kind == "write"]
    pairs = []
    for ai, a in enumerate(writes):
        for bi, b in enumerate(blanks):
            g = _gap(a.box, b.region())
            if g <= SNAP_MM:
                pairs.append((g, _centre_dist(a.box, b.region()), ai, bi))
    pairs.sort()
    used_a, used_b, moved = set(), set(), 0
    for _, _, ai, bi in pairs:
        if ai in used_a or bi in used_b:
            continue
        used_a.add(ai)
        used_b.add(bi)
        a, b = writes[ai], blanks[bi]
        if b.kind == "line":
            room = min(max(a.box[3], LINE_ROOM_MM[0]), LINE_ROOM_MM[1])
            a.box = (b.x + 1.0, b.y - room, max(b.w - 2.0, 1.0), room)
        else:
            a.box = (b.x + 1.5, b.y + 1.5, max(b.w - 3.0, 1.0), max(b.h - 3.0, 1.0))
        a.target = b.kind
        moved += 1

    mask = ink_mask(flat)
    for a in answers:
        if a.kind == "circle":
            tight = _tighten_circle(mask, a.box)
            if tight != a.box:
                a.box = tight
                a.target = "option"
                moved += 1
    return moved
