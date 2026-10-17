# Cub

A Piper Cub flight simulator for the 128K ZX Spectrum, drawn with the
fast3d engine: take off from a runway, fly over farms, a village and woods
in a world that wraps, and land again, from the cockpit or chasing the Cub.
The flying is a simplified physical flight model, tuned in Python and then
built in Z80 that matches the Python frame for frame.

The plan and its stages are this repository's issues: the parent issue
describes the whole game, and each stage is a sub-issue.
[GLOSSARY.md](GLOSSARY.md) is Cub's domain language, and
[docs/adr/](docs/adr/) the decisions made, starting with why Cub has its
own flight model.

## What exists so far

The Cub stands on the runway, rolls, steers, lifts its tail and takes off,
in the Python model. The Spectrum version draws the view; its flight
model comes in a later stage.

- **The world** is [world.json](world.json), checked against
  [world.schema.json](world.schema.json): each object keyed by its name,
  with its kind, position (16-bit, in feet) and turn; and where the Cub
  starts. So far it holds only the airfield: a runway, a hangar and a
  windsock. A model's vertices are signed bytes, so no model is more than
  254 feet across, and the runway, 2,000 feet long, is placed as one
  object with a count of segments, which `game.load_world` lays end to end
  along its turn: the first draws its near end, the last its far end, and
  each its sides and a centreline dash. The models are in
  [models.py](models.py), as edges between vertices in feet.
- **The Python model**, [game.py](game.py), has the frame. Given the game
  state, the keys held and the steps owed (fiftieths of a second), it
  returns the next state and the whole screen drawn. A frame runs the
  steps owed through the flight model, at most 10, counts them into the
  clock, and draws the cockpit view: the airfield and the horizon line in
  black on cyan, rows 0 to 17, above an empty white-on-blue panel. The
  view is drawn with fast3d's model (`examples/fast3d/model.py`), so it is
  exactly what the engine draws.
- **The flight model**, [flight.py](flight.py), is a step of a fiftieth
  of a second, in fixed point, as the Z80 will do it
  ([ADR 0002](docs/adr/0002-fixed-point-flight-model.md)). Its constants
  come from [j3.py](j3.py), the J-3's published figures and the
  assumptions no source gives, set out with their sources in
  [docs/j3-figures.md](docs/j3-figures.md).
- **The pygame window**, [fly.py](fly.py), flies the Python model from the
  keyboard and shows its frames as the Spectrum would.
- **The Spectrum version**, [cub.s](cub.s), is a 128K program. Each frame
  is drawn on the screen not being shown and shown at the next interrupt,
  as fast3d's demo does. It has a test mode, in which the keys and the
  steps owed come from `test_keys` and `test_steps` rather than the
  keyboard and the interrupt.

### How it flies

A flight starts lined up on the runway, tail down, the engine idling at
550 rpm and the parking brake on. The keys are bits of a word the frame
is given (`game.KEYS`): throttle up and down, rudder left and right,
brakes, and the stick back, forward, left and right.

- **The throttle** moves while its key is held and stays where it is left.
  The engine's rpm follows it, from idle to 2,300 standing still and a
  little more with speed. Thrust falls with speed from 320 lb standing
  still.
- **The brakes** are on, as a parking brake, until their key is first
  pressed; after that they are on while it is held. They hold the Cub
  even at full throttle.
- **The stick and the rudder** move towards where their keys push them and
  spring back to the middle when let go.
- **On the ground**, the wheels' friction acts on what the wing leaves of
  the weight. The rudder turns the Cub at a 40-foot radius at full
  deflection. The tail comes up when the tailplane's lift, from the
  airspeed and the propwash, overcomes the tail's load. Its attack is the
  fuselage's attitude, plus the elevator's share of the stick: at full
  throttle the tail starts to come up at 25 mph with the stick central, at
  16 with it forward, and back holds it down. As speed builds the tail settles where its lift balances
  the load. The Cub lifts off when the wing holds its weight: at 39 mph
  tail down, the manual's figure; at about 60 mph left alone, the tail
  flying itself; or as soon as it is pulled back, from tail up.
