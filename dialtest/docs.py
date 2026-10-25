"""docs/DIALS.md: what every control does, with pictures, for the GitHub
README. Numbers come from summary.json (`dialtest.py report`), pictures
from docs/img (`dialtest.py images`); the plain-language notes per control
are in NOTES below and get updated by hand when a test run changes the
story."""
from __future__ import annotations

import json
import math

import harness
import render

DOCS = render.DOCS
OUT = DOCS / "DIALS.md"

ORDER = ["groove", "energy", "jumps", "speed", "breathing", "footwork", "holds", "repetition",
         "difficulty", "follow", "ai"]
TITLES = {"groove": "Groove (overall)", "energy": "Energy / arc", "jumps": "Jumps", "speed": "Speed",
          "breathing": "Breathing room", "footwork": "Footwork", "holds": "Holds", "repetition": "Repetition",
          "difficulty": "Difficulty number", "follow": "Arrows follow (melody)", "ai": "AI assist"}
IMAGES = {"groove": "groove", "energy": "feel-energy", "jumps": "feel-jumps", "speed": "feel-speed",
          "breathing": "feel-breathing", "footwork": "feel-footwork", "holds": "feel-holds",
          "repetition": "feel-repetition", "difficulty": "difficulty", "follow": "follow", "ai": "ai"}
# what each control is for, in a sentence, and what to know about it from the
# test (kept short; the measured numbers are added under it automatically)
NOTES: dict[str, tuple[str, str]] = {}
NOTES_FILE = harness.HERE / "notes.json"


def load_notes() -> dict:
    if NOTES_FILE.is_file():
        return json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    return {}


def fmt(v, nd=1):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "–"
    return f"{v:.{nd}f}"


