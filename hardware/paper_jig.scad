// Paper jig for an Ender 3 / 3 Pro: puts every homework sheet in the same place,
// with nothing under the paper and no tape.
//
// A tray that hangs off the bed's front edge on two clips (-D 'part="clips"'),
// one at each back corner, outside the paper. Each clip is a small spring clamp:
//
//   * a rigid shelf reaches 45 mm forward under the tray, so the tray sits on it
//     like a shelf on a bracket, and a sprung arm on top pinches it down;
//   * a rigid arm lies flat on top of the bed (that is what keeps the tray level
//     with the bed, whatever the plate's exact thickness), and a sprung finger
//     underneath pinches the bed plate up against it.
//
// The springs only add grip: where the jig sits is decided by the rigid faces,
// so it comes back to the same place every time. Nothing merely rests in place
// (the first hooks did, and the tray's weight tipped them straight off).
//
// The two clips differ. The nozzle and fan shroud pass low over the bed's front
// LEFT corner while the pen writes, so the left clip is flat and short on top
// (under 2.5 mm tall, 8.5 mm onto the bed) and has a side plate that stops
// against the bed's left edge. Nothing passes over the right corner, so the
// right clip has a long, thick arm on top: the stronger clamp of the two.
//
// For the bare bed plate (no glass): the clips are sized to its thickness, bed_t.
//
// The sheet goes on turned round (title towards you). Its top edge butts against
// the front lip and its left edge (on your right, since it's turned round)
// against the side wall; the tray's side tab sits against the bed's
// right edge, so the jig goes back in the same place every time. Two binder
// clips, through the gaps in the lip, hold the sheet's top to the tray. The pen
// never reaches the tray, so the clips are out of its way.
//
// Print the tray upright as oriented, PLA/PETG, 0.2 mm layers, no supports. It is
// longer than an Ender 3's 220 mm bed is wide: turn it 45 degrees in the slicer.
// The clips (openscad -D 'part="clips"') print lying on their sides as laid out.
//
// Coordinates: x along the bed's front edge (0 = bed's left edge), y = 0 at the
// bed's front edge and negative in front of it, z = 0 at the bed's surface.

bed_w     = 235;    // width of the bed's surface (glass or bare)
paper_w   = 215.9;  // US Letter; 210 for A4
paper_l   = 279.4;  // the sheet ends paper_l - overhang behind the front edge
overhang  = 60;     // tray depth: the sheet ends 15 mm before the back edge, clear of the back clips
tray_t    = 4;      // tray thickness below the surface; its back face is what bears on the bed's edge
bed_t     = 3.2;    // the bed plate's thickness at its front edge (1/8 inch, measured)
spine_t   = 4;      // the clip's back, between the tray and the bed's edge
tab_reach = 10;     // how far the side tab runs on past the tray's back, beside the bed
clip_w_r  = 6.6;    // right clip: fits between the side wall and the tab
clip_w_l  = 8;      // left clip: fits in the strip left of the sheet
cap_t     = 1.6;    // left clip's side plate, against the bed's left edge
shelf_l   = 45;     // shelf under the tray: reaches past where the tray's weight acts
tray_grip = 0.55;   // how far the sprung arm is pushed up by the tray (about 4 N)
bed_grip_r = 0.8;   // how far the bed pushes the right clip's finger down (about 6 N)
bed_grip_l = 0.9;   // and the left clip's (about 7 N)
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
            // side tab: hugs the bed's right edge so the jig always sits in the same place
            translate([bed_w, -overhang - fence_t, -tray_t]) cube([tab_t, overhang + fence_t + tab_reach, tray_t]);
        }
        // gaps in the lip, for the clips that hold the sheet
        for (c = gaps) translate([c - gap_w / 2, -overhang - fence_t - 1, 0.01]) cube([gap_w, fence_t + 2, fence_h + 1]);
    }
}

// ---- the clips -------------------------------------------------------------
// Drawn as 2D profiles in the plane [y, z]: y = 0 at the tray's back face (the
// bed's front edge is at y = spine_t), z = 0 at the bed's surface. A clip is
// the same profile all the way along x, so it prints lying on its side: every
// spring is laid down in-plane, which is the strong way, and nothing overhangs.

zb = -bed_t;  // the bed's underside

// The tray's side of a clip, the same on both.
module tray_side() {
    // shelf: the tray sits on this
    polygon([[0.01, -tray_t], [-shelf_l + 1.5, -tray_t], [-shelf_l, -tray_t - 1],
             [-shelf_l, -tray_t - 2.5], [0.01, -tray_t - 5]]);
    // sprung arm over the tray: clear of it except at the bump near its tip,
    // 2 mm thick at the root thinning to 1.4, nose turned up to lead the tray in
    polygon([[0.01, 0.15], [-14.2, 0.15], [-16, -tray_grip], [-19.5, 1.0], [-19.5, 2.1],
             [-16.2, 1.55], [0.01, 2.15]]);
}

