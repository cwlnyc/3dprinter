"""A local web page that walks through the whole job: python -m hwplot serve

Everything it makes is kept in ./workspace, so closing the browser or
restarting the server loses nothing. It listens on 127.0.0.1 only: the page can
spend your API key, so it should not be reachable from the rest of the network.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
import threading
import webbrowser
from dataclasses import asdict, fields
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for

from . import page, render, solve, template
from .gcode import OutOfReach, Printer, fit_paper, generate, test_pattern
from .glyphs import Hand, learn

ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
PEN_SIZES = {"8": "Pencil (8 mm, hex or round)", "10": "Most ballpoint / gel pens (10 mm)", "12": "Markers, chunky pens (12 mm)"}


def create_app(workspace: str | os.PathLike = "workspace") -> Flask:
    ws = Path(workspace).resolve()
    out = ws / "out"
    out.mkdir(parents=True, exist_ok=True)
    app = Flask(__name__)
    app.secret_key = os.urandom(16)
    app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024
    state = {"api_key": os.environ.get("ANTHROPIC_API_KEY", ""), "paper": "letter"}

    hand_path, printer_path, answers_path = ws / "hand.json", ws / "printer.json", out / "answers.json"

    def load_hand() -> Hand | None:
        return Hand.load(str(hand_path)) if hand_path.exists() else None

    def load_printer() -> Printer:
        return Printer.load(str(printer_path)) if printer_path.exists() else Printer()

    def page_mm():
        return page.A4_MM if state["paper"] == "a4" else page.LETTER_MM

    def read_upload(f) -> np.ndarray:
        img = cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"{f.filename}: not an image I can read (use JPG or PNG)")
        return img

    def rerender(fit: bool, size: float, seed: int) -> list[str]:
        """Draw answers.json in the learned hand. Returns messages for the page."""
        msgs = []
        hand = load_hand()
        flat = cv2.imread(str(out / "page.png"))
        answers, _ = solve.load(str(answers_path))
        missing = set().union(set(), *(hand.missing(a.answer) for a in answers if a.kind == "write"))
        if missing:
            msgs.append("No handwriting sample for " + " ".join(sorted(missing)) + " - those characters are left out.")
        strokes = render.render_answers(answers, hand, flat, seed=seed, cap_mm=size)
        cv2.imwrite(str(out / "preview.png"), render.overlay(flat, strokes))
        (out / "answers.svg").write_text(render.svg(strokes, page_mm()))
        p = load_printer()
        if fit:
            p = fit_paper(strokes, p)
        try:
            (out / "answers.gcode").write_text(generate(strokes, p))
            (out / "placement.txt").write_text(f"{p.paper_x} {p.paper_y}")
        except OutOfReach as e:
            (out / "answers.gcode").unlink(missing_ok=True)
            msgs.append(f"G-code not made: {e}")
        return msgs

    @app.get("/")
    def index():
        hand = load_hand()
        placement = (out / "placement.txt").read_text().split() if (out / "placement.txt").exists() else None
        return render_template(
            "index.html",
            hand=hand,
            samples=sum(len(v) for v in hand.glyphs.values()) if hand else 0,
            blank=sorted(set(template.CHARSET) - set(hand.glyphs)) if hand else [],
            pages=template.page_count(),
            printer=load_printer(),
            printer_saved=printer_path.exists(),
            printer_fields=[f.name for f in fields(Printer)],
            has_key=bool(state["api_key"]),
            paper=state["paper"],
            has_results=answers_path.exists(),
            has_gcode=(out / "answers.gcode").exists(),
            placement=placement,
            pen_sizes=PEN_SIZES,
            openscad=bool(shutil.which("openscad")),
        )

    @app.get("/template.pdf")
    def template_pdf():
        path = ws / "handwriting-template.pdf"
        if not path.exists():
            template.write_template(str(path))
        return send_file(path, as_attachment=True)

    @app.post("/learn")
    def do_learn():
        files = [f for f in request.files.getlist("scans") if f.filename]
        if not files:
            flash("Choose the photos of your filled-in sample pages first.", "error")
            return redirect(url_for("index") + "#step1")
        try:
            hand, warnings = learn([read_upload(f) for f in files])
        except ValueError as e:
            flash(f"Couldn't read that: {e}", "error")
            return redirect(url_for("index") + "#step1")
        hand.save(str(hand_path))
        flash(f"Learned {len(hand.glyphs)} characters from {len(files)} photo(s). Check them below.", "ok")
        for w in warnings:
            flash(w, "warn")
        return redirect(url_for("index") + "#step1")

    @app.get("/specimen.png")
    def specimen():
        hand = load_hand() or abort(404)
        ok, buf = cv2.imencode(".png", render.specimen(hand, template.CHARSET))
        return send_file(io.BytesIO(buf.tobytes()), mimetype="image/png")

    @app.get("/hardware/pen_holder_<size>mm.stl")
    def stl(size):
        if size not in PEN_SIZES:
            abort(404)
        return send_file(HARDWARE / "stl" / f"pen_holder_{size}mm.stl", as_attachment=True)

    @app.post("/hardware/custom.stl")
    def custom_stl():
        if not shutil.which("openscad"):
            abort(400)
        try:
            d = float(request.form["pen_d"])
        except (KeyError, ValueError):
            abort(400)
        if not 4 <= d <= 25:
            flash("Pen diameter should be between 4 and 25 mm.", "error")
            return redirect(url_for("index") + "#step2")
        tmp = Path(tempfile.mkdtemp()) / f"pen_holder_{d:g}mm.stl"
        subprocess.run(["openscad", "-D", f"pen_d={d}", "-o", str(tmp), str(HARDWARE / "pen_holder.scad")],
                       check=True, capture_output=True, timeout=300)
        return send_file(tmp, as_attachment=True)

    @app.get("/hardware/<name>")
    def hardware_file(name):
        if name not in ("pen_holder.png", "pen_holder.scad"):
            abort(404)
        return send_file(HARDWARE / name, as_attachment=name.endswith(".scad"))

    @app.post("/printer")
    def save_printer():
        p = load_printer()
        values = asdict(p)
        for f in fields(Printer):
            raw = request.form.get(f.name)
            if raw is None:
                continue
            try:
                values[f.name] = raw.replace("\r\n", "\n") if f.type == "str" else type(values[f.name])(float(raw))
            except ValueError:
                flash(f"{f.name}: '{raw}' is not a number", "error")
                return redirect(url_for("index") + "#step3")
        Printer(**values).save(str(printer_path))
        flash("Printer settings saved.", "ok")
        return redirect(url_for("index") + "#step3")

    @app.get("/test-pattern.gcode")
    def test_gcode():
        return send_file(io.BytesIO(test_pattern(load_printer()).encode()), as_attachment=True,
                         download_name="test-pattern.gcode", mimetype="text/plain")

    @app.post("/solve")
    def do_solve():
        if request.form.get("api_key"):
            state["api_key"] = request.form["api_key"].strip()
        state["paper"] = request.form.get("paper", "letter")
        hand = load_hand()
        f = request.files.get("homework")
        if hand is None:
            flash("Do step 1 first: I need your handwriting before I can write answers.", "error")
        elif not state["api_key"]:
            flash("Paste an Anthropic API key so the questions can be solved.", "error")
        elif not f or not f.filename:
            flash("Choose a photo of the homework sheet.", "error")
        else:
            try:
                flat = page.flatten(read_upload(f), page_mm())
                cv2.imwrite(str(out / "page.png"), flat)
                import anthropic
                answers, notes = solve.solve(flat, "".join(sorted(hand.glyphs)), anthropic.Anthropic(api_key=state["api_key"]))
                solve.save(str(answers_path), answers, notes)
                for m in rerender(fit=True, size=5.0, seed=0):
                    flash(m, "warn")
                flash(f"Answered {len(answers)} question(s). Check every one before printing.", "ok")
                return redirect(url_for("results"))
            except Exception as e:  # shown to the one local user, who needs the reason
                flash(f"Solving failed: {e}", "error")
        return redirect(url_for("index") + "#step4")

    @app.get("/results")
    def results():
        if not answers_path.exists():
            return redirect(url_for("index"))
        answers, notes = solve.load(str(answers_path))
        placement = (out / "placement.txt").read_text().split() if (out / "placement.txt").exists() else None
        return render_template("results.html", answers=answers, notes=notes, placement=placement,
                               has_gcode=(out / "answers.gcode").exists(), v=int((out / "preview.png").stat().st_mtime))

    @app.post("/results")
    def edit_results():
        answers, notes = solve.load(str(answers_path))
        kept = []
        for i, a in enumerate(answers):
            if request.form.get(f"delete_{i}"):
                continue
            a.answer = request.form.get(f"answer_{i}", a.answer)
            try:
                a.box = tuple(float(request.form.get(f"{k}_{i}", v)) for k, v in zip("xywh", a.box))
            except ValueError:
                flash(f"Question {a.id}: position must be numbers", "error")
            kept.append(a)
        solve.save(str(answers_path), kept, notes)
        try:
            size, seed = float(request.form.get("size", 5)), int(request.form.get("seed", 0))
        except ValueError:
            size, seed = 5.0, 0
        for m in rerender(fit=bool(request.form.get("fit")), size=size, seed=seed):
            flash(m, "warn")
        flash("Redrawn.", "ok")
        return redirect(url_for("results"))

    @app.get("/out/<name>")
    def out_file(name):
        if name not in ("preview.png", "answers.svg", "answers.gcode", "answers.json", "page.png"):
            abort(404)
        path = out / name
        if not path.exists():
            abort(404)
        return send_file(path, as_attachment=request.args.get("download") == "1", max_age=0)

    return app


def serve(port: int = 8000, workspace: str = "workspace", open_browser: bool = True) -> None:
    app = create_app(workspace)
    url = f"http://localhost:{port}"
    print(f"homework-plotter running at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False)
