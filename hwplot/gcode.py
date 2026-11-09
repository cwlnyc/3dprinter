"""Pen strokes on the page to G-code for a 3D printer carrying a pen.

The printer thinks in nozzle positions on its bed; the answers are in pen
positions on the paper. Two offsets connect them: where the paper's top-left
corner sits on the bed, and how far the pen tip is from the nozzle. Both live in
printer.json, measured once per printer.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .strokes import Polyline


@dataclass
class Printer:
    bed_x: float = 220.0
    bed_y: float = 220.0
    # Bed coordinates (mm) of the paper's top-left corner, as seen by the PEN.
    # The paper's top edge faces the back of the printer (+Y).
    paper_x: float = 0.0
    paper_y: float = 279.4
    # Pen tip minus nozzle position. Measure: draw a dot, compare to the nozzle.
    pen_offset_x: float = 0.0
    pen_offset_y: float = 0.0
    z_down: float = 0.0       # Z at which the pen touches paper (spring slightly compressed)
    z_up: float = 3.0         # Z for travel moves
    feed_draw: int = 1500     # mm/min
    feed_travel: int = 6000
    feed_z: int = 900
    start: str = "G28\nG90\nG21"
    pause: str = "M0"          # Klipper users: PAUSE
    end: str = "G0 Z15 F900\nG0 X0 Y{bed_y} F6000\nM84"

    @classmethod
    def load(cls, path: str) -> "Printer":
        with open(path) as f:
            return cls(**json.load(f))

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    def to_bed(self, x: float, y: float) -> tuple[float, float]:
        """Page mm (origin top-left, y down) to the nozzle position that puts the pen there."""
        return self.paper_x + x - self.pen_offset_x, self.paper_y - y - self.pen_offset_y


class OutOfReach(ValueError):
    pass


def pen_range(p: Printer) -> tuple[tuple[float, float], tuple[float, float]]:
    """Where on the bed the pen can write: under the pen's travel AND over the bed.

    The pen sits beside the nozzle, so its travel is the nozzle's shifted by the
    offset. Past the bed's edge the paper hangs in the air with nothing to press
    against, so those spots do not count either.
    """
    x0, x1 = max(0.0, p.pen_offset_x), min(p.bed_x, p.bed_x + p.pen_offset_x)
    y0, y1 = max(0.0, p.pen_offset_y), min(p.bed_y, p.bed_y + p.pen_offset_y)
    return (x0, x1), (y0, y1)


def _pen_points(strokes: list[Polyline], p: Printer) -> list[tuple[float, float]]:
    return [(p.paper_x + x, p.paper_y - y) for s in strokes for x, y in s]


def check_reach(strokes: list[Polyline], p: Printer) -> None:
    pts = _pen_points(strokes, p)
    if not pts:
        return
    xs, ys = [a for a, _ in pts], [b for _, b in pts]
    (x0, x1), (y0, y1) = pen_range(p)
    bad = []
    if min(xs) < x0 - 1e-6 or max(xs) > x1 + 1e-6:
        bad.append(f"X {min(xs):.0f}..{max(xs):.0f} (pen can write {x0:.0f}..{x1:.0f})")
    if min(ys) < y0 - 1e-6 or max(ys) > y1 + 1e-6:
        bad.append(f"Y {min(ys):.0f}..{max(ys):.0f} (pen can write {y0:.0f}..{y1:.0f})")
    if bad:
        raise OutOfReach(
            "answers fall outside where the pen can write: " + "; ".join(bad)
            + ". Move the paper (paper_x / paper_y) or use --fit."
        )


def _settle(centred: float, allowed: tuple[float, float], preferred: tuple[float, float]) -> float:
    """centred, moved as little as possible into allowed, and into preferred too if both can hold."""
    lo, hi = allowed
    if lo > hi:  # answers wider than the reach; check_reach will say so
        return centred
    plo, phi = max(lo, preferred[0]), min(hi, preferred[1])
    if plo <= phi:
        lo, hi = plo, phi
    return min(max(centred, lo), hi)


def fit_paper(strokes: list[Polyline], p: Printer, margin: float = 2.0) -> Printer:
    """Choose paper_x / paper_y so the answers sit in the middle of where the pen can write.

    A Letter page is taller than most beds, so the page usually overhangs. That
    is fine: only the parts with answers need to be under the pen. Where there
    is room to choose, the paper is placed so its top-left corner is also in
    reach, because that is the point the printer shows you to line the paper
    up against (see generate).
    """
    xs = [x for s in strokes for x, _ in s]
    ys = [y for s in strokes for _, y in s]
    if not xs:
        return p
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    (x0, x1), (y0, y1) = pen_range(p)
    x0, x1, y0, y1 = x0 + margin, x1 - margin, y0 + margin, y1 - margin
    q = Printer(**asdict(p))
    # pen X of a point = paper_x + x; pen Y = paper_y - y (page y runs down, bed Y runs back)
    q.paper_x = round(_settle((x0 + x1) / 2 - cx, (x0 - min(xs), x1 - max(xs)), (x0, x1)), 1)
    q.paper_y = round(_settle((y0 + y1) / 2 + cy, (y0 + max(ys), y1 + min(ys)), (y0, y1)), 1)
    return q


def _reachable(p: Printer, page_x: float, page_y: float) -> bool:
    (x0, x1), (y0, y1) = pen_range(p)
    return x0 <= p.paper_x + page_x <= x1 and y0 <= p.paper_y - page_y <= y1


def _say(p: Printer, msg: str) -> list[str]:
    """Show msg on the printer's screen while it waits for the knob."""
    return [f"M117 {msg}", f"M0 {msg}" if p.pause.strip().upper() == "M0" else p.pause]


