#!/bin/sh
# First install onto a Kindle that already answers to `ssh kindle` (docs/device-setup.md
# steps 1 and 2). Puts Python on it, copies the code, writes a config.json if there is
# none, installs the boot job and starts the display. Safe to run again.
# Press the Kindle's power button once first so it stays on Wi-Fi. --hold keeps it awake
# on Wi-Fi afterwards, as tools/deploy.sh --hold does.
#   BUNDLE=path/to/kindle-planes-python-armv7.tar.gz  use a local bundle (build/bundle.sh)
set -e
cd "$(dirname "$0")/.."
KINDLE=${KINDLE:-kindle}
RELEASE=${RELEASE:-https://github.com/azilnik/kindle-planes/releases/latest/download}
PY=/mnt/us/python/bin/python3.12

ssh -o ConnectTimeout=6 "$KINDLE" true || {
    echo "can't reach the Kindle: press its power button once and try again"; exit 1; }

ssh "$KINDLE" 'for f in /mnt/us/libkh/bin/fbink /var/local/kmc/bin/fbink /mnt/us/usbnet/bin/fbink; do
    [ -x "$f" ] && exit 0; done; command -v fbink >/dev/null' || {
    echo "no fbink on the Kindle: see docs/device-setup.md, FBInk"; exit 1; }

# Firmware 5.16.3 and newer is hard-float; older firmware (a PW2 tops out at 5.12) has only
# the soft-float loader and needs the other bundle
if ssh "$KINDLE" '[ -e /lib/ld-linux-armhf.so.3 ]'; then
    NAME=kindle-planes-python-armv7.tar.gz
else
    NAME=kindle-planes-python-armv7-softfloat.tar.gz
fi
# A PW2's 758x1024 panel starts from its own config: a wider story panel, and the safe area
# measured in the 13x18 insert
case $(ssh "$KINDLE" 'cat /sys/class/graphics/fb0/modes') in
    *758x1024*) CONFIG=planes/config-pw2.json ;;
    *) CONFIG=planes/config.json ;;
esac

# INSTALLED is written only after a complete, tested copy: an install cut off halfway can
# still import PIL and requests, so a working import proves nothing
if ssh "$KINDLE" "[ -f /mnt/us/python/INSTALLED ]" 2>/dev/null; then
    echo "python: already there"
else
    if [ -z "$BUNDLE" ]; then
        mkdir -p out
        BUNDLE=out/$NAME
        echo "python: downloading"
        curl -fL --progress-bar -o "$BUNDLE" "$RELEASE/$NAME" || {
            echo "can't download $NAME from $RELEASE: is there a published release?"; exit 1; }
        curl -fsSL -o "$BUNDLE.sha256" "$RELEASE/$NAME.sha256"
        (cd out && shasum -a 256 -c "$NAME.sha256" >/dev/null) || {
            echo "the download doesn't match its checksum"; exit 1; }
    fi
    echo "python: copying to the Kindle, a few minutes"
    # Beside the old one, then swapped in once it works, so a cut-off copy never replaces
    # a good Python and is never mistaken for one
    ssh "$KINDLE" 'rm -rf /mnt/us/python.new && mkdir /mnt/us/python.new && cd /mnt/us/python.new && tar xzf -' < "$BUNDLE"
    ssh "$KINDLE" '/mnt/us/python.new/python/bin/python3.12 -c "import json, ssl, zlib, requests, PIL.Image, PIL.ImageFont" &&
        rm -rf /mnt/us/python && mv /mnt/us/python.new/python /mnt/us/python && rmdir /mnt/us/python.new &&
        touch /mnt/us/python/INSTALLED' || { echo "python: the copy on the Kindle doesn't work, not installed"; exit 1; }
fi

# deploy.sh never touches config.json, so a first install has to write one
ssh "$KINDLE" 'mkdir -p /mnt/us/planes'
if ssh "$KINDLE" '[ -f /mnt/us/planes/config.json ]'; then
    echo "config: keeping the Kindle's own"
else
    ssh "$KINDLE" 'cat > /mnt/us/planes/config.json' < "$CONFIG"
    echo "config: written from $CONFIG, with Toronto as home"
fi

# The boot job lives on the root filesystem, which is read-only until asked
ssh "$KINDLE" 'mntroot rw >/dev/null 2>&1; cat > /etc/upstart/planes.conf; rc=$?; mntroot ro >/dev/null 2>&1; exit $rc' \
    < planes/planes.conf
echo "boot job: installed"

tools/deploy.sh "$@"
echo "Planes within a minute. Home is set in /mnt/us/planes/config.json: README, Make it yours"
