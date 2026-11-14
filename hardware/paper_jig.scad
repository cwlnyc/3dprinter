// Paper jig for an Ender 3 / 3 Pro: puts every homework sheet in the same place,
// with nothing under the paper and no tape.
//
// One piece that hangs off the bed's front edge. Two thin hooks rest on the
// bed's front corners, outside the paper, and its back face presses against the
// bed's front edge: the tray sticking out in front makes it lean back against
// the bed, so gravity holds it there, no clamp needed. The tray's top is exactly
// level with the bed surface (the hooks set that, whatever the bed is made of),
// so the sheet lies dead flat from the tray onto the bed, with no step.
//
// Works on the glass or on the bare bed. On the glass, the jig takes the place
// of the two front clips; the two back clips stay, and the sheet stops before
// reaching them.
//
// The sheet goes on turned round (title towards you). Its top edge butts against
// the front lip and its left edge (on your right, since it's turned round)
// against the side wall; the right-hand hook's side tab sits against the bed's
// right edge, so the jig goes back in the same place every time. Two binder
// clips, through the gaps in the lip, hold the sheet's top to the tray. The pen
// never reaches the tray, so the clips are out of its way.
//
// Print upright as oriented, PLA/PETG, 0.2 mm layers, no supports. It is longer
// than an Ender 3's 220 mm bed is wide: turn it 45 degrees in the slicer.
//
// Coordinates: x along the bed's front edge (0 = bed's left edge), y = 0 at the
// bed's front edge and negative in front of it, z = 0 at the bed's surface.

bed_w     = 235;    // width of the bed's surface (glass or bare)
paper_w   = 215.9;  // US Letter; 210 for A4
paper_l   = 279.4;  // the sheet ends paper_l - overhang behind the front edge
overhang  = 60;     // tray depth: the sheet ends 15 mm before the back edge, clear of the back clips
tray_t    = 4;      // tray thickness below the surface; its back face is what bears on the bed's edge
hook_w    = 8;      // hooks stay within the strip either side of the centred sheet
hook_d    = 6;      // how far they reach onto the bed
hook_t    = 1.2;
fence_h   = 3;      // lip and wall height above the tray
fence_t   = 2.4;
tab_t     = 2;      // side tab against the bed's right edge (the only thing beside the bed)
gap_w     = 34;     // gaps in the lip for the binder clips
gaps      = [55, 160];  // their centres (x)

paper_right = (bed_w + paper_w) / 2;  // sheet centred across the bed

module jig() {
    difference() {
        union() {
            // tray, its top flush with the bed surface
            translate([0, -overhang - fence_t, -tray_t]) cube([bed_w, overhang + fence_t, tray_t]);
            // front lip: the sheet's top edge
            translate([0, -overhang - fence_t, 0]) cube([bed_w, fence_t, fence_h]);
            // side wall: the sheet's left edge (on your right)
            translate([paper_right, -overhang - fence_t, 0]) cube([fence_t, overhang + fence_t, fence_h]);
            // hooks resting on the bed's front corners
            for (x = [0, bed_w - hook_w]) translate([x, -0.01, 0]) cube([hook_w, hook_d + 0.01, hook_t]);
            // side tab: hugs the bed's right edge so the jig always sits in the same place
            translate([bed_w, -overhang - fence_t, -tray_t]) cube([tab_t, overhang + fence_t + hook_d, tray_t + hook_t]);
        }
        // gaps in the lip, for the clips that hold the sheet
        for (c = gaps) translate([c - gap_w / 2, -overhang - fence_t - 1, 0.01]) cube([gap_w, fence_t + 2, fence_h + 1]);
    }
}

translate([0, 0, tray_t]) jig();  // sitting on the print bed
