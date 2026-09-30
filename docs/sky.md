# The sky frame

The sky frame shows what's above your home beyond the planes, as a map of the sky seen
from above. The middle of the circle is straight overhead, the rim is the horizon, and you
are the dot in the middle. Like the planes map and Google Maps, the direction you face when
you look at the frame (`heading` in `config.json`) is at the top, with the cone pointing
that way, and your left is on the left. It's white on black, day and night.

<img alt="The sky frame at night: a black circle of stars with the ISS crossing it on a heavy dashed path, the Moon and Saturn low in the east, a balloon in the south, and a panel reading ISS overhead, 8:01 tonight, 83 degrees up, up now" src="images/screen-sky.png" width="640">

## What it shows

- **The Sun's day.** Its path across the sky today, the hours of daylight, sunset, when
  the stars come out, and where today sits on the year's curve of day length
- **The ISS and China's Tiangong station,** with the path of the next pass you can see
- **The newest Starlink launch,** while its satellites still cross the sky in a line
- **Weather balloons** from the nearest launch site, with a side view of the climb that
  shows where the wind turns, and **pico balloons**, the small ham-radio balloons that
  float for weeks and sometimes circle the world
- **The Moon** in its phase, and **Venus, Mars, Jupiter and Saturn**
- **Meteor showers** on their peak nights
- After dark, the brighter stars

## What leads

The headline is the one thing worth looking up for. Every candidate is an event with a
time and a wonder from 1 to 5:

| Wonder | Events |
|---|---|
| 4 | An ISS pass 60° up or more, a Starlink train, the Perseids, Geminids and Quadrantids, a pico balloon that's been up a week |
| 3 | An ISS pass 25° to 60° up, a Tiangong pass 60° up, a weather or pico balloon in the sky, the full moon, the Eta Aquariids |
| 2 | Lower passes, the Moon up at night, daylight, the smaller showers |
| 1 | Sunrise |

Something happening now scores its wonder. Something still to come scores less the further
off it is, and the bigger it is, the earlier it starts to count: a sunrise matters in the
last half hour, a great ISS pass takes the afternoon before, a big meteor shower the day
before. There's no rotation and no randomness: the same sky always gives the same screen.

The last line, *Next*, is the most wonderful thing coming up, and how soon: *ISS pass
tonight 8:49*, *Full moon in 4 days*. It looks a week ahead, and a month ahead for what
comes once a year or less, like the meteor showers: *Orionids in 20 days*.

The frame never complains. Shorter days are told as the time the stars come out, and a
meteor shower washed out by the Moon steps back instead of saying so.

## Turn it on

```bash
ssh kindle sh /mnt/us/planes/run.sh frame sky
```

`run.sh frame planes` switches back. Both write `"frame"` in `config.json` and restart the
display.

## Where the data comes from

- Satellite orbits: [CelesTrak](https://celestrak.org), at most once every 20 hours. The
  Kindle keeps them in `orbits.csv`, so a day without network still shows them.
- Balloons: [SondeHub](https://sondehub.org). In the hours after the weather balloon
  launches at 00:00 and 12:00 UTC, every 15 minutes until one is up, then every 5 to draw
  its climb. Otherwise every 3 hours, for off-schedule flights and pico balloons.
- The Sun, Moon, planets, stars and meteor showers are worked out on the Kindle, with no
  network. So Wi-Fi goes on only when orbits or balloons are due, and in between the sky
  just redraws every 10 minutes, or every minute while something crosses.
  Satellite positions use [sgp4](https://pypi.org/project/sgp4/), and the star catalog
  comes from [d3-celestial](https://github.com/ofrohn/d3-celestial).

## At night

During the `night` hours the Kindle doesn't fetch, and redraws the sky every half hour.

## Preview it

```bash
uv run --python 3.9 --with pillow==9.0.1 --with requests python planes/samples/sheet.py sky out/sky.png
```
