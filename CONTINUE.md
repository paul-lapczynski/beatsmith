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

- **1.1.2 is published.** Release Please prepares version PRs after green
  main builds. Paul reviews/merges; tag builds publish the installers and
  four add-on packs only after all required builds pass.
- Installer overlap protection, form-wheel protection, forced-BPM validation
  and Windows add-on cleanup are merged (#40/#41). Existing older
  uninstallers do not gain cleanup until updated. A mixed EXE/MSI install
  requires removing both copies before installing one current copy.
- **#28: Lead instrument mode** is implemented on this branch after Paul
  approved the explicit source-choice design on October 28. Singing remains
  the default. Lead uses real attack candidates from the other stem, favors
  selected phrase starts, traces losses through later passes and includes
  final attack alignment in groove-try selection. It does not transcribe
  musical pitches. See README for controls and limits.
- Local validation covers synthetic attacks/sustains/silence, all three
  difficulties across six short song clips, baseline compatibility, and
  UI/settings behavior. Detector alignment does not establish musical
  accuracy. Human-marked audible phrase coverage and Paul's comparison play
  tests remain acceptance gates before shipping #28.

## Remaining work

1. Finish #28 acceptance and PR review. Paul plays the short Singing/Lead
   pairs in the local **BeatSmith Lead Preview** StepMania group. Do not
   describe the mode as musically validated from its own detector score.
2. Verify clean installed-app download, generation/playback and uninstall
   behavior after the final release. Existing charts accidentally generated
   at 1 BPM need regeneration using auto/detect BPM.
3. Paul intends to wrap the project for now after #28. **#32 Mac GPU verse
   detection stays parked.** Do not start it unless he asks.

Known limits: one constant BPM per song, bar start can land half a bar off,
no triplets or mines, no section-aware styling. Pitch-aware transcription
is outside the approved bounded lead-rhythm mode.

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

Installer, UI and melody checks run with:

```bash
python -m unittest discover -s packaging -p "test_*.py"
```

Both installer jobs run them. PR #34 also passed Actionlint and ten isolated
workflow scenarios. These do not replace a live publication check.
Lead-mode timing and safety have synthetic regression checks. Also check chart changes by:
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
