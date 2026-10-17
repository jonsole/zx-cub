"""Cub in Python: the model the Z80 version matches byte for byte.

The frame is the game's interface. Given the game state, the keys held and
the steps owed (fiftieths of a second since the last frame), `frame` gives
the next game state and the screen it drew on -- the whole 6,912 bytes, as
the Z80 leaves them. The view is drawn with fast3d's model
(examples/fast3d/model.py), so it is exactly what the engine draws.

So far the Cub stands still at the start of the runway: a frame counts the
steps into the clock and draws the cockpit view, with the horizon line,
above an empty panel. Keys are taken and kept, and do nothing yet.

The view is character rows 0..17 in black on cyan; the panel rows 18..23 in
white on blue. The view's centre is (CENTRE_X, CENTRE_Y), 256 pixels from
the eye as fast3d has it (FOCAL), so the view is 53 degrees across.
"""
import json
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

import models
from fast3d import model

CUB = Path(__file__).resolve().parent

VIEW_ROWS = 18                      # character rows of view; the panel has the rest
WINDOW = (0, 0, 255, 8 * VIEW_ROWS - 1)     # left, top, right, bottom: the view, inclusive
CENTRE_X, CENTRE_Y = 128, 4 * VIEW_ROWS     # its middle: fast3d's SCREEN_CENTRE_X and _Y
FOCAL = 256                         # fast3d's: the screen is 256 pixels from the eye
HORIZON_REACH = 128                 # how far each side of the centre the horizon's ends
                                    # are worked out: past the view's edges
VIEW_ATTRIBUTE = 0x28               # black ink on cyan paper
PANEL_ATTRIBUTE = 0x0F              # white ink on blue paper

EYE_HEIGHT = 7                      # feet: the pilot's eye above the ground, tail down
GROUND_PITCH = -6 & 0xFF            # the Cub's nose-up attitude on its three wheels,
                                    # 8.4 degrees (fast3d's pitch is nose down)
MAX_STEPS = 10                      # the most steps a frame runs, however slow it was


@dataclass(frozen=True)
class WorldObject:
    name: str
    model: str                      # its model's name in models.MODELS
    position: tuple                 # x, y, z: 16-bit, feet
    turn: int                       # about the vertical, 256 to the circle


@dataclass(frozen=True)
class World:
    objects: list
    start: tuple                    # x, z, heading


def load_world(path: Path = CUB / "world.json") -> World:
    """The world's objects, in world.json's order, each with its model: a
    runway as its segments, from its near end along its turn, named for it
    and their place ("runway 1", ...)."""
    source = json.loads(path.read_text(encoding="utf-8"))
    objects = []
    for name, o in source["objects"].items():
        if o["kind"] != "runway":
            objects.append(WorldObject(name, o["kind"], (o["x"], o["y"], o["z"]), o["turn"]))
            continue
        ahead = model.ideal_matrix(0, o["turn"], 0)[2::3]      # the turned z axis
        last = o["segments"] - 1
        for i in range(o["segments"]):
            along = (2 * i + 1) * models.RUNWAY_HALF_LENGTH
            position = tuple((p + round(along * a)) & 0xFFFF for p, a in zip((o["x"], o["y"], o["z"]), ahead))
            segment = "runway-start" if i == 0 else "runway-end" if i == last else "runway-middle"
            objects.append(WorldObject(f"{name} {i + 1}", segment, position, o["turn"]))
    start = source["start"]
    return World(objects, (start["x"], start["z"], start["heading"]))


def stored(size: int):
    """A field of the state, kept in so many bytes."""
    return field(metadata={"bytes": size})


@dataclass(frozen=True)
class State:
    """The game state, as the Z80 keeps it from `state`, in this order,
    little-endian (build.py writes its labels from STATE_LAYOUT)."""
    cub_x: int = stored(2)          # the Cub, feet
    cub_y: int = stored(2)
    cub_z: int = stored(2)
    cub_pitch: int = stored(1)      # its attitude: fast3d's angles
    cub_heading: int = stored(1)
    cub_bank: int = stored(1)
    clock: int = stored(2)          # steps since the flight began
    keys: int = stored(2)           # the keys held last frame
    drawing: int = stored(1)        # the screen the next frame is drawn on: 0 at $4000, 1 at $C000

    def pack(self) -> bytes:
        return b"".join(getattr(self, name).to_bytes(size, "little") for name, size in STATE_LAYOUT)


STATE_LAYOUT = [(f.name, f.metadata["bytes"]) for f in fields(State)]


