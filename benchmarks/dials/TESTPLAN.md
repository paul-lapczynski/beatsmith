# BeatSmith dial test plan

What this answers: for every control in BeatSmith (the app's Easy tab, the
difficulty numbers, AI assist, Follow the melody and every Advanced
setting), what it actually does to a chart, how well it does what its
label says, and how the controls interact. The script `dialtest.py` runs
this plan, writes `REPORT.md` (ratings and numbers) and `docs/DIALS.md`
(the README for people with pictures of the arrows).

Testing every combination is impossible (8 sliders x 101 positions x 3
targets x ... is trillions), so the plan uses four cheaper designs that
together cover it: one dial at a time, targeted pairs, a random sample of
the whole space, and a sweep of the difficulty number.

## 1. What is being tested

### The controls (the "dials")

| Group | Control | App scale | What it moves inside BeatSmith |
|---|---|---|---|
| Groove (overall) | groove | 0 off .. 100 | rhythm_repeat, beat_backbone, flow, jacks, energy_follow, phrase_shape, run_breaks, recovery, stomps, rhythm_lock, groove_tries (2-4 tries from about 20%) |
| Feel | energy | 0..100, 50 = profile | energy_follow, crescendo, phrase_shape, rest_bars |
| Feel | jumps | same | jump, jump_clusters, jump_holds |
| Feel | speed | same | half_beats, quarter_beats, sixteenths, flow_spice, beat_backbone (down) |
| Feel | breathing | same | run_breaks, recovery, stomps |
| Feel | footwork | same | flow, flow_runs, side_to_side (down), jacks (down) |
| Feel | holds | same | hold_rate, hold_complexity, hold_free_foot |
| Feel | repetition | same | rhythm_repeat, arrow_repeat, intensity_variation (down) |
| Difficulty | target per chart | 1..10, or off | with_intensity(): density, max_nps, jump, hold_rate, half_beats, grid/min_gap, quarter_beats, flow_spice, then 16th streams |
| Melody | Arrows follow | 0..100 | melody_follow (per section kind: chorus 100%, verse/bridge 60%, intro/outro/build 30%) |
| AI | Steps placed by | 0..100 | ai_assist (blends the model's step envelope into BeatSmith's) |
| Advanced | every DiffSpec field | exact values | 45 settings, pinned exactly; sliders can no longer move a pinned one |

Order inside BeatSmith: profile -> groove -> feel sliders -> Advanced pins
(`--set`) -> target (with_intensity rescales some of the same settings
again at chart time). Follow and AI only change *where the music says a
step could go* (the step envelope); everything after that is the feel.

### Test values

Images and the main tables use **25 / 50 / 75%** of each slider, as asked.
The measurements also run 0 and 100 (and 12.5 steps for the preview page)
so the report can say whether a dial is a straight line, saturates or
flips near the ends. Advanced settings are tested at 25/50/75% of their
useful range (table in section 6).

### Songs, charts and seeds

- Songs: Wrong Note (Moon Boots, 136 BPM, house), Sandstorm (Darude,
  136, trance), Yeah! (Usher, 105, hip-hop). The script takes any audio
  files, so it can be re-run on more of your library (read-only, from
  `C:\Games\StepMania 5\Songs`).
- Charts: Easy, Medium, Hard of each run.
- Seeds 1, 2, 3 for every setting. The spread between seeds is the noise
  floor: a dial only "does something" if its change is bigger than what
  changing the seed does.
- Context: profile **konami** (the app's default) and **patterns** (the
  base), each with targets **on** (app default 3/6/8) and **off**.
- CPU only. Each song is analysed once and cached; a chart takes about
  0.2-0.7 s, so the whole plan is a few thousand charts and runs in well
  under an hour on 4 cores.

## 2. What is measured on every chart

Every chart gets the same set of measurements (the "fingerprint"), all
from the notes plus the song analysis:

