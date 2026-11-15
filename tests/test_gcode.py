import pytest


def test_start_turns_the_levelling_map_on(tmp_path):
    import json
    from hwplot.gcode import Printer
    assert "M420 S1" in Printer().start.splitlines()
    old = tmp_path / "printer.json"
    old.write_text(json.dumps({**Printer().__dict__, "start": "G28\nG90\nG21"}))
    assert "M420 S1" in Printer.load(str(old)).start
    custom = tmp_path / "custom.json"
    custom.write_text(json.dumps({**Printer().__dict__, "start": "G28\nG29"}))
    assert Printer.load(str(custom)).start == "G28\nG29"


def test_with_the_jig_on_the_pen_keeps_clear_of_its_wall_and_clips():
    from hwplot.gcode import JIG_PAGE_TOP_TO_BED, JIG_WALL_CLEARANCE, Printer, jig_reach, pen_range
    plain = Printer(pen_offset_x=77.9, pen_offset_y=-12.2)
    jig = Printer(pen_offset_x=77.9, pen_offset_y=-12.2, jig=True)
    (_, x1), (y0, _) = pen_range(jig)
    assert x1 == jig.jig_x - JIG_WALL_CLEARANCE < pen_range(plain)[0][1]
    assert y0 == 0  # as built, the bed's front edge is where the printer thinks it is
    # a calibration that finds the jig 3 mm further back moves the front limit with it
    moved = Printer(pen_offset_x=77.9, pen_offset_y=-12.2, jig=True, jig_y=jig.jig_y + 3)
    assert pen_range(moved)[1][0] == pytest.approx(3)
    # in page terms: never nearer than the clearance to the page's left edge, nor above the bed's edge
    (xa, _), (ya, _) = jig_reach(moved)
    assert xa == pytest.approx(JIG_WALL_CLEARANCE) and ya == pytest.approx(JIG_PAGE_TOP_TO_BED)
