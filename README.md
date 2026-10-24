<p align="center"><img src="branding/beatsmith-mark-512.png" alt="BeatSmith logo" width="200"></p>

# BeatSmith

[![Build](https://github.com/paul-lapczynski/beatsmith/actions/workflows/release.yml/badge.svg?branch=main&event=push)](https://github.com/paul-lapczynski/beatsmith/actions/workflows/release.yml)
[![Release](https://img.shields.io/github/v/release/paul-lapczynski/beatsmith)](https://github.com/paul-lapczynski/beatsmith/releases/latest)
[![License](https://img.shields.io/github/license/paul-lapczynski/beatsmith)](LICENSE)

Turns a song into a StepMania `.sm` file with Easy, Medium and Hard
`dance-single` (4 panel) charts.

What every slider and setting does, with pictures of the arrows at 25%, 50% and 75%:
[docs/DIALS.md](docs/DIALS.md).

## Quick start

```
python3 -m pip install -r requirements.txt     # librosa, soundfile, numpy
python3 stepgen.py "My Song.mp3" --artist "Someone" --out songs/
```

This makes `songs/My Song/` holding just `My Song.sm`, the audio converted
to `My Song.ogg` (`--keep-format` copies it as-is instead) and the song's
pictures, so `--out` can be a group folder in StepMania's `Songs` folder
itself, e.g. `--out "C:/Games/StepMania 5/Songs/AATesting"` (works in
StepMania 5, ITGmania and OutFox). Everything else stepgen keeps about the
song (stats, the settings it was made with, stems, compare charts, the
editor's backup) goes in its own data folder, under
`songs/<output folder name>-<id>/My Song/` (on Windows in
`%APPDATA%\stepgen\stepgen`). Songs made with older versions, with the
StepMania folder inside the song's folder or everything in one folder,
still open, and are moved to this layout when made again. Several files at
once: `python3 stepgen.py *.mp3`.

Folder and file names are always plain letters, because StepMania on Windows
skips a song whose folder or files have Korean, Japanese and other letters in
their names. A title like `(타샤니) Caution (경고)` by Tashannie is made as
`Tashannie - Caution/` (Korean on its own is spelled out: `경고` is
`Gyeonggo`), while the .sm keeps the real title and adds `#TITLETRANSLIT`.
MP3, OGG, WAV and FLAC load directly; anything else goes through ffmpeg.

| Option | What it does |
|---|---|
| `--bpm 140` | Force the tempo when detection picks the wrong one |
| `--seed 2` | Same timing, different arrow layout |
| `--profile flow` | Use a play-style profile from `profiles/` (or any .toml path) |
| `--list-profiles` | Show the available profiles |
| `--target Hard=9` | Aim a chart at a difficulty number (repeatable). See "Making it harder" |
| `--easy jumps=0.8` | Easy-mode slider, 0 to 1, where 0.5 leaves the profile as written (repeatable) |
| `--set Hard.jump=0.8` | Change one setting for this run (repeatable). Always wins over `--easy` |
| `--backoff` | Make the hardest chart first and cut the easier ones out of it |
| `--clicks` | Also writes `<title>.clicks.wav`: the song with a tick on every Hard note, to check sync by ear |
| `--no-art` | Leave the banner, background and jacket empty. See "Song artwork" |
| `--art-online` | Look the artwork up online when the song has none. See "Song artwork" |

## The app

`run_app.bat` (or `python stepgen_app.py`) opens a window around stepgen:

- **Queue:** add songs, add a whole folder (subfolders too) or drop files and
  folders on the window. Title and artist come from the file's tags and can be
  edited, as can the BPM ("auto" detects it).
- **Output folder:** any folder you pick, such as a group folder in
  StepMania's Songs folder (`Songs\AATesting`). Each song gets a folder in
  it with just the chart, the song and its pictures, ready to play; the
  stats, settings and the rest go in stepgen's own data folder.
  A song folder that already has charts stepgen didn't make is never touched,
  and songs already done are skipped unless you untick that.
- **Easy tab:** a difficulty number per chart (target mode) and the six feel
  sliders. **Advanced tab:** every setting per difficulty after the profile
  and sliders; edit a cell to set it exactly. File > Save settings as
  profile keeps the current mix as a profile of your own.
- **Settings per song:** every song in the queue has its own settings,
  shown in its Settings column. The bar at the top of the settings panel
  says what you're changing: with nothing selected, the settings new songs
  start with; with songs selected, those songs (a change applies to all
  selected). Songs waiting to run can still be changed while others are
  being made; a song takes its settings when it starts. A song being made
  or already made is locked and shows the settings it used; "Change
  settings and regenerate" unlocks it and Generate makes it again.
  Output folder and the Options tab apply to every song.
- Several songs run at once (Options tab), with a status per song, a
  progress bar and Cancel. Click a finished song for its stats and log;
  the stats start with the settings it was made with (also kept in the
  data folder as `<title>.app.json`, so a skipped song shows them too).
- **Show songs already made** (above the queue) lists the songs stepgen
  has already made in the output folder as "Made earlier" rows, with
  their meters, settings and stats. Select one to open it in the editor,
  or to regenerate it with new settings (if its song file is still where
  it was). Untick it to hide them again.
- Settings and the output folder are remembered.

### Edit tab (chart editor, early version)

Pick a finished song and press **Edit chart**, or open any `.sm` with
**Open chart…** (or run `python chart_editor.py song.sm` on its own). The
song plays while the steps scroll past the receptor line, with a waveform
beside the lanes to place steps against the music.

- **Mouse:** click to add a step, drag down from an empty spot for a hold,
  click a step to select it (Ctrl+click for more), drag to move the
  selection in time or across arrows, right-click to delete, drag in the
  measure ruler or Shift+drag to select a range, double-click a hold to
  make it a roll, right-click empty space to paste or insert/delete a beat,
  Ctrl+wheel to zoom. A click only grabs a step when it's nearer that step
  than the empty snap slot, so you can add steps right next to others: a
  white ring shows what a click would grab, a faint arrow where it would add.
- **Getting around:** the strip on the right shows the whole song (every
  step in its snap colour, your selection in white, a box for what's on
  screen); click or drag in it to jump. Wheel scrolls by the snap,
  Shift+wheel by a measure, Home/End go to the start and the last step.
- **Keyboard:** 1-4 toggle Left/Down/Up/Right at the cursor (hold the key
  and press Down to stretch a hold), Up/Down and PgUp/PgDn move, Left/Right
  change the snap, Shift+Up/Down select, Ctrl+C/X/V copy, cut and paste at
  the cursor, Ctrl+D duplicates the selection after itself, Ctrl+Up/Down
  nudges it, M mirrors it, Delete, Ctrl+Z/Y, Space plays, Ctrl+S saves.
- **Snap:** 1/4, 1/8, 1/12, 1/16, 1/24, 1/32, coloured the way StepMania
  colours them. Playback at 1x, 0.75x or 0.5x, with an optional tick on
  every step to check timing.
- **Play test:** press it to play the chart from the cursor (with three
  seconds' lead-in, even from the very start of the song) using the arrow keys or D F J K. You get StepMania's
  judgements (Marvelous to Miss, OK/NG for holds), a combo and a score, and
  at the end your average timing, which also tells you if the chart's
  offset is off. Esc stops.
- **Sync:** if the whole chart is early or late against the music, fix it
  on the Sync row: type the offset, nudge the steps 10 ms earlier/later,
  or move them a whole snap step (a beat at 1/4, a quarter beat at 1/16).
  After a play test, **Match my play test** moves the steps by your
  average timing. **Tap sync** plays the song from the cursor while you
  tap T on the quarter notes; press it again (or Space) and the steps
  shift onto your taps. If your taps run at a different tempo than the
  chart, it tells you the BPM to regenerate with instead. It changes the song's offset (all its charts) and is
  written with Save.
- **Compare:** shows another chart in a second set of lanes beside yours,
  scrolling and playing along, read-only: another difficulty of the song
  (handy with backoff charts), or, for a chart made with Follow the melody
  on, the same chart made without following (same settings, same seed).
  Its steps that land where yours also step are dimmed, so the bright ones
  are where the two differ.
- **Groove meter:** the status line shows a Groove score out of 100, and
  the right edge of the song strip colours each measure from red to green.
  Hover a measure for why. It scores five things per measure: steps on
  the song's hits (locked), a rhythm that comes back in the bars around it
  (pattern), runs that end so you get a moment (breathing), comfortable
  feet with no crossovers or fast jacks (footing), and busy where the song
  is loud (effort). On Sandstorm, Konami's Hard scores 84, stepgen's
  Hard 8 79, and a nonstop chart 72. In a play test, **hold G** while you feel the groove:
  the score window compares the meter where you marked with elsewhere,
  and each test is saved next to the chart as `<title>.groove-marks.json`
  so the meter can be tuned to what you actually feel.
- The status line shows where you are, the counts and stepgen's live rating
  of the chart. The first save keeps the original as `.sm.bak`.

To build the Windows installer, see `packaging/BUILD.md`.

## How it works

1. **Tempo and sync.** Separates drums from the tonal part (HPSS), tracks
   beats, then searches for the single constant BPM and phase that line up best
   with the drum onsets, snapping to a whole or half BPM when it fits. Tempos
   are folded into 90 to 200 BPM. The bar start is the beat phase with the most
   kick and chord-change energy. A fixed 16 ms correction offsets the onset
   detector's lag. On test tracks with known tempo the offset lands within 2 ms.
2. **Where the notes go.** Each measure gets a section intensity from drum
   activity, kick and loudness, which finds drops and breakdowns even in songs
   mastered flat-loud. Every slot on the grid is scored by how much there is
   to step on: kick, snare and the lead melody count, steady hi-hats barely do
   (they're loud in dance music but nobody dances to them),
   weighted by grid position (beat notes over half-beats over quarter-beats)
   and by that intensity. The note budget is shared out per measure (with an
   optional 4-bar phrase shape and breather bars) and the best slots are kept.
   Holds go where the music has no strong hits of its own to cover, and after
   they take their space the chart is topped back up to its density.
3. **Which arrows.** A two-foot model: feet alternate, the left foot uses
   Left/Down/Up and the right foot Right/Down/Up, so there are no crossovers.
   Quick notes always go foot to foot onto different arrows (no quarter-beat
   jacks), and a rising melody leans toward
   Up, a falling one toward Down. Jumps go on the strongest kick accents,
   always on a beat, gathered at section starts with `jump_clusters`. With
   `crescendo`, build-ups are found from the section intensity: the steps
   climb through them, a jump lands on the climax hit and on the final big hit
   before the song falls away. Holds go
   where a melody or chord note keeps sounding, and with `jump_holds` some big
   downbeat jumps become two-foot freezes.
   How much of each is controlled by `patterns.toml`.

All the pattern knobs live in `patterns.toml`, one table per difficulty, with a
comment explaining each: density, grid, half_beats, quarter_beats, jump, jacks,
jack_max, flow, side_to_side, flow_spice, energy_follow, the hold settings,
rhythm_repeat, arrow_repeat, intensity_variation, jump_clusters, jump_holds,
flow_runs, phrase_shape, rest_bars, beat_backbone, crescendo and target_meter. Needs Python 3.11+.

A few settings are **retired**: the dial test (`dialtest/REPORT.md`) found no
measurable effect from jack_max, flow, hold_complexity,
hold_free_foot, intensity_variation, max_run16, max_nps or meter_min/max.
Profiles that set them still load and use them as written, but no slider
moves them and the app's Advanced tab shows them greyed out. (The difficulty
target still turns max_nps as part of density.)

## Making it harder (or easier)

Use `--target`. `--target Hard=9` keeps the profile's feel and turns one
internal intensity dial until the chart rates 9, in stages, each only when
the one before can't get there:

1. **Density**: more (or fewer) steps, the grid and spacing they sit on, the
   notes/sec cap, jumps and holds. Speed's settings (8ths, quarter-beat
   bursts, 16ths, flow spice) stay where the Speed slider put them.
2. **16th streams**, within the 16th allowance Speed sets.
3. **Speed**: 8th-note runs, then quarter-beat bursts.
4. **Breathing room** eased to half.
5. For 9s and 10s only: **longer 16th streams, more 8ths and less rest**
   (shorter recovery, pauses further apart), past Speed's allowance. 16ths still stop at the share Konami's own 9s and 10s
   have (16% of steps at 9, 20% at 10).

With a target, off-beat 8ths are kept to a share Speed sets (15% of steps
plus half of `half_beats`; the weakest extra ones go), so Speed still
orders how busy a chart is even when the target supplies the step count.
The dial raises that share itself only in the Speed stage.
Whatever the target changed is recorded per chart: in `stepgen.json`
(`made_with`), the stats file's "Made with" section, and the app's Advanced
tab ("made" columns), e.g. "Speed raised (8ths 0.30 → 0.65) to get to
meter 9". Each difficulty can be aimed anywhere from about 2
to 10 (`--target Easy=3 --target Medium=6 --target Hard=9`). If a song can't
get there (a slow ballad asked for a 10), it says so and keeps the closest.

The rating is stepgen's own estimate of Konami's number, fitted on 909
official Konami pad charts from the PS2 and arcade mixes. It reads steps/sec
over the song and in its busiest bars, jumps, off-beat and quarter-beat
steps, the longest 8th-note run and holds. It lands within one of Konami's
number 70% of the time; Konami's Sandstorm charts (4/6/8) rate 3.0/5.4/7.3.
The fit itself squeezes the top (Konami's own 9s came out 8.4, their 10s
9.4), so past 8 it's stretched back until their 9s rate 9 and their 10s
rate 10. The meter written to the .sm is always
this rating, so it tells you whether a change made the chart harder.

## Easy-mode sliders

Each slider moves a group of settings together, from the profile's value
toward one end. 0.5 changes nothing.

| Slider | 0 | 1 | Moves |
|---|---|---|---|
| `energy` | flat | dramatic | energy_follow, crescendo, phrase_shape, rest_bars |
| `jumps` | none | lots | jump, jump_clusters, jump_holds |
| `speed` | on the beat, no 16ths | busy, double the usual 16ths | half_beats, quarter_beats, sixteenths, flow_spice, beat_backbone |
| `groove` | anything goes | made to groove | rhythm_repeat, beat_backbone, jacks, energy_follow, phrase_shape, run_breaks, recovery, stomps, rhythm_lock, groove_tries |
| `breathing` | nonstop runs | more pauses | run_breaks, recovery, stomps (at most 0.4); no effect on Easy, which has no runs |
| `footwork` | simple | technical | flow_runs, side_to_side, jacks |
| `holds` | none | lots | hold_rate |
| `repetition` | always fresh | choruses identical | rhythm_repeat, arrow_repeat |

With a difficulty of 9 or 10, a chart may go past these sliders to reach
the number (the app says so next to them).

16th notes are capped by difficulty the way Konami's charts are (none up
to 5, about 6% of steps at 7, 11% at 8, 16% at 9, 20% at 10), even when
aiming with `--target`; Speed scales that cap from none to double. Only
the last stage of a 9 or 10 target goes past it.

**Groove** is the overall slider, on top of the others in the app's Easy
tab. In the app it starts at 0, which is off (the profile as it is); on the
command line that's `--easy groove=0.5`, up to `groove=1`, and below 0.5
loosens the groove instead. Toward "made to groove" it moves many settings
at once: rhythms that come back bar to bar (a bar takes the previous bar's
rhythm where the music carries on alike), more breathing room and stomps,
steps on the drums, comfy footwork, busy where the song is loud. From
about 20% in the app it also makes 2-4 versions of each chart at the same difficulty and keeps
the one the groove meter scores best, which takes 2-4 times as long. The
Feel sliders are applied after it, so they still have the last word on
their own settings. Each chart's groove score is printed with its meter.

**Shorten** (`--shorten 90`, or Length: "Try to shorten to about 1:30 / 2:00"
in the app) cuts a long song down toward that length, as a separate
`<title> (short)` song; the full song isn't touched. A cut is a jump from one
bar to a later one where the music around both sounds alike (the same chords
on the same beats, the same sound), on the same spot of the 4-bar phrase,
so the beat and the chords carry straight through. It picks the fewest,
cleanest jumps that get near the target, keeps the start and the ending,
and prefers skipping music the song plays again elsewhere. A song with no
clean place to cut is left full length, so it may land over the target.
The jumps and what was kept are printed and saved in `<title>.stepgen.json`.
**Keep all verses** (`--keep-verses`) only lets it skip choruses, the intro
and outro, and quiet breakdowns. In the app it needs **AI verse detection**,
which reads the lyrics to know which parts are verses; from the music
alone a verse can be named a build or a bridge, so every part that isn't
one of those would stay and most songs couldn't be shortened at all.

**Backoff** (`--backoff`, or "Cut the easier charts out of the hardest" in
the app) makes the hardest chart first and cuts the easier ones out of it,
so two players on different difficulties dance the same song. The easier
chart keeps the steps that matter most to the music (downbeats, big hits,
the beat, holds) with the same arrows wherever the feet allow, and drops
16ths first, then weak off-beat 8ths, then weaker beats, keeping its own
spacing. Jumps that land on a beat stay (at most 2 in a row on Easy, 3
on Medium); jumps between beats become single steps. Freezes keep the
harder chart's share. On Sandstorm (Hard 8, Medium 6, Easy 3) every Medium and
Easy step sits on a Hard step, 98% with the same arrow.

**Breathing room** gives a chart the pauses a dancer finds in a groove.
Long runs get a short pause (about a beat) every few steps, placed where
the dropped steps are weakest and varied a little so it doesn't feel
mechanical; at the default that's close to Konami's charts (most runs 5-8
steps, longer in the big parts). After a long or hard run comes a rest of
up to about 3 beats, and a freeze with nothing tapped under it counts as
that rest. Where a pause lands on a row of big beats, those beats can
become 2-4 quarter-note jumps instead, [1001][1001]: following the song and
a break at once (needs jumps on). Pauses cost steps, so when aiming at a
difficulty the song can't reach with them, stepgen halves the breathing
room first, then says how close it got.

Pair them with `--target` so changing the feel doesn't also change how hard
the chart is: `--target Hard=8 --easy jumps=0.8 --easy holds=0.2`.

## Following the melody (early version)

stepgen splits each song into sections (intro, verse, chorus, bridge,
build, breakdown, outro, plus a letter per kind of music, so a chorus that
comes back has the same letter) and can make the arrows follow the tune in
some of them instead of the drums. While following, notes land on the
tune's rhythm, off the beat if the tune is, and the arrows climb toward
Right as the tune rises and back toward Left as it falls.

- `melody_follow` (0..1, default 0) turns it on. Choruses get the full
  amount, verses and bridges 60%, intros, outros and builds 30%.
  In the app: Easy tab > **Arrows follow** slider.
- `--follow chorus=1 --follow 5=0.3` sets sections exactly, by name,
  letter, number or `all`. In the app: open **Per section** under the
  slider; each kind of section has its own slider that tracks the main one
  until you move it (shown in bold, "set by you").
- The sections found, and how much each one followed, are in each song's
  stats file and printed at the end of each run. Names are a best guess
  from loudness and repeats.
- When a chart follows anywhere, stepgen also writes its beat-only version
  to a `.compare` folder in stepgen's data folder for the song, for
  the editor's **Compare with beat only**.
- `--stems` separates the vocals first with Demucs, so the arrows follow
  the singing rather than everything melodic, and only while someone is
  singing. In the app this is **Enable melody analysis**: Arrows follow,
  its per-section sliders and AI verse detection only work while it's on
  (the dial test found following without stems moves steps but not toward
  the tune). It's optional and not in the installer: ticking it the first
  time, or **Download melody analysis**, fetches it (about 1 GB, into
  `%LOCALAPPDATA%\stepgen\addons`). Separating takes a minute or two per
  song, and the stems are kept in a `.stems` folder inside the song folder
  (about 15 MB, ignored by StepMania) so it only happens once. Without
  stems, following uses the full mix's lead line.
- `--lyrics` (**Use AI verse detection** in the app) reads the words off
  the separated vocals with a speech model (Whisper "small", on the CPU only,
  about a minute per song) and names the sections from them: words that
  come back are the chorus (or the build into it), new words are a verse,
  no words is an intro, outro or break. That changes how much each part
  follows the melody and what **Shorten** and **Keep all verses** treat as
  a verse. It needs vocal separation and its own download, **Download AI
  verse detection** (about 650 MB, same folder). The words are kept as
  `lyrics.json` with the stems, and each section's first words are shown
  in the run's output.

### Downloads and where they come from

Nothing is downloaded until you press a download button, and the app lists
every source first (also `python addons.py sources stems` / `lyrics`):

| What | From |
|---|---|
| Python 3.12.7, embeddable (Windows, first add-on only) | https://www.python.org/ftp/python/3.12.7/python-3.12.7-embed-amd64.zip |
| pip | https://bootstrap.pypa.io/get-pip.py |
| Demucs, PyTorch, SoundFile, NumPy (vocal separation) | https://pypi.org (files from files.pythonhosted.org) |
| htdemucs separation model (Meta) | https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th |
| faster-whisper, CTranslate2, tokenizers, huggingface-hub, PyAV, ONNX Runtime (AI verse detection) | https://pypi.org (files from files.pythonhosted.org) |
| Whisper "small" for faster-whisper (Systran) | https://huggingface.co/Systran/faster-whisper-small |
| PyTorch and torchaudio for NVIDIA CUDA (GPU support, optional) | https://download.pytorch.org/whl/cu128 (or cu126, cu130 if that build isn't there) |

Everything goes into `%LOCALAPPDATA%\stepgen\addons`; deleting that folder
removes it all.

### Hardware acceleration

Options > **Hardware acceleration** picks where the heavy optional parts
run: **Use the GPU when there is one** (the default) or **CPU only**. Only
the neural networks can use a GPU; making the charts is always the CPU.

| Part | NVIDIA GPU | Apple Silicon GPU |
|---|---|---|
| Vocal separation (Demucs) | yes, after **Download NVIDIA GPU support** (about 3 GB) | yes, nothing to download |
| AI verse detection (Whisper) | yes, with the same download | no (CPU) |
| AI assist | no (CPU; it's small and quick) | yes (Core ML) |

The app says which GPU it found under the option. If the GPU fails (out
of memory, an old driver), that step runs on the CPU instead, so a GPU never
breaks a run. On the command line it's `--device auto|cpu`, and
`python accel.py` prints what stepgen would use on this computer.

### Song artwork

Each song gets a banner (`<title>-bn.png`, 418x164), a background
(`<title>-bg.png`, 640x480, dimmed so the arrows stay easy to read) and a
jacket (`<title>-jacket.png`, 512x512), filled into the .sm's `#BANNER`,
`#BACKGROUND` and `#JACKET`. The picture comes from, in order:

1. an image beside the song: the song's own name (`My Song.jpg` for
   `My Song.mp3`), else `cover`, `folder`, `front` or `album` .jpg/.png
2. art already in the song folder from an earlier run, kept as it is, so
   you can swap in your own (delete the files to make them again)
3. the cover art inside the song file (MP3, FLAC, Ogg, M4A)
4. online, only when Options > **Look up artwork online when a song has
   none** is ticked (`--art-online`)

Nothing is downloaded for 1 to 3. The online lookup sends the song's title
and artist to these sites, and each address is listed in the song's log
before it's fetched:

| What | From |
|---|---|
| Song search by title and artist | https://musicbrainz.org (MusicBrainz) |
| The cover for what it finds | https://coverartarchive.org (Cover Art Archive; the files come from archive.org) |
| When MusicBrainz has none | https://itunes.apple.com (iTunes Search API; the pictures come from Apple's mzstatic.com) |
| Then, and for a photo of the artist | https://api.deezer.com (Deezer API; the pictures come from dzcdn.net) |

It tries the song's own cover first, then its album's (from the album tag),
then another cover by the same artist, and last a photo of the artist.
Without an artist tag it guesses one from the name ("Artist - Title",
"ARTIST-TITLE") and also tries what's in brackets as the title. It looks
in the US, Korean and Japanese iTunes stores and accepts a title listed in
another language when the English one is in brackets ("경고 (Caution)").
The Details tab says what it matched and flags a loose match to check.

In the app the artwork is found as soon as a song is added, and the
**Details** tab (beside Chart stats and Log) shows the jacket, banner and
background it will use, where the picture came from, and what the song file
says about itself (album, year, length, format). From there **Choose
picture…** uses one of your own, **Look up online** searches for this song
only (even with the option off), and **No artwork** leaves it empty.

Options > **Add song artwork** off (`--no-art`) leaves them empty.
`python artwork.py song.mp3 --out folder [--online]` makes the pictures
for one song on its own. The art is for your own copies of the songs;
album covers belong to their owners.

## Profiles (play styles)

`patterns.toml` is the base. A profile in `profiles/` only lists what it
changes:

```toml
# Flow: rolling footwork, few jumps        <- first comment = description
base = "patterns.toml"

[all]            # applies to every difficulty
flow = 0.95
jump = 0.1

[Hard]           # just this difficulty
half_beats = 0.9

[Challenge]      # add a difficulty, starting from another one
extends = "Hard"
density = 1.9
```

Use one with `--profile flow` (or any path to a .toml), see them with
`--list-profiles`. `skip = true` in a table drops that difficulty. The
profile name goes in the `.sm` credit and the stats file. Included: `flow`,
`power` (adds a Challenge chart), `chill` and `konami` (arcade style modelled
on DDR's Sandstorm: steady beat-note groove, jump bursts at drops, jump
freezes, short freezes, rhythm repeats with fresh arrows).

## Repeated sections

Each measure gets a fingerprint (harmony per beat, timbre, loudness). Stretches
of 4+ measures that match an earlier stretch, like a returning chorus, reuse
the earlier rhythm (`rhythm_repeat`) and some of its arrows (`arrow_repeat`;
the rest are picked fresh, sometimes Left/Right mirrored), with more change
when the repeat is more intense (`intensity_variation`). A repeat keeps its own
jumps, so drops still hit, and a bar is only copied where its hits line up
like the earlier one's. The run prints which measures repeat.

## Stats dump

Every run writes `<title>.stats.md` in stepgen's data folder for the song
(shown in the app's Chart stats tab): song analysis, the
repeated sections, a stats table per difficulty, the StepMania groove radar
(stream, voltage, air, freeze, chaos, same formulas as the game) and notes per
measure as a Mermaid line chart plus a text heat strip. The radar values are
also written into the `.sm`.

## LLM review (under construction)

> Not maintained right now. It predates the AI assist model and newer options:
> the prompt leaves out the section dials, backoff, stems, shorten and lyrics,
> and its re-run drops those options. It isn't in the app.

`python3 llm_review.py "songs/My Song/My Song.sm"` has an LLM review a
generated chart against the song, like a chart author would: does it arc with
the music (climb through build-ups, hit the climax, ease off), do repeated
choruses feel like the same dance, do jumps and holds sit on big moments. It
writes `<title>.review.md` with the issues by measure and 2-4 options, each an
exact `--set` re-run, and offers to regenerate with the one you pick.

| Provider | Setup |
|---|---|
| `--provider gemini` (default) | `GEMINI_API_KEY` from Google AI Studio; the free tier is enough for this |
| `--provider claude` | `ANTHROPIC_API_KEY` |
| `--provider local` | LM Studio's local server (Developer tab, Start server), no key, offline |
| `--prompt-only` | No API: writes `<title>.review-prompt.md` to paste into any chat app. Save its answer as `<title>.review-reply.txt` next to the chart and run `--from-reply` for the same report and re-run offer |

`--model` picks another model, `--difficulty Hard` reviews one chart. Each
run of stepgen saves `<title>.stepgen.json` (song, profile, seed, settings)
so the review can suggest exact re-runs.

## Comparing charts

`python3 chartstats.py chart.sm [--audio song.ogg]` (.sm, .ssc or .dwi) prints pattern stats for
every dance-single chart: jumps and jump runs, jacks, side-to-side moves, flow
runs and walk-downs, holds and taps under them, and with audio, how well notes
land on the music and follow its loudness.

## Limits of this version

- One constant BPM per song. Songs with tempo changes or a drifting live
  drummer will slide out of sync; use `--bpm` or edit `#BPMS` by hand.
- The bar start can land half a bar off when beats 1 and 3 sound alike. It
  only shifts where measure lines fall, not the sync.
- Triplets (12th/24th notes) and mines aren't generated yet.
- No section-aware styling yet (e.g. a different feel for a rap verse).

## Example

`examples/Stepgen Test 128/` is a synthetic 128 BPM drum track with its
generated chart, useful for checking that your pad's timing feels right.
