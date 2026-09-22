"""Dropout geometry — the BikeCAD "Define by parameters" rear dropout.

A dropout is not a tube: it is a slotted ear plate + stay-attachment tabs,
described by its own schema (the ParameterizedSocket panel). `build_dropouts`
reads the parsed panel fields off a computed FrameGeometry and returns the
per-side dropouts.
"""

import math
from dataclasses import dataclass

from .geoframe import Vec3

# Dropout plate corner fillet radius (mm). BikeCAD rounds the dropout plate
# corners but exposes NO parameter for it — the .bcad has no fillet/radius key
# (confirmed absent), so this is a fixed cosmetic constant, not a CLI option.
# Value chosen to match BikeCAD's rendered corner rounding (~5mm).
DROPOUT_FILLET = 5.0

# How far a stay-socket tab extends toward its stay (mm). BikeCAD's tab length
# is arbitrary/simplified, so this is a fixed constant, not a parameter.
DROPOUT_TAB_LENGTH = 15.0

# Radius (mm) rounding the two corners at the slot MOUTH, where the axle slot
# breaks out of the plate edge. BikeCAD exposes no key for it; it renders a
# small flare smaller than the plate's own corner rounding — a fixed cosmetic.
DROPOUT_SLOT_FILLET = 2.0

# Parameterized dropout types we can build. BikeCAD's dropout panel offers
# socket / plate / hood. socket and plate share the same body (ear + U-slot)
# and differ only in the stay-tab shape (round stub vs flat tang); hood is not
# modelled yet. A --dropout request for an unsupported type must error.
SUPPORTED_DROPOUT_TYPES = ("socket", "plate")


@dataclass
class StaySocket:
    """One stay socket on a dropout, named as the BikeCAD panel labels it.

    `x`, `y`, `z` are the socket position relative to the axle center (the
    panel's Cx/Cy/Cz for the chainstay, Sx/Sy/Sz for the seatstay). `axis` is
    the unit vector along the stay the socket tab extends toward. `tubeDia` is
    the stay's own tube diameter at the dropout — the tab is sized to it so the
    stay plugs onto the socket.
    """
    x: float
    y: float
    z: float
    axis: Vec3
    tubeDia: float = 18.0


@dataclass
class ParameterizedSocket:
    """A BikeCAD "Define by parameters" dropout — the parameterizedSocket type.

    Fields mirror the BikeCAD dropout panel so the code reads like the UI:

        type            socket | plate | hood
        derailleurHanger, sliding, thruAxle   — the panel's three checkboxes
        A               linear dim, axle hole circumference → outside edge
        T               plate material thickness (the "Z view" thickness)
        Z               translates the dropout toward the front of the bike
                        while keeping the axle in place (moves the stays)
        t               socket insert fit; negative = stay tube fits INTO it
        chainstaySocket / seatstaySocket   — the Cx/Cy/Cz and Sx/Sy/Sz sockets

    Only the `socket` type carries stay sockets; plate/hood are not modelled.
    """
    name: str
    axle: Vec3              # rear axle center (the dropout origin)
    type: str = "socket"
    derailleurHanger: bool = False
    sliding: bool = False
    thruAxle: bool = False
    A: float = 20.0
    T: float = 10.0
    Z: float = 0.0
    t: float = -1.0
    slotAngle: float = 180.0    # ξ: slot opening dir, deg from +X CCW (rear)
    slotLength: float = 50.0    # D: slot length from axle center to round end
    slotWidth: float = 10.0     # axle slot width (~ axle diameter)
    fillet: float = DROPOUT_FILLET
    slotFillet: float = DROPOUT_SLOT_FILLET
    tabLength: float = DROPOUT_TAB_LENGTH
    chainstaySocket: "StaySocket | None" = None
    seatstaySocket: "StaySocket | None" = None
    feature: str = "dropout"
    color: tuple[float, float, float] = (0.4, 0.4, 0.43)


# ── Dropouts (parameterizedSocket) ─────────────────────────────────────────
#
# NOTE: this is a STUB. It models only the "socket" dropout type as a
# slotted plate + two round stay stubs — a deliberate simplification of
# BikeCAD's real socket geometry. It can be refined further either in the
# modeller (richer solid: true tab cross-section, hole, hood/plate types,
# derailleur-hanger/sliding/thru-axle variants) or exposed through the CLI
# (flags to override A/T/Z/t, tab length, axle diameter, slot direction).


