# AGENTS.md

Cub is the `examples/cub` submodule of zx-spectrum-emulator, and is worked
on from inside that checkout: its AGENTS.md is the guide to building,
testing and the house style, and applies here too. This file says only what
is different about this repository.

- **Issues live here**, in `jonsole/zx-cub`, not in the emulator's
  repository. From the emulator's root, `gh` talks to the emulator's
  issues, so name this one: `gh issue view 1 -R jonsole/zx-cub`. The parent
  issue is the whole game; its sub-issues are the stages. The triage labels
  are the emulator's: `needs-triage`, `needs-info`, `ready-for-agent`,
  `ready-for-human`, `wontfix`.
- **Changes to fast3d go into the emulator's repository**, in
  `examples/fast3d`, for every program that uses it -- not into a copy
  here. So do changes to the Python the examples share, in
  `examples/scripts`.
- **Commits here are this repository's.** After committing in
  `examples/cub`, the emulator's repository records the new submodule
  commit separately, when asked to.
- The domain language is [GLOSSARY.md](GLOSSARY.md), and decisions go in
  [docs/adr/](docs/adr/).
