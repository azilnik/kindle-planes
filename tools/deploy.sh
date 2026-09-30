#!/bin/sh
# Push planes/ to the Kindle and restart the loop. The Kindle is the `kindle` host in
# ~/.ssh/config (set KINDLE to use another name).
# In power-save mode Wi-Fi is only up for a few seconds every 5 minutes, so this waits
# for that window, drops HOLD to keep it awake, copies, then releases HOLD (unless --hold).
set -e
cd "$(dirname "$0")/../planes"
KINDLE=${KINDLE:-kindle}
IP=$(ssh -G "$KINDLE" | awk '/^hostname /{print $2}')
KEEP_HOLD=${1:-}
if ! ssh -o ConnectTimeout=3 "$KINDLE" true 2>/dev/null; then
    echo "waiting for the Kindle's next Wi-Fi window..."
    until nc -z -G 1 "$IP" 22 2>/dev/null && \
          ssh -o ConnectTimeout=3 "$KINDLE" 'touch /mnt/us/planes/HOLD; lipc-set-prop com.lab126.cmd wirelessEnable 1' 2>/dev/null; do
        sleep 0.5
    done
    sleep 4
fi
# config.json and the files written at runtime stay on the device
COPYFILE_DISABLE=1 tar cf - --exclude cache.json --exclude traffic.json --exclude 'tracks.json*' --exclude 'power.log*' \
    --exclude __pycache__ --exclude samples --exclude 'config*.json' --exclude HOLD . |
    ssh "$KINDLE" 'cd /mnt/us/planes && tar xf -'
if [ "$KEEP_HOLD" = "--hold" ]; then
    ssh "$KINDLE" 'touch /mnt/us/planes/HOLD'
else
    ssh "$KINDLE" 'rm -f /mnt/us/planes/HOLD'
fi
ssh "$KINDLE" '[ -f /tmp/planes.pid ] && kill $(cat /tmp/planes.pid) 2>/dev/null; rm -f /tmp/planes.pid; sh /mnt/us/planes/run.sh'
echo "deployed$([ "$KEEP_HOLD" = "--hold" ] && echo ' (held awake: rm /mnt/us/planes/HOLD to resume power saving)')"
