# Cub

A Piper Cub flight simulator for the 128K ZX Spectrum, drawn with the
fast3d engine: take off from a runway, fly over farms, a village and woods
in a world that wraps, and land again, from the cockpit or chasing the Cub.
The flying is a simplified physical flight model, tuned in Python and then
built in Z80 that matches the Python frame for frame.

Nothing flies yet. What exists is the plan and the words for it:

- [GLOSSARY.md](GLOSSARY.md): Cub's domain language.
- [docs/adr/](docs/adr/): the decisions made, starting with why Cub has its
  own flight model rather than the Aviator port's.
- The plan and its stages are this repository's issues: the parent issue
  describes the whole game, and each stage is a sub-issue.

## Where it lives

Cub is developed inside a checkout of
[zx-spectrum-emulator](https://github.com/jonsole/zx-spectrum-emulator),
where it is the `examples/cub` submodule. It needs things beside it there,
by relative path: the fast3d engine in `examples/fast3d`, the Python the
examples share in `examples/scripts`, the emulator's snapshot probe in
`cpp-core` to check the Z80 against the Python, and sjasmplus in `tools`. A
clone of this repository on its own does not build.

```
git clone --recurse-submodules https://github.com/jonsole/zx-spectrum-emulator
cd zx-spectrum-emulator/examples/cub
```
