"""Fresh letters each time, and samples that add up instead of replacing each other."""
import random

import numpy as np

from hwplot import template
from hwplot.glyphs import Glyph, Hand, blend, learn, wobble

from test_pipeline import filled_page, photographed


def line(x0, y0, x1, y1):
    return [(x0, y0), (x1, y1)]


def test_blend_lands_between_the_two_samples():
    a = Glyph([line(0, 0, 0, -6)], 0.0)
    b = Glyph([line(0, 0, 2, -6)], 2.0)
    mid = blend(a, b, 0.5)
    top = mid.strokes[0][-1] if mid.strokes[0][-1][1] < mid.strokes[0][0][1] else mid.strokes[0][0]
    assert abs(top[0] - 1.0) < 0.05 and abs(top[1] + 6) < 0.05


def test_blend_matches_strokes_written_in_a_different_order_and_direction():
    # A '+' written across-then-down, and down-then-across with the stroke reversed.
    a = Glyph([line(0, -3, 4, -3), line(2, -5, 2, -1)], 4.0)
    b = Glyph([line(2, -1, 2, -5), line(4, -3, 0, -3)], 4.0)
    mid = blend(a, b, 0.5)
    for s in mid.strokes:
        pts = np.array(s)
        assert np.ptp(pts[:, 0]) > 3.5 or np.ptp(pts[:, 1]) > 3.5  # still a full bar, not collapsed


def test_letters_written_differently_are_not_blended_into_mush():
    a = Glyph([line(0, 0, 0, -6)], 0.0)
    b = Glyph([line(0, -3, 6, -3)], 6.0)  # same stroke count, nothing alike
    assert blend(a, b, 0.5) is None


def test_wobble_keeps_touching_strokes_touching():
    g = Glyph([line(0, -3, 4, -3), line(4, -3, 4, 0)], 4.0)
    w = wobble(g, random.Random(3), 0.3)
    assert np.hypot(w.strokes[0][-1][0] - w.strokes[1][0][0], w.strokes[0][-1][1] - w.strokes[1][0][1]) < 1e-9


def test_make_gives_a_different_letter_each_time():
    a = Glyph([line(0, 0, 0, -6)], 0.0)
    b = Glyph([line(0, 0, 1.5, -6)], 1.5)
    hand = Hand({"l": [a, b]}, cap_height=6.0)
    rng = random.Random(0)
    tops = {round(hand.make("l", rng).strokes[0][-1][0], 3) for _ in range(10)}
    assert len(tops) > 5


def test_learning_adds_to_what_it_knows_and_ignores_a_repeat_scan():
    p0 = photographed(filled_page(0))
    hand, _, added = learn([p0])
    first = sum(len(v) for v in hand.glyphs.values())
    assert added == first > 0
    hand, _, again = learn([p0], hand)
    assert again == 0
    assert sum(len(v) for v in hand.glyphs.values()) == first


def test_saved_hand_keeps_its_style(tmp_path):
    hand = Hand({"a": [Glyph([line(0, 0, 1, -3)], 1.0)]})
    hand.style.letter_gap = 0.2
    hand.save(str(tmp_path / "h.json"))
    assert Hand.load(str(tmp_path / "h.json")).style.letter_gap == 0.2
