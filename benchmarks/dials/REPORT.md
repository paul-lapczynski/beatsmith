# stepgen dial test report

Made by `dialtest.py report` from 16,731 charts (5,577 runs) on Sandstorm, Wrong Note, Yeah. Test design: [TESTPLAN.md](TESTPLAN.md). "S/N" below is a change divided by what changing only the seed does (the noise): under 1 is lost in the noise, 3 or more is clear.

## 1. Grades

Each control is rated on five questions (0-100 each), per chart, then averaged: **moves it** (does its claimed measurement change, 25% to 75%, against the noise), **same direction** (rank correlation across 0..100), **survives target** (effect with a difficulty target on, as a share of the effect with it off), **stays in its lane** (how little it moves other dials' measurements and, with a target on, the meter) and **every song**.

| Control | Grade | Easy | Medium | Hard | Hard: moves / direction / survives / lane / songs | Claim tested |
|---|---|---|---|---|---|---|
| **Repetition** | **A** (95) | 97 | 97 | 92 | 98 / 95 / 83 / 89 / 83 | rep_rhythm up, rep_arrows up |
| **Jumps** | **A** (91) | 97 | 90 | 85 | 100 / 95 / 35 / 70 / 100 | jump_pct up, jump_holds up |
| **Holds** | **A** (89) | 89 | 90 | 88 | 100 / 100 / 31 / 87 / 100 | hold_pct up |
| **Energy / arc** | **A** (87) | 97 | 81 | 84 | 100 / 85 / 61 / 86 / 67 | energy_corr up, energy_contrast up |
| **AI assist** | **B** (82) | 86 | 78 | 82 | 91 / 80 / 96 / 82 / 50 | ai_lock up, same_pos down |
| **Speed** | **C** (68) | 64 | 73 | 66 | 100 / 48 / 7 / 82 / 56 | quarter_pct up, half_pct up, stream up |
| **Footwork** | **C** (62) | 63 | 75 | 47 | 28 / 47 / 63 / 93 / 33 | walk_pct up, lr_pct up, jack_pct down |
| **Breathing room** | **D** (51) | 15 | 50 | 86 | 100 / 83 / 79 / 74 / 78 | run_mean down, rests up, stomps up |
| **Arrows follow (melody)** | **D** (45) | 49 | 48 | 37 | 12 / 50 / 51 / 87 / 17 | melody_lock up, pitch_follow up |
| **Groove** | **F** (38) | 45 | 41 | 30 | 7 / 33 / 41 / 87 / 11 | groove up, g_pattern up, g_locked up |

## 2. What each control really does

Hard chart, konami and patterns profiles, with the app's targets on (3/6/8) unless it says otherwise. Biggest changes first, 25% to 75% (off to 75% for Groove, Follow and AI).

### Groove — grade F

| Measurement | low | 75% | S/N |
|---|---|---|---|
| steps in the loudest quarter of bars / quietest quarter | 1.6 | 2.2 | 7.2 |
| steps per second | 3.2 | 3.0 | -2.4 |
| share of steps on the beat (%) | 52.1 | 54.7 | 2.3 |
| share of steps on half-beats, 8ths (%) | 39.8 | 38.0 | -2.1 |
| rests of 2 beats or more, per minute | 9.0 | 10.4 | 1.8 |
| stomps (quarter-note jumps from breathing) | 7.0 | 12.5 | 1.5 |
| stepgen's difficulty estimate | 7.9 | 7.7 | -1.3 |
| groove: runs end, you get a moment | 90.6 | 93.7 | 1.0 |

With no target: steps in the loudest quarter of bars / quietest quarter 2.2 → 3.1 (S/N 7.4); share of steps on half-beats, 8ths (%) 32.7 → 27.6 (S/N -6.8); share of steps on the beat (%) 65.4 → 70.3 (S/N 3.7); average length of a run (steps half a beat apart or closer) 4.3 → 3.8 (S/N -3.7).

Meter change 25→75%: -0.16 with a target, -0.16 without.

### Energy / arc — grade A

| Measurement | low | 75% | S/N |
|---|---|---|---|
| steps in the loudest quarter of bars / quietest quarter | 1.1 | 2.0 | 10.5 |
| steps climb through build-ups (rank correlation) | 0.5 | 0.9 | 6.5 |
| rests of 2 beats or more, per minute | 8.2 | 10.2 | 2.5 |
| steps per second | 3.2 | 3.1 | -2.3 |
| share of steps on the beat (%) | 55.1 | 52.9 | -1.9 |
| steps per bar follow the song's loudness (rank correlation) | 0.1 | 0.3 | 1.7 |
| groove: busy where loud | 52.7 | 57.9 | 1.7 |
| groove: rhythm comes back bar to bar | 80.6 | 77.4 | -1.6 |

With no target: steps in the loudest quarter of bars / quietest quarter 1.4 → 3.1 (S/N 13.7); steps climb through build-ups (rank correlation) 0.8 → 0.9 (S/N 9.2); beats spent holding, per minute 30.9 → 28.3 (S/N -4.4); steps per bar follow the song's loudness (rank correlation) 0.3 → 0.4 (S/N 3.8).

Meter change 25→75%: -0.11 with a target, -0.07 without.

### Jumps — grade A

| Measurement | low | 75% | S/N |
|---|---|---|---|
| jumps per 100 steps | 12.8 | 22.3 | 7.7 |
| jump freezes | 9.0 | 15.1 | 4.1 |
| steps per second | 3.3 | 3.1 | -3.1 |
| freezes per 100 steps | 3.7 | 5.6 | 3.1 |
| Left<->Right or Down<->Up moves per 100 steps | 29.5 | 24.5 | -2.8 |
| beats spent holding, per minute | 13.5 | 18.0 | 2.4 |
| share of steps on the beat (%) | 50.8 | 53.3 | 2.3 |
| taps under freezes, per 100 steps | 1.5 | 2.5 | 2.3 |

With no target: jumps per 100 steps 7.0 → 17.8 (S/N 18.4); jump freezes 3.1 → 9.0 (S/N 14.6); share of steps on quarter-beats, 16ths (%) 2.1 → 1.7 (S/N -6.7); freezes per 100 steps 7.9 → 9.4 (S/N 3.9).

Meter change 25→75%: 0.04 with a target, 0.16 without.

### Speed — grade C

| Measurement | low | 75% | S/N |
|---|---|---|---|
| share of steps on quarter-beats, 16ths (%) | 4.4 | 9.8 | 4.2 |
| share of steps on the beat (%) | 55.0 | 50.9 | -3.7 |
| groove: rhythm comes back bar to bar | 83.7 | 76.8 | -3.4 |
| rests of 2 beats or more, per minute | 7.7 | 10.1 | 3.2 |
| beats spent holding, per minute | 14.7 | 18.3 | 2.0 |
| steps in the loudest quarter of bars / quietest quarter | 1.7 | 1.6 | -1.8 |
| groove: runs end, you get a moment | 89.0 | 93.3 | 1.4 |
| freezes per 100 steps | 4.6 | 5.5 | 1.4 |

With no target: share of steps on quarter-beats, 16ths (%) 1.1 → 2.4 (S/N 19.3); share of steps on half-beats, 8ths (%) 28.6 → 35.7 (S/N 9.4); share of steps on the beat (%) 70.2 → 61.9 (S/N -6.4); beats spent holding, per minute 27.8 → 30.4 (S/N 4.6).

Meter change 25→75%: 0.07 with a target, 0.16 without.

### Breathing room — grade D

| Measurement | low | 75% | S/N |
|---|---|---|---|
| rests of 2 beats or more, per minute | 6.2 | 10.3 | 5.4 |
| runs longer than 8 steps, per minute | 8.8 | 5.3 | -3.4 |
| groove: runs end, you get a moment | 83.3 | 93.4 | 3.3 |
| average length of a run (steps half a beat apart or closer) | 8.4 | 6.5 | -3.2 |
| share of steps on half-beats, 8ths (%) | 41.0 | 38.3 | -2.9 |
| taps under freezes, per 100 steps | 2.9 | 1.7 | -2.8 |
| steps per second | 3.3 | 3.1 | -2.7 |
| stomps (quarter-note jumps from breathing) | 4.2 | 12.2 | 2.3 |

With no target: runs longer than 8 steps, per minute 4.2 → 0.4 (S/N -8.9); average length of a run (steps half a beat apart or closer) 5.0 → 3.9 (S/N -8.8); longest run of 8th notes (steps) 13.0 → 7.6 (S/N -5.4); share of steps on half-beats, 8ths (%) 34.1 → 31.6 (S/N -3.3).

Meter change 25→75%: -0.24 with a target, -0.37 without.

### Footwork — grade C

| Measurement | low | 75% | S/N |
|---|---|---|---|
| Left<->Right or Down<->Up moves per 100 steps | 21.7 | 27.6 | 3.4 |
| arrows move right as the tune rises (rank correlation) | 0.0 | -0.0 | -1.2 |
| runs longer than 8 steps, per minute | 6.9 | 7.9 | 0.9 |
| groove: rhythm comes back bar to bar | 77.4 | 78.9 | 0.8 |
| share of steps on half-beats, 8ths (%) | 39.2 | 39.8 | 0.7 |
| share of steps on quarter-beats, 16ths (%) | 8.7 | 7.8 | -0.7 |
| taps under freezes, per 100 steps | 2.0 | 2.3 | 0.5 |
| steps per bar follow the song's loudness (rank correlation) | 0.3 | 0.2 | -0.5 |

With no target: Left<->Right or Down<->Up moves per 100 steps 23.1 → 27.8 (S/N 1.5); jumps per 100 steps 12.9 → 13.4 (S/N 0.9); walk-downs/ups across all 4 arrows per 100 steps 4.8 → 4.4 (S/N -0.7); beats spent holding, per minute 28.7 → 28.3 (S/N -0.7).

Meter change 25→75%: -0.03 with a target, -0.01 without.

### Holds — grade A

| Measurement | low | 75% | S/N |
|---|---|---|---|
| taps under freezes, per 100 steps | 0.9 | 5.5 | 10.6 |
| beats spent holding, per minute | 12.1 | 28.6 | 9.0 |
| freezes per 100 steps | 4.3 | 7.7 | 5.6 |
| share of steps on half-beats, 8ths (%) | 39.5 | 37.6 | -2.1 |
| jacks (same arrow again) per 100 steps | 2.4 | 3.8 | 2.1 |
| steps in the loudest quarter of bars / quietest quarter | 1.5 | 1.6 | 2.1 |
| steps per second | 3.2 | 3.1 | -1.8 |
| share of steps on the beat (%) | 52.4 | 54.2 | 1.6 |

With no target: beats spent holding, per minute 17.8 → 36.6 (S/N 32.7); freezes per 100 steps 6.2 → 12.9 (S/N 17.8); taps under freezes, per 100 steps 2.9 → 6.2 (S/N 10.6); steps in the loudest quarter of bars / quietest quarter 2.8 → 2.1 (S/N -5.1).

Meter change 25→75%: -0.04 with a target, 0.06 without.

### Repetition — grade A

| Measurement | low | 75% | S/N |
|---|---|---|---|
| repeated sections: same arrows (%) | 21.2 | 39.6 | 3.5 |
| repeated sections: same rhythm (%) | 72.2 | 82.3 | 1.9 |
| jumps per 100 steps | 18.9 | 16.8 | -1.7 |
| average length of a run (steps half a beat apart or closer) | 7.6 | 7.1 | -0.9 |
| stomps (quarter-note jumps from breathing) | 11.2 | 8.6 | -0.7 |
| groove: busy where loud | 57.6 | 55.4 | -0.7 |
| groove: rhythm comes back bar to bar | 77.6 | 79.0 | 0.7 |
| runs longer than 8 steps, per minute | 8.2 | 7.5 | -0.7 |

With no target: repeated sections: same arrows (%) 24.9 → 41.3 (S/N 3.8); beats spent holding, per minute 30.6 → 28.4 (S/N -3.7); repeated sections: same rhythm (%) 76.4 → 85.7 (S/N 2.6); jumps per 100 steps 13.1 → 11.9 (S/N -2.0).

Meter change 25→75%: -0.04 with a target, -0.01 without.

### Arrows follow (melody) — grade D

| Measurement | low | 75% | S/N |
|---|---|---|---|
| rests of 2 beats or more, per minute | 9.0 | 11.1 | 2.7 |
| taps under freezes, per 100 steps | 2.3 | 1.4 | -2.2 |
| steps in the loudest quarter of bars / quietest quarter | 1.6 | 1.7 | 1.7 |
| jacks (same arrow again) per 100 steps | 3.1 | 2.2 | -1.3 |
| steps per second | 3.2 | 3.1 | -1.2 |
| arrow variety: how unpredictable the next arrow is (0..1) | 0.9 | 0.8 | -1.2 |
| steps on melody note starts (percentile, 50 = random) | 44.5 | 45.5 | 1.1 |
| share of jumps in the first 2 bars of a section | 21.8 | 23.9 | 1.0 |

With no target: share of steps on quarter-beats, 16ths (%) 1.9 → 2.9 (S/N 14.6); jump freezes 9.3 → 11.3 (S/N 4.9); beats spent holding, per minute 28.7 → 31.1 (S/N 4.3); groove: rhythm comes back bar to bar 82.4 → 78.2 (S/N -2.5).

Meter change 25→75%: -0.05 with a target, 0.01 without.

### AI assist — grade B

| Measurement | low | 75% | S/N |
|---|---|---|---|
| share of jumps in the first 2 bars of a section | 21.8 | 25.9 | 2.0 |
| groove: steps on the song's hits | 53.8 | 52.0 | -1.6 |
| share of steps on the beat (%) | 52.1 | 53.9 | 1.5 |
| groove: rhythm comes back bar to bar | 78.5 | 81.6 | 1.5 |
| beats spent holding, per minute | 17.1 | 14.6 | -1.4 |
| steps on melody note starts (percentile, 50 = random) | 44.5 | 43.3 | -1.3 |
| share of steps on half-beats, 8ths (%) | 39.8 | 38.8 | -1.1 |
| arrows move right as the tune rises (rank correlation) | -0.0 | 0.0 | 1.0 |

With no target: jump freezes 9.3 → 7.8 (S/N -3.7); average length of a run (steps half a beat apart or closer) 4.3 → 4.5 (S/N 1.7); repeated sections: same rhythm (%) 84.6 → 89.7 (S/N 1.5); steps per second 2.6 → 2.6 (S/N 1.4).

Meter change 25→75%: -0.02 with a target, 0.10 without.

## 3. Do the Feel sliders still rule with AI assist or Follow on?

Retention = the slider's effect on its own measurement with AI (or Follow) at that level, divided by its effect at 0. 100% means the feel works exactly as well; under 50% means the AI or melody is overriding it.

**AI assist**

| Feel slider | Measured | Effect at 0 | ai 50 | ai 100 |
|---|---|---|---|---|
| Energy / arc | energy_corr | 0.11 | 150% | 127% |
| Jumps | jump_pct | 10.01 | 110% | 92% |
| Speed | quarter_pct | 2.11 | 88% | 75% |
| Breathing room | run_mean | 0.64 | 76% | 74% |
| Footwork | walk_pct | 0.60 | 53% | 69% |
| Holds | hold_pct | 12.11 | 91% | 91% |
| Repetition | rep_rhythm | 12.01 | 101% | 99% |

**Arrows follow (melody)**

| Feel slider | Measured | Effect at 0 | follow 50 | follow 100 |
|---|---|---|---|---|
| Energy / arc | energy_corr | 0.11 | 113% | 119% |
| Jumps | jump_pct | 10.01 | 106% | 109% |
| Speed | quarter_pct | 2.11 | 91% | 99% |
| Breathing room | run_mean | 0.64 | 46% | 17% |
| Footwork | walk_pct | 0.58 | -16% | 47% |
| Holds | hold_pct | 12.11 | 100% | 95% |
| Repetition | rep_rhythm | 12.01 | 74% | 68% |

**AI assist x Follow** (all charts): change from the plain chart's step positions, and where steps land

| AI | Follow | same step positions | on AI moments | on melody | on drums | meter |
|---|---|---|---|---|---|---|
| 0 | 0 | 100% | 93.9 | 45.5 | 89.2 | 5.63 |
| 0 | 50 | 78% | 93.9 | 46.3 | 89.5 | 5.50 |
| 0 | 100 | 70% | 93.7 | 48.2 | 88.8 | 5.57 |
| 50 | 0 | 71% | 94.0 | 44.9 | 88.6 | 5.60 |
| 50 | 50 | 70% | 94.2 | 45.3 | 88.4 | 5.61 |
| 50 | 100 | 67% | 94.2 | 45.9 | 88.6 | 5.57 |
| 100 | 0 | 67% | 94.1 | 44.3 | 88.5 | 5.59 |
| 100 | 50 | 67% | 94.1 | 44.3 | 88.4 | 5.60 |
| 100 | 100 | 66% | 94.1 | 44.2 | 88.4 | 5.59 |

## 4. What Groove actually does

| Chart | Groove | meter score | pattern | locked | breathing | footing | effort | avg run | meter | secs/run |
|---|---|---|---|---|---|---|---|---|---|---|
| Easy | off | 77.6 | 85 | 49 | 100 | 100 | 52 | 1.5 | 3.06 | 0.8 |
| Easy | 25% | 78.5 | 89 | 49 | 100 | 100 | 53 | 1.3 | 2.90 | 1.8 |
| Easy | 50% | 79.0 | 88 | 49 | 100 | 100 | 54 | 1.3 | 2.90 | 1.9 |
| Easy | 75% | 78.7 | 90 | 50 | 100 | 100 | 52 | 1.6 | 3.01 | 3.2 |
| Easy | 100% | 78.8 | 88 | 50 | 100 | 100 | 53 | 1.6 | 3.00 | 3.4 |
| Medium | off | 78.1 | 83 | 50 | 100 | 99 | 53 | 3.6 | 6.02 | 0.8 |
| Medium | 25% | 78.9 | 87 | 50 | 100 | 100 | 54 | 3.6 | 6.07 | 1.8 |
| Medium | 50% | 79.1 | 86 | 50 | 100 | 99 | 55 | 3.5 | 6.07 | 2.0 |
| Medium | 75% | 79.1 | 88 | 51 | 100 | 100 | 55 | 3.4 | 6.04 | 3.2 |
| Medium | 100% | 79.3 | 88 | 53 | 100 | 100 | 53 | 3.3 | 6.01 | 3.4 |
| Hard | off | 76.5 | 78 | 54 | 91 | 98 | 58 | 7.4 | 7.86 | 0.9 |
| Hard | 25% | 77.7 | 80 | 54 | 93 | 98 | 59 | 7.1 | 7.82 | 1.9 |
| Hard | 50% | 77.4 | 79 | 54 | 95 | 98 | 58 | 6.7 | 7.69 | 2.0 |
| Hard | 75% | 77.5 | 80 | 55 | 94 | 99 | 58 | 7.2 | 7.66 | 3.2 |
| Hard | 100% | 77.7 | 78 | 55 | 95 | 99 | 58 | 6.6 | 7.62 | 3.4 |

**Groove on top of the Feel sliders**: each slider's effect on its own measurement with Groove off and at 75%. The sliders are applied after Groove, so they should keep working.

| Feel slider | Measured | effect, groove off | effect, groove 75% | kept |
|---|---|---|---|---|
| Energy / arc | energy_corr | 0.11 | 0.20 | 194% |
| Jumps | jump_pct | 10.01 | 10.12 | 101% |
| Speed | quarter_pct | 2.11 | 2.50 | 119% |
| Breathing room | run_mean | 0.64 | 0.36 | 56% |
| Footwork | walk_pct | 0.62 | 0.32 | 52% |
| Holds | hold_pct | 12.11 | 12.11 | 100% |
| Repetition | rep_rhythm | 12.01 | 10.60 | 88% |

## 5. How the difficulty number changes the song

Every chart aimed at 1 to 10 (both profiles, 3 songs, 3 seeds). stepgen rates each try and turns one intensity dial (`with_intensity`) until the rating lands: 0 is the profile as written, up to +1 adds steps, jumps and 8th runs and takes away holds, past +0.6 it adds quarter-beat bursts, past +1 16th streams; below -0.4 it drops to beat notes only.

| Chart | Aim | got | miss | within 0.75 | density | jump | half_beats | quarter_beats | hold_rate | grid | steps/s | 8ths % | 16ths % | jumps % | freezes % | longest 8th run |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Easy | 1 | 1.07 | 0.07 | 100% | 0.21 | 0.07 | 0.00 | 0.00 | 0.207 | 1.0 | 0.42 | 0 | 0.0 | 3 | 22 | 1 |
| Easy | 2 | 1.96 | 0.14 | 100% | 0.39 | 0.12 | 0.00 | 0.00 | 0.157 | 1.0 | 0.81 | 0 | 0.0 | 3 | 15 | 1 |
| Easy | 3 | 3.06 | 0.13 | 100% | 0.63 | 0.19 | 0.00 | 0.00 | 0.123 | 1.6 | 1.28 | 3 | 0.0 | 4 | 12 | 2 |
| Easy | 4 | 4.14 | 0.19 | 100% | 0.75 | 0.21 | 0.00 | 0.00 | 0.110 | 2.0 | 1.47 | 8 | 0.0 | 5 | 11 | 3 |
| Easy | 5 | 4.96 | 0.09 | 100% | 1.23 | 0.28 | 0.00 | 0.00 | 0.085 | 2.3 | 1.84 | 13 | 0.0 | 7 | 8 | 5 |
| Easy | 6 | 5.97 | 0.10 | 100% | 2.23 | 0.40 | 0.12 | 0.00 | 0.039 | 3.7 | 2.32 | 21 | 1.2 | 10 | 5 | 7 |
| Easy | 7 | 6.80 | 0.24 | 100% | 2.40 | 0.42 | 0.48 | 0.13 | 0.026 | 4.0 | 2.81 | 35 | 2.1 | 10 | 3 | 10 |
| Easy | 8 | 7.23 | 0.77 | 39% | 2.40 | 0.42 | 0.60 | 0.20 | 0.026 | 4.0 | 3.02 | 40 | 2.4 | 10 | 3 | 20 |
| Easy | 9 | 8.75 | 0.34 | 83% | 3.71 | 0.42 | 0.95 | 0.20 | 0.026 | 4.0 | 3.80 | 39 | 13.6 | 8 | 3 | 16 |
| Easy | 10 | 9.39 | 0.61 | 67% | 4.20 | 0.42 | 1.00 | 0.20 | 0.026 | 4.0 | 4.25 | 37 | 20.3 | 6 | 3 | 17 |
| Medium | 1 | 1.51 | 0.51 | 67% | 0.26 | 0.09 | 0.25 | 0.07 | 0.204 | 1.0 | 0.52 | 0 | 0.0 | 4 | 20 | 2 |
| Medium | 2 | 2.05 | 0.17 | 100% | 0.35 | 0.14 | 0.25 | 0.07 | 0.185 | 1.0 | 0.71 | 1 | 0.0 | 4 | 18 | 2 |
| Medium | 3 | 2.98 | 0.10 | 100% | 0.47 | 0.19 | 0.25 | 0.07 | 0.166 | 1.0 | 0.98 | 4 | 0.0 | 5 | 17 | 2 |
| Medium | 4 | 4.11 | 0.17 | 100% | 0.71 | 0.27 | 0.25 | 0.07 | 0.137 | 1.3 | 1.46 | 9 | 0.0 | 7 | 14 | 4 |
| Medium | 5 | 5.09 | 0.17 | 100% | 0.88 | 0.30 | 0.25 | 0.07 | 0.123 | 2.0 | 1.74 | 19 | 0.0 | 7 | 13 | 6 |
| Medium | 6 | 6.04 | 0.12 | 100% | 1.47 | 0.38 | 0.25 | 0.07 | 0.088 | 2.0 | 2.21 | 25 | 1.3 | 9 | 11 | 7 |
| Medium | 7 | 7.02 | 0.14 | 100% | 3.39 | 0.52 | 0.53 | 0.16 | 0.034 | 3.4 | 2.82 | 34 | 3.4 | 14 | 5 | 10 |
| Medium | 8 | 7.73 | 0.31 | 100% | 4.00 | 0.56 | 0.82 | 0.25 | 0.023 | 4.0 | 3.23 | 41 | 6.8 | 14 | 4 | 17 |
| Medium | 9 | 8.89 | 0.18 | 100% | 5.66 | 0.56 | 0.93 | 0.26 | 0.023 | 4.0 | 3.72 | 38 | 14.1 | 12 | 4 | 17 |
| Medium | 10 | 9.54 | 0.46 | 67% | 7.00 | 0.56 | 1.00 | 0.28 | 0.023 | 4.0 | 4.24 | 35 | 21.8 | 10 | 4 | 12 |
| Hard | 1 | 2.39 | 1.39 | 17% | 0.34 | 0.26 | 0.55 | 0.35 | 0.134 | 1.0 | 0.72 | 5 | 0.0 | 8 | 13 | 2 |
| Hard | 2 | 2.53 | 0.53 | 67% | 0.35 | 0.27 | 0.55 | 0.35 | 0.132 | 1.0 | 0.75 | 5 | 0.0 | 8 | 13 | 2 |
| Hard | 3 | 3.03 | 0.12 | 100% | 0.47 | 0.32 | 0.55 | 0.35 | 0.119 | 1.0 | 0.98 | 5 | 0.0 | 8 | 12 | 2 |
| Hard | 4 | 4.04 | 0.09 | 100% | 0.73 | 0.40 | 0.55 | 0.35 | 0.101 | 1.0 | 1.50 | 4 | 0.0 | 10 | 11 | 3 |
| Hard | 5 | 4.97 | 0.27 | 100% | 1.00 | 0.45 | 0.55 | 0.35 | 0.087 | 1.3 | 1.93 | 12 | 0.0 | 12 | 10 | 4 |
| Hard | 6 | 6.20 | 0.24 | 100% | 1.11 | 0.47 | 0.55 | 0.35 | 0.082 | 2.0 | 2.24 | 31 | 1.5 | 12 | 10 | 7 |
| Hard | 7 | 7.09 | 0.11 | 100% | 2.68 | 0.59 | 0.55 | 0.35 | 0.048 | 2.6 | 2.77 | 36 | 3.4 | 15 | 7 | 10 |
| Hard | 8 | 7.91 | 0.16 | 100% | 4.97 | 0.72 | 0.78 | 0.44 | 0.018 | 3.8 | 3.22 | 40 | 7.7 | 18 | 5 | 17 |
| Hard | 9 | 9.00 | 0.09 | 100% | 6.91 | 0.74 | 0.87 | 0.48 | 0.015 | 4.0 | 3.61 | 37 | 14.8 | 17 | 5 | 15 |
| Hard | 10 | 9.56 | 0.44 | 100% | 7.95 | 0.74 | 0.88 | 0.51 | 0.015 | 4.0 | 4.06 | 35 | 20.0 | 14 | 5 | 13 |

**Grade A** (95): lands within 0.75 of the number asked 96% of the time for 2 to 8 and 90% over 1 to 10; always in order (rank correlation 1.00).


With no target the profiles rate: konami Easy 2.5, konami Hard 6.3, konami Medium 5.4, patterns Easy 2.8, patterns Hard 7.1, patterns Medium 6.0.

## 6. The Advanced settings

Each setting pinned to 25/50/75% of its range on all three charts (konami profile, seed 1, 3 songs). S/N is the biggest change it makes to any measurement between 25% and 75%.

| Setting | Kind | Moved by slider | Target rewrites it | S/N no target | S/N with target | Moves most (no target) |
|---|---|---|---|---|---|---|
| `arrow_repeat` | slider-covered | repetition | – | 4.5 | 3.4 | repeated sections: same arrows (%) (+); jumps per 100 steps (−) |
| `beat_backbone` | slider-covered | groove, speed | – | 2.0 | 5.6 | share of steps on half-beats, 8ths (%) (−); share of steps on quarter-beats, 16ths (%) (−) |
| `crescendo` | slider-covered | energy | – | 5.2 | 2.8 | steps climb through build-ups (rank correlation) (+); share of steps on quarter-beats, 16ths (%) (−) |
| `energy_follow` | slider-covered | groove, energy | – | 7.0 | 12.1 | steps in the loudest quarter of bars / quietest quarter (+); share of steps on quarter-beats, 16ths (%) (+) |
| `flow_runs` | slider-covered | footwork | – | 1.6 | 3.1 | jump freezes (+); arrows move right as the tune rises (rank correlation) (+) |
| `flow_spice` | slider-covered | speed | yes | 4.0 | 3.1 | beats spent holding, per minute (+); steps climb through build-ups (rank correlation) (−) |
| `groove_tries` | slider-covered | groove | – | 2.6 | 0.0 | walk-downs/ups across all 4 arrows per 100 steps (−); steps in the loudest quarter of bars / quietest quarter (−) |
| `half_beats` | slider-covered | speed | yes | 6.7 | 5.3 | beats spent holding, per minute (+); freezes per 100 steps (+) |
| `hold_rate` | slider-covered | holds | yes | 2.4 | 11.4 | jump freezes (−); stomps (quarter-note jumps from breathing) (−) |
| `jump_clusters` | slider-covered | jumps | – | 7.6 | 3.3 | share of steps on quarter-beats, 16ths (%) (−); share of jumps in the first 2 bars of a section (+) |
| `jump_holds` | slider-covered | jumps | – | 22.0 | 8.7 | jump freezes (+); freezes per 100 steps (+) |
| `phrase_shape` | slider-covered | groove, energy | – | 2.4 | 2.0 | share of steps on quarter-beats, 16ths (%) (+); arrows move right as the tune rises (rank correlation) (+) |
| `recovery` | slider-covered | groove, breathing | – | 2.4 | 6.4 | jump freezes (−); repeated sections: same arrows (%) (+) |
| `rest_bars` | slider-covered | energy | – | 4.1 | 4.9 | jump freezes (−); steps in the loudest quarter of bars / quietest quarter (+) |
| `rhythm_lock` | slider-covered | groove | – | 2.1 | 2.3 | jumps per 100 steps (+); jump freezes (−) |
| `rhythm_repeat` | slider-covered | groove, repetition | – | 3.6 | 3.9 | walk-downs/ups across all 4 arrows per 100 steps (−); beats spent holding, per minute (−) |
| `run_breaks` | slider-covered | groove, breathing | – | 3.1 | 5.7 | share of steps on half-beats, 8ths (%) (−); average length of a run (steps half a beat apart or closer) (−) |
| `side_to_side` | slider-covered | footwork | – | 2.2 | 4.0 | Left<->Right or Down<->Up moves per 100 steps (−); walk-downs/ups across all 4 arrows per 100 steps (+) |
| `sixteenths` | slider-covered | speed | – | 5.2 | 6.4 | share of steps on quarter-beats, 16ths (%) (+); Left<->Right or Down<->Up moves per 100 steps (−) |
| `stomps` | slider-covered | groove, breathing | – | 2.8 | 5.7 | stomps (quarter-note jumps from breathing) (+); beats spent holding, per minute (+) |
| `flow` | Advanced-only | – | – | 1.0 | 0.5 | walk-downs/ups across all 4 arrows per 100 steps (+); arrows move right as the tune rises (rank correlation) (+) |
| `hold_max` | Advanced-only | – | – | 43.4 | 15.7 | beats spent holding, per minute (+); freezes per 100 steps (+) |
| `hold_min` | Advanced-only | – | – | 42.7 | 15.0 | beats spent holding, per minute (−); freezes per 100 steps (−) |
| `max_nps` | Advanced-only | – | yes | 0.0 | 3.0 | walk-downs/ups across all 4 arrows per 100 steps (−); taps under freezes, per 100 steps (−) |
| `max_run16` | Advanced-only | – | – | 0.0 | 2.6 | walk-downs/ups across all 4 arrows per 100 steps (−); taps under freezes, per 100 steps (−) |
| `density` | overwritten by target | – | yes | 32.7 | 2.7 | share of steps on half-beats, 8ths (%) (+); beats spent holding, per minute (+) |
| `grid` | overwritten by target | – | yes | 31.7 | 3.1 | share of steps on half-beats, 8ths (%) (+); share of steps on the beat (%) (−) |
| `jump` | overwritten by target | jumps | yes | 23.7 | 9.1 | jump freezes (+); jumps per 100 steps (+) |
| `min_gap` | overwritten by target | – | yes | 26.5 | 4.5 | share of steps on half-beats, 8ths (%) (−); share of steps on the beat (%) (+) |
| `quarter_beats` | overwritten by target | speed | yes | 16.5 | 2.4 | share of steps on quarter-beats, 16ths (%) (+); beats spent holding, per minute (+) |
| `hold_complexity` | no effect found | – | – | 0.0 | 0.0 | walk-downs/ups across all 4 arrows per 100 steps (−); taps under freezes, per 100 steps (−) |
| `hold_free_foot` | no effect found | – | – | 0.0 | 0.0 | walk-downs/ups across all 4 arrows per 100 steps (−); taps under freezes, per 100 steps (−) |
| `intensity_variation` | no effect found | – | – | 0.0 | 0.0 | walk-downs/ups across all 4 arrows per 100 steps (−); taps under freezes, per 100 steps (−) |
| `jack_max` | no effect found | – | – | 0.0 | 0.0 | walk-downs/ups across all 4 arrows per 100 steps (−); taps under freezes, per 100 steps (−) |
| `jacks` | no effect found | groove, footwork | – | 0.5 | 0.0 | arrow variety: how unpredictable the next arrow is (0..1) (+); jacks (same arrow again) per 100 steps (+) |
| `meter_max` | no effect found | – | – | 0.0 | 0.0 | walk-downs/ups across all 4 arrows per 100 steps (−); taps under freezes, per 100 steps (−) |
| `meter_min` | no effect found | – | – | 0.0 | 0.0 | walk-downs/ups across all 4 arrows per 100 steps (−); taps under freezes, per 100 steps (−) |

**The Advanced table vs what a chart is really made with.** With a target on, the app shows each setting after the profile and sliders, but the target then rewrites some of them. Typical gap on Hard (app default targets):

| Setting | shown (mean) | used (mean) | charts where they differ |
|---|---|---|---|
| `density` | 1.32 | 4.96 | 100% |
| `jump` | 0.50 | 0.71 | 100% |
| `half_beats` | 0.55 | 0.77 | 43% |
| `quarter_beats` | 0.35 | 0.43 | 43% |
| `hold_rate` | 0.08 | 0.02 | 98% |
| `max_nps` | 5.50 | 4.53 | 89% |
| `flow_spice` | 0.35 | 0.40 | 43% |
| `grid` | 2.00 | 3.78 | 89% |

**Pinning a setting in Advanced freezes its slider** (effect of the slider 25→75% on its main measurement, with the setting free and pinned at 0.3):

| Slider | Pinned | Measured | free, target | free, no target | pinned, target | pinned, no target |
|---|---|---|---|---|---|---|
| Breathing room | `run_breaks` | run_mean | 0.64 | 0.19 | -0.04 | -0.01 |
| Jumps | `jump` | jump_pct | 10.01 | 11.02 | -0.20 | -0.39 |
| Speed | `half_beats` | quarter_pct | 2.11 | 0.38 | 1.88 | 0.40 |

## 7. Overlaps and conflicts between controls

Settings moved by more than one slider (Groove applies first, then the Feel sliders from where Groove left them, then Advanced pins, then the target):

| Setting | Sliders (direction toward 100%) |  | Target rewrites it too |
|---|---|---|---|
| `beat_backbone` | groove (up), speed (down) | **opposite directions** | – |
| `energy_follow` | groove (up), energy (up) | same direction | – |
| `jacks` | groove (down), footwork (down) | same direction | – |
| `phrase_shape` | groove (up), energy (up) | same direction | – |
| `recovery` | groove (up), breathing (up) | same direction | – |
| `rhythm_repeat` | groove (up), repetition (up) | same direction | – |
| `run_breaks` | groove (up), breathing (up) | same direction | – |
| `stomps` | groove (up), breathing (up) | same direction | – |

**Jumps x Breathing room** (all charts, mean; rows jumps, columns breathing)

|  | breathing 25 | breathing 50 | breathing 75 |
|---|---|---|---|
| jumps 25 | jump_pct 7.6 · run_mean 4.7 | jump_pct 8.5 · run_mean 4.5 | jump_pct 8.5 · run_mean 4.1 |
| jumps 50 | jump_pct 12.7 · run_mean 4.3 | jump_pct 13.1 · run_mean 3.9 | jump_pct 13.7 · run_mean 3.6 |
| jumps 75 | jump_pct 18.2 · run_mean 4.0 | jump_pct 18.5 · run_mean 3.7 | jump_pct 18.7 · run_mean 3.5 |

**Holds x Breathing room** (all charts, mean; rows holds, columns breathing)

|  | breathing 25 | breathing 50 | breathing 75 |
|---|---|---|---|
| holds 25 | hold_pct 7.9 · run_mean 4.4 | hold_pct 8.2 · run_mean 4.0 | hold_pct 8.1 · run_mean 3.9 |
| holds 50 | hold_pct 14.9 · run_mean 4.3 | hold_pct 15.1 · run_mean 3.9 | hold_pct 14.4 · run_mean 3.6 |
| holds 75 | hold_pct 20.6 · run_mean 3.8 | hold_pct 20.3 · run_mean 3.7 | hold_pct 20.3 · run_mean 3.6 |

**Speed x Footwork** (all charts, mean; rows speed, columns footwork)

|  | footwork 25 | footwork 50 | footwork 75 |
|---|---|---|---|
| speed 25 | quarter_pct 1.4 · walk_pct 4.0 | quarter_pct 1.4 · walk_pct 4.2 | quarter_pct 1.5 · walk_pct 4.3 |
| speed 50 | quarter_pct 2.8 · walk_pct 3.6 | quarter_pct 2.8 · walk_pct 3.7 | quarter_pct 2.7 · walk_pct 4.2 |
| speed 75 | quarter_pct 3.3 · walk_pct 3.4 | quarter_pct 3.5 · walk_pct 3.3 | quarter_pct 3.5 · walk_pct 3.4 |

**Energy / arc x Repetition** (all charts, mean; rows energy, columns repetition)

|  | repetition 25 | repetition 50 | repetition 75 |
|---|---|---|---|
| energy 25 | energy_corr 0.3 · rep_rhythm 73.1 | energy_corr 0.3 · rep_rhythm 83.8 | energy_corr 0.3 · rep_rhythm 84.6 |
| energy 50 | energy_corr 0.4 · rep_rhythm 71.3 | energy_corr 0.4 · rep_rhythm 82.6 | energy_corr 0.4 · rep_rhythm 83.3 |
| energy 75 | energy_corr 0.5 · rep_rhythm 68.6 | energy_corr 0.4 · rep_rhythm 80.5 | energy_corr 0.4 · rep_rhythm 83.4 |

## 8. Random sample: which control moves what

Share of each measurement's change (Hard, all songs) explained by each control across 450 random settings (standardized regression, main effects plus pairwise products). R² is how much the controls explain at all; the rest is song and seed.

| Measurement | R² | energy | jumps | speed | breathing | footwork | holds | repetition | groove | follow | ai | target | strongest interactions |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| steps on the AI model's likeliest moments | 0.95 | 5 | 2 | 5 | 2 | 1 | 2 | 4 | 2 | 2 | 3 | **72** |  |
| steps in the loudest quarter of bars / quietest quarter | 0.62 | **65** | 1 | 4 | 4 | 3 | 2 | 2 | 7 | 2 | 2 | 7 |  |
| steps per bar follow the song's loudness | 0.66 | **37** | 2 | 1 | 8 | 1 | 12 | 1 | 3 | 3 | 2 | **29** | energy×groove -0.10 |
| groove: steps on the song's hits | 0.58 | **28** | 5 | 4 | 1 | 2 | 3 | 2 | 4 | 1 | 5 | **44** | footwork×ai +0.08 |
| groove: rhythm comes back bar to bar | 0.71 | 4 | 2 | **25** | 4 | 1 | 6 | 5 | 3 | 3 | 4 | **43** | speed×holds +0.10, breathing×target -0.10 |
| groove meter | 0.72 | 2 | 3 | 3 | 5 | 1 | 2 | 2 | 2 | 1 | 2 | **78** | jumps×target +0.11, holds×target +0.11 |
| share of steps on half-beats, 8ths | 0.66 | 2 | 1 | 4 | 1 | 2 | 1 | 1 | 2 | 1 | 2 | **82** | speed×target -0.18, energy×target -0.11 |
| freezes per 100 steps | 0.81 | 0 | 11 | 1 | 1 | 0 | **59** | 0 | 1 | 0 | 1 | **26** | holds×target -0.22 |
| jacks | 0.50 | 3 | 9 | 9 | 7 | **39** | 2 | 3 | 2 | 1 | 3 | 22 | footwork×target +0.24, repetition×ai +0.11 |
| jump freezes | 0.81 | 1 | **67** | 0 | 1 | 0 | 6 | 0 | 1 | 0 | 1 | 21 | jumps×target +0.12, jumps×holds -0.09 |
| jumps per 100 steps | 0.84 | 0 | **87** | 2 | 2 | 0 | 1 | 1 | 1 | 0 | 1 | 4 |  |
| Left<->Right or Down<->Up moves per 100 steps | 0.77 | 1 | **29** | 1 | 2 | **61** | 2 | 1 | 1 | 1 | 1 | 1 |  |
| steps on melody note starts | 0.52 | 15 | 3 | 8 | 3 | 3 | 4 | 2 | 3 | 4 | **46** | 9 | ai×target +0.15, holds×target +0.12 |
| stepgen's difficulty estimate | 0.92 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **97** |  |
| steps per second | 0.90 | 1 | 6 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | **87** | jumps×target -0.08 |
| arrows move right as the tune rises | 0.13 | 18 | 17 | 6 | 9 | 9 | 6 | 7 | 12 | 6 | 4 | 7 | energy×jumps +0.15, energy×footwork +0.11 |
| share of steps on quarter-beats, 16ths | 0.80 | 1 | 3 | 11 | 1 | 0 | 0 | 0 | 1 | 0 | 1 | **80** | speed×target +0.20, jumps×target -0.10 |
| repeated sections: same arrows | 0.75 | 1 | 0 | 0 | 1 | 1 | 1 | **92** | 2 | 1 | 1 | 2 |  |
| repeated sections: same rhythm | 0.66 | 2 | 5 | 5 | 2 | 1 | 5 | **53** | 3 | 3 | 6 | 15 | repetition×ai +0.12, energy×groove -0.10 |
| rests of 2 beats or more, per minute | 0.78 | 1 | 4 | 8 | 2 | 1 | **45** | 2 | 2 | 1 | 1 | **34** | breathing×target +0.09 |
| average length of a run | 0.83 | 1 | 10 | 1 | 5 | 0 | 6 | 0 | 0 | 0 | 1 | **75** | jumps×target -0.23, holds×target -0.16 |
| stomps | 0.55 | 1 | 5 | 2 | **37** | 1 | 7 | 8 | 4 | 4 | 2 | **29** | breathing×target +0.13, holds×target -0.11 |
| longest run of 8th notes | 0.61 | 1 | 3 | 7 | 16 | 3 | 6 | 2 | 5 | 1 | 1 | **57** | speed×target -0.19, holds×target -0.10 |
| walk-downs/ups across all 4 arrows per 100 steps | 0.51 | 3 | **68** | 2 | 1 | 4 | 4 | 2 | 4 | 3 | 1 | 9 | footwork×groove +0.11, holds×target +0.09 |

