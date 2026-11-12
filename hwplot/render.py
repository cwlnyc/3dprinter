"""Laying answers out in your handwriting, as strokes in page millimetres.

Variation is deliberate. Real handwriting never repeats a letter exactly, so each
character is made fresh from your samples (see Hand.make) and nudged slightly in
size and position, each answer gets its own slant, and each line drifts a
little up or down. How much of each is Hand.style. A seed keeps a given run
reproducible.
"""
from __future__ import annotations

import math
import random

import cv2
import numpy as np

from .glyphs import Hand
from .page import PX_PER_MM, ink_mask
from .solve import Answer
from .strokes import Polyline, order_for_plotting

MIN_CAP_MM = 2.5


def find_writing_line(flat: np.ndarray, box) -> float | None:
    """y (mm) of a printed underline inside the box, if there is one to write on."""
    x, y, w, h = (round(v * PX_PER_MM) for v in box)
    H, W = flat.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 - x0 < 5 or y1 - y0 < 3:
        return None
    mask = ink_mask(flat[y0:y1, x0:x1]) > 0
    runs = mask.mean(axis=1)
    row = int(runs.argmax())
    return (y0 + row) / PX_PER_MM if runs[row] > 0.6 else None


def _layout_lines(text: str, hand: Hand, scale: float, space: float, gap: float, max_w: float) -> list[list[str]]:
    def word_w(word):
        return sum(hand.width_of(c) * scale + gap for c in word)

    lines, cur, cur_w = [], [], 0.0
    for para in text.split("\n"):
        for word in para.split():
            ww = word_w(word)
            if cur and cur_w + space + ww > max_w:
                lines.append(cur)
                cur, cur_w = [], 0.0
            cur_w += (space if cur else 0) + ww
            cur.append(word)
        lines.append(cur)
        cur, cur_w = [], 0.0
    return [l for l in lines if l] or [[]]


def write(text: str, box, hand: Hand, rng: random.Random, cap_mm: float = 5.0, baseline: float | None = None) -> list[Polyline]:
    """Strokes for text inside box (x, y, w, h mm). Shrinks to fit, down to MIN_CAP_MM."""
    x, y, w, h = box
    cap = min(cap_mm, h * 0.7)
    while True:
        scale = cap / hand.cap_height
        space, gap, line_h = cap * hand.style.word_space, cap * hand.style.letter_gap, cap * 1.6
        lines = _layout_lines(text, hand, scale, space, gap, w)
        widest = max(
            (sum(hand.width_of(c) * scale + gap for c in " ".join(l)) for l in lines),
            default=0,
        )
        if (len(lines) * line_h <= h + cap * 0.3 and widest <= w) or cap <= MIN_CAP_MM:
            break
        cap *= 0.9

    st = hand.style
    first_base = baseline - cap * 0.15 if baseline is not None and len(lines) == 1 else y + cap * 1.15
    slant = math.radians(rng.uniform(-st.slant_jitter_deg, st.slant_jitter_deg))
    out: list[Polyline] = []
    for i, line in enumerate(lines):
        start_x = pen_x = x + rng.uniform(0, cap * 0.2)
        base = first_base + i * line_h
        drift = math.tan(math.radians(rng.uniform(-st.line_drift_deg, st.line_drift_deg)))
        for j, word in enumerate(line):
            if j:
                pen_x += space * rng.uniform(0.85, 1.15)
            for ch in word:
                g = hand.make(ch, rng)
                if g is None:
                    continue
                s = scale * rng.uniform(1 - st.size_jitter, 1 + st.size_jitter)
                dy = rng.gauss(0, cap * st.baseline_jitter) + drift * (pen_x - start_x)
                for stroke in g.strokes:
                    out.append([(pen_x + px * s - py * s * math.tan(slant), base + dy + py * s) for px, py in stroke])
                pen_x += g.width * s + gap * rng.uniform(0.8, 1.2)
    return out


def circle(box, rng: random.Random) -> list[Polyline]:
    """A hand-drawn loop around a multiple-choice option: slightly oversized, overlapping at the end."""
    x, y, w, h = box
    cx, cy, rx, ry = x + w / 2, y + h / 2, w / 2 + 1.5, h / 2 + 1.2
    start = rng.uniform(0, 2 * math.pi)
    pts = []
    for k in range(73):
        t = start + 2.15 * math.pi * k / 72
        wobble = 1 + 0.03 * math.sin(3 * t + start)
        pts.append((cx + rx * wobble * math.cos(t), cy + ry * wobble * math.sin(t)))
    return [pts]


