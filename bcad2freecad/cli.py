"""Command-line interface for BCad2FreeCAD."""

import argparse
import sys
from pathlib import Path

from .parser import BcadParser
from .geoframe import FrameGeometry, filter_tubes, TUBE_FEATURES
from .geodropouts import SUPPORTED_DROPOUT_TYPES
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
    ap.add_argument(
        "--axle-dia", type=float, default=10.0, metavar="MM",
        help="Rear axle diameter, sets the dropout slot width (default: 10.0)",
    )

    # Feature flags select exactly which parts to export (additive filter):
    # the named set IS the export set. With no flag, the default is the parts
    # a builder fabricates — frame + stays + fork — which EXCLUDES the dropout
    # (dropouts are bought-in ready-made). --all is the only way to also get
    # the dropout. See README "Feature resolution".
    feat = ap.add_argument_group(
        "features",
        "Export exactly the named parts. No flag = frame+stays+fork (no "
        "dropout). Combine freely, e.g. --frame --fork.",
    )
    feat.add_argument("--frame", action="store_true",
                      help="Main triangle: BB shell, head/seat/top/down tubes")
    feat.add_argument("--stays", action="store_true",
                      help="Rear triangle: chainstays, seatstays, bridge")
    feat.add_argument("--fork", action="store_true",
                      help="Fork blades and steerer")
    feat.add_argument("--dropout", action="store_true",
                      help="Rear dropout only (generic simple-slot plate)")
    feat.add_argument("--all", action="store_true",
                      help="Everything, including the dropout")
    args = ap.parse_args()

    # Parse
    bcad_path = Path(args.bcad_file)
    if not bcad_path.exists():
        print(f"Error: file not found: {bcad_path}", file=sys.stderr)
        sys.exit(1)

    parser = BcadParser(str(bcad_path))
    print(f"Parsed {len(parser.data)} parameters from {bcad_path.name}")

    # Compute geometry
    geom = FrameGeometry(parser, axle_dia=args.axle_dia)
    tubes = geom.compute()

    # Print warnings
    for w in geom.warnings:
        print(f"  Warning: {w}", file=sys.stderr)

    if args.dump_params:
        print(geom.dump_params())
        sys.exit(0)

    # Resolve the export set:  R(export_set) = F ?? D
    #   F (flags)   = exactly the named features (additive filter)
    #   D (default) = frame + stays + fork  (a builder's fabricated parts;
    #                 the bought-in dropout is excluded by default)
    #   --all       = the only way to get everything, dropout included
    flagged = {
        f for f in ("frame", "stays", "fork", "dropout")
        if getattr(args, f)
    }
    if args.all:
        requested = {"frame", "stays", "fork", "dropout"}
    elif flagged:
        requested = flagged
    else:
        requested = {"frame", "stays", "fork"}

    tubes = filter_tubes(tubes, requested & set(TUBE_FEATURES))

    # Dropout: we only build the parameterized types we support (currently just
    # "socket"). For an unsupported type (plate/hood, or a static library part):
    #   - explicit --dropout  → hard error (you asked for the one thing we can't)
    #   - implicit via --all  → warn and skip, still export the rest
    dropouts = []
    if "dropout" in requested:
        supported = geom.dropout_type in SUPPORTED_DROPOUT_TYPES
        if supported:
            dropouts = geom.dropouts
        elif args.dropout:  # explicitly requested
            print(
                f"Error: dropout type '{geom.dropout_type}' is not supported "
                f"(supported: {', '.join(SUPPORTED_DROPOUT_TYPES)}). "
                "Cannot export --dropout for this frame.",
                file=sys.stderr,
            )
            sys.exit(1)
        else:  # bundled via --all / default
            print(
                f"  Warning: dropout type '{geom.dropout_type}' is not "
                "supported; skipping the dropout, exporting the rest.",
                file=sys.stderr,
            )

    if not tubes and not dropouts:
        print("Error: no exportable geometry for the selected features.",
              file=sys.stderr)
        sys.exit(1)

    # Generate FreeCAD script
    gen = FreeCADScriptGenerator(tubes, hollow=args.hollow, dropouts=dropouts)
    script = gen.generate()

    # Determine output path
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = bcad_path.with_name(bcad_path.stem + "_freecad.py")

    out_path.write_text(script)
    n = len(tubes) + len(dropouts)
    print(f"Wrote {n} parts to {out_path}")
    print(f"Open in FreeCAD: Macro > Execute Macro > {out_path.name}")


if __name__ == "__main__":
    main()
