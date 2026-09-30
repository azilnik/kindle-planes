"""The screen loop every frame shares: wake, fetch over Wi-Fi when due, draw, push to the
e-ink panel, sleep, and the night and low-battery rest. A frame (planes.py, sky.py)
supplies the data and the pictures; this owns timing, power and Wi-Fi recovery, which
were hard won on the device (docs/power.md).

A frame is an object with:
    configure(args)          re-read config.json (every loop, so edits apply live) and return
                             the settings this needs: power, rotate, style, frontlight
    fetch(session, now)      pull its data; raise requests.RequestException or ValueError
                             when the fetch as a whole failed
    fetch_every(now)         seconds until the next fetch after a good one
    render(now, fetched_at)  the picture, on the landscape canvas (fetched_at 0 = never)
    moving(now)              True while the picture changes minute to minute; otherwise
                             the loop sleeps until the next fetch
    in_night(now), next_morning(now)
                             the quiet hours, when nothing is fetched
    night_key(now, mode)     redraw the rest picture whenever this changes
    render_night(now, mode)  that picture; mode is "night", or "low" on a dying battery
and `fetch_log` and `log`, dicts of fields for the power log's fetch and draw lines.
Optionally `idle_redraw_s`: the longest a still picture waits for a redraw when the next
fetch is further off than that (the sky turns even when nothing needs fetching).
"""

import os
import re
import subprocess
import sys
import time
import traceback

import power
import requests
from PIL import Image

DRAW_S = 60
FULL_REFRESH_S = 1800     # a full e-ink flash this often to clear ghosting
NIGHT_WAKE_S = 1800       # brief wakes at night so no single suspend runs for hours
MAX_BACKOFF_S = 600       # adsb.lol rate-limits; failures back off to this
LOW_BATTERY = 5
LOW_BATTERY_RESUME = 10
UA = {"User-Agent": "kindle-planes/0.1 (home display)"}

FBINK = None
for cand in ("/mnt/us/libkh/bin/fbink", "/var/local/kmc/bin/fbink", "/mnt/us/usbnet/bin/fbink", "fbink"):
    if cand == "fbink" or os.path.exists(cand):
        FBINK = cand
        break


def panel_size():
    """The panel's native portrait size. Everything is drawn on the PW4's 1448x1072 canvas;
    a smaller panel (a PW2's 758x1024 is the same shape) gets the frame scaled to fit."""
    try:
        with open("/sys/class/graphics/fb0/modes") as f:
            m = re.match(r"\w+:(\d+)x(\d+)", f.read())  # "U:758x1024p-0"
        if m:
            return int(m.group(1)), int(m.group(2))
    except OSError:
        pass
    return 1072, 1448


PANEL = panel_size()


def turn(img, rotate):
    """Scale to the panel if it's smaller than the canvas, then clockwise quarter turns onto
    it. transpose() is a lossless row copy; rotate() resamples every pixel and cost the
    Kindle a few hundred ms a frame."""
    size = (PANEL[1], PANEL[0]) if img.size[0] > img.size[1] else PANEL
    if img.size != size:
        # BILINEAR: 370 ms on a PW2 where LANCZOS took 830, and at this 0.7x scale the two
        # are indistinguishable even magnified (Pillow widens either filter to the area)
        img = img.resize(size, Image.BILINEAR)
    if not rotate % 360:
        return img
    return img.transpose({90: Image.ROTATE_270, 180: Image.ROTATE_180, 270: Image.ROTATE_90}[rotate % 360])


def show(path, flash):
    # -w: block until the panel finishes refreshing. Suspending the EPDC mid-update hung
    # the kernel roughly every 7th sleep, and the watchdog rebooted the Kindle each time
    args = [FBINK, "-q", "-w", "-g", "file=%s" % path]
    if flash:
        args.insert(2, "-f")
    subprocess.call(args)


def battery_low(was_low):
    bat = power.battery()
    if not bat or not bat[0]:
        return False
    cap, on_ac = int(bat[0]), bat[3] == "1"
    if on_ac:
        return False
    return cap <= (LOW_BATTERY_RESUME if was_low else LOW_BATTERY)


