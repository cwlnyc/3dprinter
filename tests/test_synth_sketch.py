"""Characters the writer never wrote, and drawings, both in the writer's hand."""
import math
import random

import numpy as np
import pytest

from hwplot import sketch, synth, template
from hwplot.glyphs import learn

from test_pipeline import filled_page, photographed


@pytest.fixture(scope="module")
def hand():
    h, _, _ = learn([photographed(filled_page(p)) for p in range(template.core_page_count())])
    return h


def top(g):
    return min(y for s in g.strokes for _, y in s)


def bottom(g):
    return max(y for s in g.strokes for _, y in s)


def test_everything_spanish_and_maths_needs_can_be_written(hand):
    text = "áéíóúñüÁÉÍÓÚÑÜ¿¡ ×÷±≤≥≠≈√π∞θ°²³→←↑↓αβΔ–—…·“”’"
    assert hand.missing(text) == set()


def test_an_accent_sits_above_the_writers_own_letter(hand):
    g = synth.make("á", hand, random.Random(1))
    *letter, accent = g.strokes  # the accent is added last
    letter_top = min(y for s in letter for _, y in s)
    assert max(y for _, y in accent) < letter_top  # entirely above the letter
    assert letter_top - min(y for _, y in accent) < 0.8 * hand.cap_height  # and close to it


def test_a_squared_two_is_small_and_raised(hand):
    rng = random.Random(2)
    two, sq = hand.make("2", rng), synth.make("²", hand, rng)
    assert (bottom(sq) - top(sq)) < 0.75 * (bottom(two) - top(two))
    assert bottom(sq) < -0.3 * hand.cap_height


def test_inverted_question_mark_hangs_below_the_line(hand):
    g = synth.make("¿", hand, random.Random(3))
    assert bottom(g) > 0.1 * hand.cap_height


def test_drawn_symbols_take_the_writers_slant(hand):
    hand.style.slant_deg = 15.0
    g = synth.make("↑", hand, random.Random(4))
    shaft = max(g.strokes, key=lambda s: max(y for _, y in s) - min(y for _, y in s))
    (x_top, y_top), (x_bot, y_bot) = min(shaft, key=lambda p: p[1]), max(shaft, key=lambda p: p[1])
    assert x_top > x_bot  # leans right like the writer
    hand.measure()  # put the measured slant back


def test_a_hand_drawn_line_is_close_to_true_but_never_ruler_straight():
    p0, p1 = (10.0, 10.0), (110.0, 10.0)
    for seed in range(5):
        (s,) = sketch.draw({"type": "line", "points": [p0, p1]}, random.Random(seed))
        ys = [y for _, y in s]
        assert max(abs(y - 10) for y in ys) < 2.5  # still reads as that line
        assert np.ptp(ys) > 0.2  # but not perfectly straight
        assert abs(s[0][0] - 10) < 1 and 110 <= s[-1][0] < 111.5  # ends near target, a touch past


def test_a_hand_drawn_circle_overlaps_where_it_closes():
    (s,) = sketch.draw({"type": "circle", "points": [[50, 50]], "r": 10}, random.Random(0))
    angles = np.unwrap([math.atan2(y - 50, x - 50) for x, y in s])
    assert abs(angles[-1] - angles[0]) > 2 * math.pi  # goes past where it started
    radii = [math.hypot(x - 50, y - 50) for x, y in s]
    assert 8.5 < min(radii) and max(radii) < 11.5


def test_a_curve_goes_through_its_points():
    pts = [[10, 50], [30, 40], [50, 35], [70, 20]]
    (s,) = sketch.draw({"type": "curve", "points": pts}, random.Random(0))
    for px, py in pts:
        assert min(math.hypot(x - px, y - py) for x, y in s) < 0.6


def test_ink_is_drawn_exactly_as_given():
    pts = [[1.0, 2.0], [3.5, 2.5], [4.0, 6.0]]
    (s,) = sketch.draw({"type": "ink", "points": pts}, random.Random(0))
    assert [list(p) for p in s] == pts
