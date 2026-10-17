r"""world.json against world.schema.json, and the schema against mistakes.

    .venv-win\Scripts\python.exe examples\cub\tests\world_schema_test.py

As the Filmation designer's schemas_test.py does: the world must pass, and
each deliberately broken copy of it -- a mistake someone editing it by hand
could make -- must fail, or the schema is saying nothing.
"""
import copy
import json
import sys
from pathlib import Path

import jsonschema

CUB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CUB))

import models  # noqa: E402

BREAKAGES = [
    ("a kind with no model", lambda w: w["objects"]["hangar"].__setitem__("kind", "barn")),
    ("a position past 16 bits", lambda w: w["objects"]["hangar"].__setitem__("x", 65536)),
    ("a negative position", lambda w: w["objects"]["hangar"].__setitem__("z", -1)),
    ("a turn of a whole turn", lambda w: w["objects"]["hangar"].__setitem__("turn", 256)),
    ("an object with no kind", lambda w: w["objects"]["hangar"].pop("kind")),
    ("a misspelt key", lambda w: w["objects"]["hangar"].__setitem__("trun", 3)),
    ("an object named by its place in a list",
     lambda w: w.__setitem__("objects", list(w["objects"].values()))),
    ("a runway with no segments", lambda w: w["objects"]["runway"].pop("segments")),
    ("a runway of one segment", lambda w: w["objects"]["runway"].__setitem__("segments", 1)),
    ("a hangar with segments", lambda w: w["objects"]["hangar"].__setitem__("segments", 4)),
    ("no start", lambda w: w.pop("start")),
    ("a start with no heading", lambda w: w["start"].pop("heading")),
]


def main():
    world = json.loads((CUB / "world.json").read_text(encoding="utf-8"))
    schema = json.loads((CUB / "world.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    failures = [f"world.json: {e.message}" for e in validator.iter_errors(world)]
    kinds = schema["$defs"]["object"]["properties"]["kind"]["enum"]
    if sorted(kinds) != sorted(models.KINDS):
        failures.append(f"the schema's kinds {sorted(kinds)} are not models.py's {sorted(models.KINDS)}")
    for what, breakage in BREAKAGES:
        broken = copy.deepcopy(world)
        breakage(broken)
        if validator.is_valid(broken):
            failures.append(f"{what}: the schema let it through")
    for f in failures:
        print("FAIL", f)
    print(f"world_schema_test: {len(BREAKAGES)} breakages,", "ok" if not failures else f"{len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
