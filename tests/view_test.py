r"""The Python model's view against exact geometry.

    .venv-win\Scripts\python.exe examples\cub\tests\view_test.py

1. The horizon line, for cameras at random pitches and banks, against the
   horizon worked out in floating point from the same camera matrix: the
   line through every direction level with the ground. Each end drawn must
   lie within HORIZON_BOUND pixels of it, and the line must be drawn
   whenever the true one crosses the view, well inside it.
2. The camera's matrix, at random attitudes in the state's 16-bit angles,
   against the rotation they make worked out in floating point; and,
   banked, the horizon against where the bank puts it: the view rolled
   about the Cub's own length, whatever its heading.
3. The objects, at random attitudes round the airfield: each object's
   centre, as it lands on the screen, against where its position lands in
   floating point, from the same eye. The camera matrix's entries are
   bytes, and each centre is put right for their rounding
   (game.fine_centre), so that the objects do not wobble as the view turns.
4. The start of a flight: the runway's two sides, which run from behind
   the eye to ahead of it, are drawn from where they come into the view,
   cut at the near plane rather than missing. Where each comes into the
   view is worked out in floating point from the runway's corners and the
   camera.
"""
import math
import random
import sys
from dataclasses import replace
from pathlib import Path

CUB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CUB))

import game  # noqa: E402
import models  # noqa: E402
from fast3d import model  # noqa: E402

HORIZON_BOUND = 2.5     # pixels: a truncated division on each of two terms, and the clip
ENTRY_BOUND = 1.0       # 127ths: a rounding, and the sines' and products' floors
BANKED_BOUND = 3.0      # pixels: the horizon's, and its matrix's entries each up to half a 127th out
CENTRE_MEAN = 0.1       # pixels: an object's centre, worked out with the camera matrix's
CENTRE_MOST = 0.3       # residuals as well as its bytes


def true_horizon(rc):
    """(a, b, c) with a (x - cx) + b (cy - y) + c = 0 the horizon on the screen,
    in floating point from the matrix's entries."""
    ux, uy, uz = rc[3], rc[4], rc[5]
    return ux, uy, game.FOCAL * uz


def distance(line, x, y):
    a, b, c = line
    return abs(a * (x - game.CENTRE_X) + b * (game.CENTRE_Y - y) + c) / math.hypot(a, b)


def crosses_view(line, margin):
    """Whether the true line passes through the view at least margin inside it."""
    left, top, right, bottom = game.WINDOW
    corners = [(left + margin, top + margin), (right - margin, top + margin),
               (left + margin, bottom - margin), (right - margin, bottom - margin)]
    a, b, c = line
    sides = [a * (x - game.CENTRE_X) + b * (game.CENTRE_Y - y) + c for x, y in corners]
    return min(sides) < 0 < max(sides)


def check_horizon(failures):
    rng = random.Random(1938)
    worst, total, drawn = 0.0, 0.0, 0
    for case in range(20000):
        angles = (rng.randrange(256), rng.randrange(256), rng.randrange(256))
        if case < 256:                        # every pitch, level
            angles = (case, 0, 0)
        rc = model.make_matrix(*angles)
        line = true_horizon(rc)
        got = game.horizon_line(rc)
        if got is None:
            if crosses_view(line, HORIZON_BOUND + 1):
                failures.append(f"horizon: camera {angles}: not drawn, but it crosses the view")
            continue
        x0, y0, x1, y1 = got
        far = max(distance(line, x0, y0), distance(line, x1, y1))
        worst, total, drawn = max(worst, far), total + far, drawn + 1
        if far > HORIZON_BOUND:
            failures.append(f"horizon: camera {angles}: drawn {got}, {far:.2f} pixels from the true line")
    print(f"  horizon: {drawn} of 20000 cameras see it; an end at most {worst:.2f} pixels "
          f"from the true line, {total / max(drawn, 1):.2f} on average")


