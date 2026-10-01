#!/usr/bin/env python3
"""The sky frame: everything above the house. The sky as you'd see it lying on the lawn
looking up (zenith in the middle, north up, east on the left), with the nearest weather
balloon, the ISS and fresh Starlink trains, the Moon, planets and stars on it, a
headline for the one thing worth looking up for, and a ladder of how far away each is.

Data: satellite orbits from CelesTrak once a day, and the balloon from SondeHub around the
twice-daily launches (Buffalo's, from Toronto). Wi-Fi goes on only for those. The Sun, Moon, planets and
stars are computed on the device, so the sky still draws with no network at all.

Preview:  python planes/sky.py --sample planes/samples/sky/night.json --out out/sky.png
Run:      python planes/sky.py   (run.sh starts it when config.json says "frame": "sky")
"""

import argparse
import calendar
import csv
import io
import json
import math
import os
import time

import astro
import icons
import loop
import requests
from PIL import Image, ImageChops, ImageDraw

import planes as P

HERE = os.path.dirname(os.path.abspath(__file__))
KM_PER_LY = 9.4607e12
with open(os.path.join(HERE, "stars", "stars.json")) as _f:
    SKY = json.load(_f)
# The bold style's type: InterDisplay-Bold for headlines and numbers, Inter-Bold for names
# IBM Plex Serif for headlines and numbers, Plex Sans for names: technical and bookish at
# once, and its blunt serifs hold up on e-ink where fine ones break apart
TF = dict(head="IBMPlexSerif-Bold.ttf", num="IBMPlexSerif-Bold.ttf", name="IBMPlexSans-Bold.ttf",
          light="IBMPlexSans-SemiBold.ttf", scale=1.0)


def face(role, size):
    return P.font(TF[role], int(round(size * TF["scale"])))


def px(size):
    return int(round(size * TF["scale"]))


# Read from across a kitchen: nothing under 34 px (3 mm on the panel)
LABEL = face("name", 44)
BLABEL = face("name", 52)
RUNG = face("name", 40)
CAPS = face("name", 34)
SMALL = face("name", 34)
KM = face("light", 34)
NOTE = face("light", 34)
COMPASS = face("name", 46)
NUM = face("num", 104)
SKY_PANEL_W = 500
# Things down to this far below the horizon show outside the dome as ghosts
BELOW = 30
# Always a dark page, day and night, and light is importance: each step up the panel's 16
# grays pulls the eye harder. The one thing worth looking up for is white; everything else
# in the sky a step down; the text that supports it below that; structure (the horizon,
# rails, constellation lines) recedes, thick but dimmer. E-ink's black is a dark gray, so
# the bottom half of the range sinks into it: every level sits in the top half. Multiples
# of 17 are the panel's own levels, so none of them get rounded.
HERO, THING, SOFT, FRAME, GROUND = 255, 238, 204, 153, 0


# ---------- where things are ----------

def dome_xy(el, az):
    """The sky as a map seen from above, like the planes map: straight overhead at the
    center, the horizon at the rim, and the direction you face (config "heading") at the
    top, with your left on the left. Not mirrored as a chart held overhead would be: a map
    is what people already read, and forward is up in both frames."""
    r = DOME_R * (90 - el) / 90
    a = math.radians(az - P.HEADING)
    return DOME_X + r * math.sin(a), DOME_Y - r * math.cos(a)


def seen_from_home(lat, lon, alt_km):
    """Elevation, azimuth and straight-line km to something at a height, allowing for the
    curve of the Earth (it drops 1.3 km over the horizon at the balloon's 130 km)."""
    dist, brg = P.distance_bearing(P.HOME_LAT, P.HOME_LON, lat, lon)
    rise = alt_km - dist * dist / (2 * 6371)
    return math.degrees(math.atan2(rise, max(dist, 0.01))), brg, math.hypot(dist, alt_km)


def mag_limit(sun_el):
    """Faintest star worth drawing: none in daylight, down to 2.5 by astronomical dark. That
    keeps the ~90 stars that make the shapes people know, not the thousand a dark sky has."""
    if sun_el > -5:
        return None
    return 1.5 + 1.0 * min(1.0, (-5 - sun_el) / 12)


# Slow-changing work kept between frames: the Kindle redraws every minute, but satellite
# passes, rise and set times and the star field barely move in that time
_kept = {}


def kept(key, t, version, max_age, make, ends=None):
    """make() once and reuse it until `version` changes, it's `max_age` seconds old, the
    clock goes backwards, or `ends(value)` (when what it found is over) has passed."""
    hit = _kept.get(key)
    if (hit is None or hit[0] != version or not 0 <= t - hit[1] <= max_age
            or (ends and hit[2] is not None and ends(hit[2]) < t)):
        hit = _kept[key] = (version, t, make())
    return hit[2]


def build(data, t):
    lat, lon = P.HOME_LAT, P.HOME_LON
    sky = {"t": t, "sun_el": astro.sun_alt(t, lat, lon), "things": []}
    add = sky["things"].append

    b = data.get("balloon")
    if b:
        _, lat_b, lon_b, alt_m = b["track"][-1]
        el, az, rng = seen_from_home(lat_b, lon_b, alt_m / 1000)
        add(dict(kind="balloon", name="Weather balloon", el=el, az=az, km=rng, alt_km=alt_m / 1000,
                 rising=(b.get("vel_v") or 0) > 0, burst_km=b.get("burst_alt", 0) / 1000,
                 track=b["track"]))

    pico = data.get("amateur")
    if pico:
        el, az, rng = seen_from_home(pico["lat"], pico["lon"], pico["alt"] / 1000)
        if el > 0:
            add(dict(kind="pico", name="Pico balloon" if pico.get("days") else "Ham balloon", el=el, az=az, km=rng,
                     alt_km=pico["alt"] / 1000, call=pico["call"], days=pico.get("days")))

    def moon_el(tt):
        return astro.moon_alt_az(tt, lat, lon)[0]

    def planet_el(name):
        return lambda tt: astro.alt_az(*astro.planet(name, tt)[:2], tt, lat, lon)[0]

    def sun_el(tt):
        return astro.sun_alt(tt, lat, lon)

    def below(th, el_at):
        """Mark something under the horizon as a ghost, with when it comes up."""
        if th["el"] > 0:
            return th
        th["below"] = True
        th["rises"] = kept(("rises", th["name"]), t, None, 3600, lambda: crossing(el_at, t, rising=True),
                           ends=lambda when: when)
        return th

    ma, mz, mdist, frac, waxing = astro.moon_alt_az(t, lat, lon)
    if ma > -BELOW:
        add(below(dict(kind="moon", name="Moon", el=ma, az=mz, km=mdist, frac=frac, waxing=waxing), moon_el))
    for name in astro.PLANETS:
        if sky["sun_el"] > -5 and name != "Venus":
            continue  # the rest wash out in daylight
        ra, dec, dist = astro.planet(name, t)
        el, az = astro.alt_az(ra, dec, t, lat, lon)
        if el > -BELOW:
            add(below(dict(kind="planet", name=name, el=el, az=az, km=dist), planet_el(name)))
    if sky["sun_el"] > -BELOW:
        ra, dec, _ = astro.sun(t)
        el, az = astro.alt_az(ra, dec, t, lat, lon)
        add(below(dict(kind="sun", name="Sun", el=el, az=az, km=astro.AU_KM), sun_el))

    # The space stations, and the newest Starlink launch while it's still a train of
    # lights (the sample carries only that group); every other satellite was clutter
    orbits = data.get("orbits") or data.get("tle", "")
    sats = kept("sats", t, orbits, 86400, lambda: {
        "stations": [(n, s) for n, s in astro.read_orbits(orbits) if n.startswith(("ISS", "CSS"))],
        "fleet": [s for n, s in astro.read_orbits(orbits) if n.startswith("STARLINK")]})
    for name, sat in sats["stations"]:
        look = astro.sat_look(sat, t, lat, lon)
        # Only when you could see it: sunlit, against a sky dark enough
        if look and look[0] >= 10 and look[4] and sky["sun_el"] < -6:
            add(dict(kind="station", name="ISS" if name.startswith("ISS") else "Tiangong",
                     el=look[0], az=look[1], km=look[2], lit=look[4]))
    # Pass searches are the costly part: redo them every half hour or once a pass is over
    sky["passes"] = []
    for name, sat in sats["stations"]:
        short = "ISS" if name.startswith("ISS") else "Tiangong"
        # Three days ahead, so a week without evening passes still has one to promise. The
        # answer only changes with new orbits, so it's kept until the pass is over
        ps = kept(("pass", short), t, orbits, 6 * 3600,
                  lambda sat=sat: astro.next_visible_pass(sat, t, lat, lon, span=3 * 86400),
                  ends=lambda ps: ps["set"])
        if ps:
            sky["passes"].append((short, ps))
    sky["pass"] = next((ps for name, ps in sky["passes"] if name == "ISS"), None)
    sky["train"] = tr = kept("train", t, orbits, 600, lambda: train_pass(sats["fleet"], t, lat, lon),
                             ends=lambda tr: tr["end"])
    if tr and tr["start"] - 60 <= t <= tr["end"] and sky["sun_el"] < -6:
        # Only while a train is crossing is it worth placing each satellite
        for sat in sats["fleet"]:
            look = astro.sat_look(sat, t, lat, lon)
            if look and look[0] >= 10 and look[4]:
                add(dict(kind="train", name="Starlink", el=look[0], az=look[1], km=look[2]))

    moon = next((th for th in sky["things"] if th["kind"] == "moon" and not th.get("below")), None)
    if moon:
        moon["sets"] = kept("moonset", t, None, 3600, lambda: crossing(moon_el, t, rising=False),
                            ends=lambda when: when)

    # The Sun's day: today's, yesterday's length for the change, tomorrow's rise for the night
    lt = time.localtime(t)
    days = kept("days", t, time.strftime("%Y-%m-%d", lt), 86400,
                lambda: (sun_day(t), sun_day(t - 86400), sun_day(t + 86400)))
    sky["day"], sky["yesterday"], sky["tomorrow"] = days
    sky["year"] = kept("year", t, lt.tm_year, 30 * 86400, lambda: year_of_days(lt.tm_year, lat))
    return sky


