

def test_a_sample_far_taller_than_the_rest_is_not_written():
    from hwplot.glyphs import Glyph, Hand
    h = Hand()
    h.x_height = 5.0
    small = Glyph([[(0, -5), (2, 0), (4, -5)]], 4)
    h.glyphs["v"] = [small, Glyph([[(0, -5.5), (2, 1), (4, -5.5)]], 4), Glyph([[(0, -9), (2, 3), (4, -9)]], 5)]
    assert len(h.variants("v")) == 2 and all(g.height() < 7 for g in h.variants("v"))
