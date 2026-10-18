"""The panel, below the view, in white on blue: the airspeed, the height and
the heading as numbers, the throttle and the climb as bars, and the stall
light.

  row 19    MPH   FEET   HDG
  row 20     73   1234   045          STALL
  row 22    THR [throttle....]  CLIMB [sink..|..climb]

What the panel shows is worked out from the Cub's state by `values`, as
the Z80 will: integers, products and shifts. The state keeps what
the panel shows (its shown_ fields), so that a frame redraws only what has
changed; and since only the panel's values change, the Z80 can draw them on
both screens at once, keeping the panel the same whichever is shown. The
labels, the bars' marks and the stall light's word never change.
"""
import flight
import font
import j3
from fast3d import model

LABEL_ROW, NUMBER_ROW, BAR_ROW = 19, 20, 22     # character rows of the screen
LABELS = [(2, LABEL_ROW, "MPH"), (7, LABEL_ROW, "FEET"), (13, LABEL_ROW, "HDG"),
          (2, BAR_ROW, "THR"), (16, BAR_ROW, "CLIMB")]
# The numbers: (first column, digits, leading zeros or blanks).
SPEED = (2, 3, False)
HEIGHT = (6, 5, False)
HEADING = (13, 3, True)
STALL_COLUMN, STALL_WORD = 25, "STALL"          # the light, on NUMBER_ROW
LIGHT_OFF = 0x01                    # blue on black: an unlit lamp
LIGHT_ON = 0x57                     # bright white on red

# The bars: four pixel lines of BAR_ROW, under a line along its foot, each
# eight characters wide. Each starts on a character's edge, so that the Z80
# redraws it a byte at a time.
BAR_LINES = range(2, 6)
BAR_FOOT = 7
BAR_WIDTH = 64                      # pixels
THROTTLE_LEFT = 8 * 6               # the bar grows right from column 6,
THROTTLE_SHIFT = 2                  # a pixel each 4 of the throttle's 0..255: the whole bar
CLIMB_CENTRE = 8 * 26               # the climb bar grows right from column 26, the sink bar left,
CLIMB_REACH = BAR_WIDTH // 2        # half the bar either way at most,
FPM_A_PIXEL = 25                    # feet a minute a pixel: 800 either way, past the Cub's
                                    # 450 climbing and its glide's 500 to 600

# Airspeed in miles an hour: (V16 K_MPH) >> 20, V16 = speed >> 4.
K_MPH = round(16 * 2 ** 20 / (j3.MPH * flight.SPEED_PER_FPS))
# The climb bar: a step's rise, 2^-16 feet, (rise K_CLIMB) >> 16 pixels,
# truncated toward zero.
K_CLIMB = round(flight.STEPS_PER_SECOND * 60 / FPM_A_PIXEL)

# What the panel shows at the start of a flight, by the state's fields that
# keep it: what no value can be at the start, so that the first frame draws
# every part. (A height of 65,535 feet could be shown later, but a flight
# starts on the ground.)
NOTHING_SHOWN = {"shown_mph": 0xFF, "shown_feet": 0xFFFF, "shown_heading": 0xFFFF, "shown_throttle": 0xFF,
                 "shown_climb": -128, "shown_stall": 0xFF}


def values(s) -> dict:
    """What the panel shows of the state, by the state's fields that keep it."""
    rise = (s.speed * flight.sin16(s.gamma >> 8)) >> 15
    climb = (abs(rise) * K_CLIMB) >> 16
    return {"shown_mph": ((s.speed >> 4) * K_MPH) >> 20,
            "shown_feet": s.y >> 16,
            "shown_heading": (s.heading * 360) >> 16,
            "shown_throttle": s.throttle >> THROTTLE_SHIFT,
            "shown_climb": min(CLIMB_REACH, climb) * (-1 if rise < 0 else 1),
            "shown_stall": 1 if flight.stall_warning(s) else 0}


def digits(value: int, places: int, zeros: bool) -> str:
    """A number as the panel writes it: right-aligned in so many places,
    led by zeros or by blanks."""
    return str(value).rjust(places, "0" if zeros else " ")


def put(bitmap: bytearray, column: int, row: int, text: str) -> None:
    """Characters from font.py on the screen, from a column of a character row."""
    for i, character in enumerate(text):
        for line, bits in enumerate(font.glyph(character)):
            bitmap[model.screen_address(8 * (column + i), 8 * row + line) - 0x4000] = bits


def span(bitmap: bytearray, left: int, right: int, y: int) -> None:
    """Ink from pixel left to right, inclusive, on line y."""
    for x in range(left, right + 1):
        bitmap[model.screen_address(x, y) - 0x4000] |= 0x80 >> (x & 7)


def draw(bitmap: bytearray, attributes: bytearray, s) -> None:
    """The panel as the state's shown_ fields have it, on the bitmap and the
    attributes of a screen whose panel rows are empty."""
    for column, row, text in LABELS:
        put(bitmap, column, row, text)
    put(bitmap, STALL_COLUMN, NUMBER_ROW, STALL_WORD)
    foot = 8 * BAR_ROW + BAR_FOOT
    span(bitmap, THROTTLE_LEFT, THROTTLE_LEFT + BAR_WIDTH - 1, foot)
    span(bitmap, CLIMB_CENTRE - BAR_WIDTH // 2, CLIMB_CENTRE + BAR_WIDTH // 2 - 1, foot)
    for line in (0, 1, 6):
        span(bitmap, CLIMB_CENTRE, CLIMB_CENTRE, 8 * BAR_ROW + line)

    for value, (column, places, zeros) in ((s.shown_mph, SPEED), (s.shown_feet, HEIGHT),
                                           (s.shown_heading, HEADING)):
        put(bitmap, column, NUMBER_ROW, digits(value, places, zeros))
    for line in BAR_LINES:
        y = 8 * BAR_ROW + line
        if s.shown_throttle:
            span(bitmap, THROTTLE_LEFT, THROTTLE_LEFT + s.shown_throttle - 1, y)
        if s.shown_climb > 0:
            span(bitmap, CLIMB_CENTRE, CLIMB_CENTRE + s.shown_climb - 1, y)
        elif s.shown_climb < 0:
            span(bitmap, CLIMB_CENTRE + s.shown_climb, CLIMB_CENTRE - 1, y)
    light = 32 * NUMBER_ROW + STALL_COLUMN
    lit = LIGHT_ON if s.shown_stall else LIGHT_OFF
    attributes[light:light + len(STALL_WORD)] = bytes([lit] * len(STALL_WORD))
