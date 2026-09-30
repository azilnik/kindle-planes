#!/bin/sh
# Save what the Kindle is showing, straight from its framebuffer, upright as mounted.
# Needs the Kindle reachable (HOLD, or a Wi-Fi window). Usage: fbshot.sh [out.png]
OUT=${1:-out/kindle.png}
mkdir -p "$(dirname "$OUT")"
KINDLE=${KINDLE:-kindle}
# Row stride and visible size differ by model (PW4: 1088-byte rows of 1072, PW2: 768 of 758)
GEOM=$(ssh -o ConnectTimeout=6 "$KINDLE" 'cat /sys/class/graphics/fb0/stride; sed -n "s/^[A-Z]:\([0-9]*\)x\([0-9]*\).*/\1 \2/p" /sys/class/graphics/fb0/modes | head -1') || exit 1
set -- $GEOM
STRIDE=$1 PW=$2 PH=$3
ssh -o ConnectTimeout=6 "$KINDLE" "dd if=/dev/fb0 bs=$STRIDE count=$PH 2>/dev/null" > /tmp/kindle_fb.raw || exit 1
uv run -q --python 3.9 --with 'pillow==9.0.1' python -c "
from PIL import Image
d = open('/tmp/kindle_fb.raw', 'rb').read()[-$STRIDE * $PH:]
Image.frombytes('L', ($STRIDE, $PH), d).crop((0, 0, $PW, $PH)).transpose(Image.ROTATE_270).save('$OUT')"
echo "$OUT"
