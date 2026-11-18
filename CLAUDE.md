
## Writing homework: the user's standing preferences

- "Loose-leaf" means Kokuyo Campus B5 loose-leaf (NO-836C): 182 x 257 mm, 26 holes
  on the left, 5 mm ruled, 43 lines. Measured from a photo: the top thick ruled
  line is ~30.5 mm below the top edge, thin lines every 5 mm below it (first thin
  line at ~36.1 mm), bottom thick line ~12 mm above the bottom edge, ruled lines
  start ~12 mm from the holed edge. "No." and "Date" are printed at the top right.
- Use the whole page, top lines included. In the jig, with the title towards the
  user, the pen reaches page x ~11-141 mm and y from ~64 mm down; turned round
  (title to the back, plan_passes does this as a second pass) it reaches the top
  but only x ~41-171 mm. So: body text left-aligned at the normal margin from the
  first reachable line, and put things that suit the narrower strip (a centred
  title, the date in the Date box) in the top lines, rather than indenting all
  the text to the shared 41-141 mm strip (the user found that looked centred).
- Before every print, tell the user exactly how to put the sheet in for each
  pass: which end towards them, which side up, which edge on the wall, and a
  check they can see (e.g. "No./Date and ~3 cm of blank paper next to the lip").
- Homework photos: ask for them taken with the sheet already clipped in the jig,
  from straight above, whole sheet in view. Then find the page's four corners
  by eye on zoomed crops (the top and left edges are pinned straight by the lip
  and wall) and pass them to page.flatten(corners=...). Corners guessed from a
  loose photo were off by up to ~9 mm, which is what made every page need a
  test. Automatic paper detection (colour thresholds, GrabCut) was tried and
  was not reliable under the desk lamp and the printer screen's blue light.
- The jig calibration was re-derived from printed test circles photographed in
  the jig: corner at X226.1, Y-67.0 (the earlier cross measurement had been
  misread). If pages still land consistently off, correct jig_x/jig_y rather
  than shifting answers per page.
