#!/bin/sh
# Takes over the screen: stops the Kindle UI, turns the frontlight off, keeps Wi-Fi and
# the device awake, and loops the frame config.json names ("frame": "planes" or "sky").
# `run.sh stop` (or a reboot with /mnt/us/planes/DISABLED present) hands the screen back.
DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE=/tmp/planes.pid
PY=/mnt/us/python/bin/python3.12

# Set "key": "value" in config.json, adding it if it isn't there yet
set_key() {
    if grep -q "\"$1\"" "$DIR/config.json"; then
        sed -i "s/\"$1\": *\"[a-z-]*\"/\"$1\": \"$2\"/" "$DIR/config.json"
    else
        sed -i "s/^{/{\n  \"$1\": \"$2\",/" "$DIR/config.json"
    fi
    cat "$DIR/config.json"
}

# `run.sh style NAME` (bold, bold-right, bold-traffic, detailed) flips the planes frame's look;
# the running loop picks it up next frame
if [ "$1" = "style" ]; then
    # Any style name planes.py knows; planes.py ignores unknown names, so check here
    if ! grep -q "\"$2\": dict(" "$DIR/planes.py"; then
        echo "unknown style: $2"; exit 1
    fi
    set_key style "$2"
    exit 0
fi

# `run.sh frame planes|sky` switches what the screen shows: a different program, so restart
if [ "$1" = "frame" ]; then
    case "$2" in
        planes|sky) ;;
        *) echo "usage: run.sh frame planes|sky"; exit 1 ;;
    esac
    set_key frame "$2"
    [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null
    rm -f "$PIDFILE"
    exec sh "$0"
fi

if [ "$1" = "stop" ]; then
    [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null
    rm -f "$PIDFILE"
    touch /tmp/planes.stopped
    lipc-set-prop com.lab126.powerd preventScreenSaver 0
    start lab126_gui
    exit 0
fi

[ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null && exit 0

lipc-set-prop com.lab126.powerd preventScreenSaver 1
lipc-set-prop com.lab126.cmd wirelessEnable 1
stop lab126_gui 2>/dev/null
# Reader-side services nothing here uses; KOReader stops this same set on PW4 5.18.1
for svc in stored webreader kfxreader kfxview todo tmd rcm archive scanner otav3 otaupd; do
    stop "$svc" >/dev/null 2>&1
done
sleep 3

cd "$DIR"
FRAME=$(sed -n 's/.*"frame": *"\([a-z]*\)".*/\1/p' config.json)
case "$FRAME" in sky) ;; *) FRAME=planes ;; esac
# Toronto unless config.json sets "tz"
TZ="EST5EDT,M3.2.0,M11.1.0" SSL_CERT_FILE="$DIR/cacert.pem" REQUESTS_CA_BUNDLE="$DIR/cacert.pem" \
    nohup "$PY" "$FRAME.py" "$@" >/tmp/planes.log 2>&1 &
echo $! >"$PIDFILE"
