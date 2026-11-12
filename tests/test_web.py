"""The local web page, driven through Flask's test client. The Claude call is faked."""
import io

import cv2
import pytest

from hwplot import solve as solve_mod
from hwplot import template, web
from hwplot.solve import Answer

from test_pipeline import filled_page, photographed


def png(img) -> io.BytesIO:
    ok, buf = cv2.imencode(".jpg", img)
    return io.BytesIO(buf.tobytes())


@pytest.fixture
def client(tmp_path):
    app = web.create_app(tmp_path)
    app.testing = True
    return app.test_client()


def test_whole_flow(client, monkeypatch):
    assert b"Teach it your handwriting" in client.get("/").data
    assert client.get("/template.pdf").data[:4] == b"%PDF"
    assert len(client.get("/hardware/pen_holder_8mm.stl").data) > 1000

    pages = [(png(photographed(filled_page(p))), f"p{p}.jpg") for p in range(template.core_page_count())]
    r = client.post("/learn", data={"scans": pages}, content_type="multipart/form-data", follow_redirects=True)
    assert b"88 characters" in r.data and b"Added" in r.data
    assert client.get("/specimen.png").data[:4] == b"\x89PNG"

    r = client.post("/printer", data={"bed_x": "235", "z_down": "1.2"}, follow_redirects=True)
    assert b"saved" in r.data
    assert b"G1 Z1.20" in client.get("/test-pattern.gcode").data

    used = {}

    def fake_solve(flat, charset, client=None, model=solve_mod.MODEL):
        used["model"] = model
        return ([Answer("1", "12 x 7", "84", "write", (140.0, 40.0, 40.0, 10.0), "high")], "all fine",
                solve_mod.Usage(model, 2000, 6000))

    monkeypatch.setattr(solve_mod, "solve", fake_solve)
    sheet = filled_page(0)
    r = client.post("/solve", data={"homework": (png(sheet), "hw.jpg"), "api_key": "test", "paper": "letter",
                          "model": "claude-haiku-5-5"},
                    content_type="multipart/form-data", follow_redirects=True)
    assert b"Answered 1 question" in r.data, r.data[:2000]
    assert used["model"] == "claude-haiku-5-5"
    assert "¢".encode() in r.data
    assert b"G-code for the printer" in r.data
    gcode = client.get("/out/answers.gcode").data.decode()
    assert "G1 Z1.20" in gcode

    r = client.post("/results", data={"answer_0": "85", "x_0": "140", "y_0": "40", "w_0": "40", "h_0": "10",
                                      "size": "5", "seed": "1", "fit": "1"}, follow_redirects=True)
    assert b'value="85"' in r.data


def test_solve_without_handwriting_says_what_to_do(client):
    r = client.post("/solve", data={"api_key": "x"}, follow_redirects=True)
    assert b"Do step 1 first" in r.data


def test_unknown_files_are_not_served(client):
    assert client.get("/out/../hand.json").status_code == 404
    assert client.get("/hardware/pen_holder_99mm.stl").status_code == 404


def test_a_bad_sample_can_be_deleted_and_put_back(client):
    pages = [(png(photographed(filled_page(0))), "p0.jpg")]
    client.post("/learn", data={"scans": pages}, content_type="multipart/form-data")
    page = client.get("/").data
    assert b"Check each sample" in page and b'action="/samples/delete"' in page

    before = page.count(b'class="sitem"')
    r = client.post("/samples/delete", data={"ch": "a", "idx": "0"}, follow_redirects=True)
    assert b"Deleted one" in r.data
    assert r.data.count(b'class="sitem"') == before - 1
    assert b"Undo last delete" in r.data

    r = client.post("/samples/undo", follow_redirects=True)
    assert r.data.count(b'class="sitem"') == before


def test_deleting_a_sample_that_is_gone_is_harmless(client):
    pages = [(png(photographed(filled_page(0))), "p0.jpg")]
    client.post("/learn", data={"scans": pages}, content_type="multipart/form-data")
    r = client.post("/samples/delete", data={"ch": "a", "idx": "99"}, follow_redirects=True)
    assert b"already gone" in r.data


def test_answers_solved_elsewhere_can_be_imported(client, tmp_path):
    pages = [(png(photographed(filled_page(p))), f"p{p}.jpg") for p in range(template.core_page_count())]
    client.post("/learn", data={"scans": pages}, content_type="multipart/form-data")
    answers = [Answer("1", "12 x 7", "84", "write", (140.0, 40.0, 40.0, 10.0), "high", "line")]
    path = tmp_path / "answers.json"
    solve_mod.save(str(path), answers, "solved in chat")
    r = client.post("/import", data={"homework": (png(filled_page(0)), "hw.jpg"),
                                     "answers": (io.BytesIO(path.read_bytes()), "answers.json"), "paper": "letter"},
                    content_type="multipart/form-data", follow_redirects=True)
    assert b"Loaded 1 answer" in r.data
    assert b"solved in chat" in r.data
    assert client.get("/out/answers.gcode").status_code == 200


