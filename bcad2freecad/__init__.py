"""BCad2FreeCAD - Convert BikeCAD .bcad files to FreeCAD Python macros.

Public API (also the names the test suite imports):
    BcadParser              - parse a .bcad file into a key-value store
    Vec3, TubeSpec          - geometry primitives
    FrameGeometry           - compute tube specs from parsed parameters
    FreeCADScriptGenerator  - emit a standalone FreeCAD macro
"""

from .parser import BcadParser
from .geometry import Vec3, TubeSpec, FrameGeometry
from .generator import FreeCADScriptGenerator

__all__ = [
    "BcadParser",
    "Vec3",
    "TubeSpec",
    "FrameGeometry",
    "FreeCADScriptGenerator",
]
