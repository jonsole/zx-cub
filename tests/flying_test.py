r"""The Cub in the air, through the frame: scripted flights flown by a pilot
in the test, checked against what j3.py's figures work out to in floating
point -- the stalling speed, the cruise, the top speed and the climb, the
turn a bank makes.

    .venv-win\Scripts\python.exe examples\cub\tests\flying_test.py

1. The stick springs back to the middle when let go, and the attitude stays
   where it was left.
2. Slowing power off and held level, the stall light comes on where the
   wing is STALL_WARNING short of the stall, and the wing stalls at the
   manual's 38 mph. Then the nose drops, the light stays on while the wing
   is stalled, and with the stick let go the Cub recovers as speed builds.
3. Held level, full throttle flies at the top speed, and the throttle that
   turns the engine at the manual's cruise r.p.m. flies at the cruise
   speed the figures work out to, near the manual's.
4. Full throttle at the best climbing speed climbs at the rate the figures
   work out to, near the published one.
5. A banked Cub turns without rudder, at the rate the lift's sideways part
   makes; with its wings level it does not turn. Banked and left alone, it
   sinks, its lift's upward part short of the weight.

The pilot works the stick as a pilot does, leading the change: to hold the
path level it taps the stick back while the path, a second ahead at its
present rate, is below level, and pushes while it is above; to hold a
speed, it pulls while the speed a second ahead is above it and pushes
while below. Its taps, never two frames running, keep the stick near the
middle, so that its corrections do not jolt the wing's angle to the air:
holding the stick back for longer, the stall came anywhere between 38.0
and 39.2 mph, as the corrections happened to fall.
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
FOOT = 65536                                    # a position's unit
LEAD = 50                                       # steps the pilot looks ahead


def degrees(angle: float) -> float:
    """An angle in the state's units, 65,536 to the turn, in degrees."""
    return angle * 360 / 65536


def mph(s) -> float:
    """The state's speed, 2^-16 feet a step, in miles an hour."""
    return s.speed / FOOT / STEP / j3.MPH


def attack(s) -> float:
    """The wing's angle to the air, degrees: the attitude above the flight
    path (gamma is angle units times 256), and the incidence."""
    return degrees(s.pitch - s.gamma / 256) + j3.INCIDENCE


def flying(at_mph: float, throttle: int, height: int = 1000):
    """A Cub in level flight at a speed, its attitude what the figures say
    holds it up there, the throttle set and the engine still to wind up to
    it."""
    cl = j3.WEIGHT / (j3.q(at_mph) * j3.WING_AREA)
    pitch = cl / j3.CL_SLOPE + j3.ALPHA_ZERO_LIFT - j3.INCIDENCE
    return replace(game.start_state(WORLD), y=height * FOOT, speed=round(at_mph * j3.MPH * FOOT * STEP),
                   pitch=round(pitch * 65536 / 360), gamma=0, throttle=throttle, rpm=round(j3.IDLE_RPM), flags=0)


class Pilot:
    """Works the stick, a frame at a time, from what it sees of the state."""

    def __init__(self):
        self.was = None
        self.pulled = False

    def ahead(self, value: int) -> int:
        """The value a second ahead, at the rate it changed over the last frame."""
        was, self.was = (value if self.was is None else self.was), value
        return value + LEAD * (value - was)

    def level(self, s) -> int:
        path = self.ahead(s.gamma)
        if path < 0 and not self.pulled:
            self.pulled = True
            return keys.STICK_BACK
        self.pulled = False
        return keys.STICK_FORWARD if path > 0 and s.stick <= 0 else 0

    def holding(self, speed: int):
        def stick(s) -> int:
            return keys.STICK_BACK if self.ahead(s.speed) > speed else keys.STICK_FORWARD
        return stick


def fly(s, steps: int, keys_for, until=None) -> list:
    """The states after each frame, a step a frame, the keys chosen from the
    state; stopping early once until(state) holds."""
    out = []
    for _ in range(steps):
        s, _ = game.frame(s, WORLD, keys_for(s), 1, draw=False)
        out.append(s)
        if until and until(s):
            break
    return out


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


def excess_thrust(v: float, rpm: float) -> float:
    """lb: the thrust left over from the drag in level flight at v mph."""
    cl = j3.WEIGHT / (j3.q(v) * j3.WING_AREA)
    return j3.thrust(v, rpm) - j3.q(v) * j3.WING_AREA * (j3.CD0 + j3.INDUCED * cl * cl)


