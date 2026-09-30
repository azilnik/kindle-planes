#!/usr/bin/env python3
"""The sky frame: everything above the house. The sky as you'd see it lying on the lawn
looking up (zenith in the middle, north up, east on the left), with planes, the nearest
weather balloon, the ISS and fresh Starlink trains, the Moon, planets and stars on it, a
headline for the one thing worth looking up for, and a ladder of how far away each is.

Data: planes from the planes frame's ADS-B fetch; satellite orbits from CelesTrak once a
day; the balloon from SondeHub around the twice-daily launches (Buffalo's, from Toronto). The Sun, Moon, planets and
stars are computed on the device, so the sky still draws with no network at all.

Preview:  python planes/sky.py --sample planes/samples/sky/night.json --out out/sky.png
Run:      python planes/sky.py   (run.sh starts it when config.json says "frame": "sky")
"""

import argparse
import calendar
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
BODY = P.font("Inter-SemiBold.ttf", 40)
# Things down to this far below the horizon show outside the dome as ghosts
BELOW = 30
# Page colors: paper by day, the whole page goes dark with the sky
DAY = dict(bg=P.PAPER, fg=P.INK, dim=P.DIM, faint=P.FAINT, bar=P.FAINT_BAR)
NIGHT = dict(bg=0, fg=P.PAPER, dim=170, faint=110, bar=64)
T = DAY


# ---------- where things are ----------

def dome_xy(el, az):
    """Azimuthal equidistant, looking up: zenith at center, north up, east left."""
    r = DOME_R * (90 - el) / 90
    a = math.radians(az - P.HEADING)
    return DOME_X - r * math.sin(a), DOME_Y - r * math.cos(a)


def seen_from_home(lat, lon, alt_km):
    """Elevation, azimuth and straight-line km to something at a height, allowing for the
    curve of the Earth (it drops 1.3 km over the horizon at the balloon's 130 km)."""
    dist, brg = P.distance_bearing(P.HOME_LAT, P.HOME_LON, lat, lon)
    rise = alt_km - dist * dist / (2 * 6371)
    return math.degrees(math.atan2(rise, max(dist, 0.01))), brg, math.hypot(dist, alt_km)


