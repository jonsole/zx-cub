"""Cub's flight model: a step, a 25th of a second, of the Cub on the
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
  speed     2^-16 feet a tick, a fiftieth of a second, along the flight
            path (on the ground, along the heading), 24 bits, held to
            SPEED_LIMIT; V16 = speed >> 4,
            15 bits, for the products
  gamma     the flight path's climb, angle units times 256, 24 bits signed,
            held to +-90 degrees
  Q         V16^2 >> 12, as the dynamic pressure: 18 bits
  PER_SPEED the speed's reciprocal, the step's one division: 16 bits
  dV        a tick's change of speed, in speed units: G_TICK is gravity's.
            A step is STEP_TICKS ticks: it adds STEP_TICKS times a tick's
            change, and moves STEP_TICKS ticks' way (see ADR 0004)
Every product along the way is a number of up to 24 bits times one of up
to 16, and fits 32 bits signed, so that the Z80 keeps it in DE:HL: the
widest are the steering's, the position's speed >> 3 times a sine, and the
lift's sideways part times PER_SPEED, 31 bits at their most.

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
TICKS_PER_SECOND = 50              # speed's unit is 2^-16 feet a tick
STEP_SHIFT = 1                      # a step is 2^STEP_SHIFT ticks: the Z80's flight
STEP_TICKS = 1 << STEP_SHIFT        # model is too slow to step every tick (ADR 0004)
STEPS_PER_SECOND = TICKS_PER_SECOND // STEP_TICKS
FOOT = 65536                        # a position's unit: 16.16
SPEED_PER_FPS = FOOT / TICKS_PER_SECOND     # speed units in a foot a second


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
THROTTLE_RATE = 4 * STEP_TICKS      # a step: full in 1.3 seconds
STICK_FULL = 64                     # the stick, back positive, and right positive
STICK_RATE = 8 * STEP_TICKS         # full in 0.16 seconds
RUDDER_FULL = 64                    # the rudder, right positive
RUDDER_RATE = 8 * STEP_TICKS

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


# The flight model's own sines: 32,767 sin at 1,024 angles round the turn,
# taken at the nearest, with no interpolation and so no multiplication --
# a step needs eight, and the Z80 has no time for eight more products. A
# 1,024th of a turn is 0.35 degrees, so a direction is never more than
# 0.18 degrees out. (The camera keeps sin16's interpolation: the view must
# turn smoothly.)
SINE_STEPS = 1024
SINE_FINE = [round(32767 * math.sin(2 * math.pi * i / SINE_STEPS)) for i in range(SINE_STEPS)]
SINE_SHIFT = 6                      # 65,536 / 1,024


def sin_fine(a: int) -> int:
    return SINE_FINE[((a + (1 << (SINE_SHIFT - 1))) >> SINE_SHIFT) & (SINE_STEPS - 1)]


def cos_fine(a: int) -> int:
    return sin_fine(a + TURN // 4)


# --- Constants from the figures --------------------------------------------

V16_PER_FPS = SPEED_PER_FPS / 16
Q_PER_FPS2 = V16_PER_FPS ** 2 / 4096                # Q a (ft/s)^2
G_TICK = round(j3.G / TICKS_PER_SECOND * SPEED_PER_FPS)    # dV of 1 g, 843

# Lift and drag: dV = (QK CL1024) >> 12, QK = (Q K_AERO) >> 12 shared by the
# two, CL1024 the coefficient times 1,024: q S CL / m a tick.
K_AERO = round(0.5 * j3.RHO * j3.WING_AREA * j3.G / j3.WEIGHT / Q_PER_FPS2
               / TICKS_PER_SECOND * SPEED_PER_FPS / 1024 * 2 ** 24)
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

# Thrust: dV = ((r^2 >> 2) K_THRUST >> 16) - (((V16 r) >> 8) K_FALL >> 16), r the
# r.p.m. over STATIC_RPM in 256ths: r^2 >> 2 so that it fits 16 bits.
R_SHIFT = 10
R_SCALE = round(256 * 2 ** R_SHIFT / j3.STATIC_RPM)  # r = (rpm R_SCALE) >> R_SHIFT: a byte's multiplier
K_THRUST = round(j3.STATIC_THRUST * j3.G / j3.WEIGHT / TICKS_PER_SECOND * SPEED_PER_FPS * 4)
K_FALL = round(j3.THRUST_FALL / j3.MPH / V16_PER_FPS * j3.G / j3.WEIGHT
               / TICKS_PER_SECOND * SPEED_PER_FPS / 256 * 2 ** 24)

# The engine: r.p.m. towards IDLE + (STATIC - IDLE + a little with speed)
# times the throttle, an eighth of the way a tick (RPM_LAG).
IDLE_RPM = round(j3.IDLE_RPM)
STATIC_RPM = round(j3.STATIC_RPM)
K_RPM_SPEED = round(j3.RPM_PER_MPH / j3.MPH / V16_PER_FPS * 65536)     # (V16 K) >> 16

# Friction, of the load on the wheels, in 256ths.
ROLLING = round(j3.ROLLING_FRICTION * 256)
BRAKING = round(j3.BRAKE_FRICTION * 256)

# Steering on the ground: full rudder turns at TURN_RADIUS.
K_STEER = round(TURN / (2 * math.pi) / j3.TURN_RADIUS / V16_PER_FPS / TICKS_PER_SECOND
                / RUDDER_FULL * 2 ** 20)            # a tick's: heading += (rudder V16 K_STEER) >> 20

# The tail (j3.py says how it is modelled).
THREE_POINT = angle(j3.THREE_POINT)
TAIL_UP_LIMIT = angle(0.0)          # tail up, the fuselage no lower than level
ELEVATOR = angle(j3.ELEVATOR)
Q_WASH = round(j3.PROPWASH_MPH ** 2 * j3.MPH ** 2 * Q_PER_FPS2)
TAIL_LOAD = round(j3.TAIL_LOAD * j3.MPH ** 2 * Q_PER_FPS2 * TURN / 360)
TAIL_SHIFT = 15 - STEP_SHIFT        # how fast the tail answers its moment, a step
RPM_LAG = 3 - STEP_SHIFT            # the r.p.m. go an eighth of the way to the target a tick
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
# does not turn its path in one step. Then, for a step's ticks,
# gamma += (across PER_SPEED) >> (8 - STEP_SHIFT),
# across held to ACROSS_LIMIT, and
# heading += (sideways PER_SPEED) >> (16 - STEP_SHIFT), rounded. ACROSS_LIMIT keeps the
# flight path from curving faster than 4 g would. (The turn's rate is the
# sideways force over the speed along the path, not over its level part:
# a little slow climbing or diving, and no gimbal at 90 degrees.)
K_PER_SPEED = round(TURN / (2 * math.pi) * 256 / 16 * 256)
ACROSS_LIMIT = 4 * G_TICK
V16_FLOOR = speed_of(10) >> 4
GAMMA_LIMIT = (TURN // 4) << 8


# --- The step --------------------------------------------------------------

def toward(value: int, target: int, rate: int) -> int:
    if value < target:
        return min(value + rate, target)
    return max(value - rate, target)


def lift_coefficient(alpha: int) -> int:
    """CL times 1,024 at an angle of attack: a straight line to the stall,
    and falling away past it; held to +-CL_MAX, so that an attitude far
    from the flight path, which the stick can leave, neither lifts nor
    drags more than the wing can, and every product it goes into fits 32
    bits."""
    if alpha <= ALPHA_STALL:
        cl = ((alpha - ALPHA_ZERO) * CL_SLOPE) >> CL_SLOPE_SHIFT
    else:
        cl = CL_MAX - (((alpha - ALPHA_STALL) * CL_SLOPE) >> (CL_SLOPE_SHIFT + 1))
    return max(-CL_MAX, min(CL_MAX, cl))


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
    rpm = s.rpm + ((target - s.rpm) >> RPM_LAG)
    r = (rpm * R_SCALE) >> R_SHIFT

    # The air.
    q = (v16 * v16) >> 12
    on_ground = flags & GROUND
    gamma = 0 if on_ground else s.gamma
    alpha = attack(s.pitch, gamma)
    cl = lift_coefficient(alpha)
    cd = CD0 + ((cl * cl * INDUCED) >> 22)
    qk = (q * K_AERO) >> 12
    lift = (qk * cl) >> 12
    drag = (qk * cd) >> 12
    thrust = ((((r * r) >> 2) * K_THRUST) >> 16) - ((((v16 * r) >> 8) * K_FALL) >> 16)

    speed, pitch, heading, bank = s.speed, s.pitch, s.heading, s.bank
    if on_ground:
        load = max(0, G_TICK - lift)
        friction = (load * (ROLLING + (BRAKING if braking else 0))) >> 8
        speed = min(SPEED_LIMIT, max(0, speed + ((thrust - drag - friction) << STEP_SHIFT)))
        heading = (heading + ((rudder * v16 * K_STEER) >> (20 - STEP_SHIFT))) & 0xFFFF
        pitch = tail(pitch, stick, q, r)
        if lift > G_TICK:
            flags &= ~GROUND                    # lift-off
    else:
        if alpha > ALPHA_STALL:
            flags |= STALLED
        elif alpha < ALPHA_RECOVER:
            flags &= ~STALLED
        gravity = (G_TICK * sin_fine(gamma >> 8)) >> 15
        speed = min(SPEED_LIMIT, max(0, speed + ((thrust - drag - gravity) << STEP_SHIFT)))
        per_speed = K_PER_SPEED // max(v16, V16_FLOOR)
        across = ((lift * cos_fine(bank)) >> 15) - ((G_TICK * cos_fine(gamma >> 8)) >> 15)
        across = max(-ACROSS_LIMIT, min(ACROSS_LIMIT, across))
        gamma = max(-GAMMA_LIMIT, min(GAMMA_LIMIT, gamma + ((across * per_speed) >> (8 - STEP_SHIFT))))
        sideways = (lift * sin_fine(bank)) >> 15
        heading = (heading + ((sideways * per_speed + (0x8000 >> STEP_SHIFT)) >> (16 - STEP_SHIFT))) & 0xFFFF
        pitch = signed16(pitch + ((stick * AIR_PITCH_RATE) >> 6) - (STALL_PITCH_RATE if flags & STALLED else 0))
        bank = max(-BANK_LIMIT, min(BANK_LIMIT, bank + ((stick_roll * ROLL_RATE) >> 6)))

    # Where it goes: speed >> 3, 16 bits, so that each product is 16 by 16;
    # 8 units of 2^-16 feet a tick is a 1,500th of an inch.
    speed8 = speed >> 3
    along = (speed8 * cos_fine(gamma >> 8)) >> 15
    x = (s.x + ((along * sin_fine(heading)) >> (12 - STEP_SHIFT))) & 0xFFFFFFFF
    z = (s.z + ((along * cos_fine(heading)) >> (12 - STEP_SHIFT))) & 0xFFFFFFFF
    y = s.y + ((speed8 * sin_fine(gamma >> 8)) >> (12 - STEP_SHIFT))
    if y <= 0 and not flags & GROUND:
        if gamma < 0 or y < 0:                  # back on the ground
            y, gamma, bank, flags = 0, 0, 0, (flags | GROUND) & ~STALLED
            pitch = max(TAIL_UP_LIMIT, min(pitch, THREE_POINT))     # between level and three-point
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