def test_a_broken_answers_file_is_refused(client):
    pages = [(png(photographed(filled_page(0))), "p0.jpg")]
    client.post("/learn", data={"scans": pages}, content_type="multipart/form-data")
    r = client.post("/import", data={"homework": (png(filled_page(0)), "hw.jpg"),
                                     "answers": (io.BytesIO(b'{"nope": 1}'), "answers.json")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert b"Couldn" in r.data


def test_a_dropped_folder_is_imported(client, tmp_path):
    pages = [(png(photographed(filled_page(p))), f"p{p}.jpg") for p in range(template.core_page_count())]
    client.post("/learn", data={"scans": pages}, content_type="multipart/form-data")
    path = tmp_path / "answers.json"
    solve_mod.save(str(path), [Answer("1", "q", "A", "write", (140.0, 40.0, 6.0, 4.4), "high", "line")], "")
    folder = [(png(filled_page(0)), "vocab1/photo.jpg"), (io.BytesIO(path.read_bytes()), "vocab1/answers.json"),
              (io.BytesIO(b"junk"), "vocab1/.DS_Store")]
    r = client.post("/import", data={"bundle": folder, "paper": "letter"},
                    content_type="multipart/form-data", follow_redirects=True)
    assert b"Loaded 1 answer" in r.data


def test_a_folder_with_two_sheets_in_it_is_explained(client, tmp_path):
    pages = [(png(photographed(filled_page(0))), "p0.jpg")]
    client.post("/learn", data={"scans": pages}, content_type="multipart/form-data")
    folder = [(png(filled_page(0)), "hw/a.jpg"), (png(filled_page(0)), "hw/b.jpg"),
              (io.BytesIO(b"{}"), "hw/answers.json")]
    r = client.post("/import", data={"bundle": folder}, content_type="multipart/form-data", follow_redirects=True)
    assert b"find a photo with its answers.json" in r.data


def _zip(entries):
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries:
            z.writestr(name, data)
    buf.seek(0)
    return buf


def test_a_zip_of_several_sheets_lists_them_to_write_one_at_a_time(client, tmp_path):
    pages = [(png(photographed(filled_page(p))), f"p{p}.jpg") for p in range(template.core_page_count())]
    client.post("/learn", data={"scans": pages}, content_type="multipart/form-data")
    path = tmp_path / "answers.json"
    solve_mod.save(str(path), [Answer("1", "q", "A", "write", (140.0, 40.0, 6.0, 4.4), "high", "line")], "")
    photo = png(filled_page(0)).getvalue()
    z = _zip([("Spanish homework/vocab1/photo.jpg", photo), ("Spanish homework/vocab1/answers.json", path.read_bytes()),
              ("Spanish homework/vocab2/photo.jpg", photo), ("Spanish homework/vocab2/answers.json", path.read_bytes()),
              ("__MACOSX/Spanish homework/._vocab1", b"junk")])
    r = client.post("/import", data={"bundle": [(z, "spanish_homework.zip")]},
                    content_type="multipart/form-data", follow_redirects=True)
    assert b"Found 2 sheets" in r.data
    assert b'action="/inbox/vocab1"' in r.data and b'action="/inbox/vocab2"' in r.data
    r = client.post("/inbox/vocab2", follow_redirects=True)
    assert b"Loaded 1 answer" in r.data
    r = client.post("/inbox-clear", follow_redirects=True)
    assert b"/inbox/vocab1" not in r.data


def test_a_zip_of_one_sheet_goes_straight_through(client, tmp_path):
    pages = [(png(photographed(filled_page(p))), f"p{p}.jpg") for p in range(template.core_page_count())]
    client.post("/learn", data={"scans": pages}, content_type="multipart/form-data")
    path = tmp_path / "answers.json"
    solve_mod.save(str(path), [Answer("1", "q", "A", "write", (140.0, 40.0, 6.0, 4.4), "high", "line")], "")
    z = _zip([("vocab1/photo.jpg", png(filled_page(0)).getvalue()), ("vocab1/answers.json", path.read_bytes())])
    r = client.post("/import", data={"homework": (z, "vocab1.zip")}, content_type="multipart/form-data",
                    follow_redirects=True)
    assert b"Loaded 1 answer" in r.data


def test_inbox_names_cannot_reach_outside_it(client):
    assert client.post("/inbox/..%2Fhand.json").status_code == 404


def test_paper_placement_is_described_in_words():
    from hwplot.web import describe_corner
    t = describe_corner(218.0, -33.0, True, 220, 220)
    assert t == "The page's top-left corner (its corner nearest you on the right) goes at the bed's right edge, hanging 3.3 cm off the front."
    t = describe_corner(80.3, 205.8, False, 220, 220)
    assert "8 cm in from the bed's left edge" in t and "1.4 cm in from the back edge" in t


def test_with_the_jig_the_page_says_slide_it_in_and_the_print_has_no_stops(client, tmp_path):
    pages = [(png(photographed(filled_page(p))), f"p{p}.jpg") for p in range(template.core_page_count())]
    client.post("/learn", data={"scans": pages}, content_type="multipart/form-data")
    from hwplot.gcode import Printer
    ws = tmp_path  # the client fixture's workspace is tmp_path
    Printer(pen_offset_x=77.9, pen_offset_y=-12.2, z_down=1.7, z_up=4.7, jig=True).save(str(ws / "printer.json"))
    path = tmp_path / "answers.json"
    solve_mod.save(str(path), [Answer("1", "q", "A", "write", (60.0, 100.0, 6.0, 4.4), "high", "line")], "")
    r = client.post("/import", data={"homework": (png(filled_page(0)), "hw.jpg"),
                                     "answers": (io.BytesIO(path.read_bytes()), "answers.json")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert b"Slide the sheet into the jig" in r.data
    assert "M0" not in client.get("/out/answers.gcode").data.decode()
