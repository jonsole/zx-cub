"""The keys held, as bits of the word a frame is given: what the keyboard,
the joystick or a test script presses."""

THROTTLE_UP = 0x0001            # the throttle stays where it is left
THROTTLE_DOWN = 0x0002
RUDDER_LEFT = 0x0004
RUDDER_RIGHT = 0x0008
BRAKES = 0x0010                 # held; the first press takes the parking brake off
STICK_BACK = 0x0020             # the stick springs back to the middle when let go
STICK_FORWARD = 0x0040
STICK_LEFT = 0x0080             # (rolling comes with flying)
STICK_RIGHT = 0x0100
