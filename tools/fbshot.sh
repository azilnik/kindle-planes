#!/bin/sh
# Save what the Kindle is showing, straight from its framebuffer, upright as mounted.
# Needs the Kindle reachable (HOLD, or a Wi-Fi window). Usage: fbshot.sh [out.png]
OUT=${1:-out/kindle.png}
mkdir -p "$(dirname "$OUT")"
KINDLE=${KINDLE:-kindle}
ssh -o ConnectTimeout=6 "$KINDLE" 'dd if=/dev/fb0 bs=1088 count=1448 2>/dev/null' > /tmp/kindle_fb.raw || exit 1
uv run -q --python 3.9 --with 'pillow==9.0.1' python -c "
from PIL import Image
d = open('/tmp/kindle_fb.raw', 'rb').read()[-1088 * 1448:]
Image.frombytes('L', (1088, 1448), d).crop((0, 0, 1072, 1448)).transpose(Image.ROTATE_270).save('$OUT')"
echo "$OUT"
