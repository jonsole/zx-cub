"""Cub's models: vertices as signed bytes in feet, x right, y up, z forward
along the object's turn, the object's position at (0, 0, 0) on the ground;
and edges between them.

KINDS are what world.json can place. Each is one model, but for the
runway, which is longer than a model can be (254 feet at most) and is
placed as one object and built of segments end to end (game.load_world):
the first draws the runway's near end, the last its far end, and every one
its sides and a centreline dash.

None has faces yet, so each is drawn whole (fast3d's model_block with no
parts); buildings lose their back edges in a later stage.
"""
from fast3d import build

RUNWAY_HALF_WIDTH = 30          # feet: the runway is 60 wide
RUNWAY_HALF_LENGTH = 125        # and built of segments 250 long
RUNWAY_DASH = 40                # half a centreline dash's length


def runway_segment(near_end: bool, far_end: bool):
    w, h = RUNWAY_HALF_WIDTH, RUNWAY_HALF_LENGTH
    near_left, near_right, far_left, far_right = (-w, 0, -h), (w, 0, -h), (-w, 0, h), (w, 0, h)
    edges = [(near_left, far_left), (near_right, far_right), ((0, 0, -RUNWAY_DASH), (0, 0, RUNWAY_DASH))]
    if near_end:
        edges.append((near_left, near_right))
    if far_end:
        edges.append((far_left, far_right))
    return edges


def hangar():
    """60 feet across (x), 50 deep (z), walls 20 high and a ridge at 30
    running front to back: gable ends front and back."""
    w, d, wall, ridge = 30, 25, 20, 30
    edges = []
    for z in (-d, d):
        floor_l, floor_r, eave_l, eave_r, top = (-w, 0, z), (w, 0, z), (-w, wall, z), (w, wall, z), (0, ridge, z)
        edges += [(floor_l, floor_r), (floor_l, eave_l), (floor_r, eave_r), (eave_l, eave_r),
                  (eave_l, top), (eave_r, top)]
    for x in (-w, w):
        edges += [((x, 0, -d), (x, 0, d)), ((x, wall, -d), (x, wall, d))]
    edges.append(((0, ridge, -d), (0, ridge, d)))
    return edges


def windsock():
    """A pole 17 feet high and a sock hanging limp from it in calm air."""
    foot, top, mouth, tip = (0, 0, 0), (0, 17, 0), (0, 14, 1), (1, 8, 3)
    return [(foot, top), (top, tip), (mouth, tip), (top, mouth)]


# Every model's edges, as pairs of vertices: the runway's three segments,
# and one for each other kind.
MODELS = {
    "runway-start": runway_segment(near_end=True, far_end=False),
    "runway-middle": runway_segment(near_end=False, far_end=False),
    "runway-end": runway_segment(near_end=False, far_end=True),
    "hangar": hangar(),
    "windsock": windsock(),
}

# What world.json can place.
KINDS = ["runway", "hangar", "windsock"]


def model(name: str):
    """(vertices, edges): the vertices once each, a vertex and its mirror
    first (fast3d transforms the mirror for nothing), and the edges as pairs
    of indices into them."""
    edges = MODELS[name]
    vertices = build.paired(list(dict.fromkeys(v for edge in edges for v in edge)))
    return vertices, [(vertices.index(a), vertices.index(b)) for a, b in edges]
