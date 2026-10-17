"""Where Cub finds the fast3d engine, beside it in examples/fast3d: its
model (fast3d's model.py, which the engine's Z80 matches exactly) and its
build's writers (tables, line blocks, model blocks), the latter loaded under
a name of its own since Cub has a build.py too.

    from fast3d import model, build
"""
import importlib.util
import sys
from pathlib import Path

FAST3D = Path(__file__).resolve().parent.parent / "fast3d"
sys.path.insert(0, str(FAST3D))

import model  # noqa: E402,F401

_spec = importlib.util.spec_from_file_location("fast3d_build", FAST3D / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)
