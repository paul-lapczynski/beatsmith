# Command-line reference

[Home](../README.md) · [App guide](APP_GUIDE.md) · [AI Usage](../AI_USAGE.md)

The installers are the simplest way to use BeatSmith. These commands are for
a source checkout, batch work and exact settings. Run them from the repository.
Python 3.12 is the package-build version.

## Install source dependencies

```sh
python -m pip install -r requirements.txt
```

For the desktop app as well:

```sh
python -m pip install -r requirements-app.txt
python beatsmith_app.py
```

`run_app.bat` launches the source app on Windows. Source installs handle
optional add-ons differently from the packaged app: packages/models are
installed into a private add-on environment rather than downloading the
release's ready-made pack. See [AI Usage](../AI_USAGE.md).

## Generate charts

```sh
python stepgen.py "My Song.mp3" --artist "Someone" --out "songs/BeatSmith"
python stepgen.py "My Song.mp3" --out "C:/Games/OutFox/Songs/BeatSmith" --target Easy=3 --target Medium=6 --target Hard=8
python stepgen.py "First Song.mp3" "Second Song.flac" --out "songs/BeatSmith"
```

MP3, OGG, WAV and FLAC are supported directly. Other formats may require
ffmpeg. Output is a folder per song with `.sm`, playable audio and optional
artwork. The original input stays in place. By default audio is converted
to Ogg Vorbis; `--keep-format` copies it as-is.

Run `python stepgen.py --help` for the current option list.

| Option | Purpose |
|---|---|
| `--title "My Song"`, `--artist "Someone"` | Chart title/artist; an explicit title applies to a single-input run |
| `--out PATH` | Output group; it can be inside a rhythm game's Songs folder |
| `--bpm 140` | Force a constant BPM; omitted or zero detects it; nonzero values below 20 are rejected |
| `--seed 2` | Another deterministic arrangement at the same settings |
| `--profile flow` | Built-in play style or a path to a `.toml` profile |
| `--list-profiles` | List available built-in profiles and exit |
| `--target Hard=9` | Request a difficulty; repeat for other charts |
| `--set Hard.jump=0.8` | Exact per-difficulty setting; repeat as needed |
| `--easy jumps=0.8` | A grouped feel control; 0.5 leaves the profile as written |
| `--backoff` | Make the hardest chart first, then cut easier charts from it |
| `--shorten 90` | Try a separate shorter cut; no clean cut can mean keeping full length |
| `--keep-verses` | With shortening, avoid dropping detected verses; lyric-based labels are more useful |
| `--keep-format` | Copy the input format instead of converting to Ogg; shortening still writes a new cut |
| `--clicks` | Write an additional timing-check audio file with step clicks |
| `--no-art` | Do not make song pictures |
| `--art-online` | Allow online artwork lookup when local/embedded art is unavailable |
| `--art-image cover.png` | Use a chosen local image |
| `--device auto` or `--device cpu` | Choose supported AI acceleration or force CPU |

## Difficulty, profiles and feel

Profiles live in `profiles/`; the fallback settings are in `patterns.toml`.
Their comments explain the detailed settings. A custom profile uses one
table per difficulty. An exact `--set` overrides the selected profile and
grouped controls.

```sh
python stepgen.py "My Song.mp3" --profile flow --seed 3 --target Hard=8 --easy holds=0.7 --set Hard.jump=0.2
```

| Grouped control | Lower end | Higher end |
|---|---|---|
| `energy` | Flatter density | Stronger quiet/loud contrast |
| `jumps` | Fewer jumps | More jump accents and clusters |
| `speed` | Simpler beat rhythms | More off-beats and bursts |
| `breathing` | Fewer pauses | More pauses and recovery |
| `footwork` | Simpler patterns | More technical patterns |
| `holds` | Fewer holds | More holds |
| `repetition` | More fresh choices | More repeated rhythm/arrow patterns |
| `groove` | Looser combined settings | Stronger combined groove settings and candidate selection |

