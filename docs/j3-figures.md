# The J-3 Cub's figures

What Cub's flight model is tuned to, where each figure comes from, and what
had to be assumed. [j3.py](../j3.py) holds them all as numbers; the flight
model derives its constants from it, and the tests their expected values.

## Sources

- **TCDS**: FAA Aircraft Specification A-691, Revision 32 (1997), the
  section for Model J3C-65. A primary source, read from the PDF on
  [Wikimedia Commons](https://upload.wikimedia.org/wikipedia/commons/8/8a/US_FAA_A-691.pdf).
- **Manual**: Piper's J3C-65 owner's manual, 1946, from the scan on
  [ManualsLib](https://www.manualslib.com/manual/4110781/Piper-J3c-65.html).
  A primary source, but the scan's text is badly garbled in places; the
  figures used are those that read clearly.
- **Secondary**: performance tables and fact sheets, such as
  [AOPA's](https://www.aopa.org/go-fly/aircraft-and-ownership/aircraft-fact-sheets/piper-j3-cub)
  and [pilotfriend's](http://pilotfriend.com/aircraft%20performance/Piper/1/1.htm).
  They disagree with each other, and are used only where no primary
  source gives a figure.

## Published

| Figure | Value | Source |
|---|---|---|
| Maximum weight | 1,220 lb | TCDS (serials 10339 and up) |
| Engine | Continental A-65, 65 hp at 2,350 rpm | TCDS |
| Static rpm, full throttle | not over 2,300 | TCDS; the manual's take-off rpm |
| Level flight and climb limit | 90 mph | TCDS |
| Wing area | 178.5 sq ft | Manual |
| Wing span | 35 ft 2.5 in | Secondary (the manual's scan reads 36 ft) |
| Stalling speed | 38 mph | Manual |
| Lift-off | "airborne at approximately 39 mph", loaded | Manual |
| Cruise | 73 mph at 2,150 rpm | Manual |
| Top speed | 87 mph | Secondary |
| Climb | 450 ft a minute | Secondary (AOPA gives 540 for the 1946 Special) |
| Take-off ground roll | 370 ft | Secondary |

## Assumed

No source gives these. Each is a guess that a J-3's shape makes
reasonable, and the tests say which results rest on them.

| Assumption | Value | Why |
|---|---|---|
| Lift slope | 0.1 a degree | A wing of the Cub's aspect ratio, about 7 |
| Zero-lift attack | -2 degrees | A cambered wing |
| Wing incidence | 2 degrees | Its angle to the fuselage |
| Span efficiency | 0.75 | For the induced drag |
| Static thrust | 320 lb | A 65 hp engine and a fixed-pitch wooden propeller |
| Idle | 550 rpm | |
| Rpm with speed | +0.6 rpm a mph | So that full throttle reaches the TCDS's 2,350 near top speed |
| Rolling friction | 0.04 | Turf |
| Brake friction | 0.30 | Enough to hold full throttle, as the Cub's start needs |
| Turning radius | 40 ft | Full rudder, with the tailwheel steering |
| Line of sight | 6 degrees below the datum | So that, tail down, the view is not all sky |
| Elevator | 8 degrees of the tailplane's attack | Full back stick holds the tail down past lift-off |
| Propwash | worth 20 mph over the tail at full rpm | |
| Tail up | 25 mph, stick central, full throttle | Sets the tail's load |
| Pitch rate | 10 degrees a second on the ground, 15 in the air | |
| Roll rate | 30 degrees a second at full stick | A Cub rolls slowly |
| Steepest bank | 60 degrees | |
| The stall's nose drop | 30 degrees a second | |
| Flying again | under 6 degrees of attack | Where the stalled wing's nose drop stops |
| Stall light | 2 degrees of attack before the stall | About 2 mph above the stalling speed |

## Worked out

From those, in [j3.py](../j3.py):

- **Maximum lift coefficient**, 1.85: the weight held at the stalling speed.
  High for the Cub's wing, which says the published 38 mph is a kind one.
- **The stall**, at 16.5 degrees of attack, from the lift slope.
- **The three-point attitude**, 13.6 degrees: tail down, the wing's attack
  lifts the weight at the manual's 39 mph. The real Cub's is nearer 11
  degrees; the difference is the same kind stalling speed.
- **Parasite drag**, 0.053: at top speed, full throttle's thrust (65 hp at
  a propeller efficiency of 0.75) balances the drag.
- **The thrust's fall with speed**, 1.4 lb a mph, from the same balance.
- **The tail's load**, from the tail coming up at 25 mph.
- **The stall light**, at 14.5 degrees of attack: on at 40.2 mph slowing
  level.

So the stalling speed, the top speed, the 39 mph lift-off and the tail
coming up at 25 mph are what the model was tuned to; the tests of those
check the fixed-point stepping and rounding, not the model.

The rest checks against figures it was not tuned to. Full throttle climbs
at 435 ft a minute at 57 mph, against the published 450. A take-off held
tail down lifts off after 376 ft, against the published 370. At the
throttle that turns the engine at the manual's cruise r.p.m., 2,150, the
Cub cruises at 79 mph, against the manual's 73: what the propeller and
the drag that make the top speed come to there (77 worked out in floating
point, for level flight). The manual's figures would want more drag or
less thrust at cruise than at full throttle; the model has neither.
