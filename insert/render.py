"""Shaded 3D views of the insert (painter's algorithm on a finely subdivided mesh, so
large faces can't sort wrong). Usage: render.py insert-rodalm13x18.stl out.png"""
import sys

import numpy as np
import trimesh
from PIL import Image, ImageDraw

mesh = trimesh.load(sys.argv[1])
v, f = trimesh.remesh.subdivide_to_size(mesh.vertices, mesh.faces, max_edge=2.5)
views = [("Front: the mat you see", (-35, 25), True), ("Back: pocket, snap lips, side springs", (-35, 25), False)]
W, H, S = 900, 620, 3.9
out = Image.new("RGB", (W * 2, H), (255, 255, 255))
for i, (title, (az, el), front) in enumerate(views):
    V = v.copy()
    if front:
        V[:, 2] = -V[:, 2]
    a, e = np.radians(az), np.radians(el)
    Rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, np.cos(e - np.pi / 2), -np.sin(e - np.pi / 2)], [0, np.sin(e - np.pi / 2), np.cos(e - np.pi / 2)]])
    P = V @ Rz.T @ Rx.T
    tris = P[f]
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.linalg.norm(n, axis=1)[:, None] + 1e-12
    visible = n[:, 2] > 0
    light = np.array([-0.4, 0.5, 0.75])
    light /= np.linalg.norm(light)
    shade = 0.35 + 0.65 * np.clip(n @ light, 0, 1)
    order = np.argsort(tris[:, :, 2].mean(axis=1))
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for k in order:
        if not visible[k]:
            continue
        pts = [(W / 2 + x * S, H / 2 - y * S) for x, y, _ in tris[k]]
        c = int(235 * shade[k])
        d.polygon(pts, fill=(c, c, int(c * 0.97)))
    d.text((16, 12), title, fill=(40, 40, 40))
    out.paste(img, (i * W, 0))
out.save(sys.argv[2])
print(sys.argv[2])