def check_stick(failures):
    s = flying(70, 200)
    held = fly(s, 10, lambda s: keys.STICK_RIGHT | keys.STICK_BACK)[-1]
    let_go = fly(held, flight.STICK_FULL // flight.STICK_RATE, lambda s: 0)
    after = let_go[-1]
    check(failures, "the stick springs back", (held.stick, held.stick_roll) != (0, 0)
          and (after.stick, after.stick_roll) == (0, 0),
          f"held back and right, at {held.stick}, {held.stick_roll}; {len(let_go)} steps after letting go, "
          f"{after.stick}, {after.stick_roll}")
    later = fly(after, 100, lambda s: 0)[-1]
    check(failures, "the attitude stays", later.bank == after.bank and later.pitch == after.pitch
          and after.bank > 0,
          f"banked {degrees(after.bank):.1f}, pitched {degrees(after.pitch):.1f} degrees when let go; "
          f"{degrees(later.bank):.1f} and {degrees(later.pitch):.1f} two seconds on")


def check_stall(failures):
    pilot = Pilot()
    states = fly(flying(60, 0), 5000, pilot.level, until=flight.stalled)
    warned = next((s for s in states if flight.stall_warning(s)), None)
    s = states[-1]
    warning_alpha = j3.STALL_ALPHA - j3.STALL_WARNING
    warning_mph = j3.STALL_MPH * math.sqrt(j3.CL_MAX / j3.lift_coefficient(warning_alpha))
    check(failures, "stall light, slowing level", warned is not None and not flight.stalled(warned)
          and abs(mph(warned) - warning_mph) <= 1.5,
          f"on at {mph(warned):.1f} mph, before the stall; {warning_mph:.1f} worked out" if warned
          else "never on")
    check(failures, "stall, slowing level", flight.stalled(s) and abs(mph(s) - j3.STALL_MPH) <= 1.0,
          f"at {mph(s):.1f} mph, {attack(s):.1f} degrees of attack; the manual's {j3.STALL_MPH:.0f}")

    # Holding the stick back: the nose drops all the same, the light on.
    pitch = s.pitch
    after = fly(s, 25, lambda s: keys.STICK_BACK)
    dropped = degrees(pitch - min(a.pitch for a in after))
    lit = all(flight.stall_warning(a) for a in after if flight.stalled(a))
    check(failures, "stall, the nose drops", dropped >= 5 and lit,
          f"{dropped:.1f} degrees in half a second, stick held back, the light on while stalled")

    # Let go: the nose stops dropping once the wing is flying again (the
    # step it is, the path still sinking, adds a little to the attack), and
    # it flies on as the speed builds.
    recovery = fly(after[-1], 500, lambda s: 0)
    flies = next((a for a in after + recovery if not flight.stalled(a)), None)
    check(failures, "stall, the nose stops", flies is not None
          and abs(attack(flies) - j3.RECOVER_ALPHA) <= 1,
          f"the wing flying again at {attack(flies):.1f} degrees of attack; {j3.RECOVER_ALPHA:.0f} assumed"
          if flies else "still stalled")
    out = next((i for i, a in enumerate(recovery) if not flight.stalled(a) and not flight.stall_warning(a)), None)
    end = recovery[-1]
    check(failures, "stall, recovered", out is not None and out * STEP <= 2
          and not any(flight.stalled(a) for a in recovery[out:])
          and mph(end) > mph(recovery[out]) + 5 and mph(end) > j3.STALL_MPH + 5,
          f"the light out {out * STEP:.1f} s after letting go, and {mph(end):.1f} mph ten seconds on, "
          f"{(s.y - end.y) // FOOT} ft lower" if out is not None else "still stalled")


def level_flight(throttle: int, settle: int = 3000, measure: int = 500) -> tuple:
    """(mph, r.p.m., ft a second up) held level at a throttle, averaged once
    settled. The pilot holds the path near level, not on it, so it says
    how near."""
    states = fly(flying(75, throttle), settle + measure, Pilot().level)[-measure:]
    return (sum(mph(s) for s in states) / measure, sum(s.rpm for s in states) / measure,
            (states[-1].y - states[0].y) / FOOT / ((measure - 1) * STEP))


def speed_flying(rising: float, rpm_at) -> float:
    """mph where the thrust left over from the drag is what the weight takes
    along a path rising so many feet a second; rpm_at(v) the engine's."""
    return solve(lambda v: excess_thrust(v, rpm_at(v)) - j3.WEIGHT * rising / (v * j3.MPH), 45, 100)


def check_speeds(failures):
    top, rpm, rising = level_flight(flight.THROTTLE_FULL)
    want = speed_flying(rising, j3.full_rpm)
    check(failures, "top speed", abs(top - want) <= 1.0 and abs(top - j3.TOP_MPH) <= 2,
          f"{top:.1f} mph at full throttle, {rpm:.0f} r.p.m., {rising * 60:+.0f} ft a minute; "
          f"{want:.1f} worked out, {j3.TOP_MPH:.0f} published level")

    # The throttle that turns the engine at the cruise r.p.m. when level.
    lo, hi = 128, flight.THROTTLE_FULL
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if level_flight(mid, 2000, 250)[1] < j3.CRUISE_RPM:
            lo = mid
        else:
            hi = mid
    cruise, rpm, rising = level_flight(hi)
    want = speed_flying(rising, lambda v: rpm)
    check(failures, "cruise", abs(cruise - want) <= 1.0 and abs(cruise - j3.CRUISE_MPH) <= 0.1 * j3.CRUISE_MPH,
          f"{cruise:.1f} mph at throttle {hi}, {rpm:.0f} r.p.m., {rising * 60:+.0f} ft a minute; "
          f"{want:.1f} worked out, the manual's {j3.CRUISE_MPH:.0f} at {j3.CRUISE_RPM:.0f}")


def check_climb(failures):
    climbs = {v: excess_thrust(v, j3.full_rpm(v)) * v * j3.MPH / j3.WEIGHT * 60 for v in range(40, 88)}
    best = max(climbs, key=climbs.get)
    target = round(best * j3.MPH * FOOT * STEP)
    states = fly(flying(best, flight.THROTTLE_FULL), 3000, Pilot().holding(target))
    a, b = states[1000], states[-1]
    fpm = (b.y - a.y) / FOOT / ((len(states) - 1001) * STEP) * 60
    check(failures, "climb", abs(fpm - climbs[best]) <= 0.05 * climbs[best] and abs(fpm - j3.CLIMB_FPM)
          <= 0.1 * j3.CLIMB_FPM,
          f"{fpm:.0f} ft a minute at {mph(b):.1f} mph, full throttle; {climbs[best]:.0f} worked out at {best}, "
          f"{j3.CLIMB_FPM:.0f} published")


def check_turn(failures):
    for name, stick, sign in (("right", keys.STICK_RIGHT, 1), ("left", keys.STICK_LEFT, -1)):
        pilot = Pilot()
        rolled = fly(flying(70, 220), 500, lambda s: pilot.level(s) | stick,
                     until=lambda s: abs(degrees(s.bank)) >= 30)[-1]
        s, turned = rolled, 0.0
        for _ in range(500):
            v = mph(s) * j3.MPH
            lift = j3.q(mph(s)) * j3.WING_AREA * j3.lift_coefficient(attack(s))
            turned += lift * math.sin(math.radians(degrees(s.bank))) / (j3.WEIGHT / j3.G * v) * STEP
            s = fly(s, 1, pilot.level)[-1]
        got = math.radians(degrees((s.heading - rolled.heading + 32768) % 65536 - 32768))
        check(failures, f"banked {name}, no rudder", sign * got > 0 and abs(got - turned) <= 0.03 * abs(turned),
              f"banked {degrees(rolled.bank):+.1f} degrees, turned {math.degrees(got):+.1f} in ten seconds; "
              f"{math.degrees(turned):+.1f} worked out")
    pilot = Pilot()
    level = flying(70, 220)
    s = fly(level, 500, pilot.level)[-1]
    check(failures, "wings level", s.heading == level.heading, f"heading {s.heading >> 8} after ten seconds, "
          f"from {level.heading >> 8}")

    # Left alone, level and banked alike from the same state: the banked
    # Cub's lift holds up only cos(bank) of what it did.
    left_alone = {}
    for name, bank in (("level", 0), ("banked", 30)):
        start = replace(level, bank=round(bank * 65536 / 360))
        left_alone[name] = fly(start, 150, lambda s: 0)[-1]
    sank = (left_alone["level"].y - left_alone["banked"].y) / FOOT
    lift = j3.q(70) * j3.WING_AREA * j3.lift_coefficient(attack(level))
    want = lift * (1 - math.cos(math.radians(30))) / (j3.WEIGHT / j3.G) * 3 ** 2 / 2
    check(failures, "banked, left alone", left_alone["banked"].y < left_alone["level"].y and sank <= want,
          f"{sank:.1f} ft below the level Cub after three seconds; at most {want:.1f} if its path never "
          f"steepened")


def main():
    failures = []
    for part in (check_stick, check_stall, check_speeds, check_climb, check_turn):
        part(failures)
    print("flying_test:", "ok" if not failures else f"{len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