def ideal_camera(state) -> list:
    """Rc in floating point, from the Cub's attitude in degrees: rolled by
    the bank about its length (right wing down), pitched with the line of
    sight VIEW_DOWN below the datum (nose up), turned to the heading
    (right): Ry Rx Rz in fast3d's senses, x nose down and z the view's
    right side up."""
    def radians(angle):
        return 2 * math.pi * angle / 65536
    x, y, z = radians(game.VIEW_DOWN - state.pitch), radians(state.heading), radians(-state.bank)
    sx, cx, sy, cy, sz, cz = math.sin(x), math.cos(x), math.sin(y), math.cos(y), math.sin(z), math.cos(z)
    ry = [cy, 0, sy, 0, 1, 0, -sy, 0, cy]
    rx = [1, 0, 0, 0, cx, -sx, 0, sx, cx]
    rz = [cz, -sz, 0, sz, cz, 0, 0, 0, 1]

    def times(a, b):
        return [sum(a[3 * i + k] * b[3 * k + j] for k in range(3)) for i in range(3) for j in range(3)]
    return times(ry, times(rx, rz))


def check_camera(failures):
    rng = random.Random(1940)
    world = game.load_world()
    worst = 0.0
    for case in range(5000):
        state = replace(game.start_state(world), pitch=rng.randrange(-32768, 32768), heading=rng.randrange(65536),
                        bank=rng.randrange(-32768, 32768), flags=0)
        far = max(abs(got - 127 * want) for got, want in zip(game.camera_matrix(state), ideal_camera(state)))
        worst = max(worst, far)
        if far > ENTRY_BOUND:
            failures.append(f"camera: pitch {state.pitch}, heading {state.heading}, bank {state.bank}: "
                            f"an entry {far:.2f} 127ths out")
    print(f"  camera: 5000 attitudes, every entry within {worst:.2f} 127ths of the true rotation")


def check_banked(failures):
    """Banked, the view rolls about the Cub's own length, whatever its
    heading: the horizon is where it would be with the wings level, the line
    of sight theta above it, turned about the view's centre by the bank. On
    the screen, with u = x - CENTRE_X and v = CENTRE_Y - y, that is
    -u sin(bank) + v cos(bank) + FOCAL tan(theta) = 0: banked right, its
    right end higher."""
    rng = random.Random(1939)
    world = game.load_world()
    worst = 0.0
    for case in range(2000):
        up, bank, heading = rng.randint(-5461, 5461), rng.randint(-10923, 10923), rng.randrange(65536)
        state = replace(game.start_state(world), pitch=game.VIEW_DOWN + up, bank=bank, heading=heading,
                        y=500 << 16, flags=0)
        theta, roll = 2 * math.pi * up / 65536, 2 * math.pi * bank / 65536
        line = (-math.sin(roll), math.cos(roll), game.FOCAL * math.tan(theta))
        got = game.horizon_line(game.camera_matrix(state))
        if got is None:
            if crosses_view(line, HORIZON_BOUND + 1):
                failures.append(f"banked: pitch {up}, bank {bank}, heading {heading}: no horizon drawn")
            continue
        far = max(distance(line, got[0], got[1]), distance(line, got[2], got[3]))
        worst = max(worst, far)
        if far > BANKED_BOUND:
            failures.append(f"banked: pitch {up}, bank {bank}, heading {heading}: drawn {got}, "
                            f"{far:.2f} pixels from the true line")
    print(f"  banked: 2000 attitudes, the horizon's ends at most {worst:.2f} pixels from where the bank puts it")


