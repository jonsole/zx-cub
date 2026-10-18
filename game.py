"""Cub in Python: the model the Z80 version matches byte for byte.

The frame is the game's interface. Given the game state, the keys held and
the steps owed (fiftieths of a second since the last frame), `frame` gives
the next game state and the screen it drew on -- the whole 6,912 bytes, as
the Z80 leaves them. The view is drawn with fast3d's model
(examples/fast3d/model.py), so it is exactly what the engine draws.

A frame runs the steps owed through the flight model (flight.py), counts
them into the clock, and draws the cockpit view, with the horizon line,
above the panel (panel.py).

The view is character rows 0..17 in black on cyan; the panel rows 18..23 in
white on blue. The view's centre is (CENTRE_X, CENTRE_Y), 256 pixels from
the eye as fast3d has it (FOCAL), so the view is 53 degrees across.
"""
import json
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

import flight
import j3
import models
import panel
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

EYE_HEIGHT = 7                      # feet: the pilot's eye above the main wheels
VIEW_DOWN = flight.angle(j3.VIEW_DOWN)      # the line of sight below the fuselage's datum
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


def stored(size: int, signed: bool = False):
    """A field of the state, kept in so many bytes, signed or not."""
    return field(metadata={"bytes": size, "signed": signed})


@dataclass(frozen=True)
class State:
    """The game state, as the Z80 keeps it from `state`, in this order,
    little-endian (build.py writes its labels from STATE_LAYOUT)."""
    x: int = stored(4)              # the Cub's main wheels: feet, 16.16 (flight.py's units)
    y: int = stored(4)
    z: int = stored(4)
    heading: int = stored(2)        # its attitude, 65,536 to the turn: heading right,
                                    # pitch nose up, bank right wing down
    pitch: int = stored(2, signed=True)
    bank: int = stored(2, signed=True)
    speed: int = stored(3)          # along the flight path, 2^-16 feet a step
    gamma: int = stored(3, signed=True)     # the flight path's climb, angle units times 256
    rpm: int = stored(2)            # the engine
    throttle: int = stored(1)       # 0..255
    stick: int = stored(1, signed=True)     # back positive, -64..64
    stick_roll: int = stored(1, signed=True)    # the stick to the side, right positive, -64..64
    rudder: int = stored(1, signed=True)    # right positive, -64..64
    flags: int = stored(1)          # flight.PARKED, GROUND, STALLED
    clock: int = stored(2)          # steps since the flight began
    keys: int = stored(2)           # the keys held last frame
    drawing: int = stored(1)        # the screen the next frame is drawn on: 0 at $4000, 1 at $C000
    # What the panel shows (panel.values), on both screens.
    shown_mph: int = stored(1)
    shown_feet: int = stored(2)
    shown_heading: int = stored(2)
    shown_throttle: int = stored(1)
    shown_climb: int = stored(1, signed=True)
    shown_stall: int = stored(1)

    def pack(self) -> bytes:
        """The bytes the Z80 keeps. A value its field cannot hold is an error
        in the flight model, which keeps each in its field's range."""
        return b"".join(getattr(self, f.name).to_bytes(f.metadata["bytes"], "little", signed=f.metadata["signed"])
                        for f in fields(self))


STATE_LAYOUT = [(f.name, f.metadata["bytes"]) for f in fields(State)]


def start_state(world: World) -> State:
    """As the Spectrum starts, a flight: the Cub tail down at the world's
    start, lined up, the engine idling, the parking brake on; the first
    frame drawn on the screen at $C000, the one not shown; and nothing on
    the panel yet."""
    x, z, heading = world.start
    return State(x=x << 16, y=0, z=z << 16, heading=heading << 8, pitch=flight.THREE_POINT, bank=0,
                 speed=0, gamma=0, rpm=flight.IDLE_RPM, throttle=0, stick=0, stick_roll=0, rudder=0,
                 flags=flight.PARKED | flight.GROUND, clock=0, keys=0, drawing=1,
                 **panel.NOTHING_SHOWN)


def frame(state: State, world: World, held: int, steps: int, draw: bool = True) -> tuple:
    """(the next state, the screen drawn on, all 6,912 bytes): the steps
    owed run, at most MAX_STEPS, each with the keys held (keys.py's bits).
    With draw false,
    no screen (for tests of the flying alone)."""
    steps = min(steps, MAX_STEPS)
    for _ in range(steps):
        state = flight.step(state, held)
    after = replace(state, clock=(state.clock + steps) & 0xFFFF, keys=held, drawing=state.drawing ^ 1,
                    **panel.values(state))
    return after, screen(view_lines(after, world), after) if draw else None


def eye(state: State) -> tuple:
    """The camera's position: whole feet, the eye EYE_HEIGHT above the wheels."""
    return state.x >> 16, ((state.y >> 16) + EYE_HEIGHT) & 0xFFFF, state.z >> 16


def camera_angles(state: State) -> tuple:
    """The camera's angles, 65,536 to the turn, about x, y and z as fast3d
    turns them: the pitch (fast3d's is nose down, and the line of sight
    VIEW_DOWN below the datum), the heading, and the roll (fast3d's turns
    the view's right side up: the Cub banked left)."""
    return (VIEW_DOWN - state.pitch) & 0xFFFF, state.heading, (-state.bank) & 0xFFFF


def q15(a: int, b: int) -> int:
    """A product of two numbers with 32,767 for 1.0, floored, as the Z80
    takes the high word of a 32-bit product shifted left once."""
    return (a * b) >> 15


