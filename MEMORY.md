# BCad2FreeCAD Project - Session Memory

## Last Updated: 2026-09-21

## Current State
v1 converter implemented and tested. 48 tests pass, 4 skip when `Gravel.bcad`
is absent (the integration tests). Split from a single file into a package.
Forked to `3dyuval/BikeCAD2FreeCAD` (upstream `fiddlythings`); refactor lives
on branch `refactor/split-parser-features`.

## Files
- `bcad2freecad/` — package (was single-file `bcad2freecad.py`):
  - `parser.py` — `BcadParser`
  - `geometry.py` — `Vec3`, `TubeSpec`, `FrameGeometry` (the "features" layer)
  - `generator.py` — `FreeCADScriptGenerator`
  - `cli.py` + `__main__.py` — CLI; run as `python -m bcad2freecad`
  - `__init__.py` — re-exports the public names (tests import `from bcad2freecad import ...`)
- `tests/test_parser.py` — parser unit tests
- `tests/test_geometry.py` — geometry + script generation tests
- `Gravel.bcad` — sample input (7216 params); **not currently present**, so its
  integration tests skip
- `MyBike.bcad` — the sample present in this checkout (6441 params; static
  Paragon DR0001 dropout)

## What's Implemented
- **BcadParser**: Java Properties XML parser with typed getters (float/int/bool/str)
- **FrameGeometry**: Computes 3D tube positions. Origin at BB center, X=forward, Y=up, Z=right.
  - Reference points: BB, HT top/bottom, ST top, rear/front axle
  - Measure style 3: FCD textfield interpreted as Reach (= 410mm for Gravel.bcad)
- **13 tubes**: BB shell, head tube (tapered), seat tube (tapered), top tube, down tube, 2x chainstay, 2x seatstay, seatstay bridge, 2x fork blade, steerer
- **FreeCADScriptGenerator**: Emits standalone FreeCAD Python macro with `make_tube()` helper
- **CLI**: `--dump-params` and `--hollow` flags
- **Dropout mode detection**: reads `DropoutParamOrStatic` to report static
  (library part, e.g. Paragon DR0001) vs parametric dropout in `--dump-params`.
  The `Dropout joint N` array is deliberately NOT parsed — it only feeds
  parametric mode and is dead state otherwise; stay endpoints come from
  `rear_axle` + `Dropout spacing` regardless.

## Key Geometry Decisions
- Reach derived from `FCD textfield` when `Top tube front center measure style` = 3
- Fork ATC = `FORK{type}L`, Fork rake = `FORK{type}R`
- Chainstay oval approximated as equivalent-area circle for FreeCAD cones
- Seatstay junction = `Seat stay offset` (35mm) below ST top along seat tube
- Front axle height sanity check: ~10mm discrepancy vs BB drop (acceptable for v1)

## Known Limitations / Future Work
- Chainstays modeled as simple cones (no oval cross-section or S-bend)
- No tube mitering at junctions
- No bent tube support (all bent flags are false in Gravel.bcad)
- Only measure style 3 (Stack & Reach) properly handled
- Wall thickness in FreeCAD only renders with `--hollow` flag
- Needs visual verification in FreeCAD

## Conventions
- Commits: Conventional Commits (`type(scope): subject`) with **body-empty** —
  subject line only, no body, no trailer (commitlint hook rejects otherwise).
  Prefer several small commits split by architecture choice.
