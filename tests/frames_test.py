r"""The Z80 version against the Python model, frame by frame.

    .venv-win\Scripts\python.exe examples\cub\tests\frames_test.py

Builds Cub (build.py), loads output/cub.z80 into cpp-core's snapshot_probe
through the examples' shared driver (examples/scripts/probe.py), and runs
`setup`, as the Spectrum does at the start, with the test mode on: each
frame takes the keys held and the steps owed from test_keys and
test_steps instead of the keyboard and the interrupt. Then scripts of
frames, each a `game_frame` on the Z80 and a `game.frame` in Python; after
every one, the whole game state and the whole screen drawn on must match,
and the panel's parts the Z80 says it redrew (panel_redrawn) must be those
whose shown_ fields changed, and no others.

1. Two take-offs from the start of the runway: one held tail down, and
   one tail up, steered with the rudder and pulled off, climbing away into
   a turn. Their frames run from 1 to 12 steps, past the most a frame runs.
2. A flight in the air, from 70 mph and 300 feet: a climb, a cruise, turns
   left and right, and a stall held into with the stick back, then let go;
   the Cub must stall, and recover with the stall light out.
3. Frames from varied flight states poked into the Z80's, on the ground and
   in the air, with varied keys held, a few steps each: the flight model
   from where no script goes.
4. Frames from varied views poked into the Z80's, no steps: every pitch,
   heading and bank, round the airfield and above it, so that the horizon
   is drawn at every slope and the airfield seen, cut and clipped from
   every side.
"""
import random
import statistics
import sys
from dataclasses import replace
from pathlib import Path

CUB = Path(__file__).resolve().parent.parent
OUT = CUB / "output"
sys.path.insert(0, str(CUB))
sys.path.insert(0, str(CUB.parent / "scripts"))

import flight  # noqa: E402
import flying_test  # noqa: E402
import game  # noqa: E402
import keys  # noqa: E402
import panel  # noqa: E402
import probe  # noqa: E402
from fast3d import model  # noqa: E402

STEPS = [1, 3, 5, 7, 10, 12]    # steps owed, frame by frame in turn: 12 runs 10
FLIGHTS = 60                    # frames from varied flight states
VIEWS = 60                      # frames from varied views
FULL = keys.THROTTLE_UP


def frames(phases) -> list:
    """(keys held, steps owed) a frame, from (keys, frames) phases."""
    script = []
    for held, count in phases:
        for _ in range(count):
            script.append((held, STEPS[len(script) % len(STEPS)]))
    return script


# Held tail down: the throttle opened against the brakes, then the stick
# held back until the Cub lifts off at about 39 mph, and on.
TAIL_DOWN = frames([(0, 1), (keys.BRAKES | FULL, 15), (FULL | keys.STICK_BACK, 75)])
# Tail up: the brakes tapped, the stick forward to lift the tail, the
# rudder either way, then pulled off, rolled left into a climbing turn, the
# throttle eased.
TAIL_UP = frames([(keys.BRAKES, 1), (FULL | keys.STICK_FORWARD, 30), (FULL | keys.RUDDER_LEFT, 3),
                  (FULL | keys.RUDDER_RIGHT, 3), (FULL, 8), (FULL | keys.STICK_BACK, 10), (FULL, 20),
                  (FULL | keys.STICK_LEFT, 4), (FULL | keys.STICK_BACK, 5), (keys.THROTTLE_DOWN, 4),
                  (keys.STICK_RIGHT | keys.VIEW | keys.NEW_FLIGHT, 3), (0, 5)])
# In the air, from 70 mph and 300 feet: a climb at full throttle, a cruise,
# turns left and right, then the throttle closed and the stick held back
# into a stall, and let go to recover.
IN_THE_AIR = frames([(FULL | keys.STICK_BACK, 3), (FULL, 20), (keys.THROTTLE_DOWN, 2), (0, 15),
                     (keys.STICK_LEFT, 4), (keys.STICK_BACK, 2), (0, 15), (keys.STICK_RIGHT, 8), (0, 10),
                     (keys.STICK_LEFT, 4), (keys.THROTTLE_DOWN, 12), (keys.STICK_BACK, 30), (0, 30)])


def state_differences(want: bytes, got: bytes) -> list:
    out, at = [], 0
    for name, size in game.STATE_LAYOUT:
        w, g = (int.from_bytes(b[at:at + size], "little") for b in (want, got))
        if w != g:
            out.append(f"{name} {g} (the model's {w})")
        at += size
    return out


def screen_differences(want: bytes, got: bytes) -> list:
    """The pixels that differ, as (x, y), and the attributes."""
    out = []
    for y in range(192):
        for x in range(0, 256, 8):
            a = model.screen_address(x, y) - 0x4000
            if want[a] != got[a]:
                out.append(f"({x + 7 - (want[a] ^ got[a]).bit_length() + 1}, {y})")
    out += [f"attribute {i}" for i in range(768) if want[6144 + i] != got[6144 + i]]
    return out


def changed(before, after) -> int:
    """The panel's parts whose shown_ fields a frame changed, as panel.REDRAWN's bits."""
    return sum(bit for name, bit in panel.REDRAWN.items() if getattr(before, name) != getattr(after, name))


