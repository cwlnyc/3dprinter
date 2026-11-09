"""The connector's tools, called the way Claude calls them, with a fake printer on the end of the USB cable."""
import json
import shutil
import threading
import time

import anyio
import cv2
import pytest

from hwplot import connector, template
from hwplot.gcode import Printer
from hwplot.glyphs import learn
from hwplot.usbprint import Sender, commands, framed

from test_blanks import sheet as blank_sheet
from test_pipeline import filled_page, photographed


class FakeMarlin:
    """Answers like Marlin: 'start' on connect, then 'ok' per line, one checksum failure along the way."""

    def __init__(self):
        self.out = [b"start\n"]
        self.received = []
        self.lock = threading.Lock()
        self.failed_once = False

    def readline(self):
        for _ in range(50):
            with self.lock:
                if self.out:
                    return self.out.pop(0)
            time.sleep(0.002)
        return b""

    def write(self, data):
        line = data.decode().strip()
        with self.lock:
            n = int(line.split()[0][1:])
            if n == 3 and not self.failed_once:
                self.failed_once = True
                self.out += [b"Error:checksum mismatch, Last Line: 2\n", b"Resend: 3\n", b"ok\n"]
                return
            self.received.append(line)
            self.out.append(b"ok\n")

    def reset_input_buffer(self):
        pass

    def close(self):
        pass


def call(server, name, **args):
    async def go():
        return await server.call_tool(name, args)
    return anyio.run(go)


def text_of(result):
    return "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")


def images_in(result):
    return [c for c in result.content if getattr(c, "type", "") == "image"]


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "ws"
    (ws / "photos").mkdir(parents=True)
    hand, _, _ = learn([photographed(filled_page(p)) for p in range(template.page_count())])
    hand.save(str(ws / "hand.json"))
    Printer(pen_offset_x=77.9, pen_offset_y=-12.2, z_down=1.7, z_up=4.7, jig=True).save(str(ws / "printer.json"))
    cv2.imwrite(str(ws / "photos" / "hw.jpg"), photographed(blank_sheet()))
    return ws


def test_a_sheet_goes_from_photo_to_printer(workspace, monkeypatch):
    fake = FakeMarlin()
    monkeypatch.setattr("hwplot.connector.find_port", lambda preferred="": "/dev/fake")
    monkeypatch.setattr("hwplot.usbprint.find_port", lambda preferred="": "/dev/fake")
    sender = Sender(open_serial=lambda port: fake)
    server = connector.create_server(workspace, sender=sender)

    r = call(server, "get_sheet")
    assert "hw.jpg" in text_of(r) and images_in(r)
    r = call(server, "find_blanks")
    rows = [l for l in text_of(r).splitlines() if " line " in l or " box " in l]
    box_no = next(int(l.split()[0]) for l in rows if " box " in l)  # the answer box, inside the jig's reach
    assert images_in(r)

    r = call(server, "preview_answers", answers=[{"blank": box_no, "text": "7", "label": "2"}])
    assert text_of(r).startswith("Ready"), text_of(r)
    assert "jig" in text_of(r) and images_in(r)

    assert "Started" in text_of(call(server, "start_print"))
    for _ in range(500):
        if sender.job.state in ("done", "error"):
            break
        time.sleep(0.01)
    assert sender.job.state == "done", sender.job.summary()
    assert fake.failed_once  # the garbled line was sent again
    numbers = [int(l.split()[0][1:]) for l in fake.received]
    assert numbers == sorted(numbers) and len(numbers) == len(set(numbers))  # in step: none skipped or doubled
    sent = [l.split(" ", 1)[1].rsplit("*", 1)[0] for l in fake.received]
    assert sent[0] == "M110 N0" and "G28" in sent
    assert not any(c.startswith("M0") for c in sent)  # in the jig: no alignment stops
    assert "Done" in text_of(call(server, "printer_status"))


def test_answers_out_of_the_jigs_reach_are_refused_not_printed(workspace):
    server = connector.create_server(workspace, sender=Sender(open_serial=lambda port: FakeMarlin()))
    call(server, "get_sheet")
    r = call(server, "preview_answers", answers=[{"text": "x", "x": 190.0, "y": 20.0, "w": 15.0, "h": 8.0}])
    assert text_of(r).startswith("NOT ready") and "Out of reach in the jig" in text_of(r)
    assert "Nothing to print" in text_of(call(server, "start_print"))


def test_without_usb_the_file_is_saved_for_the_sd_card(workspace, monkeypatch):
    monkeypatch.setattr("hwplot.connector.find_port", lambda preferred="": None)
    server = connector.create_server(workspace)
    call(server, "get_sheet")
    call(server, "find_blanks")
    r = call(server, "preview_answers", answers=[{"text": "7", "x": 60.0, "y": 100.0, "w": 20.0, "h": 8.0}])
    assert "No printer on USB" in text_of(r)
    assert "SD card" in text_of(call(server, "start_print"))
    assert (workspace / "out" / "answers.gcode").exists()


def test_jig_calibration_moves_the_jig_and_turns_it_on(workspace):
    server = connector.create_server(workspace, sender=Sender(open_serial=lambda port: FakeMarlin()))
    # Crosses landed 3 mm further from the left edge and 2 mm further from the top than intended.
    r = call(server, "jig_calibrate", cross1_from_left=43, cross1_from_top=82, cross2_from_left=123, cross2_from_top=192)
    p = Printer.load(str(workspace / "printer.json"))
    assert p.jig and p.jig_x == 231.0 and p.jig_y == -47.0
    assert "Jig set" in text_of(r)


def test_a_missing_photo_is_explained(tmp_path):
    server = connector.create_server(tmp_path / "ws")
    assert "No photo found" in text_of(call(server, "get_sheet"))


def test_the_secret_is_made_once_and_kept(tmp_path):
    a = connector.secret(tmp_path)
    assert len(a) >= 30 and connector.secret(tmp_path) == a


def test_lines_are_framed_the_way_marlin_checks_them():
    assert framed(1, "G28") == "N1 G28*18"
    assert commands("; header\nG28 ; home\n\nG1 X1\n") == ["G28", "G1 X1"]


def test_the_tunnel_address_is_read_from_cloudflared(tmp_path):
    fake = tmp_path / "cloudflared"
    fake.write_text("#!/bin/sh\necho 'INF Requesting new quick Tunnel...' >&2\n"
                    "echo '|  https://brave-lion-example.trycloudflare.com  |' >&2\nsleep 30\n")
    fake.chmod(0o755)
    proc, url = connector.start_tunnel(8765, str(fake), timeout=10)
    proc.terminate()
    assert url == "https://brave-lion-example.trycloudflare.com"


def test_the_mac_registers_its_tunnel_with_the_front_door():
    import http.server
    got = {}

    class FrontDoor(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            got["path"] = self.path
            got["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, *a):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), FrontDoor)
    threading.Thread(target=httpd.handle_request, daemon=True).start()
    connector.register(f"http://127.0.0.1:{httpd.server_port}", "s3cret", "https://x.trycloudflare.com")
    assert got == {"path": "/s3cret/register", "body": {"origin": "https://x.trycloudflare.com"}}


def test_the_secret_comes_with_a_name_for_the_front_door(tmp_path):
    connector.secret(tmp_path)
    data = json.loads((tmp_path / "connector.json").read_text())
    assert data["relay_project"].startswith("hwplot-")
