

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
