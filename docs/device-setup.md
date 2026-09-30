# Device setup

One model is supported: Kindle Paperwhite 10th generation (2018, "PW4"), 1072×1448 screen.
Sleep, wake and the front light are all device-specific, so other Kindles need work.

This is what was done once, in order. Each step is manual; the jailbreak can't be scripted
and Amazon patches it, so block firmware updates as soon as it's in.

## 1. Jailbreak

Follow [kindlemodding.org](https://kindlemodding.org/jailbreaking/). On firmware 5.16.3 to
5.19.5, SpiderCat works entirely on the device: open the Kindle's browser, download the
book, open it. Do not update the firmware afterwards.

## 2. SSH over Wi-Fi

`build/install-ssh.sh` is a KUAL scriptlet. Put it in `documents/` with a folder
`/mnt/us/claude-bootstrap/` holding `unl.tar` (notmarek's USBNetLite) and your public key
as `authorized_keys`. Opening the scriptlet installs dropbear, key-only login, root, and
starts it at boot. It writes the Kindle's IP to `claude-bootstrap/ip.txt`.

On your computer, add a host to `~/.ssh/config`:

```
Host kindle
  HostName <the IP>
  User root
  IdentityFile ~/.ssh/kindle
```

Everything in `tools/` uses `ssh kindle`. Set `KINDLE=othername` to use another host.

## 3. Python

[python-build-standalone](https://github.com/astral-sh/python-build-standalone) 3.12,
`armv7-unknown-linux-gnueabihf`, unpacked to `/mnt/us/python`. The user store is FAT, so
there are no symlinks: call `/mnt/us/python/bin/python3.12` by its full name (`run.sh`
does).

## 4. Pillow and requests

The Kindle's libc is glibc 2.20, so wheels must be built against something older.
`build/pillow-armhf.sh` runs inside `docker run --platform linux/arm/v7 debian/eol:jessie`
with the Python tarball mounted at `/work/py312.tgz`. It builds Pillow with zlib and
FreeType only, linking the Kindle's own `libfreetype.so.6`, and downloads `requests` and its
dependencies as wheels. Install them with that Python's pip on the device.

Pillow's `stroke_width` segfaults against that FreeType. The code draws halos by offsetting
text instead.

## 5. FBInk

`planes.py` looks for `fbink` at `/mnt/us/libkh/bin`, `/var/local/kmc/bin` and
`/mnt/us/usbnet/bin`. It comes with the KindleModding tool packages and with KOReader.

## 6. Install

```bash
tools/deploy.sh --hold
ssh kindle 'cp /mnt/us/planes/planes.conf /etc/upstart/planes.conf'
ssh kindle 'cat > /mnt/us/planes/config.json' < planes/config.json   # then edit lat/lon etc.
ssh kindle 'rm /mnt/us/planes/HOLD'
```

`planes.conf` starts the display 45 seconds after the Kindle's UI on every boot. To keep
the display off across reboots, create `/mnt/us/planes/DISABLED`.

## Controls

| | |
|---|---|
| Stop and get the Kindle UI back | `ssh kindle sh /mnt/us/planes/run.sh stop`, or press power twice (see README) |
| Switch style | `ssh kindle sh /mnt/us/planes/run.sh style detailed` |
| Deploy code | `tools/deploy.sh` (waits for a Wi-Fi window) |
| Keep it awake while iterating | `tools/deploy.sh --hold`, then `rm /mnt/us/planes/HOLD` |
| Screenshot | `tools/fbshot.sh out/kindle.png` |
| Logs | `/tmp/planes.log` on the device; battery in `/mnt/us/planes/power.log` |
