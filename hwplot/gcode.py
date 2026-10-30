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


def check_reach(strokes: list[Polyline], p: Printer) -> None:
    pts = [p.to_bed(x, y) for s in strokes for x, y in s]
    if not pts:
        return
    xs, ys = [a for a, _ in pts], [b for _, b in pts]
    bad = []
    if min(xs) < 0 or max(xs) > p.bed_x:
        bad.append(f"X {min(xs):.0f}..{max(xs):.0f} (bed 0..{p.bed_x:.0f})")
    if min(ys) < 0 or max(ys) > p.bed_y:
        bad.append(f"Y {min(ys):.0f}..{max(ys):.0f} (bed 0..{p.bed_y:.0f})")
    if bad:
        raise OutOfReach(
            "answers fall outside what the printer can reach: " + "; ".join(bad)
            + ". Move the paper (paper_x / paper_y) or use --fit."
        )


def fit_paper(strokes: list[Polyline], p: Printer) -> Printer:
    """Choose paper_x / paper_y so the answers sit in the middle of the bed.

    A Letter page is taller than most beds, so the page usually overhangs. That
    is fine: only the parts with answers need to be under the pen.
    """
    xs = [x for s in strokes for x, _ in s]
    ys = [y for s in strokes for _, y in s]
    if not xs:
        return p
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    q = Printer(**asdict(p))
    q.paper_x = round(p.bed_x / 2 - cx + p.pen_offset_x, 1)
    q.paper_y = round(p.bed_y / 2 + cy + p.pen_offset_y, 1)
    return q


def generate(strokes: list[Polyline], p: Printer, align: bool = True) -> str:
    check_reach(strokes, p)
    out = ["; homework-plotter", f"; paper top-left corner at bed X{p.paper_x} Y{p.paper_y} (pen position)"]
    out += p.start.format(**asdict(p)).splitlines()
    out.append(f"G0 Z{p.z_up + 10:.2f} F{p.feed_z}")
    if align:
        cx, cy = p.to_bed(0, 0)
        if 0 <= cx <= p.bed_x and 0 <= cy <= p.bed_y:
            out += [
                f"G0 X{cx:.2f} Y{cy:.2f} F{p.feed_travel}",
                f"G0 Z{p.z_up:.2f} F{p.feed_z}",
                "; line the paper's top-left corner up under the pen tip, then resume",
                p.pause,
            ]
        else:
            out += ["; paper corner is off the bed - place the paper by measurement", p.pause]
    out.append(f"G0 Z{p.z_up:.2f} F{p.feed_z}")
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
