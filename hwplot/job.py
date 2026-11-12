"""From answers to a print job: drawn in the hand, split into passes if need be, as G-code.

Shared by the web page, the connector and the command line, so they all place
sheets and split jobs the same way.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import render
from .gcode import Pass, Printer, generate_passes, plan_passes
from .glyphs import Hand
from .solve import Answer
from .strokes import Polyline, order_for_plotting


@dataclass
class Job:
    strokes: list[Polyline]   # everything, for the preview
    passes: list[Pass]
    gcode: str

    def steps(self, answers: list[Answer]) -> list[str]:
        """What the person does, pass by pass, in words."""
        out = []
        for n, ps in enumerate(self.passes, 1):
            ids = ", ".join(answers[i].id for i in ps.answers)
            if not ps.align:
                where = "in the jig"
            elif ps.printer.paper_flipped:
                where = "turned round (title towards you)"
            else:
                where = "the right way round (title to the back)"
            if n == 1:
                out.append(f"Pass 1: sheet {where}. Writes {ids}.")
            else:
                out.append(f"Pass {n}: the printer parks and its screen says how to turn the sheet: {where}. "
                           f"It then stops to line it up. Writes {ids}.")
        return out


def build(answers: list[Answer], hand: Hand, flat: np.ndarray | None, printer: Printer,
          page_w: float = 215.9, seed: int = 0, cap_mm: float = 5.0) -> Job:
    """Raises gcode.OutOfReach when an answer can't be reached in any placement."""
    per_answer = [render.render_answers([a], hand, flat, seed=seed + i, cap_mm=cap_mm)
                  for i, a in enumerate(answers)]
    passes = plan_passes(per_answer, printer, page_w)
    gcode = generate_passes(passes, marks=render.alignment_marks(answers))
    return Job(order_for_plotting([s for strokes in per_answer for s in strokes]), passes, gcode)