def start_state(world: World) -> State:
    """As the Spectrum starts: the Cub tail down at the world's start, and
    the first frame drawn on the screen at $C000, the one not shown."""
    x, z, heading = world.start
    return State(cub_x=x, cub_y=0, cub_z=z, cub_pitch=GROUND_PITCH, cub_heading=heading, cub_bank=0,
                 clock=0, keys=0, drawing=1)


def frame(state: State, world: World, keys: int, steps: int) -> tuple:
    """(the next state, the screen drawn on, all 6,912 bytes)."""
    steps = min(steps, MAX_STEPS)
    after = replace(state, clock=(state.clock + steps) & 0xFFFF, keys=keys, drawing=state.drawing ^ 1)
    return after, screen(view_lines(after, world))


def eye(state: State) -> tuple:
    return state.cub_x, state.cub_y + EYE_HEIGHT, state.cub_z


def camera_angles(state: State) -> tuple:
    """fast3d's camera angles, about x, y and z: pitch, heading, bank."""
    return state.cub_pitch, state.cub_heading, state.cub_bank


def view_lines(state: State, world: World) -> list:
    """The cockpit view's lines, clipped to the view: the horizon, then each
    object the camera sees, its edges in front of the near plane and those
    crossing it cut there."""
    rc = model.make_matrix(*camera_angles(state))
    camera = eye(state)
    lines = [horizon_line(rc)]
    for o in world.objects:
        vertices, edges = models.model(o.model)
        t = model.view_centre(o.position, camera, rc, wrap=True)
        if t is None or model.culled(t, model.bounding_radius(vertices)):
            continue
        m = model.view_matrix(rc, model.make_matrix(0, o.turn, 0))
        points, cuts = model.object_lines(vertices, edges, m, t, CENTRE_X, CENTRE_Y)
        lines += [model.clip_line(*points[i], *points[j], WINDOW) for i, j in edges if points[i] and points[j]]
        lines += [model.clip_line(*cut, WINDOW) for cut in cuts]
    return [line for line in lines if line]


def horizon_line(rc: list):
    """The horizon, clipped to the view, or None if it is out of it.

    u = Rc^T (0, 1, 0), the world's up in camera space, is Rc's middle row,
    and a direction is level when u . c = 0: on the screen,
    u_x (x - CENTRE_X) + u_y (CENTRE_Y - y) + FOCAL u_z = 0. Mostly level
    (|u_x| <= |u_y|), y is worked out at x = CENTRE_X -+ HORIZON_REACH, the
    view's left edge and one past its right, as CENTRE_Y + a -+ b with
    a = FOCAL u_z / u_y and b = HORIZON_REACH u_x / u_y; banked steeper
    than 45 degrees, x at y = CENTRE_Y -+ HORIZON_REACH, past the top and
    bottom, the same way with u_x and u_y swapped. Each is fast3d's
    divide_wide, of a 16-bit numerator by a byte, truncated and held to
    +-16,383, so the ends fit 16 bits; then clip_line. (The Z80 makes the
    numerators by placing u in a byte: FOCAL u_z is u_z * 256, and
    HORIZON_REACH u half that.)"""
    ux, uy, uz = rc[3], rc[4], rc[5]
    if abs(ux) <= abs(uy):
        if uy == 0:
            return None                       # looking straight up or down
        sign = 1 if uy > 0 else -1
        a = model.divide_wide(sign * FOCAL * uz, abs(uy))
        b = model.divide_wide(sign * HORIZON_REACH * ux, abs(uy))
        ends = (CENTRE_X - HORIZON_REACH, CENTRE_Y + a - b, CENTRE_X + HORIZON_REACH, CENTRE_Y + a + b)
    else:
        sign = 1 if ux > 0 else -1
        a = model.divide_wide(-sign * FOCAL * uz, abs(ux))
        b = model.divide_wide(sign * HORIZON_REACH * uy, abs(ux))
        ends = (CENTRE_X + a - b, CENTRE_Y - HORIZON_REACH, CENTRE_X + a + b, CENTRE_Y + HORIZON_REACH)
    return model.clip_line(*ends, WINDOW)


def screen(lines: list) -> bytes:
    """The whole screen: the lines on an empty bitmap, and the attributes."""
    bitmap = bytearray(6144)
    for line in lines:
        for x, y in model.line(*line):
            bitmap[model.screen_address(x, y) - 0x4000] |= 0x80 >> (x & 7)
    attributes = bytes([VIEW_ATTRIBUTE] * (32 * VIEW_ROWS) + [PANEL_ATTRIBUTE] * (32 * (24 - VIEW_ROWS)))
    return bytes(bitmap) + attributes
