// Parametric name peg - text auto-fits the available space
// All dimensions in mm
// Z=0 is the bottom of the head; the main body's top face is at Z=10.

name = "Michael";

// Overall body
length = 110;   // X
width  = 20;    // Y
depth  = 8;     // Z thickness of the main body
head_depth = 10; // total thickness of the head (X=0 end)
head_len   = 20; // head runs from X=0 to the start of the notch

top_z = head_depth;   // top face of everything (body is flush with head top)

// Notch cut into the bottom face of the body
notch_len    = 34;  // along X
notch_offset = 20;  // from the X=0 end
notch_depth  = 3;   // cut up from the body's bottom face

// Colour layer: one 0.2 mm layer on top (colour change at Z = top_z)
layer_h     = 0.4;
block_len   = 30;   // coloured block at the X=0 end
text_start  = 35;   // name area starts here (first 35 mm clear of text)

// Text auto-fit
max_text_size = 10;   // size used for short names
text_margin   = 2;    // clear space kept at each end of the name area
text_font     = "Liberation Sans:style=Bold";  // width table below is measured for THIS font

// ---- Text width estimate (no experimental OpenSCAD features needed) ----
// Advance width of each printable ASCII character per 1 unit of text size,
// measured from Liberation Sans Bold. Characters not in the table use the
// average width. If you change text_font, the fit will only be approximate.
charset = " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~";
adv_table = [
    0.377, 0.452, 0.643, 0.754, 0.754, 1.206, 0.979, 0.323, 0.452, 0.452, 0.528, 0.792,
    0.377, 0.452, 0.377, 0.377, 0.754, 0.754, 0.754, 0.754, 0.754, 0.754, 0.754, 0.754,
    0.754, 0.754, 0.452, 0.452, 0.792, 0.792, 0.792, 0.829, 1.323, 0.979, 0.979, 0.979,
    0.979, 0.905, 0.829, 1.055, 0.979, 0.377, 0.754, 0.979, 0.829, 1.130, 0.979, 1.055,
    0.905, 1.055, 0.979, 0.905, 0.829, 0.979, 0.905, 1.280, 0.905, 0.905, 0.829, 0.452,
    0.377, 0.452, 0.792, 0.754, 0.452, 0.754, 0.829, 0.754, 0.829, 0.754, 0.452, 0.829,
    0.829, 0.377, 0.377, 0.754, 0.377, 1.206, 0.829, 0.829, 0.829, 0.829, 0.528, 0.754,
    0.452, 0.829, 0.754, 1.055, 0.754, 0.754, 0.678, 0.528, 0.379, 0.528, 0.792
];
avg_adv = 0.8;

function char_adv(c) =
    let (i = search(c, charset)[0])
    (i == undef || i == []) ? avg_adv : adv_table[i];

function sum_adv(s, i = 0) =
    i >= len(s) ? 0 : char_adv(s[i]) + sum_adv(s, i + 1);

area_w     = length - text_start - 2 * text_margin;   // width available for the name
name_w_per = sum_adv(name);                           // name width at size 1
fit_size   = name_w_per > 0 ? area_w / name_w_per : max_text_size;
text_size  = min(max_text_size, fit_size);

echo(str("Name '", name, "': text size ", text_size, " (max ", max_text_size, ")"));

$fn = 64;

// Main body + head
difference() {
    union() {
        // body: top flush at top_z, bottom at top_z - depth
        translate([0, 0, top_z - depth]) cube([length, width, depth]);
        // head: extends down to Z=0
        cube([head_len, width, head_depth]);
    }
    // notch up from the body's bottom face
    translate([notch_offset, -0.01, top_z - depth - 0.01])
        cube([notch_len, width + 0.02, notch_depth + 0.01]);
}

// Coloured block on top (X=0 to block_len), single layer
translate([0, 0, top_z - 0.01])
    cube([block_len, width, layer_h + 0.01]);

// Name, single layer, centred in the space after text_start
translate([text_start + (length - text_start) / 2, width / 2, top_z - 0.01])
    linear_extrude(layer_h + 0.01)
        text(name, size = text_size, font = text_font,
             halign = "center", valign = "center");
