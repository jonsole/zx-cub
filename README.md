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

In the Python model the Cub stands on the runway, rolls, steers, lifts its
tail and takes off, then flies: it climbs, turns banked, stalls and
recovers, with the panel below the view. The Spectrum version flies the
same flight model from the keyboard or an Interface II joystick, and
draws the view and the panel the same way, byte for byte.

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
  state, the keys held and the steps owed (25ths of a second), it
  returns the next state and the whole screen drawn. A frame runs the
  steps owed through the flight model, at most 10, counts them into the
  clock, and draws the cockpit view: the airfield and the horizon line in
  black on cyan, rows 0 to 17, above the panel in white on blue
  ([panel.py](panel.py)). The view is drawn with fast3d's model
  (`examples/fast3d/model.py`), so it is exactly what the engine draws.
- **The flight model**, [flight.py](flight.py), is a step of a 25th of
  a second, in fixed point, as the Z80 does it
  ([ADR 0002](docs/adr/0002-fixed-point-flight-model.md),
  [ADR 0004](docs/adr/0004-a-step-is-two-ticks.md)). Its constants
  come from [j3.py](j3.py), the J-3's published figures and the
  assumptions no source gives, set out with their sources in
  [docs/j3-figures.md](docs/j3-figures.md).
- **The pygame window**, [fly.py](fly.py), flies the Python model from the
  keyboard and shows its frames as the Spectrum would.
- **The Spectrum version**, [cub.s](cub.s), is a 128K program. Each frame
  reads the keys, runs the steps owed through the flight model,
  [flight.s](flight.s), redraws what changed on the panel
  ([panel.s](panel.s)) on both screens, and draws the view on the screen
  not being shown, to be shown at the next interrupt, as fast3d's demo
  does. The interrupt
  counts fiftieths, and a step is owed for every two. It has a test mode,
  in which the keys and the steps owed come from `test_keys` and
  `test_steps` rather than the keyboard and the interrupt.

### How it flies

A flight starts lined up on the runway, tail down, the engine idling at
550 rpm and the parking brake on. The keys are bits of a word the frame
is given ([keys.py](keys.py)): throttle up and down, rudder left and
right, brakes, and the stick back, forward, left and right; and the view
and a new flight, which are kept and act from their own later stages.

| | On the Spectrum | In the pygame window |
|---|---|---|
| Throttle up, down | Q, A | Q, A |
| Rudder left, right | Z, X | Z, X |
| Brakes | Space, or fire | Space |
| Stick left, right, back, forward | an Interface II joystick: 6, 7, 8, 9 in its first port, 1, 2, 3, 4 in its second (back is down) | the cursor keys (down pulls back) |
| The view, a new flight | V, N | |


- **The throttle** moves while its key is held and stays where it is left.
  The engine's rpm follows it, from idle to 2,300 standing still and a
  little more with speed. Thrust falls with speed from 320 lb standing
  still.
- **The brakes** are on, as a parking brake, until their key is first
  pressed; after that they are on while it is held. They hold the Cub
  even at full throttle.
- **The stick and the rudder** move towards where their keys push them and
  spring back to the middle when let go. The stick pitches the Cub, back
  and forward, and rolls it, left and right.
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
- **In the air**, the stick turns the nose and rolls the Cub while it is
  held, 15 and 30 degrees a second at full stick, and the attitude stays
  where it is left, as a Cub trimmed for how it is flying. The bank goes
  no steeper than 60 degrees. The lift, from the airspeed and the wing's
  angle to the air, is tilted with the bank: its upward part, less the
  weight's share across the flight path, curves the path up or down, and
  its sideways part turns it, so that a banked Cub turns without rudder.
  In a turn some of the lift goes sideways, so holding the height takes a
  little back stick. Thrust and drag speed the Cub up or slow it, and so
  does gravity along the path: diving speeds it up, climbing slows it.
