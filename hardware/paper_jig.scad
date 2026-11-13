// Paper jig for an Ender 3 / 3 Pro: puts every homework sheet in the same place.
//
// A thin tray whose tongue lies on the front-right corner of the glass, taped
// down along its whole length with masking/painter's tape. No binder clip: on
// the front edge its spine would sit exactly where the tray runs, and on the
// side edge it scrapes the printer's frame. Tape is flat, so it hits nothing.
// The clip that was at that corner goes back on the front edge, left of the jig.
// The sheet lies on the bed turned round (title towards you). The overhanging
// top part rests on this tray; the sheet's top edge butts against the tray's
// front lip and its left edge (on your right, since it's turned round) against
// the side wall. Same spot every time, so the printer needs no lining-up stops.
// One short piece of tape holds the sheet's corner to the tray; the pen never
// reaches that strip of the page.
//
// Fit it once, push it snug against the glass, tape it, and leave it there:
// then run the jig calibration (two crosses, measured with a ruler) so the
// software knows exactly where it sits.
//
// Print flat as oriented, PLA/PETG, 0.2 mm layers, no supports.

width     = 100;   // along the bed's front edge
tongue    = 12;    // how far it reaches onto the glass, under the clip
overhang  = 44;    // how far it sticks out in front of the bed, holding the sheet's top
plate     = 1.6;   // thickness; the sheet steps down by this much where the tongue ends
lip_h     = 4;     // fences rise this far above the plate
lip_t     = 2.4;
wall_len  = overhang;  // side wall runs along the overhang, leaving the tongue clear for the clip

// tray (y = 0 is the front, nearest you; the tongue is at the back, on the glass)
cube([width, overhang + tongue, plate]);
// front lip: the sheet's top edge
cube([width, lip_t, plate + lip_h]);
// side wall at the right end: the sheet's left edge
translate([width - lip_t, 0, 0]) cube([lip_t, wall_len, plate + lip_h]);
