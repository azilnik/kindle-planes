"""Frame insert for the Kindle Paperwhite 10th gen (PW4) in an IKEA RÖDALM frame.

One printed piece, printed face-down (the front is the visible mat):
  - a mat window centred in the frame, with a 45° mat bevel;
  - behind it a friction-fit pocket for the Kindle (landscape, port/logo edge on the left);
  - room beside the charging port for the plug, the cable leaving out the back;
  - a finger notch to lift the Kindle out.

The Kindle's screen sits off-centre in its body (the logo bezel is deeper), and the plug
needs room on that side too, so the screen ends up off-centre in the frame. The window is
therefore the largest rectangle that is centred in the frame AND inside the screen; the
strip of screen it hides is reported as the `safe` area for planes/config.json, so the
display lays itself out in exactly the visible part.

Values marked MEASURE are estimates: confirm with a ruler/calipers before printing.
Print face-down in PETG (PLA springs creep), no brim or skirt. Fits an A1 mini bed.
Run:  uv run --python 3.12 --with manifold3d --with numpy --with trimesh --with pillow \\
          --with networkx --with lxml python insert.py [rodalm13x18|rodalm21x30]
"""

import os
import sys

import numpy as np
from manifold3d import CrossSection, Manifold

HERE = os.path.dirname(os.path.abspath(__file__))

FRAMES = {
    # IKEA RÖDALM 13x18 cm, landscape. Its front opening is the whole rebate, so the printed
    # face IS the mat. A normal plug doesn't fit beside the port: use a flat FPC micro-USB
    # extension (FPV-drone style; ~5 mm past the port, ribbon folds back and slips out under
    # the back board).
    "rodalm13x18": dict(rebate_l=180.0, rebate_w=131.0, ikea_mat=False, plug_room=5.5,
                        ikea_opening_l=0, ikea_opening_w=0),
    # IKEA RÖDALM 21x30 cm, landscape: printed inner mat behind IKEA's paper mat (double mat),
    # a rim drops into the IKEA opening to centre it; any right-angle plug fits beside it.
    "rodalm21x30": dict(rebate_l=300.0, rebate_w=210.0, ikea_mat=True, plug_room=0.0,
                        ikea_opening_l=170.0, ikea_opening_w=120.0),   # MEASURE the opening
}

P = dict(
    kindle_l=167.0,          # Amazon spec
    kindle_w=116.0,
    kindle_t=8.2,
    screen_l=122.4,          # active area: 1448 px at 300 ppi
    screen_w=90.7,           # 1072 px
    bezel_port=26.0,         # MEASURE: port/logo edge of the body to the screen
    bezel_top=18.6,          # MEASURE: opposite edge to the screen
    port_from_edge=58.0,     # MEASURE: along the port edge, top (as mounted) to USB centre
    fit=0.25,                # pocket clearance per side
    rebate_fit=0.5,          # insert clearance to the frame per side
    window_overlap=1.5,      # mat covers this much of the screen edge; absorbs bezel estimate error
    ikea_mat_t=1.4,          # MEASURE (21x30 only)
    face_t=1.6,              # mat thickness in front of the Kindle
    rim_h=0.8,
    bevel=1.2,
    plug_notch_w=14.0,
    finger_notch=22.0,
    # Holding it all without a back board (print in PETG: PLA springs creep)
    spring_len=30.0,         # side spring tabs: rise from the mat plate, free at the back
    spring_t=1.8,            # tab thickness
    spring_gap=1.0,          # slot behind the tab
    spring_bump=1.2,         # outward bump -> 0.7 mm interference with rebate_fit 0.5
    lip_len=24.0,            # snap lips on the long sides of the pocket
    lip_over=1.0,            # how far a lip hangs over the Kindle's back edge
    lip_t=1.2,
    back_fit=0.3,            # pocket depth over the Kindle's thickness
    px_per_mm=1448 / 122.4,
)


def box(lx, ly, lz, cx=0.0, cy=0.0, z0=0.0):
    return Manifold.cube((lx, ly, lz), center=True).translate((cx, cy, z0 + lz / 2))


