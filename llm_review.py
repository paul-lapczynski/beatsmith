#!/usr/bin/env python3
"""llm_review: have an LLM review a generated chart against the song.

UNDER CONSTRUCTION: predates AI assist and the newer options (section dials,
backoff, stems, shorten, lyrics), which the prompt and the re-run leave out.

  python3 llm_review.py "songs/Sandstorm/Sandstorm.sm"                  # Gemini (free tier)
  python3 llm_review.py "songs/Sandstorm/Sandstorm.sm" --provider claude
  python3 llm_review.py "songs/Sandstorm/Sandstorm.sm" --provider local  # LM Studio
  python3 llm_review.py "songs/Sandstorm/Sandstorm.sm" --prompt-only     # no API at all

It sends the model a text summary of the song (section intensity per
measure, build-ups and climaxes, repeated sections, where the kick, drums
and melody are busy), every chart measure by measure, the chart stats and
the settings that made it. The model answers like a chart reviewer: what
works, where the chart doesn't arc with the music or doesn't repeat on the
chorus, and a few options, each a set of --set changes. The review is
written to <title>.review.md next to the chart, and you can pick an option
to regenerate with it straight away.

Keys come from the environment: GEMINI_API_KEY (free key from Google AI
Studio), ANTHROPIC_API_KEY, or nothing for a local LM Studio server
(Developer tab, Start server; default http://localhost:1234/v1).
--prompt-only writes the prompt to <title>.review-prompt.md instead, to
paste into any chat app (e.g. the free Gemini website) yourself. Save the
answer as <title>.review-reply.txt next to the song's stats and run with
--from-reply to get the same report and re-run offer.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

import chartstats as cs
import stepgen as sg
from layout import outer_of, side

HERE = Path(__file__).resolve().parent
ARROWS = "LDUR"
DEFAULT_MODELS = {"gemini": "gemini-flash-latest", "claude": "claude-opus-5-5", "local": "local-model"}


# --------------------------------------------------------------------------
# what the model gets to read
# --------------------------------------------------------------------------

def bar(x: float) -> str:
    return " ▁▂▃▄▅▆▇█"[int(np.clip(x, 0, 1) * 8.99)]


def song_summary(a: sg.Analysis) -> str:
    M = a.spb * sg.BEATS_PER_MEASURE
    n = len(a.intensity)

    def band(env, m):
        i0, i1 = a.frame(a.t0 + m * M), a.frame(a.t0 + (m + 1) * M)
        return float(env[i0:max(i1, i0 + 1)].mean())

    cols = {"kick": a.low_env, "drums": a.onset_env, "melody": a.harm_env, "loud": a.rms}
    norm = {k: max(np.percentile([band(e, m) for m in range(n)], 95), 1e-9) for k, e in cols.items()}
    builds = sg.find_builds(a)
    climaxes = set(sg.climax_bars(a))
    repeats = sg.find_repeats(a)
    rep_of = {}
    for t, s, L in repeats:
        for k in range(L):
            rep_of[t + k] = s + k
    lines = [f"BPM {a.bpm:g}, {n} measures of 4 beats, music from {a.music_start:.1f}s to "
             f"{a.music_end:.1f}s. Measures are numbered from 1.",
             "",
             "Build-ups (steps should climb through these): "
             + (", ".join(f"measures {b + 1}-{c + 1} (climax {c + 1})" for b, c in builds) or "none found"),
             "Repeated sections (should feel the same, variations allowed when more intense): "
             + (", ".join(f"{t + 1}-{t + L} repeat {s + 1}-{s + L}" for t, s, L in repeats) or "none found"),
             "",
             "Per measure, 0-1 scales: intensity = section energy (drums, kick, loudness); "
             "kick / drums / melody = how busy each is; loud = loudness. "
             "start = a new section begins here.",
             "",
             "measure | intensity | kick | drums | melody | loud | notes"]
    for m in range(n):
        tags = []
        if a.section_start[m] > 0:
            tags.append("start")
        if m in climaxes:
            tags.append("climax")
        if m in rep_of:
            tags.append(f"repeats {rep_of[m] + 1}")
        vals = [band(e, m) / norm[k] for k, e in cols.items()]
        lines.append(f"{m + 1:>3} | {a.intensity[m]:.2f} {bar(a.intensity[m])} | "
                     + " | ".join(f"{v:.2f}" for v in vals) + " | " + ", ".join(tags))
    return "\n".join(lines)


def chart_text(ch: cs.Chart, bpm: float, offset: float, a: sg.Analysis) -> str:
    """One line per measure: beat-in-measure:arrows, jumps as LR, holds as
    D(hold 2) for a 2-beat hold."""
    shift = (-offset - a.t0) / a.spb                  # chart beats -> analysis beats
    by_m: dict[int, list[str]] = {}
    rows = ch.rows
    for i, r in enumerate(rows):
        arrows = "".join(ARROWS[c] for c, v in enumerate(r.cols) if v in "124")
        if not arrows:
            continue
        b = round((float(r.beat) * 60 / bpm / a.spb + shift) * 48) / 48   # snap rounding noise
        m = int(np.floor(b / 4 + 1e-6))
        pos = b - 4 * m + 1
        tok = f"{pos:g}:{arrows}"
        heads = [c for c, v in enumerate(r.cols) if v in "24"]
        if heads:
            c = heads[0]
            end = next((q.beat for q in rows[i + 1:] if q.cols[c] == "3"), None)
            if end is not None:
                tok += f"(hold {float(end - r.beat):g})"
        by_m.setdefault(m, []).append(tok)
    n = len(a.intensity)
    return "\n".join(f"{m + 1:>3}: " + (" ".join(by_m.get(m, [])) or "-") for m in range(n))


def settings_text(spec: sg.DiffSpec) -> str:
    skip = {"name", "meter_min", "meter_max", "max_run16"}
    text = ", ".join(f"{k}={v:g}" for k, v in vars(spec).items()
                     if k not in skip and isinstance(v, (int, float)))
    if spec.target_meter > 0:
        text += (f"\n  (target_meter={spec.target_meter:g}: stepgen turned density, jump, hold_rate, "
                 "half_beats, quarter_beats and flow_spice up or down together until the chart rated "
                 "that number, so suggest a different target_meter to change how hard it is, and the "
                 "other settings to change its feel)")
    return text


def load_meta(sm: Path) -> tuple[dict, Path]:
    """How the chart was made (from <title>.stepgen.json, else the .sm itself)."""
    head, _ = cs.parse(sm)
    meta_path = side(sm, ".stepgen.json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    music = sm.parent / (head.get("music") or "")
    if not music.is_file():
        sys.exit(f"can't find the song file {music} next to the chart")
    if "profile" not in meta:
        credit = re.search(r"#CREDIT:stepgen ([^;]*);", sm.read_text(encoding="utf-8", errors="replace"))
        meta["profile"] = credit.group(1).strip() if credit else "patterns"
    # charts copied between computers: re-run from the song next to the chart
    if not meta.get("source") or not Path(meta["source"]).is_file():
        meta["source"] = str(music.resolve())
    if not meta.get("out") or not Path(meta["out"]).is_dir():
        meta["out"] = str(outer_of(sm.resolve()).parent)
    meta.setdefault("title", sm.stem)
    return meta, music


def build_prompt(sm: Path, focus: str | None) -> tuple[str, dict, list[sg.DiffSpec]]:
    head, charts = cs.parse(sm)
    bpm = cs.first_bpm(head["bpms"])
    offset = float(head.get("offset", 0) or 0)
    meta, music = load_meta(sm)
    print(f"analyzing {music.name} ...", file=sys.stderr)
    a = sg.analyze(music, meta.get("bpm"))
    try:
        profile = sg.resolve_profile(meta.get("profile", "patterns"))
        specs = sg.load_patterns(profile, meta.get("set", []), meta.get("easy") or None)
    except Exception:
        specs = sg.load_patterns()
    spec_by = {s.name: s for s in specs}
    doc = "\n".join(l[2:] for l in (HERE / "patterns.toml").read_text().splitlines() if l.startswith("#"))

    parts = [
        "You are an expert DDR / StepMania chart author reviewing a chart that a program "
        "generated for a 4-panel dance pad. Judge it the way a player would: does it feel "
        "like dancing to this song? In particular check that:",
        "- density and intensity arc with the music: steps climb through build-ups, the "
        "climax hits hard (a jump on the big hit), and the steps ease off when the music does",
        "- repeated sections (choruses, a verse over the same beat) feel like the same "
        "dance, with variations when the repeat is more intense",
        "- jumps, holds and quick notes sit on big moments in the music, not at random",
        "- patterns are natural for two feet: quick notes go foot to foot, no awkward "
        "crossovers, enough breathing room",
        "",
        "Only suggest changes that the settings below can make. Each option is a list of "
        "--set changes written as Difficulty.setting=value (e.g. Hard.crescendo=0.9). "
        "Give 2 to 4 options, most useful first. Refer to measures by number.",
        "",
        "Answer with JSON only, in this shape:",
        '{"summary": "two or three sentences", '
        '"issues": [{"difficulty": "Hard", "measures": "12-16", "problem": "...", "severity": "high|medium|low"}], '
        '"options": [{"title": "...", "why": "...", "set": ["Hard.crescendo=0.9"], "tradeoff": "..."}]}',
        "",
        "## What the settings do",
        doc,
        "",
        "## The song",
        song_summary(a),
    ]
    for ch in charts:
        if focus and ch.difficulty.lower() != focus.lower():
            continue
        st = cs.stats(ch, bpm)
        rv = cs.radar(ch, bpm, a.music_end - a.music_start)
        keep = ["steps (rows)", "notes/sec", "jump %", "jump run lengths", "jack run lengths (same arrow N times)",
                "L<->R side-to-side % of single-step moves", "flow run avg length", "holds",
                "hold lengths (beats)", "holds that force a crossover", "subdivisions"]
        parts += ["", f"## Chart: {ch.difficulty} (meter {ch.meter})",
                  "Settings: " + (settings_text(spec_by[ch.difficulty]) if ch.difficulty in spec_by else "unknown"),
                  "Stats: " + "; ".join(f"{k} {st[k]}" for k in keep if k in st),
                  "Groove radar: " + ", ".join(f"{k} {v:.2f}" for k, v in rv.items()),
                  "Steps per measure (beat:arrows, beat 1-4.75, L D U R, two letters = jump):",
                  chart_text(ch, bpm, offset, a)]
    return "\n".join(parts), meta, specs


# --------------------------------------------------------------------------
# providers (plain HTTP, no extra packages)
# --------------------------------------------------------------------------

def _post(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"{url.split('/')[2]} said {e.code}: {e.read().decode(errors='replace')[:800]}")
    except urllib.error.URLError as e:
        sys.exit(f"couldn't reach {url}: {e.reason}")


def ask_gemini(prompt: str, model: str) -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        sys.exit("set GEMINI_API_KEY (free key at https://aistudio.google.com/apikey), "
                 "or use --prompt-only and paste the prompt into Gemini yourself")
    r = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
              {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
               "generationConfig": {"responseMimeType": "application/json"}},
              {"x-goog-api-key": key})
    try:
        return "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError):
        sys.exit(f"unexpected Gemini reply: {json.dumps(r)[:800]}")


def ask_claude(prompt: str, model: str) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("set ANTHROPIC_API_KEY, or use --prompt-only")
    r = _post("https://api.anthropic.com/v1/messages",
              {"model": model, "max_tokens": 16000, "fallbacks": "default",
               "messages": [{"role": "user", "content": prompt}]},
              {"x-api-key": key, "anthropic-version": "2023-06-01",
               "anthropic-beta": "server-side-fallback-2026-07-01"})
    if r.get("stop_reason") == "refusal":
        sys.exit("Claude declined this request")
    return "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")


def ask_local(prompt: str, model: str, base: str) -> str:
    r = _post(base.rstrip("/") + "/chat/completions",
              {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3}, {})
    try:
        return r["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        sys.exit(f"unexpected reply from the local server: {json.dumps(r)[:800]}")


def parse_reply(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        sys.exit("the model didn't answer with JSON:\n" + text[:2000])
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        sys.exit("the model's JSON didn't parse:\n" + text[:2000])


# --------------------------------------------------------------------------
# report and re-run
# --------------------------------------------------------------------------

SET_RE = re.compile(r"^(Easy|Medium|Hard|Challenge|Beginner)\.([a-z_0-9]+)=-?[0-9.]+$", re.I)
KNOWN = set(sg.DiffSpec.__dataclass_fields__) - {"name"}


def valid_sets(o: dict) -> list[str]:
    """Only changes stepgen understands: Difficulty.setting=number."""
    out = []
    for s in o.get("set", []):
        s = str(s).replace(" ", "")
        m = SET_RE.match(s)
        if m and m.group(2) in KNOWN:
            out.append(s)
    return out


def rerun_cmd(meta: dict, sets: list[str]) -> list[str]:
    cmd = [sys.executable, str(HERE / "stepgen.py"), meta["source"], "--out", meta["out"],
           "--title", meta["title"], "--seed", str(meta.get("seed", 1)),
           "--profile", meta.get("profile", "patterns")]
    if meta.get("artist"):
        cmd += ["--artist", meta["artist"]]
    if meta.get("bpm"):
        cmd += ["--bpm", str(meta["bpm"])]
    if meta.get("keep_format"):
        cmd.append("--keep-format")
    if (meta.get("art") or {}).get("on") is False:
        cmd.append("--no-art")
    for k, v in (meta.get("easy") or {}).items():
        cmd += ["--easy", f"{k}={v}"]
    for s in list(meta.get("set", [])) + sets:
        cmd += ["--set", s]
    return cmd


def quote(cmd: list[str]) -> str:
    return " ".join(f'"{c}"' if " " in c else c for c in cmd)


def report(rv: dict, meta: dict, provider: str, model: str) -> str:
    md = [f"# Chart review ({provider}, {model})", "", rv.get("summary", ""), "", "## Issues", ""]
    issues = rv.get("issues", [])
    if issues:
        md += ["| Difficulty | Measures | Severity | Problem |", "|---|---|---|---|"]
        md += [f"| {i.get('difficulty', '')} | {i.get('measures', '')} | {i.get('severity', '')} | "
               f"{str(i.get('problem', '')).replace('|', '/')} |" for i in issues]
    else:
        md.append("None flagged.")
    md += ["", "## Options", ""]
    for n, o in enumerate(rv.get("options", []), 1):
        sets = valid_sets(o)
        md += [f"**{n}. {o.get('title', '')}**", "", o.get("why", ""), ""]
        if o.get("tradeoff"):
            md += [f"Trade-off: {o['tradeoff']}", ""]
        md += ["Changes: " + (", ".join(f"`{s}`" for s in sets) or "none the settings can make"), ""]
        if sets and meta.get("source"):
            md += ["```", quote(rerun_cmd(meta, sets)), "```", ""]
    return "\n".join(md)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("chart", type=Path, help="a .sm made by stepgen")
    ap.add_argument("--provider", choices=["gemini", "claude", "local"], default="gemini")
    ap.add_argument("--model", help="model name (defaults: " + ", ".join(f"{k} {v}" for k, v in DEFAULT_MODELS.items()) + ")")
    ap.add_argument("--local-url", default=os.environ.get("LOCAL_LLM_URL", "http://localhost:1234/v1"),
                    help="OpenAI-compatible server for --provider local (LM Studio default)")
    ap.add_argument("--difficulty", help="review only this chart, e.g. Hard")
    ap.add_argument("--prompt-only", action="store_true", help="write the prompt to a file and stop")
    ap.add_argument("--from-reply", nargs="?", type=Path, const=True, metavar="FILE",
                    help="read a model's answer you pasted into FILE (default "
                         "<title>.review-reply.txt next to the chart) instead of calling an API")
    ap.add_argument("--no-ask", action="store_true", help="don't offer to regenerate")
    args = ap.parse_args(argv)

    sm = args.chart
    if args.from_reply:
        src = side(sm, ".review-reply.txt") if args.from_reply is True else args.from_reply
        if not src.is_file():
            sys.exit(f"paste the model's answer into {src} first")
        meta, _ = load_meta(sm)
        rv = parse_reply(src.read_text(encoding="utf-8", errors="replace"))
        return finish(rv, meta, sm, "pasted reply", src.name, args.no_ask)

    prompt, meta, _ = build_prompt(sm, args.difficulty)
    if args.prompt_only:
        out = side(sm, ".review-prompt.md")
        out.write_text(prompt, encoding="utf-8")
        print(f"prompt written to {out} ({len(prompt) // 4} tokens or so). Paste it into any chat app,\n"
              f"save its answer as {sm.stem}.review-reply.txt next to the chart, then run:\n"
              f'  python llm_review.py "{sm}" --from-reply')
        return 0

    model = args.model or DEFAULT_MODELS[args.provider]
    print(f"asking {args.provider} ({model}) ...", file=sys.stderr)
    if args.provider == "gemini":
        text = ask_gemini(prompt, model)
    elif args.provider == "claude":
        text = ask_claude(prompt, model)
    else:
        text = ask_local(prompt, model, args.local_url)
    return finish(parse_reply(text), meta, sm, args.provider, model, args.no_ask)


def finish(rv: dict, meta: dict, sm: Path, provider: str, model: str, no_ask: bool) -> int:
    md = report(rv, meta, provider, model)
    out = side(sm, ".review.md")
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"\nsaved to {out}")

    options = [o for o in rv.get("options", []) if valid_sets(o)]
    if no_ask or not options or not meta.get("source") or not sys.stdin.isatty():
        return 0
    pick = input(f"\nRegenerate with an option? 1-{len(rv.get('options', []))}, or Enter to skip: ").strip()
    if pick.isdigit() and 1 <= int(pick) <= len(rv.get("options", [])):
        o = rv["options"][int(pick) - 1]
        sets = valid_sets(o)
        cmd = rerun_cmd(meta, sets)
        print(quote(cmd))
        return subprocess.call(cmd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
