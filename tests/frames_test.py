r"""The Z80 version against the Python model, frame by frame.

    .venv-win\Scripts\python.exe examples\cub\tests\frames_test.py

Builds Cub (build.py), loads output/cub.z80 into cpp-core's snapshot_probe
through the examples' shared driver (examples/scripts/probe.py), and runs
`setup`, as the Spectrum does at the start, with the test mode on: each
frame takes the keys held and the steps owed from test_keys and
test_steps instead of the keyboard and the interrupt. Then a script of
frames, each a `game_frame` on the Z80 and a `game.frame` in Python; after
every one, the whole game state and the whole screen drawn on must match.
Then frames from varied states, each poked into the Z80's state first.
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

import game  # noqa: E402
import keys  # noqa: E402
import probe  # noqa: E402
from fast3d import model  # noqa: E402

VARIED = 60         # frames from varied states
# (keys held, steps owed) a frame: steps past MAX_STEPS are capped. The Z80
# has no flight model until a later stage (game.py's has), so the keys held
# are only those the flight model does not act on yet -- the stick left and
# right, and bits no key has -- which are kept all the same; with them the
# Cub stands idling on its parking brake, and a step changes nothing but
# the clock.
IDLE_KEYS = keys.STICK_LEFT | keys.STICK_RIGHT | 0xFE00
SCRIPT = [(0, 0), (0, 1), (keys.STICK_LEFT, 2), (keys.STICK_RIGHT, 3), (0x8000, 4), (0, 25), (IDLE_KEYS, 1),
          (0x1200, 10), (0, 11), (0, 5)]


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

        def run(what, keys, steps):
            nonlocal state
            z.poke("test_keys", keys.to_bytes(2, "little"))
            z.poke("test_steps", [steps])
            base = 0xC000 if state.drawing else 0x4000
            times.append(z.call("game_frame").tstates)
            state, want = game.frame(state, world, keys, steps)
            differ = state_differences(state.pack(), z.peek("state", size))
            differ += screen_differences(want, z.peek(base, 6912))
            if differ:
                failures.append(f"{what} (keys {keys:04X}, {steps} steps): "
                                f"{len(differ)} differ: {', '.join(differ[:8])}")

        for number, (keys, steps) in enumerate(SCRIPT):
            run(f"frame {number}", keys, steps)
        # Then frames from states poked into the Z80's: every pitch, heading
        # and bank, round the airfield and above it, so that the horizon is
        # drawn at every slope and the airfield seen, cut and clipped from
        # every side. No steps, so that only the view is compared.
        rng = random.Random(1937)
        x0, z0, _ = world.start
        for number in range(VARIED):
            state = replace(state, x=((x0 + rng.randint(-400, 400)) << 16 | rng.randrange(65536)) & 0xFFFFFFFF,
                            y=rng.choice([0, 0, 20, 300]) << 16 | rng.randrange(65536),
                            z=((z0 + rng.randint(-300, 2300)) << 16 | rng.randrange(65536)) & 0xFFFFFFFF,
                            pitch=rng.randrange(-32768, 32768), heading=rng.randrange(65536),
                            bank=rng.randrange(-32768, 32768))
            z.poke("state", state.pack())
            run(f"varied frame {number}, the eye at {game.eye(state)}, turned {game.camera_angles(state)}", 0, 0)
    for f in failures:
        print("FAIL", f)
    if times:
        print(f"  {len(times)} frames, {statistics.mean(times):,.0f} T-states on average, {max(times):,} at most")
    print("frames_test:", "ok" if not failures else f"{len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
