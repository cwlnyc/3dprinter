"""A Claude connector for the plotter: python3 -m hwplot mcp

Claude, in any chat (phone included), gets the sheet's photo from this Mac,
reads and solves it, says which answer goes in which blank, and prints. No API
key is involved: the solving happens in the chat, on the user's Claude plan.
This server only does what needs the Mac: the photo, the blanks, the
handwriting and the printer.

It is reached through a tunnel (Cloudflare or similar) at a URL with a long
random secret in the path. That secret is the only thing standing between the
internet and the printer, so it lives in workspace/connector.json and is never
printed anywhere but the terminal that starts the server.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from pydantic import BaseModel, Field

from . import blanks, page, render
from .gcode import OutOfReach, Printer, generate, jig_reach, jig_test, place
from .gcode import jig_calibrate as calibrate
from .glyphs import Hand
from .solve import Answer
from .usbprint import Sender, find_port

PHOTO_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic")
INSTRUCTIONS = """Writes homework answers on paper in the user's own handwriting, with a pen on their 3D printer.

To do a sheet: get_sheet (the newest photo the user saved) -> read and solve every
question yourself -> find_blanks -> preview_answers with each answer on its
numbered blank -> show the user the preview and anything flagged -> start_print
only once they have seen it -> printer_status to follow it.

Answers must be correct and short, as a student would write them. Use zoom when
text is small. For multiple choice, circle the option (kind="circle", blank=None,
box around the printed option). Use only characters the user's handwriting has."""


class AnswerIn(BaseModel):
    text: str = Field(description="Exactly what to write, e.g. 'G' or 'x = 5'")
    blank: int | None = Field(None, description="Number from find_blanks to write on; omit to give a box instead")
    kind: str = Field("write", description="'write', or 'circle' to circle a printed option")
    x: float | None = Field(None, description="Box left, mm from the page's left edge (when not using a blank)")
    y: float | None = Field(None, description="Box top, mm from the page's top edge")
    w: float | None = Field(None, description="Box width, mm")
    h: float | None = Field(None, description="Box height, mm")
    label: str = Field("", description="Question number as printed, for the user's reference")


@dataclass
class Sheet:
    photo: Path
    original: np.ndarray
    flat: np.ndarray
    blanks: list[blanks.Blank] | None = None


def _jpeg(img: np.ndarray, quality: int = 85) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("could not encode image")
    return buf.tobytes()


def line_room(b: blanks.Blank, all_blanks: list[blanks.Blank]) -> float:
    """How tall an answer on this line can be without running into the line above."""
    above = [o.y for o in all_blanks if o.kind == "line" and o is not b and o.y < b.y - 0.5
             and o.x < b.x + b.w and b.x < o.x + o.w]
    gap = b.y - max(above) if above else 12.0
    return max(4.0, min(12.0, gap - 0.8))


def answers_from(items: list[AnswerIn], sheet: Sheet) -> tuple[list[Answer], list[str]]:
    found = sheet.blanks or []
    out, problems = [], []
    for i, a in enumerate(items, 1):
        name = a.label or str(a.blank or i)
        if a.blank is not None:
            if not 1 <= a.blank <= len(found):
                problems.append(f"{name}: there is no blank {a.blank} (find_blanks found {len(found)})")
                continue
            b = found[a.blank - 1]
            if b.kind == "line":
                room = line_room(b, found)
                box, target = (b.x + 1.0, b.y - room, max(b.w - 2.0, 1.0), room), "line"
            else:
                box, target = (b.x + 1.5, b.y + 1.5, max(b.w - 3.0, 1.0), max(b.h - 3.0, 1.0)), "box"
        elif None not in (a.x, a.y, a.w, a.h):
            box, target = (a.x, a.y, a.w, a.h), "none"
        else:
            problems.append(f"{name}: give either a blank number or x, y, w and h")
            continue
        kind = "circle" if a.kind == "circle" else "write"
        out.append(Answer(name, "", a.text, kind, box, "high", target))
    return out, problems


