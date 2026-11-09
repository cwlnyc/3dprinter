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
    # The paper's top edge faces the back of the printer (+Y) unless flipped,
    # when the sheet is turned round: top edge to the front, top-left corner at
    # the front right. fit_paper flips it when that keeps the sheet from
    # hanging off the bed's side, since the pen only reaches one side of it.
    paper_x: float = 0.0
    paper_y: float = 279.4
    paper_flipped: bool = False
    # A paper jig (hardware/paper_jig.scad) clipped to the bed's front-right
    # corner puts every sheet in the same place, turned round. With it on, that
    # fixed spot is used and no alignment stops are needed. jig_x / jig_y are
    # where the page's top-left corner lands, as measured by jig_calibrate.
    jig: bool = False
    jig_x: float = 228.0
    jig_y: float = -45.0
    # Pen tip minus nozzle position. Measure: draw a dot, compare to the nozzle.
    pen_offset_x: float = 0.0
    pen_offset_y: float = 0.0
    z_down: float = 0.0       # Z at which the pen touches paper (spring slightly compressed)
    z_up: float = 3.0         # Z for travel moves (never less than TRAVEL_CLEARANCE above z_down)
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

    def pen(self, x: float, y: float) -> tuple[float, float]:
        """Page mm (origin top-left, y down) to where that spot sits on the bed."""
        if self.paper_flipped:
            return self.paper_x - x, self.paper_y + y
        return self.paper_x + x, self.paper_y - y

    def to_bed(self, x: float, y: float) -> tuple[float, float]:
        """Page mm to the nozzle position that puts the pen there."""
        px, py = self.pen(x, y)
        return px - self.pen_offset_x, py - self.pen_offset_y

    @property
    def travel_z(self) -> float:
        # Paper that has lifted a little must not catch the pen between strokes:
        # a caught sheet gets dragged and scrunched, and the pen writes on it wherever it ends up.
        return max(self.z_up, self.z_down + TRAVEL_CLEARANCE)


TRAVEL_CLEARANCE = 4.5  # mm above pen-down for moves between strokes


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
    return [p.pen(x, y) for s in strokes for x, y in s]


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


def _overhang(lo: float, hi: float, p: Printer) -> float:
    """How far a sheet spanning lo..hi (bed X) hangs off the bed's sides.

    Off the front or back is harmless; off the sides it runs into the frame's
    uprights as the bed slides, and the sheet buckles.
    """
    return max(0.0, -lo) + max(0.0, hi - p.bed_x)


def fit_paper(strokes: list[Polyline], p: Printer, margin: float = 2.0, page_w: float = 215.9) -> Printer:
    """Choose where the paper goes so the answers sit in the middle of where the pen can write.

    A Letter page is taller than most beds, so the page overhangs front and
    back; that is fine. What is not fine is overhanging the sides, so both ways
    round are tried and the one hanging off the sides less is used. Where there
    is room to choose, the paper is also placed so its top-left corner is in
    reach, because that is the point the printer shows you to line up against.
    """
    xs = [x for s in strokes for x, _ in s]
    ys = [y for s in strokes for _, y in s]
    if not xs:
        return p
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    (x0, x1), (y0, y1) = pen_range(p)
    x0, x1, y0, y1 = x0 + margin, x1 - margin, y0 + margin, y1 - margin

    options = []
    for flipped in (False, True):
        q = Printer(**asdict(p))
        q.paper_flipped = flipped
        if not flipped:  # pen X = paper_x + x, pen Y = paper_y - y
            q.paper_x = round(_settle((x0 + x1) / 2 - cx, (x0 - min(xs), x1 - max(xs)), (x0, x1)), 1)
            q.paper_y = round(_settle((y0 + y1) / 2 + cy, (y0 + max(ys), y1 + min(ys)), (y0, y1)), 1)
            span = (q.paper_x, q.paper_x + page_w)
        else:  # pen X = paper_x - x, pen Y = paper_y + y
            q.paper_x = round(_settle((x0 + x1) / 2 + cx, (x0 + max(xs), x1 + min(xs)), (x0, x1)), 1)
            q.paper_y = round(_settle((y0 + y1) / 2 - cy, (y0 - min(ys), y1 - max(ys)), (y0, y1)), 1)
            span = (q.paper_x - page_w, q.paper_x)
        try:
            check_reach(strokes, q)
            fits = True
        except OutOfReach:
            fits = False
        options.append((not fits, _overhang(*span, p) - (0 if not flipped else 5.0), flipped, q))
    # Fits first, then least side overhang; turning the sheet round has to save
    # more than 5 mm to be worth the oddness of placing it upside down.
    return min(options, key=lambda o: (o[0], o[1], o[2]))[3]


