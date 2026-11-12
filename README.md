# homework-plotter

Learns your handwriting from one sample sheet, reads a homework sheet from a
photo, works out the answers, and writes them back onto the paper in your
handwriting using a pen clipped to a 3D printer.

```
template ─► (you fill it in) ─► learn ─► hand.json
homework photo ─► solve ─► answers.json ─► render ─► preview.png / answers.svg / answers.gcode ─► printer
```

## Setup

```bash
cd homework-plotter
python3 -m pip install -r requirements.txt
export ANTHROPIC_API_KEY=...   # only `solve` / `run` need it
```

## The easy way: the local web page

```bash
python3 -m hwplot serve
```

This opens http://localhost:8000. It walks you through everything below step by
step: what to print and photograph, which pen-holder file to print, the
printer settings, and uploading the homework. It makes all the files there and
lets you fix answers and redraw before printing. Everything it makes is kept in
`workspace/`. It only listens on your own computer.

The rest of this README is the same flow from the command line.

## 1. Teach it your handwriting

```bash
python3 -m hwplot template            # -> handwriting-template.pdf (2 pages)
```

Print it **at 100% / actual size**. Write one character in each box, sitting on
the tick marks, **with the pen you will put in the printer**. Every character
is on the sheet twice, so the output alternates between your two versions and
doesn't look stamped. Photograph or scan both pages (any angle is fine, as long
as all four black corner squares are in the shot), then:

```bash
python3 -m hwplot learn page1.jpg page2.jpg     # -> hand.json
```

It warns about any box it found empty. Redo just that page if you need to.

## 2. Answer a sheet

```bash
python3 -m hwplot run homework.jpg --fit
```

That runs both halves. Separately:

- `solve homework.jpg` finds the page in the photo, flattens it, and sends it to
  Claude, which reads each question, solves it, and says where the answer goes.
  The result is written to `out/answers.json`, with a confidence on each answer.
  It uses Claude Sonnet 5.5 by default, roughly 5–8¢ a sheet. Pass
  `--model claude-opus-5-5` for the most accurate (about 20¢), or
  `--model claude-haiku-5-5` for under 1¢ on simple sheets. The web page has the
  same choice, and every solve prints what it actually cost.
- `render` lays the answers out in your handwriting and writes:
  - `out/preview.png`: the sheet with the answers drawn on. **Check this first.**
  - `out/answers.svg`: just the answers, at true page size. This is the "file of
    answers in place": you can also send it to any SVG pen plotter or Cricut.
  - `out/answers.gcode`: the job for the printer.

After solving, each answer is snapped onto the sheet's own blanks: a printed
answer line, an empty answer box, or (for multiple choice) the printed option it
circles. Claude places boxes by eye, and the page says exactly where the lines
are. Each blank takes one answer, and anything more than about 9 mm from a blank
keeps Claude's box. The results page says which ones were snapped.

Each letter is made fresh: two of your samples of it are blended in random
proportions and the result is wobbled slightly, and each line drifts a little.
So no two copies of a word are identical. `learn` adds to the samples you
already have (use `--fresh` to start over), so filling in more sheets over time
gives a wider range. Scanning the same page twice adds nothing.

Characters you never wrote are built in your style: accents (á ñ ü ¿ ¡)
from your own letters plus the mark, superscripts (² ³) from your digits made
small and raised, and maths symbols (× ÷ ± ≤ ≥ ≠ ≈) from your own pieces. Others
(√ π ∞ θ ° and arrows) are drawn from plain shapes, then given your measured
slant, size and wobble. The template's optional page 3 has the common ones: fill
it in and your real versions are used instead.

Answers can also be drawings (`kind: "draw"`): lines, arrows, boxes, polygons,
circles, and curves through points for graphs. They come out the way a hand
draws them: lines bow and wander a little and run slightly past their ends,
corners overshoot, and circles are a touch oval and overlap where they close.

When answers spread wider than the pen can reach with the sheet in one place,
the job is split into passes. It's still one print: between passes the printer
parks and its screen says how to turn the sheet, then it stops to line it up.

