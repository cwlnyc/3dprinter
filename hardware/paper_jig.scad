// Paper jig for an Ender 3 / 3 Pro: puts every homework sheet in the same place.
//
// A thin tray whose tongue lies on the front-right corner of the glass, held by
// the binder clip at that corner, moved onto the glass's RIGHT edge so it grips
// the end of the tongue from the side. (A clip on the front edge can't work:
// its spine wraps round the front of the glass, exactly where the tray runs.) The sheet lies on the bed
// turned round (title towards you). The overhanging top part rests on this
// tray; the sheet's top edge butts against the tray's front lip and its left
// edge (on your right, since it's turned round) against the side wall. Same
// spot every time, so the printer needs no lining-up stops.
//
// The binder clip also holds the sheet: its mouth faces into the bed, so open
// it, slide the sheet's corner under its jaw on top of the tongue, let go. No tape. The pen never reaches that
// strip of the page, so the clip can sit on it.
//
// Fit it once, push it snug against the glass, clamp it, and leave it there:
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
