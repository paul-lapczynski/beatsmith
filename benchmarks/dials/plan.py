"""The test plan (TESTPLAN.md) as lists of runs. Each group is a few
settings that get compared with each other, made on one song with one
seed; the first entry of a group is its reference (what "unchanged" means
for that comparison)."""
from __future__ import annotations

import random
from dataclasses import dataclass

from harness import APP_TARGETS, FEEL, Config

LEVELS = (0, 25, 50, 75, 100)
PROFILES = ("konami", "patterns")
SEEDS = (1, 2, 3)

# Advanced settings: (25%, 50%, 75%) of a useful range (TESTPLAN.md section 6)
ADVANCED = {
    "density": (0.75, 1.25, 1.75), "max_nps": (3, 5, 7), "grid": (1, 2, 4), "min_gap": (0.25, 0.5, 1.0),
    "jack_max": (2, 3, 5), "hold_min": (1, 2, 4), "hold_max": (2, 4, 6), "hold_free_foot": (0, 1, 2),
    "sixteenths": (0.5, 1.0, 1.5), "max_run16": (3, 6, 12), "groove_tries": (1, 2, 4),
    "meter_min": (1, 4, 7), "meter_max": (4, 7, 10),
}
UNIT = ("jump", "jacks", "flow", "side_to_side", "flow_spice", "energy_follow", "half_beats",
        "quarter_beats", "run_breaks", "recovery", "stomps", "rhythm_lock", "hold_rate",
        "hold_complexity", "rhythm_repeat", "arrow_repeat", "intensity_variation", "jump_clusters",
        "jump_holds", "flow_runs", "phrase_shape", "rest_bars", "beat_backbone", "crescendo")
for _k in UNIT:
    ADVANCED[_k] = (0.25, 0.5, 0.75)

PAIRS = {"C5": ("jumps", "breathing"), "C6": ("holds", "breathing"),
         "C7": ("speed", "footwork"), "C8": ("energy", "repetition")}
PINS = {"jumps": "jump", "speed": "half_beats", "breathing": "run_breaks"}


@dataclass
class Group:
    design: str
    key: str                    # unique within the design
    song: str
    configs: list               # [Config], first = reference
    tags: list                  # one dict per config: which dial is at which value


def _ctx():
    for prof in PROFILES:
        for tg in (True, False):
            yield prof, tg


