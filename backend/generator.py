"""NFC antenna generator.

Generates a rectangular spiral PCB antenna as an SVG (1 SVG unit = 1 mm) and a
text report with the estimated inductance, impedance and the tuning capacitor
needed to resonate at the target frequency.

Usage:
    python generator.py --turns 4 --length 40 --width 30
    python generator.py            (prompts for the required values)
"""
import argparse
import math
import sys
from pathlib import Path

MIL = 0.0254                 # mm per mil
MU0 = 4e-7 * math.pi         # H/m
RHO_CU = 1.72e-8             # ohm*m, copper at ~20 C
OZ_TO_UM = 34.8              # copper thickness per oz/ft^2, micrometres
NFC_FREQ_MHZ = 13.56


LEAD_MM = 2.0                # straight length of the bent terminal lead, after its bend


ARC_SEGMENTS = 16            # straight pieces per 90-degree arc (≈5.6 deg each)


def round_corners(pts, radii):
    """Replace each right-angle corner pts[i] with a quarter-circle arc.

    `radii[i - 1]` is the radius for interior vertex pts[i]. Radii are used
    exactly (never shrunk, so concentric arcs stay concentric); raises
    ValueError if two arcs would need more than the straight run between them.
    """
    last = len(pts) - 1
    tangent = [0.0] + list(radii) + [0.0]      # arc length taken from each side of a vertex
    for i in range(last):
        if tangent[i] + tangent[i + 1] > math.dist(pts[i], pts[i + 1]) + 1e-9:
            raise ValueError(
                "Corner diameter too large: the rounded corners do not fit on the shorter "
                "sides. Reduce the corner diameter, the number of turns, or the opening gap.")

    out = [pts[0]]
    for i in range(1, last):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        la, lb = math.dist(a, b), math.dist(b, c)
        k = radii[i - 1]
        d1 = ((b[0] - a[0]) / la, (b[1] - a[1]) / la)
        d2 = ((c[0] - b[0]) / lb, (c[1] - b[1]) / lb)
        start = (b[0] - d1[0] * k, b[1] - d1[1] * k)
        center = (start[0] + d2[0] * k, start[1] + d2[1] * k)
        a0 = math.atan2(start[1] - center[1], start[0] - center[0])
        sweep = math.pi / 2 if d1[0] * d2[1] - d1[1] * d2[0] > 0 else -math.pi / 2
        out += [(center[0] + k * math.cos(a0 + sweep * s / ARC_SEGMENTS),
                 center[1] + k * math.sin(a0 + sweep * s / ARC_SEGMENTS))
                for s in range(ARC_SEGMENTS + 1)]
    out.append(pts[-1])
    return out


def spiral_points(length, width, turns, trace_w, spacing, opening, gap, radius, chip_inside):
    """Centerline of the spiral (top copper only). Dimensions in mm, 1 SVG unit = 1 mm.

    `length`/`width` are the outer edge of the copper, so the centerline is
    inset by half a trace width.

    The terminals sit at the middle of one side: a `length` side (top) or a
    `width` side (right), chosen by `opening`. The outermost and innermost
    loops both end straight at that middle point, aligned. Then one end bends
    with a quarter-circle of radius `gap`, which shifts it `gap` mm sideways:
      chip_inside=1: the outer end bends out of the antenna, inner end stays flat;
      chip_inside=0: the inner end bends into the coil, outer end stays flat.
    The flat end is left for a back-side jumper you route yourself, `gap` mm
    beside the bent lead. Each loop steps inward by one pitch at a corner.

    Every loop corner is an arc, and at each corner the arcs of all loops are
    concentric: the innermost loop uses `radius` and each loop further out adds
    one pitch, so neighbouring turns stay exactly one pitch apart round the bend.
    (This holds at the stepping corner too, whose common center is simply one
    pitch lower.)
    """
    # Build with sharp corners and the opening on the top edge, round every
    # corner, then rotate for the width side.
    along, across = (length, width) if opening == "length" else (width, length)
    pitch = trace_w + spacing
    x_end = along / 2
    left, top = trace_w / 2, trace_w / 2
    right, bottom = along - trace_w / 2, across - trace_w / 2
    if chip_inside:   # outer end: bend at x_end - gap, then `LEAD_MM` straight out
        pts = [(x_end - gap, top - gap - LEAD_MM), (x_end - gap, top)]
    else:
        pts = [(x_end, top)]
    for _ in range(turns):
        pts += [(right, top), (right, bottom), (left, bottom), (left, top + pitch)]
        left, top, right, bottom = left + pitch, top + pitch, right - pitch, bottom - pitch
    if chip_inside:
        pts.append((x_end, top))
    else:             # inner end: bend at x_end + gap, then `LEAD_MM` into the coil
        pts += [(x_end + gap, top), (x_end + gap, top + gap + LEAD_MM)]

    # Loop k (0 = outermost) has 4 corners of radius `radius + (turns-1-k) * pitch`.
    # The lead bend has radius `gap`, so it starts exactly at x_end and both
    # loop ends align.
    loop_radii = [radius + (turns - 1 - k) * pitch for k in range(turns) for _ in range(4)]
    radii = [gap] + loop_radii if chip_inside else loop_radii + [gap]
    pts = round_corners(pts, radii)

    if opening == "width":           # rotate 90 deg clockwise: top edge -> right edge
        pts = [(length - y, x) for x, y in pts]
    return pts


