# Continue here

A handoff for any coding agent (Claude Code, OpenAI Codex, ...) picking up
BeatSmith. Read this first, then the [README](README.md). Last updated
2026-10-28.

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

- **1.1.2 is published.** It includes the installer overlap guard, form-wheel
  protection, forced-BPM validation and Windows add-on uninstall cleanup.
  Release Please prepares version PRs after successful current-main builds;
  Paul reviews and merges. Tagged builds publish only after all required
  installers and add-on packs are present.
- **#28 is closed as not planned.** Paul rejected the proposed lead-instrument
  mode after play testing. Draft #43 was closed without merging. Do not
  resume it or copy incidental changes from that branch without a new
  request. The existing released experimental melody controls are unchanged.
- **#32 Mac GPU verse detection stays parked.** Feature work is wrapped for
  now. Paul approved documentation/screenshots and repository organization, not
  another app feature.
- The public user documentation is [README](README.md),
  [the app guide](docs/APP_GUIDE.md), [AI Usage](AI_USAGE.md),
  [the control reference](docs/DIALS.md) and
  [the command-line reference](docs/COMMAND_LINE.md).
- AI transparency must describe actual local/cloud behavior. Keep private
  model-making details out of public files. The separate LLM review tool is
  unfinished and is not part of normal desktop generation.

## Remaining acceptance

Verify the installed app's add-on download, chart generation/playback and
uninstall behavior on a clean installation. Current Windows uninstallers
remove add-ons; already-installed older uninstallers retain their old behavior.
A mixed EXE/MSI installation requires removing both before installing one
current copy. Charts made at an accidental 1 BPM need regeneration with
BPM on detect/auto.

These checks are separate from the canceled melody experiment. Check current
GitHub state before acting; this document is a dated snapshot. Paul reviews
and merges application and release PRs.

## Layout

| Path | What it is |
|---|---|
| `src/beatsmith/stepgen.py` | the generator: beats, onsets, sections, step placement, `.sm` writer |
| `src/beatsmith/beatsmith_app.py` | the app window (queue, settings tabs, editor tab) |
| `src/beatsmith/chart_editor.py` | the chart editor |
| `groove.py`, `layout.py`, `verses.py`, `chartstats.py` | feel passes, foot layout, repeated sections, stats |
| `stems.py`, `lyrics.py`, `accel.py`, `addons.py` | vocal separation, verse detection (faster-whisper), GPU choice, opt-in add-on packs |
| `ai_assist.py`, `models/` | the optional AI assist model (ONNX) |
| `artwork.py` | song pictures |
| `profiles/*.toml`, `patterns.toml` | play styles and step patterns |
| `docs/` | App guide, CLI/control references, real app screenshots and Pages site |
| `packaging/` | installer builds; see `packaging/BUILD.md` |
| `.github/workflows/release.yml` | builds Windows and Mac on PRs and `main`, publishes on tags |
| `.github/workflows/release-please.yml` | prepares version PRs and draft releases after successful current-main builds |
| `version.txt`, `packaging/version.py` | shared source version and installer/tag validation |
| `packaging/RELEASING.md` | release automation setup, review flow and recovery |

Root Python entry points remain compatibility launchers. See
[the current repository layout](docs/REPOSITORY_LAYOUT.md) for canonical
module, worker, tool and test locations. User-data/resource locations are unchanged.

## Run and check

```bash
python -m pip install -r requirements.txt -r requirements-app.txt
python stepgen.py "Some Song.mp3" --artist "Someone" --out songs/
python beatsmith_app.py          # or run_app.bat on Windows
```

Existing installer, tempo and form-control checks run with:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Both installer jobs run them. Windows CI also exercises the compiled MSI
and EXE: installation/update, startup and uninstall/add-on cleanup. These
checks do not replace installed-app acceptance and play testing.
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