def main():
    summ = json.loads((harness.HERE / "summary.json").read_text(encoding="utf-8"))
    ratings = summ.get("ratings", {})
    notes = load_notes()
    L = []
    w = L.append
    w("# What the controls do\n")
    w("BeatSmith has one overall control (**Groove**), seven **Feel** sliders, a **difficulty number** "
      "per chart, two ways to change where steps come from (**Arrows follow** and **AI assist**) "
      "and an **Advanced** table with every setting. This page shows what each one does to a "
      "chart: 4 bars made at 25%, 50% and 75% (Groove off/25/50/75, difficulty 3/5/7/9), "
      "plus what the dial test measured across whole songs. Each picture shows the 4 bars where its "
      "control changes the chart the same way it does over the whole song, and the numbers under "
      "each column are for the whole chart.\n")
    w("Try them live: **[preview.html](preview.html)** has a slider per control, the 4 bars next to "
      "the default, and the song with a tick on every step.\n")
    w("![Note colours](img/legend.svg)\n")
    w("The pictures are the Medium chart of *BeatSmith Demo* (examples/BeatSmith Demo, a track synthesized for these docs; the "
      "difficulty picture uses Hard) with the konami profile, "
      "seed 1 and the app's default difficulty targets (Easy 3, Medium 6, Hard 8), with "
      "everything else at its default. Each column's header gives the whole chart's rating, "
      "step count, jumps and freezes.\n")
    w("## At a glance\n")
    rows = []
    for k in ORDER:
        r = ratings.get(k)
        short = notes.get(k, {}).get("short", "")
        rows.append([f"[{TITLES[k]}](#{anchor(TITLES[k])})", short,
                     f"**{r['grade']}**" if r else "–"])
    w(table(["Control", "What it does", "Test grade"], rows))
    w("\nThe grade is from the dial test ([how it's scored](../dialtest/REPORT.md#1-grades)): A means "
      "it clearly moves what its label says, always in the same direction, on every song, without "
      "changing other things, and keeps working with a difficulty target on.\n")
    w("**The order things happen in:** the profile sets every value, Groove moves its settings, "
      "the Feel sliders move theirs from there (so they have the last word), exact values from "
      "the Advanced table replace whatever the sliders made, and then the difficulty number "
      "turns density, jumps, half-beats, holds and faster notes up or down until the chart rates "
      "what you asked for. Arrows follow and AI assist work earlier, on where the music says a "
      "step could go; everything after that still applies.\n")
    for k in ORDER:
        n = notes.get(k, {})
        w(f"## {TITLES[k]}\n")
        if n.get("lead"):
            w(n["lead"] + "\n")
        img = IMAGES.get(k)
        if img and (render.IMG / f"{img}.svg").is_file():
            w(f"![{TITLES[k]} at different settings](img/{img}.svg)\n")
        r = ratings.get(k)
        if r and r.get("per_diff"):
            h = r["per_diff"].get("Hard", {})
            sc = h.get("scores", {})
            w(f"**Test grade {r['grade']}** (score per chart: Easy {fmt(r['per_diff'].get('Easy', {}).get('score'), 0)}, "
              f"Medium {fmt(r['per_diff'].get('Medium', {}).get('score'), 0)}, Hard {fmt(h.get('score'), 0)}). "
              "On Hard: " + " · ".join(f"{a} {b:.0f}" for a, b in sc.items()) + " (each out of 100).\n")
        elif r:
            w(f"**Test grade {r['grade']}**: within 0.75 of the number asked {r['accuracy_2_8'] * 100:.0f}% of the "
              f"time from 2 to 8, {r['accuracy_all'] * 100:.0f}% from 1 to 10.\n")
        for line in n.get("facts", []):
            w(f"- {line}")
        if n.get("facts"):
            w("")
    # advanced
    w("## The Advanced table\n")
    w(notes.get("advanced", {}).get("lead", "") + "\n")
    adv = summ.get("advanced", {})
    if adv:
        kinds = {}
        for p, v in adv.items():
            kinds.setdefault(v["kind"], []).append(p)
        rows = [[kind, ", ".join(f"`{p}`" for p in sorted(ps))] for kind, ps in
                sorted(kinds.items(), key=lambda kv: ["slider-covered", "Advanced-only", "overwritten by target",
                                                      "no effect found"].index(kv[0]))]
        w(table(["What the test found", "Settings"], rows))
        w("")
    for line in notes.get("advanced", {}).get("facts", []):
        w(f"- {line}")
    w("")
    w("## Find a preset from a chart you like\n")
    w("`python dialtest/dialtest.py find-preset \"path/to/Song.sm\" --name my-style` reads the chart "
      "(.sm, .ssc or .dwi) and its song, measures it the way the dial test measures BeatSmith's charts, "
      "then makes charts and moves one control at a time until BeatSmith's chart of that song is as "
      "close to it as the controls allow. It saves `profiles/my-style.toml` (each difficulty's "
      "settings, aimed at the chart's own difficulty) and `my-style.find-preset.md` with how close "
      "each measurement got. It takes a few minutes per chart on the CPU and only reads the chart's "
      "folder.\n")
    for line in notes.get("find_preset", {}).get("facts", []):
        w(f"- {line}")
    w("")
    w("## Re-running the tests\n")
    w("```\npython dialtest/dialtest.py run            # the whole plan, about an hour on 4 cores\n"
      "python dialtest/dialtest.py report         # dialtest/REPORT.md\n"
      "python dialtest/dialtest.py images         # docs/img/\n"
      "python dialtest/dialtest.py preview        # docs/preview.html\n"
      "python dialtest/dialtest.py docs           # this page\n```\n")
    w("Needs `pip install -r dialtest/requirements.txt` on top of BeatSmith's own. `run` takes any songs (`dialtest.py run a.ogg b.mp3`), needs only the CPU, and resumes where "
      "it stopped. The plan is in [dialtest/TESTPLAN.md](../dialtest/TESTPLAN.md), every number in "
      "[dialtest/REPORT.md](../dialtest/REPORT.md).\n")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


def anchor(title: str) -> str:
    return "".join(c for c in title.lower().replace(" ", "-") if c.isalnum() or c == "-")


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])
