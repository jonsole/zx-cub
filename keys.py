"""The keys held, as bits of the word a frame is given: what the keyboard,
the joystick or a test script presses."""

THROTTLE_UP = 0x0001            # the throttle stays where it is left
THROTTLE_DOWN = 0x0002
RUDDER_LEFT = 0x0004
RUDDER_RIGHT = 0x0008
BRAKES = 0x0010                 # held; the first press takes the parking brake off
STICK_BACK = 0x0020             # the stick springs back to the middle when let go
STICK_FORWARD = 0x0040
STICK_LEFT = 0x0080             # the stick to the side: rolls the Cub in the air
STICK_RIGHT = 0x0100
VIEW = 0x0200                   # the cockpit or the chase view: kept, and acts from the chase view's stage
NEW_FLIGHT = 0x0400             # back to the runway: kept, and acts from the touchdowns' stage
