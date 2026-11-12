"""End to end without a pen or an API key: fake a filled-in sample sheet, photograph
it at an angle, learn from it, and lay out answers in the learned hand."""
import random

import cv2
import numpy as np
import pytest

from hwplot import page, render, template
from hwplot.gcode import OutOfReach, Printer, fit_paper, generate
from hwplot.glyphs import learn
from hwplot.solve import Answer
from hwplot.strokes import trace

DPI = 200


def filled_page(p: int) -> np.ndarray:
    """A template page with each box 'handwritten' in OpenCV's script font."""
    img = np.array(template.render_page(p, dpi=DPI).convert("RGB"))[:, :, ::-1].copy()
    px = DPI / 25.4
    for cell in (c for c in template.cells() if c.page == p):
        org = (round((cell.x + 3) * px), round((cell.y + template.BASELINE_FROM_TOP) * px))
        cv2.putText(img, cell.char, org, cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 2.0, (20, 20, 20), 3, cv2.LINE_AA)
    return img


def photographed(img: np.ndarray) -> np.ndarray:
    """Put the sheet on a dark table, tilted, as a phone would see it."""
    h, w = img.shape[:2]
    canvas = np.full((h + 400, w + 400, 3), 60, np.uint8)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[230, 180], [w + 160, 240], [w + 210, h + 330], [170, h + 260]])
    m = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, m, (canvas.shape[1], canvas.shape[0]), dst=canvas, borderMode=cv2.BORDER_TRANSPARENT)


@pytest.fixture(scope="module")
def hand():
    scans = [photographed(filled_page(p)) for p in range(template.core_page_count())]
    h, warnings, _ = learn(scans)
    return h, warnings


def test_every_character_is_learned_from_tilted_photos(hand):
    h, warnings = hand
    assert set(template.CHARSET) <= set(h.glyphs), warnings
    assert all(len(h.glyphs[c]) == template.COPIES for c in "aZ7?")
    assert 3 < h.cap_height < 12


def test_descenders_hang_below_the_baseline(hand):
    h, _ = hand
    lo_g = max(y for s in h.glyphs["g"][0].strokes for _, y in s)
    lo_x = max(y for s in h.glyphs["x"][0].strokes for _, y in s)
    assert lo_g > lo_x + 0.2 * h.cap_height


def test_trace_turns_a_thick_line_into_one_stroke():
    m = np.zeros((40, 120), np.uint8)
    cv2.line(m, (10, 20), (110, 20), 255, 7)
    lines = trace(m)
    assert len(lines) == 1
    xs = [x for x, _ in lines[0]]
    assert min(xs) < 16 and max(xs) > 104


def test_writing_stays_in_its_box(hand):
    h, _ = hand
    box = (30.0, 40.0, 60.0, 12.0)
    strokes = render.write("x = 42", box, h, random.Random(1))
    xs = [x for s in strokes for x, _ in s]
    ys = [y for s in strokes for _, y in s]
    assert strokes
    assert box[0] - 1 <= min(xs) and max(xs) <= box[0] + box[2] + 1
    assert box[1] - 1 <= min(ys) and max(ys) <= box[1] + box[3] + 2


def test_long_answers_wrap_and_shrink(hand):
    h, _ = hand
    box = (20.0, 20.0, 40.0, 20.0)
    strokes = render.write("the mitochondria is the powerhouse of the cell", box, h, random.Random(2))
    xs = [x for s in strokes for x, _ in s]
    assert max(xs) <= box[0] + box[2] + 1.5


def test_gcode_lifts_between_strokes_and_maps_page_to_bed(hand):
    h, _ = hand
    answers = [Answer("1", "2+2", "4", "write", (100.0, 100.0, 20.0, 10.0), "high")]
    strokes = render.render_answers(answers, h)
    p = fit_paper(strokes, Printer())
    code = generate(strokes, p)
    downs = code.count(f"Z{p.z_down:.2f}")
    assert downs == len(strokes)
    for line in code.splitlines():
        if line.startswith(("G0 X", "G1 X")):
            x, y = (float(t[1:]) for t in line.split()[1:3])
            assert 0 <= x <= p.bed_x and 0 <= y <= p.bed_y


def test_gcode_refuses_answers_the_printer_cannot_reach(hand):
    h, _ = hand
    # Near the top of a Letter page: 260 mm up the bed, past a 220 mm bed.
    answers = [Answer("9", "q", "7", "write", (20.0, 10.0, 20.0, 10.0), "high")]
    strokes = render.render_answers(answers, h)
    with pytest.raises(OutOfReach):
        generate(strokes, Printer(paper_x=0, paper_y=279.4))


