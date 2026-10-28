# Continue here

A handoff for any coding agent (Claude Code, OpenAI Codex, ...) picking up
BeatSmith. Read this first, then the [README](README.md). Last updated
2026-10-27.

**If you can read Paul's private repo `paul-lapczynski/rhythm-agent`, start
there:** its `AGENTS.md` and its issues are the up-to-date task list,
and when you finish, update the issue and its history. This file is the
fallback for when you can't.

## What BeatSmith is

A desktop app and command line tool that turns a song into a StepMania `.sm`
file with Easy, Medium and Hard `dance-single` charts that follow the music.
Python; the app is PySide6 (`beatsmith_app.py`), the generator is
`stepgen.py`. Windows and macOS installers are built by GitHub Actions.

## Hard rules

1. **Never push to `main`.** Every change goes on its own branch and through a
   pull request. Paul reviews and squash-merges; never merge a PR yourself.
2. **Never delete a repository**, and never force-push `main` or delete
   someone else's branch.
3. **Never commit songs, audio, artwork, Konami charts or fan charts.** That
   means no `.mp3/.ogg/.wav/.wma/...`, nothing from `songs/`, `song-data/`,
   `examples/`, `calibration/`, `shorten-tests*/` or `Step Mania/`, and no
   cover art. `.gitignore` covers most of this; check `git status` before
   every commit and stage files by name, not with `git add -A`.
4. **Don't publish `training/`** and don't describe how the AI model was
   made, in code, docs, commit messages, PRs or issues. `training/` is kept
   local (gitignored). Using the shipped model (`models/`, `ai_assist.py`) is
   fine to talk about.
5. Write docs, PRs and release notes in plain, short sentences for a
   non-technical reader. Start each PR body with the attribution block the
   existing PRs use.

## Current state

- **1.0.0 is released** (tag `v1.0.0`, GitHub release with Windows `.msi`
  and `.exe` and a macOS `.dmg`).
- **PR #31 is merged** (add-ons as ready-made packs downloaded from the
  release, Windows and Mac; closes #29). It is on `main` but not released.
  Its `main` build passed. The packs are built by
  `packaging/addon_pack.py` and attached to each release by `release.yml`.
- **PR #34 is merged** (Release Please and shared installer versions).
  Paul approved Release Please, saved `RELEASE_PLEASE_TOKEN`, and approved
  enabling Actions PR creation. The first Prepare release run succeeded
  and opened **PR #35, release 1.1.0**. All four build checks on #35 passed.
  Verify current PR and workflow state before continuing; this is a snapshot.
- **1.1.0 is not published yet.** The first automated tag/publication path
  and the installed app's version-specific pack download still need checking.

## Next tasks, in order

1. **Finish release 1.1.0 through PR #35.** Paul reviews and merges the
   version PR. Check its notes include the ready-made add-on packs from #31;
   the initial generated notes only list #34. After merging, verify the
   main build, Prepare release, tagged builds and publication. Check the
   release has one MSI, one EXE, one DMG and four add-on packs, then verify
   an installed app downloads its version's pack. Do not mark this done just
   because PR builds pass. See "Releasing" below.
2. **#28: Follow the melody**, for instrumental tunes such as piano in
   Abyss. A [concrete design and acceptance plan](https://github.com/paul-lapczynski/beatsmith/issues/28#issuecomment-6436408296)
   is posted and awaits Paul's approval before implementation. It proposes
   an explicit Lead instrument source, controlled attack placement, and
   measuring which phrase starts survive later passes. Production behavior
   is unchanged. `_stem_melody` and `follow_for` are the starting points.
   Explicit section overrides already bypass the automatic singing cap;
   removing that cap alone is not the whole feature.
3. **#32: GPU verse detection on Apple Silicon (mlx-whisper) stays parked.** Low payoff,
   real risks (listed in the issue). Only do it if Paul asks; if so, compare
   the sections both engines give on a few songs first.

Smaller known gaps (README, "Limits of this version"): one constant BPM per
song, bar start can land half a bar off, no triplets or mines, no
section-aware styling.

## Layout

| Path | What it is |
|---|---|
| `stepgen.py` | the generator: beats, onsets, sections, step placement, `.sm` writer |
| `beatsmith_app.py` | the app window (queue, settings tabs, editor tab) |
| `chart_editor.py` | the chart editor |
| `groove.py`, `layout.py`, `verses.py`, `chartstats.py` | feel passes, foot layout, repeated sections, stats |
| `stems.py`, `lyrics.py`, `accel.py`, `addons.py` | vocal separation, verse detection (faster-whisper), GPU choice, opt-in add-on packs |
| `ai_assist.py`, `models/` | the optional AI assist model (ONNX) |
| `artwork.py` | song pictures |
| `profiles/*.toml`, `patterns.toml` | play styles and step patterns |
| `docs/` | GitHub Pages site and `DIALS.md` (every slider, with pictures) |
| `packaging/` | installer builds; see `packaging/BUILD.md` |
| `.github/workflows/release.yml` | builds Windows and Mac on PRs and `main`, publishes on tags |
| `.github/workflows/release-please.yml` | prepares version PRs and draft releases after successful current-main builds |
| `version.txt`, `packaging/version.py` | shared source version and installer/tag validation |
| `packaging/RELEASING.md` | release automation setup, review flow and recovery |

## Run and check

```bash
python -m pip install -r requirements.txt -r requirements-app.txt
python stepgen.py "Some Song.mp3" --artist "Someone" --out songs/
python beatsmith_app.py          # or run_app.bat on Windows
```

Installer versions and release sequencing have ten automated checks:

```bash
python -m unittest discover -s packaging -p "test_*.py"
```

Both installer jobs run them. PR #34 also passed Actionlint and ten isolated
workflow scenarios. These do not replace a live publication check.
There is no general chart-generation test suite. Check chart changes by:
- generating charts for a few songs and comparing the stats and charts
  before and after (`chartstats.py`, the app's stats panel);
- for timing or editor changes, playing the result in StepMania (Paul plays
  them; ask him to);
- the Release workflow, which builds both installers on every PR that
  touches code. A PR must be green before Paul merges.

Song files are local only. Paul's test songs sit in the repo folder on his
PC but are gitignored; never add them.

## Releasing

Use the reviewed version PR. Release Please updates `version.txt`, the
manifest and changelog. After Paul merges it and the current-main build
passes, automation creates a draft release and tag. The Release workflow
builds that tag and publishes only after every required file is present.
Never merge the version PR or publish manually on Paul's behalf.

Use `feat:` or `fix:` squash-merge titles for future changes so the next
version and notes can be inferred. See [packaging/RELEASING.md](packaging/RELEASING.md)
for setup, manual recovery and token renewal. The token's presence has been
verified and the first version PR was generated; never put its value here
or in a log. Manual tags are a fallback and must agree with `version.txt`.

## Working style

- One PR per change, on a branch named like `fix/...`, `addons/...`,
  `docs/...`. Small and focused.
- Open an issue for ideas Paul wants to come back to.
- When unsure what Paul wants, ask before building; propose a plan for
  anything large.
