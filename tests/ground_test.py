r"""The Cub on the ground and taking off, through the frame: scripted runs of
keys and steps, each checked against what j3.py's figures work out to in
floating point -- the manual's lift-off speed, the tail's lift from its
stated assumptions, the turn the rudder's radius makes, the stop the
brakes' friction makes.

    .venv-win\Scripts\python.exe examples\cub\tests\ground_test.py

1. A flight starts lined up on the runway, engine idling, brakes on, and
   the brakes hold it, even at full throttle.
2. The throttle stays where it is set.
3. The tail starts to come up, stick central and full throttle, at
   TAIL_UP_MPH; with the stick forward sooner, where the elevator's extra
   lift balances the load; with the stick back, not before the Cub lifts
   off.
4. Held tail down (stick back), the Cub lifts off at the manual's 39 mph,
   in about the published ground roll; pulled back at speed with the tail
   up, within a second, and climbs away. Left alone, stick central, it
   lifts off where the tail's balance leaves the wing enough attack.
5. The rudder turns the Cub on the ground, at the radius full rudder makes.
6. The brakes stop it, in the distance their friction makes.
7. The same run gives the same state whatever the frame rate: steps carry
   the time.
"""
import math
import sys
from dataclasses import replace
from pathlib import Path

CUB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CUB))

import flight  # noqa: E402
import game  # noqa: E402
import j3  # noqa: E402
import keys  # noqa: E402

WORLD = game.load_world()
STEP = 1 / 50                                   # seconds


class Run:
    """A flight driven a step a frame (or more), keeping what each step left."""

    def __init__(self, state=None):
        self.state = state or game.start_state(WORLD)
        self.steps = 0

    def hold(self, held: int, steps: int, per_frame: int = 1, until=None):
        """Hold the keys for so many steps; stop early once until(state) holds."""
        done = 0
        while done < steps:
            n = min(per_frame, steps - done)
            self.state, _ = game.frame(self.state, WORLD, held, n, draw=False)
            done += n
            self.steps += n
            if until and until(self.state):
                return True
        return False

    @property
    def mph(self) -> float:
        return flight.mph(self.state)


def release_brakes(run: Run) -> None:
    """A tap on the brakes takes the parking brake off."""
    run.hold(keys.BRAKES, 1)


def check(failures, what, ok, detail):
    print(f"  {what}: {detail}{'' if ok else '  <-- FAIL'}")
    if not ok:
        failures.append(f"{what}: {detail}")


def solve(f, lo, hi):
    """Where f crosses zero between lo and hi, by bisection."""
    for _ in range(60):
        mid = (lo + hi) / 2
        if (f(lo) < 0) == (f(mid) < 0):
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def check_start(failures):
    s = game.start_state(WORLD)
    x, z, heading = WORLD.start
    check(failures, "start", (s.x >> 16, s.z >> 16) == (x, z) and s.heading >> 8 == heading
          and flight.on_ground(s) and s.speed == 0,
          f"at {(s.x >> 16, s.z >> 16)}, heading {s.heading >> 8}, on the ground, standing still")
    check(failures, "start, idling", s.throttle == 0 and abs(s.rpm - j3.IDLE_RPM) <= 1,
          f"throttle {s.throttle}, {s.rpm} r.p.m. (idle {j3.IDLE_RPM:.0f})")
    check(failures, "start, brakes", flight.parked(s), f"parking brake {'on' if flight.parked(s) else 'off'}")
    run = Run()
    run.hold(0, 250)
    moved = math.hypot(run.state.x - s.x, run.state.z - s.z) / 65536
    check(failures, "five seconds idling", moved == 0, f"moved {moved:.1f} ft")
    run.hold(keys.THROTTLE_UP, 500)
    moved = math.hypot(run.state.x - s.x, run.state.z - s.z) / 65536
    check(failures, "ten seconds at full throttle, parked",
          moved == 0 and run.state.throttle == flight.THROTTLE_FULL,
          f"throttle {run.state.throttle}, {run.state.rpm} r.p.m., moved {moved:.1f} ft")


def check_throttle(failures):
    run = Run()
    run.hold(keys.THROTTLE_UP, 40)
    set_to = run.state.throttle
    run.hold(0, 200)
    check(failures, "throttle", 0 < set_to < flight.THROTTLE_FULL and run.state.throttle == set_to,
          f"opened to {set_to}, and {run.state.throttle} four seconds after letting go")


