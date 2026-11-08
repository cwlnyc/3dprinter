// Spring-loaded pen holder for a 3D printer, printed in one piece.
//
// A parallelogram flexure (two thin parallel leaves) lets the pen ride up a
// few millimetres when it touches the paper, so slightly uneven paper or a
// Z a little too low gives even, light pressure instead of a gouge or a skip.
// It is not a crash stop: set z_down with care, a few mm too low will bend it hard.
// No springs, bearings or rods to buy: just two M3 screws to mount it and one
// M3 screw + nut to grip the pen.
//
// Print: as oriented (mount plate standing up), PETG or PLA, 0.2 mm layers,
// 4 walls, no supports. The top leaf bridges 30 mm, which most printers manage;
// slow the bridge speed if yours sags.
//
// Mount: bolt the plate to the toolhead (fan shroud / carriage) with M3
// screws through the slots. The slots take any hole spacing from
// slot_min to slot_max, so measure your two screw holes and they will fit.

/* [Pen] */
pen_d        = 10.0;  // pen barrel diameter where it is clamped (measure it!)
clearance    = 0.4;   // added to pen_d for the bore
/* [Flexure] */
leaf_len     = 30;    // longer = softer
leaf_t       = 0.6;   // thinner = softer. Printed flat, so this is layers: 3 x 0.2 mm.
                      // ~1.5 N (150 g) of pen pressure at 2 mm of travel in PLA.
leaf_w       = 14;    // width of each leaf
leaf_gap     = 22;    // vertical distance between the two leaves
/* [Mount] */
plate_w      = 56;
plate_h      = 30;
plate_t      = 5;
slot_min     = 22;    // smallest screw spacing the slots accept
slot_max     = 44;    // largest
slot_z       = 15;    // height of the slot centreline on the plate
standoff     = 12;    // gap from plate to flexure frame (clears fans, hoses)
/* [Hardware] */
m3           = 3.4;
m3_nut_af    = 5.7;   // across flats, with clearance
m3_nut_t     = 2.6;
// Reusing the printer's own screws: the plate is only this thick under each
// screw head, so a screw that held the cover alone still reaches far enough.
screw_seat   = 1.5;   // set to plate_t for a plain plate and longer screws
head_d       = 6.4;   // screw head diameter plus clearance

$fn = 64;

carrier_d = pen_d + clearance + 8;   // carrier block size around the pen
frame_t   = 6;                       // thickness of the fixed back post
H         = leaf_gap + leaf_t;       // overall height of the flexure

module slot(len, d) {
    hull() {
        translate([-len/2, 0, 0]) cylinder(d = d, h = 50, center = true);
        translate([ len/2, 0, 0]) cylinder(d = d, h = 50, center = true);
    }
}

module mount_plate() {
    difference() {
        translate([-plate_w/2, 0, 0]) cube([plate_w, plate_t, plate_h]);
        // two slots, one each side of centre, so any spacing in range fits
        for (s = [-1, 1])
            translate([s * (slot_min + slot_max) / 4, plate_t/2, slot_z])
                rotate([90, 0, 0]) slot((slot_max - slot_min) / 2, m3);
        // pockets for the screw heads, from the outer face, leaving screw_seat of plate
        for (s = [-1, 1])
            translate([s * (slot_min + slot_max) / 4, plate_t + 25 - (plate_t - screw_seat), slot_z])
                rotate([90, 0, 0]) slot((slot_max - slot_min) / 2, head_d);
    }
}

module back_post() {
    // fixed side of the flexure, tied to the plate by a standoff block
    translate([-leaf_w/2, plate_t, 0]) cube([leaf_w, standoff + frame_t, H]);
}

module leaves() {
    y0 = plate_t + standoff + frame_t;
    for (z = [0, leaf_gap])
        translate([-leaf_w/2, y0 - 0.01, z]) cube([leaf_w, leaf_len + 0.02, leaf_t]);
}

module carrier() {
    y0 = plate_t + standoff + frame_t + leaf_len;
    difference() {
        translate([-carrier_d/2, y0, 0]) cube([carrier_d, carrier_d, H]);
        // pen bore, straight through vertically
        translate([0, y0 + carrier_d/2, -1]) cylinder(d = pen_d + clearance, h = H + 2);
        // clamp screw from the front, with a captive nut
        translate([0, y0 + carrier_d/2, H/2]) rotate([-90, 0, 0]) cylinder(d = m3, h = carrier_d);
        translate([0, y0 + carrier_d - 2.2 - m3_nut_t, H/2])
            rotate([-90, 0, 0]) rotate([0, 0, 30]) cylinder(d = m3_nut_af / cos(30), h = m3_nut_t, $fn = 6);
        // let the nut drop in from the top
        translate([-m3_nut_af/2, y0 + carrier_d - 2.2 - m3_nut_t, H/2]) cube([m3_nut_af, m3_nut_t, H]);
    }
}

union() {
    mount_plate();
    back_post();
    leaves();
    carrier();
}
