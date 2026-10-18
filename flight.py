"""Cub's flight model: a step, a fiftieth of a second, of the Cub on the
ground or in the air, in fixed point, as the Z80 will do it (docs/adr/0002).

Every number is an integer, and every operation one the Z80 does as cheaply:
products, shifts right (floor, as SRA does), one division of a step, and a
sine looked up and interpolated. The constants come from j3.py's figures,
worked out once here and rounded; the tests work out what they should
come to in floating point from the same figures.

Units, and the widths the Z80 keeps them in:
  angle     65,536 to the turn (TURN), 16 bits; heading wraps, right
            positive; pitch and bank are signed, nose up and right wing
            down positive; fast3d's angles are the high byte
  position  feet as 16.16, 32 bits: x, y (up, the main wheels' height) and
            z; x and z wrap with the world
  speed     2^-16 feet a step along the flight path (on the ground, along
            the heading), 24 bits, held to SPEED_LIMIT; V16 = speed >> 4,
            15 bits, for the products
  gamma     the flight path's climb, angle units times 256, 24 bits signed,
            held to +-90 degrees
  Q         V16^2 >> 12, as the dynamic pressure: 18 bits
  PER_SPEED the speed's reciprocal, the step's one division: 16 bits
  dV        a step's change of speed, in speed units: G_STEP is gravity's
The products along the way are wider: the thrust's r^2 K_THRUST and the
tail's moment 32 bits, a position's speed times a sine 40; the lift's
sideways part times PER_SPEED 30 bits at 200 mph and the wing's most lift,
and its part across the path 27, held to ACROSS_LIMIT.

On the ground: the throttle and the engine, the brakes, steering with the
rudder, the tail lifting as the air over it builds, and lift-off. In the
air: the stick pitches and rolls the Cub, the attitude holding where it is
left; the lift, tilted with the bank, curves the flight path up or down
and turns it, so that a banked Cub turns without rudder; past the stall
the nose drops until the wing flies again. Touchdowns are not judged yet:
back on the ground, the Cub is simply put down.
"""
import math
from dataclasses import replace

import j3
import keys

TURN = 65536
STEPS_PER_SECOND = 50
FOOT = 65536                        # a position's unit: 16.16
SPEED_PER_FPS = FOOT / STEPS_PER_SECOND     # speed units in a foot a second


def angle(degrees: float) -> int:
    return round(degrees * TURN / 360)


def speed_of(mph: float) -> int:
    return round(mph * j3.MPH * SPEED_PER_FPS)


def signed16(value: int) -> int:
    """As a 16-bit register holds it: wrapped to -32,768..32,767."""
    return ((value + 32768) & 0xFFFF) - 32768


SPEED_LIMIT = speed_of(200)         # past any dive the Cub can make, so V16 fits 15 bits


# The controls. The throttle stays where it is set; the stick and the
# rudder move towards where the keys push them and spring back to the
# middle when let go.
THROTTLE_FULL = 255
THROTTLE_RATE = 4                   # a step: full in 1.3 seconds
STICK_FULL = 64                     # the stick, back positive, and right positive
STICK_RATE = 8
RUDDER_FULL = 64                    # the rudder, right positive
RUDDER_RATE = 8

# flags
PARKED = 1                          # the parking brake: on until the brakes are first pressed
GROUND = 2                          # on the ground
STALLED = 4                         # the wing stalled, from past ALPHA_STALL until under ALPHA_RECOVER


# --- Sines -----------------------------------------------------------------

# 32,767 sin, a 256th of a turn apart, one over: interpolated between.
SINE = [round(32767 * math.sin(2 * math.pi * i / 256)) for i in range(257)]


def sin16(a: int) -> int:
    a &= 0xFFFF
    s0, s1 = SINE[a >> 8], SINE[(a >> 8) + 1]
    return s0 + (((s1 - s0) * (a & 0xFF)) >> 8)


