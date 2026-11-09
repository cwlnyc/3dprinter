"""Command line: python -m hwplot <command>.

  template  print this, write one character per box
  learn     scan the filled-in sample sheets -> hand.json
  solve     scan a homework sheet -> answers.json (+ the flattened page)
  render    answers.json + hand.json -> preview PNG, SVG and G-code
  run       solve + render in one go
  serve     the same steps as a web page on http://localhost:8000
  blanks    flatten a homework photo and list its answer lines and boxes, numbered
"""
from __future__ import annotations

import argparse
import os
import sys

import cv2

from . import blanks, page, render, solve, template
from .gcode import OutOfReach, Printer, fit_paper, generate
from .glyphs import Hand, learn


def cmd_template(a):
    n = template.write_template(a.out)
    print(f"wrote {a.out} ({n} pages). Print at 100% / actual size, fill in every box, then run `learn`.")


def cmd_learn(a):
    existing = Hand.load(a.out) if os.path.exists(a.out) and not a.fresh else None
    hand, warnings, added = learn([page.load(p) for p in a.scans], existing)
    hand.save(a.out)
    total = sum(len(v) for v in hand.glyphs.values())
    print(f"added {added} new samples: {len(hand.glyphs)} characters, {total} samples in all, "
          f"cap height {hand.cap_height:.1f} mm -> {a.out}")
    for w in warnings:
        print("warning:", w)


def _flatten(path, out_dir, size):
    flat = page.flatten(page.load(path), page.A4_MM if size == "a4" else page.LETTER_MM)
    cv2.imwrite(os.path.join(out_dir, "page.png"), flat)
    return flat


def cmd_solve(a):
    os.makedirs(a.out_dir, exist_ok=True)
    hand = Hand.load(a.hand)
    flat = _flatten(a.homework, a.out_dir, a.paper)
    answers, notes, usage = solve.solve(flat, "".join(sorted(hand.glyphs)), model=a.model)
    print("cost:", usage.describe())
    moved = blanks.snap(answers, flat)
    if moved:
        print(f"snapped {moved} answer(s) onto the sheet's own lines and boxes")
    path = os.path.join(a.out_dir, "answers.json")
    solve.save(path, answers, notes)
    for x in answers:
        flag = "" if x.confidence == "high" else f"   [{x.confidence} confidence]"
        print(f"{x.id:>5}: {x.answer}{flag}")
    if notes:
        print("notes:", notes)
    print(f"-> {path}  (edit it if anything is wrong, then run `render`)")
    return flat


def cmd_render(a, flat=None):
    hand = Hand.load(a.hand)
    if flat is None:
        flat = cv2.imread(os.path.join(a.out_dir, "page.png"))
    answers, _ = solve.load(os.path.join(a.out_dir, "answers.json"))
    missing = set().union(*(hand.missing(x.answer) for x in answers if x.kind == "write"))
    if missing:
        print("warning: no handwriting sample for", " ".join(sorted(missing)), "- those characters are skipped")
    strokes = render.render_answers(answers, hand, flat, seed=a.seed, cap_mm=a.size)
    page_mm = page.A4_MM if a.paper == "a4" else page.LETTER_MM

    cv2.imwrite(os.path.join(a.out_dir, "preview.png"), render.overlay(flat, strokes))
    with open(os.path.join(a.out_dir, "answers.svg"), "w") as f:
        f.write(render.svg(strokes, page_mm))

    printer = Printer.load(a.printer) if a.printer and os.path.exists(a.printer) else Printer()
    if a.fit:
        printer = fit_paper(strokes, printer)
    try:
        code = generate(strokes, printer, marks=render.alignment_marks(answers))
    except OutOfReach as e:
        print("G-code not written:", e)
        return 1
    with open(os.path.join(a.out_dir, "answers.gcode"), "w") as f:
        f.write(code)
    print(f"wrote preview.png, answers.svg, answers.gcode in {a.out_dir}")
    print(f"place the paper with its top-left corner under the pen at bed X{printer.paper_x} Y{printer.paper_y}, top edge to the back")
    return 0