def run(frame, args):
    cfg = frame.configure(args)
    power.set_governor(cfg["power"].get("governor"))
    session = requests.Session()
    session.headers.update(UA)
    # PGM: uncompressed, 7 ms to write on the Kindle where PNG took 500+
    frame_path = args.out or "/tmp/planes.pgm"
    night_drawn = ""
    low = False
    started, hold_until, hold_started = time.time(), 0, 0
    fetched_at = next_fetch = last_full = 0.0
    failures = 0
    last_style = cfg["style"]
    while True:
        cfg = frame.configure(args)
        pw = cfg["power"]
        restyled, last_style = last_style != cfg["style"], cfg["style"]
        now = time.time()

        low = not args.once and battery_low(low)
        if not args.once and (frame.in_night(now) or low):
            power.set_frontlight(0)  # nobody's reading it at night or on a dying battery
            mode = "low" if low else "night"
            if night_drawn != frame.night_key(now, mode):
                try:
                    img = frame.render_night(now, mode)
                    turn(img, cfg["rotate"]).save(frame_path)
                    show(frame_path, flash=True)
                    night_drawn = frame.night_key(now, mode)
                    power.log("night_draw", mode=mode, **frame.log)
                except Exception:
                    traceback.print_exc()
            if pw.get("wifi_toggle"):
                power.wifi_down()
            suspend = pw.get("suspend", False) and time.time() - started > 60
            woke = power.sleep_until(now + NIGHT_WAKE_S if low else min(now + NIGHT_WAKE_S, frame.next_morning(now)),
                                     suspend=suspend)
            power.log("wake", how=woke, night=1)
            next_fetch = 0  # fetch straight away when morning comes
            last_full = 0
            continue

        if now >= next_fetch:
            woke = time.time()
            # Escalate on a dead link (wifid can lose the network overnight and never retry):
            # radio cycle every 3rd failure, restart wifid after ~1 h, reboot after ~3 h
            if failures and failures % 36 == 0:
                power.reboot()
            if failures and failures % 12 == 0:
                power.restart_wifid()
            took = power.wifi_up(reset=failures >= 3 and failures % 3 == 0) if pw.get("wifi_toggle") else 0.0
            try:
                # wifid reports CONNECTED a moment before the link carries traffic; retry
                # inside this wake rather than paying for another Wi-Fi join next minute
                for attempt in range(3):
                    try:
                        frame.fetch(session, now)
                        break
                    except requests.ConnectionError:
                        if attempt == 2:
                            raise
                        time.sleep(2)
                fetched_at, failures = now, 0
            except (requests.RequestException, ValueError) as e:
                failures += 1
                print("fetch failed (%d): %r" % (failures, e), file=sys.stderr, flush=True)
            if pw.get("wifi_toggle"):
                power.wifi_down()
            if failures:
                next_fetch = now + min(60 * failures, MAX_BACKOFF_S)
            else:
                next_fetch = now + frame.fetch_every(now)
            power.log("fetch", ok=int(not failures), wifi_s="%.1f" % (took or -1),
                      awake_s="%.1f" % (time.time() - woke), **frame.fetch_log)

        # Suspend switches the frontlight off, so a steady glow is only possible awake:
        # light it when on a charger (and skip suspend below), keep it dark on battery
        charging = power.on_ac()
        power.set_frontlight(cfg["frontlight"] if charging else 0)
        drawn = time.time()
        try:
            img = frame.render(drawn, fetched_at)
            turn(img, cfg["rotate"]).save(frame_path)
            if not args.out:
                flash = restyled or drawn - last_full > FULL_REFRESH_S
                show(frame_path, flash=flash)
                if flash:
                    last_full = drawn
        except Exception:
            if args.once:
                raise
            traceback.print_exc()
        power.log("draw", ms=int((time.time() - drawn) * 1000), **frame.log)
        if args.once:
            print(frame_path)
            return

        # Draw on the minute so the clock is exact; with nothing to move, just wait for the fetch
        next_draw = (int(time.time() // DRAW_S) + 1) * DRAW_S if frame.moving(drawn) else next_fetch
        if getattr(frame, "idle_redraw_s", None):
            next_draw = min(next_draw, drawn + frame.idle_redraw_s)
        # Never deep-sleep in the first minute after start, so a bad build can be stopped over SSH
        suspend = pw.get("suspend", False) and time.time() - started > 60 and not (charging and cfg["frontlight"])
        woke = power.sleep_until(min(next_draw, next_fetch), suspend=suspend)
        if woke == "button" and hold_until and time.time() - hold_started > 5:
            # A second press while held means leave: hand the screen back to the Kindle
            # UI until the next reboot. The gap keeps a quick double tap from exiting.
            power.log("button_exit")
            if os.path.exists(power.HOLD):
                os.remove(power.HOLD)
            subprocess.call(["sh", os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.sh"), "stop"])
            return
        if woke == "button":
            # A power-button press means someone wants in: hold awake with Wi-Fi for 10 minutes
            open(power.HOLD, "w").close()
            hold_started = time.time()
            hold_until = hold_started + 600
            power.wifi_up()
            power.log("button_hold")
        if hold_until and time.time() > hold_until and os.path.exists(power.HOLD):
            os.remove(power.HOLD)
            hold_until = 0
        power.log("wake", how=woke)
