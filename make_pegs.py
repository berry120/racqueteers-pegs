#!/usr/bin/env python3
"""
Generate name pegs: for each name, render an STL with OpenSCAD and build a
Bambu Studio project (.3mf) by swapping the mesh into a template project.

The template keeps everything else: printer/filament/process settings, tree
supports, and the pause / colour-change stop at the colour layer.

STL files go in one folder and .3mf files in another.

Usage:
    python make_pegs.py --template template.3mf --scad peg.scad Alice Bob "Mary-Jane"
    python make_pegs.py --template template.3mf --scad peg.scad --names-file names.txt --sync

With --sync, any .stl / .3mf in the output folders that no longer matches a
name in the list is deleted, so the folders always mirror the list. (This only
happens if every name built successfully.)

Requires: Python 3.8+ and OpenSCAD (on PATH, or pass --openscad PATH).
"""
import argparse
import hashlib
import re
import struct
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

MODEL_SETTINGS = "Metadata/model_settings.config"
MIN_LEGIBLE_SIZE = 4.0  # mm; warn below this text size


# --------------------------------------------------------------------------- STL
def parse_ascii_stl(path):
    """Return (vertices, triangles) with duplicate vertices merged."""
    index = {}
    verts = []
    tris = []
    cur = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("vertex"):
                _, x, y, z = line.split()
                p = (float(x), float(y), float(z))
                key = (round(p[0], 5), round(p[1], 5), round(p[2], 5))
                if key not in index:
                    index[key] = len(verts)
                    verts.append(p)
                cur.append(index[key])
                if len(cur) == 3:
                    if len(set(cur)) == 3:          # skip degenerate triangles
                        tris.append(tuple(cur))
                    cur = []
    if not tris:
        raise RuntimeError(f"No triangles read from {path} (is it an ASCII STL?)")
    return verts, tris


def write_binary_stl(path, verts, tris):
    """Write a compact binary STL (about 5x smaller than ASCII)."""
    with open(path, "wb") as f:
        f.write(b"binary STL written by make_pegs.py".ljust(80, b" "))  # must not start with 'solid'
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            p0, p1, p2 = verts[a], verts[b], verts[c]
            ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
            vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            ln = (nx * nx + ny * ny + nz * nz) ** 0.5
            if ln > 0:
                nx, ny, nz = nx / ln, ny / ln, nz / ln
            f.write(struct.pack("<12fH", nx, ny, nz, *p0, *p1, *p2, 0))


def bbox(verts):
    xs, ys, zs = zip(*verts)
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


def signed_volume(verts, tris):
    v = 0.0
    for a, b, c in tris:
        ax, ay, az = verts[a]
        bx, by, bz = verts[b]
        cx, cy, cz = verts[c]
        v += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)) / 6.0
    return v