def _reachable(p: Printer, page_x: float, page_y: float) -> bool:
    (x0, x1), (y0, y1) = pen_range(p)
    bx, by = p.pen(page_x, page_y)
    return x0 <= bx <= x1 and y0 <= by <= y1


def _say(p: Printer, msg: str) -> list[str]:
    """Show msg on the printer's screen while it waits for the knob."""
    return [f"M117 {msg}", f"M0 {msg}" if p.pause.strip().upper() == "M0" else p.pause]


Mark = tuple[float, float, str]  # page x, page y (mm), what to line up there


def alignment(p: Printer, marks: list[Mark] | None = None) -> list[str]:
    """Stops where the pen hovers over the paper, for lining the sheet up.

    The first stop fixes where the sheet sits: its top-left corner, or when that
    is out of reach, a printed mark such as the start of an answer line. The
    second fixes its angle: a point well down the left edge, or else a second
    mark far from the first. The pen hovers 2 mm above the pen-down height,
    clear of the sheet as it is slid underneath, but close enough to judge.
    Messages are short because the screen shows about 20 characters.
    """
    hover = p.z_down + 2.0
    reachable = [(x, y, m) for x, y, m in marks or [] if _reachable(p, x, y)]
    stops = []
    if _reachable(p, 0, 0):
        stops.append(((0.0, 0.0), "Top-left corner here"))
    elif reachable:
        x, y, m = reachable[0]
        stops.append(((x, y), m))
    edge = next((d for d in range(200, 59, -10) if _reachable(p, 0, d)), None)
    if edge is not None:
        stops.append(((0.0, float(edge)), "Left edge under pen"))
    elif stops and reachable:
        (ax, ay) = stops[0][0]
        far = max(reachable, key=lambda r: (r[0] - ax) ** 2 + (r[1] - ay) ** 2)
        if (far[0] - ax) ** 2 + (far[1] - ay) ** 2 >= 40 ** 2:
            stops.append(((far[0], far[1]), ("Turn: " + far[2].replace("Pen at ", ""))))
    out = []
    for (px, py), msg in stops:
        x, y = p.to_bed(px, py)
        out += [f"; alignment stop: page ({px:.0f}, {py:.0f}) mm",
                f"G0 Z{p.travel_z:.2f} F{p.feed_z}", f"G0 X{x:.2f} Y{y:.2f} F{p.feed_travel}",
                f"G0 Z{hover:.2f} F{p.feed_z}", *_say(p, msg[:20]), f"G0 Z{p.travel_z:.2f} F{p.feed_z}"]
    if not stops:
        out += ["; nothing on the sheet is in the pen's reach to line up against: place it by measurement",
                *_say(p, "Place paper, click")]
    return out


def place(strokes: list[Polyline], p: Printer, page_w: float = 215.9) -> tuple[Printer, bool]:
    """Where this sheet goes, and whether the G-code should stop to line it up.

    With the jig it always goes in the jig, so nothing needs lining up.
    """
    if p.jig:
        q = Printer(**asdict(p))
        q.paper_x, q.paper_y, q.paper_flipped = p.jig_x, p.jig_y, True
        return q, False
    return fit_paper(strokes, p, page_w=page_w), True


def jig_reach(p: Printer) -> tuple[tuple[float, float], tuple[float, float]]:
    """The part of the page (page mm) the pen can write on when the sheet is in the jig."""
    (x0, x1), (y0, y1) = pen_range(p)
    # turned round: pen X = jig_x - x, pen Y = jig_y + y
    return (p.jig_x - x1, p.jig_x - x0), (y0 - p.jig_y, y1 - p.jig_y)


