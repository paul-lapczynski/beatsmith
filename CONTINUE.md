# Continue here

A handoff for any coding agent (Claude Code, OpenAI Codex, ...) picking up
BeatSmith. Read this first, then the [README](README.md). Last updated
2026-10-25.

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
- **No open PRs.**

## Next tasks, in order

1. **Release 1.1.0.** `main` has #31 since 1.0.0. Check the latest
   Release workflow run on `main` is green, then tag it (see "Releasing").
   Check the add-on packs are attached to the release and that the app
   downloads them from it. Write short release notes.
2. **#30: Changesets (or release-please) for versions and release notes.**
   The issue has the plan and the open questions. Keep the existing
   `release.yml` doing the builds; the new tool only bumps the version,
   writes the changelog and pushes the `vX.Y.Z` tag.
3. **#28: Follow the melody**, for songs where the tune is an instrument
   (piano in Abyss). Brainstorm issue: weigh the ideas in it and propose a
   design to Paul before building. Starting points: `_stem_melody` and
   `follow_curve` in `stepgen.py`.
4. **#32: GPU verse detection on Apple Silicon (mlx-whisper).** Low payoff,
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

## Run and check

```bash
python -m pip install -r requirements.txt -r requirements-app.txt
python stepgen.py "Some Song.mp3" --artist "Someone" --out songs/
python beatsmith_app.py          # or run_app.bat on Windows
```

There is no automated test suite. Check a change by:
- generating charts for a few songs and comparing the stats and charts
  before and after (`chartstats.py`, the app's stats panel);
- for timing or editor changes, playing the result in StepMania (Paul plays
  them; ask him to);
- the Release workflow, which builds both installers on every PR that
  touches code. A PR must be green before Paul merges.

Song files are local only. Paul's test songs sit in the repo folder on his
PC but are gitignored; never add them.

## Releasing

Releases are made from `main` by a tag; the workflow builds and publishes.

```bash
git switch main
git pull
git tag v1.1.0
git push origin v1.1.0
```

Tag only a commit whose `main` build is green. Then edit the GitHub release
to add short notes. Versions follow semver (`v1.1.0` for features, `v1.0.1`
for fixes).

## Working style

- One PR per change, on a branch named like `fix/...`, `addons/...`,
  `docs/...`. Small and focused.
- Open an issue for ideas Paul wants to come back to.
- When unsure what Paul wants, ask before building; propose a plan for
  anything large.
