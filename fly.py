r"""Flies Cub's Python model in a pygame window, drawn as the Spectrum
draws it: the screen game.frame leaves, in the Spectrum's colours, with a
border, three times the size.

    .venv-win\Scripts\python.exe examples\cub\fly.py
    .venv-win\Scripts\python.exe examples\cub\fly.py --shot cub.png   # one frame to a PNG, no window

Each frame runs the steps owed since the last, fiftieths of a second of the
wall clock, as the Spectrum's interrupt counts them. The keys:

    Q / A           throttle up / down (it stays where it is left)
    Z / X           rudder left / right
    Space           brakes (the first press takes the parking brake off)
    cursor keys     the stick: down pulls back, up pushes forward, left and
                    right roll (it springs back to the middle when let go)
    Escape          close the window

The panel shows the airspeed, the height, the heading, the throttle, the
climb and the stall light; the window's title adds the engine's r.p.m.
and what the Cub is doing.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import flight  # noqa: E402
import game  # noqa: E402
import keys  # noqa: E402
from fast3d import model  # noqa: E402

SCALE = 3
BORDER = 24                         # pixels of border round the screen, before scaling
# The Spectrum's colours, not bright: black, blue, red, magenta, green, cyan, yellow, white.
COLOURS = [(0, 0, 0), (0, 0, 0xD7), (0xD7, 0, 0), (0xD7, 0, 0xD7),
           (0, 0xD7, 0), (0, 0xD7, 0xD7), (0xD7, 0xD7, 0), (0xD7, 0xD7, 0xD7)]
BORDER_COLOUR = 1                   # blue, as cub.s sets it


# Eight pixels' RGB bytes, by the screen's byte and its attribute's colours:
# made as they are first needed.
EIGHT = {}


def eight(bits: int, attribute: int) -> bytes:
    key = (bits, attribute & 0x3F)
    if key not in EIGHT:
        ink, paper = bytes(COLOURS[attribute & 7]), bytes(COLOURS[(attribute >> 3) & 7])
        EIGHT[key] = b"".join(ink if bits & (0x80 >> i) else paper for i in range(8))
    return EIGHT[key]


def to_rgb(screen: bytes) -> bytes:
    """The screen as 256 by 192 RGB pixels, ink where a pixel is set."""
    rows = []
    for y in range(192):
        line = model.screen_address(0, y) - 0x4000
        attributes = 6144 + 32 * (y >> 3)
        rows.append(b"".join(eight(screen[line + i], screen[attributes + i]) for i in range(32)))
    return b"".join(rows)


def surface(pygame, screen: bytes):
    image = pygame.Surface((256 + 2 * BORDER, 192 + 2 * BORDER))
    image.fill(COLOURS[BORDER_COLOUR])
    image.blit(pygame.image.frombuffer(to_rgb(screen), (256, 192), "RGB"), (BORDER, BORDER))
    return pygame.transform.scale(image, (image.get_width() * SCALE, image.get_height() * SCALE))


def keys_held(pygame) -> int:
    held = pygame.key.get_pressed()
    word = 0
    for key, bit in ((pygame.K_q, keys.THROTTLE_UP), (pygame.K_a, keys.THROTTLE_DOWN),
                     (pygame.K_z, keys.RUDDER_LEFT), (pygame.K_x, keys.RUDDER_RIGHT),
                     (pygame.K_SPACE, keys.BRAKES), (pygame.K_DOWN, keys.STICK_BACK),
                     (pygame.K_UP, keys.STICK_FORWARD), (pygame.K_LEFT, keys.STICK_LEFT),
                     (pygame.K_RIGHT, keys.STICK_RIGHT)):
        if held[key]:
            word |= bit
    return word


def readout(state) -> str:
    where = ("parked" if flight.parked(state) else "tail up" if flight.tail_up(state)
             else "tail down" if flight.on_ground(state) else "stalled" if flight.stalled(state) else "flying")
    return f"Cub   {state.rpm:4d} rpm   {where}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--shot", help="draw the first frame to this PNG and stop, with no window")
    args = ap.parse_args()
    if args.shot:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame
    pygame.init()
    world = game.load_world()
    state = game.start_state(world)
    state, screen = game.frame(state, world, 0, 0)
    if args.shot:
        pygame.image.save(surface(pygame, screen), args.shot)
        print(f"Wrote {args.shot}")
        return
    window = pygame.display.set_mode(((256 + 2 * BORDER) * SCALE, (192 + 2 * BORDER) * SCALE))
    pygame.display.set_caption("Cub")
    last = pygame.time.get_ticks()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                pygame.quit()
                return
        window.blit(surface(pygame, screen), (0, 0))
        pygame.display.flip()
        pygame.display.set_caption(readout(state))
        now = pygame.time.get_ticks()
        steps, last = (now - last) // 20, last + (now - last) // 20 * 20
        state, screen = game.frame(state, world, keys_held(pygame), steps)


if __name__ == "__main__":
    main()