JIG_TEST_MARKS = ((40.0, 80.0), (120.0, 190.0))  # page mm, both well inside the jig's reach


def jig_test(p: Printer) -> str:
    """G-code drawing two small crosses on a sheet in the jig, for jig_calibrate to measure."""
    q = Printer(**asdict(p))
    q.paper_x, q.paper_y, q.paper_flipped = p.jig_x, p.jig_y, True
    arm = 4.0
    strokes = []
    for x, y in JIG_TEST_MARKS:
        strokes += [[(x - arm, y), (x + arm, y)], [(x, y - arm), (x, y + arm)]]
    return generate(strokes, q, align=False)


def jig_calibrate(p: Printer, measured: list[tuple[float, float]]) -> Printer:
    """Correct the jig's position from where jig_test's crosses actually landed.

    measured: for each cross, its distance (mm) from the page's left edge and
    from its top edge, read with a ruler on the sheet the right way up.
    """
    q = Printer(**asdict(p))
    dx = [mx - x for (x, _), (mx, _) in zip(JIG_TEST_MARKS, measured)]
    dy = [my - y for (_, y), (_, my) in zip(JIG_TEST_MARKS, measured)]
    # turned round, a cross drawn at bed X = jig_x - x lands at page x = true_x - (jig_x - x)
    q.jig_x = round(p.jig_x + sum(dx) / len(dx), 1)
    # and at bed Y = jig_y + y lands at page y = (jig_y + y) - true_y
    q.jig_y = round(p.jig_y - sum(dy) / len(dy), 1)
    return q


@dataclass
class Pass:
    """One placement of the sheet and the answers written while it's there."""
    printer: Printer      # with paper_x / paper_y / paper_flipped for this pass
    answers: list[int]    # indexes of the answers written in this pass
    strokes: list[Polyline]
    align: bool           # stop to line the sheet up first (not needed in the jig)


def _bbox(strokes: list[Polyline]) -> tuple[float, float, float, float]:
    xs = [x for s in strokes for x, _ in s]
    ys = [y for s in strokes for _, y in s]
    return min(xs), min(ys), max(xs), max(ys)


def _fits(strokes: list[Polyline], p: Printer) -> bool:
    try:
        check_reach(strokes, p)
        return True
    except OutOfReach:
        return False


def plan_passes(per_answer: list[list[Polyline]], p: Printer, page_w: float = 215.9,
                margin: float = 2.0) -> list[Pass]:
    """Split the answers into as few placements of the sheet as reach allows.

    The pen reaches a window of the page about 14 x 21 cm on this printer. When
    the answers spread wider than that, the ones that fit are written first,
    then the printer stops and the sheet is moved (usually turned round) for
    the rest. With the jig, the first pass is whatever the jig position reaches.
    Raises OutOfReach only for an answer too big for the window on its own.
    """
    from .strokes import order_for_plotting

    todo = [i for i, s in enumerate(per_answer) if s]
    passes: list[Pass] = []
    if p.jig and todo:
        q, _ = place([], p, page_w)
        inside = [i for i in todo if _fits(per_answer[i], q)]
        if inside:
            passes.append(Pass(q, inside, order_for_plotting([s for i in inside for s in per_answer[i]]), False))
            todo = [i for i in todo if i not in inside]

    (x0, x1), (y0, y1) = pen_range(p)
    win_w, win_h = (x1 - x0) - 2 * margin, (y1 - y0) - 2 * margin
    boxes = {i: _bbox(per_answer[i]) for i in todo}
    while todo:
        # The window position (in page mm) holding the most remaining answers.
        xs = sorted({boxes[i][0] for i in todo} | {boxes[i][2] - win_w for i in todo})
        ys = sorted({boxes[i][1] for i in todo} | {boxes[i][3] - win_h for i in todo})
        best: list[int] = []
        for wx in xs:
            for wy in ys:
                inside = [i for i in todo if boxes[i][0] >= wx - 1e-6 and boxes[i][2] <= wx + win_w + 1e-6
                          and boxes[i][1] >= wy - 1e-6 and boxes[i][3] <= wy + win_h + 1e-6]
                if len(inside) > len(best):
                    best = inside
        if not best:
            too_big = [i for i in todo if boxes[i][2] - boxes[i][0] > win_w or boxes[i][3] - boxes[i][1] > win_h]
            raise OutOfReach(f"{len(too_big) or len(todo)} answer(s) are bigger than the pen can reach in one go")
        strokes = [s for i in best for s in per_answer[i]]
        q = fit_paper(strokes, p, margin=margin, page_w=page_w)
        if not _fits(strokes, q):  # very tight fit: try again without the safety margin
            q = fit_paper(strokes, p, margin=0.0, page_w=page_w)
        if not _fits(strokes, q):
            raise OutOfReach("couldn't place a group of answers within reach")
        q.jig = False
        passes.append(Pass(q, best, order_for_plotting(strokes), True))
        todo = [i for i in todo if i not in best]
    return passes


