r"""Flies Cub's Python model in a pygame window, drawn as the Spectrum
draws it: the screen game.frame leaves, in the Spectrum's colours, with a
border, three times the size.

    .venv-win\Scripts\python.exe examples\cub\fly.py
    .venv-win\Scripts\python.exe examples\cub\fly.py --shot cub.png   # one frame to a PNG, no window

Each frame runs the steps owed since the last, fiftieths of a second of the
wall clock, as the Spectrum's interrupt counts them. Nothing answers the
keys yet but Escape, which closes the window.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import game  # noqa: E402
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
        now = pygame.time.get_ticks()
        steps, last = (now - last) // 20, last + (now - last) // 20 * 20
        state, screen = game.frame(state, world, 0, steps)


if __name__ == "__main__":
    main()
