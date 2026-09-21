"""Command-line interface for BCad2FreeCAD."""

import argparse
import sys
from pathlib import Path

from .parser import BcadParser
from .geometry import FrameGeometry, filter_tubes, TUBE_FEATURES
from .generator import FreeCADScriptGenerator


def main():
    ap = argparse.ArgumentParser(
        description="Convert a BikeCAD .bcad file to a FreeCAD Python macro."
    )
    ap.add_argument("bcad_file", help="Path to .bcad file")
    ap.add_argument(
        "-o", "--output",
        help="Output .py file (default: <input>_freecad.py)",
    )
    ap.add_argument(
        "--dump-params", action="store_true",
        help="Print extracted geometry parameters and exit",
    )
    ap.add_argument(
        "--hollow", action="store_true",
        help="Generate hollow tubes (slower render but more realistic)",
    )

    # Feature flags: pass any combination to export only those parts.
    # With none given, everything is exported (--all is the implicit default).
    feat = ap.add_argument_group(
        "features",
        "Select which parts to export (default: all). Combine freely, "
        "e.g. --frame --stays.",
    )
    feat.add_argument("--frame", action="store_true",
                      help="Main triangle: BB shell, head/seat/top/down tubes")
    feat.add_argument("--stays", action="store_true",
                      help="Rear triangle: chainstays, seatstays, bridge")
    feat.add_argument("--fork", action="store_true",
                      help="Fork blades and steerer")
    feat.add_argument("--dropout", action="store_true",
                      help="Rear dropout (plate export not yet implemented)")
    feat.add_argument("--all", action="store_true",
                      help="Export everything (same as passing no feature flag)")
    args = ap.parse_args()

    # Parse
    bcad_path = Path(args.bcad_file)
    if not bcad_path.exists():
        print(f"Error: file not found: {bcad_path}", file=sys.stderr)
        sys.exit(1)

    parser = BcadParser(str(bcad_path))
    print(f"Parsed {len(parser.data)} parameters from {bcad_path.name}")

    # Compute geometry
    geom = FrameGeometry(parser)
    tubes = geom.compute()

    # Print warnings
    for w in geom.warnings:
        print(f"  Warning: {w}", file=sys.stderr)

    if args.dump_params:
        print(geom.dump_params())
        sys.exit(0)

    # Resolve requested features. No flag (and no --all) means export all.
    requested = {
        f for f in ("frame", "stays", "fork", "dropout")
        if getattr(args, f)
    }
    if args.all or not requested:
        requested = set(("frame", "stays", "fork", "dropout"))

    # --dropout has no tube geometry: the dropout is a plate (a static library
    # part in files like MyBike.bcad), so it cannot be emitted yet. Warn.
    if "dropout" in requested:
        print(
            "  Warning: --dropout requested but dropout export is not "
            "implemented (it is a plate / static library part, not a tube). "
            "No dropout geometry will be written.",
            file=sys.stderr,
        )

    # Keep only the tube features that actually produce geometry.
    tubes = filter_tubes(tubes, requested & set(TUBE_FEATURES))
    if not tubes:
        print("Error: no exportable geometry for the selected features.",
              file=sys.stderr)
        sys.exit(1)

    # Generate FreeCAD script
    gen = FreeCADScriptGenerator(tubes, hollow=args.hollow)
    script = gen.generate()

    # Determine output path
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = bcad_path.with_name(bcad_path.stem + "_freecad.py")

    out_path.write_text(script)
    print(f"Wrote {len(tubes)} tubes to {out_path}")
    print(f"Open in FreeCAD: Macro > Execute Macro > {out_path.name}")


if __name__ == "__main__":
    main()
