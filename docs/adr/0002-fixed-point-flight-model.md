# The flight model is fixed point, written as the Z80 will compute it

The Z80 version has to match the Python model byte for byte after every
frame. So the Python flight model is not a model in floating point for
the Z80 to approximate. It is integer arithmetic of exactly the kind the
Z80 does cheaply: products, shifts right that floor as `SRA` does, one
division a step, and a sine looked up in a table. Its
units are chosen to fit, each with a width the Z80 keeps it in, and the
model holds every value to its width as the Z80 would:

- angles 65,536 to the turn;
- positions in feet as 16.16;
- speed in 2^-16 feet a tick, a fiftieth of a second ([ADR 0004](0004-a-step-is-two-ticks.md)).

Its constants are worked out once from the J-3's figures in `j3.py` and
rounded. The Z80 version then implements the same operations, in the same
order, on the same integers.

The real aeroplane's figures stay in floating point in one place,
`j3.py`. The tests use it to work out what the fixed-point model should
come to, the manual's lift-off speed or a stopping distance, so that what
the tests expect never comes from the code under test.

## Considered

- **Floating point in Python, and a Z80 that gets close.** Simpler to
  write and tune, but the Z80 could never match it exactly. The frame
  comparison, the project's main check, would become a tolerance check on
  every number in the state, and drift would compound over a flight.
- **Tuning in floating point, then porting to fixed point once the feel is
  right.** Tuning would then have to happen twice: rounding and truncation
  change how the model flies, and the feel is the point.
