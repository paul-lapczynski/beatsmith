# Sandstorm (DDR PSX, .dwi) vs stepgen

Read-only review of `Songs\PS2\Sandstorm` (nothing there was changed). The chart
was decoded from `.dwi` (chartstats.py reads .dwi now) and lined up with the
song's audio. Numbers are for Basic / Another / Maniac, which StepMania shows as
Easy / Medium / Hard.

## 1. A sync bug this found (fixed)

On Sandstorm, stepgen's beat grid sat **about 0.4 beat off**: it locked onto the
off-beat hi-hats and bass, which in trance are louder than the kick. The grid
now gives the kick drum extra weight. After the fix:

| Song | Phase vs reference |
|---|---|
| Sandstorm (vs Konami's chart) | +16 ms |
| Wrong Note (vs your chart) | -5 ms |
| Synthetic 95 / 128 / 174 BPM | within 2 ms |

Any chart made from a song with a four-on-the-floor kick and loud off-beats
(trance, house, eurodance) before this fix is worth regenerating.

## 2. What makes Konami's chart work

**It repeats rhythm, not arrows.** Out of 49 measures, Maniac reuses an earlier
measure's *rhythm* 30 times but its exact *arrows* only once. Basic does reuse
short 2-beat arrow cells a lot (50 of 78 cells), Maniac much less (20 of 85).
So the chorus "feels the same" because your feet hit the same rhythm, while the
arrows keep moving. stepgen currently copies arrows (65-90% identical), which
is the opposite balance.

**Density is a choreography choice, not only the music.** Sandstorm is
mastered flat-loud from measure 12 to the end, and on closer analysis the
drums and bass don't drop there either, yet Maniac goes light around measures
29-32 and then dense to the end. That's the chart designer giving the player a
breather and building a phrase, so stepgen now models it directly
(`rest_bars`, `phrase_shape`) as well as following section intensity.

**Jumps come in clusters at section starts, not spread by loudness.**
```
loudness  ▃    ▁▁▃▄▂▃▂▅▅▅▆▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇█▇▇██▄
Maniac    ...........1.1.22.13.2......22...321...............1   jumps per measure
```
Maniac's jumps sit in three bursts (the first drop, the second build, the
return after the breakdown), often 2-4 back-to-back, then none through the
final stream where the pattern is all running steps. 10.6% of Maniac's steps
are jumps; stepgen Hard on the same song makes only 3.1%.

**"Powerful two notes" are jump freezes.** 9 of Maniac's 36 freezes start as a
jump (`2002`, both feet held), on the big synth hits at beats 1 and 3.

**Lots of short freezes.** Most freezes are 1 beat (23 of 36 on Maniac), on the
synth stabs. You found 1-beat holds unpleasant in stepgen, so this is a style
choice rather than something to copy; it fits a `konami` profile.

**Long flow runs.** Average run of steps without jumps or jacks: Maniac 13.6,
Another 15.6, stepgen Hard 6.2. The jacks and frequent short breaks in
stepgen's patterns cut the flow up.

## 3. Side by side (after the sync fix)

| | Konami Maniac | stepgen Hard |
|---|---|---|
| Notes/sec | 2.73 | 2.61 |
| Jumps % | 10.6 | 3.1 |
| Freezes (1-beat) | 36 (23) | 23 (0) |
| Jump freezes | 9 | 0 |
| Flow run avg | 13.6 | 6.2 |
| Rhythm reused from an earlier measure | 31 of 46 | 24 of 50 |
| Radar stream / voltage / air / freeze / chaos | .38 / .52 / .26 / .40 / .07 | .37 / .47 / .08 / .26 / .04 |

## 4. Proposed changes

1. **Split `repeat` into `rhythm_repeat` and `arrow_repeat`.** Repeated music
   reuses the earlier rhythm (high, ~0.9) and only some of the arrows
   (Hard ~0.3, Easy ~0.6), with fresh arrows following the flow rules.
2. **Section intensity instead of loudness.** Score each measure by drum
   activity, bass presence and how different it sounds from its neighbours
   (novelty), so breakdowns and drops are found even in loud mastered songs.
   `energy_follow` would use it.
3. **`jump_clusters`.** Put jumps where a section starts or hits its peak, in
   short runs, instead of spreading them evenly. Paired with a `jump` budget
   that can reach Konami's ~10% on Hard.
4. **`jump_holds`.** Chance a big downbeat becomes a two-foot freeze (`2002`).
5. **`flow_runs`.** Longer uninterrupted runs: fewer jacks and breaks inside a
   section, jacks saved for repeated hits at section edges.
6. **A `konami` profile** using all of the above plus short 1-beat freezes on
   stabs, for songs like this.

## 5. Result (all six built)

Same song, Hard, `--profile konami` against Konami's Maniac:

| | Konami Maniac | stepgen konami Hard | stepgen base Hard |
|---|---|---|---|
| Notes/sec | 2.73 | 2.74 | 2.88 |
| Jumps % | 10.6 | 10.5 | 6.4 |
| Freezes | 36 | 33 | 24 |
| Jump freezes | 9 | 9 | 3 |
| Flow run avg | 13.6 | 8.2 | 5.5 |
| Rhythm reused | 31 of 46 | 24 of 50 | 24 of 50 |
| Radar stream / voltage / air / freeze / chaos | .38 / .52 / .26 / .40 / .07 | .42 / .47 / .28 / .37 / .02 | .42 / .53 / .18 / .27 / .08 |

Medium (konami) is 1.97 notes/sec against Another's 1.93, with 10% jumps (5.9)
and 33 freezes (30). Flow runs are still the biggest gap (Medium 4.9 vs 15.6):
Konami's long runs are steady beat notes, and stepgen still breaks them with
holds and rests more often.

Also added along the way: `beat_backbone`, which fills beat notes before
half-beats. Trance off-beat bass is louder than the kick, so without it the
charts skipped beats 1-2 and crammed 8ths into beats 3-4.

## 6. Follow-up: steps that follow the music

Correlation of where notes land with each part of the music (Hard, from
measure 12 on; higher means the steps sit on that sound):

| | kick | snare | lead synth | hi-hats |
|---|---|---|---|---|
| Konami Maniac | +.52 | +.35 | +.33 | -.23 |
| stepgen `konami` before | +.31 | +.17 | +.18 | -.04 |
| stepgen `konami` now | +.53 | +.32 | +.29 | -.21 |
| stepgen base Medium before | -.02 | +.32 | +.26 | +.46 |
| stepgen base Medium now | +.59 | +.47 | +.39 | -.07 |

Konami steps on the kick, snare and lead and stays off the hi-hats. stepgen was
scoring slots by all drum onsets, and in trance the off-beat hats are the
loudest onsets, so it stepped on them. Now slots are scored by kick, snare and
lead with hats nearly ignored, holds and jump freezes avoid covering strong
hits, and repeated bars are only copied where their hits line up.

Also: quick notes never jack. Quarter-beat repeats of one arrow are gone, and
half-beat jacks are down to about 2-5% of half-beat moves (Konami: 4%).
