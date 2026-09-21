# BCad2FreeCAD

Convert BikeCAD `.bcad` files to FreeCAD 3D models — without BikeCAD Pro.

BikeCAD Pro can export to FreeCAD natively, but if you only have the free version or a `.bcad` file from a builder, this tool generates a standalone FreeCAD Python macro that recreates the frame tubes as a 3D model.

```
Gravel.bcad  -->  [bcad2freecad.py]  -->  Gravel_freecad.py  -->  [FreeCAD]  -->  3D frame
```

## What it produces

A FreeCAD macro that creates the frame as 13 tubes:

- **Main triangle**: bottom bracket shell, head tube (tapered), seat tube, top tube, down tube
- **Rear triangle**: chainstays (x2), seatstays (x2), seatstay bridge
- **Fork**: fork blades (x2), steerer tube

Optionally (`--dropout` / `--all`) it also emits a **generic simple-slot dropout**
plate on each side. This is a placeholder — real frames use bought-in dropouts,
so it is excluded by default and is not the frame's actual library part.

The scope is otherwise **frame and fork tubes only** — no wheels, brakes, saddle, or other catalog components.

## Requirements

- Python 3.10+
- [FreeCAD](https://www.freecad.org/) (to open the generated macro)
- No additional Python packages needed

## Usage

```bash
b() { python -m bcad2freecad MyBike.bcad "$@"; }   # shorthand for the examples

# --- what to export (feature flags select exactly the named parts) ---
b                     # default: frame + stays + fork  (no dropout)
b --stays             # just the rear triangle
b --frame --fork      # several parts combined
b --dropout           # just the dropout (generic simple-slot plate)
b --stays --dropout   # any combination you like
b --all               # everything, dropout included

# --- how to render / where to write (options, combine with any of the above) ---
b -o rear.py                    # choose the output filename
b --hollow                      # hollow tubes (realistic, slower to render)
b --axle-dia 12                 # dropout slot for a 12mm thru-axle (default 10)
b --dump-params                 # inspect extracted geometry, write nothing
b --stays --hollow -o rear.py   # parts + options together
```

Two orthogonal axes: **which parts** (feature flags) × **how to render**
(options). Any option combines with any feature selection.

### Feature resolution

Feature flags are an **additive filter** — the named set *is* the export set.
With no flag, the default is the parts a builder fabricates (frame, stays,
fork); the dropout is **excluded by default** because dropouts are bought-in
ready-made. `--all` is the only way to also emit the dropout.

| Flag | Parts | In default? |
|------|-------|:-----------:|
| `--frame` | BB shell, head/seat/top/down tubes | ✅ |
| `--stays` | chainstays (×2), seatstays (×2), seatstay bridge | ✅ |
| `--fork` | fork blades (×2), steerer | ✅ |
| `--dropout` | generic simple-slot dropout plate (×2) | ❌ (bought-in) |
| `--all` | everything above, dropout included | — |

Then in FreeCAD: **Macro > Execute Macro** and select the generated `.py` file.

## Example output from `--dump-params`

```
Computed Frame Geometry
==================================================
  Head angle (deg).............. 71.0
  Seat angle (deg).............. 73.0
  Stack......................... 662.0
  Reach......................... 410.0
  BB drop....................... 65.0
  CS length..................... 450.0
  HT length..................... 195.0
  ST length..................... 560.0
  Fork ATC...................... 445.0
  Fork rake..................... 55.0
  Dropout mode.................. static (DR0001)
  ...

Tubes:
  BB_Shell................. L=68.0mm  R=20.0
  Head_Tube................ L=195.0mm  R=23.8->19.0
  Seat_Tube................ L=560.0mm  R=14.3->14.9
  Top_Tube................. L=587.5mm  R=14.9
  Down_Tube................ L=672.5mm  R=15.9->19.1
  ...
```

## Coordinate system

- **Origin**: bottom bracket center
- **X**: forward (toward front wheel)
- **Y**: upward
- **Z**: right (drive side)

## Limitations

This is a v1 tool built by reverse-engineering the `.bcad` format. Known limitations:

- **Chainstays** are modeled as tapered cones, not oval-to-round lofts with S-bends
- **No tube mitering** at junctions (tubes overlap rather than being trimmed)
- **Bent tubes** are not supported (straight only — though most steel frames use straight tubes)
- **Measure style 3** (Stack & Reach) is the only fully supported geometry mode; other BikeCAD measure styles use a rough estimate for Reach
- **Fork geometry** assumes straight blades; curved fork blades are not modeled
- Visual fidelity is approximate — this is for visualization and reference, not manufacturing

## How it works

The `bcad2freecad` package separates parsing from geometry from output:

1. **`parser.py` — `BcadParser`** reads the `.bcad` file (Java Properties XML) into a key-value store with typed getters
2. **`geometry.py` — `FrameGeometry`** computes 3D endpoints for every tube from the parsed parameters, using the BB center as origin
3. **`generator.py` — `FreeCADScriptGenerator`** emits a standalone Python script that uses FreeCAD's `Part.makeCylinder()` and `Part.makeCone()` to create each tube
4. **`cli.py`** wires these together for `python -m bcad2freecad`

## Running tests

```bash
python -m pytest tests/ -v
```

## License

MIT
