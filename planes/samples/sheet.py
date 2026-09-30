"""Render every sample in one style and tile them into a contact sheet.
Usage: sheet.py STYLE out.png"""
import glob
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PLANES = os.path.join(HERE, "..")
style, out = sys.argv[1], sys.argv[2]
with open(os.path.join(PLANES, "config.json")) as f:
    SAFE = tuple(json.load(f)["safe"])
label_font = ImageFont.truetype(os.path.join(PLANES, "fonts", "Inter-SemiBold.ttf"), 22)

tiles = []
for path in sorted(glob.glob(os.path.join(HERE, "*.json"))):
    name = os.path.basename(path)[:-5]
    if name == "base":
        continue
    png = "/tmp/sample_%s.png" % name
    cmd = [sys.executable, os.path.join(PLANES, "planes.py"), "--sample", path, "--style", style,
           "--rotate", "0", "--out", png] + (["--night"] if name == "night" else [])
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL)
    im = Image.open(png).crop(SAFE).convert("L")
    # Case name in a strip above the tile, never on top of the design
    framed = Image.new("L", (im.width, im.height + 34), 120)
    framed.paste(im, (0, 34))
    ImageDraw.Draw(framed).text((6, 8), name.replace("_", " "), fill=255, font=label_font)
    tiles.append(framed)

tw, th = tiles[0].size
cols = 2
sheet = Image.new("L", (cols * tw + (cols + 1) * 16, ((len(tiles) + 1) // cols) * (th + 16) + 16), 120)
for i, t in enumerate(tiles):
    sheet.paste(t, (16 + (i % cols) * (tw + 16), 16 + (i // cols) * (th + 16)))
sheet.save(out)
print(out)
