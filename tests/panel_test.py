r"""The panel against the Cub's state, every frame of a scripted flight: the
numbers read back off the screen by their characters, the bars by their
pixels and the stall light by its colour, each checked against what the
state works out to in floating point.

    .venv-win\Scripts\python.exe examples\cub\tests\panel_test.py

The flight takes off at full throttle, climbs at 57 mph, rolls into a turn
to the left and out again, then closes the throttle and slows until the
wing stalls, lets the nose drop, and dives away. Every frame runs three
steps, so the panel is read about 17 times a second of flight.
"""
import math
import sys
from pathlib import Path

CUB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CUB))

import flight  # noqa: E402
import font  # noqa: E402
import game  # noqa: E402
import j3  # noqa: E402
import keys  # noqa: E402
import panel  # noqa: E402
from fast3d import model  # noqa: E402

WORLD = game.load_world()
STEP = 1 / 50                                   # seconds
FOOT = 65536                                    # a position's unit
STEPS = 3                                       # a frame
EDGE = 0.02                                     # how near a boundary rounding may fall either side
CHARACTERS = {font.glyph(c): c for c in font.GLYPHS}


# --- What the state works out to ---------------------------------------------

def degrees(angle: float) -> float:
    return angle * 360 / 65536


def mph(s) -> float:
    return s.speed / FOOT / STEP / j3.MPH


def climb_fpm(s) -> float:
    """Feet a minute up the flight path's climb; gamma is angle units times 256."""
    return mph(s) * j3.MPH * 60 * math.sin(math.radians(degrees(s.gamma / 256)))


def stall_warning(s):
    """Lit, unlit, or None when the wing is too near the warning to say."""
    if flight.on_ground(s):
        return False
    if flight.stalled(s):
        return True
    margin = degrees(s.pitch - s.gamma / 256) + j3.INCIDENCE - (j3.STALL_ALPHA - j3.STALL_WARNING)
    return None if abs(margin) < 0.05 else margin > 0


def floors(value: float, scale: float = 1.0) -> set:
    """The whole numbers a truncated value may show, near a boundary either."""
    return {math.floor(value - EDGE * scale), math.floor(value + EDGE * scale)}


def truncations(value: float) -> set:
    """The same, truncated toward zero."""
    return {math.trunc(value - EDGE), math.trunc(value + EDGE)}


# --- What the screen shows -------------------------------------------------

def cell(screen: bytes, column: int, row: int) -> str:
    glyph = bytes(screen[model.screen_address(8 * column, 8 * row + line) - 0x4000] for line in range(8))
    return CHARACTERS.get(glyph, "?")


def number(screen: bytes, where) -> int | None:
    column, places, _ = where
    text = "".join(cell(screen, column + i, panel.NUMBER_ROW) for i in range(places)).strip()
    return int(text) if text.isdigit() else None


def inked(screen: bytes, x: int, y: int) -> bool:
    return bool(screen[model.screen_address(x, y) - 0x4000] & (0x80 >> (x & 7)))


def bar(screen: bytes, left: int, right: int) -> list:
    """Which pixels of a bar are inked, on each of its lines."""
    return [[inked(screen, x, 8 * panel.BAR_ROW + line) for x in range(left, right)] for line in panel.BAR_LINES]


def throttle_bar(screen: bytes) -> int | None:
    rows = bar(screen, panel.THROTTLE_LEFT, panel.THROTTLE_LEFT + panel.BAR_WIDTH)
    n = rows[0].count(True)
    return n if all(row == [True] * n + [False] * (panel.BAR_WIDTH - n) for row in rows) else None


def climb_bar(screen: bytes) -> int | None:
    half = panel.BAR_WIDTH // 2
    rows = bar(screen, panel.CLIMB_CENTRE - half, panel.CLIMB_CENTRE + half)
    left, right = rows[0][:half].count(True), rows[0][half:].count(True)
    shape = [False] * (half - left) + [True] * (left + right) + [False] * (half - right)
    if any(row != shape for row in rows) or (left and right):
        return None
    return right - left


