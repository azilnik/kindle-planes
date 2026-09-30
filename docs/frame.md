# The frame

The Kindle sits in an IKEA RÖDALM 13×18 cm frame, held by a 3D-printed insert. The front
of the insert is the mat you see; the back is a pocket the Kindle snaps into, with room
beside it for a flat USB cable.

<img alt="Two views of the printed insert. Front: a flat mat with a rectangular window. Back: a pocket the size of the Kindle with snap lips on the long sides and spring tabs on the outer walls" src="images/insert-13x18.png" width="820">

## Print the insert

| Frame | Kindle | File |
|---|---|---|
| RÖDALM 13×18 cm | Paperwhite 4 | [insert-rodalm13x18.3mf](../insert/insert-rodalm13x18.3mf) ([.stl](../insert/insert-rodalm13x18.stl)) |
| RÖDALM 13×18 cm | Paperwhite 2 | [insert-rodalm13x18-pw2.3mf](../insert/insert-rodalm13x18-pw2.3mf) ([.stl](../insert/insert-rodalm13x18-pw2.stl)) |
| RÖDALM 21×30 cm | Paperwhite 4 | [insert-rodalm21x30.3mf](../insert/insert-rodalm21x30.3mf) ([.stl](../insert/insert-rodalm21x30.stl)) |

- Print face down in PETG, with no brim or skirt. PLA works, but its spring tabs relax
  over time.
- Each insert fits a 180 mm print bed and uses about 54 cm³ of filament.
- The 13×18 insert needs a flat ribbon USB cable, because a normal plug doesn't fit beside
  the Kindle. The 21×30 takes any right-angle plug.
- Only the Paperwhite 4 13×18 insert has been printed and used. The Paperwhite 2 version
  comes from a test fit in it: 0.5 mm more along the port edge and a 40 mm cable slot. The
  21×30 insert hasn't been built yet; measure its mat opening before printing.

For a different frame, add its size to `FRAMES` in [insert/insert.py](../insert/insert.py)
and run it. The command is at the top of that file.

## Measure what the mat hides

The mat covers the edges of the screen. `safe` in `config.json` tells the display which part
stays visible, as `[left, top, right, bottom]` in pixels. The test pattern shows you the
numbers.

<img alt="The test pattern: a grid with heavy lines every 100 pixels labeled x100, x200 across and y100, y200 down, and a box in the middle explaining how to read it" src="images/test-pattern.png" width="520">

1. Press the Kindle's power button once to wake its Wi-Fi.
2. Run `tools/grid.sh` to put the pattern on the screen.
3. With the Kindle in its frame, read the first label or line you can see at each edge.
   Heavy lines are every 100 pixels, thin lines every 20. For example, two thin lines and
   then `x100` on the left edge means left is 60.
4. Put the four numbers in `safe` on the Kindle.
5. Run `tools/grid.sh check`. It draws a box at `safe`, and all four sides of it should be
   visible, right at the edge of the mat.
6. Run `tools/grid.sh done` to bring the planes back.

The map runs right up to the edges of `safe`. Text stays 1 mm further in, set by `inset`.

<img alt="The frame showing the grid instead of planes, so the visible area can be read off" src="images/calibration-grid.jpg" width="520">
