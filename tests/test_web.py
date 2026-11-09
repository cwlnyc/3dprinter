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

    pages = [(png(photographed(filled_page(p))), f"p{p}.jpg") for p in range(template.page_count())]
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