// Right clip: long rigid arm on top of the bed, finger underneath rooted at
// the spine and pressing up 19 mm in, under-beam below it as its hard stop.
module clip_right_profile() {
    top = 4.5;
    difference() {
        union() {
            tray_side();
            translate([0, -10.7]) square([spine_t, 10.7 + top]);                          // spine
            polygon([[spine_t - 0.01, 0], [spine_t + 19.5, 0], [spine_t + 22, 1.0],       // arm on the bed
                     [spine_t + 22, top - 1.5], [spine_t + 20.5, top], [spine_t - 0.01, top]]);
            polygon([[spine_t - 0.01, zb - 0.25], [spine_t + 17.3, zb + bed_grip_r - 0.5],  // finger
                     [spine_t + 19, zb + bed_grip_r], [spine_t + 23.5, zb - 0.9],
                     [spine_t + 23.5, zb - 2.1], [spine_t + 19, zb + bed_grip_r - 2.0],
                     [spine_t - 0.01, zb - 2.65]]);
            polygon([[spine_t - 0.01, -6.7], [spine_t + 14.5, -6.7], [spine_t + 15.5, -5.9],  // under-beam
                     [spine_t + 21, -5.9], [spine_t + 21, -9.7], [spine_t + 20, -10.7],
                     [spine_t - 0.01, -10.7]]);
        }
        corner_reliefs();
    }
}

// Left clip: short thin arm on top of the bed (the nozzle passes behind it),
// finger underneath rooted on a post at the far end and pressing up 5.5 mm in,
// under the arm; the post is also the hard stop if the tray is leant on.
module clip_left_profile() {
    difference() {
        union() {
            tray_side();
            translate([0, -10.2]) square([spine_t, 10.2 + 2.15]);                         // spine
            polygon([[spine_t - 0.01, 0], [spine_t + 7, 0], [spine_t + 8.5, 0.8],         // arm on the bed
                     [spine_t + 8.5, 1.8], [spine_t - 0.01, 1.8]]);
            polygon([[spine_t + 24.51, zb - 0.25], [spine_t + 7.2, zb + bed_grip_l - 0.5],  // finger
                     [spine_t + 5.5, zb + bed_grip_l], [spine_t + 3.4, zb + bed_grip_l - 0.6],
                     [spine_t + 3.4, zb + bed_grip_l - 1.8], [spine_t + 7.2, zb + bed_grip_l - 1.9],
                     [spine_t + 24.51, zb - 2.65]]);
            polygon([[spine_t - 0.01, zb - 0.25], [spine_t + 2.2, zb - 0.25], [spine_t + 2.2, -5.8],  // under-beam,
                     [spine_t + 9, -5.8], [spine_t + 10, -6.7], [spine_t + 24.5, -6.7],              // lift stop, post
                     [spine_t + 24.5, zb - 0.2], [spine_t + 26.8, zb - 0.2], [spine_t + 28, zb - 1.4],
                     [spine_t + 28, -9.2], [spine_t + 27, -10.2], [spine_t - 0.01, -10.2]]);
        }
        corner_reliefs();
    }
}

// Printed inside corners come out rounded; these nicks keep that rounding from
// holding the bed's edge and the tray's edge off the faces they locate against.
module corner_reliefs() {
    translate([spine_t, 0]) circle(r = 0.5, $fn = 16);
    translate([0, -tray_t]) circle(r = 0.5, $fn = 16);
}

// The side plate on the left clip's outer end: stops against the bed's left edge.
module left_cap_profile() {
    translate([spine_t - 0.01, -1.6]) square([8.51, 1.6 + 1.8]);
}

module clip_right() { linear_extrude(clip_w_r) clip_right_profile(); }
module clip_left() {
    linear_extrude(cap_t) { clip_left_profile(); left_cap_profile(); }
    translate([0, 0, cap_t - 0.01]) linear_extrude(clip_w_l + 0.01) clip_left_profile();
}

module clips() {  // one of each, lying on their sides for printing (left clip's side plate down)
    translate([shelf_l, 11]) clip_right();
    translate([shelf_l, 33]) clip_left();
}

part = "jig";  // openscad -D 'part="clips"' for the clips
if (part == "jig") translate([0, 0, tray_t]) jig();  // sitting on the print bed
if (part == "clips") clips();
