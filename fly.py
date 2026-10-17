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
    cursor keys     the stick: down pulls back, up pushes forward
    Escape          close the window

There is no panel yet, so the window's title shows the speed, the engine,
the throttle and the height.
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


def to_pixels(screen: bytes) -> list:
    """The screen as rows of 256 colours, ink where a pixel is set."""
    rows = []
    for y in range(192):
        row = []
        for x in range(256):
            attribute = screen[6144 + 32 * (y >> 3) + (x >> 3)]
            lit = screen[model.screen_address(x, y) - 0x4000] & (0x80 >> (x & 7))
            row.append(COLOURS[attribute & 7] if lit else COLOURS[(attribute >> 3) & 7])
        rows.append(row)
    return rows


def surface(pygame, screen: bytes):
    image = pygame.Surface((256 + 2 * BORDER, 192 + 2 * BORDER))
    image.fill(COLOURS[BORDER_COLOUR])
    for y, row in enumerate(to_pixels(screen)):
        for x, colour in enumerate(row):
            image.set_at((BORDER + x, BORDER + y), colour)
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
             else "tail down" if flight.on_ground(state) else "flying")
    return (f"Cub   {flight.mph(state):5.1f} mph   {state.rpm:4d} rpm   throttle {100 * state.throttle // 255:3d}%   "
            f"{state.y / 65536:6.1f} ft   {where}")


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