# --------------------------------------------------------------------------- template
MESH_RE = re.compile(r"<mesh>.*?</mesh>", re.S)
VERT_RE = re.compile(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"/>')


def find_object_model(zf):
    names = [n for n in zf.namelist() if n.startswith("3D/Objects/") and n.endswith(".model")]
    if len(names) != 1:
        raise RuntimeError(f"Expected exactly one object model in template, found: {names}")
    return names[0]


def template_mesh_extent(text):
    vs = [tuple(map(float, m)) for m in VERT_RE.findall(text)]
    (x0, x1), (y0, y1), (z0, z1) = bbox(vs)
    return (x1 - x0, y1 - y0, z1 - z0)


def fmt(v):
    s = format(v, ".7g")
    return "0" if s in ("-0", "-0.0") else s


def build_mesh_xml(verts, tris, centre):
    cx, cy, cz = centre
    out = ["<mesh>", "    <vertices>"]
    for x, y, z in verts:
        out.append(f'     <vertex x="{fmt(x - cx)}" y="{fmt(y - cy)}" z="{fmt(z - cz)}"/>')
    out.append("    </vertices>")
    out.append("    <triangles>")
    for a, b, c in tris:
        out.append(f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>')
    out.append("    </triangles>")
    out.append("   </mesh>")
    return "\n".join(out)


def make_3mf(template, out_path, verts, tris, display_name):
    with zipfile.ZipFile(template) as zin:
        obj_name = find_object_model(zin)
        obj_text = zin.read(obj_name).decode("utf-8")
        t_size = template_mesh_extent(obj_text)

        (x0, x1), (y0, y1), (z0, z1) = bbox(verts)
        size = (x1 - x0, y1 - y0, z1 - z0)
        if any(abs(a - b) > 0.01 for a, b in zip(size, t_size)):
            raise RuntimeError(
                "New part's bounding box %s differs from the template's %s. The template's "
                "placement and colour-change height would no longer match - rebuild the template."
                % (tuple(round(s, 3) for s in size), tuple(round(s, 3) for s in t_size))
            )
        centre = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)

        new_obj = MESH_RE.sub(lambda m: build_mesh_xml(verts, tris, centre), obj_text, count=1)

        settings = zin.read(MODEL_SETTINGS).decode("utf-8")
        settings = re.sub(r'face_count="\d+"', f'face_count="{len(tris)}"', settings)
        safe = escape(display_name, {'"': "&quot;"})
        settings = re.sub(r'(<metadata key="name" value=")[^"]*(")', rf"\g<1>{safe}\g<2>", settings)

        with zipfile.ZipFile(out_path, "w") as zout:
            for info in zin.infolist():       # keep original order and compression
                data = zin.read(info.filename)
                if info.filename == obj_name:
                    data = new_obj.encode("utf-8")
                elif info.filename == MODEL_SETTINGS:
                    data = settings.encode("utf-8")
                zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                zi.compress_type = info.compress_type
                zi.external_attr = info.external_attr
                zout.writestr(zi, data)


# --------------------------------------------------------------------------- OpenSCAD
def render_stl(openscad, scad, name, stl_path):
    esc = name.replace("\\", "\\\\").replace('"', '\\"')
    cmd = [openscad, "-D", f'name="{esc}"', "-o", str(stl_path), str(scad)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not Path(stl_path).exists():
        raise RuntimeError(f"OpenSCAD failed for {name!r}:\n{r.stderr}")
    m = re.search(r"text size ([0-9.]+)", r.stderr)
    return float(m.group(1)) if m else None


# --------------------------------------------------------------------------- names
def read_names(path):
    """One name per line. Blank lines and lines starting with # are ignored."""
    names = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.append(line)
    return names


def unique(names):
    seen, out = set(), []
    for n in names:
        if n in seen:
            print(f"note: duplicate name {n!r} ignored")
            continue
        seen.add(n)
        out.append(n)
    return out


def slug(name):
    """ASCII-only, filesystem-safe file stem (José -> Jose), so the same file names work
    on Windows, macOS and Linux. Names with no ASCII letters at all get a hash instead."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9.-]+", "_", ascii_name).strip("_.")[:80]
    return s or f"name-{hashlib.sha1(name.encode('utf-8')).hexdigest()[:6]}"


def assign_filenames(names):
    """Safe file stem per name. If two different names would share a stem, every
    one of them gets a short hash, so the result doesn't depend on list order."""
    slugs = {n: slug(n) for n in names}
    counts = {}
    for s in slugs.values():
        counts[s.lower()] = counts.get(s.lower(), 0) + 1
    out = {}
    for n, s in slugs.items():
        out[n] = f"{s}-{hashlib.sha1(n.encode('utf-8')).hexdigest()[:6]}" if counts[s.lower()] > 1 else s
    return out


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="names to put on the pegs")
    ap.add_argument("--names-file", help="text file with one name per line")
    ap.add_argument("--template", required=True, help="Bambu Studio template .3mf")
    ap.add_argument("--scad", default="peg.scad", help="OpenSCAD file (default: peg.scad)")
    ap.add_argument("--stl-dir", default="stl", help="output folder for .stl files (default: stl)")
    ap.add_argument("--3mf-dir", dest="mf_dir", default="3mf", help="output folder for .3mf files (default: 3mf)")
    ap.add_argument("--openscad", default="openscad", help="path to the openscad executable")
    ap.add_argument("--sync", action="store_true",
                    help="delete .stl/.3mf files in the output folders that are not in the name list")
    args = ap.parse_args()

    names = list(args.names)
    if args.names_file:
        names += read_names(args.names_file)
    names = unique(names)
    if not names and not args.names_file:
        ap.error("give at least one name (or --names-file)")

    stl_dir, mf_dir = Path(args.stl_dir), Path(args.mf_dir)
    stl_dir.mkdir(parents=True, exist_ok=True)
    mf_dir.mkdir(parents=True, exist_ok=True)

    stems = assign_filenames(names)
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        # A peg with a blank name shows how many triangles the model has without any text.
        # A real name must add to that, otherwise the font had none of its characters.
        render_stl(args.openscad, args.scad, " ", Path(tmp) / "blank.stl")
        blank_tris = len(parse_ascii_stl(Path(tmp) / "blank.stl")[1])
        for name in names:
            stem = stems[name]
            try:
                size = render_stl(args.openscad, args.scad, name, Path(tmp) / "peg.stl")
                verts, tris = parse_ascii_stl(Path(tmp) / "peg.stl")
                if len(tris) <= blank_tris:
                    raise RuntimeError("no text was rendered - the font probably has none of these characters")
                write_binary_stl(stl_dir / f"{stem}.stl", verts, tris)
                make_3mf(args.template, mf_dir / f"{stem}.3mf", verts, tris, name)
                note = ""
                if size is not None:
                    note = f"  text size {size:.1f} mm"
                    if size < MIN_LEGIBLE_SIZE:
                        note += f"  ** WARNING: below {MIN_LEGIBLE_SIZE} mm, may be hard to read **"
                print(f"OK    {name!r} -> {stem}.stl, {stem}.3mf{note}")
            except Exception as e:                   # keep going with the other names
                failed += 1
                print(f"FAIL  {name!r}: {e}", file=sys.stderr)

    if failed:
        print(f"{failed} name(s) failed; not removing any existing files.", file=sys.stderr)
        sys.exit(1)

    if args.sync:
        keep_stl = {f"{s}.stl" for s in stems.values()}
        keep_mf = {f"{s}.3mf" for s in stems.values()}
        for folder, pattern, keep in ((stl_dir, "*.stl", keep_stl), (mf_dir, "*.3mf", keep_mf)):
            for p in sorted(folder.glob(pattern)):
                if p.name not in keep:
                    p.unlink()
                    print(f"REMOVED {p}")


if __name__ == "__main__":
    main()
