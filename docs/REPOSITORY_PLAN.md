# Repository cleanup plan

[Home](../README.md) · [App guide](APP_GUIDE.md)

**Recommendation:** organize documentation and development-only material
first. Move runtime code only through separate, tested changes. This is a
proposal, not authorization to move files or change the released app.

The current documentation PR does not move runtime modules, models,
profiles, installer scripts or user data. No folder layout can guarantee
compatibility by itself; the checkpoints below are the release gates.

## What is actually mixed together

The tracked root contains the desktop app, editor, generator, audio helpers,
optional integrations and developer tools as sibling Python modules. Tests
live under `packaging/` even when they test tempo or form controls. User
instructions, research measurements and developer instructions have shared
the README. Build scripts and their generated outputs share `packaging/`.

A working checkout may also contain ignored songs, exports, cached stems,
calibration runs, virtual environments and other experiments. Those local
folders are not the same thing as the tracked repository. Inventory them
separately; never move or delete them just to make Git look tidy.

## Proposed end state

```text
beatsmith/
├── README.md                    # App overview and quick start
├── AI_USAGE.md                  # Public AI/data-flow disclosure
├── CHANGELOG.md
├── LICENSE
├── AGENTS.md / CONTINUE.md       # Contributor rules and handoff
├── version.txt                  # Keep release contracts stable
├── requirements*.txt            # Keep dependency entry points initially
├── run_app.bat                  # Existing user launcher
├── beatsmith_app.py             # Small compatibility launcher, later
├── stepgen.py                   # Existing CLI compatibility launcher, later
├── chart_editor.py              # Standalone-editor compatibility launcher, later
├── src/beatsmith/               # Runtime modules, moved without redesign
│   ├── app.py
│   ├── editor.py
│   ├── generation.py
│   ├── ...audio/chart helpers...
│   └── resources.py             # One source/frozen resource resolver
├── resources/                   # Models, profiles and default patterns, later
├── tests/
│   ├── unit/
│   ├── integration/
│   └── installers/              # Disposable-runner-only Windows tests
├── tools/
│   ├── chartstats.py
│   ├── llm_review.py
│   └── ...development utilities...
├── docs/                        # App/CLI guides, site, screenshots, tool notes
├── benchmarks/                  # Dial-test scripts and measurements
├── packaging/                   # Existing build entry points kept initially
├── branding/
└── .github/workflows/
```

This is an eventual shape, not a request to create every folder now.
Do not split the generator's algorithms into new subsystems while moving
them. A mechanical move and a behavior redesign should be separate reviews.

Keep source songs, generated audio/charts, add-on environments and private
material outside the tracked structure. Do not relocate an existing user's
files as part of a code-organization PR. Do not move an installed private
Python environment: it can contain paths that depend on its location.

## Stage 1: documentation and inventory

Complete the app-first README, illustrated app guide, command reference and
AI disclosure. Keep user docs distinct from old benchmark reports and
unfinished tools. Update the contributor handoff so canceled work is not
mistaken for the next task.

Before any later move, record tracked files separately from ignored local
data and generated build output. Establish a known-good commit and a
reproducible synthetic chart fixture with fixed settings and seed. Store
temporary outputs outside Git. **This is the recommended stopping point
while feature work is wrapped.**

## Stage 2: developer-only files

Move tests from `packaging/test_*.py` into `tests/`, and group installer-only
checks together. Update both build scripts and the workflow's discovery
commands in the same PR. Verify that every previous test is still discovered;
an empty or skipped suite is not a successful migration.

Move dial-test scripts/reports into `benchmarks/` only after finding their
relative-path dependencies and updating documentation/site links. Move
standalone review/inspection tools into `tools/` with compatibility launchers
for documented root commands where needed. Avoid moving the packaging build
entry points, model or runtime modules in this stage.

**Gate:** previous unit checks still run, developer commands start from a
fresh checkout, documentation links resolve, and relevant CI runs. Confirm
which new paths trigger builds; the workflows currently treat docs-only
changes differently from runtime and packaging changes.

## Stage 3: centralize resource paths before moving modules

Several files currently find resources beside `__file__`; frozen builds use
`sys._MEIPASS`. Introduce one resource resolver while keeping the existing
physical layout. Cover default patterns, profiles, the bundled model,
icons, version information and shipped README/help resources.

Keep **bundled resources**, **user app data**, **output songs** and
**downloaded add-ons** as distinct locations. In particular, `layout.py`
currently places source-run data beside the source checkout. Moving that
module must not silently switch existing `song-data/` to a new location.

The add-on Python executes plain `stems.py` and `lyrics.py` scripts in
isolated mode. Preserve those worker entry points and their plain-Python
dependencies. They must not accidentally import compiled app libraries
from a different Python runtime.

**Gate:** source and frozen resource lookups pass; a source app and the
packaged app can find profiles/model/worker scripts; old user data paths
are unchanged. Do not combine this with model, Python-version or dependency
upgrades.

## Stage 4: move runtime modules into a package

Move modules into `src/beatsmith/` in small groups, retaining their internal
behavior. Settle package imports explicitly rather than adding more
`sys.path` patches. Add a standard package entry point only when its
dependency and frozen-build behavior is verified.

Keep the old root commands working during the transition: `run_app.bat`,
`python beatsmith_app.py`, `python stepgen.py …` and
`python chart_editor.py …`. Preserve the frozen executable's
`--run-stepgen` and add-on dispatch flags. Update PyInstaller's entry script,
hidden imports and bundled data together with each affected move.

Keep compatibility launchers small. Do not leave two competing copies of
the generator or app implementation.

**Gate for each runtime PR:**

1. Existing unit and UI checks pass with the same discovery count.
2. Source CLI, GUI launch and standalone editor start.
3. The fixed-seed synthetic fixture has the same chart timings, panels,
   holds, tempo and offset. Compare actual charts, not just a private score.
4. Profiles, saved settings, old song data, compare files and regeneration work.
5. Optional worker scripts run in the separate add-on Python, including a
   cached-add-on case, without downloading packages merely to pass a test.
6. Windows and Mac frozen builds start and perform a short generation/editor
   check; `--help` alone does not test the whole app.
7. Disposable Windows CI exercises MSI and EXE install/update/uninstall,
   including the legacy-overlap guard and add-on preservation/cleanup.
8. A short manual play test confirms the saved chart remains usable.

## Stage 5: optional resource and packaging consolidation

Only after the package move is stable, consider grouping models, patterns
and profiles into `resources/` and separating Windows/Mac build helpers.
Use the resource resolver from Stage 3. Keep old build entry scripts as
delegating wrappers until automation and documented commands are updated.

Release Please currently expects root `version.txt` and its manifest/config;
leave them there unless a separate release-configuration change is tested.
Review PyInstaller data destinations, artifact globs, add-on worker paths,
workflow filters and installer upgrade identity before approving a move.
Avoid another EXE/MSI or runtime-layout collision.

**Gate:** repeat the relevant frozen-build, installer and release-artifact
checks. Verify the generated installer/add-on names and version agreement.
Do not publish a release just to test whether the new tree works.

## Rollback and scope

Each stage is its own PR from a known-good base. Keep a before/after path
map in the PR, avoid behavior changes, and let failed checks stop the next
stage. Revert that stage's code commit if needed; do not restore software
by deleting or overwriting user song/data folders. A code revert cannot
undo an unsafe user-data migration, which is why this plan excludes one.

Recommend Stage 1 now, Stage 2 as a small follow-up if desired, and defer
the runtime/resource moves until there is a reason to resume development.
