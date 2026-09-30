#!/bin/sh
# Grab the Photo Booth window (webcam pointed at the Kindle), un-mirrored. Usage: camshot.sh [out.png]
DIR="$(cd "$(dirname "$0")" && pwd)"
OUT=${1:-out/cam.png}
mkdir -p "$(dirname "$OUT")"
ID=$(swift "$DIR/photobooth-window.swift" 2>/dev/null | awk '$4==0{print $1; exit}')
[ -n "$ID" ] || { echo "Photo Booth window not found"; exit 1; }
screencapture -x -o -l "$ID" /tmp/kindle_cam.png && sips -f horizontal /tmp/kindle_cam.png --out "$OUT" >/dev/null && sips -Z 1400 "$OUT" >/dev/null
echo "$OUT"