def path_length(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def check_fit(length, width, turns, pitch, trace_w, opening, gap, chip_inside):
    """Copper-to-copper inner opening of the spiral, as (along length, along width).

    Across the opening side it is bounded by the final segment (one pitch
    further in) and the far side of the innermost loop. The bent lead must sit
    at least one pitch from the flat end so a trace-width jumper keeps one
    spacing; with chip_inside=0 the inward lead must also fit in the opening.
    """
    along, across = (length, width) if opening == "length" else (width, length)
    spacing = pitch - trace_w
    inner_along = along - 2 * trace_w - 2 * (turns - 1) * pitch
    inner_across = across - 2 * trace_w - (2 * turns - 1) * pitch
    if gap < pitch:
        raise ValueError(
            f"Opening gap {gap:g} mm is too small for {trace_w / MIL:.1f} mil trace / "
            f"{spacing / MIL:.1f} mil spacing; use at least {pitch:.2f} mm.")
    need_along, need_across = spacing, spacing
    if not chip_inside:      # inward lead: clear of the far side and the opposite side
        need_along = 2 * (gap + pitch) - trace_w
        need_across = gap + LEAD_MM + spacing
    if inner_along < need_along or inner_across < need_across:
        raise ValueError(
            f"{turns} turns do not fit in {length} x {width} mm with "
            f"{trace_w / MIL:.1f} mil trace / {spacing / MIL:.1f} mil spacing. "
            "Reduce turns, trace width or spacing.")
    return (inner_along, inner_across) if opening == "length" else (inner_across, inner_along)


def inductance_h(length, width, turns, pitch, trace_w):
    """Modified Wheeler (Mohan et al.) for a spiral, using mean dimensions."""
    d_out = (length + width) / 2 * 1e-3
    d_in = max(d_out - 2 * turns * pitch * 1e-3 + (pitch - trace_w) * 1e-3, 1e-6)
    d_avg = (d_out + d_in) / 2
    rho = (d_out - d_in) / (d_out + d_in)
    k1, k2 = 2.34, 2.75      # square spiral coefficients
    return k1 * MU0 * turns ** 2 * d_avg / (1 + k2 * rho)


def resistance_ohm(len_mm, trace_w_mm, thick_um, freq_hz):
    """Returns (R_dc, R_ac) with a skin-effect correction for the conductor."""
    w, t = trace_w_mm * 1e-3, thick_um * 1e-6
    r_dc = RHO_CU * len_mm * 1e-3 / (w * t)
    skin = math.sqrt(RHO_CU / (math.pi * freq_hz * MU0))
    t_eff = skin * (1 - math.exp(-t / skin))   # effective conducting depth
    r_ac = RHO_CU * len_mm * 1e-3 / (w * t_eff)
    return r_dc, max(r_ac, r_dc)


def write_svg(path, pts, length, width, trace_w):
    pad = 1 + trace_w    # around the outline and any lead sticking out of it
    x0 = min(0, *(x for x, _ in pts)) - pad
    y0 = min(0, *(y for _, y in pts)) - pad
    vw = max(length, *(x for x, _ in pts)) + pad - x0
    vh = max(width, *(y for _, y in pts)) + pad - y0
    d = "M " + " L ".join(f"{x:.4f},{y:.4f}" for x, y in pts)
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{vw:.3f}mm" height="{vh:.3f}mm" viewBox="{x0:.3f} {y0:.3f} {vw:.3f} {vh:.3f}">
  <title>NFC antenna {length} x {width} mm, trace {trace_w / MIL:.1f} mil</title>
  <rect x="0" y="0" width="{length}" height="{width}" fill="none" stroke="#999" stroke-width="0.05" stroke-dasharray="0.5 0.5"/>
  <path d="{d}" fill="none" stroke="#b87333" stroke-width="{trace_w:.4f}" stroke-linejoin="round" stroke-linecap="square"/>
</svg>
"""
    Path(path).write_text(svg, encoding="utf-8")


def design(turns, length, width, freq=NFC_FREQ_MHZ, copper_oz=0.5, trace_mil=15,
           spacing_mil=None, opening="length", opening_gap=1.0, chip_inside=1,
           corner_diameter=2.0, chip_cap_pf=0):
    """Compute the antenna. Returns dict(pts, report, length, width, trace_w).

    Raises ValueError with a readable message for invalid or non-fitting input.
    Shared by the command line and the GUI.
    """
    if spacing_mil is None:
        spacing_mil = trace_mil
    if min(turns, length, width, freq, copper_oz, trace_mil, spacing_mil, corner_diameter, opening_gap) <= 0:
        raise ValueError("All inputs must be positive (chip capacitance may be 0).")
    if chip_cap_pf < 0:
        raise ValueError("Chip capacitance cannot be negative.")
    if opening not in ("length", "width"):
        raise ValueError("Opening must be 'length' or 'width'.")
    chip_inside = 1 if chip_inside else 0

    trace_w = trace_mil * MIL
    spacing = spacing_mil * MIL
    thick_um = copper_oz * OZ_TO_UM
    f = freq * 1e6
    pitch = trace_w + spacing

    inner_l, inner_w = check_fit(length, width, turns, pitch, trace_w, opening, opening_gap, chip_inside)
    pts = spiral_points(length, width, turns, trace_w, spacing, opening, opening_gap,
                        corner_diameter / 2, chip_inside)
    length_mm = path_length(pts)
    L = inductance_h(length, width, turns, pitch, trace_w)
    r_dc, r_ac = resistance_ohm(length_mm, trace_w, thick_um, f)
    w = 2 * math.pi * f
    xl = w * L
    z_mag = math.hypot(r_ac, xl)
    q = xl / r_ac
    c_total = 1 / (w ** 2 * L)
    c_ext = c_total - chip_cap_pf * 1e-12

    lines = [
        "NFC Antenna Report",
        "==================",
        "Inputs",
        f"  Target frequency   : {freq:g} MHz",
        f"  Turns              : {turns}",
        f"  Outer size         : {length:g} x {width:g} mm",
        f"  Copper             : {copper_oz:g} oz ({thick_um:.1f} um)",
        f"  Trace width/space  : {trace_mil:g} mil / {spacing_mil:g} mil",
        f"  Chip capacitance   : {chip_cap_pf:g} pF",
        f"  Terminals          : middle of a {opening} side, "
        + ("outer end bent out" if chip_inside else "inner end bent in")
        + f" by {opening_gap:g} mm (chip_inside={chip_inside})",
        f"  Corner arcs        : concentric, innermost diameter {corner_diameter:g} mm, "
        f"outermost diameter {corner_diameter + 2 * (turns - 1) * pitch:.3g} mm (centerline)",
        f"  Lead bend radius   : {opening_gap:g} mm (= opening gap)",
        "",
        "Geometry",
        f"  Inner opening      : {inner_l:.2f} x {inner_w:.2f} mm",
        f"  Trace length       : {length_mm:.1f} mm (excl. back-side jumper)",
        f"  Conductor area     : {trace_w * thick_um * 1e-3:.5f} mm^2 (cross-section)",
        "",
        "Electrical (at target frequency)",
        f"  Inductance L       : {L * 1e6:.3f} uH",
        f"  Resistance DC      : {r_dc * 1e3:.1f} mOhm",
        f"  Resistance AC      : {r_ac * 1e3:.1f} mOhm (skin effect)",
        f"  Reactance XL       : {xl:.2f} Ohm",
        f"  Impedance |Z|      : {z_mag:.2f} Ohm  (= {r_ac:.3f} + j{xl:.2f})",
        f"  Quality factor Q   : {q:.1f} (unloaded)",
        "",
        "Tuning",
        f"  Total C to resonate: {c_total * 1e12:.2f} pF",
        f"  External C needed  : {c_ext * 1e12:.2f} pF" + ("  (chip cap already subtracted)" if chip_cap_pf else ""),
        "",
        "Note: L is a modified-Wheeler estimate (~5-10% typical error); tune with a VNA.",
    ]
    if c_ext < 0:
        lines.insert(-2, "  WARNING: chip capacitance exceeds the required total; reduce turns.")
    return {"pts": pts, "report": "\n".join(lines) + "\n",
            "length": length, "width": width, "trace_w": trace_w}


def save(res, out):
    """Write <out>.svg and <out>.txt from a design() result. Returns both paths."""
    out = Path(out)
    svg_path, txt_path = out.with_suffix(".svg"), out.with_suffix(".txt")
    write_svg(svg_path, res["pts"], res["length"], res["width"], res["trace_w"])
    txt_path.write_text(res["report"], encoding="utf-8")
    return svg_path, txt_path


def main():
    ap = argparse.ArgumentParser(description="NFC PCB antenna generator")
    ap.add_argument("--freq", type=float, default=NFC_FREQ_MHZ, help="target frequency, MHz (default 13.56)")
    ap.add_argument("--turns", type=int, help="number of turns")
    ap.add_argument("--length", type=float, help="outer length, mm")
    ap.add_argument("--width", type=float, help="outer width, mm")
    ap.add_argument("--copper-oz", type=float, default=0.5, help="copper weight in oz (default 0.5)")
    ap.add_argument("--trace-mil", type=float, default=15, help="trace width, mil (default 15)")
    ap.add_argument("--spacing-mil", type=float, help="trace spacing, mil (default = trace width)")
    ap.add_argument("--opening", choices=["length", "width"], default="length",
                    help="side where both terminals come out: the middle of a length side "
                         "(top) or of a width side (right) (default length)")
    ap.add_argument("--opening-gap", type=float, default=1.0,
                    help="sideways offset of the bent lead from the flat end, center to center, mm (default 1)")
    ap.add_argument("--chip-inside", type=int, choices=[0, 1], default=1,
                    help="0: inner end bends into the coil, outer end stays flat; "
                         "1: outer end bends out of the antenna, inner end stays flat (default 1)")
    ap.add_argument("--corner-diameter", type=float, default=2.0,
                    help="diameter of the innermost loop's corner arc (centerline), mm; outer loops "
                         "use concentric arcs one pitch larger in radius each (default 2)")
    ap.add_argument("--chip-cap-pf", type=float, default=0, help="chip input capacitance to subtract, pF (default 0)")
    ap.add_argument("--out", default="antenna", help="output file prefix (default 'antenna')")
    a = ap.parse_args()

    def ask(val, label, cast):
        while val is None:
            try:
                val = cast(input(f"{label}: "))
            except ValueError:
                print("Invalid number.")
            except EOFError:
                sys.exit("Missing required input.")
        return val

    a.turns = ask(a.turns, "Number of turns", int)
    a.length = ask(a.length, "Outer length (mm)", float)
    a.width = ask(a.width, "Outer width (mm)", float)

    try:
        res = design(a.turns, a.length, a.width, freq=a.freq, copper_oz=a.copper_oz,
                     trace_mil=a.trace_mil, spacing_mil=a.spacing_mil, opening=a.opening,
                     opening_gap=a.opening_gap, chip_inside=a.chip_inside, corner_diameter=a.corner_diameter,
                     chip_cap_pf=a.chip_cap_pf)
    except ValueError as e:
        sys.exit(str(e))

    svg_path, txt_path = save(res, a.out)
    print(res["report"])
    print(f"Wrote {svg_path} and {txt_path}")


if __name__ == "__main__":
    main()