- **In the air**, the stick turns the nose while it is held, and the
  attitude stays where it is left. The flight path climbs or sinks with
  the lift.

### How it draws

The cockpit view is fast3d's camera at the pilot's eye, 7 feet above the
main wheels, turned as the Cub is: pitch, heading, bank. The line of sight
is 6 degrees below the fuselage's datum, so that tail down, 13.6 degrees
nose up, the view is not all sky. The view is 256 by 144 pixels, centred on row 72: fast3d's
`SCREEN_CENTRE_Y` is defined to match, and lines are clipped to the view. One unit is a foot, so fast3d's near plane is 8 feet from the
eye and its far plane 8,191 feet away. The world wraps (fast3d's
`WORLD_WRAP`).

Each frame clears the whole view. It then draws the horizon line, every
edge of the objects the cull lets through with both ends in front of the
near plane, and each edge crossing the near plane cut there. Everything is
clipped to the view. At the start of a flight the runway's first segment
runs from behind the eye, so its sides are drawn from where they come
into view, cut at the near plane.

The horizon is the line of directions level with the ground. The world's
up in camera space, u, is the camera matrix's middle row, and a point on
the screen is level when
`u_x (x - 128) + u_y (72 - y) + 256 u_z = 0`, 256 being fast3d's focal
length. Mostly level, its ends are worked out at the view's left edge and
one past its right, 128 pixels (`HORIZON_REACH`) either side of the
centre. Banked steeper than 45 degrees, they are worked out past its top
and bottom instead.
Each end takes two of fast3d's `divide_wide`, then the line goes through
`clip_line`. An end lies within 2.13 pixels of the true line worked out
from the same matrix, 0.62 on average.

A frame at the start takes about 529,000 T-states, about 6.7 frames a
second on a 128K's 3.5469 MHz. Clearing the whole view is about 61,000 of
that.

### Memory

| Where | What |
|---|---|
| bank 2, `$8000` | the program, fast3d and the world |
| bank 5, `$4000` | the first screen; from `$6000` the points, the objects drawn and the lines cut at the near plane |
| bank 7, `$C000` | the second screen, paged in all the time |

## Where it lives

