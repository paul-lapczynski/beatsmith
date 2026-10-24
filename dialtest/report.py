"""REPORT.md from the results of `dialtest.py run`: a grade per dial, what
each one really moves, how they interact, how the difficulty number works
and what every Advanced setting does.

The numbers are also kept as results/summary.json, which docs.py and
find_preset.py read."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

import harness
import metrics
from harness import FEEL, stepgen

RESULTS = harness.WORK / "results"
OUT = harness.HERE / "REPORT.md"
SUMMARY = harness.HERE / "summary.json"
DIFFS = list(harness.DIFFS)

# what each control claims, as (measurement, direction it should move)
CLAIMS = {
    "groove": [("groove", 1), ("g_pattern", 1), ("g_locked", 1)],
    "energy": [("energy_corr", 1), ("energy_contrast", 1)],
    "jumps": [("jump_pct", 1), ("jump_holds", 1)],
    "speed": [("quarter_pct", 1), ("half_pct", 1), ("stream", 1)],
    "breathing": [("run_mean", -1), ("rests", 1), ("stomps", 1)],
    "footwork": [("walk_pct", 1), ("lr_pct", 1), ("jack_pct", -1)],
    "holds": [("hold_pct", 1)],
    "repetition": [("rep_rhythm", 1), ("rep_arrows", 1)],
    "follow": [("melody_lock", 1), ("pitch_follow", 1)],
    "ai": [("ai_lock", 1), ("same_pos", -1)],
}
NAMES = {"difficulty": "Difficulty number", "groove": "Groove", "energy": "Energy / arc", "jumps": "Jumps", "speed": "Speed",
         "breathing": "Breathing room", "footwork": "Footwork", "holds": "Holds",
         "repetition": "Repetition", "follow": "Arrows follow (melody)", "ai": "AI assist"}
MEASURES = [k for k in metrics.DESCRIBE if k not in ("steps",)]
# settings the difficulty number rewrites at chart time (stepgen.with_intensity)
TARGET_REWRITES = ("density", "max_nps", "jump", "hold_rate", "half_beats", "grid", "min_gap",
                   "quarter_beats", "flow_spice")


def load() -> pd.DataFrame:
    frames = [pd.read_json(f, lines=True) for f in sorted(RESULTS.glob("*.jsonl")) if f.stat().st_size]
    if not frames:
        raise SystemExit(f"no results in {RESULTS}: run `python dialtest.py run` first")
    return pd.concat(frames, ignore_index=True)


def fmt(v, nd=1) -> str:
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "–"
    return f"{v:.{nd}f}"


def table(head: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def spearman(x, y) -> float:
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(np.argsort(np.argsort(x)), np.argsort(np.argsort(y)))[0, 1])


# --------------------------------------------------------------------------
# noise: how much a measurement moves when only the seed changes
# --------------------------------------------------------------------------

def noise_table(A: pd.DataFrame) -> dict:
    """Per (diff, target on/off, measurement): the typical seed-to-seed
    spread of the reference charts, pooled over songs, profiles and dials."""
    ref = A[A["i"] == 0].drop_duplicates(["song", "profile", "target", "seed", "diff"])
    out = {}
    for (diff, tg), g in ref.groupby(["diff", "target_on"]):
        for m in MEASURES:
            if m not in g:
                continue
            v = g.groupby(["song", "profile"])[m].var().dropna()
            sd = float(np.sqrt(v.mean())) if len(v) else float("nan")
            # floor: never smaller than 2% of the measurement's typical size
            out[(diff, tg, m)] = max(sd, 0.02 * abs(float(g[m].mean())) + 1e-6, 1e-3)
    return out


# --------------------------------------------------------------------------
# A: one dial at a time
# --------------------------------------------------------------------------

def rate_dials(A: pd.DataFrame, noise: dict) -> dict:
    res = {}
    for dial, claims in CLAIMS.items():
        d = A[A["dial"] == dial]
        if d.empty:
            continue
        per_diff = {}
        for diff in DIFFS:
            dd = d[d["diff"] == diff]
            parts = {"effect": [], "mono": [], "survive": [], "songs": [], "side": [], "meter_on": [], "meter_off": []}
            curves = {}
            for m, sign in claims:
                if m not in dd or dd[m].isna().all():
                    continue
                lo = dd[dd["value"] == 25].set_index(["song", "profile", "target_on", "seed"])[m]
                hi = dd[dd["value"] == 75].set_index(["song", "profile", "target_on", "seed"])[m]
                eff = (hi - lo).dropna() * sign
                if eff.empty:
                    continue
                sn = {tg: eff.xs(tg, level="target_on").mean() / noise.get((diff, tg, m), 1)
                      for tg in (True, False) if tg in eff.index.get_level_values("target_on")}
                parts["effect"].append(np.mean(list(sn.values())))
                if sn.get(False, 0) > 0:
                    parts["survive"].append(np.clip(sn.get(True, 0) / sn[False], 0, 1))
                rhos = [spearman(g["value"], g[m]) * sign
                        for _, g in dd.groupby(["song", "profile", "target_on", "seed"])]
                parts["mono"].append(np.nanmedian(rhos) if rhos else np.nan)
                by_song = eff.groupby(level="song").mean() / noise.get((diff, True, m), 1)
                parts["songs"].append(float((by_song >= 1.5).mean()))
                curves[m] = {str(tg): dd[dd["target_on"] == tg].groupby("value")[m].mean().round(3).to_dict()
                             for tg in (True, False)}
            # side effects: the other dials' main measurements
            side = []
            for other, oc in CLAIMS.items():
                if other == dial:
                    continue
                m = oc[0][0]
                if m not in dd:
                    continue
                lo = dd[dd["value"] == 25].groupby(["song", "profile", "target_on", "seed"])[m].mean()
                hi = dd[dd["value"] == 75].groupby(["song", "profile", "target_on", "seed"])[m].mean()
                e = (hi - lo).dropna()
                if len(e):
                    side.append((other, m, float(e.mean() / noise.get((diff, True, m), 1))))
            for tg, key in ((True, "meter_on"), (False, "meter_off")):
                x = dd[dd["target_on"] == tg]
                lo, hi = x[x["value"] == 25]["meter"].mean(), x[x["value"] == 75]["meter"].mean()
                parts[key] = float(hi - lo)
            s1 = 100 * np.clip(np.nanmean(parts["effect"]) / 3, 0, 1) if parts["effect"] else 0
            s2 = 100 * np.clip(np.nanmean(parts["mono"]), 0, 1) if parts["mono"] else 0
            s3 = 100 * np.nanmean(parts["survive"]) if parts["survive"] else 0
            sidev = np.mean([min(abs(s) / 3, 1) for _, _, s in side]) if side else 0
            s4 = 100 * (1 - sidev) * (1 - min(abs(parts["meter_on"]) / 1.5, 1) * 0.5)
            s5 = 100 * np.nanmean(parts["songs"]) if parts["songs"] else 0
            score = 0.35 * s1 + 0.2 * s2 + 0.15 * s3 + 0.15 * s4 + 0.15 * s5
            if dial in ("follow", "ai", "groove"):        # target survival is scored the same way
                pass
            per_diff[diff] = {
                "scores": {"moves it": s1, "same direction": s2, "survives target": s3,
                           "stays in its lane": s4, "every song": s5},
                "score": float(score), "sn": float(np.nanmean(parts["effect"])) if parts["effect"] else 0.0,
                "meter_on": parts["meter_on"], "meter_off": parts["meter_off"],
                "side": sorted(side, key=lambda t: -abs(t[2]))[:3], "curves": curves,
            }
        overall = float(np.mean([v["score"] for v in per_diff.values()])) if per_diff else 0
        res[dial] = {"per_diff": per_diff, "score": overall, "grade": grade(overall)}
    return res


def grade(score: float) -> str:
    for g, cut in (("A", 85), ("B", 70), ("C", 55), ("D", 40)):
        if score >= cut:
            return g
    return "F"


def all_moves(A: pd.DataFrame, noise: dict, dial: str, diff: str = "Hard", tg: bool = True,
              top: int = 8) -> list[tuple[str, float, float, float]]:
    """Everything a dial moves from 25% to 75% (or off to 75% for groove,
    follow and AI), biggest first: (measurement, at low, at high, S/N)."""
    d = A[(A["dial"] == dial) & (A["diff"] == diff) & (A["target_on"] == tg)]
    lo_v = 25 if dial in FEEL else 0
    out = []
    for m in MEASURES:
        if m not in d or d[m].isna().all():
            continue
        lo, hi = d[d["value"] == lo_v][m].mean(), d[d["value"] == 75][m].mean()
        sn = (hi - lo) / noise.get((diff, tg, m), 1)
        if not math.isnan(sn):
            out.append((m, float(lo), float(hi), float(sn)))
    return sorted(out, key=lambda t: -abs(t[3]))[:top]


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def main():
    df = load()
    if "target" in df:
        df["target_on"] = df["target"].astype(float) > 0
    A = df[df["design"] == "A"].copy()
    A["target_on"] = A["target_on"].astype(bool)
    noise = noise_table(A)
    ratings = rate_dials(A, noise)
    L: list[str] = []
    w = L.append
    songs = sorted(df["song"].unique())
    w("# stepgen dial test report\n")
    w(f"Made by `dialtest.py report` from {len(df):,} charts ({len(df) // 3:,} runs) on "
      f"{', '.join(songs)}. Test design: [TESTPLAN.md](TESTPLAN.md). "
      "\"S/N\" below is a change divided by what changing only the seed does (the noise): "
      "under 1 is lost in the noise, 3 or more is clear.\n")

    # ---- grades
    w("## 1. Grades\n")
    w("Each control is rated on five questions (0-100 each), per chart, then averaged: "
      "**moves it** (does its claimed measurement change, 25% to 75%, against the noise), "
      "**same direction** (rank correlation across 0..100), **survives target** (effect with a "
      "difficulty target on, as a share of the effect with it off), **stays in its lane** (how little "
      "it moves other dials' measurements and, with a target on, the meter) and **every song**.\n")
    rows = []
    for dial, r in sorted(ratings.items(), key=lambda kv: -kv[1]["score"]):
        pd_ = r["per_diff"]
        cells = [f"{pd_[d]['score']:.0f}" if d in pd_ else "–" for d in DIFFS]
        claim = ", ".join(f"{m} {'up' if s > 0 else 'down'}" for m, s in CLAIMS[dial])
        h = pd_.get("Hard", {}).get("scores", {})
        rows.append([f"**{NAMES[dial]}**", f"**{r['grade']}** ({r['score']:.0f})", *cells,
                     " / ".join(f"{v:.0f}" for v in h.values()), claim])
    w(table(["Control", "Grade", "Easy", "Medium", "Hard", "Hard: moves / direction / survives / lane / songs",
             "Claim tested"], rows))
    w("")

    # ---- per dial detail
    w("## 2. What each control really does\n")
    w("Hard chart, konami and patterns profiles, with the app's targets on (3/6/8) unless it says "
      "otherwise. Biggest changes first, 25% to 75% (off to 75% for Groove, Follow and AI).\n")
    for dial in CLAIMS:
        if dial not in ratings:
            continue
        r = ratings[dial]
        w(f"### {NAMES[dial]} — grade {r['grade']}\n")
        h = r["per_diff"].get("Hard", {})
        rows = []
        for m, lo, hi, sn in all_moves(A, noise, dial):
            rows.append([metrics.DESCRIBE.get(m, m), fmt(lo), fmt(hi), fmt(sn)])
        w(table(["Measurement", "low", "75%", "S/N"], rows))
        moff = all_moves(A, noise, dial, tg=False, top=4)
        if moff:
            w("\nWith no target: " + "; ".join(f"{metrics.DESCRIBE.get(m, m)} {fmt(lo)} → {fmt(hi)} "
                                                 f"(S/N {fmt(sn)})" for m, lo, hi, sn in moff) + ".")
        if h:
            w(f"\nMeter change 25→75%: {fmt(h['meter_on'], 2)} with a target, {fmt(h['meter_off'], 2)} without.")
        w("")

    # ---- feel over AI and follow
    w("## 3. Do the Feel sliders still rule with AI assist or Follow on?\n")
    w("Retention = the slider's effect on its own measurement with AI (or Follow) at that level, "
      "divided by its effect at 0. 100% means the feel works exactly as well; under 50% means the "
      "AI or melody is overriding it.\n")
    feel_ret = {}
    for design, other in (("C2", "ai"), ("C3", "follow")):
        C = df[df["design"] == design]
        if C.empty:
            continue
        rows = []
        for s in FEEL:
            m, sign = CLAIMS[s][0]
            c = C[C["dial"] == s]
            cells = []
            base = None
            for ov in (0, 50, 100):
                x = c[c[other] == ov]
                e = (x[x["value"] == 75].groupby(["song", "seed", "diff"])[m].mean()
                     - x[x["value"] == 25].groupby(["song", "seed", "diff"])[m].mean()).mean() * sign
                if ov == 0:
                    base = e
                cells.append(e)
            ret = [100 * c_ / base if base and base > 0 else float("nan") for c_ in cells[1:]]
            feel_ret.setdefault(other, {})[s] = ret
            rows.append([NAMES[s], m, fmt(cells[0], 2), f"{fmt(ret[0], 0)}%", f"{fmt(ret[1], 0)}%"])
        w(f"**{NAMES[other]}**\n")
        w(table(["Feel slider", "Measured", "Effect at 0", f"{other} 50", f"{other} 100"], rows))
        w("")
    # AI x follow
    C9 = df[df["design"] == "C9"]
    if not C9.empty:
        w("**AI assist x Follow** (all charts): change from the plain chart's step positions, and where steps land\n")
        rows = []
        for ai in (0, 50, 100):
            for fo in (0, 50, 100):
                x = C9[(C9["ai"] == ai) & (C9["follow"] == fo)]
                rows.append([ai, fo, fmt(x["same_pos"].mean(), 0) + "%", fmt(x["ai_lock"].mean()),
                             fmt(x["melody_lock"].mean()), fmt(x["drum_lock"].mean()), fmt(x["meter"].mean(), 2)])
        w(table(["AI", "Follow", "same step positions", "on AI moments", "on melody", "on drums", "meter"], rows))
        w("")

    # ---- groove
    w("## 4. What Groove actually does\n")
    g = A[(A["dial"] == "groove") & (A["target_on"])]
    if not g.empty:
        rows = []
        for diff in DIFFS:
            for v in (0, 25, 50, 75, 100):
                x = g[(g["diff"] == diff) & (g["value"] == v)]
                if x.empty:
                    continue
                rows.append([diff, "off" if v == 0 else f"{v}%", fmt(x["groove"].mean()),
                             fmt(x["g_pattern"].mean(), 0), fmt(x["g_locked"].mean(), 0),
                             fmt(x["g_breathing"].mean(), 0), fmt(x["g_footing"].mean(), 0),
                             fmt(x["g_effort"].mean(), 0), fmt(x["run_mean"].mean()), fmt(x["meter"].mean(), 2),
                             fmt(x["secs"].mean(), 1)])
        w(table(["Chart", "Groove", "meter score", "pattern", "locked", "breathing", "footing", "effort",
                 "avg run", "meter", "secs/run"], rows))
        w("")
    C4 = df[df["design"] == "C4"].copy()
    if not C4.empty:
        # the "groove" tag shares its name with the groove meter column: read it from the label
        C4["groove"] = C4["config"].str.extract(r"groove (\d+)")[0].astype(float).fillna(0)
        w("**Groove on top of the Feel sliders**: each slider's effect on its own measurement with "
          "Groove off and at 75%. The sliders are applied after Groove, so they should keep working.\n")
        rows = []
        for s in FEEL:
            m, sign = CLAIMS[s][0]
            c = C4[C4["dial"] == s]
            eff = []
            for gv in (0, 75):
                x = c[c["groove"] == gv]
                eff.append((x[x["value"] == 75][m].mean() - x[x["value"] == 25][m].mean()) * sign)
            rows.append([NAMES[s], m, fmt(eff[0], 2), fmt(eff[1], 2),
                         f"{fmt(100 * eff[1] / eff[0], 0)}%" if eff[0] and eff[0] > 0 else "–"])
        w(table(["Feel slider", "Measured", "effect, groove off", "effect, groove 75%", "kept"], rows))
        w("")

    # ---- difficulty
    w("## 5. How the difficulty number changes the song\n")
    B = df[df["design"] == "B"]
    diff_info = {}
    if not B.empty:
        w("Every chart aimed at 1 to 10 (both profiles, 3 songs, 3 seeds). stepgen rates each try "
          "and turns one intensity dial (`with_intensity`) until the rating lands: 0 is the profile as "
          "written, up to +1 adds steps, jumps and 8th runs and takes away holds, past +0.6 it adds "
          "quarter-beat bursts, past +1 16th streams; below -0.4 it drops to beat notes only.\n")
        rows = []
        for diff in DIFFS:
            for m in range(1, 11):
                x = B[(B["diff"] == diff) & (B["target_all"] == m)]
                if x.empty:
                    continue
                err = (x["meter"] - m).abs()
                rows.append([diff, m, fmt(x["meter"].mean(), 2), fmt(err.mean(), 2), f"{(err <= 0.75).mean() * 100:.0f}%",
                             fmt(x["used.density"].mean(), 2), fmt(x["used.jump"].mean(), 2),
                             fmt(x["used.half_beats"].mean(), 2), fmt(x["used.quarter_beats"].mean(), 2),
                             fmt(x["used.hold_rate"].mean(), 3), fmt(x["used.grid"].mean(), 1),
                             fmt(x["nps"].mean(), 2), fmt(x["half_pct"].mean(), 0), fmt(x["quarter_pct"].mean(), 1),
                             fmt(x["jump_pct"].mean(), 0), fmt(x["hold_pct"].mean(), 0), fmt(x["stream"].mean(), 0)])
                diff_info.setdefault(diff, {})[m] = {"meter": float(x["meter"].mean()), "hit": float((err <= 0.75).mean())}
        w(table(["Chart", "Aim", "got", "miss", "within 0.75", "density", "jump", "half_beats", "quarter_beats",
                 "hold_rate", "grid", "steps/s", "8ths %", "16ths %", "jumps %", "freezes %", "longest 8th run"], rows))
        hit = B[(B["target_all"] > 0)]
        acc = float(((hit["meter"] - hit["target_all"]).abs() <= 0.75).mean())
        mid = hit[hit["target_all"].between(2, 8)]
        acc_mid = float(((mid["meter"] - mid["target_all"]).abs() <= 0.75).mean())
        mono = np.nanmedian([spearman(g["target_all"], g["meter"]) for _, g in hit.groupby(["song", "profile", "seed", "diff"])])
        dscore = 100 * (0.5 * acc_mid + 0.25 * acc + 0.25 * max(mono, 0))
        ratings["difficulty"] = {"score": dscore, "grade": grade(dscore), "per_diff": {},
                                 "accuracy_all": acc, "accuracy_2_8": acc_mid}
        w(f"\n**Grade {grade(dscore)}** ({dscore:.0f}): lands within 0.75 of the number asked "
          f"{acc_mid * 100:.0f}% of the time for 2 to 8 and {acc * 100:.0f}% over 1 to 10; always in order "
          f"(rank correlation {mono:.2f}).\n")
        nat = B[B["target_all"] == 0].groupby(["profile", "diff"])["meter"].mean().round(1)
        w("\nWith no target the profiles rate: " + ", ".join(f"{p} {d} {v}" for (p, d), v in nat.items()) + ".\n")

    # ---- advanced
    w("## 6. The Advanced settings\n")
    w("Each setting pinned to 25/50/75% of its range on all three charts (konami profile, seed 1, 3 "
      "songs). S/N is the biggest change it makes to any measurement between 25% and 75%.\n")
    E = df[df["design"] == "E"]
    sliders_of = {}
    for sl, items in stepgen.EASY_SLIDERS.items():
        for k, _lo, _hi in items:
            sliders_of.setdefault(k, []).append(sl)
    adv = {}
    if not E.empty:
        e_noise = {}
        ref = E[E["level"] == 0]
        for (diff, tg), gg in ref.groupby(["diff", "target_on"]):
            for m in MEASURES:
                if m in gg:
                    e_noise[(diff, tg, m)] = noise.get((diff, tg, m), max(float(gg[m].std() or 0), 1e-3))
        rows = []
        for param, gp in E.groupby("param"):
            best = {}
            for tg in (True, False):
                x = gp[(gp["target_on"] == tg) & (gp["diff"] == "Hard")]
                cand = []
                for m in MEASURES:
                    if m not in x:
                        continue
                    lo, hi = x[x["level"] == 25][m].mean(), x[x["level"] == 75][m].mean()
                    sn = (hi - lo) / e_noise.get(("Hard", tg, m), 1)
                    if not math.isnan(sn):
                        cand.append((abs(sn), m, sn))
                cand.sort(reverse=True)
                best[tg] = cand[:2]
            s_off = best[False][0][0] if best[False] else 0
            s_on = best[True][0][0] if best[True] else 0
            if param in ("meter_min", "meter_max") or max(s_off, s_on) < 1.0:
                kind = "no effect found"
            elif param in TARGET_REWRITES and s_on < 0.5 * s_off:
                kind = "overwritten by target"
            elif param in sliders_of:
                kind = "slider-covered"
            else:
                kind = "Advanced-only"
            adv[param] = {"kind": kind, "sliders": sliders_of.get(param, []), "sn_off": s_off, "sn_on": s_on,
                          "moves": [m for _, m, _ in best[False]]}
            rows.append([f"`{param}`", kind, ", ".join(sliders_of.get(param, [])) or "–",
                         "yes" if param in TARGET_REWRITES else "–",
                         fmt(s_off), fmt(s_on),
                         "; ".join(f"{metrics.DESCRIBE.get(m, m)} ({'+' if sn > 0 else '−'})"
                                   for _, m, sn in best[False]) or "–"])
        order = {"slider-covered": 0, "Advanced-only": 1, "overwritten by target": 2, "no effect found": 3}
        rows.sort(key=lambda r: (order[r[1]], r[0]))
        w(table(["Setting", "Kind", "Moved by slider", "Target rewrites it", "S/N no target",
                 "S/N with target", "Moves most (no target)"], rows))
        w("")
    # displayed vs used
    A_on = A[A["target_on"]]
    if not A_on.empty:
        w("**The Advanced table vs what a chart is really made with.** With a target on, the app "
          "shows each setting after the profile and sliders, but the target then rewrites some of them. "
          "Typical gap on Hard (app default targets):\n")
        rows = []
        h = A_on[A_on["diff"] == "Hard"]
        for k in ("density", "jump", "half_beats", "quarter_beats", "hold_rate", "max_nps", "flow_spice", "grid"):
            a_, u_ = h[f"asked.{k}"], h[f"used.{k}"]
            rows.append([f"`{k}`", fmt(a_.mean(), 2), fmt(u_.mean(), 2), f"{(np.abs(a_ - u_) > 1e-6).mean() * 100:.0f}%"])
        w(table(["Setting", "shown (mean)", "used (mean)", "charts where they differ"], rows))
        w("")
    C10 = df[df["design"] == "C10"]
    if not C10.empty:
        w("**Pinning a setting in Advanced freezes its slider** (effect of the slider 25→75% on its main "
          "measurement, with the setting free and pinned at 0.3):\n")
        rows = []
        for (dial, param), c in C10.groupby(["dial", "param"]):
            m, sign = CLAIMS[dial][0]
            cells = []
            for pin in (False, True):
                for tg in (True, False):
                    x = c[(c["pinned"] == pin) & (c["target_on"] == tg)]
                    cells.append(fmt((x[x["value"] == 75][m].mean() - x[x["value"] == 25][m].mean()) * sign, 2))
            rows.append([NAMES[dial], f"`{param}`", m, *cells])
        w(table(["Slider", "Pinned", "Measured", "free, target", "free, no target", "pinned, target",
                 "pinned, no target"], rows))
        w("")

    # ---- overlaps and conflicts
    w("## 7. Overlaps and conflicts between controls\n")
    w("Settings moved by more than one slider (Groove applies first, then the Feel sliders "
      "from where Groove left them, then Advanced pins, then the target):\n")
    rows = []
    for k, sls in sorted(sliders_of.items()):
        if len(sls) > 1:
            dirs = []
            for sl in sls:
                lo, hi = next((lo, hi) for kk, lo, hi in stepgen.EASY_SLIDERS[sl] if kk == k)
                dirs.append(f"{sl} ({'up' if hi > lo else 'down'})")
            conflict = len({d.split('(')[1] for d in dirs}) > 1
            rows.append([f"`{k}`", ", ".join(dirs), "**opposite directions**" if conflict else "same direction",
                         "yes" if k in TARGET_REWRITES else "–"])
    w(table(["Setting", "Sliders (direction toward 100%)", "", "Target rewrites it too"], rows))
    w("")
    for name in ("C5", "C6", "C7", "C8"):
        C = df[df["design"] == name]
        if C.empty:
            continue
        x_, y_ = C["x"].iloc[0], C["y"].iloc[0]
        mx, sx = CLAIMS[x_][0]
        my, sy = CLAIMS[y_][0]
        w(f"**{NAMES[x_]} x {NAMES[y_]}** (all charts, mean; rows {x_}, columns {y_})\n")
        rows = []
        for vx in (25, 50, 75):
            r = [f"{x_} {vx}"]
            for vy in (25, 50, 75):
                c = C[(C["vx"] == vx) & (C["vy"] == vy)]
                r.append(f"{mx} {fmt(c[mx].mean())} · {my} {fmt(c[my].mean())}")
            rows.append(r)
        w(table(["", *[f"{y_} {v}" for v in (25, 50, 75)]], rows))
        w("")

    # ---- screening (D)
    D = df[df["design"] == "D"]
    sens = {}
    if len(D) > 40:
        w("## 8. Random sample: which control moves what\n")
        w("Share of each measurement's change (Hard, all songs) explained by each control across "
          f"{len(D) // 3} random settings (standardized regression, main effects plus pairwise "
          "products). R² is how much the controls explain at all; the rest is song and seed.\n")
        sens = screening(D)
        cols = list(FEEL) + ["groove", "follow", "ai", "target"]
        rows = []
        for m, info in sens.items():
            rows.append([metrics.DESCRIBE.get(m, m).split(" (")[0], fmt(info["r2"], 2),
                         *[(f"**{info['share'][c] * 100:.0f}**" if info['share'][c] >= 0.25
                            else f"{info['share'][c] * 100:.0f}") for c in cols],
                         ", ".join(info["inter"][:2])])
        w(table(["Measurement", "R²", *cols, "strongest interactions"], rows))
        w("")

    SUMMARY.write_text(json.dumps({
        "ratings": {k: {kk: vv for kk, vv in v.items() if kk.startswith("accuracy")} | {"grade": v["grade"], "score": v["score"],
                        "per_diff": {d: {kk: vv for kk, vv in x.items() if kk != "side"} | {
                            "side": [list(t) for t in x["side"]]} for d, x in v["per_diff"].items()}}
                    for k, v in ratings.items()},
        "noise": {f"{d}|{t}|{m}": v for (d, t, m), v in noise.items()},
        "feel_retention": feel_ret, "difficulty": diff_info, "advanced": adv, "sensitivity": sens,
    }, indent=1, default=float), encoding="utf-8")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {OUT} and {SUMMARY}")


def screening(D: pd.DataFrame) -> dict:
    """Variance share per control for each claimed measurement, from the
    random sample (Hard)."""
    h = D[D["diff"] == "Hard"].copy()
    X = pd.DataFrame(index=h.index)
    for s in FEEL:
        X[s] = h["config"].str.extract(rf"{s} (\d+)")[0].astype(float).fillna(50)
    X["groove"] = h["config"].str.extract(r"groove (\d+)")[0].astype(float).fillna(0)
    X["follow"] = h["config"].str.extract(r"follow (\d+)")[0].astype(float).fillna(0)
    X["ai"] = h["config"].str.extract(r"AI (\d+)")[0].astype(float).fillna(0)
    X["target"] = h["target"].replace(0, np.nan).fillna(h["meter"].mean())
    Xs = (X - X.mean()) / X.std().replace(0, 1)
    songs = pd.get_dummies(h["song"], drop_first=True).astype(float)
    cols = list(Xs.columns)
    pairs = [(a, b) for i, a in enumerate(cols) for b in cols[i + 1:]]
    out = {}
    want = sorted(({m for c in CLAIMS.values() for m, _ in c} | {"meter", "nps"}) - {"same_pos"})
    for m in want:
        y = h[m]
        ok = ~y.isna()
        if ok.sum() < 30:
            continue
        ys = (y[ok] - y[ok].mean()) / (y[ok].std() or 1)
        M = np.column_stack([Xs[ok].values] + [songs[ok].values] +
                            [(Xs[a] * Xs[b])[ok].values[:, None] for a, b in pairs] + [np.ones(ok.sum())])
        lam = 1.0
        beta = np.linalg.solve(M.T @ M + lam * np.eye(M.shape[1]), M.T @ ys.values)
        pred = M @ beta
        r2 = 1 - np.sum((ys.values - pred) ** 2) / np.sum((ys.values - ys.values.mean()) ** 2)
        main = beta[:len(cols)]
        inter = beta[len(cols) + songs.shape[1]:len(cols) + songs.shape[1] + len(pairs)]
        contrib = {c: main[i] ** 2 for i, c in enumerate(cols)}
        for (a, b), v in zip(pairs, inter):
            contrib[a] += v ** 2 / 2
            contrib[b] += v ** 2 / 2
        tot = sum(contrib.values()) or 1
        top = sorted(zip(pairs, inter), key=lambda t: -abs(t[1]))
        out[m] = {"r2": float(r2), "share": {c: float(v / tot) for c, v in contrib.items()},
                  "main": {c: float(main[i]) for i, c in enumerate(cols)},
                  "inter": [f"{a}×{b} {v:+.2f}" for (a, b), v in top[:3] if abs(v) > 0.08]}
    return out


if __name__ == "__main__":
    main()
