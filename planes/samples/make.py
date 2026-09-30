"""Build the design-test samples from samples/base.json (a real capture): long names, a
landing long-haul, no route, just departed, an empty sky, a plane at the edge, a crowd."""
import copy
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import planes as P  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "base.json")) as f:
    base = json.load(f)


def plane(cs, lat, lon, alt, gs, track, reg="", typ="B738"):
    d, b = P.distance_bearing(P.HOME_LAT, P.HOME_LON, lat, lon)
    return dict(hex=cs.lower(), callsign=cs, reg=reg, name=cs, type=typ, alt=alt, gs=gs,
                track=track, rate=0, lat=lat, lon=lon, dist=d, brg=b)


def route(fc, fcity, fll, tc, tcity, tll, airline=None):
    return {"airline": airline, "flight": None, "from": fc, "from_city": fcity, "from_ll": fll,
            "to": tc, "to_city": tcity, "to_ll": tll}


def with_feature(p, r, model, extra=None):
    d = copy.deepcopy(base)
    d["planes"] = [p] + [q for q in d["planes"] if q["dist"] > p["dist"]] + (extra or [])
    d["routes"][p["callsign"]] = r
    d["frames"][p["hex"]] = {"model": model}
    return d


YYZ, YTZ = [43.6777, -79.6248], [43.6275, -79.3962]
out = {
    "long_names": with_feature(
        plane("ROU1984", P.HOME_LAT + 0.02, P.HOME_LON + 0.03, 41000, 560, 290),
        route("FRA", "Frankfurt am Main", [50.03, 8.57], "YAM", "Sault Ste. Marie", [46.48, -84.51]),
        "Airbus A330"),
    "landing_long_haul": with_feature(
        plane("CPA826", P.HOME_LAT - 0.02, P.HOME_LON - 0.07, 1200, 150, 240),
        route("HKG", "Hong Kong", [22.31, 113.91], "YYZ", "Toronto", YYZ),
        "Boeing 777"),
    "no_route": with_feature(
        plane("CGYNJ", P.HOME_LAT + 0.006, P.HOME_LON - 0.006, 3500, 210, 45, reg="C-GYNJ", typ="B350"),
        None, "Beechcraft King Air B350"),
    "just_departed": with_feature(
        plane("WJA248", 43.70, -79.58, 300, 150, 60),
        route("YYZ", "Toronto", YYZ, "YHZ", "Halifax", [44.88, -63.51]),
        "Boeing 737"),
    "empty": dict(planes=[], routes={}, frames={}),
    "edge": with_feature(
        plane("JZA7802", 43.66, -79.14, 9000, 300, 80),
        route("YTZ", "Toronto", YTZ, "YOW", "Ottawa", [45.32, -75.67]),
        "De Havilland DHC-8"),
}
random.seed(4)
crowd = [plane("X%03d" % i, P.HOME_LAT + random.uniform(-.25, .25), P.HOME_LON + random.uniform(-.4, .3),
               random.choice([1500, 6000, 12000, 36000]), 300, random.uniform(0, 360)) for i in range(40)]
out["crowded"] = with_feature(
    plane("ACA1", P.HOME_LAT + 0.001, P.HOME_LON + 0.001, 2500, 160, 240),
    route("NRT", "Tokyo", [35.77, 140.39], "YYZ", "Toronto", YYZ), "Boeing 787", extra=crowd)
def day_curve(seed, upto=None):
    """A plausible Toronto day: quiet overnight, morning bank, midday lull, evening peak."""
    rnd = random.Random(seed)

    def shape(h):
        return (2 + 15 * math.exp(-((h - 8.5) / 1.6) ** 2) + 9 * math.exp(-((h - 13) / 2.5) ** 2)
                + 19 * math.exp(-((h - 18.6) / 1.9) ** 2))

    n = 288 if upto is None else upto
    return [max(0, int(round(shape(i / 12.0) + rnd.gauss(0, 1.6)))) for i in range(n)] + [None] * (288 - n)


traffic = {"2026-09-23": day_curve(1), "2026-09-24": day_curve(2, upto=16 * 12 + 9)}
for name, d in out.items():
    d["traffic"] = traffic
    d["time"] = "2026-09-24 16:45"
    with open(os.path.join(HERE, name + ".json"), "w") as f:
        json.dump(d, f, indent=1)
print(" ".join(out))