def light(screen: bytes):
    at = 6144 + 32 * panel.NUMBER_ROW + panel.STALL_COLUMN
    colours = set(screen[at:at + len(panel.STALL_WORD)])
    if colours == {panel.LIGHT_ON}:
        return True
    return False if colours == {panel.LIGHT_OFF} else None


# --- The flight -------------------------------------------------------------

def climbing(s) -> int:
    """Full throttle, holding 57 mph: back while faster, forward while slower."""
    return keys.THROTTLE_UP | (keys.STICK_BACK if mph(s) > 57 else keys.STICK_FORWARD)


def level(s) -> int:
    return keys.STICK_BACK if s.gamma < 0 else 0


SCRIPT = [
    (lambda s: keys.BRAKES, lambda s: True),
    (lambda s: keys.THROTTLE_UP | keys.STICK_BACK, lambda s: not flight.on_ground(s)),
    (climbing, lambda s: s.y >> 16 >= 120),
    (lambda s: climbing(s) | keys.STICK_LEFT, lambda s: degrees(s.bank) <= -30),
    (climbing, lambda s: degrees((s.heading + 32768) % 65536 - 32768) <= -90),
    (lambda s: climbing(s) | keys.STICK_RIGHT, lambda s: s.bank >= 0),
    (lambda s: keys.THROTTLE_DOWN | level(s), flight.stalled),
    (lambda s: keys.STICK_BACK, lambda s: not flight.stalled(s)),
    (lambda s: 0, lambda s: mph(s) >= 60),
]


def check(failures, what, ok, detail):
    print(f"  {what}: {detail}{'' if ok else '  <-- FAIL'}")
    if not ok:
        failures.append(f"{what}: {detail}")


def main():
    failures, wrong = [], []
    seen = {"lit": 0, "climbing": 0, "sinking": 0, "frames": 0}
    s = game.start_state(WORLD)
    for phase, (keys_for, until) in enumerate(SCRIPT):
        for _ in range(3000):
            s, screen = game.frame(s, WORLD, keys_for(s), STEPS)
            seen["frames"] += 1
            shown = {"airspeed": number(screen, panel.SPEED), "height": number(screen, panel.HEIGHT),
                     "heading": number(screen, panel.HEADING), "throttle": throttle_bar(screen),
                     "climb": climb_bar(screen), "stall light": light(screen)}
            climb = max(-panel.CLIMB_REACH, min(panel.CLIMB_REACH, climb_fpm(s) / panel.FPM_A_PIXEL))
            want = {"airspeed": floors(mph(s)), "height": {s.y // FOOT},
                    "heading": {math.floor(degrees(s.heading))},
                    "throttle": {math.floor(s.throttle / 256 * panel.BAR_WIDTH)},
                    "climb": truncations(climb), "stall light": {stall_warning(s)}}
            for name, value in shown.items():
                if value not in want[name] and None not in want[name]:
                    wrong.append(f"phase {phase}, frame {seen['frames']}: {name} {value}, "
                                 f"the state's {sorted(want[name], key=str)}")
            seen["lit"] += shown["stall light"] is True
            seen["climbing"] += (shown["climb"] or 0) > 0
            seen["sinking"] += (shown["climb"] or 0) < 0
            if until(s):
                break
        else:
            failures.append(f"phase {phase} never ended")
    check(failures, "the panel, every frame", not wrong,
          f"{seen['frames']} frames; {len(wrong)} wrong" + (f": {'; '.join(wrong[:5])}" if wrong else ""))
    check(failures, "what the flight showed", seen["lit"] and seen["climbing"] and seen["sinking"],
          f"the stall light lit in {seen['lit']} frames, the climb bar up in {seen['climbing']}, "
          f"down in {seen['sinking']}")
    print("panel_test:", "ok" if not failures else f"{len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