Mark = tuple[float, float, str]  # page x, page y (mm), what to line up there


def alignment(p: Printer, marks: list[Mark] | None = None) -> list[str]:
    """Stops where the pen hovers over the paper, for lining the sheet up.

    One stop fixes where the sheet sits: its top-left corner, or, when the
    answers run too far down the page for the corner to be in reach, a mark on
    the sheet itself such as the start of the first answer line. A second stop
    well down the left edge fixes its angle. The pen hovers 1 mm above the
    paper so the gap is easy to judge without marking anything. Messages are
    short because the screen shows about 20 characters.
    """
    hover = p.z_down + 1.0
    stops = []
    if _reachable(p, 0, 0):
        stops.append(((0.0, 0.0), "Corner under pen"))
    else:
        mark = next(((x, y, m) for x, y, m in marks or [] if _reachable(p, x, y)), None)
        if mark:
            stops.append(((mark[0], mark[1]), mark[2][:20]))
    edge = next((d for d in range(200, 59, -10) if _reachable(p, 0, d)), None)
    if edge is not None:
        stops.append(((0.0, float(edge)), "Left edge under pen"))
    out = []
    for (px, py), msg in stops:
        x, y = p.to_bed(px, py)
        out += [f"; alignment stop: page ({px:.0f}, {py:.0f}) mm",
                f"G0 Z{p.z_up:.2f} F{p.feed_z}", f"G0 X{x:.2f} Y{y:.2f} F{p.feed_travel}",
                f"G0 Z{hover:.2f} F{p.feed_z}", *_say(p, msg), f"G0 Z{p.z_up:.2f} F{p.feed_z}"]
    if not stops:
        out += ["; the paper's left edge is out of the pen's reach: place it by measurement", *_say(p, "Place paper, click")]
    return out


def generate(strokes: list[Polyline], p: Printer, align: bool = True, marks: list[Mark] | None = None) -> str:
    check_reach(strokes, p)
    out = ["; homework-plotter", f"; paper top-left corner at bed X{p.paper_x} Y{p.paper_y} (pen position)"]
    out += p.start.format(**asdict(p)).splitlines()
    out.append(f"G0 Z{p.z_up + 10:.2f} F{p.feed_z}")
    if align:
        out += alignment(p, marks)
    out.append(f"G0 Z{p.z_up:.2f} F{p.feed_z}")
    out.append("M117 Writing")
    for s in strokes:
        if not s:
            continue
        x, y = p.to_bed(*s[0])
        out.append(f"G0 X{x:.2f} Y{y:.2f} F{p.feed_travel}")
        out.append(f"G1 Z{p.z_down:.2f} F{p.feed_z}")
        for px, py in s[1:]:
            x, y = p.to_bed(px, py)
            out.append(f"G1 X{x:.2f} Y{y:.2f} F{p.feed_draw}")
        out.append(f"G0 Z{p.z_up:.2f} F{p.feed_z}")
    out += p.end.format(**asdict(p)).splitlines()
    return "\n".join(out) + "\n"


def test_pattern(p: Printer, size: float = 30.0) -> str:
    """A square with a cross through it, centred on the bed.

    Run this with a scrap sheet down before anything else. Faint or broken lines
    mean z_down is too high; a gouged or wobbly line means it is too low.
    """
    cx, cy = p.bed_x / 2, p.bed_y / 2
    h = size / 2
    # Expressed in pen positions on the bed, converted to nozzle positions.
    lines = [
        [(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h), (cx - h, cy - h)],
        [(cx - h, cy), (cx + h, cy)],
        [(cx, cy - h), (cx, cy + h)],
    ]
    out = ["; homework-plotter test pattern: 30 mm square and cross at bed centre"]
    out += p.start.format(**asdict(p)).splitlines()
    out.append(f"G0 Z{p.z_up + 10:.2f} F{p.feed_z}")
    for line in lines:
        x, y = line[0]
        out.append(f"G0 X{x - p.pen_offset_x:.2f} Y{y - p.pen_offset_y:.2f} F{p.feed_travel}")
        out.append(f"G1 Z{p.z_down:.2f} F{p.feed_z}")
        for x, y in line[1:]:
            out.append(f"G1 X{x - p.pen_offset_x:.2f} Y{y - p.pen_offset_y:.2f} F{p.feed_draw}")
        out.append(f"G0 Z{p.z_up:.2f} F{p.feed_z}")
    out += p.end.format(**asdict(p)).splitlines()
    return "\n".join(out) + "\n"