def build(songs: list[str], quick: bool = False) -> list[Group]:
    seeds = SEEDS[:1] if quick else SEEDS
    out: list[Group] = []
    tg_of = lambda on: tuple(APP_TARGETS.items()) if on else None

    # A. one dial at a time
    dials = list(FEEL) + ["groove", "follow", "ai"]
    for song in songs:
        for seed in seeds:
            for prof, tg in _ctx():
                base = Config(profile=prof, targets=tg_of(tg), seed=seed)
                for dial in dials:
                    cfgs, tags = [], []
                    ref = 50 if dial in FEEL else 0
                    for v in [ref] + [x for x in LEVELS if x != ref]:
                        c = base.with_(feel={dial: v}) if dial in FEEL else base.with_(**{dial: v})
                        cfgs.append(c)
                        tags.append({"dial": dial, "value": v, "profile": prof, "target": tg})
                    out.append(Group("A", f"{dial}|{prof}|{tg}|{song}|{seed}", song, cfgs, tags))

    # B. difficulty sweep: every chart aimed at 1..10
    for song in songs:
        for seed in seeds:
            for prof in PROFILES:
                base = Config(profile=prof, targets=None, seed=seed)
                cfgs = [base] + [base.with_(targets={d: float(m) for d in APP_TARGETS}) for m in range(1, 11)]
                tags = [{"target_all": 0, "profile": prof}] + [{"target_all": m, "profile": prof} for m in range(1, 11)]
                out.append(Group("B", f"{prof}|{song}|{seed}", song, cfgs, tags))

    # C. interaction sets (konami, app targets)
    for song in songs:
        for seed in seeds:
            base = Config(seed=seed)
            for other, vals in (("ai", (0, 50, 100)), ("follow", (0, 50, 100))):
                design = "C2" if other == "ai" else "C3"
                for s in FEEL:
                    cfgs, tags = [], []
                    for ov in vals:
                        for v in (50, 25, 75):
                            cfgs.append(base.with_(feel={s: v}, **{other: ov}))
                            tags.append({"dial": s, "value": v, other: ov})
                    out.append(Group(design, f"{s}|{song}|{seed}", song, cfgs, tags))
            for s in FEEL:
                cfgs, tags = [], []
                for g in (0, 75):
                    for v in (50, 25, 75):
                        cfgs.append(base.with_(feel={s: v}, groove=g))
                        tags.append({"dial": s, "value": v, "groove": g})
                out.append(Group("C4", f"{s}|{song}|{seed}", song, cfgs, tags))
            for name, (x, y) in PAIRS.items():
                cfgs, tags = [], []
                for vx in (50, 25, 75):
                    for vy in (50, 25, 75):
                        cfgs.append(base.with_(feel={x: vx, y: vy}))
                        tags.append({"x": x, "y": y, "vx": vx, "vy": vy})
                out.append(Group(name, f"{song}|{seed}", song, cfgs, tags))
            cfgs, tags = [], []
            for ai in (0, 50, 100):
                for fo in (0, 50, 100):
                    cfgs.append(base.with_(ai=ai, follow=fo))
                    tags.append({"ai": ai, "follow": fo})
            out.append(Group("C9", f"{song}|{seed}", song, cfgs, tags))
            for slider, param in PINS.items():
                for tg in (True, False):
                    cfgs, tags = [], []
                    b2 = base.with_(targets=tg_of(tg))
                    for pin in (False, True):
                        sets = tuple(f"{d}.{param}=0.3" for d in APP_TARGETS) if pin else ()
                        for v in (50, 25, 75):
                            cfgs.append(b2.with_(feel={slider: v}, sets=sets))
                            tags.append({"dial": slider, "param": param, "value": v, "pinned": pin, "target": tg})
                    out.append(Group("C10", f"{slider}|{tg}|{song}|{seed}", song, cfgs, tags))

    # D. random sample of everything (Latin hypercube), seed 1
    n = 40 if quick else 150
    for song in songs:
        rng = random.Random(f"D-{song}")
        cols = list(FEEL) + ["groove", "follow", "ai", "tE", "tM", "tH"]
        strata = {c: rng.sample(range(n), n) for c in cols}
        for i in range(n):
            u = {c: (strata[c][i] + rng.random()) / n for c in cols}
            feel = {s: round(100 * u[s]) for s in FEEL}
            targets = None if rng.random() < 0.15 else {
                "Easy": round(1 + 4 * u["tE"], 1), "Medium": round(3 + 5 * u["tM"], 1),
                "Hard": round(5 + 5 * u["tH"], 1)}
            c = Config(groove=round(100 * u["groove"]) if u["groove"] > 0.25 else 0,
                       feel=tuple(sorted(feel.items())), targets=tuple(targets.items()) if targets else None,
                       follow=round(100 * u["follow"]) if u["follow"] > 0.3 else 0,
                       ai=round(100 * u["ai"]) if u["ai"] > 0.3 else 0, seed=1)
            out.append(Group("D", f"{song}|{i}", song, [c], [{"i": i}]))

    # E. Advanced settings one at a time (konami, both target modes)
    for song in songs:
        for seed in seeds[:1]:
            for tg in (True, False):
                base = Config(targets=tg_of(tg), seed=seed)
                for param, vals in ADVANCED.items():
                    cfgs = [base] + [base.with_(sets=tuple(f"{d}.{param}={v:g}" for d in APP_TARGETS))
                                     for v in vals]
                    tags = [{"param": param, "level": 0, "value": None, "target": tg}] + [
                        {"param": param, "level": lv, "value": v, "target": tg}
                        for lv, v in zip((25, 50, 75), vals)]
                    out.append(Group("E", f"{param}|{tg}|{song}|{seed}", song, cfgs, tags))
    return out
