# kindle-planes

**A Kindle in a picture frame that shows the planes overhead.**

<img alt="A light wood picture frame on a kitchen counter. Inside, an e-ink screen shows Toronto to Montréal, 900 feet, 233 km/h, 48 minutes to go, and a small map with the featured plane over the lakeshore" src="docs/images/hero.jpg" width="820">

An old Kindle Paperwhite runs this on its own. It fetches live flight positions, picks the
closest plane, and draws where it's going, how high and fast it is, and how far along its
trip it is. The screen updates every minute. A charge lasts about five days. At night it
draws the whole day's traffic as one picture.

Agents: read [AGENTS.md](AGENTS.md) first.

---

## Start here

You need a Kindle Paperwhite 10th generation (2018, "PW4") that is jailbroken with SSH over
Wi-Fi, and Claude Code. [docs/device-setup.md](docs/device-setup.md) covers the Kindle side.
Nothing runs on your computer once it's installed.

To see what it draws before touching a Kindle, open Claude on an empty folder and paste:

```text
Clone azilnik/kindle-planes, read its AGENTS.md, then render every style from the samples
and show me.
```

**You'll know it worked when** you see contact sheets like this, one per style:

<img alt="The day view: a story panel on the left with Tokyo to Toronto, 2,500 feet, 296 km/h, a progress line from NRT to YYZ, 14h 32m flown, Air Canada 1. On the right a map with the lakeshore, two airports and many small planes" src="docs/images/screen-day.png" width="640">

To put it on your Kindle:

```text
My Kindle answers to `ssh kindle`. Set home to <your address>, deploy, and show me a screenshot.
```

Claude writes the location into the Kindle's `config.json`, builds a shoreline for your
lake if you're not in Toronto, copies the code over, and reads the screen back.

**You'll know it worked when** the Kindle shows a plane within a minute. Then say what's
wrong with it: *"turn the map so north is up"*, *"the frame hides the top edge"*, *"use the
detailed style"*. Every setting is one line in `config.json`, and the Kindle re-reads it
every minute.

---

## What it shows

**Day.** The nearest plane in the air. City pair, height and speed, a progress line between
the two airports, time flown or time to go, airline and flight number. The map shows home
as a crosshair, the airports, the lake, and every other plane within 30 km.

**Night** (11 pm to 7 am). One drawing of the day: every position it saw, as a dot. Approach
paths draw themselves.

<img alt="The night view: thousands of small dots on white paper forming two dense diagonal bands where arrivals line up for the airport, a faint shoreline, and the caption 520 flights today" src="docs/images/screen-night.png" width="640">

**Quiet skies** when nothing is up. **Offline** with the time of the last fetch if the
network is down, so an outage never looks like an empty sky.

---

## Make it yours

Everything is in `planes/config.json` on the Kindle. Edit it over SSH; no restart needed.

| Key | What it does | Default |
|---|---|---|
| `style` | `bold-right` (photos above), `bold` (mirrored), `bold-traffic` (adds the day's chart), `detailed` (dense, many labels) | `bold-right` |
| `lat`, `lon` | Home. The map is centred here | Toronto City Hall |
| `city`, `airports` | Your city's name and its airports, `[["YYZ", lat, lon], ...]` | Toronto, YYZ + YTZ |
| `heading` | Compass direction you face when looking at it; the map turns so that's up | `0` (north up) |
| `rotate` | `270` puts the Kindle's logo on the left, `90` on the right | `270` |
| `safe` | The part of the screen your frame doesn't cover, `[x0, y0, x1, y1]` | fits the frame below |
| `night` | `["23:00", "07:00"]` | |
| `frontlight` | 0–24, only while on a charger | `3` |
| `power` | `wifi_toggle`, `suspend`, `governor`. All on for battery life | on |

**A new place.** Set `lat`, `lon`, `city`, `airports`. The lake comes from
`tools/shore.py "Lake Ontario" LAT LON`, which pulls the shoreline from Natural Earth. No
lake? Make `planes/shore.json` an empty list: `[]`.

**A different frame.** `tools/grid.py` draws a numbered grid; put it on the screen, take a
photo through the frame, and read off the `safe` box.

<img alt="The frame showing a numbered calibration grid instead of planes, so the visible area can be read off" src="docs/images/calibration-grid.jpg" width="520">

**The power button.** One press wakes the Kindle with Wi-Fi on for 10 minutes, so you can
SSH in. A second press a few seconds later hands the screen back to the normal Kindle. A
reboot brings the planes back.

---

## The frame

IKEA RÖDALM 13×18 cm, with a 3D-printed insert that holds the Kindle behind a mat and leaves
room for a flat USB cable. `insert/insert.py` generates it; the notes at the top of that
file cover printing. A 21×30 version with a double mat is in the same file.

<img alt="The frame on a counter against a tiled wall, showing Toronto to Winnipeg" src="docs/images/frame-winnipeg.jpg" width="640">

---

## How it works

Positions come from [adsb.lol](https://adsb.lol) (with [adsb.fi](https://adsb.fi) as
backup), routes and aircraft types from [adsbdb](https://www.adsbdb.com). No keys.

The Kindle only turns Wi-Fi on for a few seconds every 10 minutes to fetch. Between fetches
it moves each plane along its last known track and speed, redraws once a minute, and
deep-sleeps in between. Wi-Fi joins are the big cost; everything else was tuned until a
frame draws in about a third of a second. [docs/power.md](docs/power.md) has the numbers.

Routes are checked before they're shown: a plane low over Toronto is on the leg that starts
or ends here, and a route whose path doesn't pass near the plane is dropped. Time flown and
time to go are estimates from position and speed; there is no schedule data.

---

## Repo map

| Path | What it is |
|---|---|
| [AGENTS.md](AGENTS.md) | What an agent needs to know that the code doesn't say |
| [planes/](planes/) | Everything that runs on the Kindle: `planes.py` (fetch, draw, loop), `power.py` (Wi-Fi, sleep, battery log), `run.sh`, `config.json`, fonts, shoreline |
| [planes/samples/](planes/samples/) | Saved and synthetic data for previews. `sheet.py` renders them all |
| [tools/](tools/) | `deploy.sh`, `fbshot.sh` (screenshot), `grid.py` (frame calibration), `shore.py` (new lake), `battery.py` (power log) |
| [insert/](insert/) | The printable frame insert |
| [build/](build/) | How SSH and Pillow were built for the Kindle |
| [docs/device-setup.md](docs/device-setup.md) | Jailbreak, SSH, Python, install |
| [docs/power.md](docs/power.md) | Battery measurements and what each change was worth |
| [docs/roadmap.md](docs/roadmap.md) | Phone setup mode, so someone else can own one |

## Contributing

Run `ruff check planes tools insert` and render the contact sheets before opening a PR.
Screenshots come from `tools/fbshot.sh`, not the camera. If you correct Claude on the same
thing twice, that correction belongs in `AGENTS.md`.

MIT. Fonts and data keep their own licenses; see [LICENSE](LICENSE).
