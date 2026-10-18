"""The Piper J-3 Cub as Cub flies it: the published figures, where they come
from, and the assumptions the flight model needs that no source gives. In
floating point and in the units of the sources -- pounds, feet, seconds,
miles an hour, degrees -- for flight.py to turn into its fixed-point
constants, and for the tests to work their expected values out from.

Sources (docs/j3-figures.md has the detail):

  TCDS   FAA Aircraft Specification A-691, Rev. 32, Model J3C-65.
  MANUAL Piper J3C-65 owner's manual, 1946 (the scan on ManualsLib).
  OTHER  Secondary: performance tables and fact sheets, which disagree.
"""
import math

# --- Published -------------------------------------------------------------

WEIGHT = 1220.0             # lb: maximum weight (TCDS, serials 10339 and up)
WING_AREA = 178.5           # sq ft (MANUAL)
WING_SPAN = 35.2            # ft: 35 ft 2.5 in (OTHER; the MANUAL scan reads 36)
STALL_MPH = 38.0            # power off (MANUAL)
LIFT_OFF_MPH = 39.0         # "will become airborne at approximately 39 M.P.H." loaded (MANUAL)
STATIC_RPM = 2300.0         # full throttle on the ground: "not over 2300" (TCDS; MANUAL's take-off r.p.m.)
MAX_RPM = 2350.0            # 65 hp, for all operations (TCDS)
CRUISE_MPH = 73.0           # at 2150 r.p.m. (MANUAL)
CRUISE_RPM = 2150.0
TOP_MPH = 87.0              # full throttle, level (OTHER; TCDS limits level flight to 90)
CLIMB_FPM = 450.0           # full throttle (OTHER; AOPA gives 540 for the 1946 Special)
TAKE_OFF_RUN = 370.0        # ft, ground roll (OTHER)

# --- The air and gravity ---------------------------------------------------

G = 32.174                  # ft/s^2
RHO = 0.002377              # slug/ft^3: sea level, standard day
MPH = 5280.0 / 3600.0       # ft/s in a mile an hour


def q(mph: float) -> float:
    """Dynamic pressure at a speed, lb/sq ft."""
    v = mph * MPH
    return 0.5 * RHO * v * v


# --- Assumed: what no source gives -----------------------------------------
#
# Each is a guess a J-3's shape makes reasonable, and is named as one.

CL_SLOPE = 0.1              # the wing's lift coefficient a degree of attack
ALPHA_ZERO_LIFT = -2.0      # degrees: the cambered wing lifts at zero attack
INCIDENCE = 2.0             # degrees: the wing's angle to the fuselage's datum
OSWALD = 0.75               # span efficiency, for the induced drag
STATIC_THRUST = 320.0       # lb at STATIC_RPM, standing still
IDLE_RPM = 550.0
RPM_PER_MPH = 0.6           # a fixed-pitch propeller turns faster as speed builds
ROLLING_FRICTION = 0.04     # of the load on the wheels: turf
BRAKE_FRICTION = 0.30       # more, with the brakes on: enough to hold full throttle
TURN_RADIUS = 40.0          # ft: full rudder, rolling, tailwheel and rudder together
VIEW_DOWN = 6.0             # degrees the pilot's line of sight is below the datum
AIR_PITCH_RATE = 15.0       # degrees a second the stick turns the nose, held over
ROLL_RATE = 30.0            # degrees a second the stick rolls the Cub, held over: a Cub rolls slowly
BANK_LIMIT = 60.0           # degrees: the steepest bank the Cub is let roll to
STALL_PITCH_RATE = 30.0     # degrees a second the nose drops, the wing stalled
RECOVER_ALPHA = 6.0         # degrees of attack: below it the wing is flying again
STALL_WARNING = 2.0         # degrees of attack before the stall that the stall light comes on

# The tail. It rests on its wheel until the tailplane's lift overcomes the
# tail's share of the weight. The tailplane's attack is the fuselage's
# attitude above level (it lifts nothing with the fuselage level), and the
# elevator adds ELEVATOR degrees of it at full forward stick (and takes as
# much away at full back). The air over it comes from the airspeed and from
# the propeller: at STATIC_RPM its wash is worth PROPWASH_MPH, more or less
# as the square of the r.p.m. The tail's load is set by one more choice:
# with the stick central and full throttle, the tail comes up at
# TAIL_UP_MPH.
ELEVATOR = 8.0              # degrees: full back holds the tail down past lift-off
PROPWASH_MPH = 20.0
TAIL_UP_MPH = 25.0

# --- Worked out from the above ---------------------------------------------

ASPECT_RATIO = WING_SPAN * WING_SPAN / WING_AREA
CL_MAX = WEIGHT / (q(STALL_MPH) * WING_AREA)                    # 1.85
INDUCED = 1.0 / (math.pi * OSWALD * ASPECT_RATIO)               # CD = CD0 + INDUCED CL^2


def thrust(mph: float, rpm: float) -> float:
    """lb: static thrust falling in a line to what top speed takes, scaled
    for r.p.m. as the square for the static part and in proportion for the
    fall with speed."""
    r = rpm / STATIC_RPM
    return STATIC_THRUST * r * r - THRUST_FALL * mph * r


def full_rpm(mph: float) -> float:
    return STATIC_RPM + RPM_PER_MPH * mph


# At top speed, full throttle balances the drag: so the parasite drag
# follows from TOP_MPH, and the thrust's fall with speed from a propeller's
# efficiency there (0.75 of the engine's 65 hp).
_TOP_THRUST = 65.0 * 550.0 * 0.75 / (TOP_MPH * MPH)
_r_top = full_rpm(TOP_MPH) / STATIC_RPM
THRUST_FALL = (STATIC_THRUST * _r_top * _r_top - _TOP_THRUST) / (TOP_MPH * _r_top)   # lb an mph
_cl_top = WEIGHT / (q(TOP_MPH) * WING_AREA)
CD0 = _TOP_THRUST / (q(TOP_MPH) * WING_AREA) - INDUCED * _cl_top ** 2


def lift_coefficient(alpha: float) -> float:
    """At an angle of attack in degrees, up to the stall: a straight line."""
    return CL_SLOPE * (alpha - ALPHA_ZERO_LIFT)


STALL_ALPHA = ALPHA_ZERO_LIFT + CL_MAX / CL_SLOPE              # 16.5 degrees

# Tail down on three wheels, the wing is at the attack that lifts the Cub's
# weight at LIFT_OFF_MPH: the manual's lift-off, held there by back stick.
THREE_POINT_ALPHA = ALPHA_ZERO_LIFT + CL_MAX * (STALL_MPH / LIFT_OFF_MPH) ** 2 / CL_SLOPE
THREE_POINT = THREE_POINT_ALPHA - INCIDENCE                    # the fuselage's attitude, 13.6 degrees


def tail_air(mph: float, rpm: float) -> float:
    """What lifts the tail, as mph^2: the airspeed's and the propwash's."""
    return mph * mph + PROPWASH_MPH ** 2 * (rpm / STATIC_RPM) ** 2


# The tail's load, in the same units times degrees of the tailplane's attack.
TAIL_LOAD = tail_air(TAIL_UP_MPH, full_rpm(TAIL_UP_MPH)) * THREE_POINT
