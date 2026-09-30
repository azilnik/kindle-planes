# kindle-planes — agent context

Facts you can't get by reading the code. Everything else is in the README and `docs/`.

Everything runs on the Kindle. The laptop only previews, builds and deploys.

## Preview, don't fetch

Render from samples, never from the live API on the laptop: a laptop on the same network as
a Kindle shares its public IP and trips adsb.lol's rate limit for both.

```bash
uv run --python 3.9 --with pillow==9.0.1 --with requests python planes/planes.py \
  --sample planes/samples/crowded.json --rotate 0 --out out/x.png
```

Every style, every sample, one image: `planes/samples/sheet.py STYLE out/sheet.png` (add
`--night` yourself for `night.json`; the sheet does). Regenerate samples after changing the
home location: `planes/samples/make.py` and `make_night.py`.

The pinned Python 3.9 + Pillow 9 preview is the compatibility floor. Keep `planes.py` 3.9
compatible. The Kindle itself runs a standalone Python 3.12 with a Pillow built against its
own FreeType (`docs/device-setup.md`).

## Kindle quirks

- Pillow `stroke_width` segfaults the Kindle's FreeType. Use `halo_text()`.
- The screen's controller does its own 16-level quantising. Don't posterise.
- `rtc1`, not `rtc0`, wakes a PW4 from suspend. Never suspend without an alarm armed.
- FBInk returns before the panel finishes. `fbink -w`, or the next suspend can hang the kernel.

## Deploying

- `tools/deploy.sh` copies `planes/` to `/mnt/us/planes` and restarts the loop. It waits for
  the Kindle's Wi-Fi window (up for a few seconds every 5 minutes in power-save mode). One
  press of the power button opens a 10-minute window immediately.
- `config.json` is never deployed. The device keeps its own; edit it over SSH.
- `tools/deploy.sh --hold` leaves the Kindle awake with Wi-Fi on. Remove
  `/mnt/us/planes/HOLD` when done, or the battery drains.
- Runtime files stay on the device and are gitignored: `cache.json`, `traffic.json`,
  `tracks.json`, `power.log`.
- After a visual change, show a screenshot: `tools/fbshot.sh` reads the framebuffer.
- Measure power only on battery: `ac=0` rows in `power.log`, summarised by `tools/battery.py`.

## Style rules

- Comments say why, not what. Delete code instead of commenting it out.
- `ruff check planes tools insert` must pass (`ruff.toml`).
- Styles: `bold-right` is the default and what the photos show. `bold` mirrors it,
  `bold-traffic` adds the day's chart, `detailed` is the dense original.