def cmd_run(a):
    flat = cmd_solve(a)
    return cmd_render(a, flat)


def cmd_blanks(a):
    """For solving a sheet by hand (or in a chat): where are the blanks, exactly?"""
    os.makedirs(a.out_dir, exist_ok=True)
    flat = _flatten(a.homework, a.out_dir, a.paper)
    found = blanks.find_blanks(flat)
    marked = flat.copy()
    for i, b in enumerate(found, 1):
        x, y, w, h = (round(v * page.PX_PER_MM) for v in (b.x, b.y, b.w, b.h))
        colour = (40, 140, 40) if b.kind == "line" else (200, 90, 20)
        if b.kind == "line":
            cv2.line(marked, (x, y), (x + w, y), colour, 3)
        else:
            cv2.rectangle(marked, (x, y), (x + w, y + h), colour, 3)
        cv2.putText(marked, str(i), (x, max(12, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)
        print(f"{i:>3}  {b.kind:<4}  x={b.x:6.1f}  y={b.y:6.1f}  w={b.w:6.1f}  h={b.h:5.1f}  (mm)")
    path = os.path.join(a.out_dir, "blanks.png")
    cv2.imwrite(path, marked)
    print(f"{len(found)} blank(s); page.png and {path} written")


def cmd_serve(a):
    from .web import serve
    serve(a.port, a.workspace, open_browser=not a.no_browser)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hwplot", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("template")
    t.add_argument("--out", default="handwriting-template.pdf")
    t.set_defaults(fn=cmd_template)

    l = sub.add_parser("learn")
    l.add_argument("scans", nargs="+", help="photos or scans of the filled-in sample pages")
    l.add_argument("--out", default="hand.json")
    l.add_argument("--fresh", action="store_true", help="start over instead of adding to the samples already in --out")
    l.set_defaults(fn=cmd_learn)

    def common(p, homework=True):
        if homework:
            p.add_argument("homework", help="photo or scan of the homework sheet")
        p.add_argument("--hand", default="hand.json")
        p.add_argument("--out-dir", default="out")
        p.add_argument("--paper", choices=["letter", "a4"], default="letter")
        if homework:
            p.add_argument("--model", choices=list(solve.MODELS), default=solve.MODEL,
                           help="which Claude solves the sheet (default: %(default)s)")

    def render_opts(p):
        p.add_argument("--printer", default="printer.json")
        p.add_argument("--fit", action="store_true", help="choose where the paper goes so the answers are centred on the bed")
        p.add_argument("--size", type=float, default=5.0, help="capital-letter height in mm (shrinks to fit)")
        p.add_argument("--seed", type=int, default=0)

    s = sub.add_parser("solve"); common(s); s.set_defaults(fn=cmd_solve)
    r = sub.add_parser("render"); common(r, homework=False); render_opts(r); r.set_defaults(fn=cmd_render)
    u = sub.add_parser("run"); common(u); render_opts(u); u.set_defaults(fn=cmd_run)

    b = sub.add_parser("blanks")
    b.add_argument("homework")
    b.add_argument("--out-dir", default="out")
    b.add_argument("--paper", choices=["letter", "a4"], default="letter")
    b.set_defaults(fn=cmd_blanks)

    v = sub.add_parser("serve")
    v.add_argument("--port", type=int, default=8000)
    v.add_argument("--workspace", default="workspace", help="where hand.json, printer.json and results are kept")
    v.add_argument("--no-browser", action="store_true")
    v.set_defaults(fn=cmd_serve)

    a = ap.parse_args(argv)
    rc = a.fn(a)
    return rc if isinstance(rc, int) else 0


if __name__ == "__main__":
    sys.exit(main())