Cub is developed inside a checkout of
[zx-spectrum-emulator](https://github.com/jonsole/zx-spectrum-emulator),
where it is the `examples/cub` submodule. It needs these beside it there,
by relative path:

- the fast3d engine and its model, in `examples/fast3d`;
- the Python the examples share, in `examples/scripts`: `z80file.py` for
  the snapshot, `probe.py` for the checks;
- the emulator's snapshot probe, in `cpp-core`;
- sjasmplus, in `tools`.

A clone of this repository on its own does not build.

```
git clone --recurse-submodules https://github.com/jonsole/zx-spectrum-emulator
cd zx-spectrum-emulator/examples/cub
```

## Building, running and checking

From the emulator's root, with its venv (pygame and jsonschema are in it):

```powershell
.\.venv-win\Scripts\python.exe examples\cub\build.py       # -> examples\cub\output\cub.z80, with its SLD
.\.venv-win\Scripts\python.exe examples\cub\fly.py         # the Python model in a pygame window
```

In the pygame window, Q and A are the throttle, Z and X the rudder, Space
the brakes, and the cursor keys the stick (down pulls back); the window's
title shows the speed, the rpm, the throttle and the height, since there is
no panel yet.

To run the Spectrum version, choose **ZX Spectrum: Cub** in VS Code's Run
and Debug. It builds the program first.

`build.py` writes fast3d's tables and line blocks into fast3d's own
`output/`, with fast3d's own writers. The engine includes them from there,
and sjasmplus looks beside the engine before any include path.

The checks:

```powershell
.\.venv-win\Scripts\python.exe examples\cub\tests\world_schema_test.py   # the world against its schema
.\.venv-win\Scripts\python.exe examples\cub\tests\view_test.py           # the Python view against exact geometry
.\.venv-win\Scripts\python.exe examples\cub\tests\frames_test.py         # the Z80 against the Python, frame by frame
.\.venv-win\Scripts\python.exe examples\cub\tests\ground_test.py         # rolling, steering, braking, taking off
```

- `world_schema_test.py` checks that the world passes its schema, and
  that twelve broken copies of it fail. Each copy holds a mistake someone
  could make by hand: a kind with no model, a position past 16 bits, a
  list where names belong, and so on. It also checks that the schema's
  kinds are models.py's.
- `view_test.py` checks the horizon for 20,000 cameras, every pitch
  among them, against the true line worked out in floating point. It also
  checks that at the start of a flight the runway's sides are drawn where
  they come into the view, worked out exactly from the runway's corners.
- `frames_test.py` builds Cub and loads it into the snapshot probe
  (build it with `cpp-core\build.ps1 -Release -Target snapshot_probe`). It
  calls `setup` and turns the test mode on, then runs ten scripted frames
  of steps, then 60 more from varied states poked into the Z80's state, at
  every pitch, heading and bank, round the airfield and above it. After
  every frame the whole game state and the whole screen drawn on must
  match the Python model's. Until the Z80 has the flight model, no keys
  are held: standing idling on the parking brake, a step changes nothing
  but the clock. The varied frames run no steps, so they compare only the
  view.
- `ground_test.py` drives scripted runs through the frame and checks them
  against what j3.py's figures work out to in floating point. It covers
  the start, the throttle staying where it is set, and the tail starting
  to come up with the stick central, forward and back. It checks lift-off at the
  manual's 39 mph, in about the published ground roll, and lift-off a
  third of a second after pulling back with the tail up. It checks the
  lift-off with the stick central, where the tail's balance leaves the
  wing enough attack: nothing was tuned to that, so it, and the ground
  roll against the published 370 ft, are the model's independent checks.
  The 39 mph lift-off and the 25 mph tail are what the model was tuned
  to, so those check the stepping and the rounding. It checks the
  rudder's turn against its radius, the brakes' stop against their
  friction, and the same run giving the same state at every rate from 1
  to 10 steps a frame.

The test mode leaves out what only runs live: `start`, the interrupt, and
the wait for it to show a frame. That was checked by running `cub.z80` in
the emulator: both screens held exactly the Python model's frame, and
the screen shown changed from one to the other.

Each check has been shown to fail on a bug planted for it. Without the cut
at the near plane, the start's runway sides go missing. With the
horizon's slope flipped, 4,130 cameras fail. With the Z80's horizon end
wrong, 13 varied frames fail. Without the Z80's clock, every frame after
the first fails. Without the propwash, the tail comes up at 32 mph, not
25. Without the brakes, full throttle moves the parked Cub. With steering
twice as hard, the turn is twice as far. With a frame's keys held for its
first step only, the frame rates disagree.

## Not done

Everything after taking off. The stages, in order, are this repository's
sub-issues:

- flying and the panel;
- touchdowns, landings and crashes;
- the chase view;
- the whole world;
- each stage again in Z80;
- sound on the AY.

Some limits so far:

- The Spectrum version has no flight model, and outside the test mode
  reads no keys.
- In the air the model is only what leaving the ground needs. The stick
  turns the nose, but nothing rolls or banks, the rudder does nothing, and
  the stall does not drop the nose. The climb after lift-off is shallow:
  16 ft in five seconds with the stick let go. Flying comes next.
- Back on the ground after leaving it, the Cub is simply put down. Telling
  a landing from a crash comes with touchdowns.
- The eye stays 7 feet above the main wheels whatever the attitude.
- Buildings are drawn see-through. Back faces come with the whole world.
- The camera's angles go to fast3d's `make_matrix`, which turns about z
  last, about the world's axis rather than the Cub's. That is right while
  the Cub's bank is 0, and needs a camera matrix of the Cub's own
  attitude before it banks in flight.
- The frame is slower than the 8 frames a second wanted, partly because
  it clears the whole view every frame.
- `compute_frame` and `render_frame` follow fast3d's demo closely: the
  pool of points, the list of objects drawn, the cut lines and drawing
  each edge are much the same code. A routine in fast3d for drawing a
  world of objects could serve both. That is left until Cub's needs (back
  faces, the chase view, the 8 frames a second) say what it must do.