def create_server(workspace: str | os.PathLike = "workspace", photos: str | os.PathLike = "",
                  serial_port: str = "", sender: Sender | None = None):
    from mcp.server.mcpserver import Image, MCPServer

    ws = Path(workspace).resolve()
    out = ws / "out"
    out.mkdir(parents=True, exist_ok=True)
    photo_dir = Path(photos).expanduser() if photos else ws / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    sender = sender or Sender(serial_port)
    state: dict = {"sheet": None, "job": None}

    def hand() -> Hand:
        path = ws / "hand.json"
        if not path.exists():
            raise ValueError("No handwriting learned yet: do step 1 on the web page (python3 -m hwplot serve) first.")
        return Hand.load(str(path))

    def printer() -> Printer:
        path = ws / "printer.json"
        return Printer.load(str(path)) if path.exists() else Printer()

    def sheet() -> Sheet:
        if state["sheet"] is None:
            raise ValueError("No sheet loaded: call get_sheet first.")
        return state["sheet"]

    server = MCPServer("hwplot", instructions=INSTRUCTIONS)

    @server.tool()
    def get_sheet(filename: str = "") -> list:
        """Load the newest homework photo the user saved (or the named one) and show it, flattened to the page.

        Coordinates used by every other tool are millimetres on this flattened page,
        from its top-left corner.
        """
        photos_found = sorted((p for p in photo_dir.iterdir() if p.suffix.lower() in PHOTO_EXT),
                              key=lambda p: p.stat().st_mtime, reverse=True) if photo_dir.exists() else []
        if filename:
            photos_found = [p for p in photos_found if p.name == filename]
        if not photos_found:
            return [f"No photo found in {photo_dir}. Ask the user to save the homework photo there."]
        path = photos_found[0]
        img = cv2.imread(str(path))
        if img is None:
            return [f"{path.name} isn't an image this can read (HEIC: set the iPhone camera to 'Most Compatible', "
                    "or share it as JPEG)."]
        flat = page.flatten(img)
        state["sheet"] = Sheet(path, img, flat)
        cv2.imwrite(str(out / "page.png"), flat)
        age = (time.time() - path.stat().st_mtime) / 60
        return [f"{path.name}, saved {age:.0f} min ago. Page is {page.LETTER_MM[0]} x {page.LETTER_MM[1]} mm. "
                "Use zoom for small print.", Image(data=_jpeg(flat), format="jpeg")]

    @server.tool()
    def zoom(x: float, y: float, w: float, h: float) -> list:
        """A sharper close-up of part of the sheet (mm on the page), for reading small text."""
        s = sheet()
        scale = 16.0
        big = page.flatten(s.original, scale=scale)
        x0, y0 = max(0, int(x * scale)), max(0, int(y * scale))
        crop = big[y0:int((y + h) * scale), x0:int((x + w) * scale)]
        if crop.size == 0:
            return ["That area is off the page."]
        return [Image(data=_jpeg(crop, 90), format="jpeg")]

    @server.tool()
    def find_blanks() -> list:
        """Number every answer line and empty answer box on the sheet, with a marked-up image."""
        s = sheet()
        s.blanks = blanks.find_blanks(s.flat)
        marked = s.flat.copy()
        rows = []
        for i, b in enumerate(s.blanks, 1):
            x, y, w, h = (round(v * page.PX_PER_MM) for v in (b.x, b.y, b.w, b.h))
            colour = (40, 140, 40) if b.kind == "line" else (200, 90, 20)
            if b.kind == "line":
                cv2.line(marked, (x, y), (x + w, y), colour, 3)
            else:
                cv2.rectangle(marked, (x, y), (x + w, y + h), colour, 3)
            cv2.putText(marked, str(i), (x, max(12, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)
            rows.append(f"{i} {b.kind} x={b.x:.1f} y={b.y:.1f} w={b.w:.1f}" + (f" h={b.h:.1f}" if b.h else ""))
        note = ("Numbered in no particular reading order: match each to its question by position. "
                "Short lines right after a question number are usually its blank; marks on hole punches, titles "
                "and Name/Date lines are not answers.")
        return [note + "\n" + "\n".join(rows), Image(data=_jpeg(marked), format="jpeg")]

    @server.tool()
    def preview_answers(answers: list[AnswerIn], letter_height_mm: float = 5.0) -> list:
        """Draw the answers in the user's handwriting on the sheet and prepare the print. Nothing prints yet.

        Shows the result. Check it, show it to the user, then call start_print.
        """
        s = sheet()
        if s.blanks is None:
            s.blanks = blanks.find_blanks(s.flat)
        items, problems = answers_from(answers, s)
        h = hand()
        missing = set().union(set(), *(h.missing(a.answer) for a in items if a.kind == "write"))
        strokes = render.render_answers(items, h, s.flat, cap_mm=letter_height_mm)
        preview = render.overlay(s.flat, strokes)
        cv2.imwrite(str(out / "preview.png"), preview)
        p, align = place(strokes, printer())
        notes = list(problems)
        if missing:
            notes.append("No handwriting sample for " + " ".join(sorted(missing)) + ": those characters are left out.")
        try:
            gcode = generate(strokes, p, align=align, marks=render.alignment_marks(items))
        except OutOfReach as e:
            state["job"] = None
            if p.jig:
                (xa, xb), (ya, yb) = jig_reach(p)
                notes.append(f"Out of reach in the jig: the pen can only write between {xa:.0f} and {xb:.0f} mm "
                             f"from the left edge and {ya:.0f} to {yb:.0f} mm from the top. ({e})")
            else:
                notes.append(str(e))
            return ["NOT ready to print.\n" + "\n".join(notes), Image(data=_jpeg(preview), format="jpeg")]
        (out / "answers.gcode").write_text(gcode)
        state["job"] = gcode
        where = ("Sheet goes in the jig." if p.jig else
                 f"No jig: the sheet goes {'turned round (title to the front)' if p.paper_flipped else 'title to the back'}, "
                 "and the printer will stop to line it up.")
        port = find_port(sender.port)
        how = f"Printer found on USB ({port})." if port else \
              f"No printer on USB: start_print will save the file for the SD card instead ({out / 'answers.gcode'})."
        return [f"Ready: {len(items)} answers. {where} {how}" + ("\n" + "\n".join(notes) if notes else ""),
                Image(data=_jpeg(preview), format="jpeg")]

    @server.tool()
    def start_print() -> str:
        """Print the answers from the last preview. Only after the user has seen the preview."""
        if not state["job"]:
            return "Nothing to print: call preview_answers first (and fix anything it flagged)."
        if not find_port(sender.port):
            return (f"No printer on USB. The G-code is saved at {out / 'answers.gcode'}: "
                    "copy it to the SD card and print it from the printer's menu.")
        return sender.start(state["job"]) + " Use printer_status to follow it."

    @server.tool()
    def printer_status() -> str:
        """What the printer is doing: idle, printing (with progress), done, or the error."""
        job = sender.job
        tail = ("\nLast from printer: " + " | ".join(job.log[-3:])) if job.log else ""
        return job.summary() + tail

    @server.tool()
    def cancel_print() -> str:
        """Stop the current print and lift the pen."""
        if not sender.busy:
            return "Nothing is printing."
        sender.cancel()
        return "Stopping: the pen lifts and the printer halts."

    @server.tool()
    def jig_test_print() -> str:
        """One-time jig setup, step 1: print two small crosses on a sheet in the jig.

        Then ask the user to measure each cross's centre: mm from the page's left
        edge and from its top edge (with the sheet the right way up), and pass
        those to jig_calibrate.
        """
        if not find_port(sender.port):
            path = out / "jig-test.gcode"
            path.write_text(jig_test(printer()))
            return f"No printer on USB: saved {path} for the SD card."
        return sender.start(jig_test(printer()))

    @server.tool()
    def jig_calibrate(cross1_from_left: float, cross1_from_top: float,
                      cross2_from_left: float, cross2_from_top: float) -> str:
        """One-time jig setup, step 2: correct the jig position from the measured crosses, and turn the jig on."""
        p = calibrate(printer(), [(cross1_from_left, cross1_from_top), (cross2_from_left, cross2_from_top)])
        p.jig = True
        p.save(str(ws / "printer.json"))
        (xa, xb), (ya, yb) = jig_reach(p)
        return (f"Jig set (corner at X{p.jig_x}, Y{p.jig_y}) and turned on. In the jig the pen reaches "
                f"{xa:.0f}-{xb:.0f} mm from the page's left edge and {ya:.0f}-{yb:.0f} mm from its top.")

    return server


def _config(workspace: str | os.PathLike) -> tuple[Path, dict]:
    path = Path(workspace) / "connector.json"
    return path, (json.loads(path.read_text()) if path.exists() else {})


def _save_config(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    os.chmod(path, 0o600)


def secret(workspace: str | os.PathLike) -> str:
    """The URL secret, made once and kept, so the connector's address stays the same."""
    path, data = _config(workspace)
    if not data.get("secret") or not data.get("relay_project"):
        # Settings saved before the .pages.dev front door existed have a secret but
        # no site name: keep the secret (the connector URL stays the same), add the name.
        data.setdefault("secret", secrets.token_urlsafe(24))
        data.setdefault("relay_project", "hwplot-" + secrets.token_hex(3))
        _save_config(path, data)
    return data["secret"]


TUNNEL_URL = __import__("re").compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def find_cloudflared() -> str | None:
    import shutil
    for candidate in (shutil.which("cloudflared"), Path.home() / "cloudflared", Path.cwd() / "cloudflared"):
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def start_tunnel(port: int, binary: str, timeout: float = 60.0):
    """Start a Cloudflare quick tunnel to localhost:port and return (process, its https address)."""
    import subprocess
    import threading

    proc = subprocess.Popen([binary, "tunnel", "--no-autoupdate", "--url", f"http://localhost:{port}"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    found: dict = {}
    ready = threading.Event()

    def watch():
        for line in proc.stderr:  # keep reading for its whole life, or the pipe fills and it stalls
            m = TUNNEL_URL.search(line)
            if m and not found:
                found["url"] = m.group(0)
                ready.set()
        ready.set()

    threading.Thread(target=watch, daemon=True).start()
    ready.wait(timeout)
    if "url" not in found:
        proc.terminate()
        raise RuntimeError("cloudflared didn't report a tunnel address; run it by hand to see why")
    return proc, found["url"]


def register(relay: str, key: str, origin: str, tries: int = 6) -> None:
    """Tell the .pages.dev front door where the Mac is now."""
    import ssl
    import urllib.request

    # Python from python.org on a Mac ships without the system's trusted
    # certificates, so every HTTPS request fails verification. certifi's bundle
    # is the usual fix; verification stays on.
    try:
        import certifi
        tls = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        tls = ssl.create_default_context()
    body = json.dumps({"origin": origin}).encode()
    last = None
    for attempt in range(tries):
        try:
            # Cloudflare refuses Python's default "Python-urllib" label outright (error 1010).
            req = urllib.request.Request(f"{relay.rstrip('/')}/{key}/register", data=body, method="POST",
                                         headers={"Content-Type": "application/json",
                                                  "User-Agent": "hwplot-connector/1.0"})
            with urllib.request.urlopen(req, timeout=15, context=tls) as r:
                if r.status == 200:
                    return
        except Exception as e:  # network hiccups while the tunnel settles: retry
            last = e
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"couldn't register with {relay}: {last}")


def run(workspace: str = "workspace", photos: str = "", port: int = 8765, serial_port: str = "",
        relay: str = "") -> None:
    import threading

    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings

    key = secret(workspace)
    path, data = _config(workspace)
    relay = relay or data.get("relay", "")
    if relay and data.get("relay") != relay:
        data["relay"] = relay
        _save_config(path, data)

    server = create_server(workspace, photos, serial_port)
    # The tunnel delivers requests with its own hostname, which the default
    # localhost-only check would refuse. The secret path does that job instead.
    app = server.streamable_http_app(
        streamable_http_path=f"/{key}/mcp",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    app = _logged(app, key)

    tunnel = None
    if relay:
        binary = find_cloudflared()
        if not binary:
            raise SystemExit("cloudflared not found: put it in your home folder or on your PATH (see the README).")
        tunnel, origin = start_tunnel(port, binary)

        data["tunnel"] = origin  # for `hwplot check`
        _save_config(path, data)

        def announce():
            try:
                register(relay, key, origin)
                print(f"Connected. Connector URL (the same every time): {relay.rstrip('/')}/{key}/mcp")
                print("Keep it private: anyone with it can print on your printer. Leave this window open.")
            except RuntimeError as e:
                print(f"Tunnel is up at {origin}, but {e}")

        threading.Thread(target=announce, daemon=True).start()
    else:
        print(f"hwplot connector on http://localhost:{port}")
        print(f"Connector URL (after starting a tunnel): https://<your tunnel address>/{key}/mcp")
        print("Keep that URL private: anyone with it can print on your printer.")
    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    finally:
        if tunnel:
            tunnel.terminate()


def _logged(app, key: str):
    """Print one line per request (method, path, status, client), with the secret blanked.

    When Claude can't connect, this shows whether its requests reach the Mac at all,
    and what the connector answered.
    """
    import datetime

    async def wrapper(scope, receive, send):
        if scope.get("type") != "http":
            return await app(scope, receive, send)
        headers = {k.decode().lower(): v.decode(errors="replace") for k, v in scope.get("headers", [])}
        rpc = {"name": ""}

        async def receive_logged():
            message = await receive()
            if message.get("type") == "http.request" and not rpc["name"]:
                try:
                    body = json.loads(message.get("body") or b"{}")
                    rpc["name"] = body.get("method", "") if isinstance(body, dict) else "batch"
                except ValueError:
                    pass
            return message

        async def send_logged(message):
            if message.get("type") == "http.response.start":
                when = datetime.datetime.now().strftime("%H:%M:%S")
                path = scope.get("path", "").replace(key, "<secret>")
                agent = headers.get("user-agent", "-")[:40]
                print(f"{when} {scope.get('method')} {path} {rpc['name']} -> {message.get('status')}  ({agent})",
                      flush=True)
            await send(message)

        return await app(scope, receive_logged, send_logged)

    return wrapper


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "hwplot-check", "version": "1"}}}


def _probe(url: str) -> tuple[bool, str]:
    """Try opening an MCP session at url, as Claude does. (ok, what happened)."""
    import ssl
    import urllib.error
    import urllib.request

    try:
        import certifi
        tls = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        tls = ssl.create_default_context()
    req = urllib.request.Request(url, data=json.dumps(INIT).encode(), method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
        "User-Agent": "hwplot-check/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20, context=tls) as r:
            body = r.read(4000).decode(errors="replace")
            return ("serverInfo" in body, f"HTTP {r.status}" + ("" if "serverInfo" in body else f": {body[:120]!r}"))
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read(200).decode(errors='replace')!r}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def check(workspace: str = "workspace", port: int = 8765) -> int:
    """Test each link between Claude and this Mac, without printing the secret."""
    key = secret(workspace)
    _, data = _config(workspace)
    links = [("This Mac (the connector itself)", f"http://127.0.0.1:{port}/{key}/mcp")]
    if data.get("tunnel"):
        links.append(("The tunnel (" + data["tunnel"] + ")", f"{data['tunnel']}/{key}/mcp"))
    if data.get("relay"):
        links.append(("The front door (" + data["relay"] + ")", f"{data['relay'].rstrip('/')}/{key}/mcp"))
    failed = 0
    for name, url in links:
        ok, what = _probe(url)
        print(f"{'OK  ' if ok else 'FAIL'} {name}: {what}")
        failed += not ok
    if not failed:
        print("Every link works. In Claude, check the connector URL is exactly the one the connector printed.")
    return 1 if failed else 0