def test_page_is_found_and_flattened():
    sheet = np.full((1100, 850, 3), 245, np.uint8)
    cv2.putText(sheet, "1. 3 x 4 = ____", (80, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)
    flat = page.flatten(photographed(sheet))
    assert flat.shape[:2] == (round(page.LETTER_MM[1] * page.PX_PER_MM), round(page.LETTER_MM[0] * page.PX_PER_MM))
    assert flat[:40].mean() > 200  # corners are paper, not table


def test_underline_is_used_as_the_writing_line():
    flat = np.full((600, 600, 3), 255, np.uint8)
    cv2.line(flat, (60, 300), (300, 300), (0, 0, 0), 2)
    y = render.find_writing_line(flat, (8.0, 40.0, 45.0, 15.0))
    assert y is not None and abs(y - 300 / page.PX_PER_MM) < 0.5


def test_fit_centres_the_pen_not_the_nozzle_when_the_pen_is_beside_it(hand):
    h, _ = hand
    answers = [Answer("1", "q", "84", "write", (100.0, 100.0, 20.0, 10.0), "high")]
    strokes = render.render_answers(answers, h)
    # Holder on the right side of the print head: pen 62 mm right of the nozzle.
    p = fit_paper(strokes, Printer(pen_offset_x=62.0))
    pen_xs = [p.pen(x, y)[0] for s in strokes for x, y in s]
    assert 62 <= min(pen_xs) and max(pen_xs) <= 220  # inside the strip the pen can reach
    assert 62 <= p.paper_x <= 220  # and the paper's corner is too, so it can be pointed at
    code = generate(strokes, p)
    for line in code.splitlines():
        if line.startswith(("G0 X", "G1 X")):
            x = float(line.split()[1][1:])
            assert 0 <= x <= p.bed_x


def test_pen_never_writes_off_the_edge_of_the_bed(hand):
    h, _ = hand
    answers = [Answer("1", "q", "84", "write", (100.0, 100.0, 20.0, 10.0), "high")]
    strokes = render.render_answers(answers, h)
    # Nozzle could reach, but the pen would be out past the bed's right edge.
    with pytest.raises(OutOfReach):
        generate(strokes, Printer(pen_offset_x=62.0, paper_x=125.0, paper_y=200.0))


def test_paper_is_placed_so_its_corner_can_be_pointed_at(hand):
    h, _ = hand
    # Like the Spanish vocab sheets: two answer columns down most of the page.
    answers = [Answer(str(i), "q", "A", "write", (x, y, 6.0, 4.4), "high", "line")
               for i, (x, y) in enumerate([(25, 55), (108, 55), (25, 190), (108, 190)])]
    strokes = render.render_answers(answers, h)
    me = Printer(pen_offset_x=77.9, pen_offset_y=-12.2, z_down=1.7, z_up=4.7)
    p = fit_paper(strokes, me)
    code = generate(strokes, p)
    assert "Top-left corner here" in code and "Left edge under pen" in code
    # the corner stop really puts the pen over the corner
    corner_nozzle = p.to_bed(0, 0)
    assert f"G0 X{corner_nozzle[0]:.2f} Y{corner_nozzle[1]:.2f}" in code
    # and it hovers clear of the paper rather than touching it
    assert "G0 Z3.70" in code


def test_when_the_corner_is_out_of_reach_the_pen_points_at_the_first_blank(hand):
    h, _ = hand
    # Answers from near the top to near the bottom: too tall for the corner to be in reach too.
    answers = [Answer("1", "q", "A", "write", (30.0, 60.0, 6.0, 4.4), "high", "line"),
               Answer("2", "q", "B", "write", (30.0, 212.0, 6.0, 4.4), "high", "line")]
    strokes = render.render_answers(answers, h)
    p = fit_paper(strokes, Printer(pen_offset_x=77.9, pen_offset_y=-12.2, z_down=1.7, z_up=4.7))
    code = generate(strokes, p, marks=render.alignment_marks(answers))
    assert "Top-left corner here" not in code
    assert "M0 Pen at blank 1" in code
    nozzle = p.to_bed(29.0, 64.4)  # where blank 1's line starts
    assert f"G0 X{nozzle[0]:.2f} Y{nozzle[1]:.2f}" in code


def test_sheet_is_turned_round_when_that_keeps_it_off_the_frame(hand):
    h, _ = hand
    # Answers in the left half of the page, pen far to the right of the nozzle:
    # the right-hand side of the page used to hang ~7 cm off the bed into the upright.
    answers = [Answer(str(i), "q", "A", "write", (x, y, 6.0, 4.4), "high", "line")
               for i, (x, y) in enumerate([(25, 60), (115, 60), (25, 200), (115, 200)])]
    strokes = render.render_answers(answers, h)
    me = Printer(pen_offset_x=77.9, pen_offset_y=-12.2, z_down=1.7, z_up=4.7)
    p = fit_paper(strokes, me)
    assert p.paper_flipped
    lo, hi = p.paper_x - 215.9, p.paper_x
    assert hi <= me.bed_x + 1 and lo >= -25  # barely off the bed's sides now
    code = generate(strokes, p, marks=render.alignment_marks(answers))
    pen_xs = [p.pen(x, y)[0] for s in strokes for x, y in s]
    assert min(pen_xs) >= 77.9 and max(pen_xs) <= 220
    assert "TURNED" not in code and "FRONT" in code  # the file says which way round


def test_travel_never_skims_the_paper():
    p = Printer(z_down=1.7, z_up=2.2)
    assert p.travel_z >= 1.7 + 4.5