def tail_up_mph(elevator: float) -> float:
    """Where the tail, tail down at full throttle, starts to lift:
    tail_air(v) (three-point attitude + elevator) = TAIL_LOAD."""
    return solve(lambda v: j3.tail_air(v, j3.full_rpm(v)) * (j3.THREE_POINT + elevator) - j3.TAIL_LOAD, 0, 80)


def full_throttle_roll() -> Run:
    """Full throttle with the brakes on until the engine has wound up, then
    the brakes released."""
    run = Run()
    run.hold(keys.THROTTLE_UP, 150)
    release_brakes(run)
    return run


def check_tail(failures):
    for name, stick, elevator in (("central", 0, 0.0), ("forward", keys.STICK_FORWARD, j3.ELEVATOR)):
        run = full_throttle_roll()
        lifted = run.hold(keys.THROTTLE_UP | stick, 1500, until=flight.tail_up)
        want = tail_up_mph(elevator)
        check(failures, f"tail up, stick {name}", lifted and abs(run.mph - want) <= 1.0,
              f"at {run.mph:.1f} mph; {want:.1f} worked out")
    run = full_throttle_roll()
    run.hold(keys.THROTTLE_UP | keys.STICK_BACK, 1500,
             until=lambda s: flight.tail_up(s) or not flight.on_ground(s))
    check(failures, "tail up, stick back", not flight.tail_up(run.state) and not flight.on_ground(run.state),
          f"the tail stayed down until lift-off, at {run.mph:.1f} mph")


def check_lift_off(failures):
    run = full_throttle_roll()
    start = (run.state.x, run.state.z)
    run.hold(keys.THROTTLE_UP | keys.STICK_BACK, 1500, until=lambda s: not flight.on_ground(s))
    check(failures, "lift-off, tail held down", abs(run.mph - j3.LIFT_OFF_MPH) <= 1.0,
          f"at {run.mph:.1f} mph; the manual's {j3.LIFT_OFF_MPH:.0f}")
    roll = math.hypot(run.state.x - start[0], run.state.z - start[1]) / 65536
    check(failures, "ground roll, tail held down", abs(roll - j3.TAKE_OFF_RUN) <= 0.15 * j3.TAKE_OFF_RUN,
          f"{roll:.0f} ft in {run.steps * STEP:.1f} s; {j3.TAKE_OFF_RUN:.0f} published (a secondary source)")

    run = full_throttle_roll()
    run.hold(keys.THROTTLE_UP, 1500, until=lambda s: flight.mph(s) >= 45)
    tail_was_up = flight.tail_up(run.state)
    pulled = run.steps
    run.hold(keys.THROTTLE_UP | keys.STICK_BACK, 200, until=lambda s: not flight.on_ground(s))
    took = (run.steps - pulled) * STEP
    check(failures, "lift-off, tail up then pulled back at 45 mph",
          tail_was_up and not flight.on_ground(run.state) and took <= 1.0,
          f"airborne {took:.2f} s after the pull, at {run.mph:.1f} mph")
    run.hold(keys.THROTTLE_UP, 250)
    check(failures, "climbing away", not flight.on_ground(run.state) and run.state.y > 0,
          f"{(run.state.y >> 16)} ft up five seconds later, at {run.mph:.1f} mph")


def central_lift_off_mph() -> float:
    """Stick central, full throttle: the tail settles where its lift
    balances its load, the fuselage at TAIL_LOAD / tail_air(v) degrees (no
    lower than level), and the Cub lifts off where the wing at that
    attitude holds the weight."""
    def excess(v):
        attitude = max(0.0, j3.TAIL_LOAD / j3.tail_air(v, j3.full_rpm(v)))
        return j3.q(v) * j3.WING_AREA * j3.lift_coefficient(attitude + j3.INCIDENCE) - j3.WEIGHT
    return solve(excess, 30, 85)


def check_central(failures):
    run = full_throttle_roll()
    run.hold(keys.THROTTLE_UP, 3000, until=lambda s: not flight.on_ground(s))
    want = central_lift_off_mph()
    check(failures, "lift-off, stick central", not flight.on_ground(run.state) and abs(run.mph - want) <= 1.5,
          f"at {run.mph:.1f} mph, the tail flying itself; {want:.1f} worked out")


