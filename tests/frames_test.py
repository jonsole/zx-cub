r"""The Z80 version against the Python model, frame by frame.

    .venv-win\Scripts\python.exe examples\cub\tests\frames_test.py

Builds Cub (build.py), loads output/cub.z80 into cpp-core's snapshot_probe
through the examples' shared driver (examples/scripts/probe.py), and runs
`setup`, as the Spectrum does at the start, with the test mode on: each
frame takes the keys held and the steps owed from test_keys and
test_steps instead of the keyboard and the interrupt. Then scripts of
frames, each a `game_frame` on the Z80 and a `game.frame` in Python; after
every one, the game state and the screen drawn on must match: all of
them but the panel, which the Z80 does not draw yet (the panel's shown_
fields of the state, and the screen's rows below the view).

1. Two take-offs from the start of the runway: one held tail down, and
   one tail up, steered with the rudder and pulled off, climbing away into
   a turn. Their frames run from 1 to 12 steps, past the most a frame runs.
2. Frames from varied flight states poked into the Z80's, on the ground and
   in the air, with varied keys held, a few steps each: the flight model
   from where no script goes.
3. Frames from varied views poked into the Z80's, no steps: every pitch,
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
import game  # noqa: E402
import keys  # noqa: E402
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
# The state up to the panel's fields, and the screen's view: what the Z80
# has so far.
NAMES = [name for name, _ in game.STATE_LAYOUT]
COMPARED = NAMES[:NAMES.index("shown_mph")]


def state_differences(want: bytes, got: bytes) -> list:
    out, at = [], 0
    for name, size in game.STATE_LAYOUT:
        w, g = (int.from_bytes(b[at:at + size], "little") for b in (want, got))
        if w != g and name in COMPARED:
            out.append(f"{name} {g} (the model's {w})")
        at += size
    return out


def screen_differences(want: bytes, got: bytes) -> list:
    """The pixels of the view that differ, as (x, y), and its attributes."""
    out = []
    for y in range(8 * game.VIEW_ROWS):
        for x in range(0, 256, 8):
            a = model.screen_address(x, y) - 0x4000
            if want[a] != got[a]:
                out.append(f"({x + 7 - (want[a] ^ got[a]).bit_length() + 1}, {y})")
    out += [f"attribute {i}" for i in range(32 * game.VIEW_ROWS) if want[6144 + i] != got[6144 + i]]
    return out


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
            state, want = game.frame(state, world, held, steps)
            differ = state_differences(state.pack(), z.peek("state", size))
            differ += screen_differences(want, z.peek(base, 6912))
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