The app's **Groove off** corresponds to CLI `--easy groove=0.5`; its maximum
corresponds to `groove=1`. The CLI also permits values below 0.5 to loosen it.
Higher Groove can evaluate multiple candidates, increasing generation time.

Targets are requests, not guaranteed output ratings. The generator adjusts
density and, when necessary, other limits to get closer. Higher targets can
push past the requested feel. The stats, generation record's `made_with`,
and app's **made** columns show what was changed. Read the
[control reference](DIALS.md) for detailed behavior and earlier measurements.

## Optional local AI controls

```sh
python addons.py status
python addons.py sources stems
python addons.py install stems
python stepgen.py "My Song.mp3" --stems --set Hard.melody_follow=0.8 --follow chorus=1
```

`--stems` uses the separation add-on. The experimental follow control favors
vocal/tonal onset signals; automatic follow is reduced by section type and
singing activity. Overrides such as `--follow all=1`, `--follow B=0.8` or
`--follow 3=0.4` win over those automatic values. Without stems, CLI follow
uses full-mix signals and is less selective. It does not transcribe pitches.
There is no released `--melody-source` option.

`--lyrics` adds local lyric-based verse detection, requiring the lyrics
add-on and separated vocals. `--ai 0.5` blends the bundled step-placement
model into each difficulty; explicit per-difficulty `ai_assist` settings can
override it. These operations do not require a cloud AI API key.

`python accel.py` reports the available acceleration paths. See
[AI Usage](../AI_USAGE.md) for download destinations and data flow.

## Files and analysis tools

The playable output folder holds the chart/audio/pictures. From source,
the supporting records are under `song-data/`, unless `BEATSMITH_DATA`
overrides that location. Installed apps use their own app-data folder.

| Record | Contents |
|---|---|
| `<title>.stats.md` | Chart statistics, sections and settings actually used |
| `<title>.stepgen.json` | Source, output, generation settings and section data |
| `<title>.app.json` | App-side per-song settings |
| `.stems/` | Cached separation output and optional lyrics data |
| `.compare/` | Available comparison charts, kept outside the game-facing song folder |

```sh
python chartstats.py "songs/BeatSmith/My Song/My Song.sm"
python chartstats.py "songs/BeatSmith/My Song/My Song.sm" --audio "songs/BeatSmith/My Song/My Song.ogg"
python chart_editor.py "songs/BeatSmith/My Song/My Song.sm"
```

`chartstats.py` also reads `.ssc` and `.dwi` dance-single charts. The standalone
editor opens `.sm`; see the [app guide](APP_GUIDE.md#edit-and-play-test) for keys.

## Unfinished LLM review tool

`llm_review.py` predates newer options. Its prompt and rerun suggestions do
not cover all current settings. It is not part of normal desktop generation.

Start with a prompt file you can inspect without contacting an AI API:

```sh
python llm_review.py "songs/BeatSmith/My Song/My Song.sm" --prompt-only
```

An explicitly selected cloud run sends derived text (section summaries,
chart steps/statistics and settings), not the audio file. Gemini is the
default provider and uses `GEMINI_API_KEY` (or `GOOGLE_API_KEY`); Claude uses
`--provider claude` and `ANTHROPIC_API_KEY`. A configured local server uses
`--provider local` and, if needed, `--local-url`. `--model` chooses a model.
Provider availability and costs can change; no free-tier promise is made.

If you paste the prompt into another service, its own policies apply.
`--from-reply` reads a saved response; `--no-ask` avoids offering a rerun.
Do not assume that an offered rerun preserves newer app options. See
[AI Usage](../AI_USAGE.md#separate-cloud-review-tool-unfinished) before using it.

## Development and releases

[Installer build instructions](../packaging/BUILD.md) cover Windows and Mac.
[Release instructions](../packaging/RELEASING.md) describe version PRs and
tagged publication. Application changes go through pull requests; the
maintainer reviews and merges them.