- **The stall.** Past 16.5 degrees of attack the wing stalls: its lift
  falls away, and the nose drops 30 degrees a second (full back stick
  only slows it by half) until the wing is under 6 degrees and flying
  again. The stall
  light comes on 2 degrees of attack short of the stall, and stays on
  while the wing is stalled.
- **How it compares.** Held level as it slows with the throttle closed,
  it stalls at 37.5 mph, against the manual's 38. Full throttle flies
  level at 87 mph, the published figure. At the throttle that turns the
  engine at the manual's cruise r.p.m., 2,150, it cruises at 78 mph,
  against the manual's 73: what the propeller and the drag that make the
  top speed come to there. Full throttle climbs at 442 feet a minute at
  57 mph, against a published 450. [docs/j3-figures.md](docs/j3-figures.md) says
  which of these the model was tuned to.

### The panel

```
 MPH   FEET   HDG
  73   1234   045          STALL
 THR [throttle....]  CLIMB [sink..|..climb]
```

The airspeed in miles an hour, the height of the wheels in feet and the
heading in degrees are numbers; the throttle and the climb are bars, the
climb a pixel each 25 feet a minute either way of the middle, 800 at most;
the stall light is the word STALL, dark until it lights in white on red.
The characters are Cub's own, in [font.py](font.py).

The game state keeps what the panel shows, so that a frame redraws only
what has changed. Only the values change, so the Spectrum version draws
them on both screens at once and the panel is the same whichever screen
is shown ([ADR 0003](docs/adr/0003-panel-on-both-screens.md)). Its
unchanging parts -- the labels, the stall light's word, the bars' feet --
are drawn once at the start, from the bytes `panel.draw_static` inks,
which build.py lists. Each frame then works out what the panel shows as
`panel.values` does, and redraws each part whose shown_ field differs: a
number from its decimal digits, a bar as eight bytes a line from a table
of left-hand masks, the light by its five attributes. With nothing
changed that takes about 3,200 T-states; with everything, as on the first
frame, 32,000.

### How it draws

The cockpit view is fast3d's camera at the pilot's eye, 7 feet above the
main wheels, turned as the Cub is: rolled by its bank about its own
length, then pitched, then turned to its heading. Its matrix is made from
the Cub's angles in their full 16 bits, with the flight model's
interpolated sines, as products of two or three of them
(`game.camera_matrix`, and `camera_matrix` in cub.s), each entry then
rounded to fast3d's byte. fast3d's own `make_matrix` would not do: it
takes its angles in whole 256ths of a turn, so the view turned in steps of
1.4 degrees, a jump of 6 pixels at the horizon, and it rolls last, about
the world's axis rather than the Cub's. The Z80 hands the matrix to
fast3d's `set_camera_matrix`. Every entry is within 0.54 of a 127th of
the true rotation, so the view turns in steps of about half a degree.

That half a 127th is still enough to put an object a third of a degree
from where it is, and as the view turns the entries round now one way
and now the other: the objects wobbled by a pixel a frame, and up to 3.
So each entry's rounding is kept as well, in 32nds of a 127th, and once
the cull has let an object through, its centre in camera space, T, has
their share put back: (R^T d + 16) >> 5, d the object's position less the
eye's (`game.fine_centre`, and `fine_centre` in cub.s). T is then within
0.03 pixels of exact on average, and its error changes by 0.03 pixels a
frame as the view turns, against 1.1. The vertices about the centre, from
the object's own byte matrix, are within 0.3 pixels of steady.

The line of sight is 6 degrees below the fuselage's datum, so that tail down, 13.6 degrees
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

Drawing the view at the start takes about 600,000 T-states. Clearing the
whole view is about 61,000 of that, the camera's matrix about 24,000, and
putting each object's centre right 5,100 an object, 51,000 for the start's
ten. A step of the flight model takes about 17,500 more on the ground and
34,000 in the air, and a frame runs a step for every 25th of a second it
takes. So on the runway a frame takes about 685,000 T-states, 5.2 frames
a second on a 128K's 3.5469 MHz, and in the air about 760,000, 4.7; the
panel adds 3,200 a frame, and a few thousand more for each number that
changed.