def detect_dropout_type(style: str) -> str:
    """Map the "DROPOUT STYLE" family string to a modelled type.

    socket and plate are modelled; hood and any unrecognised style fall back to
    socket, and the CLI errors when an unsupported type is requested via
    --dropout.
    """
    style = style.upper()
    if "PLATE" in style:
        return "plate"
    if "HOOD" in style:
        return "hood"
    return "socket"


def build_dropouts(geom) -> tuple[list[ParameterizedSocket], str]:
    """Build a parameterizedSocket dropout per side, read from the panel.

    BikeCAD's "Define by parameters" dropout stores its panel fields in the
    (positionally-named) `Dropout joint N` array plus `Dropout ADJ`. These
    keys were verified by the signpost method (set a unique value in the
    UI, save, grep):

        type                = Dropout model / socket panel  (socket here)
        A                   = Dropout joint 15
        T                   = Dropout joint 8
        Z                   = Dropout ADJ
        t                   = Dropout joint 13   (negative = insert fit)
        chainstaySocket Cx,Cy,Cz = Dropout joint 0,1,2  (mirror 21,22,23)
        seatstaySocket  Sx,Sy,Sz = Dropout joint 3,4,5  (mirror 24,25,26)

    Values are only live in parametric mode; the defaults keep a static-
    mode file producing a plausible socket. Returns (dropouts, dropout_type).
    """
    p = geom.p

    dropout_type = detect_dropout_type(p.get_str("DROPOUT STYLE", ""))

    # Panel scalars (named as the BikeCAD dropout schema).
    A = p.get_float("Dropout joint 15", 20.0)
    T = p.get_float("Dropout joint 8", 10.0)
    Z = p.get_float("Dropout ADJ", 0.0)
    t = p.get_float("Dropout joint 13", -1.0)
    # Slot opening angle ξ (Dropout joint 9), degrees from +X (forward),
    # CCW: 0=forward, 90=up, 180/-180=rear, -90=down.
    slotAngle = p.get_float("Dropout joint 9", 180.0)
    # Slot length D (Dropout joint 10): how far the slot runs from the
    # axle center out to its rounded end.
    slotLength = p.get_float("Dropout joint 10", 50.0)
    dropoutSpacing = p.get_float("Dropout spacing", 135.0)

    # Stay axes (in the frame plane) the socket tabs extend along.
    chainstayAxis = (geom.bb_center - geom.rear_axle).normalized()
    seatAngle = math.radians(p.get_float("Seat angle", 73.0))
    seatStayOffset = p.get_float("Seat stay offset", 35.0)
    seatTubeDir = Vec3(-math.cos(seatAngle), math.sin(seatAngle), 0)
    seatstayJunction = geom.st_top - seatTubeDir * seatStayOffset
    seatstayAxis = (seatstayJunction - geom.rear_axle).normalized()

    # Stay tube diameters at the dropout — the tabs are sized to these so
    # each stay plugs onto its socket (same keys the stays themselves use).
    chainstayDia = p.get_float("Chain stay back diameter", 18.0)
    seatstayDia = p.get_float("SEATSTAY_HR", 17.0)

    dropouts: list[ParameterizedSocket] = []
    halfSpacing = dropoutSpacing / 2
    for side, z_sign in [("Drive", 1.0), ("NonDrive", -1.0)]:
        axle = Vec3(geom.rear_axle.x, geom.rear_axle.y,
                    z_sign * halfSpacing)
        dropouts.append(ParameterizedSocket(
            name=f"Dropout_{side}",
            axle=axle,
            type=dropout_type,
            A=A, T=T, Z=Z, t=t,
            slotAngle=slotAngle,
            slotLength=slotLength,
            slotWidth=geom.axle_dia,
            chainstaySocket=StaySocket(
                x=p.get_float("Dropout joint 0", 0.0),
                y=p.get_float("Dropout joint 1", 0.0),
                z=z_sign * p.get_float("Dropout joint 2", 0.0),
                axis=Vec3(chainstayAxis.x, chainstayAxis.y, 0),
                tubeDia=chainstayDia,
            ),
            seatstaySocket=StaySocket(
                x=p.get_float("Dropout joint 3", 0.0),
                y=p.get_float("Dropout joint 4", 0.0),
                z=z_sign * p.get_float("Dropout joint 5", 0.0),
                axis=Vec3(seatstayAxis.x, seatstayAxis.y, 0),
                tubeDia=seatstayDia,
            ),
        ))
    return dropouts, dropout_type