If an answer is wrong or sits in the wrong spot, edit `out/answers.json` (each
`box` is `[x, y, width, height]` in mm from the page's top-left corner) and
run `render` again. No new API call is needed. `--size 4` writes smaller,
`--seed 3` gives a different random mix of your letter variants, and
multiple-choice answers are circled instead of written.

### Solving a sheet in a Claude chat instead

If you'd rather not use an API key, send the homework photo to Claude in a chat.
Claude runs `python3 -m hwplot blanks photo.jpg` to flatten the page and number
its answer lines and boxes, solves the questions, and sends back an
`answers.json`. On the web page, open step 4's **"Already have the answers?"**
and upload the **same photo** with that file. Positions only line up with the
photo that was solved, so retaking the photo means solving it again.

## 3. The printer

### Print the pen holder

Ready-made STLs in `hardware/stl/` (source: `hardware/pen_holder.scad`):

| File | For |
|---|---|
| `pen_holder_8mm.stl` | pencils (hex or round), mechanical pencils |
| `pen_holder_10mm.stl` | most ballpoint and gel pens |
| `pen_holder_12mm.stl` | markers, chunky pens |
| `pen_holder_pilot_g2.stl` | Pilot G2 gel pens: an 11.0 mm hole sized for its 10.5 mm rubber grip |

![pen holder](hardware/pen_holder.png)

It's one printed part with no springs to buy. Two thin parallel leaves let the
pen ride up a couple of millimetres when it touches the paper, so the pressure
stays light and even. To set it up:

1. **Measure your pen's barrel** where it'll be clamped and pick the closest
   STL. For another size, set `pen_d` in the `.scad` in OpenSCAD and export,
   or use "Make STL" on the web page.
2. Print it in PLA or PETG at 0.2 mm layers with no supports.
3. Push an M3 nut into the slot on top of the clamp block, then use an M3 screw
   to grip the pen.
4. Bolt the plate to your toolhead with two screws through the slots. The
   slots fit any hole spacing from 22 to 44 mm, and the plate is only 1.5 mm
   thick under each screw head, so the screws already holding a cover on the
   print head are usually long enough to reuse.
5. Slide the pen down so its tip sits **about 2 mm below the nozzle**. That
   gives the pen first contact, and the flexure absorbs homing.

### Calibrate once

```bash
cp printer.example.json printer.json
```

- `bed_x`, `bed_y`: your bed size.
- `pen_offset_x/y`: how far the pen tip is from the nozzle, in mm. To find it,
  move the nozzle to X100 Y100, lower until the pen marks the paper, and
  measure where the dot landed relative to the X100 Y100 point.
- `z_down`: lower Z by hand until the pen just draws a clean line, then go about
  0.5 mm further for the flexure. `z_up` is 3 mm above that.
- `pause`: `M0` for Marlin with a screen. Use `PAUSE` on Klipper.

### Run it

`render` prints where the paper goes, for example "top-left corner under the
pen at bed X12.3 Y241.0". A Letter page is taller than most beds, so it usually
overhangs. That's fine, because `--fit` centres the *answers* on the bed. Tape
the page down. The G-code homes, moves the pen over the paper's corner (when
that's on the bed) and pauses so you can line the paper up. Then it writes.

The G-code refuses to generate if any stroke falls outside the bed, rather
than driving the head into the frame.

## Limits worth knowing

- **Check the preview.** Claude is good at homework, but a misread photo means
  a confidently wrong answer in ink. Low-confidence answers are flagged.
- Answer boxes are placed from the photo. They are usually right, and a printed
  underline in the box is snapped to automatically, but a blank with no line
  can land a few mm off.
- It writes only characters you gave it samples for. A character it has no
  sample for is skipped, with a warning.
- Glyphs are centre-line traces of your scan, so a felt tip gives cleaner
  samples than a pen that skips.
- Bambu printers don't take raw G-code jobs the same way. This targets Marlin
  and Klipper machines (Ender, Prusa, Voron and similar).

## The Claude connector: send a photo, get it printed

`python3 -m hwplot mcp` lets Claude, in any chat including on your phone, get
the homework photo from your Mac, solve it, and print it. Claude does the
solving in the chat, so it uses your Claude plan and **no API credits**.

**Every time:** save the homework photo into `workspace/photos/` (an iCloud
Drive folder works well: pass it with `--photos`), put the sheet in the jig, and
tell Claude "do my homework". Claude shows you the preview before it prints.

**Setup, once:**

1. Install:
   ```bash
   python3 -m pip install -r requirements.txt
   ```
2. Get `cloudflared` into your home folder (no Homebrew needed). Run
   `uname -m`: `arm64` means Apple Silicon, `x86_64` means Intel.
   ```bash
   cd ~ && curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz | tar -xz
   ```
   (On Intel, use `cloudflared-darwin-amd64.tgz` instead.)
3. Put the permanent front door online at `hwplot-…pages.dev`, with your own
   Cloudflare account. This needs Node, and logs you in to Cloudflare in the
   browser if you aren't already:
   ```bash
   ./scripts/relay-deploy.sh
   ```
4. Start the connector, and leave the window open. It starts the tunnel
   itself, tells the front door where your Mac is, and prints your connector
   URL, which is the same every time:
   ```bash
   python3 -m hwplot mcp --photos ~/Library/Mobile\ Documents/com~apple~CloudDocs/Homework
   ```
5. In Claude: **Settings → Connectors → Add custom connector**, and paste that
   URL. **Keep it private:** anyone with it can print on your printer.
6. Plug the printer into the Mac with USB. Without it, the connector saves the
   G-code for the SD card instead.

After that, starting the connector (step 4) is all you ever do.

Without the front door, `python3 -m hwplot mcp` alone serves on
`localhost:8765`, and any tunnel pointed at it works. The front door just keeps
the address from changing.

### Running it on a Raspberry Pi instead of the Mac

A Pi 3 or newer next to the printer can run the connector all the time, so the
Mac doesn't have to stay plugged in.

1. With Raspberry Pi Imager, flash **Raspberry Pi OS Lite (64-bit)**. In its
   settings, set a hostname (e.g. `hwplot`), a user, your Wi-Fi, and turn on SSH.
2. Stop the connector on the Mac (Ctrl + C). Only one should run at a time.
3. From the Mac, in the 3dprinter folder:
   ```bash
   ./scripts/pi-push.sh <user>@hwplot.local
   ```
   It copies the project and your `workspace/` (handwriting, printer settings,
   connector secret) and installs everything. The connector then starts by
   itself whenever the Pi is on. Same connector URL as before.
4. Plug the printer into the Pi with a USB-A to Mini-USB data cable.

Rerun step 3 after changing anything on the Mac, such as handwriting or
calibration.

### Sending the photo from the chat

`put_photo` takes the photo itself (base64), so a chat can hand over the
picture it was sent instead of it being saved to a folder:
`python3 -m hwplot remote put_photo --photo homework.jpg`.

### The paper jig

`hardware/stl/paper_jig.stl` is a tray that clips onto the front-right corner of
the glass with the binder clip already there. The sheet goes turned round
(title towards you): its top edge against the front lip, its left edge against
the side wall, and the clip holds it. No tape and no lining up.

Once it's fitted, ask Claude to run the jig setup (`jig_test_print`, then
`jig_calibrate`). The printer draws two crosses, you measure where they landed
with a ruler, and the software learns exactly where the jig sits. After that,
every print skips the alignment stops. In the jig the pen reaches roughly 1–15
cm from the page's left edge and 4.5–25 cm from its top. Answers outside that
are flagged rather than printed.

## Tests

```bash
python3 -m pytest -q tests
```

The tests build a fake filled-in sample sheet, photograph it at an angle,
learn from it, and check the layout and G-code. They don't need a pen or an
API key.
