"""Build planes/shore.json for a new home: the shoreline of one lake from Natural Earth
(10 m), clipped to a box around home. The map fills the water side of the line.
Usage: shore.py "Lake Ontario" LAT LON [half_degrees]   (default box: +-0.6 deg)

Only lakes for now. For a sea coast, write shore.json by hand: a list of rings, each a
list of [lon, lat] points running along the coast with the water on the right."""
import json
import os
import sys
import urllib.request

URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_lakes.geojson"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "planes", "shore.json")

name, lat, lon = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
half = float(sys.argv[4]) if len(sys.argv) > 4 else 0.6
with urllib.request.urlopen(URL) as r:
    lakes = json.load(r)["features"]
lake = next((f for f in lakes if f["properties"].get("name") == name), None)
if not lake:
    sys.exit("no lake called %r in Natural Earth" % name)
ring = lake["geometry"]["coordinates"][0]


def inside(p):
    return abs(p[0] - lon) <= half and abs(p[1] - lat) <= half


# Rotate the ring so it starts outside the box, then keep each run of points inside it
start = next((i for i, p in enumerate(ring) if not inside(p)), 0)
ring = ring[start:] + ring[:start]
runs, cur = [], []
for p in ring:
    if inside(p):
        cur.append([round(p[0], 4), round(p[1], 4)])
    elif cur:
        runs.append(cur)
        cur = []
if cur:
    runs.append(cur)
with open(OUT, "w") as f:
    json.dump(runs, f)
print("%s: %d shoreline runs, %d points -> %s" % (name, len(runs), sum(map(len, runs)), OUT))