def layout(p, f):
    """Where things sit, in mm, origin at the frame centre, +x away from the port."""
    if f["ikea_mat"]:
        insert_l, insert_w = 178.0, 128.0     # A1 mini bed
    else:
        insert_l = f["rebate_l"] - 2 * p["rebate_fit"]
        insert_w = f["rebate_w"] - 2 * p["rebate_fit"]
    pl, pw = p["kindle_l"] + 2 * p["fit"], p["kindle_w"] + 2 * p["fit"]
    # Ideal: screen centred. Screen centre is (bezel_port - bezel_top)/2 from body centre,
    # toward the far side, so the body sits that far toward the port...
    body_cx = -(p["bezel_port"] - p["bezel_top"]) / 2.0
    # ...unless the port side then lacks room for the plug: push the body away from it.
    port_wall = insert_l / 2 + (body_cx - pl / 2)
    need = f["plug_room"]
    if not f["ikea_mat"] and port_wall < need:
        body_cx += need - port_wall
    screen_cx = body_cx + (p["bezel_port"] - p["bezel_top"]) / 2.0
    s0, s1 = screen_cx - p["screen_l"] / 2, screen_cx + p["screen_l"] / 2
    # Largest window centred on the frame and inside the screen (minus the overlap)
    half = min(-s0, s1) - p["window_overlap"]
    wl = 2 * half
    ww = p["screen_w"] - 2 * p["window_overlap"]
    # Visible part of the screen in landscape canvas pixels (canvas x=0 at the port side)
    k = p["px_per_mm"]
    safe = [round((-half - s0) * k), round(p["window_overlap"] * k),
            round((half - s0) * k), round((p["screen_w"] - p["window_overlap"]) * k)]
    return dict(insert_l=insert_l, insert_w=insert_w, pl=pl, pw=pw, body_cx=body_cx,
                screen_cx=screen_cx, wl=wl, ww=ww, safe=safe,
                port_wall=insert_l / 2 + (body_cx - pl / 2),
                far_wall=insert_l / 2 - (body_cx + pl / 2), side_wall=(insert_w - pw) / 2)


def wedge(x0, x1, y_wall, inward, z_catch, z_back, overhang):
    """A ramped lip along x: flat catch face at z_catch, sloping to nothing at z_back."""
    y_in = y_wall + inward * overhang
    pts = [(x, y, z) for x in (x0, x1) for (y, z) in
           ((y_wall, z_catch), (y_in, z_catch), (y_wall, z_back))]
    return Manifold.hull_points(pts)


def build(p, f, L):
    rim = f["ikea_mat"]
    rim_h = p["rim_h"] if rim else 0.0
    front = rim_h + p["face_t"]
    z_catch = front + p["kindle_t"] + p["back_fit"]      # the Kindle's back rests here
    body_t = p["face_t"] + p["kindle_t"] + p["back_fit"] + p["lip_t"]
    back = rim_h + body_t
    il, iw = L["insert_l"], L["insert_w"]
    solid = box(il, iw, body_t, z0=rim_h)
    if rim:
        solid = solid + box(f["ikea_opening_l"] - 0.6, f["ikea_opening_w"] - 0.6, rim_h)

    # Window with a mat bevel widening toward the viewer
    bev = min(p["bevel"], front)
    wl, ww = L["wl"], L["ww"]
    sec = CrossSection.square((wl + 2 * bev, ww + 2 * bev), center=True)
    bevel = Manifold.extrude(sec, bev, scale_top=(wl / (wl + 2 * bev), ww / (ww + 2 * bev)))
    solid = solid - bevel.translate((0, 0, -0.001)) - box(wl, ww, front + 0.02, z0=-0.01)

    # Kindle pocket, open to the back (the Kindle presses in from behind)
    cx, pl, pw = L["body_cx"], L["pl"], L["pw"]
    solid = solid - box(pl, pw, body_t + 1, cx=cx, z0=front)

    # Snap lips: ramped overhangs on the long sides, each on a flexible tab so it can
    # spring outward as the Kindle goes in, then snap over its back edge
    for sx in (-1, 1):
        x0 = cx + sx * (pl / 4) - p["lip_len"] / 2
        for sy in (-1, 1):
            y_wall = sy * pw / 2
            solid = solid + wedge(x0, x0 + p["lip_len"], y_wall, -sy, z_catch, back, p["lip_over"])
            slot_y = y_wall + sy * (p["spring_t"] + p["spring_gap"] / 2)
            solid = solid - box(p["lip_len"] + 4, p["spring_gap"], back - front - 1.5,
                                cx=x0 + p["lip_len"] / 2, cy=slot_y, z0=front + 1.5 + 0.01)
            for ex in (x0 - 2, x0 + p["lip_len"] + 2):
                solid = solid - box(p["spring_gap"], p["spring_t"] + p["spring_gap"], back - front - 1.5,
                                    cx=ex, cy=y_wall + sy * (p["spring_t"] + p["spring_gap"]) / 2,
                                    z0=front + 1.5 + 0.01)

    # Side springs: tabs in the long walls, rooted in the mat plate, free at the back, with
    # a bump that presses on the frame's rebate walls. None on the short ends: their bumps
    # would push the length past the 180 mm A1 mini bed.
    h = back - front
    n = p["spring_len"]
    for sgn in (-1, 1):
        out = sgn * iw / 2
        slot_c = out - sgn * (p["spring_t"] + p["spring_gap"] / 2)
        for along in (-il / 4, il / 4):
            solid = solid - box(n, p["spring_gap"], h + 0.1, cx=along, cy=slot_c, z0=front)
            for e in (along - n / 2, along + n / 2):
                solid = solid - box(p["spring_gap"], p["spring_t"] + p["spring_gap"] + 0.2, h + 0.1,
                                    cx=e, cy=out - sgn * (p["spring_t"] + p["spring_gap"]) / 2, z0=front)
            solid = solid + box(n - 4, p["spring_bump"], 3, cx=along, cy=out + sgn * p["spring_bump"] / 2, z0=back - 3)

    port_y = pw / 2 - p["port_from_edge"]
    # Plug notch beside the port, open to the side and back
    edge = cx - pl / 2
    solid = solid - box(40, p["plug_notch_w"], body_t + 1, cx=edge - 20 + 0.5, cy=port_y, z0=front)

    # Finger notch on the far edge: push the Kindle out from the side
    far = cx + pl / 2
    solid = solid - box(14, p["finger_notch"], body_t + 1, cx=far + 5, z0=front + 1.2)
    return solid, rim_h + body_t