def train_pass(fleet, t, lat, lon):
    """A fresh Starlink launch strings out along one orbit, so the satellites cross the
    same path one after another over several minutes. Summarise the pass that's on now
    or starts within 15 minutes: how many you'll see, from when to when, and the path."""
    seen = [ps for ps in (astro.next_pass(sat, t, lat, lon, span=1800, step=30) for sat in fleet)
            if ps and ps["visible"] and ps["rise"] <= t + 900]
    if len(seen) < 3:
        return None
    # Draw the path of the one that's highest right now (else the next one up): later
    # members cross a little to the side as the Earth turns under them
    def now_el(ps):
        k = min(ps["track"], key=lambda k: abs(k[0] - t))
        return k[1] if abs(k[0] - t) <= 30 else -90
    lead = max(seen, key=now_el) if any(now_el(ps) > -90 for ps in seen) else min(seen, key=lambda ps: ps["rise"])
    return dict(n=len(seen), start=min(ps["rise"] for ps in seen), end=max(ps["set"] for ps in seen),
                track=lead["track"], rise_az=lead["rise_az"], set_az=lead["set_az"], peak_el=lead["peak_el"])


SUN_HORIZON = -0.833  # refraction and the Sun's half-width: the almanac's sunrise and sunset


def sun_day(day_t):
    """The Sun's day, for the local calendar day of `day_t`: sunrise and sunset to the minute,
    their azimuths, and the arc between as (t, el, az) every 5 minutes."""
    lat, lon = P.HOME_LAT, P.HOME_LON
    lt = time.localtime(day_t)
    t0 = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    step = 300
    rise = sets = prev = None
    arc = []
    for k in range(86400 // step + 1):
        tt = t0 + k * step
        ra, dec, _ = astro.sun(tt)
        el, az = astro.alt_az(ra, dec, tt, lat, lon)
        if el > SUN_HORIZON:
            arc.append((tt, el, az))
        if prev:
            if prev[1] <= SUN_HORIZON < el and rise is None:
                rise = prev[0] + step * (SUN_HORIZON - prev[1]) / (el - prev[1])
            if prev[1] > SUN_HORIZON >= el:
                sets = prev[0] + step * (prev[1] - SUN_HORIZON) / (prev[1] - el)
        prev = (tt, el)
    if not (rise and sets):
        return None

    def az_at(tt):
        ra, dec, _ = astro.sun(tt)
        return astro.alt_az(ra, dec, tt, lat, lon)[1]

    # Dark enough for stars: the Sun 12 degrees down, after sunset
    dark = next((tt for tt in range(int(sets), int(sets) + 4 * 3600, 300) if astro.sun_alt(tt, lat, lon) < -12), None)
    return dict(rise=rise, set=sets, rise_az=az_at(rise), set_az=az_at(sets), arc=arc, length=sets - rise, dark=dark)


def day_length_h(tt, lat):
    """Hours of daylight on the day of `tt`, from the Sun's declination alone: the almanac's
    formula, good to a minute, for the year's curve."""
    dec = math.radians(astro.sun(tt)[1])
    lat = math.radians(lat)
    x = (math.sin(math.radians(SUN_HORIZON)) - math.sin(lat) * math.sin(dec)) / (math.cos(lat) * math.cos(dec))
    return 2 * math.degrees(math.acos(max(-1.0, min(1.0, x)))) / 15


def year_of_days(year, lat):
    """[(day of year, hours of daylight)] every 4 days: the shape of the year."""
    jan1 = time.mktime((year, 1, 1, 12, 0, 0, 0, 0, -1))
    return [(doy, day_length_h(jan1 + (doy - 1) * 86400, lat)) for doy in range(1, 367, 4)]


def crossing(el_at, t, rising, span=18 * 3600, step=120):
    """When something next rises over (or sets below) the horizon, to two minutes."""
    return next((tt for tt in range(int(t), int(t) + span, step) if (el_at(tt) > 0) == rising), None)


# ---------- drawing ----------

def star_level(mag):
    return THING if mag < 1.5 else SOFT


def star_dot(img, d, x, y, mag, fill):
    if mag < 0.6:
        # The handful of brightest stars twinkle
        icons.paste(img, icons.glyph("sparkle", 24, fill), x, y, 0)
        return
    r = max(2.0, 6.4 - mag * 1.2)
    d.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def inside(x, y, pad=0):
    return math.hypot(x - DOME_X, y - DOME_Y) <= DOME_R - pad


def star_layer(t, limit, star_fill):
    """The stars on black, for lightening onto the night dome. No constellation lines: at a
    size that reads across a room there's no space for them beside the labels. The sky
    turns a quarter degree a minute (about a pixel here), so this is redrawn every ten."""
    lat, lon = P.HOME_LAT, P.HOME_LON
    # Only the dome's square, not the whole page
    ox, oy = DOME_X - DOME_R, DOME_Y - DOME_R
    layer = Image.new("L", (2 * DOME_R + 1, 2 * DOME_R + 1), 0)
    d = ImageDraw.Draw(layer)
    pos = {}

    def xy(ra, dec):
        k = (ra, dec)
        if k not in pos:
            el, az = astro.alt_az(ra, dec, t, lat, lon)
            pos[k] = None
            if el > 0:
                x, y = dome_xy(el, az)
                pos[k] = (x - ox, y - oy)
        return pos[k]

    for ra, dec, mag in SKY["stars"]:
        if mag <= limit:
            p = xy(ra, dec)
            if p:
                star_dot(layer, d, p[0], p[1], mag, star_fill or star_level(mag))
    return layer


def draw_stars(img, t, limit):
    # In half magnitudes, so twilight deepening doesn't redraw the field every minute
    limit = round(limit * 2) / 2
    layer = kept("stars", t, (limit, DOME_X, DOME_Y, DOME_R, P.HEADING), 600,
                 lambda: star_layer(t, limit, None))
    box = (DOME_X - DOME_R, DOME_Y - DOME_R, DOME_X + DOME_R + 1, DOME_Y + DOME_R + 1)
    img.paste(ImageChops.lighter(img.crop(box), layer), box[:2])


def star_names(d, t):
    """The two highest named stars, and only where every other label has left room: they
    go down last."""
    up = sorted(((astro.alt_az(ra, dec, t, P.HOME_LAT, P.HOME_LON), name) for ra, dec, name in SKY["names"]),
                reverse=True)
    placed = 0
    for (el, az), name in up:
        if el <= 0 or placed == 2:
            break
        p = dome_xy(el, az)
        w, h = P.text_w(d, name, SMALL), SMALL.size
        for lx in (p[0] + 14, p[0] - 14 - w):
            box = (lx - 6, p[1] - h * 0.7, lx + w + 6, p[1] + h * 0.7)
            if inside(lx, p[1], 20) and inside(lx + w, p[1], 20) and not any(
                    box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in TAKEN):
                glow_text(d, (lx, p[1] - h * 0.6), name, SMALL, SOFT, GROUND)
                named(name, STAR_LY.get(name, 100) * KM_PER_LY, "star")
                TAKEN.append(box)
                placed += 1
                break


def moon_near(things, x, y):
    """True when the moon is close enough that a planet's name goes on the moon's label."""
    return any(math.hypot(*(a - b for a, b in zip(dome_xy(m["el"], m["az"]), (x, y)))) < 100
               for m in things if m["kind"] == "moon" and not m.get("below"))


def glow_text(d, xy, s, f, fill, bg):
    """halo_text() against any background, not just paper."""
    x, y = xy
    for dx in (-3, 0, 3):
        for dy in (-3, 0, 3):
            if dx or dy:
                d.text((x + dx, y + dy), s, font=f, fill=bg)
    d.text(xy, s, font=f, fill=fill)


TAKEN = []
# Everything the dome has put a name to, as (name, km, kind): the list in the panel is its key
NAMED = []


def named(name, km, kind):
    if name not in (n for n, _, _ in NAMED):
        NAMED.append((name, km, kind))


def side_label(d, x, y, off, s, f, fill, bg, dy=0):
    """Label beside its mark: the eight places around it, the side facing the dome's center
    first, then the same ring a line further out. Where nothing is clear it takes the place
    that overlaps least, so a label never wanders off from what it names."""
    w, h = P.text_w(d, s, f), f.size
    spots = []
    for o in (off, off + h):
        beside = [(x + o, y - h * 0.6 + dy), (x - o - w, y - h * 0.6 + dy)]
        if x >= DOME_X:
            beside.reverse()
        spots += beside + [(x - w / 2, y - o - h * 1.1), (x - w / 2, y + o - h * 0.1),
                           (x + o * 0.7, y - o * 0.7 - h), (x + o * 0.7, y + o * 0.7),
                           (x - o * 0.7 - w, y - o * 0.7 - h), (x - o * 0.7 - w, y + o * 0.7)]

    def box(lx, ly):
        return (lx - 4, ly - 2, lx + w + 4, ly + h * 1.2)

    def overlap(sp):
        b = box(*sp)
        return sum(max(0, min(b[2], t[2]) - max(b[0], t[0])) * max(0, min(b[3], t[3]) - max(b[1], t[1]))
                   for t in TAKEN)

    on = [sp for sp in spots if inside(sp[0], sp[1] + h / 2, 4) and inside(sp[0] + w, sp[1] + h / 2, 4)] or spots
    lx, ly = next((sp for sp in on if not overlap(sp)), None) or min(on, key=overlap)
    TAKEN.append(box(lx, ly))
    glow_text(d, (lx, ly), s, f, fill, bg)


def draw_balloon(img, x, y, px, ink, bg, burst=False):
    """The balloon, or once it has burst, what's left coming down under its parachute."""
    icons.paste(img, icons.glyph("parachute" if burst else "balloon", px, ink), x, y, bg)


def moon_icon(r, frac, waxing, x, y, sun_xy, night, lit_shade=255):
    """The Moon's icon in the nearest of Weather Icons' 28 phases, its lit side toward
    where the sun is on the dome (turned in 5 degree steps so the cache stays small)."""
    elong = math.degrees(math.acos(max(-1.0, min(1.0, 1 - 2 * frac))))
    phase = int(round((elong if waxing else 360 - elong) / 360 * 28)) % 28
    ang = math.degrees(math.atan2(sun_xy[1] - y, sun_xy[0] - x))
    return icons.moon(2 * r, phase, int(round(ang / 5.0)) * 5, night, lit_shade)


def dash_line(d, pts, fill, width, on, off):
    """Dashes measured along the whole path, so they stay even however it's sampled."""
    carry, drawing = on, True
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        pos = 0.0
        while pos < seg:
            step = min(carry, seg - pos)
            if drawing:
                f0, f1 = pos / seg, (pos + step) / seg
                d.line((x0 + (x1 - x0) * f0, y0 + (y1 - y0) * f0, x0 + (x1 - x0) * f1, y0 + (y1 - y0) * f1),
                       fill=fill, width=width)
            pos += step
            carry -= step
            if carry <= 0:
                drawing = not drawing
                carry = on if drawing else off


def claim_path(pts, half):
    """Mark a drawn path as taken, a box every few pixels along it, so labels go beside it."""
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) // half))
        for k in range(n + 1):
            x, y = x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n
            TAKEN.append((x - half, y - half, x + half, y + half))


