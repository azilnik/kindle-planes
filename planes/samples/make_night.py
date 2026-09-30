"""Synthetic day of Toronto traffic, sampled once a minute like the Kindle records it,
for previewing the night constellation: samples/night.json."""
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
YYZ, YTZ = (43.6777, -79.6248), (43.6275, -79.3962)
rnd = random.Random(7)


def walk(lat, lon, track, kmin, n):
    pts = []
    for _ in range(n):
        pts.append([round(lat, 4), round(lon, 4)])
        a = math.radians(track)
        lat += kmin * math.cos(a) / 110.57
        lon += kmin * math.sin(a) / (111.32 * math.cos(math.radians(lat)))
    return pts


def toward(dest, bearing_in, start_km, kmin, jitter):
    # start start_km out along the reciprocal of the final course, fly the course in
    back = math.radians(bearing_in + 180)
    lat = dest[0] + start_km * math.cos(back) / 110.57 + rnd.gauss(0, jitter)
    lon = dest[1] + start_km * math.sin(back) / (111.32 * math.cos(math.radians(dest[0]))) + rnd.gauss(0, jitter)
    phase = rnd.random() * kmin
    return walk(lat, lon, bearing_in + rnd.gauss(0, 1.5), kmin, int(start_km / kmin))[:] if phase else []


pts, hexes = [], []
for i in range(520):
    kind = rnd.random()
    if kind < 0.42:     # YYZ west-flow arrivals on the long final over the city
        seg = toward(YYZ, 237, 60 + rnd.random() * 10, 5.5 + rnd.random() * 2, 0.012)
    elif kind < 0.55:   # downwind legs feeding the final, north and south of the city
        side = rnd.choice((-1, 1))
        seg = walk(43.80 + side * 0.02 if side > 0 else 43.60, -79.95, 67, 7 + rnd.random(), 11)
    elif kind < 0.70:   # YYZ departures climbing out and turning
        seg = walk(YYZ[0], YYZ[1], rnd.choice((240, 300, 20, 90, 150)) + rnd.gauss(0, 8), 6 + rnd.random() * 3, 9)
    elif kind < 0.82:   # Porter into YTZ along the shore from the east
        seg = toward(YTZ, 262, 45, 5 + rnd.random(), 0.006)
    else:               # high overflights
        lat, lon = 43.4 + rnd.random() * 0.6, -80.1
        seg = walk(lat, lon, 60 + rnd.random() * 60, 12 + rnd.random() * 3, 10)
    pts.extend(seg)
    hexes.append("%06x" % i)
with open(os.path.join(HERE, "night.json"), "w") as f:
    json.dump({"planes": [], "routes": {}, "frames": {}, "tracks": {"day": "2026-09-24", "pts": pts, "hexes": hexes}}, f)
print(len(pts), "points,", len(hexes), "flights")