### The flight model on the Z80

[flight.s](flight.s) is `flight.step` operation for operation, in bank 7
above its screen. Every product is a signed number of up to 24 bits times
one of up to 16, and each fits 32 bits (flight.py says so of every one),
so `mul` leaves it in DE:HL, and `SHIFTED` shifts it as Python's `>>`
does, flooring, in code written out for each shift. The magnitudes
multiply in `umul16`: a multiplier of a byte or of under 12 bits by shift
and add from its highest set bit, a wider one by quarter squares from a
table of n n / 4. The speed's one division a step is a restoring
division. The flight model's sines are a table of 1,024 taken at the
nearest, with no multiplication; the camera keeps `sin16`'s interpolated
ones.

A step was 64,000 T-states as first written, nine tenths of a fiftieth
of a second. Running a step every two fiftieths (ADR 0004), narrowing products
where it changed nothing a test could see, keeping products in registers
and the sines in a table brought it to the figures above: still about
12% of the Spectrum's time on the ground and 24% in the air, more than
half of it in `umul16`.

### Memory

| Where | What |
|---|---|
| bank 2, `$8000` | the program, fast3d and the world |
| bank 5, `$4000` | the first screen; from `$6000` the points, the objects drawn and the lines cut at the near plane |
| bank 7, `$C000` | the second screen, paged in all the time; from `$DB00` the flight model, its sines and its quarter squares, and the panel |

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

