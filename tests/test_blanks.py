"""Answers land on the sheet's own lines and boxes, not just near them."""
import cv2
import numpy as np

from hwplot import blanks
from hwplot.page import LETTER_MM, PX_PER_MM
from hwplot.solve import Answer


def px(mm):
    return round(mm * PX_PER_MM)


def sheet():
    w, h = px(LETTER_MM[0]), px(LETTER_MM[1])
    img = np.full((h, w, 3), 250, np.uint8)
    cv2.putText(img, "1. 12 x 7 =", (px(20), px(40)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    cv2.line(img, (px(120), px(40)), (px(180), px(40)), (0, 0, 0), 2)          # answer line
    cv2.putText(img, "2. Name a prime", (px(20), px(80)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    cv2.rectangle(img, (px(120), px(70)), (px(180), px(90)), (0, 0, 0), 2)     # answer box
    cv2.putText(img, "A) 9   B) 11", (px(20), px(130)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    return img


def test_finds_the_line_and_the_box():
    found = blanks.find_blanks(sheet())
    lines = [b for b in found if b.kind == "line"]
    boxes = [b for b in found if b.kind == "box"]
    assert any(abs(b.y - 40) < 1 and abs(b.x - 120) < 1.5 and abs(b.w - 60) < 2 for b in lines)
    assert any(abs(b.x - 120) < 1.5 and abs(b.y - 70) < 1.5 for b in boxes)
    # the box's own edges are not reported as separate answer lines
    assert not any(abs(b.y - 70) < 1.5 or abs(b.y - 90) < 1.5 for b in lines)


def test_a_box_a_few_mm_off_snaps_onto_the_line():
    a = Answer("1", "", "84", "write", (126.0, 26.0, 40.0, 10.0), "high")  # 4 mm above the line
    assert blanks.snap([a], sheet()) == 1
    assert a.target == "line"
    assert abs(a.box[1] + a.box[3] - 40) < 1  # box bottom is the line


def test_two_answers_do_not_share_one_line():
    a = Answer("1", "", "84", "write", (126.0, 29.0, 40.0, 10.0), "high")
    b = Answer("1b", "", "85", "write", (126.0, 31.0, 40.0, 10.0), "high")
    blanks.snap([a, b], sheet())
    assert sorted([a.target, b.target]) in (["line", "none"], ["box", "line"])


def test_far_away_boxes_are_left_alone():
    a = Answer("9", "", "x", "write", (20.0, 200.0, 30.0, 10.0), "high")
    blanks.snap([a], sheet())
    assert a.target == "none" and a.box == (20.0, 200.0, 30.0, 10.0)


def test_circle_tightens_onto_the_printed_option():
    a = Answer("3", "", "B", "circle", (33.0, 120.0, 17.0, 14.0), "high")  # loose, around "B) 11"
    blanks.snap([a], sheet())
    assert a.target == "option"
    x, y, w, h = a.box
    assert w < 17 and h < 8
    assert 33 <= x < 35 and 125 <= y < 127  # hugs the printed "B) 11"


def test_short_numbered_blanks_are_found():
    # Vocabulary sheets use "1.___" blanks only about 5 mm long.
    img = sheet()
    cv2.line(img, (px(30), px(160)), (px(35.5), px(160)), (0, 0, 0), 2)
    found = blanks.find_blanks(img)
    assert any(b.kind == "line" and abs(b.y - 160) < 1 and abs(b.x - 30) < 1 for b in found)