def cos16(a: int) -> int:
    return sin16(a + TURN // 4)


# --- Constants from the figures --------------------------------------------

V16_PER_FPS = SPEED_PER_FPS / 16
Q_PER_FPS2 = V16_PER_FPS ** 2 / 4096                # Q a (ft/s)^2
G_STEP = round(j3.G / STEPS_PER_SECOND * SPEED_PER_FPS)    # dV of 1 g, 843

# Lift and drag: dV = ((Q CL1024) >> 8) K_AERO >> 16, CL1024 the coefficient
# times 1,024: q S CL / m a step.
K_AERO = round(0.5 * j3.RHO * j3.WING_AREA * j3.G / j3.WEIGHT / Q_PER_FPS2
               / STEPS_PER_SECOND * SPEED_PER_FPS / 1024 * 2 ** 24)
ALPHA_ZERO = angle(j3.ALPHA_ZERO_LIFT)
# The lift slope in 1,024ths an angle unit, as a multiply and a shift:
# 0.1 a degree is 0.5625, which is 9/16 within 0.003%.
CL_SLOPE, CL_SLOPE_SHIFT = 9, 4
assert abs(CL_SLOPE / 2 ** CL_SLOPE_SHIFT - j3.CL_SLOPE * 1024 * 360 / TURN) < 1e-3
CL_MAX = round(j3.CL_MAX * 1024)
ALPHA_STALL = ALPHA_ZERO + (CL_MAX << CL_SLOPE_SHIFT) // CL_SLOPE
CD0 = round(j3.CD0 * 1024)
INDUCED = round(j3.INDUCED * 4096)  # CD += (CL1024^2 INDUCED) >> 22
INCIDENCE = angle(j3.INCIDENCE)

# Thrust: dV = (r^2 K_THRUST >> 24) - (V16 r K_FALL >> 24), r the r.p.m.
# over STATIC_RPM in 256ths.
R_SCALE = round(256 * 65536 / j3.STATIC_RPM)        # r = (rpm R_SCALE) >> 16
K_THRUST = round(j3.STATIC_THRUST * j3.G / j3.WEIGHT / STEPS_PER_SECOND * SPEED_PER_FPS * 256)
K_FALL = round(j3.THRUST_FALL / j3.MPH / V16_PER_FPS * j3.G / j3.WEIGHT
               / STEPS_PER_SECOND * SPEED_PER_FPS / 256 * 2 ** 24)

# The engine: r.p.m. towards IDLE + (STATIC - IDLE + a little with speed)
# times the throttle, an eighth of the way a step.
IDLE_RPM = round(j3.IDLE_RPM)
STATIC_RPM = round(j3.STATIC_RPM)
K_RPM_SPEED = round(j3.RPM_PER_MPH / j3.MPH / V16_PER_FPS * 65536)     # (V16 K) >> 16

# Friction, of the load on the wheels, in 256ths.
ROLLING = round(j3.ROLLING_FRICTION * 256)
BRAKING = round(j3.BRAKE_FRICTION * 256)

# Steering on the ground: full rudder turns at TURN_RADIUS.
K_STEER = round(TURN / (2 * math.pi) / j3.TURN_RADIUS / V16_PER_FPS / STEPS_PER_SECOND
                / RUDDER_FULL * 2 ** 20)            # heading += (rudder V16 K_STEER) >> 20

# The tail (j3.py says how it is modelled).
THREE_POINT = angle(j3.THREE_POINT)
TAIL_UP_LIMIT = angle(0.0)          # tail up, the fuselage no lower than level
ELEVATOR = angle(j3.ELEVATOR)
Q_WASH = round(j3.PROPWASH_MPH ** 2 * j3.MPH ** 2 * Q_PER_FPS2)
TAIL_LOAD = round(j3.TAIL_LOAD * j3.MPH ** 2 * Q_PER_FPS2 * TURN / 360)
TAIL_SHIFT = 15                     # how fast the tail answers its moment
PITCH_RATE = angle(10.0 / STEPS_PER_SECOND)     # at most 10 degrees a second

# In the air, the stick turns the nose while it is held over, and the
# attitude stays where it is left when it springs back: a Cub trimmed as
# it is flying.
AIR_PITCH_RATE = angle(j3.AIR_PITCH_RATE / STEPS_PER_SECOND)   # a step, at full stick
ROLL_RATE = angle(j3.ROLL_RATE / STEPS_PER_SECOND)
BANK_LIMIT = angle(j3.BANK_LIMIT)

# Past ALPHA_STALL the wing stalls, and the nose drops STALL_PITCH_RATE a
# step, until the wing is under ALPHA_RECOVER and flying again: full back
# stick, which raises it AIR_PITCH_RATE, only slows the drop by half. The
# stall light comes on STALL_WARNING before the stall.
STALL_PITCH_RATE = angle(j3.STALL_PITCH_RATE / STEPS_PER_SECOND)
ALPHA_RECOVER = angle(j3.RECOVER_ALPHA)
ALPHA_WARNING = ALPHA_STALL - angle(j3.STALL_WARNING)

# The lift, tilted with the bank, turns the flight path: its upward part,
# less the weight's share across the path, curves it up or down, and its
# sideways part turns it. Each turns it by a force over the speed, so the
# step's one division is the speed's reciprocal, PER_SPEED = K_PER_SPEED /
# V16, V16 held to at least V16_FLOOR (10 mph) so that a Cub falling slowly
# does not turn its path in one step. Then gamma += (across PER_SPEED) >> 8,
# across held to ACROSS_LIMIT, and
# heading += (sideways PER_SPEED) >> 16, rounded. ACROSS_LIMIT keeps the
# flight path from curving faster than 4 g would. (The turn's rate is the
# sideways force over the speed along the path, not over its level part:
# a little slow climbing or diving, and no gimbal at 90 degrees.)
K_PER_SPEED = round(TURN / (2 * math.pi) * 256 / 16 * 256)
ACROSS_LIMIT = 4 * G_STEP
V16_FLOOR = speed_of(10) >> 4
GAMMA_LIMIT = (TURN // 4) << 8


# --- The step --------------------------------------------------------------

def toward(value: int, target: int, rate: int) -> int:
    if value < target:
        return min(value + rate, target)
    return max(value - rate, target)


def lift_coefficient(alpha: int) -> int:
    """CL times 1,024 at an angle of attack: a straight line to the stall,
    and falling away past it."""
    if alpha <= ALPHA_STALL:
        return ((alpha - ALPHA_ZERO) * CL_SLOPE) >> CL_SLOPE_SHIFT
    return CL_MAX - (((alpha - ALPHA_STALL) * CL_SLOPE) >> (CL_SLOPE_SHIFT + 1))


def attack(pitch: int, gamma: int) -> int:
    """The wing's angle to the air: the attitude above the flight path, and
    the wing's incidence."""
    return signed16(pitch - (gamma >> 8) + INCIDENCE)


def step(s, held: int):
    """The state a step on, with these keys held (keys.py's bits)."""
    # The controls.
    throttle = s.throttle
    if held & keys.THROTTLE_UP:
        throttle = min(THROTTLE_FULL, throttle + THROTTLE_RATE)
    if held & keys.THROTTLE_DOWN:
        throttle = max(0, throttle - THROTTLE_RATE)
    pull = (STICK_FULL if held & keys.STICK_BACK else 0) - (STICK_FULL if held & keys.STICK_FORWARD else 0)
    stick = toward(s.stick, pull, STICK_RATE)
    lean = (STICK_FULL if held & keys.STICK_RIGHT else 0) - (STICK_FULL if held & keys.STICK_LEFT else 0)
    stick_roll = toward(s.stick_roll, lean, STICK_RATE)
    push = (RUDDER_FULL if held & keys.RUDDER_RIGHT else 0) - (RUDDER_FULL if held & keys.RUDDER_LEFT else 0)
    rudder = toward(s.rudder, push, RUDDER_RATE)
    flags = s.flags
    if held & keys.BRAKES:
        flags &= ~PARKED
    braking = flags & PARKED or held & keys.BRAKES

    # The engine.
    v16 = s.speed >> 4
    full = STATIC_RPM - IDLE_RPM + ((v16 * K_RPM_SPEED) >> 16)
    target = IDLE_RPM + ((full * (throttle + (throttle >> 7))) >> 8)
    rpm = s.rpm + ((target - s.rpm) >> 3)
    r = (rpm * R_SCALE) >> 16

    # The air.
    q = (v16 * v16) >> 12
    on_ground = flags & GROUND
    gamma = 0 if on_ground else s.gamma
    alpha = attack(s.pitch, gamma)
    cl = lift_coefficient(alpha)
    cd = CD0 + ((cl * cl * INDUCED) >> 22)
    lift = (((q * cl) >> 8) * K_AERO) >> 16
    drag = (((q * cd) >> 8) * K_AERO) >> 16
    thrust = ((r * r * K_THRUST) >> 24) - ((v16 * r * K_FALL) >> 24)

    speed, pitch, heading, bank = s.speed, s.pitch, s.heading, s.bank
    if on_ground:
        load = max(0, G_STEP - lift)
        friction = (load * (ROLLING + (BRAKING if braking else 0))) >> 8
        speed = min(SPEED_LIMIT, max(0, speed + thrust - drag - friction))
        heading = (heading + ((rudder * v16 * K_STEER) >> 20)) & 0xFFFF
        pitch = tail(pitch, stick, q, r)
        if lift > G_STEP:
            flags &= ~GROUND                    # lift-off
    else:
        if alpha > ALPHA_STALL:
            flags |= STALLED
        elif alpha < ALPHA_RECOVER:
            flags &= ~STALLED
        speed = min(SPEED_LIMIT, max(0, speed + thrust - drag - ((G_STEP * sin16(gamma >> 8)) >> 15)))
        per_speed = K_PER_SPEED // max(v16, V16_FLOOR)
        across = ((lift * cos16(bank)) >> 15) - ((G_STEP * cos16(gamma >> 8)) >> 15)
        across = max(-ACROSS_LIMIT, min(ACROSS_LIMIT, across))
        gamma = max(-GAMMA_LIMIT, min(GAMMA_LIMIT, gamma + ((across * per_speed) >> 8)))
        sideways = (lift * sin16(bank)) >> 15
        heading = (heading + ((sideways * per_speed + 0x8000) >> 16)) & 0xFFFF
        pitch = signed16(pitch + ((stick * AIR_PITCH_RATE) >> 6) - (STALL_PITCH_RATE if flags & STALLED else 0))
        bank = max(-BANK_LIMIT, min(BANK_LIMIT, bank + ((stick_roll * ROLL_RATE) >> 6)))

    # Where it goes.
    along = (speed * cos16(gamma >> 8)) >> 15
    x = (s.x + ((along * sin16(heading)) >> 15)) & 0xFFFFFFFF
    z = (s.z + ((along * cos16(heading)) >> 15)) & 0xFFFFFFFF
    y = s.y + ((speed * sin16(gamma >> 8)) >> 15)
    if y <= 0 and not flags & GROUND:
        if gamma < 0 or y < 0:                  # back on the ground
            y, gamma, bank, flags = 0, 0, 0, (flags | GROUND) & ~STALLED
            pitch = min(pitch, THREE_POINT)
    y = max(0, y) & 0xFFFFFFFF

    return replace(s, x=x, y=y, z=z, heading=heading, pitch=pitch, bank=bank, speed=speed, gamma=gamma,
                   rpm=rpm, throttle=throttle, stick=stick, stick_roll=stick_roll, rudder=rudder, flags=flags)


def tail(pitch: int, stick: int, q: int, r: int) -> int:
    """The fuselage's attitude on the ground. The tail lifts while the air
    over the tailplane -- airspeed and propwash -- at the tailplane's attack
    (the attitude, plus the elevator's share of the stick forward) is worth
    more than the tail's load, and settles back while it is worth less, at
    a rate that grows with the difference, to at most PITCH_RATE a step;
    between the tail resting on its wheel and the fuselage level."""
    air = q + ((Q_WASH * r * r) >> 16)
    moment = air * (pitch - ((stick * ELEVATOR) >> 6)) - TAIL_LOAD
    if moment > 0:
        pitch -= min(PITCH_RATE, (moment >> TAIL_SHIFT) + 1)
    elif moment < 0 and pitch < THREE_POINT:
        pitch += min(PITCH_RATE, ((-moment) >> TAIL_SHIFT) + 1)
    return max(TAIL_UP_LIMIT, min(THREE_POINT, pitch))


# --- What the tests and the game ask -----------------------------------------

def on_ground(s) -> bool:
    return bool(s.flags & GROUND)


def parked(s) -> bool:
    return bool(s.flags & PARKED)


def tail_up(s) -> bool:
    return on_ground(s) and s.pitch < THREE_POINT


def stalled(s) -> bool:
    """Whether the wing is stalled: from past ALPHA_STALL until under ALPHA_RECOVER."""
    return bool(s.flags & STALLED)


def stall_warning(s) -> bool:
    """The stall light: in the air, the wing stalled or near it."""
    return not on_ground(s) and (stalled(s) or attack(s.pitch, s.gamma) >= ALPHA_WARNING)


def mph(s) -> float:
    return s.speed / SPEED_PER_FPS / j3.MPH