| Area | Measurements |
|---|---|
| Amount | steps, steps/sec, BeatSmith's meter estimate, distance from the target |
| Jumps | jumps per 100 steps, jump freezes, share of jumps in the first 2 bars of a section (clustering), stomps |
| Speed | share of beat / half-beat / quarter-beat steps, 16th count, longest 8th run |
| Holds | holds per 100 steps, held beats, taps under holds |
| Breathing | average run length, runs over 8 steps, rests of 2+ beats |
| Footwork | jacks, Left<->Right and Down<->Up moves, walk-downs and flow runs, arrow variety (entropy) |
| Energy | how closely steps per bar follow the song's loudness (rank correlation), contrast loud vs quiet bars, climb through build-ups |
| Repetition | in repeated sections: share of the same rhythm, share of the same arrows |
| Groove | groove meter total and its five parts (locked, pattern, breathing, footing, effort) |
| Melody | share of steps on melody onsets vs drum onsets, arrows rising with the tune (in followed sections) |
| AI | share of steps on the model's likeliest moments, overlap with the same chart at AI 0 |
| Change | overlap of step positions and arrows with the 50% chart (how much moved at all) |

## 3. Designs

### A. One dial at a time (main effects)

Every Easy-tab control alone at 0/25/50/75/100 with everything else at
its default, in all 4 contexts (2 profiles x targets on/off), 3 songs, 3
seeds. About 1,100 runs (3,300 charts).

### B. Difficulty sweep

Each chart (Easy, Medium, Hard as written in the profile) aimed at 1 to
10 in steps of 1, both profiles, 3 songs, 3 seeds. Records: the meter it
landed on, the intensity dial `k` the search settled on, the resulting
settings (density, jump, half_beats, grid, quarter_beats, ...) and the
fingerprint. This shows *how* a number becomes a chart: which mechanism
kicks in at which level, and where songs can't reach.

### C. Targeted interaction sets

Picked because the code says these controls touch the same settings or
depend on each other:

| Set | Grid | Question |
|---|---|---|
| C1 Feel x target | each feel slider 25/75, target on/off | Does aiming at a number eat the slider's effect? (Speed and Jumps share settings with the target dial) |
| C2 Feel x AI assist | each feel slider 25/75, AI 0/50/100 | Do the feel sliders still rule when the AI places the steps? |
| C3 Feel x Follow | each feel slider 25/75, follow 0/50/100 | Same, for following the melody |
| C4 Groove x feel | groove 0/75, each feel slider 25/75 | Who wins on shared settings (both move breathing, footwork, energy and repetition settings; speed and groove push beat_backbone in opposite directions) |
| C5 Jumps x breathing | 25/50/75 each | Stomps need jumps: does breathing do anything with jumps low? |
| C6 Holds x breathing | 25/50/75 each | A freeze counts as a rest: do holds reduce the pauses breathing adds? |
| C7 Speed x footwork | 25/50/75 each | Both decide what happens in fast runs |
| C8 Energy x repetition | 25/50/75 each | Energy reshapes density, repetition copies earlier bars: which wins in a returning chorus? |
| C9 AI x follow | 0/50/100 each | Both rewrite the step envelope: do they stack or cancel? |
| C10 Advanced pin x slider | pin jump/half_beats/run_breaks, move its slider | Confirms a pinned setting freezes its slider, and that the Advanced table shows the values really used when a target is on |

### D. Random sample of everything (screening)

150 random settings per song (Latin hypercube over the 8 sliders,
follow, AI and the three targets), seed 1. A regression on these gives
each dial's share of the change in every measurement and the strongest
interactions anywhere, including pairs not picked in C. It also trains
the quick lookup used by "find preset" (section 7).

### E. Advanced settings one at a time

Every DiffSpec field at 25/50/75% of its range on Medium and Hard, both
target modes, 3 songs, seed 1 (all three charts get the value). Each setting gets labelled:

- **Slider-covered**: a feel or groove slider moves it (and which).
- **Advanced-only**: no slider touches it (grid, min_gap, max_nps,
  jack_max, hold_min, hold_max, max_run16, ...).
- **Overwritten by target**: with a target on, with_intensity resets or
  rescales it, so changing it there does little.
- **No effect found**: changing it moves nothing beyond seed noise
  (meter_min/meter_max are expected here: kept only so old profiles load).

## 4. How each dial is rated

Each control has a claim (from its label and tooltip) turned into one or
two measurements with the direction they should move:

