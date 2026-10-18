# A step of the flight model is a 25th of a second, two ticks

The flight model was written to step every fiftieth of a second, once an
interrupt. Ported to the Z80 operation for operation, a step took 64,000
T-states: nine tenths of a fiftieth of a second's 70,938, before anything
was drawn. Even made as quick as its arithmetic allows, it would have
taken a third of the Spectrum's time, and the frame rate below four.

So a step is two ticks, a 25th of a second, and the interrupt owes a
step for every two. The speeds and the forces stay in a tick's units --
speed in 2^-16 feet a tick, a force as a tick's change of speed -- so
every product keeps the width it had; a step applies them twice over, as
a shift (`STEP_SHIFT`): the speed changes by its tick's change shifted
left, the flight path and the turns by theirs shifted one less to the
right, and the position moves a step's ticks' way. The rates a step --
the controls, the pitch and roll, the tail, the engine's lag -- are
doubled, so that each still takes as long in seconds.

The step then took about 17,500 T-states on the ground and 34,000 in the
air, after narrowing products where it changed nothing a test could see,
keeping them in registers and the sines in a table: 12% and 24% of the
Spectrum's time.

## Considered

- **Steps of a fiftieth, made faster.** Even at 20,000 T-states a step,
  about the least its products allow, the flight model would take 30% of
  the time, and the frame rate fall to about 4.
- **A step of a 25th, with speeds in its units.** Every per-step quantity
  doubles, and the lift, the speed and several products would need more
  bits than the Z80's multiply takes.
- **A step of four ticks or more.** Quicker still: `STEP_SHIFT` of 2, 12.5
  steps a second, would halve the flight model's time again, and is the
  next to try if the frame rate needs it. Much longer, and the tail's and
  the flight path's responses, a few tenths of a second, would be stepped
  too coarsely.