def _turn(p: Printer) -> str:
    return "title to FRONT" if p.paper_flipped else "title to BACK"


def generate_passes(passes: list[Pass], marks: list[Mark] | None = None) -> str:
    """One G-code file for every pass: between passes the printer parks and waits for the sheet to be moved."""
    if not passes:
        raise OutOfReach("nothing to write")
    first = passes[0].printer
    out = ["; homework-plotter", f"; {len(passes)} pass(es)"]
    for n, ps in enumerate(passes, 1):
        where = "in the jig" if not ps.align else \
            f"top-left corner at bed X{ps.printer.paper_x} Y{ps.printer.paper_y}, {_turn(ps.printer)}"
        out.append(f"; pass {n}: {len(ps.answers)} answer(s), sheet {where}")
    out += first.start.format(**asdict(first)).splitlines()
    for n, ps in enumerate(passes, 1):
        p = ps.printer
        check_reach(ps.strokes, p)
        out.append(f"G0 Z{p.travel_z + 10:.2f} F{p.feed_z}")
        if n > 1:
            # Park with the bed out front and wait while the sheet is moved.
            out += [f"; pass {n}: move the sheet", f"G0 X0 Y{p.bed_y:.2f} F{p.feed_travel}",
                    *_say(p, f"Turn: {_turn(p)}")]
        if ps.align:
            out += alignment(p, marks)
        out.append(f"G0 Z{p.travel_z:.2f} F{p.feed_z}")
        out.append(f"M117 Writing {n}/{len(passes)}" if len(passes) > 1 else "M117 Writing")
        for s in ps.strokes:
            if not s:
                continue
            x, y = p.to_bed(*s[0])
            out.append(f"G0 X{x:.2f} Y{y:.2f} F{p.feed_travel}")
            out.append(f"G1 Z{p.z_down:.2f} F{p.feed_z}")
            for px, py in s[1:]:
                x, y = p.to_bed(px, py)
                out.append(f"G1 X{x:.2f} Y{y:.2f} F{p.feed_draw}")
            out.append(f"G0 Z{p.travel_z:.2f} F{p.feed_z}")
    out += first.end.format(**asdict(first)).splitlines()
    return "\n".join(out) + "\n"


def generate(strokes: list[Polyline], p: Printer, align: bool = True, marks: list[Mark] | None = None) -> str:
    """A single pass with the sheet where p says."""
    return generate_passes([Pass(p, [], strokes, align)], marks)


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
    out.append(f"G0 Z{p.travel_z + 10:.2f} F{p.feed_z}")
    for line in lines:
        x, y = line[0]
        out.append(f"G0 X{x - p.pen_offset_x:.2f} Y{y - p.pen_offset_y:.2f} F{p.feed_travel}")
        out.append(f"G1 Z{p.z_down:.2f} F{p.feed_z}")
        for x, y in line[1:]:
            out.append(f"G1 X{x - p.pen_offset_x:.2f} Y{y - p.pen_offset_y:.2f} F{p.feed_draw}")
        out.append(f"G0 Z{p.travel_z:.2f} F{p.feed_z}")
    out += p.end.format(**asdict(p)).splitlines()
    return "\n".join(out) + "\n"
