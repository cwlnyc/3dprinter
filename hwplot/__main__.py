"""Command line: python -m hwplot <command>.

  template  print this, write one character per box
  learn     scan the filled-in sample sheets -> hand.json
  solve     scan a homework sheet -> answers.json (+ the flattened page)
  render    answers.json + hand.json -> preview PNG, SVG and G-code
  run       solve + render in one go
"""
from __future__ import annotations

import argparse
import os
import sys

import cv2

from . import page, render, solve, template
from .gcode import OutOfReach, Printer, fit_paper, generate
from .glyphs import Hand, learn


def cmd_template(a):
    n = template.write_template(a.out)
    print(f"wrote {a.out} ({n} pages). Print at 100% / actual size, fill in every box, then run `learn`.")


def cmd_learn(a):
    hand, warnings = learn([page.load(p) for p in a.scans])
    hand.save(a.out)
    total = sum(len(v) for v in hand.glyphs.values())
    print(f"learned {len(hand.glyphs)} characters ({total} samples), cap height {hand.cap_height:.1f} mm -> {a.out}")
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
    answers, notes = solve.solve(flat, "".join(sorted(hand.glyphs)))
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
        code = generate(strokes, printer)
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


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hwplot", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("template")
    t.add_argument("--out", default="handwriting-template.pdf")
    t.set_defaults(fn=cmd_template)

    l = sub.add_parser("learn")
    l.add_argument("scans", nargs="+", help="photos or scans of the filled-in sample pages")
    l.add_argument("--out", default="hand.json")
    l.set_defaults(fn=cmd_learn)

    def common(p, homework=True):
        if homework:
            p.add_argument("homework", help="photo or scan of the homework sheet")
        p.add_argument("--hand", default="hand.json")
        p.add_argument("--out-dir", default="out")
        p.add_argument("--paper", choices=["letter", "a4"], default="letter")

    def render_opts(p):
        p.add_argument("--printer", default="printer.json")
        p.add_argument("--fit", action="store_true", help="choose where the paper goes so the answers are centred on the bed")
        p.add_argument("--size", type=float, default=5.0, help="capital-letter height in mm (shrinks to fit)")
        p.add_argument("--seed", type=int, default=0)

    s = sub.add_parser("solve"); common(s); s.set_defaults(fn=cmd_solve)
    r = sub.add_parser("render"); common(r, homework=False); render_opts(r); r.set_defaults(fn=cmd_render)
    u = sub.add_parser("run"); common(u); render_opts(u); u.set_defaults(fn=cmd_run)

    a = ap.parse_args(argv)
    rc = a.fn(a)
    return rc if isinstance(rc, int) else 0


if __name__ == "__main__":
    sys.exit(main())