def render_answers(answers: list[Answer], hand: Hand, flat: np.ndarray | None = None, seed: int = 0, cap_mm: float = 5.0) -> list[Polyline]:
    rng = random.Random(seed)
    strokes: list[Polyline] = []
    for a in answers:
        if a.kind == "draw":
            from .sketch import draw
            for shape in a.shapes or []:
                strokes += draw(shape, rng)
        elif a.kind == "circle":
            strokes += circle(a.box, rng)
        else:
            if a.target == "line":
                line = a.box[1] + a.box[3]  # snapped: the box sits on the page's own line
            elif a.target == "box":
                line = a.box[1] + a.box[3] / 2 + min(cap_mm, a.box[3] * 0.7) / 2  # middle of the box
            else:
                line = find_writing_line(flat, a.box) if flat is not None else None
            strokes += write(a.answer, a.box, hand, rng, cap_mm, baseline=line)
    return order_for_plotting(strokes)


def overlay(flat: np.ndarray, strokes: list[Polyline], pen_mm: float = 0.5) -> np.ndarray:
    """The homework sheet with the answers drawn on, as the plotter would leave it."""
    out = flat.copy()
    thick = max(1, round(pen_mm * PX_PER_MM))
    for s in strokes:
        pts = (np.array(s) * PX_PER_MM).round().astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(out, [pts], False, (140, 40, 20), thick, cv2.LINE_AA)
    return out


def svg(strokes: list[Polyline], page_mm, pen_mm: float = 0.5) -> str:
    w, h = page_mm
    paths = "\n".join(
        '<path d="M' + " L".join(f"{x:.2f},{y:.2f}" for x, y in s) + '"/>' for s in strokes if s
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" height="{h}mm" viewBox="0 0 {w} {h}">\n'
        f'<g fill="none" stroke="#1a2a8c" stroke-width="{pen_mm}" stroke-linecap="round" stroke-linejoin="round">\n'
        f"{paths}\n</g>\n</svg>\n"
    )


def specimen(hand: Hand, chars: str, cols: int = 16, cell_mm: float = 9.0, cap_mm: float = 5.0) -> np.ndarray:
    """Every learned character in a grid, so you can see what the tracer made of your writing."""
    rows = max(1, -(-len(chars) // cols))
    w_mm, h_mm = cols * cell_mm + 6, rows * cell_mm * 1.4 + 6
    img = np.full((round(h_mm * PX_PER_MM), round(w_mm * PX_PER_MM), 3), 255, np.uint8)
    rng = random.Random(0)
    strokes: list[Polyline] = []
    for i, ch in enumerate(chars):
        r, c = divmod(i, cols)
        x, y = 3 + c * cell_mm, 3 + r * cell_mm * 1.4
        cv2.putText(img, ch, (round((x + 0.3) * PX_PER_MM), round((y + cell_mm * 1.33) * PX_PER_MM)),
                    cv2.FONT_HERSHEY_PLAIN, 0.8, (170, 170, 170), 1, cv2.LINE_AA)
        if hand.variants(ch):
            strokes += write(ch, (x + 1.5, y, cell_mm - 2, cell_mm * 1.2), hand, rng, cap_mm)
        else:
            cv2.rectangle(img, (round(x * PX_PER_MM), round(y * PX_PER_MM)),
                          (round((x + cell_mm - 1) * PX_PER_MM), round((y + cell_mm) * PX_PER_MM)), (60, 60, 220), 2)
    return overlay(img, strokes)


def alignment_marks(answers: list[Answer]) -> list[tuple[float, float, str]]:
    """Printed spots worth lining the paper up against: the start of each answer line, top first."""
    lines = sorted((a for a in answers if a.target == "line"), key=lambda a: (a.box[1], a.box[0]))
    # A snapped box starts 1 mm in from the line and sits on it (see blanks.snap).
    return [(a.box[0] - 1.0, a.box[1] + a.box[3], f"Pen at blank {a.id}") for a in lines]
