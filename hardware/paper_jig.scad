// Paper jig for an Ender 3 / 3 Pro: puts every homework sheet in the same place,
// with nothing under the paper and no tape.
//
// A tray that hangs off the bed's front edge. Two small clips (paper_jig_clips)
// push onto the tray's back corners; each has a hook that rests on the bed's
// front corner, outside the paper, and a spine that bears on the bed's front
// edge: the tray sticking out in front makes it lean back against the bed, so
// gravity holds it there, no clamp needed. The tray's top is level with the bed
// surface (the hooks set that, whatever the bed is made of), so the sheet lies
// dead flat from the tray onto the bed, with no step.
//
// The hooks are separate parts because, printed on the tray, they would hang in
// the air over nothing: they come out as loose strands and snap off.
//
// Works on the glass or on the bare bed. On the glass, the jig takes the place
// of the two front clips; the two back clips stay, and the sheet stops before
// reaching them.
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
hook_w    = 6;      // clips stay within the strip either side of the centred sheet
hook_d    = 6;      // how far the hook reaches onto the bed
hook_t    = 1.6;
spine_t   = 2;      // the clip's back, between the tray and the bed's edge
jaw_l     = 10;     // how far the clip's jaws reach along the tray
fit       = 0.2;    // clearance round the tray in the clip
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
            translate([bed_w, -overhang - fence_t, -tray_t]) cube([tab_t, overhang + fence_t + spine_t + hook_d, tray_t]);
        }
        // gaps in the lip, for the clips that hold the sheet
        for (c = gaps) translate([c - gap_w / 2, -overhang - fence_t - 1, 0.01]) cube([gap_w, fence_t + 2, fence_h + 1]);
    }
}

// One clip, in the tray's frame (y = 0 at the tray's back face). Its profile is
// the same along x, so it prints lying on its side: strong, and no overhangs.
module clip_profile() {
    // top jaw over the tray, carrying on back over the bed as the hook
    translate([-jaw_l, 0]) square([jaw_l + spine_t + hook_d, hook_t]);
    // spine down the tray's back face
    translate([0, -tray_t - fit - hook_t]) square([spine_t, tray_t + fit + 2 * hook_t]);
    // bottom jaw under the tray
    translate([-jaw_l, -tray_t - fit - hook_t]) square([jaw_l + spine_t, hook_t]);
}

module clips() {  // two, side by side, lying flat for printing
    for (i = [0, 1]) translate([0, i * 12, 0]) linear_extrude(hook_w) clip_profile();
}

part = "jig";  // openscad -D 'part="clips"' for the clips
if (part == "jig") translate([0, 0, tray_t]) jig();  // sitting on the print bed
if (part == "clips") clips();
