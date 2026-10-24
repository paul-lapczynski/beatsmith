# Dial test re-run on the dial fixes (PR #6)

The same plan as the first run (5,577 runs, 3 songs, konami/power profiles,
targets on and off) on stepgen with PR #6 applied. Charts made with no
difficulty target came out identical to before, so everything below is
what the fixes changed.

## Grades

| Control | Before | After | Why it moved |
|---|---|---|---|
| Difficulty number | A (94) | A (96) | within 0.75 of the number from 1 to 10: 80% before, 89% now |
| Jumps | A (90) | A (91) | |
| Energy | A (86) | A (89) | |
| Holds | A (90) | A (88) | |
| Repetition | A (96) | A (90) | weaker on Hard with a target; not looked into yet |
| AI assist | B (83) | B (83) | |
| Speed | C (70) | C (69) | **not fixed on Hard 8** (below) |
| Footwork | B (72) | **D (51)** | lost its jacks control when `jacks` was retired (below) |
| Breathing room | D (50) | D (47) | still nothing on Easy; on Hard with a target it now holds up much better ("survives target" 58 to 84) |
| Groove | D (42) | F (34) | lost its stomps and jacks moves; it still doesn't move the groove meter |
| Arrows follow | D (44) | F (40) | the dial test runs without stems; with stems it works (follow-stems-results.txt) |

## What worked

- **9 and 10 are reachable now, almost.** Hard aimed at 9 rates 8.79 (was
  8.49), aimed at 10 rates 9.22 (was 8.80). 1 to 8 is unchanged.
- **Breathing room on Hard with a target** keeps most of its effect, and
  100% no longer piles on stomps: 14 per Hard chart at 100% (was 27).

## What didn't, or went too far

1. **Speed still loses to the target on Hard 8.** With a target, 8ths on Hard
   are about 40% of steps whatever Speed says (0% to 100%), same as before.
   Hard 8 needs the "Speed raise" stage on these songs, so the target still
   sets half_beats. Medium 6 also ignores Speed until 100%. Odd new detail:
   on Hard 8, Speed **0** gets more 16ths (8.1%) than Speed 25 (4.2%),
   probably because the target goes past stage 3 when Speed starts low.
2. **Hard 9 and 10 lean hard on 16ths:** 25% of steps at 9 and 35% at 10
   (was 14% and 17%). That's likely heavier than Konami's own 9s; worth checking against real charts.
3. **`jacks` wasn't dead, only weak.** The first run's Advanced test moved it
   from 0.25 to 0.75 and saw a small change (signal-to-noise 0.5, under the
   cut-off), so it was listed as "no effect". But the Footwork slider swings
   it from 0.6 to 0, and that did cut jacks (7.4 to 2.9 per 100 steps on
   Easy). Retiring it took that away, which is most of Footwork's drop.
   `flow` was the same kind of borderline (0.9) but its slider effect was
   tiny too; the others really showed nothing.

## Suggested next steps

- Bring `jacks` back (and make it stronger: your Wrong Note Hard has 12 jacks
  per 100 steps, stepgen's most was about 9, on Easy with Footwork at 0).
- Let the target reach Hard 8 without the Speed stage: more density and
  jumps first, Speed only as the last resort.
- Cap 16ths at 9 and 10 nearer to Konami's own charts.

## Second re-run: the follow-up fixes (jacks back, Speed and 16ths)

| Control | First run | PR #6 | Follow-up |
|---|---|---|---|
| Footwork | B (72) | D (51) | C (64): jacks is back (Easy, no target: 5.7 to 3.0 per 100 steps across the slider) |
| Repetition | A (96) | A (90) | A (97) |
| Speed | C (70) | C (69) | C (68): 16ths now follow Speed on Hard 8 (0%, 3.7, 7.4, 8.9, 10.8% from Speed 0 to 100); 8ths still about 40% whatever Speed says, because the target needs them to reach 8 |
| Groove | D (42) | F (34) | F (38) |
| Breathing room | D (50) | D (47) | D (51) |
| Difficulty number | A (94) | A (96) | A (92) |

**The 16th cap undid the 9 and 10 gain.** With 16ths stopped at Konami's
75th percentile (16% of steps at 9, 20% at 10), Hard aimed at 9 rates 8.48
and at 10 rates 8.78, back to where they were before PR #6. 16ths: 15% at 9,
20% at 10 (PR #6 had 25% and 35%). Within 0.75 of the number from 1 to 10:
79% (PR #6: 89%). So on these songs it's one or the other: Konami-like 16ths,
or reaching 9 and 10.

## Third re-run: main after #10 (9s and 10s without more 16ths)

Grades: Difficulty A (95), Jumps A, Holds A, Energy A, Repetition A, AI B, Footwork C, Speed C, Breathing D, Follow D (no stems), Groove F.

Hard aimed at 9 now rates 9.0 and at 10 rates 9.56, with 16ths at 15% and 20%. Within 0.75 of the number: 96% from 2 to 8, 90% from 1 to 10. Note the rating's top end was recalibrated on Konami's own charts in #10 (their 9s used to rate 8.4), so most of the gain at 9 is the scale, not a different chart: Hard 9 charts are about as dense as before (3.6 steps a second). At 10 they are denser (4.1, was 3.9). The docs (docs/DIALS.md, pictures and preview) are regenerated from this run.