| Control | Claim | Main measurement (direction) |
|---|---|---|
| groove | rhythms come back, pauses, steps on the drums, busy where loud | groove meter total (up), pattern and locked parts (up) |
| energy | flat .. dramatic | steps-per-bar vs loudness correlation (up), loud/quiet contrast (up) |
| jumps | none .. lots | jumps per 100 steps (up), jump freezes (up) |
| speed | on the beat .. busy, more 16ths | off-beat share (up), 16ths (up), longest 8th run (up) |
| breathing | nonstop runs .. pauses and stomps | average run length (down), rests (up), stomps (up) |
| footwork | simple .. technical | walk-downs + Left<->Right (up), arrow variety (up), jacks (down) |
| holds | none .. lots | holds per 100 steps (up) |
| repetition | always fresh .. choruses identical | same rhythm and arrows in repeats (up) |
| follow | the beat .. the tune | steps on melody onsets (up), arrows follow pitch (up) |
| AI assist | BeatSmith's rules .. the AI model | steps on the model's moments (up), change vs AI 0 (up) |
| target | lands on the number | distance to target (small), monotonic, no song left out |

Scores per control, each 0-100, combined into a grade A-F:

1. **Does it move the right thing?** Effect size: change from 25% to 75%
   divided by the seed noise. 3x the noise or more is full marks.
2. **Always the same direction?** Rank correlation between slider and
   measurement across 0..100, per song and seed.
3. **Survives a target?** Effect with target on / effect with target off.
4. **Stays in its lane?** How much it also moves things it doesn't claim
   (especially difficulty: a feel slider shouldn't change the meter when
   a target is on).
5. **Works on every song?** Share of songs where 1-2 pass.

"Feel as the overall rules over AI and follow" is scored as retention:
each feel slider's effect with AI (or follow) at 100 divided by its
effect at 0. 80% or more means the feel still rules.

## 5. Pictures

For every control: 4 bars of Hard (target 8, konami, seed 1) of *BeatSmith Demo*, a track synthesized by `demo_track.py` so it can ship with the repo (the test songs are copyrighted and stay out of it), at 25, 50
and 75%, side by side, the same 4 bars each time (a loud returning
chorus, found automatically), arrows coloured by note length like
StepMania (beat red, half-beat blue, quarter-beat yellow), freezes as
bars. Plus the difficulty number at 3/5/7/9, groove at 0/25/50/75, and
follow and AI at 0/50/100. PNGs, in `docs/img/`.

## 6. Advanced ranges used

| Setting | 25 / 50 / 75% | Setting | 25 / 50 / 75% |
|---|---|---|---|
| 0..1 settings | 0.25 / 0.5 / 0.75 | density | 0.75 / 1.25 / 1.75 |
| max_nps | 3 / 5 / 7 | grid | 1 / 2 / 4 |
| min_gap | 0.25 / 0.5 / 1 | jack_max | 2 / 3 / 5 |
| hold_min, hold_max | 1 / 2 / 4, 2 / 4 / 6 | hold_free_foot | 0 / 1 / 2 |
| sixteenths | 0.5 / 1 / 1.5 | max_run16 | 3 / 6 / 12 |
| groove_tries | 1 / 2 / 4 | meter_min/max | 1-4 / 4-7 / 7-10 |

## 7. Find preset (reverse import)

Take a `.sm` you like plus its song, and find the dial settings that make
BeatSmith chart it the most like that:

1. Read the chart (`.sm`, `.ssc` or `.dwi`) and
   measure its fingerprint (section 2) against the song's analysis.
2. Start from the closest of the D-sample settings (a quick lookup from
   fingerprint to dials learned from section D), with each chart's target
   set to its measured meter.
3. Refine by real generation: move one dial at a time in 12.5% steps and
   keep a move when the generated chart's fingerprint gets closer (each
   measurement scaled by its seed noise, so no one number dominates).
   About 100-200 charts, a minute or two per song.
4. Save it as a profile (`profiles/<name>.toml`, with the sliders baked
   into settings as the app's "Save settings as profile" does) and the
   slider positions as app settings, plus a short report: how close each
   measurement got and what BeatSmith can't copy (for example 12th notes,
   mines or BPM changes).

Several charts can be imported together (for example all of a pack's
Hard charts) to find one preset for a style rather than one song.

## 8. Outputs

- `benchmarks/dials/dialtest.py run|report|images|docs|preview|find-preset`
- `benchmarks/dials/results/*.csv`: every chart's settings and fingerprint
- `benchmarks/dials/REPORT.md`: grades, numbers, interactions, Advanced map
- `docs/DIALS.md` + `docs/img/*.png`: the README section for GitHub
- `docs/preview.html`: the semi-live preview (one page, works offline)