def taxi(mph: float) -> Run:
    """Rolling straight at about this speed, throttle eased back."""
    run = Run()
    run.hold(keys.THROTTLE_UP, 60)
    release_brakes(run)
    run.hold(keys.THROTTLE_UP, 1000, until=lambda s: flight.mph(s) >= mph)
    run.hold(keys.THROTTLE_DOWN, 300)
    return run


def check_rudder(failures):
    for name, rudder, sign in (("right", keys.RUDDER_RIGHT, 1), ("left", keys.RUDDER_LEFT, -1)):
        run = taxi(12)
        run.hold(rudder, flight.RUDDER_FULL // flight.RUDDER_RATE + 1)       # full rudder
        before, turned = run.state.heading, 0.0
        for _ in range(100):
            v = flight.mph(run.state) * j3.MPH
            run.hold(rudder, 1)
            turned += v * STEP / j3.TURN_RADIUS
        got = ((run.state.heading - before + 32768) % 65536 - 32768) * 2 * math.pi / 65536
        want = sign * turned
        check(failures, f"rudder {name}", abs(got - want) <= 0.03 * abs(want) + 0.01,
              f"turned {math.degrees(got):+.1f} degrees in two seconds; {math.degrees(want):+.1f} at "
              f"{j3.TURN_RADIUS:.0f} ft's radius")


def stopping_distance(mph: float, alpha: float) -> float:
    """ft, braking from mph with the throttle closed, worked out in floating
    point from j3's figures: the friction of brakes and wheels on the load
    the wing leaves them, the drag, less the idle thrust."""
    v, d, dt = mph * j3.MPH, 0.0, 0.0005
    cl = j3.lift_coefficient(alpha)
    while v > 0:
        q = 0.5 * j3.RHO * v * v * j3.WING_AREA
        lift, drag = q * cl, q * (j3.CD0 + j3.INDUCED * cl * cl)
        load = max(0.0, j3.WEIGHT - lift)
        force = (j3.BRAKE_FRICTION + j3.ROLLING_FRICTION) * load + drag - j3.thrust(v / j3.MPH, j3.IDLE_RPM)
        v -= force / (j3.WEIGHT / j3.G) * dt
        d += v * dt
    return d


def check_brakes(failures):
    run = taxi(12)
    if not flight.tail_up(run.state):
        v0 = run.mph
        start = (run.state.x, run.state.z)
        stopped = run.hold(keys.BRAKES | keys.THROTTLE_DOWN, 1000, until=lambda s: s.speed == 0)
        got = math.hypot(run.state.x - start[0], run.state.z - start[1]) / 65536
        want = stopping_distance(v0, j3.THREE_POINT_ALPHA)
        check(failures, "brakes", stopped and abs(got - want) <= 0.05 * want + 1,
              f"from {v0:.1f} mph, stopped in {got:.1f} ft; {want:.1f} worked out")
    else:
        check(failures, "brakes", False, "the tail was up at taxi speed")


def check_frame_rate(failures):
    """Keys change only every 60 steps, so every rate below divides them."""
    script = [(keys.THROTTLE_UP, 60), (keys.BRAKES | keys.THROTTLE_UP, 60),
              (keys.THROTTLE_UP | keys.RUDDER_LEFT, 120), (keys.THROTTLE_UP | keys.STICK_FORWARD, 240),
              (keys.THROTTLE_UP | keys.STICK_BACK, 240), (keys.THROTTLE_DOWN, 120)]
    finals = {}
    for per_frame in (1, 2, 3, 4, 5, 6, 10):
        run = Run()
        for held, steps in script:
            run.hold(held, steps, per_frame)
        finals[per_frame] = replace(run.state, drawing=0).pack()
    same = len(set(finals.values())) == 1
    check(failures, "frame rate", same,
          f"{len(finals)} rates, 1 to 10 steps a frame: {'the same state' if same else 'different states'} after "
          f"{sum(s for _, s in script)} steps")


def main():
    failures = []
    for part in (check_start, check_throttle, check_tail, check_lift_off, check_central, check_rudder,
                 check_brakes, check_frame_rate):
        part(failures)
    print("ground_test:", "ok" if not failures else f"{len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