def matrix_entry(q: int) -> int:
    """A Q15 entry as fast3d keeps it, 127 for 1.0: (127 q + 16,384) >> 15.
    The entries' sums never pass 16 bits: each is at most 1 in size, and
    the table's sines are at most 32,767, so floors cannot take one past."""
    if not -32768 <= q <= 32767:
        raise ValueError(f"a camera matrix entry of {q} does not fit 16 bits")
    return (q * 127 + 16384) >> 15


RESIDUAL_SHIFT = 5                  # residuals in 32nds of an entry's unit: 4,064 for 1.0


def matrix_residual(q: int) -> int:
    """What rounding a Q15 entry to a byte left out, in 32nds of the byte's
    unit: (127 q + 512) >> 10, the entry with 127 x 32 for 1.0, less 32
    times matrix_entry's. Within +-16, so that the Z80 multiplies by it in
    five rounds, and keeps only its low byte."""
    residual = ((q * 127 + 512) >> 10) - (matrix_entry(q) << RESIDUAL_SHIFT)
    if not -16 <= residual <= 16:
        raise ValueError(f"the residual {residual} of {q} is past 16")
    return residual


def camera_q15(state: State) -> list:
    """Rc, the camera's matrix, row by row, in Q15: the Cub's attitude,
    rolled about its own length, then pitched, then turned to its heading,
    Ry Rx Rz in fast3d's senses. Made from the full 16-bit angles, with the
    flight model's interpolated sines, so that the view turns smoothly:
    fast3d's make_matrix takes its angles in whole 256ths of a turn, steps
    of 1.4 degrees, and turns the other way round, Rz Ry Rx. Each product
    is q15's, in this order, as the Z80 makes them."""
    x, y, z = camera_angles(state)
    sx, cx, sy, cy, sz, cz = (flight.sin16(x), flight.cos16(x), flight.sin16(y), flight.cos16(y),
                              flight.sin16(z), flight.cos16(z))
    sxsz, sxcz = q15(sx, sz), q15(sx, cz)
    return [q15(cy, cz) + q15(sy, sxsz), q15(sy, sxcz) - q15(cy, sz), q15(sy, cx),
            q15(cx, sz), q15(cx, cz), -sx,
            q15(cy, sxsz) - q15(sy, cz), q15(sy, sz) + q15(cy, sxcz), q15(cy, cx)]


def camera_matrix(state: State) -> list:
    """Rc as fast3d keeps it, row by row, each entry a byte, 127 for 1.0."""
    return [matrix_entry(q) for q in camera_q15(state)]


def camera_residuals(state: State) -> list:
    """What rounding Rc's entries to bytes left out, row by row, in 32nds
    of a byte's unit."""
    return [matrix_residual(q) for q in camera_q15(state)]


def fine_centre(t: tuple, position: tuple, camera: tuple, residuals: list) -> tuple:
    """An object's centre in camera space, T, with what Rc's rounding left
    out put back. fast3d's cull works T out as Rc^T d exactly, d = P - C,
    with Rc's entries in bytes: rounded, each up to half a 127th out, which
    puts an object up to a third of a degree from where it is, and as the
    camera turns they round now one way and now the other, so that the
    objects wobble by a pixel or more a frame. The residuals' share,
    (R^T d + 16) >> 5, makes T good to an 8,000th instead, a 30th of a
    pixel. Only for an object the cull lets through, as the Z80 does it:
    the cull is generous enough not to need it."""
    d = [model.to_signed16(p - c) for p, c in zip(position, camera)]
    half = 1 << (RESIDUAL_SHIFT - 1)
    return tuple(t[i] + ((sum(residuals[3 * j + i] * d[j] for j in range(3)) + half) >> RESIDUAL_SHIFT)
                 for i in range(3))


def objects_seen(state: State, world: World) -> list:
    """Each object the camera sees, in the world's order, as (the object,
    T its centre in camera space, its points, its cut lines): the points
    transform_object's, None behind the near plane, and the cut lines
    cut_edges', each edge crossing the near plane from its front end's
    point to where it crosses."""
    rc, residuals = camera_matrix(state), camera_residuals(state)
    camera = eye(state)
    seen = []
    for o in world.objects:
        vertices, edges = models.model(o.model)
        t = model.view_centre(o.position, camera, rc, wrap=True)
        if t is None or model.culled(t, model.bounding_radius(vertices)):
            continue
        t = fine_centre(t, o.position, camera, residuals)
        m = model.view_matrix(rc, model.make_matrix(0, o.turn, 0))
        seen.append((o, t) + model.object_lines(vertices, edges, m, t, CENTRE_X, CENTRE_Y))
    return seen


def view_lines(state: State, world: World) -> list:
    """The cockpit view's lines, clipped to the view: the horizon, then each
    object the camera sees, its edges in front of the near plane and those
    crossing it cut there."""
    lines = [horizon_line(camera_matrix(state))]
    for o, _, points, cuts in objects_seen(state, world):
        _, edges = models.model(o.model)
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


def screen(lines: list, state: State) -> bytes:
    """The whole screen: the view's lines on an empty bitmap, the panel as
    the state shows it, and the attributes."""
    bitmap = bytearray(6144)
    for line in lines:
        for x, y in model.line(*line):
            bitmap[model.screen_address(x, y) - 0x4000] |= 0x80 >> (x & 7)
    attributes = bytearray([VIEW_ATTRIBUTE] * (32 * VIEW_ROWS) + [PANEL_ATTRIBUTE] * (32 * (24 - VIEW_ROWS)))
    panel.draw(bitmap, attributes, state)
    return bytes(bitmap) + bytes(attributes)