def export(solid, stem):
    import trimesh
    m = solid.to_mesh()
    mesh = trimesh.Trimesh(vertices=np.asarray(m.vert_properties)[:, :3], faces=np.asarray(m.tri_verts))
    mesh.export(stem + ".stl")
    mesh.export(stem + ".3mf")
    return mesh


def preview(p, f, L, path, scale=5):
    """Front view as seen through the frame, with the hidden Kindle and screen ghosted in."""
    from PIL import Image, ImageDraw
    fl, fw = f["rebate_l"], f["rebate_w"]
    W, H = int((fl + 40) * scale), int((fw + 40) * scale)
    im = Image.new("RGB", (W, H), (196, 170, 132))      # birch-ish frame
    d = ImageDraw.Draw(im)

    def rect(cx, cy, lx, ly, **kw):
        d.rectangle((W / 2 + (cx - lx / 2) * scale, H / 2 - (cy + ly / 2) * scale,
                     W / 2 + (cx + lx / 2) * scale, H / 2 - (cy - ly / 2) * scale), **kw)

    rect(0, 0, fl, fw, fill=(248, 247, 243))                                  # mat
    rect(L["body_cx"], 0, p["kindle_l"], p["kindle_w"], outline=(215, 212, 205), width=2)   # hidden body
    rect(L["screen_cx"], 0, p["screen_l"], p["screen_w"], outline=(230, 190, 120), width=2)  # full screen
    rect(0, 0, L["wl"], L["ww"], fill=(222, 224, 219), outline=(120, 120, 118), width=2)     # window
    port_y = L["pw"] / 2 - p["port_from_edge"]
    rect(L["body_cx"] - p["kindle_l"] / 2 - 3, port_y, 6, 10, fill=(240, 120, 60))          # plug
    im.save(path)


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "rodalm13x18"
    f = FRAMES[name]
    L = layout(P, f)
    solid, thick = build(P, f, L)
    mesh = export(solid, os.path.join(HERE, "insert-" + name))
    preview(P, f, L, os.path.join(HERE, "preview-" + name + ".png"))
    print("%s: %.0f x %.0f x %.1f mm, %.0f cm3, watertight %s" % (
        name, L["insert_l"], L["insert_w"], thick, mesh.volume / 1000, mesh.is_watertight))
    print("window %.1f x %.1f mm (screen %.1f x %.1f); walls: port %.1f, far %.1f, sides %.1f mm" % (
        L["wl"], L["ww"], P["screen_l"], P["screen_w"], L["port_wall"], L["far_wall"], L["side_wall"]))
    print('config.json  "safe": %s' % L["safe"])
