"""Frame geometry — compute 3D tube positions from parsed .bcad parameters.

This is the "features" layer: each frame element (head tube, seat tube,
stays, fork, …) is produced by its own `_make_*` method as one or more
TubeSpec objects.
"""

import math
from contextlib import contextmanager
from dataclasses import dataclass

from .parser import BcadParser

# Feature groups that map to actual generated tubes. "dropout" is a recognized
# feature but has no tube geometry: the dropout is a plate (and in static-mode
# files a library part not present in the .bcad), so it currently emits nothing.
TUBE_FEATURES = ("frame", "stays", "fork")
ALL_FEATURES = TUBE_FEATURES + ("dropout",)


def filter_tubes(tubes: list["TubeSpec"], features: set[str]) -> list["TubeSpec"]:
    """Return only tubes whose feature is in `features`."""
    return [t for t in tubes if t.feature in features]


@dataclass
class Vec3:
    """Simple 3D vector."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, s: float) -> "Vec3":
        return Vec3(self.x * s, self.y * s, self.z * s)

    def __rmul__(self, s: float) -> "Vec3":
        return self.__mul__(s)

    def length(self) -> float:
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)

    def normalized(self) -> "Vec3":
        ln = self.length()
        if ln < 1e-9:
            return Vec3(0, 0, 0)
        return Vec3(self.x / ln, self.y / ln, self.z / ln)

    def tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass
class TubeSpec:
    """Specification for one tube to be generated in FreeCAD."""
    name: str
    start: Vec3
    end: Vec3
    radius1: float          # radius at start
    radius2: float          # radius at end (same as radius1 for cylinder)
    wall: float = 0.0       # wall thickness (0 = solid)
    color: tuple[float, float, float] = (0.6, 0.6, 0.65)  # steel gray
    feature: str = "frame"  # feature group: frame | stays | fork

    @property
    def direction(self) -> Vec3:
        return (self.end - self.start).normalized()

    @property
    def length(self) -> float:
        return (self.end - self.start).length()

    @property
    def is_cylinder(self) -> bool:
        return abs(self.radius1 - self.radius2) < 0.01


@dataclass
class PlateSpec:
    """A simple slotted dropout plate.

    A flat rectangular plate lying in the X-Y plane (frame plane), extruded
    along Z by `thickness`, centered at `center`. A U-slot of width
    `slot_width` is cut open to the lower (-Y) edge so the axle can slide in.
    """
    name: str
    center: Vec3            # plate center (at the rear axle)
    width: float            # X extent of the plate
    height: float           # Y extent of the plate
    thickness: float        # Z extent (plate thickness)
    slot_width: float       # width of the axle slot (~ axle diameter)
    feature: str = "dropout"
    color: tuple[float, float, float] = (0.4, 0.4, 0.43)  # dark steel


class FrameGeometry:
    """Compute 3D tube positions from parsed .bcad parameters.

    Coordinate system:
        Origin: BB center
        X: forward (toward head tube / front wheel)
        Y: upward
        Z: right (drive side)
    """

    def __init__(self, parser: BcadParser, axle_dia: float = 10.0):
        self.p = parser
        self.axle_dia = axle_dia
        self.tubes: list[TubeSpec] = []
        self.plates: list[PlateSpec] = []
        self.warnings: list[str] = []

        # Computed reference points (populated by _compute_reference_points)
        self.bb_center = Vec3(0, 0, 0)
        self.rear_axle = Vec3()
        self.ht_top = Vec3()
        self.ht_bottom = Vec3()
        self.st_top = Vec3()
        self.front_axle = Vec3()

    def compute(self) -> list[TubeSpec]:
        """Compute all tube specs, each tagged with its feature group."""
        self._compute_reference_points()
        with self._feature("frame"):
            self._make_bb_shell()
            self._make_head_tube()
            self._make_seat_tube()
            self._make_top_tube()
            self._make_down_tube()
        with self._feature("stays"):
            self._make_chainstays()
            self._make_seatstays()
            self._make_seatstay_bridge()
        with self._feature("fork"):
            self._make_fork()
        # Dropouts are plates, not tubes — kept in self.plates, not self.tubes.
        self._make_dropouts()
        return self.tubes

    @contextmanager
    def _feature(self, name: str):
        """Stamp `feature=name` on every tube appended within this block."""
        start = len(self.tubes)
        yield
        for t in self.tubes[start:]:
            t.feature = name

    def _compute_reference_points(self):
        """Derive all reference points from .bcad parameters."""
        p = self.p

        # ── Angles (convert to radians) ──
        head_angle = math.radians(p.get_float("Head angle", 72.0))
        seat_angle = math.radians(p.get_float("Seat angle", 73.0))

        # ── Key dimensions ──
        stack = p.get_float("Stack", 600.0)
        bb_drop = p.get_float("BB textfield", 65.0)
        cs_length = p.get_float("CS textfield", 450.0)
        ht_length = p.get_float("Head tube length textfield", 150.0)
        st_length = p.get_float("Seat tube length", 500.0)

        # ── Reach ──
        # With measure style 3 (Stack & Reach), FCD textfield stores Reach
        measure_style = p.get_int("Top tube front center measure style", 0)
        fcd = p.get_float("FCD textfield", 400.0)
        if measure_style == 3:
            reach = fcd
        else:
            # Fallback: estimate reach from front center distance
            # This is approximate and should be refined for other styles
            reach = fcd - 250  # rough estimate
            self.warnings.append(
                f"Measure style {measure_style} (not Stack&Reach). "
                f"Reach estimated as {reach:.1f}mm from FCD={fcd}. "
                "Geometry may be inaccurate."
            )

        # ── Fork parameters ──
        fork_type = p.get_int("Fork type", 0)
        fork_atc = p.get_float(f"FORK{fork_type}L", 445.0)
        fork_rake = p.get_float(f"FORK{fork_type}R", 55.0)

        # ── Dropout mode ──
        # BikeCAD defines the rear dropout in one of two modes:
        #   DropoutParamOrStatic == 0 → "static drawing": the dropout is a
        #       built-in library part (StaticDropout, e.g. "DR0001" = Paragon
        #       DR0001). The "Dropout joint N" array is IGNORED by BikeCAD in
        #       this mode — it is dead/leftover state, not the plate shape.
        #   DropoutParamOrStatic == 1 → "parameters": "Dropout model" picks a
        #       family (socket/hooded/…) and only THEN is "Dropout joint N"
        #       a live, decodable plate profile.
        # We do NOT parse the joint array either way: this tube model places
        # stay endpoints from rear_axle + Dropout spacing and never needs the
        # dropout plate outline. The mode is recorded only for the dump/report.
        self.dropout_is_static = p.get_int("DropoutParamOrStatic", 0) == 0
        self.dropout_model = (
            p.get_str("StaticDropout", "?")
            if self.dropout_is_static
            else p.get_str("Dropout model", "?")
        )

        # ── Reference points ──

        # Head tube top (defines the Stack & Reach point)
        self.ht_top = Vec3(reach, stack, 0)

        # Head tube axis direction (bottom → top): backward and up
        ht_dir = Vec3(-math.cos(head_angle), math.sin(head_angle), 0)

        # Head tube bottom
        self.ht_bottom = self.ht_top - ht_dir * ht_length

        # Seat tube top
        st_dir = Vec3(-math.cos(seat_angle), math.sin(seat_angle), 0)
        self.st_top = self.bb_center + st_dir * st_length

        # Rear axle: behind and above BB by CS length and BB drop
        rear_axle_y = bb_drop
        rear_axle_x = -math.sqrt(max(cs_length**2 - bb_drop**2, 0))
        self.rear_axle = Vec3(rear_axle_x, rear_axle_y, 0)

        # Front axle: from head tube bottom along fork
        steerer_down = Vec3(math.cos(head_angle), -math.sin(head_angle), 0)
        rake_dir = Vec3(math.sin(head_angle), math.cos(head_angle), 0)
        self.front_axle = (
            self.ht_bottom
            + steerer_down * fork_atc
            + rake_dir * fork_rake
        )

        # ── Sanity checks ──
        front_axle_y = self.front_axle.y
        expected_axle_y = bb_drop
        axle_y_error = abs(front_axle_y - expected_axle_y)
        if axle_y_error > 20:
            self.warnings.append(
                f"Front axle height ({front_axle_y:.1f}mm) differs from "
                f"BB drop ({expected_axle_y:.1f}mm) by {axle_y_error:.1f}mm. "
                "Fork/geometry parameters may be inconsistent."
            )

        # Store key values for dump
        self._params = {
            "Head angle (deg)": math.degrees(head_angle),
            "Seat angle (deg)": math.degrees(seat_angle),
            "Stack": stack,
            "Reach": reach,
            "BB drop": bb_drop,
            "CS length": cs_length,
            "HT length": ht_length,
            "ST length": st_length,
            "Fork ATC": fork_atc,
            "Fork rake": fork_rake,
            "Dropout mode": (
                f"static ({self.dropout_model})"
                if self.dropout_is_static
                else f"parametric ({self.dropout_model})"
            ),
            "HT top": f"({self.ht_top.x:.1f}, {self.ht_top.y:.1f})",
            "HT bottom": f"({self.ht_bottom.x:.1f}, {self.ht_bottom.y:.1f})",
            "ST top": f"({self.st_top.x:.1f}, {self.st_top.y:.1f})",
            "Rear axle": f"({self.rear_axle.x:.1f}, {self.rear_axle.y:.1f})",
            "Front axle": f"({self.front_axle.x:.1f}, {self.front_axle.y:.1f})",
        }

    # ── Phase 2: Main triangle ─────────────────────────────────────────────

    def _make_bb_shell(self):
        p = self.p
        bb_dia = p.get_float("BB diameter", 40.0)
        bb_len = p.get_float("BB length", 68.0)
        r = bb_dia / 2
        start = Vec3(0, 0, -bb_len / 2)
        end = Vec3(0, 0, bb_len / 2)
        self.tubes.append(TubeSpec(
            name="BB_Shell", start=start, end=end,
            radius1=r, radius2=r,
            wall=3.0,  # typical BB shell wall
            color=(0.45, 0.45, 0.48),
        ))

    def _make_head_tube(self):
        p = self.p
        ht_type = p.get_int("Head tube type", 0)
        top_dia = p.get_float("Head tube diameter", 38.0)
        if ht_type == 1:  # tapered
            bottom_dia = p.get_float("Head tube d", top_dia)
        else:
            bottom_dia = top_dia
        self.tubes.append(TubeSpec(
            name="Head_Tube", start=self.ht_bottom, end=self.ht_top,
            radius1=bottom_dia / 2, radius2=top_dia / 2,
            wall=1.5,
            color=(0.55, 0.55, 0.58),
        ))

    def _make_seat_tube(self):
        p = self.p
        st_type = p.get_int("Seat tube type", 0)
        top_dia = p.get_float("Seat tube diameter", 28.6)
        if st_type == 1:  # tapered
            bottom_dia = p.get_float("Seat tube bottom diameter textfield", top_dia)
        else:
            bottom_dia = top_dia
        self.tubes.append(TubeSpec(
            name="Seat_Tube", start=self.bb_center, end=self.st_top,
            radius1=bottom_dia / 2, radius2=top_dia / 2,
            wall=p.get_float("Wall thickness Seat tube", 0.9),
            color=(0.6, 0.6, 0.63),
        ))

    def _make_top_tube(self):
        p = self.p
        tt_dia = p.get_float("Top tube diameter", 28.6)
        # TT connects ST top to HT top
        self.tubes.append(TubeSpec(
            name="Top_Tube", start=self.st_top, end=self.ht_top,
            radius1=tt_dia / 2, radius2=tt_dia / 2,
            wall=p.get_float("Wall thickness Top tube", 0.9),
            color=(0.6, 0.6, 0.63),
        ))

    def _make_down_tube(self):
        p = self.p
        dt_type = p.get_int("Down tube type", 0)
        rear_dia = p.get_float("Down tube diameter", 31.8)
        if dt_type == 1:
            front_dia = p.get_float("Down tube front diameter", rear_dia)
        else:
            front_dia = rear_dia
        # DT connects BB area to HT bottom
        self.tubes.append(TubeSpec(
            name="Down_Tube", start=self.bb_center, end=self.ht_bottom,
            radius1=rear_dia / 2, radius2=front_dia / 2,
            wall=p.get_float("Wall thickness Down tube", 0.9),
            color=(0.6, 0.6, 0.63),
        ))

    # ── Phase 3: Stays ─────────────────────────────────────────────────────

    def _make_chainstays(self):
        p = self.p
        if not p.get_bool("INCLUDE_CHAINSTAY", True):
            return

        bb_len = p.get_float("BB length", 68.0)
        dropout_spacing = p.get_float("Dropout spacing", 135.0)
        cs_offset = p.get_float("CHAINSTAYOFFSET", 0.0)

        # Chainstay cross-section at BB end: oval
        horz_dia = p.get_float("Chain stay horizontal diameter", 18.0)
        vert_dia = p.get_float("Chain stay vertical diameter", 26.0)
        # At dropout end: round
        rear_dia = p.get_float("Chain stay back diameter", 18.0)

        # For FreeCAD, approximate oval as circle with equivalent area
        # area of ellipse = pi * a * b; equivalent circle r = sqrt(a*b)
        equiv_radius_bb = math.sqrt((horz_dia / 2) * (vert_dia / 2))

        # BB-end z offset: typically starts at BB shell edge
        bb_z_offset = bb_len / 2
        cs_bb_z_position = p.get_float("Chain stay position on BB", 15.0)

        # Dropout z offset: half the dropout spacing
        dropout_z = dropout_spacing / 2

        for side, z_sign in [("Drive", 1.0), ("NonDrive", -1.0)]:
            start = Vec3(0, 0, z_sign * bb_z_offset)
            end = Vec3(
                self.rear_axle.x,
                self.rear_axle.y,
                z_sign * dropout_z,
            )
            self.tubes.append(TubeSpec(
                name=f"Chainstay_{side}",
                start=start, end=end,
                radius1=equiv_radius_bb,
                radius2=rear_dia / 2,
                wall=p.get_float("Wall thickness Chain stay", 1.2),
                color=(0.58, 0.56, 0.55),
            ))

    def _make_seatstays(self):
        p = self.p
        if not p.get_bool("INCLUDE_SEATSTAY", True):
            return

        seat_angle = math.radians(p.get_float("Seat angle", 73.0))
        ss_offset = p.get_float("Seat stay offset", 35.0)
        dropout_spacing = p.get_float("Dropout spacing", 135.0)
        ss_z_offset_top = p.get_float("SSTopZOFFSET", 8.0)

        # Seatstay diameters
        ss_front_dia = p.get_float("SEATSTAY_VF", 19.0)
        ss_rear_dia = p.get_float("SEATSTAY_HR", 17.0)
        taper_len = p.get_float("SEATSTAYtaperLength", 100.0)

        # SS junction on seat tube: offset mm below ST top, along seat tube
        st_dir = Vec3(-math.cos(seat_angle), math.sin(seat_angle), 0)
        ss_junction_2d = self.st_top - st_dir * ss_offset

        # Dropout z offset
        dropout_z = dropout_spacing / 2

        for side, z_sign in [("Drive", 1.0), ("NonDrive", -1.0)]:
            start = Vec3(
                ss_junction_2d.x,
                ss_junction_2d.y,
                z_sign * ss_z_offset_top,
            )
            end = Vec3(
                self.rear_axle.x,
                self.rear_axle.y,
                z_sign * dropout_z,
            )
            self.tubes.append(TubeSpec(
                name=f"Seatstay_{side}",
                start=start, end=end,
                radius1=ss_front_dia / 2,
                radius2=ss_rear_dia / 2,
                wall=p.get_float("Wall thickness Seat stay", 1.0),
                color=(0.58, 0.58, 0.60),
            ))

    def _make_seatstay_bridge(self):
        p = self.p
        if not p.get_bool("SEATSTAYbrdgCheck", False):
            return

        bridge_dia = p.get_float("SEATSTAYbrdgdia1", 16.0)
        # Bridge shift is distance from rear axle along seatstay
        bridge_shift = p.get_float("SEATSTAYbrdgshift", 330.0)

        # Position the bridge between the two seatstays
        # Approximate: fraction along seatstay from dropout end
        # We need the seatstay length to compute the fraction
        seat_angle = math.radians(p.get_float("Seat angle", 73.0))
        ss_offset = p.get_float("Seat stay offset", 35.0)
        st_dir = Vec3(-math.cos(seat_angle), math.sin(seat_angle), 0)
        ss_junction = self.st_top - st_dir * ss_offset

        # Seatstay vector (2D, from dropout to junction)
        ss_vec_2d = Vec3(
            ss_junction.x - self.rear_axle.x,
            ss_junction.y - self.rear_axle.y,
            0,
        )
        ss_length_2d = ss_vec_2d.length()

        if ss_length_2d < 1:
            return

        # fraction along stay from dropout
        frac = min(bridge_shift / ss_length_2d, 0.95)

        dropout_spacing = p.get_float("Dropout spacing", 135.0)
        dropout_z = dropout_spacing / 2
        ss_z_top = p.get_float("SSTopZOFFSET", 8.0)

        # Interpolate position on each seatstay
        bridge_x = self.rear_axle.x + frac * ss_vec_2d.x
        bridge_y = self.rear_axle.y + frac * ss_vec_2d.y
        bridge_z_right = dropout_z + frac * (ss_z_top - dropout_z)
        bridge_z_left = -bridge_z_right

        r = bridge_dia / 2
        self.tubes.append(TubeSpec(
            name="Seatstay_Bridge",
            start=Vec3(bridge_x, bridge_y, bridge_z_left),
            end=Vec3(bridge_x, bridge_y, bridge_z_right),
            radius1=r, radius2=r,
            wall=0.0,
            color=(0.55, 0.55, 0.58),
        ))

    # ── Phase 4: Fork ──────────────────────────────────────────────────────

    def _make_fork(self):
        p = self.p
        fork_type = p.get_int("Fork type", 0)
        prefix = f"FORK{fork_type}"

        fork_atc = p.get_float(f"{prefix}L", 445.0)
        fork_rake = p.get_float(f"{prefix}R", 55.0)
        crown_dia = p.get_float(f"{prefix}D", 35.0)
        dropout_dia = p.get_float(f"{prefix}H", 20.0)
        fork_width = p.get_float(f"{prefix}W", 40.0)

        head_angle = math.radians(p.get_float("Head angle", 72.0))

        # Steerer direction (downward from crown)
        steerer_down = Vec3(math.cos(head_angle), -math.sin(head_angle), 0)
        # Rake direction (perpendicular to steerer, forward)
        rake_dir = Vec3(math.sin(head_angle), math.cos(head_angle), 0)

        # For a straight-blade fork, blades are parallel to steerer but
        # offset by the full rake amount
        blade_top_2d = self.ht_bottom + rake_dir * fork_rake
        blade_bottom_2d = blade_top_2d + steerer_down * fork_atc

        half_w = fork_width / 2

        for side, z_sign in [("Drive", 1.0), ("NonDrive", -1.0)]:
            start = Vec3(blade_top_2d.x, blade_top_2d.y, z_sign * half_w)
            end = Vec3(blade_bottom_2d.x, blade_bottom_2d.y, z_sign * half_w)
            self.tubes.append(TubeSpec(
                name=f"Fork_Blade_{side}",
                start=start, end=end,
                radius1=crown_dia / 2,
                radius2=dropout_dia / 2,
                wall=p.get_float("Wall thickness Down tube", 0.9),
                color=(0.50, 0.50, 0.55),
            ))

        # Steerer tube (through head tube)
        steerer_dia = 28.6  # standard 1-1/8" steerer
        self.tubes.append(TubeSpec(
            name="Steerer",
            start=self.ht_bottom, end=self.ht_top,
            radius1=steerer_dia / 2, radius2=steerer_dia / 2,
            wall=2.0,
            color=(0.48, 0.48, 0.50),
        ))

    # ── Dropouts (simple slot, generic) ────────────────────────────────────

    def _make_dropouts(self):
        """Generate a simple slotted dropout plate on each side.

        Real frames use bought-in dropouts, so this is a generic slot plate
        (not the frame's actual library part). It is derived from the plate
        thickness, the plate footprint dimensions, and the axle diameter —
        positioned at the rear axle, one per side of the dropout spacing.
        """
        p = self.p
        thickness = p.get_float("Default_dropout_plate_thick", 7.0)
        # Plate footprint: reuse the dropout size params when present.
        width = p.get_float("Dropout F", 40.0)      # X extent
        height = p.get_float("Dropout S", 30.0)     # Y extent
        dropout_spacing = p.get_float("Dropout spacing", 135.0)
        slot_width = self.axle_dia

        z = dropout_spacing / 2
        for side, z_sign in [("Drive", 1.0), ("NonDrive", -1.0)]:
            center = Vec3(self.rear_axle.x, self.rear_axle.y, z_sign * z)
            self.plates.append(PlateSpec(
                name=f"Dropout_{side}",
                center=center,
                width=width,
                height=height,
                thickness=thickness,
                slot_width=slot_width,
            ))

    def dump_params(self) -> str:
        """Return a formatted string of computed geometry parameters."""
        lines = ["Computed Frame Geometry", "=" * 50]
        for k, v in self._params.items():
            lines.append(f"  {k:.<30s} {v}")
        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  ! {w}")
        lines.append("")
        lines.append("Tubes:")
        for t in self.tubes:
            r_str = f"R={t.radius1:.1f}"
            if not t.is_cylinder:
                r_str = f"R={t.radius1:.1f}->{t.radius2:.1f}"
            lines.append(
                f"  {t.name:.<25s} L={t.length:.1f}mm  {r_str}"
            )
        return "\n".join(lines)