The keys are in [How it flies](#how-it-flies). In the pygame window the
title adds the engine's r.p.m. and what the Cub is doing to the panel.

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
.\.venv-win\Scripts\python.exe examples\cub\tests\flying_test.py         # the stall, the speeds, the climb, turning
.\.venv-win\Scripts\python.exe examples\cub\tests\panel_test.py          # the panel against the state, every frame
```

- `world_schema_test.py` checks that the world passes its schema, and
  that twelve broken copies of it fail. Each copy holds a mistake someone
  could make by hand: a kind with no model, a position past 16 bits, a
  list where names belong, and so on. It also checks that the schema's
  kinds are models.py's.
- `view_test.py` checks the horizon for 20,000 cameras, every pitch
  among them, against the true line worked out in floating point. It
  checks the camera's matrix for 5,000 attitudes against the rotation
  they make in floating point, and the horizon for 2,000 banked attitudes
  of the Cub against where the bank puts it, the level horizon turned
  about the view's centre, so that the view rolls about the Cub's own
  length whatever the heading. It checks the objects' centres, at 300
  attitudes round the airfield, against where their positions land in
  floating point: 0.03 pixels out on average, 0.17 at most. It also
  checks that at the start of a flight the runway's sides are drawn where
  they come into the view, worked out exactly from the runway's corners.
- `frames_test.py` builds Cub and loads it into the snapshot probe
  (build it with `cpp-core\build.ps1 -Release -Target snapshot_probe`). It
  calls `setup` and turns the test mode on, then flies two scripted
  take-offs, one held tail down and one tail up, steered with the rudder,
  pulled off and climbing into a turn, their frames running 1 to 12 steps
  each, past the 10 a frame runs. Then 60 frames from varied flight states
  poked into the Z80's, on the ground and in the air up to 200 mph, with
  varied keys and a few steps each; and 60 from varied views, no steps, at
  every pitch, heading and bank round the airfield and above it. Between
  them, a flight in the air from 70 mph and 300 feet: a climb, a cruise,
  turns left and right, then the throttle closed and the stick held back
  into a stall, and let go; it must stall and recover with the stall light
  out. After every frame the whole game state and the whole screen drawn
  on, panel and all, must match the Python model's, and the panel's parts
  the Z80 says it redrew (`panel_redrawn`) must be those whose shown_
  fields changed, and no others.
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
- `flying_test.py` flies scripted flights through the frame, with a pilot
  in the test working the stick from what it sees, a second ahead. It
  checks the stick springing back and the attitude staying where it is
  left. Slowing level with the throttle closed, it checks the stall light
  coming on at the speed its warning angle works out to, and the stall at
  the manual's 38 mph; then the nose dropping with the stick held back,
  stopping where the wing flies again, and the Cub recovering as the
  speed builds. It checks the top speed, the cruise at the throttle that
  gives the cruise r.p.m. and the best climb against what j3.py's
  figures work out to in floating point, and against the published
  figures more loosely. And it checks turns banked left and right, with
  no rudder, against the turn the lift's sideways part makes, worked out
  step by step from each state; no turn with the wings level; and a
  banked Cub left alone sinking, its lift's upward part short of its
  weight. The speeds are worked out for the path the pilot flies, which
  sinks a few feet a minute.
- `panel_test.py` flies a take-off, a climb, a turn, a stall and a dive,
  three steps a frame, and reads the panel back off every frame's screen:
  the numbers by their characters, the bars by their pixels, the light by
  its colour. Each must be what the state works out to in floating
  point, the numbers truncated, give or take where rounding falls on a
  boundary.

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
first step only, the frame rates disagree. With the bank turning the Cub
the wrong way, both banked turns fail; with all the lift kept upward when
banked, a banked Cub left alone does not sink; without the nose drop, the
stall never ends; with the stall ending only under zero lift, the nose
stops dropping 7.5 degrees too late; with the side stick not springing back, the
stick and the attitude checks fail. With the panel's heading a degree
short in 360, its sink drawn as climb, its light lit only once stalled or
never updated, or its airspeed 0.3% slow, the panel check fails. With the
camera rolling the wrong way, or one of its matrix's entries' signs
wrong, the camera check fails, its entries up to 204 127ths out; with the
Z80 putting one entry in another's place, 139 pixels of the first frame
differ. In the Z80's flight model, with the engine's lag a shift too far,
a step's change of speed not doubled, every product taken as positive, or
the sines taken below rather than at the nearest, 145 to 245 frames
differ; with the quarter squares' seventeenth bit dropped, one varied
flight at over 130 mph does, which no take-off reaches. In the Z80's
panel, with the airspeed redrawn every frame whether it changed or not,
246 frames fail on what was redrawn; with leading blanks drawn as zeros,
every frame; with a bar's last pixel lost, 451; with the sink drawn as
climb, 85; with everything drawn on the first screen alone, 232. Without the objects' centres put right, they are 0.85 pixels out
on average and up to 2.5; without it on the Z80 alone, 48 pixels of the
first frame differ.

## Not done

The stages still to come, in order, are this repository's sub-issues:

- touchdowns, landings and crashes;
- the chase view;
- the whole world;
- each stage again in Z80;
- sound on the AY.

Some limits so far:

- The Spectrum version's flight model takes about 12% of its time on the
  ground and 24% in the air, and its frame rate is well short of the 8 a
  second wanted.
- In the air the attitude holds where it is left: the Cub has no
  stability of its own to bring its nose back to where it flies trimmed.
  The rudder does nothing in the air, and there is no spin, slip or
  adverse yaw. A turn's rate is worked out from the speed along the path
  rather than its level part, so it is a little slow climbing or diving.
- The air is the same at every height, so the Cub has no ceiling.
- Back on the ground after leaving it, the Cub is simply put down, its
  wings levelled. Telling a landing from a crash comes with touchdowns.
- The eye stays 7 feet above the main wheels whatever the attitude.
- Buildings are drawn see-through. Back faces come with the whole world.
- The frame is slower than the 8 frames a second wanted, partly because
  it clears the whole view every frame.
- `compute_frame` and `render_frame` follow fast3d's demo closely: the
  pool of points, the list of objects drawn, the cut lines and drawing
  each edge are much the same code. A routine in fast3d for drawing a
  world of objects could serve both. That is left until Cub's needs (back
  faces, the chase view, the 8 frames a second) say what it must do.
