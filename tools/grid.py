"""Calibration grid for measuring `safe`: lines every 20 px, labeled every 100, in the
1448x1072 landscape canvas, turned onto the panel like planes.py does.
Usage: grid.py ROTATE out.png"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1448, 1072
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
font = ImageFont.truetype(os.path.join(ROOT, "planes/fonts/Inter-SemiBold.ttf"), 22)

img = Image.new("L", (W, H), 255)
d = ImageDraw.Draw(img)
for x in range(0, W, 20):
    d.line((x, 0, x, H), fill=0 if x % 100 == 0 else 190, width=2 if x % 100 == 0 else 1)
for y in range(0, H, 20):
    d.line((0, y, W, y), fill=0 if y % 100 == 0 else 190, width=2 if y % 100 == 0 else 1)
# Labels on every major line, repeated so any visible strip carries its numbers
for x in range(100, W, 100):
    for y in range(40, H, 200):
        d.text((x + 4, y), str(x), font=font, fill=0)
for y in range(100, H, 100):
    for x in range(120, W, 200):
        d.text((x, y + 4), str(y), font=font, fill=0)

rotate = int(sys.argv[1]) % 360
if rotate:
    img = img.transpose({90: Image.ROTATE_270, 180: Image.ROTATE_180, 270: Image.ROTATE_90}[rotate])
img.save(sys.argv[2])