def on_ground(th):
    """True when something below the horizon falls inside the frame, so it's drawn there
    with its rise time."""
    x, y = dome_xy(th["el"], th["az"])
    return SKY_BOX[0] + 30 < x < SKY_BOX[2] - 30 and SKY_BOX[1] + 30 < y < SKY_BOX[3] - 30


def compass_boxes(d):
    """Where N, E, S and W go, just outside the horizon, as boxes for labels to keep clear of."""
    boxes = []
    for lab, az in (("N", 0), ("E", 90), ("S", 180), ("W", 270)):
        x, y = dome_xy(0, az)
        w = P.text_w(d, lab, COMPASS)
        boxes.append((x - w / 2 - 4, y - COMPASS.size * 0.6 - 2, x + w / 2 + 4, y + COMPASS.size * 0.7))
    return boxes


def draw_dome(img, d, sky):
    dome, ink = GROUND, THING
    hk = sky["hero"]["kind"] if sky["hero"].get("start", 0) <= sky["t"] else None
    hname = sky["hero"].get("name")

    def lit(kind):
        return HERO if kind == hk else THING
    R = DOME_R
    ghost = FRAME
    # Solid page, sky and ground alike: only the horizon line says where the sky ends
    d.ellipse((DOME_X - R, DOME_Y - R, DOME_X + R, DOME_Y + R), outline=FRAME, width=7)

    # The way you face, as a soft cone from the middle toward the top, the way a map shows
    # it. Drawn first, so everything in the sky sits on top of it
    cone = DOME_R * 0.34
    d.pieslice((DOME_X - cone, DOME_Y - cone, DOME_X + cone, DOME_Y + cone), 242, 298, fill=FRAME - 68)

    things = sky["things"]
    del TAKEN[:]
    del NAMED[:]
    # Compass letters on the horizon, in a gap cut in the line, like a compass bezel. First,
    # so the sky draws over them (the Moon rising in the east beats the E), and taken, so
    # no label lands on one
    for lab, box in zip("NESW", compass_boxes(d)):
        d.rectangle((box[0] - 4, box[1], box[2] + 4, box[3]), fill=GROUND)
        d.text((box[0] + 4, box[1] + 2), lab, font=COMPASS, fill=SOFT)
        TAKEN.append(box)
    for th in [th for th in things if not th.get("below")]:
        # Marks claim their space before any label goes down
        x, y = dome_xy(th["el"], th["az"])
        if th["kind"] in ("balloon", "pico"):
            TAKEN.append((x - 30, y - 32, x + 30, y + 32))
            continue
        r = {"moon": 36, "station": 40, "sun": 36, "train": 18, "planet": 18}.get(th["kind"], 10)
        TAKEN.append((x - r, y - r, x + r, y + r))
    limit = mag_limit(sky["sun_el"])
    if limit:
        draw_stars(img, sky["t"], limit)
        # The few brightest are sparkles, big enough that a label on one hides it
        for ra, dec, mag in SKY["stars"]:
            if mag < 0.6:
                el, az = astro.alt_az(ra, dec, sky["t"], P.HOME_LAT, P.HOME_LON)
                if el > 0:
                    x, y = dome_xy(el, az)
                    TAKEN.append((x - 14, y - 14, x + 14, y + 14))
    sun_ra, sun_dec, _ = astro.sun(sky["t"])
    sel, saz = astro.alt_az(sun_ra, sun_dec, sky["t"], P.HOME_LAT, P.HOME_LON)
    sun_xy = dome_xy(sel, saz)  # off the dome when it's down, which still points the right way

    # By day, the Sun's whole path today, with a bead each hour
    day = sky.get("day")
    if day and sky["sun_el"] > SUN_HORIZON:
        pts = [dome_xy(SUN_HORIZON, day["rise_az"])] + [dome_xy(el, az) for _, el, az in day["arc"]] + \
            [dome_xy(SUN_HORIZON, day["set_az"])]
        d.line(pts, fill=FRAME, width=6, joint="curve")
        for tt, el, az in day["arc"]:
            if time.localtime(tt).tm_min == 0:
                bx, by = dome_xy(el, az)
                d.ellipse((bx - 7, by - 7, bx + 7, by + 7), fill=SOFT)

    # You, under the middle of the sky, as a map marks you: a dot, on top of the cone
    d.ellipse((DOME_X - 19, DOME_Y - 19, DOME_X + 19, DOME_Y + 19), fill=GROUND)
    d.ellipse((DOME_X - 13, DOME_Y - 13, DOME_X + 13, DOME_Y + 13), fill=THING)

    # Paths first, so no label ends up under a line: they claim their room like the marks
    tr = sky.get("train")
    if tr:
        path = [dome_xy(k[1], k[2]) for k in tr["track"]]
        dash_line(d, path, lit("train"), width=6, on=12, off=10)
        claim_path(path, 10)
    # The headline's pass if it's a station's, else the ISS's, once it's within the hour
    ps = sky["hero"].get("pass_") or sky.get("pass")
    lead = sky["hero"].get("name") if sky["hero"].get("pass_") else "ISS"
    if ps and ps["rise"] <= sky["t"] + 3600:
        pts = [(k[0], dome_xy(k[1], k[2])) for k in ps["track"]]
        # Heavy enough to survive e-ink: flown part solid, the rest in long dashes
        flown = [p for tt, p in pts if tt <= sky["t"]]
        ahead = [p for tt, p in pts if tt > sky["t"]]
        if flown and ahead:
            ahead.insert(0, flown[-1])
        if len(flown) > 1:
            d.line(flown, fill=lit("station") if lead == hname else THING, width=14, joint="curve")
        dash_line(d, ahead, lit("station") if lead == hname else THING, width=12, on=26, off=14)
        claim_path([p for _, p in pts], 14)
        # Arrowhead where it leaves
        (xa, ya), (xb, yb) = pts[-2][1], pts[-1][1]
        ang = math.atan2(yb - ya, xb - xa)
        d.polygon([(xb + 42 * math.cos(ang), yb + 42 * math.sin(ang)),
                   (xb + 32 * math.cos(ang + 2.4), yb + 32 * math.sin(ang + 2.4)),
                   (xb + 32 * math.cos(ang - 2.4), yb + 32 * math.sin(ang - 2.4))],
                  fill=lit("station") if lead == hname else THING)

    # Things below the horizon, ghosted on the ground outside it
    for th in [th for th in things if th.get("below") and th["kind"] == "moon"]:
        x, y = dome_xy(th["el"], th["az"])
        if not on_ground(th):
            continue
        if th["kind"] == "moon":
            icons.paste(img, moon_icon(26, th["frac"], th["waxing"], x, y, sun_xy, True, ghost), x, y, dome)
        else:
            rr = 18 if th["kind"] == "sun" else 8
            d.ellipse((x - rr, y - rr, x + rr, y + rr), outline=ghost, width=5)
        # The rise time, unless the headline is this very rise and already says it
        said = sky["hero"]["kind"] == th["kind"] and sky["hero"].get("start") == th.get("rises")
        lab = th["name"] + (" rises " + clock(th["rises"]) if th.get("rises") and not said else "")
        w, h = P.text_w(d, lab, SMALL), SMALL.size
        # Below, above, right or left of it: the first spot clear of the compass letters,
        # and outside the dome, where the ground is
        spots = [(x - w / 2, y + 30), (x - w / 2, y - 30 - h * 1.2), (x + 36, y - h * 0.6), (x - 36 - w, y - h * 0.6)]
        spots = [(min(max(lx, SKY_BOX[0]), SKY_BOX[2] - w), min(max(ly, SKY_BOX[1]), SKY_BOX[3] - h * 1.2))
                 for lx, ly in spots]

        def cost(sp, w=w, h=h):
            b = (sp[0] - 4, sp[1] - 2, sp[0] + w + 4, sp[1] + h * 1.2)
            hit = sum(max(0, min(b[2], c[2]) - max(b[0], c[0])) * max(0, min(b[3], c[3]) - max(b[1], c[1]))
                      for c in compass_boxes(d) + TAKEN)
            return hit, inside((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)

        lx, ly = min(spots, key=cost)
        TAKEN.append((lx - 4, ly - 2, lx + w + 4, ly + h * 1.2))
        glow_text(d, (lx, ly), lab, SMALL, SOFT, GROUND)
        named(th["name"], th["km"], th["kind"])

    for th in [th for th in things if not th.get("below")]:
        x, y = dome_xy(th["el"], th["az"])
        if th["kind"] == "moon":
            icons.paste(img, moon_icon(34, th["frac"], th["waxing"], x, y, sun_xy, True, lit("moon")), x, y, dome)
            near = [p["name"] for p in things if p["kind"] == "planet" and not p.get("below")
                    and math.hypot(*(a - b for a, b in zip(dome_xy(p["el"], p["az"]), (x, y)))) < 100]
            side_label(d, x, y, 44, " & ".join(["Moon"] + near), LABEL, lit("moon"), dome, dy=-30)
            named("Moon", th["km"], "moon")
            for p in things:
                if p["name"] in near:
                    named(p["name"], p["km"], "planet")
        elif th["kind"] == "planet":
            # Ringed for the giants, a sparkle for Venus, a plain dot for Mars
            icon = {"Venus": ("sparkle", 34), "Mars": ("dot", 16)}.get(th["name"], ("planet", 38))
            icons.paste(img, icons.glyph(icon[0], icon[1], ink), x, y, dome)
            if not moon_near(things, x, y):
                side_label(d, x, y, 24, th["name"], LABEL, ink, dome, dy=4)
                named(th["name"], th["km"], "planet")
        elif th["kind"] == "sun":
            icons.paste(img, icons.glyph("sun", 68, ink), x, y, dome)
            side_label(d, x, y, 46, "Sun", LABEL, ink, dome)
            named("Sun", th["km"], "sun")

    tr = sky.get("train")
    if tr:
        # A bead for each one up right now, on the path drawn with the others above
        path = [dome_xy(k[1], k[2]) for k in tr["track"]]
        beads = [dome_xy(th["el"], th["az"]) for th in things if th["kind"] == "train"]
        for x, y in beads:
            icons.paste(img, icons.glyph("satellite", 30, lit("train")), x, y, dome)
        at = min(beads, key=lambda b: b[1]) if beads else path[len(path) // 2]
        side_label(d, at[0], at[1], 26, "Starlink", BLABEL, lit("train"), dome)
        cars = [th["km"] for th in things if th["kind"] == "train"]
        if cars:
            named("Starlink", min(cars), "train")

    for pb in (th for th in things if th["kind"] == "pico"):
        x, y = dome_xy(max(pb["el"], 5), pb["az"])
        draw_balloon(img, x, y, 48, lit("pico"), dome)
        side_label(d, x, y, 32, pb["name"], BLABEL, lit("pico"), dome)
        named(pb["name"], pb["km"], "pico")

    b = next((th for th in things if th["kind"] == "balloon"), None)
    if b:
        # Nudged up off the horizon line when it's very low, so the whole icon shows
        x, y = dome_xy(max(b["el"], 5), b["az"])
        draw_balloon(img, x, y, 56, lit("balloon"), dome, burst=not b["rising"])
        side_label(d, x, y, 36, "Balloon", BLABEL, lit("balloon"), dome)
        named("Balloon", b["km"], "balloon")

    for th in things:
        if th["kind"] == "station":
            x, y = dome_xy(th["el"], th["az"])
            level = lit("station") if th["name"] == hname else THING
            icon = icons.glyph("satellite", 70, level)
            icons.paste(img, icon, x, y, dome)
            side_label(d, x, y - 4, icon[0].width // 2 + 10, th["name"], BLABEL, level, dome)
            named(th["name"], th["km"], "station")

    if limit:
        star_names(d, sky["t"])



# ---------- panel ----------

def fmt_km(km):
    if km >= KM_PER_LY * 0.5:
        return "%d light-years" % round(km / KM_PER_LY)
    if km >= 1e9:
        return "%.1f billion km" % (km / 1e9)
    if km >= 1e6:
        return "%d million km" % round(km / 1e6)
    return "{:,} km".format(int(round(km, -3 if km > 1e5 else 0)))


def clock(t):
    return time.strftime("%-I:%M", time.localtime(t))


def hm(seconds):
    """A duration as the planes frame writes them: 11h 46m, never 11:46, which reads as a time."""
    return "%dh %02dm" % divmod(int(round(seconds / 60.0)), 60)


def ms(seconds):
    return "%dm %02ds" % divmod(int(round(seconds)), 60) if seconds >= 60 else "%ds" % round(seconds)


def moon_phase(frac, waxing):
    if frac > 0.97:
        return "Full moon"
    if frac < 0.03:
        return "New moon"
    if 0.42 < frac < 0.58:
        return "First quarter moon" if waxing else "Last quarter moon"
    return ("Waxing " if waxing else "Waning ") + ("gibbous moon" if frac > 0.5 else "crescent moon")


def when_clock(t, now):
    """8:01, or 'tomorrow 8:01' / 'Sat 8:01' past midnight."""
    day = time.localtime(t).tm_yday - time.localtime(now).tm_yday
    return clock(t) if day == 0 else ("tomorrow %s" % clock(t) if day == 1 else
                                      time.strftime("%a ", time.localtime(t)) + clock(t))


def day_word(t, now):
    """When, in the caps under a time, since the clock has no am or pm: TONIGHT, TOMORROW AM."""
    lt = time.localtime(t)
    days = round((time.mktime(lt[:3] + (12, 0, 0, 0, 0, -1)) -
                  time.mktime(time.localtime(now)[:3] + (12, 0, 0, 0, 0, -1))) / 86400)
    half = "AM" if lt.tm_hour < 12 else "PM"
    if days == 0:
        return "TONIGHT" if lt.tm_hour >= 18 else ("THIS MORNING" if half == "AM" else "THIS AFTERNOON")
    if days == 1:
        return "TOMORROW " + half
    return time.strftime("%a ", lt).upper() + half


def countdown(start, end, t):
    """The line under the path: how long until it starts, or that it's up now."""
    if t >= start:
        return "Up now" if t <= end else "Gone"
    mins = (start - t) / 60
    if mins < 90:
        return "In %d min" % max(1, round(mins))
    return "Up for %d min" % max(1, round((end - start) / 60))


def along(start, end, t):
    return min(1.0, max(0.0, (t - start) / float(max(1, end - start))))


# The frame invites; it never complains. Every line is something to look forward to or go
# out for: a shortening day is told as the hour the stars come out, and a shower washed out
# by the Moon steps back rather than saying so.
#
# What's worth looking up for, and when. Every candidate is an event with a window and a
# wonder from 1 (a sunset) to 5 (an eclipse). The headline is the event scoring highest
# right now: a thing that's on scores its wonder in full; a thing still to come scores
# less the further off it is, with a lead that grows with wonder, so a sunset only matters
# in the moment while a great ISS pass takes the afternoon and a big meteor shower the day
# before. Below the headline, "Next" names the most wonderful thing in the coming week.
LEAD_H = {1: 0.5, 2: 2, 3: 6, 4: 24, 5: 24 * 7}
NEXT_DAYS = 7          # for everything; past a week only for what comes once a year or less,
YEARLY_DAYS = 30       # and not so far off that it says the same thing all season
# Peak nights of the showers worth a look, with their usual rates an hour under a dark sky
SHOWERS = (("Quadrantids", 1, 3, 80), ("Lyrids", 4, 22, 18), ("Eta Aquariids", 5, 5, 50),
           ("Perseids", 8, 12, 100), ("Orionids", 10, 21, 20), ("Leonids", 11, 17, 15), ("Geminids", 12, 13, 150))


def score(ev, t):
    if t > ev["end"]:
        return 0.0
    if t >= ev["start"]:
        return float(ev["wonder"])
    lead = LEAD_H[ev["wonder"]]
    return ev["wonder"] * lead / (lead + (ev["start"] - t) / 3600.0)


def how_soon(at, now, timed):
    """For the Next line: tonight 8:49, tomorrow night, in 25 days."""
    lt = time.localtime(at)
    days = round((time.mktime(lt[:3] + (12, 0, 0, 0, 0, -1)) -
                  time.mktime(time.localtime(now)[:3] + (12, 0, 0, 0, 0, -1))) / 86400)
    if days >= 2:
        return "in %d days" % days
    word = night_word(at, now) if lt.tm_hour >= 18 or lt.tm_hour < 6 else ("today" if days == 0 else "tomorrow")
    return word + (" " + clock(at) if timed else "")


def night_word(t, now):
    """Tonight, tomorrow night, Sat night: for things that belong to a night."""
    if t - now > 6 * 86400:
        return time.strftime("%b %-d", time.localtime(t))
    d = day_word(t, now)
    return {"TONIGHT": "tonight", "TOMORROW PM": "tomorrow night", "TOMORROW AM": "tomorrow night"}.get(
        d, time.strftime("%a", time.localtime(t)) + " night")


def pass_event(name, ps, t):
    """A visible pass of a space station. Tiangong only counts from 30° up: lower, it's a
    faint dot in the haze, and the ISS already teaches the eye what a pass looks like."""
    up = "overhead" if ps["peak_el"] >= 60 else "pass"
    if name == "ISS":
        wonder = 4 if ps["peak_el"] >= 60 else (3 if ps["peak_el"] >= 25 else 2)
    elif ps["peak_el"] >= 30:
        wonder = 3 if ps["peak_el"] >= 60 else 2
    else:
        return None
    return dict(kind="station", name=name, pass_=ps, wonder=wonder,
                start=ps["rise"], end=ps["set"], head=name + " " + up,
                stats=[(clock(ps["peak"]), day_word(ps["peak"], t)), ("%d°" % ps["peak_el"], "UP")],
                path=(P.compass(ps["rise_az"]), P.compass(ps["set_az"]), along(ps["rise"], ps["set"], t)),
                foot=countdown(ps["rise"], ps["set"], t),
                next=("%s %s" % (name, up), ps["peak"], True))


def shower_events(t, lat, lon):
    """This year's and next year's peak nights, 10 pm to 5 am, with the Moon's say in it."""
    out = []
    year = time.localtime(t).tm_year
    for name, m, d, rate in SHOWERS:
        for y in (year, year + 1):
            start = time.mktime((y, m, d, 22, 0, 0, 0, 0, -1))
            frac = astro.moon(start)[3]
            wonder = 4 if rate >= 80 else (3 if rate >= 50 else 2)
            if frac < 0.6:
                moon_stat = ("%d%%" % round(frac * 100), "MOON LIT")
            else:
                # A bright Moon washes the shower out: say when it sets, and don't lead with it
                moonset = crossing(lambda tt: astro.moon_alt_az(tt, lat, lon)[0], start, rising=False, span=7 * 3600)
                moon_stat = (clock(moonset), "MOON SETS") if moonset else None
                wonder = max(2, wonder - 1)
            out.append(dict(kind="shower", wonder=wonder,
                            start=start, end=start + 7 * 3600, head=name,
                            stats=[("%d" % rate, "AN HOUR")] + ([moon_stat] if moon_stat else []),
                            foot="Best after midnight" if t >= start else night_word(start, t).capitalize(),
                            next=(name, start, False), yearly=True))
    return out


def next_full_moon(t):
    """The next night the Moon is full, to the hour."""
    tt = t
    while tt < t + 31 * 86400:
        if astro.moon(tt)[3] > 0.995:
            return tt
        tt += 3600
    return None


def events(sky):
    """Every candidate headline, with its window and wonder, set out like the planes
    frame's flight: a headline, two big numbers, a path from where it rises to where it
    sets with the thing on it, and a line under that."""
    t, things, tr = sky["t"], sky["things"], sky.get("train")
    lat, lon = P.HOME_LAT, P.HOME_LON
    evs = []
    if tr:
        evs.append(dict(kind="train", wonder=4, start=tr["start"], end=tr["end"], head="Starlink train",
                        stats=[("%d" % tr["n"], "IN A LINE"), (clock(tr["start"]), day_word(tr["start"], t))],
                        path=(P.compass(tr["rise_az"]), P.compass(tr["set_az"]), along(tr["start"], tr["end"], t)),
                        foot=countdown(tr["start"], tr["end"], t), next=("Starlink train", tr["start"], True)))
    for name, station_pass in sky.get("passes", []):
        ev = pass_event(name, station_pass, t)
        if ev:
            evs.append(ev)
    pico = next((th for th in things if th["kind"] == "pico"), None)
    if pico:
        # A balloon on its own, from a ham radio club or a school: the long ones circle the world
        evs.append(dict(kind="pico", wonder=4 if (pico["days"] or 0) >= 7 else 3, start=t, end=t, head=pico["name"],
                        stats=[("%.0f" % pico["alt_km"], "KM UP"), ("%d°" % pico["el"], "UP IN THE " + P.compass(pico["az"]))],
                        foot="%s, day %d aloft" % (pico["call"], pico["days"]) if pico["days"] else pico["call"]))
    b = next((th for th in things if th["kind"] == "balloon"), None)
    if b:
        evs.append(dict(kind="balloon", wonder=3, start=t, end=t, head="Weather balloon",
                        stats=[("%.0f" % b["alt_km"], "KM UP"), ("%d°" % max(0, b["el"]), "UP IN THE " + P.compass(b["az"]))],
                        foot=("Climbing" if b["rising"] else "Falling") + ", from " + launch_site(b["track"][0])))
    day = sky.get("day")
    if day:
        # Daylight: the day as a path from sunrise to sunset, and how it's changing
        sun = next((th for th in things if th["kind"] == "sun"), None)
        diff = day["length"] - sky["yesterday"]["length"] if sky.get("yesterday") else 0
        evs.append(dict(kind="sun", wonder=2, start=day["rise"], end=day["set"], head="Sunset " + clock(day["set"]),
                        stats=[(hm(day["length"]), "OF DAYLIGHT"),
                               ("%d°" % (sun["el"] if sun else 0), "UP IN THE " + P.compass(sun["az"] if sun else 180))],
                        path=(P.compass(day["rise_az"]), P.compass(day["set_az"]), along(day["rise"], day["set"], t)),
                        icon="sun",
                        foot="Longest day of the year" if abs(diff) < 15 and day["length"] > 12 * 3600 else
                        ("Gaining %s a day" % ms(diff) if diff > 0 else
                         ("Stars out by " + clock(day["dark"]) if day.get("dark") else None))))
    rise = day["rise"] if day and t < day["rise"] else (sky.get("tomorrow") or {}).get("rise")
    if rise:
        evs.append(dict(kind="sun", wonder=1, start=rise, end=rise + 3600, head="Sunrise " + clock(rise), stats=[]))
    moon = next((th for th in things if th["kind"] == "moon"), None)
    if moon:
        full = moon["frac"] > 0.97
        phase = moon_phase(moon["frac"], moon["waxing"])
        if not moon.get("below") and sky["sun_el"] < 0:
            # A full or new moon says how lit it is in its name; the percent is for the others
            lit = [] if phase in ("Full moon", "New moon") else [("%d%%" % round(moon["frac"] * 100), "LIT")]
            evs.append(dict(kind="moon", wonder=3 if full else 2, start=t, end=moon.get("sets") or t + 3600, head=phase,
                            stats=[("%d°" % moon["el"], "UP IN THE " + P.compass(moon["az"]))] + lit,
                            foot="Sets %s" % when_clock(moon["sets"], t) if moon.get("sets") else None))
        elif moon.get("rises") and astro.sun_alt(moon["rises"], lat, lon) < 0:
            # Rising later tonight: a headline in advance, once it's the best thing coming
            az = astro.moon_alt_az(moon["rises"], lat, lon)[1]
            evs.append(dict(kind="moon", wonder=3 if full else 2, start=moon["rises"], end=moon["rises"] + 6 * 3600,
                            head=phase, stats=[(clock(moon["rises"]), day_word(moon["rises"], t)),
                                               ("%d%%" % round(moon["frac"] * 100), "LIT")],
                            foot="Rises in the " + P.compass(az),
                            # The dome already says it when the Moon is drawn below the horizon
                            next=None if on_ground(moon) else ("Moon rises", moon["rises"], True)))
    fm = kept("fullmoon", t, None, 6 * 3600, lambda: next_full_moon(t + 86400), ends=lambda when: when)
    if fm and fm > t + 86400:
        evs.append(dict(kind="moon", wonder=3, start=fm, end=fm + 6 * 3600, head="Full moon", stats=[],
                        next=("Full moon", fm, False)))
    evs += kept("showers", t, time.localtime(t).tm_year, 86400, lambda: shower_events(t, lat, lon))
    return evs


def hero(sky):
    """The headline and, below it, the most wonderful thing in the coming week."""
    t = sky["t"]
    evs = events(sky)
    # Ties (an overhead pass while a train crosses): the station, the rarer sight, then the sooner
    rank = {"station": 2, "train": 1, "pico": 1}
    best = max(evs, key=lambda ev: (score(ev, t), rank.get(ev["kind"], 0), -ev["start"])) if evs else None
    if not best or score(best, t) <= 0:
        best = dict(kind=None, head="Clear above", stats=[])
    ahead = [ev for ev in evs if ev is not best and ev.get("next") and t < ev["start"]
             and ev["start"] < t + (YEARLY_DAYS if ev.get("yearly") else NEXT_DAYS) * 86400
             and not (ev["kind"] == best["kind"] and ev["start"] == best["start"])]
    nxt = min(ahead, key=lambda ev: (-ev["wonder"], ev["start"]))["next"] if ahead else None
    best["next"] = "%s %s" % (nxt[0], how_soon(nxt[1], t, nxt[2])) if nxt else None
    return best


def launch_site(fix):
    """Where the balloon went up: by name for the sites people know, else by distance."""
    for name, lat, lon in SONDE_SITES:
        if P.distance_bearing(lat, lon, fix[1], fix[2])[0] < 40:
            return name
    dist, brg = P.distance_bearing(P.HOME_LAT, P.HOME_LON, fix[1], fix[2])
    return "%d km %s" % (round(dist, -1), P.compass(brg))


SONDE_SITES = (("Buffalo", 42.94, -78.72), ("Detroit", 42.70, -83.47), ("Albany", 42.69, -73.83),
               ("Maniwaki", 46.30, -76.01), ("Pittsburgh", 40.53, -80.22))


# Distances of the named stars, light-years, for the list in the panel
STAR_LY = {"Vega": 25, "Deneb": 2600, "Altair": 17, "Arcturus": 37, "Capella": 43, "Aldebaran": 65,
           "Polaris": 430, "Betelgeuse": 550, "Rigel": 860, "Sirius": 8.6, "Procyon": 11.5,
           "Pollux": 34, "Castor": 51, "Regulus": 79, "Spica": 250, "Antares": 550, "Fomalhaut": 25,
           "Canopus": 310, "Achernar": 139, "Acrux": 320, "Hadar": 390, "Rigil Kentaurus": 4.4}


def wind_turn(pts):
    """Height (km) where the balloon's east-west drift reverses by more than a km, or None."""
    lo = hi = 0
    for i, (x, _alt) in enumerate(pts):
        if x < pts[lo][0]:
            lo = i
        if x > pts[hi][0]:
            hi = i
        if pts[lo][0] < x - 1 and lo:
            return pts[lo][1]
        if pts[hi][0] > x + 1 and hi:
            return pts[hi][1]
    return None


def draw_balloon_side(d, b, x0, y, width):
    """The balloon's flight side-on: height against east-west drift from the launch, so a
    change of wind with height shows as a bend. Returns the y below it."""
    y += 40  # headroom for the balloon at the top of its climb
    tr = b["track"]
    lat0, lon0 = tr[0][1], tr[0][2]
    pts = [((lo - lon0) * 111.32 * math.cos(math.radians(lat0)), a / 1000) for _, la, lo, a in tr]
    top_km = max(35.0, pts[-1][1])
    cw, ch = width - P.text_w(d, "30 km", SMALL) - 16, 170
    turn = wind_turn(pts)
    tx_km = next(x for x, a in pts if a >= turn) if turn else None
    xs = [x for x, _ in pts]
    lo_km, hi_km = min(xs), max(xs)
    # Room for "wind turns" on the outside of the bend, where the line isn't
    room = P.text_w(d, "wind turns", SMALL) + 24
    west_bend = turn is not None and tx_km - lo_km < hi_km - tx_km
    lpad, rpad = (room, 16) if west_bend else (16, room if turn else 16)
    per_km = min((cw - lpad - rpad) / max(hi_km - lo_km, 0.1), cw / 8.0)  # small drifts stay small
    mid = (lo_km + hi_km) / 2
    cx = x0 + lpad + (cw - lpad - rpad) / 2

    def xy(x, alt):
        return cx + (x - mid) * per_km, y + ch - alt / top_km * ch

    for km in (10, 20, 30):
        gy = xy(0, km)[1]
        d.line((x0, gy, x0 + cw, gy), fill=FRAME, width=3)
        d.text((x0 + cw + 10, gy - SMALL.size * 0.6), "%d km" % km, font=SMALL, fill=SOFT)
    d.line((x0, y + ch, x0 + cw, y + ch), fill=FRAME, width=5)
    d.line([xy(x, a) for x, a in pts], fill=HERO, width=8, joint="curve")
    nx, ny = xy(*pts[-1])
    draw_balloon(P.CANVAS, nx, ny, 36, HERO, GROUND, burst=not b["rising"])
    if turn:
        tx, ty = xy(tx_km, turn)
        lab = "wind turns"
        lx = tx - 14 - P.text_w(d, lab, SMALL) if west_bend else tx + 14
        glow_text(d, (lx, ty - SMALL.size * 0.6), lab, SMALL, SOFT, GROUND)
    lab = "west      drift      east"
    d.text((x0 + cw / 2 - P.text_w(d, lab, SMALL) / 2, y + ch + 6), lab, font=SMALL, fill=SOFT)
    return y + ch + SMALL.size + 30


def draw_stats(d, x, y, w, stats):
    """Two big numbers with their caps under them, as the planes frame's height and speed."""
    sf = NUM
    cols = [max(P.text_w(d, v, sf), P.text_w(d, lab, CAPS), 200) for v, lab in stats]
    while sf.size > 64 and sum(cols) + 44 * (len(cols) - 1) > w:
        sf = P.font(TF["num"], sf.size - 4)
        cols = [max(P.text_w(d, v, sf), P.text_w(d, lab, CAPS), 170) for v, lab in stats]
    sx = x
    for (value, lab), cw in zip(stats, cols):
        d.text((sx, y), value, font=sf, fill=HERO)
        d.text((sx + 2, y + sf.size + 10), lab, font=CAPS, fill=SOFT)
        sx += cw + 44
    return y + sf.size + CAPS.size + 44


def draw_path(d, x, y, w, rise, sets, frac, icon):
    """Where it comes up and where it goes down, solid for the part it has crossed, with
    the thing itself on the line: the planes frame's progress bar, for the sky."""
    ly = y + 10
    fx = x + 22 + int((w - 44) * frac)
    d.line((fx, ly, x + w, ly), fill=FRAME, width=8)
    d.line((x, ly, fx, ly), fill=HERO, width=8)
    d.ellipse((x - 1, ly - 9, x + 17, ly + 9), fill=HERO)
    d.ellipse((x + w - 18, ly - 9, x + w, ly + 9), outline=SOFT, width=5, fill=GROUND)
    icons.paste(P.CANVAS, icons.glyph(icon, 50, HERO, 0, 6), fx, ly, GROUND)
    d.text((x, y + 40), rise, font=CAPS, fill=SOFT)
    d.text((x + w - P.text_w(d, sets, CAPS), y + 40), sets, font=CAPS, fill=SOFT)
    return y + 40 + CAPS.size + 30


def draw_year(d, sky, x0, y, width, bottom):
    """Hours of daylight through the year, today on it: where the year stands between the
    solstices. As a sparkline marks its extremes: the longest day's value above the peak,
    the shortest's below the trough, so the line never runs through either, months under."""
    pts = sky["year"]
    lo, hi = min(h for _, h in pts), max(h for _, h in pts)
    line_h = SMALL.size + 10
    top = y + line_h
    ch = min(150, bottom - top - 2 * line_h - 10)
    if ch < 70:
        return

    def xy(doy, h):
        return x0 + (doy - 1) / 365.0 * width, top + ch - (h - lo) / (hi - lo) * ch

    d.line([xy(*p) for p in pts], fill=SOFT, width=5, joint="curve")
    today = time.localtime(sky["t"]).tm_yday
    for (doy, h), above in ((max(pts, key=lambda p: p[1]), True), (min(pts, key=lambda p: p[1]), False)):
        if abs(doy - today) < 12:
            continue  # today is the extreme: its dot says so
        px_, py_ = xy(doy, h)
        lab = hm(h * 3600)
        lw = P.text_w(d, lab, SMALL)
        lx = min(max(px_ - lw / 2, x0), x0 + width - lw)
        d.text((lx, py_ - line_h - 2 if above else py_ + 10), lab, font=SMALL, fill=SOFT)
    for i, m in enumerate("JFMAMJJASOND"):
        mx = x0 + (i + 0.5) / 12.0 * width
        d.text((mx - P.text_w(d, m, SMALL) / 2, top + ch + line_h + 6), m, font=SMALL, fill=FRAME)
    tx, ty = xy(today, sky["day"]["length"] / 3600.0)
    d.ellipse((tx - 13, ty - 13, tx + 13, ty + 13), fill=HERO)


def draw_panel(d, sky):
    x0, x1 = PANEL_X, PANEL_R
    width = x1 - x0
    y = P.TEXT[1] - 6
    h = sky["hero"]
    for ln, f in P.wrap(d, h["head"], TF["head"], px(112), width, floor=px(64)):
        d.text((x0, y), ln, font=f, fill=HERO)
        y += f.size + 4
    y += 30
    if h["stats"]:
        y = draw_stats(d, x0, y, width, h["stats"])
    if h.get("path"):
        y = draw_path(d, x0, y + 14, width, *h["path"], icon=h.get("icon", "satellite"))
    if h["kind"] == "balloon":
        b = next(th for th in sky["things"] if th["kind"] == "balloon")
        y = draw_balloon_side(d, b, x0, y - 30, width)
    if h.get("foot"):
        ff = P.fit_font(d, h["foot"], TF["head"], px(66), width)
        d.text((x0, y), h["foot"], font=ff, fill=HERO)
        y += ff.size + 20

    bottom = P.TEXT[3] - 10
    if h.get("next"):
        # What's coming: the week's most wonderful thing, on the last line
        line = "Next: " + h["next"]
        f = P.fit_font(d, line, TF["name"], RUNG.size, width, floor=30)
        d.text((x0, bottom - f.size - 6), line, font=f, fill=THING)
        bottom -= f.size + 30
    if h["kind"] == "sun" and h["stats"]:
        draw_year(d, sky, x0, y + 20, width, bottom)
        return

    # How far away each thing named on the dome is, farthest first: a key to the dome, so
    # everything on one is on the other. Only in quiet moments: while something worth going
    # out for is on or coming within the hour, the panel stays on it. And whole or not at all
    if "wonder" in h and score(h, sky["t"]) >= 3:
        return
    items = sorted(NAMED, key=lambda i: i[1])
    top, gap = y + 30, 64
    if not items or len(items) > int((bottom - 10 - top) / gap):
        return
    # A rail with a stop for each, like a transit line: each dot level with its own name
    rail, lx = x0 + 12, x0 + 44
    mid = RUNG.size * 0.62
    d.line((rail, top + mid, rail, top + (len(items) - 1) * gap + mid), fill=FRAME, width=8)
    for i, (name, km, _kind) in enumerate(reversed(items)):
        ly = top + i * gap
        d.ellipse((rail - 13, ly + mid - 13, rail + 13, ly + mid + 13), fill=THING)
        d.text((lx, ly), name, font=RUNG, fill=THING)
        nw = P.text_w(d, name, RUNG)
        d.text((lx + nw + 14, ly + RUNG.size - KM.size - 1), P.fit(d, fmt_km(km), KM, x1 - lx - nw - 14),
               font=KM, fill=SOFT)


def render(data, t, note=None):
    sky = build(data, t)
    sky["hero"] = hero(sky)
    img = P.CANVAS = Image.new("L", (P.W, P.H), GROUND)
    d = P.CachedDraw(img)
    draw_dome(img, d, sky)
    draw_panel(d, sky)
    if note:
        # Bottom corner beside the dome, which the circle leaves empty
        d.text((SKY_BOX[2] - P.text_w(d, note, NOTE), P.TEXT[3] - NOTE.size - 6), note, font=NOTE, fill=SOFT)
    return img, sky


def layout():
    """The panel where the planes frame's style puts its story (`bold-right`: on the left),
    the dome in the map's place. Everything on the dome's rim is lettering (compass points,
    rise times), so the dome keeps to TEXT."""
    global PANEL_X, PANEL_R, DOME_X, DOME_Y, DOME_R, SKY_BOX
    t = P.TEXT
    pw = max(P.PANEL_W_CFG or 0, SKY_PANEL_W)
    if P.STYLES[P.STYLE].get("map_side") == "right":
        PANEL_X, PANEL_R = P.PANEL_X, P.PANEL_X + pw - 8
        SKY_BOX = (PANEL_R + 24, t[1], t[2], t[3])
    else:
        PANEL_X, PANEL_R = P.PANEL_R - pw + 8, P.PANEL_R
        SKY_BOX = (t[0], t[1], PANEL_X - 24, t[3])
    # The compass letters sit on the horizon itself, in gaps cut in the line, so the dome
    # only needs room for half a letter outside it
    DOME_R = int(min(SKY_BOX[2] - SKY_BOX[0], SKY_BOX[3] - SKY_BOX[1]) / 2 - 26)
    DOME_X = (SKY_BOX[0] + SKY_BOX[2]) // 2
    DOME_Y = (SKY_BOX[1] + SKY_BOX[3]) // 2


# ---------- live data ----------

CELESTRAK = "https://celestrak.org/NORAD/elements/gp.php?GROUP=%s&FORMAT=csv"
SONDEHUB = "https://api.v2.sondehub.org/sondes?lat=%.4f&lon=%.4f&distance=250000&last=1800"
ORBITS_PATH = os.path.join(HERE, "orbits.csv")
BALLOON_PATH = os.path.join(HERE, "balloon.json")
ORBITS_MAX_AGE = 20 * 3600    # CelesTrak asks for no more than one download every 2 hours
ORBITS_RETRY_S = 3 * 3600     # after a failed download, keep the old orbits (good for days)
# Radiosondes go up at 00 and 12 UTC everywhere (11:00 and 23:00 by the clock at Buffalo);
# a flight is up about two hours, then falls
BALLOON_WINDOWS = ((10.75, 14.0), (22.75, 26.0))
# Outside the windows, one look every 3 hours: research flights go up off the schedule, and
# pico balloons drift through at any hour. Every 30 minutes while a pico is in our sky
SONDE_CHECK_S = 3 * 3600
WINDOW_CHECK_S = 900
PICO_CHECK_S = 1800
AMATEUR = "https://api.v2.sondehub.org/amateur?lat=%.4f&lon=%.4f&distance=250000&last=7200"


def fetch_orbits(session, now):
    """The space stations, and the newest Starlink launch of the last 30 days: the one most
    likely to still be a train of lights. A few hundred objects instead of the whole fleet's
    ten thousand. CSV (OMM), not TLE: CelesTrak has no TLEs past catalog number 99999, which
    every launch since mid-2026 is. train_pass() decides whether it still looks like a train."""
    got = {}
    for group in ("stations", "last-30-days"):
        r = session.get(CELESTRAK % group, timeout=30)
        r.raise_for_status()
        if not r.text.startswith("OBJECT_NAME"):
            raise ValueError("not CelesTrak CSV: %r" % r.text[:60])
        got[group] = list(csv.DictReader(io.StringIO(r.text)))
    keep = [row for row in got["stations"] if row["OBJECT_NAME"] in ("ISS (ZARYA)", "CSS (TIANHE)")]
    if not keep:
        raise ValueError("no ISS in CelesTrak's stations")
    starlink = [row for row in got["last-30-days"] if row["OBJECT_NAME"].startswith("STARLINK")]
    if starlink:
        # OBJECT_ID is the launch: 2026-159A is the first object of 2026's 159th
        newest = max(row["OBJECT_ID"][:8] for row in starlink)
        keep += [row for row in starlink if row["OBJECT_ID"][:8] == newest]
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=list(got["stations"][0]), lineterminator="\n")
    w.writeheader()
    w.writerows(keep)
    text = out.getvalue()
    if not any(name.startswith("ISS") for name, _ in astro.read_orbits(text)):
        raise ValueError("CelesTrak's ISS row doesn't parse")
    try:
        with open(ORBITS_PATH + ".tmp", "w") as f:
            f.write(text)
        os.replace(ORBITS_PATH + ".tmp", ORBITS_PATH)
    except OSError:
        pass  # Drive Mode: keep them in memory, the next download saves them
    return text


def in_balloon_window(now):
    h = time.gmtime(now).tm_hour + time.gmtime(now).tm_min / 60.0
    return any(a <= h < b or a <= h + 24 < b for a, b in BALLOON_WINDOWS)


def fetch_balloon(session, now, balloon):
    """The nearest radiosonde heard in the last half hour, its track built up one fetch at a
    time (5 minutes apart is enough to show the wind turning with height)."""
    r = session.get(SONDEHUB % (P.HOME_LAT, P.HOME_LON), timeout=20)
    r.raise_for_status()
    fresh = []
    for f in r.json().values():
        try:
            when = calendar.timegm(time.strptime(f["datetime"][:19], "%Y-%m-%dT%H:%M:%S"))
        except (KeyError, ValueError):
            continue
        if now - when < 900:
            fresh.append((P.distance_bearing(P.HOME_LAT, P.HOME_LON, f["lat"], f["lon"])[0], when, f))
    if not fresh:
        return balloon if balloon and now - balloon["track"][-1][0] < 1200 else None
    _, when, f = min(fresh, key=lambda x: x[0])
    if not balloon or balloon["serial"] != f["serial"]:
        balloon = dict(serial=f["serial"], track=[], burst_alt=0)
    if not balloon["track"] or when > balloon["track"][-1][0]:
        balloon["track"].append([round(when), round(f["lat"], 4), round(f["lon"], 4), round(f["alt"])])
    balloon.update(vel_v=f.get("vel_v"), temp=f.get("temp"), burst_alt=max(balloon["burst_alt"], round(f["alt"])))
    return balloon


def fetch_amateur(session, now):
    """The nearest amateur balloon aloft within 250 km and heard in the last two hours. The
    long-duration picos report how many days they've been up."""
    r = session.get(AMATEUR % (P.HOME_LAT, P.HOME_LON), timeout=20)
    r.raise_for_status()
    near = []
    for f in r.json().values():
        f = f if "lat" in f else list(f.values())[-1]
        try:
            when = calendar.timegm(time.strptime(f["datetime"][:19], "%Y-%m-%dT%H:%M:%S"))
            if now - when > 7200 or f["alt"] < 3000:
                continue
            near.append((P.distance_bearing(P.HOME_LAT, P.HOME_LON, f["lat"], f["lon"])[0], dict(
                call=f.get("payload_callsign", "?"), lat=round(f["lat"], 4), lon=round(f["lon"], 4),
                alt=round(f["alt"]), when=when, days=int(float(f["days_aloft"])) if f.get("days_aloft") else None)))
        except (KeyError, TypeError, ValueError):
            continue
    return min(near, key=lambda n: n[0])[1] if near else None


def next_balloon_window(now):
    """Epoch when the next balloon window opens."""
    day = now - now % 86400
    starts = [day + k * 86400 + a * 3600 for k in (0, 1) for a, _ in BALLOON_WINDOWS]
    return min(t for t in starts if t > now)


class Frame:
    """The sky frame for loop.run. Wi-Fi goes on only when something is due: orbits once a
    day, and the balloon every 5 minutes around its launches. The rest is computed here, so
    in between it just redraws, every 10 minutes, or every minute while something crosses.
    At night (config "night") it fetches nothing and redraws at each half-hourly wake."""

    idle_redraw_s = 600

    def __init__(self, args):
        self.args, self.log, self.fetch_log = args, {}, {}
        self.sky = {}
        try:
            with open(ORBITS_PATH) as f:
                self.orbits = f.read()
            self.orbits_at = os.path.getmtime(ORBITS_PATH)
        except OSError:
            self.orbits, self.orbits_at = "", 0
        self.orbits_tried = 0
        self.sondes_at, self.amateur = 0, None
        try:
            with open(BALLOON_PATH) as f:
                self.balloon = json.load(f)
        except (OSError, ValueError):
            self.balloon = None

    def configure(self, args):
        cfg = P.load_config(args)
        layout()
        return cfg

    def orbits_due(self):
        return max(self.orbits_at + ORBITS_MAX_AGE, self.orbits_tried + ORBITS_RETRY_S)

    def fetch(self, session, now):
        """Orbits when a day old, the balloon around launches. A dead link raises, so the
        loop backs off and recovers Wi-Fi; a bad answer from a server waits for next time."""
        self.fetch_log = {}
        if now >= self.orbits_due():
            try:
                self.orbits, self.orbits_at = fetch_orbits(session, now), now
                self.fetch_log["orbits"] = 1
            except (requests.ConnectionError, requests.Timeout):
                raise
            except (requests.RequestException, ValueError, KeyError) as e:
                self.orbits_tried = now
                print("orbits fetch failed: %r" % e, flush=True)
        if self.balloons_due(now) <= now:
            try:
                self.balloon = fetch_balloon(session, now, self.balloon)
                P.write_json(BALLOON_PATH, self.balloon)
                self.fetch_log["balloon"] = int(bool(self.balloon))
                self.amateur = fetch_amateur(session, now)
                self.fetch_log["pico"] = int(bool(self.amateur))
            except (requests.ConnectionError, requests.Timeout):
                raise
            except (requests.RequestException, ValueError, KeyError) as e:
                print("balloon fetch failed: %r" % e, flush=True)
            self.sondes_at = now
        if self.args.save_sample:
            with open(self.args.save_sample, "w") as f:
                json.dump(self.data(now), f)

    def data(self, now):
        return {"time": now, "orbits": self.orbits, "balloon": self.balloon, "amateur": self.amateur}

    def balloons_due(self, now):
        # In a launch window, every 15 minutes until one is up; then every 5 to draw its climb,
        # every minute on a charger, where Wi-Fi is up anyway
        if self.balloon:
            return self.sondes_at + (60 if getattr(self, "plugged", False) else P.FETCH_BUSY_S)
        if in_balloon_window(now):
            return self.sondes_at + WINDOW_CHECK_S
        return min(next_balloon_window(now), self.sondes_at + (PICO_CHECK_S if self.amateur else SONDE_CHECK_S))

    def fetch_every(self, now):
        return max(60, min(self.orbits_due(), self.balloons_due(now)) - now)

    def render(self, now, fetched_at, note=None):
        img, self.sky = render(self.data(now), now, note)
        self.log = {"things": len(self.sky["things"])}
        return img

    def moving(self, now):
        """Minute redraws while a pass or train is on: they cross the sky in minutes. Not for
        balloons, which only move when new data comes in, every 5 minutes with the fetch."""
        tr = self.sky.get("train")
        return any(ps["rise"] - 1800 <= now <= ps["set"] for _, ps in self.sky.get("passes", [])) or \
            bool(tr and tr["start"] - 900 <= now <= tr["end"])

    def in_night(self, now):
        return P.in_night(now)

    def next_morning(self, now):
        return P.next_morning(now)

    def night_key(self, now, mode):
        return mode + str(int(now // loop.NIGHT_WAKE_S))

    def render_night(self, now, mode):
        return self.render(now, 0, note="Battery low" if mode == "low" else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="render one frame and exit")
    ap.add_argument("--out", help="write PNG here instead of pushing to the screen")
    ap.add_argument("--sample", help="render from a saved {time, orbits or tle, balloon} JSON instead of the network")
    ap.add_argument("--save-sample", help="also write the fetched data to this JSON (for design testing)")
    ap.add_argument("--time", type=float, help="with --sample: unix time to render instead of the sample's")
    ap.add_argument("--heading", type=float, help="compass direction the viewer faces (0-359)")
    ap.add_argument("--rotate", type=int, choices=(0, 90, 180, 270), help="clockwise turn onto the panel")
    ap.add_argument("--panel", help="preview another Kindle's panel, portrait WxH (758x1024 for a PW2)")
    ap.add_argument("--config", help="read this instead of the config.json beside sky.py")
    args = ap.parse_args()
    args.style = None
    if args.panel:
        loop.PANEL = tuple(int(v) for v in args.panel.split("x"))
    P.load_config(args)
    layout()

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    if args.sample:
        with open(args.sample) as f:
            data = json.load(f)
        img, sky = render(data, args.time or data["time"])
        path = args.out or "/tmp/planes.pgm"
        loop.turn(img, P.ROTATE).save(path)
        print(path, "sun %.1f°" % sky["sun_el"], len(sky["things"]), "things")
        return

    loop.run(Frame(args), args)


if __name__ == "__main__":
    main()
