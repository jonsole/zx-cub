r"""The Python model's view against exact geometry.

    .venv-win\Scripts\python.exe examples\cub\tests\view_test.py

1. The horizon line, for cameras at random pitches and banks, against the
   horizon worked out in floating point from the same camera matrix: the
   line through every direction level with the ground. Each end drawn must
   lie within HORIZON_BOUND pixels of it, and the line must be drawn
   whenever the true one crosses the view, well inside it.
2. Banked, at random attitudes, the horizon against where the bank puts
   it: the view rolled about the Cub's own length, whatever its heading.
3. The start of a flight: the runway's two sides, which run from behind
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


def check_banked(failures):
    """Banked, the view rolls about the Cub's own length, whatever its
    heading: the horizon is where it would be with the wings level, the line
    of sight theta above it, turned about the view's centre by the bank. On
    the screen, with u = x - CENTRE_X and v = CENTRE_Y - y, that is
    -u sin(bank) + v cos(bank) + FOCAL tan(theta) = 0: banked right, its
    right end higher. The angles are whole bytes, as fast3d takes them, so
    that only the matrices' rounding is measured."""
    rng = random.Random(1939)
    world = game.load_world()
    worst = 0.0
    for case in range(2000):
        up, bank, heading = rng.randint(-21, 21), rng.randint(-42, 42), rng.randrange(256)
        state = replace(game.start_state(world), pitch=game.VIEW_DOWN + 256 * up, bank=256 * bank,
                        heading=256 * heading, y=500 << 16, flags=0)
        theta, roll = math.radians(up * 360 / 256), math.radians(bank * 360 / 256)
        line = (-math.sin(roll), math.cos(roll), game.FOCAL * math.tan(theta))
        got = game.horizon_line(game.camera_matrix(state))
        if got is None:
            if crosses_view(line, HORIZON_BOUND + 1):
                failures.append(f"banked: pitch {up}, bank {bank}, heading {heading}: no horizon drawn")
            continue
        far = max(distance(line, got[0], got[1]), distance(line, got[2], got[3]))
        worst = max(worst, far)
        if far > HORIZON_BOUND:
            failures.append(f"banked: pitch {up}, bank {bank}, heading {heading}: drawn {got}, "
                            f"{far:.2f} pixels from the true line")
    print(f"  banked: 2000 attitudes, the horizon's ends at most {worst:.2f} pixels from where the bank puts it")


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
    rc_float = model.ideal_matrix(*game.camera_angles(state))
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
    check_banked(failures)
    check_start(failures)
    for f in failures[:20]:
        print("FAIL", f)
    print("view_test:", "ok" if not failures else f"{len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