def flight_state(rng, state, world):
    """A state the flight model could be in, round the airfield: on the
    ground, or in the air at any attitude it lets the Cub reach."""
    x0, z0, _ = world.start
    ground = rng.random() < 0.4
    return replace(state, x=((x0 + rng.randint(-400, 400)) << 16 | rng.randrange(65536)) & 0xFFFFFFFF,
                   y=0 if ground else (rng.choice([1, 20, 300]) << 16 | rng.randrange(65536)),
                   z=((z0 + rng.randint(-300, 2300)) << 16 | rng.randrange(65536)) & 0xFFFFFFFF,
                   heading=rng.randrange(65536),
                   pitch=rng.randint(0, flight.THREE_POINT) if ground else rng.randrange(-32768, 32768),
                   bank=0 if ground else rng.randint(-flight.BANK_LIMIT, flight.BANK_LIMIT),
                   speed=rng.randint(0, flight.speed_of(rng.choice([20, 60, 120, 200]))),
                   gamma=0 if ground else rng.randint(-flight.GAMMA_LIMIT, flight.GAMMA_LIMIT),
                   rpm=rng.randint(flight.IDLE_RPM, 2400), throttle=rng.randrange(256),
                   stick=rng.randint(-64, 64), stick_roll=rng.randint(-64, 64), rudder=rng.randint(-64, 64),
                   flags=(flight.GROUND if ground else rng.choice([0, flight.STALLED]))
                   | rng.choice([0, flight.PARKED]))


def main():
    failures = []
    world = game.load_world()
    with probe.Probe(OUT / "cub.z80", OUT / "cub.sld", build=[sys.executable, str(CUB / "build.py")]) as z:
        z.call("setup")
        z.poke("test_mode", [1])
        state = game.start_state(world)
        size = len(state.pack())
        failures += [f"setup: {d}" for d in state_differences(state.pack(), z.peek("state", size))]
        times = []

        def run(what, held, steps):
            nonlocal state
            z.poke("test_keys", held.to_bytes(2, "little"))
            z.poke("test_steps", [steps])
            base = 0xC000 if state.drawing else 0x4000
            times.append(z.call("game_frame").tstates)
            before = state
            state, want = game.frame(state, world, held, steps)
            differ = state_differences(state.pack(), z.peek("state", size))
            differ += screen_differences(want, z.peek(base, 6912))
            redrawn = z.peek("panel_redrawn", 1)[0]
            if redrawn != changed(before, state):
                differ.append(f"panel redrawn {redrawn:06b} (changed {changed(before, state):06b})")
            if differ:
                failures.append(f"{what} (keys {held:04X}, {steps} steps): "
                                f"{len(differ)} differ: {', '.join(differ[:8])}")

        for name, script in (("held tail down", TAIL_DOWN), ("tail up", TAIL_UP)):
            state = game.start_state(world)
            z.poke("state", state.pack())
            for number, (held, steps) in enumerate(script):
                run(f"{name}, frame {number}", held, steps)
            print(f"  take-off, {name}: {len(script)} frames, {state.clock} steps; "
                  f"{'airborne' if not flight.on_ground(state) else 'on the ground'}, {state.y >> 16} ft up, "
                  f"{flight.mph(state):.0f} mph")
            if flight.on_ground(state):
                failures.append(f"take-off, {name}: never left the ground")
        state = replace(flying_test.flying(70, 200), x=32768 << 16, z=29000 << 16, y=300 << 16)
        z.poke("state", state.pack())
        stalled = recovered = False
        start_y, highest = state.y, state.y
        turned, left, right = 0, 0, 0               # the heading's change, its least and most
        for number, (held, steps) in enumerate(IN_THE_AIR):
            heading = state.heading
            run(f"in the air, frame {number}", held, steps)
            turned += (state.heading - heading + 32768) % 65536 - 32768
            left, right = min(left, turned), max(right, turned)
            highest = max(highest, state.y)
            if flight.stalled(state):
                stalled = True
            elif stalled and not flight.stall_warning(state):
                recovered = True
        climbed = (highest - start_y) >> 16
        left, right = (round(a * 360 / 65536) for a in (left, right - left))
        print(f"  in the air: {len(IN_THE_AIR)} frames; climbed {climbed} ft, turned {-left} degrees left and "
              f"{right} back right, {'stalled' if stalled else 'never stalled'}, "
              f"{'recovered' if recovered else 'never recovered'}; {state.y >> 16} ft up, {flight.mph(state):.0f} mph")
        if not (climbed >= 30 and left <= -10 and right >= 10 and stalled and recovered):
            failures.append("in the air: the flight did not climb, turn both ways, stall and recover")
        rng = random.Random(1937)
        for number in range(FLIGHTS):
            state = flight_state(rng, state, world)
            z.poke("state", state.pack())
            run(f"varied flight {number}", rng.randrange(0x800), rng.randint(1, 3))
        for number in range(VIEWS):
            x0, z0, _ = world.start
            state = replace(state, x=((x0 + rng.randint(-400, 400)) << 16 | rng.randrange(65536)) & 0xFFFFFFFF,
                            y=rng.choice([0, 0, 20, 300]) << 16 | rng.randrange(65536),
                            z=((z0 + rng.randint(-300, 2300)) << 16 | rng.randrange(65536)) & 0xFFFFFFFF,
                            pitch=rng.randrange(-32768, 32768), heading=rng.randrange(65536),
                            bank=rng.randrange(-32768, 32768))
            z.poke("state", state.pack())
            run(f"varied view {number}, the eye at {game.eye(state)}, turned {game.camera_angles(state)}", 0, 0)
    for f in failures[:20]:
        print("FAIL", f)
    if times:
        print(f"  {len(times)} frames, {statistics.mean(times):,.0f} T-states on average, {max(times):,} at most")
    print("frames_test:", "ok" if not failures else f"{len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