def check_objects(failures):
    """Each object's centre, T, where it lands on the screen, against where
    the object's position lands in floating point, from the same eye."""
    rng = random.Random(1941)
    world = game.load_world()
    x0, z0, _ = world.start
    errors = []
    for case in range(300):
        state = replace(game.start_state(world), x=(x0 + rng.randint(-600, 600)) << 16,
                        y=rng.randint(20, 500) << 16, z=(z0 + rng.randint(-1500, 2500)) << 16,
                        pitch=rng.randint(-3000, 3000), heading=rng.randrange(65536),
                        bank=rng.randint(-8000, 8000), flags=0)
        rf, eye = ideal_camera(state), game.eye(state)
        for o, t, _, _ in game.objects_seen(state, world):
            d = [model.to_signed16(p - e) for p, e in zip(o.position, eye)]
            cx, cy, cz = (sum(rf[3 * j + i] * d[j] for j in range(3)) for i in range(3))
            if t[2] < 20 * 127 or cz < 20:
                continue
            drawn = (game.FOCAL * t[0] / t[2], game.FOCAL * t[1] / t[2])
            errors.append(math.dist(drawn, (game.FOCAL * cx / cz, game.FOCAL * cy / cz)))
    mean = sum(errors) / len(errors)
    print(f"  objects: {len(errors)} centres in view at 300 attitudes, {mean:.3f} pixels from exact on "
          f"average, {max(errors):.2f} at most")
    if mean > CENTRE_MEAN or max(errors) > CENTRE_MOST:
        failures.append(f"objects: centres {mean:.3f} pixels from exact on average, {max(errors):.2f} at most")


def first_in_view(corner_a, corner_b, eye, rc_float):
    """The nearest point of the line between two world points that is in
    front of the near plane and in the view, projected exactly: (x, y), or
    None if none of it is."""
    def camera(p):
        d = [p[i] - eye[i] for i in range(3)]
        return [sum(rc_float[3 * j + i] * d[j] for j in range(3)) for i in range(3)]
    a, b = camera(corner_a), camera(corner_b)
    left, top, right, bottom = game.WINDOW
    best = None
    for k in range(4001):
        p = [a[i] + k / 4000 * (b[i] - a[i]) for i in range(3)]
        if p[2] < model.NEAR * 128 / 127:
            continue
        x, y = game.CENTRE_X + game.FOCAL * p[0] / p[2], game.CENTRE_Y - game.FOCAL * p[1] / p[2]
        if left <= x <= right and top <= y <= bottom and (best is None or p[2] < best[0]):
            best = (p[2], x, y)
    return best and best[1:]


def check_start(failures):
    world = game.load_world()
    state = game.start_state(world)
    screen = game.frame(state, world, 0, 0)[1]
    eye = game.eye(state)
    rc_float = ideal_camera(state)
    first = next(o for o in world.objects if o.model == "runway-start")
    h, w = models.RUNWAY_HALF_LENGTH, models.RUNWAY_HALF_WIDTH
    x, z = first.position[0], first.position[2]
    for side in (-w, w):
        near_corner, far_corner = (x + side, 0, z - h), (x + side, 0, z + h)
        if game.eye(state)[2] < near_corner[2]:
            failures.append(f"start: the runway's first segment does not reach behind the eye")
        want = first_in_view(near_corner, far_corner, eye, rc_float)
        if want is None:
            failures.append(f"start: the runway's side at {side} is not in the view")
            continue
        wx, wy = want
        near = [(px, row) for px in range(max(0, round(wx) - 3), min(256, round(wx) + 4))
                for row in range(max(0, round(wy) - 3), min(game.WINDOW[3] + 1, round(wy) + 4))
                if screen[model.screen_address(px, row) - 0x4000] & (0x80 >> (px & 7))]
        print(f"  start: the runway's side at {side:+} feet comes into the view at "
              f"({wx:.1f}, {wy:.1f}); {'drawn' if near else 'MISSING'} there")
        if not near:
            failures.append(f"start: nothing drawn near ({wx:.1f}, {wy:.1f}), where the side comes into the view")


def main():
    failures = []
    check_horizon(failures)
    check_camera(failures)
    check_banked(failures)
    check_objects(failures)
    check_start(failures)
    for f in failures[:20]:
        print("FAIL", f)
    print("view_test:", "ok" if not failures else f"{len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