def mag_limit(sun_el):
    """Faintest star worth drawing: none in daylight, all of the catalog by astronomical dark."""
    if sun_el > -5:
        return None
    return 1.5 + 3.0 * min(1.0, (-5 - sun_el) / 12)


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

    for p in data["planes"]:
        el, az, rng = seen_from_home(p["lat"], p["lon"], p["alt"] * 0.0003048)
        if el > 2:
            add(dict(kind="plane", name=p["name"], el=el, az=az, km=rng, track=p["track"], alt=p["alt"]))

    b = data.get("balloon")
    if b:
        _, lat_b, lon_b, alt_m = b["track"][-1]
        el, az, rng = seen_from_home(lat_b, lon_b, alt_m / 1000)
        add(dict(kind="balloon", name="Weather balloon", el=el, az=az, km=rng, alt_km=alt_m / 1000,
                 rising=(b.get("vel_v") or 0) > 0, burst_km=b.get("burst_alt", 0) / 1000,
                 track=b["track"]))

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
    tle = data["tle"]
    sats = kept("sats", t, tle, 86400, lambda: {
        "stations": [(n, s) for n, s in astro.read_tles(tle) if n.startswith(("ISS", "CSS"))],
        "fleet": [s for n, s in astro.read_tles(tle) if n.startswith("STARLINK")]})
    for name, sat in sats["stations"]:
        look = astro.sat_look(sat, t, lat, lon)
        if look and look[0] >= 10:
            add(dict(kind="station", name="ISS" if name.startswith("ISS") else "Tiangong",
                     el=look[0], az=look[1], km=look[2], lit=look[4]))
    iss = next((s for n, s in sats["stations"] if n.startswith("ISS")), None)
    # Pass searches are the costly part: redo them every half hour or once a pass is over
    sky["pass"] = kept("pass", t, tle, 1800, lambda: astro.next_visible_pass(iss, t, lat, lon) if iss else None,
                       ends=lambda ps: ps["set"])
    sky["train"] = tr = kept("train", t, tle, 600, lambda: train_pass(sats["fleet"], t, lat, lon),
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


def crossing(el_at, t, rising, span=18 * 3600, step=120):
    """When something next rises over (or sets below) the horizon, to two minutes."""
    return next((tt for tt in range(int(t), int(t) + span, step) if (el_at(tt) > 0) == rising), None)


# ---------- drawing ----------

def star_dot(img, d, x, y, mag, fill):
    if mag < 0.6:
        # The handful of brightest stars twinkle
        icons.paste(img, icons.glyph("sparkle", 18, fill), x, y, 0)
        return
    r = max(1.2, 4.6 - mag * 0.95)
    d.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def inside(x, y, pad=0):
    return math.hypot(x - DOME_X, y - DOME_Y) <= DOME_R - pad


def star_layer(t, limit, line_fill, star_fill):
    """Constellation lines and stars on black, for lightening onto the night dome. The sky
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

    for seg in SKY["lines"]:
        pts = [xy(ra, dec) for ra, dec in seg]
        for a, b in zip(pts, pts[1:]):
            if a and b:
                d.line((a, b), fill=line_fill, width=2)
    for ra, dec, mag in SKY["stars"]:
        if mag <= limit:
            p = xy(ra, dec)
            if p:
                star_dot(layer, d, p[0], p[1], mag, star_fill)
    return layer


def draw_stars(img, d, t, limit, name_fill, line_fill, star_fill, taken):
    # In half magnitudes, so twilight deepening doesn't redraw the field every minute
    limit = round(limit * 2) / 2
    layer = kept("stars", t, (limit, DOME_X, DOME_Y, DOME_R, P.HEADING), 600,
                 lambda: star_layer(t, limit, line_fill, star_fill))
    box = (DOME_X - DOME_R, DOME_Y - DOME_R, DOME_X + DOME_R + 1, DOME_Y + DOME_R + 1)
    img.paste(ImageChops.lighter(img.crop(box), layer), box[:2])
    # Names are few and go where the moment's marks leave room, so they're placed each frame
    for ra, dec, name in SKY["names"]:
        el, az = astro.alt_az(ra, dec, t, P.HOME_LAT, P.HOME_LON)
        if el <= 0:
            continue
        p = dome_xy(el, az)
        if inside(*p, 40):
            w = P.text_w(d, name, P.F["tiny"])
            lx = p[0] + 9 if p[0] < DOME_X + DOME_R / 2 else p[0] - 9 - w
            d.text((lx, p[1] - 12), name, font=P.F["tiny"], fill=name_fill)
            taken.append((lx - 6, p[1] - 16, lx + w + 6, p[1] + 16))


def moon_near(things, x, y):
    """True when the moon is close enough that a planet's name goes on the moon's label."""
    return any(math.hypot(*(a - b for a, b in zip(dome_xy(m["el"], m["az"]), (x, y)))) < 72
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


def side_label(d, x, y, off, s, f, fill, bg, dy=0):
    """Label beside a mark, trying the side facing the dome's center first, then the
    other side, above and below, so labels on the dome never sit on one another."""
    w, h = P.text_w(d, s, f), f.size
    inward = x < DOME_X
    spots = [(x + off, y - h * 0.6 + dy), (x - off - w, y - h * 0.6 + dy)]
    if not inward:
        spots.reverse()
    spots += [(x - w / 2, y - off - h * 1.2), (x - w / 2, y + off)]
    # Crowded (the moon beside a planet at moonrise): step further out along the inward side
    step = 1 if inward else -1
    spots += [(x + step * (off + k * 24) - (0 if inward else w), y + dy2) for k in (1, 2, 3) for dy2 in (h, -2 * h)]
    def ok(lx, ly, clear):
        box = (lx - 4, ly - 2, lx + w + 4, ly + h * 1.2)
        return inside(lx, ly + h / 2, 4) and inside(lx + w, ly + h / 2, 4) and not (clear and any(
            box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in TAKEN))

    # Clear of everything if possible, else at least on the dome
    lx, ly = next((sp for sp in spots if ok(sp[0], sp[1], True)), None) or \
        next((sp for sp in spots if ok(sp[0], sp[1], False)), spots[0])
    box = (lx - 4, ly - 2, lx + w + 4, ly + h * 1.2)
    TAKEN.append(box)
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


def draw_dome(img, d, sky):
    night = sky["sun_el"] < -5
    dome, ink = T["bg"], T["fg"]
    R = DOME_R
    ghost = 120
    # Solid page, sky and ground alike: only the horizon line says where the sky ends
    d.ellipse((DOME_X - R, DOME_Y - R, DOME_X + R, DOME_Y + R), outline=140 if night else P.FAINT, width=3)

    things = sky["things"]
    del TAKEN[:]
    for th in [th for th in things if not th.get("below")]:
        # Marks claim their space before any label goes down, and the moon and planets
        # hold room for their names so a star's name doesn't take it
        x, y = dome_xy(th["el"], th["az"])
        if th["kind"] == "balloon":
            TAKEN.append((x - 24, y - 26, x + 24, y + 26))
            continue
        r = {"moon": 28, "station": 34, "sun": 30, "train": 14, "planet": 14}.get(th["kind"], 8)
        TAKEN.append((x - r, y - r, x + r, y + r))
    held = [(x - 130, y - 40, x + 130, y + 40) for x, y in
            (dome_xy(th["el"], th["az"]) for th in things if th["kind"] in ("moon", "planet") and not th.get("below"))]
    limit = mag_limit(sky["sun_el"])
    if limit:
        draw_stars(img, d, sky["t"], limit, 150, 64, P.PAPER, TAKEN + held)
    sun_ra, sun_dec, _ = astro.sun(sky["t"])
    sel, saz = astro.alt_az(sun_ra, sun_dec, sky["t"], P.HOME_LAT, P.HOME_LON)
    sun_xy = dome_xy(sel, saz)  # off the dome when it's down, which still points the right way

    # Home: straight up, the same plain crosshair as the planes map
    r = 13
    d.line((DOME_X - r, DOME_Y, DOME_X + r, DOME_Y), fill=ink, width=3)
    d.line((DOME_X, DOME_Y - r, DOME_X, DOME_Y + r), fill=ink, width=3)

    # Things below the horizon, ghosted on the ground outside it
    for th in [th for th in things if th.get("below")]:
        x, y = dome_xy(th["el"], th["az"])
        if not (SKY_BOX[0] + 30 < x < SKY_BOX[2] - 30 and SKY_BOX[1] + 30 < y < SKY_BOX[3] - 30):
            continue
        if th["kind"] == "moon":
            icons.paste(img, moon_icon(22, th["frac"], th["waxing"], x, y, sun_xy, True, ghost), x, y, dome)
        else:
            rr = 16 if th["kind"] == "sun" else 6
            d.ellipse((x - rr, y - rr, x + rr, y + rr), outline=ghost, width=3)
        lab = th["name"] + (" rises " + clock(th["rises"]) if th.get("rises") else "")
        w = P.text_w(d, lab, P.F["tiny"])
        lx = min(max(x - w / 2, SKY_BOX[0] + 8), SKY_BOX[2] - 8 - w)
        d.text((lx, y + 24), lab, font=P.F["tiny"], fill=ghost)

    for th in [th for th in things if not th.get("below")]:
        x, y = dome_xy(th["el"], th["az"])
        if th["kind"] == "moon":
            icons.paste(img, moon_icon(26, th["frac"], th["waxing"], x, y, sun_xy, night), x, y, dome)
            near = [p["name"] for p in things if p["kind"] == "planet" and not p.get("below")
                    and math.hypot(*(a - b for a, b in zip(dome_xy(p["el"], p["az"]), (x, y)))) < 72]
            side_label(d, x, y, 36, " & ".join(["Moon"] + near), P.F["small"], ink, dome, dy=-30)
        elif th["kind"] == "planet":
            # Ringed for the giants, a sparkle for Venus, a plain dot for Mars
            icon = {"Venus": ("sparkle", 26), "Mars": ("dot", 12)}.get(th["name"], ("planet", 30))
            icons.paste(img, icons.glyph(icon[0], icon[1], ink), x, y, dome)
            if not moon_near(things, x, y):
                side_label(d, x, y, 18, th["name"], P.F["small"], ink, dome, dy=4)
        elif th["kind"] == "sun":
            icons.paste(img, icons.glyph("sun", 56, ink), x, y, dome)
            side_label(d, x, y, 40, "Sun", P.F["small"], ink, dome)

    tr = sky.get("train")
    if tr:
        # The path they all follow, thin, and a bead for each one up right now
        path = [dome_xy(k[1], k[2]) for k in tr["track"]]
        dash_line(d, path, ink, width=3, on=8, off=10)
        beads = [dome_xy(th["el"], th["az"]) for th in things if th["kind"] == "train"]
        for x, y in beads:
            icons.paste(img, icons.glyph("satellite", 24, ink), x, y, dome)
        at = min(beads, key=lambda b: b[1]) if beads else path[len(path) // 2]
        side_label(d, at[0], at[1], 22, "Starlink", P.F["label"], ink, dome)

    for th in sorted((th for th in things if th["kind"] == "plane"), key=lambda th: th["km"])[:12]:
        x, y = dome_xy(th["el"], th["az"])
        # Mirrored like the rest of the view from below, so turn by minus the track
        turn = int(round((-(th["track"] or 0) + P.HEADING) % 360 / 5.0)) * 5
        icons.paste(img, icons.glyph("plane", 32, ink, turn), x, y, dome)

    b = next((th for th in things if th["kind"] == "balloon"), None)
    if b:
        # Nudged up off the horizon line when it's very low, so the whole icon shows
        x, y = dome_xy(max(b["el"], 5), b["az"])
        draw_balloon(img, x, y, 46, ink, dome, burst=not b["rising"])
        side_label(d, x, y, 30, "Balloon", P.F["label"], ink, dome)

    ps = sky.get("pass")
    if ps and ps["rise"] <= sky["t"] + 3600:
        pts = [(k[0], dome_xy(k[1], k[2])) for k in ps["track"]]
        # Heavy enough to survive e-ink: flown part solid, the rest in long dashes
        flown = [p for tt, p in pts if tt <= sky["t"]]
        ahead = [p for tt, p in pts if tt > sky["t"]]
        if flown and ahead:
            ahead.insert(0, flown[-1])
        if len(flown) > 1:
            d.line(flown, fill=ink, width=8, joint="curve")
        dash_line(d, ahead, ink, width=6, on=18, off=12)
        # Arrowhead where it leaves
        (xa, ya), (xb, yb) = pts[-2][1], pts[-1][1]
        ang = math.atan2(yb - ya, xb - xa)
        d.polygon([(xb + 26 * math.cos(ang), yb + 26 * math.sin(ang)),
                   (xb + 20 * math.cos(ang + 2.4), yb + 20 * math.sin(ang + 2.4)),
                   (xb + 20 * math.cos(ang - 2.4), yb + 20 * math.sin(ang - 2.4))], fill=ink)
    for th in things:
        if th["kind"] == "station":
            x, y = dome_xy(th["el"], th["az"])
            icon = icons.glyph("satellite", 60, ink)
            icons.paste(img, icon, x, y, dome)
            side_label(d, x, y - 4, icon[0].width // 2 + 10, th["name"], P.F["blabel"], ink, dome)

    # Compass letters around the dome
    for lab, az in (("N", 0), ("E", 90), ("S", 180), ("W", 270)):
        x, y = dome_xy(-5, az)
        w = P.text_w(d, lab, P.F["label"])
        d.text((x - w / 2, y - 18), lab, font=P.F["label"], fill=T["dim"])


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


def pass_lines(ps):
    return "rises %s %s, gone %s %s" % (P.compass(ps["rise_az"]), clock(ps["rise"]),
                                        P.compass(ps["set_az"]), clock(ps["set"]))


def hero(sky):
    """The one thing worth looking up for, in priority order: (its kind, headline, two lines)."""
    t, ps, things, tr = sky["t"], sky.get("pass"), sky["things"], sky.get("train")
    up = "overhead" if ps and ps["peak_el"] > 60 else "%d° up" % (ps["peak_el"] if ps else 0)
    iss_now = ps and ps["rise"] - 300 <= t <= ps["set"]
    if tr and not iss_now:
        return "train", "Starlink train", "%d satellites in a line" % tr["n"], \
            "%s to %s, %s–%s" % (P.compass(tr["rise_az"]), P.compass(tr["set_az"]), clock(tr["start"]), clock(tr["end"]))
    if ps and ps["rise"] - 2700 <= t <= ps["set"]:
        mins = (ps["peak"] - t) / 60
        if ps["rise"] - t > 5 * 60:
            return "station", "ISS at %s" % clock(ps["peak"]), "%s · in %d min" % (up, round(mins)), pass_lines(ps)
        when = "overhead now" if abs(mins) < 0.75 else ("in %d min" % round(mins) if mins > 0 else "going away")
        head = "ISS overhead" if ps["peak_el"] > 60 else "ISS pass"
        return "station", head, "%s · peaks %d° up" % (when, ps["peak_el"]), pass_lines(ps)
    b = next((th for th in things if th["kind"] == "balloon"), None)
    if b:
        return "balloon", "Weather balloon", "%.0f km up, %s" % (b["alt_km"], "climbing" if b["rising"] else "falling"), \
            "from %s · look %s, %d° up" % (launch_site(b["track"][0]), P.compass(b["az"]), b["el"])
    moon = next((th for th in things if th["kind"] == "moon" and not th.get("below")), None)
    if moon and sky["sun_el"] < 0:
        return "moon", moon_phase(moon["frac"], moon["waxing"]), \
            "%d° up in the %s" % (moon["el"], P.compass(moon["az"])), \
            "sets %s" % when_clock(moon["sets"], t) if moon.get("sets") else ""
    if ps:
        return "station", "Next ISS pass", "%s · %s" % (when_clock(ps["peak"], t), up), pass_lines(ps)
    return None, "Clear above", "", ""


def launch_site(fix):
    """Where the balloon went up: by name for the sites people know, else by distance."""
    for name, lat, lon in SONDE_SITES:
        if P.distance_bearing(lat, lon, fix[1], fix[2])[0] < 40:
            return name
    dist, brg = P.distance_bearing(P.HOME_LAT, P.HOME_LON, fix[1], fix[2])
    return "%d km %s" % (round(dist, -1), P.compass(brg))


SONDE_SITES = (("Buffalo", 42.94, -78.72), ("Detroit", 42.70, -83.47), ("Albany", 42.69, -73.83),
               ("Maniwaki", 46.30, -76.01), ("Pittsburgh", 40.53, -80.22))


def ladder_items(sky):
    items, things = [], sky["things"]
    planes = sorted((th for th in things if th["kind"] == "plane"), key=lambda th: th["km"])
    if planes:
        items.append((planes[0]["name"], planes[0]["km"], "plane"))
    for kind in ("balloon", "station", "train", "moon", "sun", "planet"):
        for th in sorted((th for th in things if th["kind"] == kind and not th.get("below")), key=lambda th: th["km"])[:1]:
            items.append((th["name"], th["km"], kind))
    if mag_limit(sky["sun_el"]):
        # The farthest thing you can see tonight: the named star closest to the zenith
        best = max(SKY["names"], key=lambda s: astro.alt_az(s[0], s[1], sky["t"], P.HOME_LAT, P.HOME_LON)[0])
        items.append((best[2], STAR_LY.get(best[2], 100) * KM_PER_LY, "star"))
    return sorted(items, key=lambda i: i[1])


# Distances of the named stars, light-years (for the ladder's top rung)
STAR_LY = {"Vega": 25, "Deneb": 2600, "Altair": 17, "Arcturus": 37, "Capella": 43, "Aldebaran": 65,
           "Polaris": 430, "Betelgeuse": 550, "Rigel": 860, "Sirius": 8.6, "Procyon": 11.5,
           "Pollux": 34, "Castor": 51, "Regulus": 79, "Spica": 250, "Antares": 550, "Fomalhaut": 25}


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
    cw, ch = width - P.text_w(d, "30 km", P.F["tiny"]) - 16, 150
    turn = wind_turn(pts)
    tx_km = next(x for x, a in pts if a >= turn) if turn else None
    xs = [x for x, _ in pts]
    lo_km, hi_km = min(xs), max(xs)
    # Room for "wind turns" on the outside of the bend, where the line isn't
    room = P.text_w(d, "wind turns", P.F["tiny"]) + 24
    west_bend = turn is not None and tx_km - lo_km < hi_km - tx_km
    lpad, rpad = (room, 16) if west_bend else (16, room if turn else 16)
    per_km = min((cw - lpad - rpad) / max(hi_km - lo_km, 0.1), cw / 8.0)  # small drifts stay small
    mid = (lo_km + hi_km) / 2
    cx = x0 + lpad + (cw - lpad - rpad) / 2

    def xy(x, alt):
        return cx + (x - mid) * per_km, y + ch - alt / top_km * ch

    for km in (10, 20, 30):
        gy = xy(0, km)[1]
        d.line((x0, gy, x0 + cw, gy), fill=T["bar"], width=1)
        d.text((x0 + cw + 10, gy - 12), "%d km" % km, font=P.F["tiny"], fill=T["dim"])
    d.line((x0, y + ch, x0 + cw, y + ch), fill=T["faint"], width=2)
    d.line([xy(x, a) for x, a in pts], fill=T["fg"], width=4, joint="curve")
    nx, ny = xy(*pts[-1])
    draw_balloon(P.CANVAS, nx, ny, 28, T["fg"], T["bg"], burst=not b["rising"])
    if turn:
        tx, ty = xy(tx_km, turn)
        lab = "wind turns"
        lx = tx - 14 - P.text_w(d, lab, P.F["tiny"]) if west_bend else tx + 14
        d.text((lx, ty - 12), lab, font=P.F["tiny"], fill=T["dim"])
    lab = "west      drift      east"
    d.text((x0 + cw / 2 - P.text_w(d, lab, P.F["tiny"]) / 2, y + ch + 6), lab, font=P.F["tiny"], fill=T["dim"])
    return y + ch + 34


def draw_panel(d, sky):
    x0, x1 = PANEL_X, P.TEXT[2]
    width = x1 - x0
    y = P.TEXT[1] + 4
    kind, head, sub, line = hero(sky)
    hf = P.fit_font(d, head, "InterDisplay-Bold.ttf", 76, width)
    d.text((x0 - 3, y), head, font=hf, fill=T["fg"])
    y += hf.size + 18
    if sub:
        d.text((x0, y), P.fit(d, sub, BODY, width), font=BODY, fill=T["fg"])
        y += 52
    if line:
        d.text((x0, y), P.fit(d, line, P.F["small"], width), font=P.F["small"], fill=T["dim"])
        y += 40

    if kind == "balloon":
        b = next(th for th in sky["things"] if th["kind"] == "balloon")
        y = draw_balloon_side(d, b, x0, y + 10, width) + 14

    # How far: log scale, far at the top, one rung per kind of thing
    items = ladder_items(sky)
    top, bot = y + 50, P.TEXT[3] - 20
    lo, hi = 0.0, 15.0  # 1 km .. 10^15 km (about 100 light-years)

    def ypos(km):
        return bot - (math.log10(max(km, 1)) - lo) / (hi - lo) * (bot - top)

    rail = x0 + 14
    d.line((rail, top, rail, bot), fill=T["bar"], width=4)
    # Space labels at least a rung apart, keeping them in order
    gap, rows = min(58, (bot - top) / max(1, len(items) - 1)), []
    for name, km, kind in reversed(items):
        want = ypos(km)
        rows.append([name, km, kind, want, want])
    for i, r in enumerate(rows):
        if i and r[4] < rows[i - 1][4] + gap:
            r[4] = rows[i - 1][4] + gap
    if rows and rows[-1][4] > bot:
        rows[-1][4] = bot
        for i in range(len(rows) - 2, -1, -1):
            if rows[i][4] > rows[i + 1][4] - gap:
                rows[i][4] = rows[i + 1][4] - gap
    for name, km, _kind, dot_y, lab_y in rows:
        d.ellipse((rail - 9, dot_y - 9, rail + 9, dot_y + 9), fill=T["fg"])
        lx = rail + 40
        d.line((rail + 10, dot_y, lx - 8, lab_y), fill=T["faint"], width=2)
        d.text((lx, lab_y - 22), name, font=P.F["label"], fill=T["fg"])
        nw = P.text_w(d, name, P.F["label"])
        d.text((lx + nw + 12, lab_y - 16), P.fit(d, fmt_km(km), P.F["small"], x1 - lx - nw - 12),
               font=P.F["small"], fill=T["dim"])


def render(data, t, note=None):
    global T
    sky = build(data, t)
    T = NIGHT if sky["sun_el"] < -5 else DAY
    img = P.CANVAS = Image.new("L", (P.W, P.H), T["bg"])
    d = P.CachedDraw(img)
    draw_dome(img, d, sky)
    draw_panel(d, sky)
    if note:
        d.text((P.TEXT[0], P.TEXT[3] - 36), note, font=P.F["small"], fill=T["dim"])
    return img, sky


def layout():
    """The dome on one side, the panel on the other, inside `safe`. Everything on the dome's
    rim is lettering (compass points, rise times), so it all keeps to TEXT."""
    global PANEL_X, DOME_X, DOME_Y, DOME_R, SKY_BOX
    x0, y0, x1, y1 = P.TEXT
    PANEL_X = x1 - (P.PANEL_W_CFG or PANEL_W)
    SKY_BOX = (x0, y0, PANEL_X - 40, y1)
    # Room outside the horizon for the compass letters, which now sit on the ground
    DOME_R = int(min(SKY_BOX[2] - x0, y1 - y0) / 2 - 30)
    DOME_X = (x0 + SKY_BOX[2]) // 2
    DOME_Y = (y0 + y1) // 2


PANEL_W = 450


# ---------- live data ----------

CELESTRAK = "https://celestrak.org/NORAD/elements/gp.php?GROUP=%s&FORMAT=tle"
SONDEHUB = "https://api.v2.sondehub.org/sondes?lat=%.4f&lon=%.4f&distance=250000&last=1800"
TLE_PATH = os.path.join(HERE, "tle.txt")
BALLOON_PATH = os.path.join(HERE, "balloon.json")
TLE_MAX_AGE = 20 * 3600   # CelesTrak asks for no more than one download every 2 hours
TLE_RETRY_S = 3 * 3600    # after a failed download, keep the old orbits (good for days)
TRAIN_DAYS = 12           # a launch still reads as a train of lights for a week or two
# Radiosondes go up at 00 and 12 UTC everywhere (11:00 and 23:00 by the clock at Buffalo);
# a flight is up about two hours, then falls
BALLOON_WINDOWS = ((10.75, 14.0), (22.75, 26.0))
QUIET_FETCH_S = 900


def tle_epoch(line1):
    yy, day = int(line1[18:20]), float(line1[20:32])
    return calendar.timegm((2000 + yy if yy < 57 else 1900 + yy, 1, 1, 0, 0, 0)) + (day - 1) * 86400


def trios(text):
    rows = [r.rstrip() for r in text.splitlines() if r.strip()]
    return [rows[i:i + 3] for i in range(0, len(rows) - 2, 3)
            if rows[i + 1].startswith("1 ") and rows[i + 2].startswith("2 ")]


def fetch_tles(session, now):
    """The space stations, and the newest Starlink launch while it's still young enough to
    be a train. Launches from the last 30 days rather than the whole Starlink fleet: a few
    hundred objects instead of ten thousand, and every train is in it."""
    got = {}
    for group in ("stations", "last-30-days"):
        r = session.get(CELESTRAK % group, timeout=30)
        r.raise_for_status()
        got[group] = trios(r.text)
    keep = [t for t in got["stations"] if t[0].strip() in ("ISS (ZARYA)", "CSS (TIANHE)")]
    if not keep:
        raise ValueError("no ISS in CelesTrak's stations")
    starlink = [t for t in got["last-30-days"] if t[0].startswith("STARLINK")]
    if starlink:
        # International designator: launch year and number, e.g. 26159 = the 159th of 2026
        newest = max(t[1][9:14] for t in starlink)
        group = [t for t in starlink if t[1][9:14] == newest]
        if now - min(tle_epoch(t[1]) for t in group) < TRAIN_DAYS * 86400:
            keep += group
    text = "\n".join(line for trio in keep for line in trio) + "\n"
    try:
        with open(TLE_PATH + ".tmp", "w") as f:
            f.write(text)
        os.replace(TLE_PATH + ".tmp", TLE_PATH)
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


class Frame:
    """The sky frame for loop.run. At night (config "night") it fetches nothing and
    redraws at each half-hourly wake: everything but the planes is computed on the device."""

    def __init__(self, args):
        self.args, self.log, self.fetch_log = args, {}, {}
        self.raw, self.sky = [], {}
        try:
            with open(TLE_PATH) as f:
                self.tle = f.read()
            self.tle_at = os.path.getmtime(TLE_PATH)
        except OSError:
            self.tle, self.tle_at = "", 0
        self.tle_tried = 0
        try:
            with open(BALLOON_PATH) as f:
                self.balloon = json.load(f)
        except (OSError, ValueError):
            self.balloon = None

    def configure(self, args):
        cfg = P.load_config(args)
        layout()
        return cfg

    def fetch(self, session, now):
        """Planes every time; orbits when a day old; the balloon only around launches.
        The extras never fail the fetch: the planes are what the loop's backoff is for."""
        self.fetch_log = {}
        if now - self.tle_at > TLE_MAX_AGE and now - self.tle_tried > TLE_RETRY_S:
            self.tle_tried = now
            try:
                self.tle, self.tle_at = fetch_tles(session, now), now
                self.fetch_log["tle"] = 1
            except (requests.RequestException, ValueError) as e:
                print("tle fetch failed: %r" % e, flush=True)
        if in_balloon_window(now) or self.balloon:
            try:
                self.balloon = fetch_balloon(session, now, self.balloon)
                P.write_json(BALLOON_PATH, self.balloon)
                self.fetch_log["balloon"] = int(bool(self.balloon))
            except (requests.RequestException, ValueError, KeyError) as e:
                print("balloon fetch failed: %r" % e, flush=True)
        self.raw = P.fetch_aircraft(session)
        self.fetch_log["planes"] = len(self.raw)
        if self.args.save_sample:
            with open(self.args.save_sample, "w") as f:
                json.dump(self.data(now), f)

    def data(self, now):
        return {"time": now, "planes": P.project(self.raw, now), "tle": self.tle, "balloon": self.balloon}

    def fetch_every(self, now):
        if self.balloon or in_balloon_window(now):
            return P.FETCH_BUSY_S
        return P.FETCH_S if P.project(self.raw, now) else QUIET_FETCH_S

    def render(self, now, fetched_at, note=None):
        img, self.sky = render(self.data(now), now, note)
        self.log = {"things": len(self.sky["things"])}
        return img

    def moving(self, now):
        """Minute redraws while planes are up, a pass or train is on, or a balloon flies;
        otherwise the stars' drift is fine at the fetch's pace."""
        if P.project(self.raw, now) or self.balloon:
            return True
        ps, tr = self.sky.get("pass"), self.sky.get("train")
        return bool((ps and ps["rise"] - 1800 <= now <= ps["set"]) or (tr and tr["start"] - 900 <= now <= tr["end"]))

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
    ap.add_argument("--sample", help="render from a saved {time, planes, tle, balloon} JSON instead of the network")
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
