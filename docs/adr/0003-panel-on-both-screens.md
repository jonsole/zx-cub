# The panel is drawn on both screens, and the state keeps what it shows

The view is drawn on the screen not being shown, and the two screens take
turns. The panel could be drawn the same way, but then each screen's panel
would be two frames behind the Cub, and redrawing only what changed would
mean keeping what each screen's panel shows, twice over.

Instead, the game state keeps what the panel shows: the airspeed, height
and heading drawn, the bars' lengths and the stall light. A frame works
out the panel's values from the Cub's state, compares them with what is
kept, and redraws only the parts that differ, on both screens at once:
the 128K keeps both in memory all the time, bank 5's at `$4000` and bank
7's at `$C000`. The view never reaches the panel's rows, so nothing else
draws there, and the panel is the same whichever screen is shown.

Because what the panel shows is part of the game state, the Python model
keeps it too, and the frame comparison checks it like the rest of the
state. At the start of a flight it holds values no panel can show, so the
first frame draws every part.

## Considered

- **Drawing the whole panel every frame.** Simplest, but the numbers alone
  are 11 characters of 8 bytes each, and the frame is already slower than
  the 8 frames a second wanted.
- **A panel on each screen, each with its own record.** Each would lag the
  Cub by two frames, and the state would carry two copies of what the
  panel shows. The panel drawn on the shown screen changes up to a frame
  before the view does, which at 8 frames a second nobody sees.
