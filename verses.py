"""AI verse detection: name a song's sections from its lyrics.

stepgen's own section names are guesses from the music (loudness, what
repeats). The words settle what the music can't: a chorus is the same words
coming back, a verse is new words (often over the same music as another
verse), and no words at all is an intro, outro, break or solo. The words come
from lyrics.py (Whisper, run on the separated vocals by the lyrics add-on).

Only the names change, never the section lines. A song with hardly any
words (an instrumental) keeps the names from the music.
"""
from __future__ import annotations

import re
from collections import Counter

MIN_WORDS = 30          # fewer words in the whole song: treat it as instrumental
SUNG = 1.0              # words per bar for a section to count as sung
REPEATED = 0.45         # share of a section's word triples heard in another section: repeated lyrics


def _norm(w: str) -> str:
    return re.sub(r"[^\w']", "", w.lower())


def _triples(tokens: list[str]) -> set[tuple[str, ...]]:
    return {tuple(tokens[k:k + 3]) for k in range(len(tokens) - 2)}


def _triples_list(tokens: list[str]) -> list[tuple[str, ...]]:
    return [tuple(tokens[k:k + 3]) for k in range(len(tokens) - 2)]


def section_words(a, sections: list[dict], words) -> list[list[str]]:
    """The words sung in each section ([start, end, word] in song seconds)."""
    measure = 4 * a.spb
    out = []
    for s in sections:
        t0, t1 = a.t0 + s["start"] * measure, a.t0 + s["end"] * measure
        out.append([_norm(w) for st, en, w in words if t0 <= (st + en) / 2 < t1 and _norm(w)])
    return out


def relabel(a, sections: list[dict], words, all_words=None) -> list[dict]:
    """Sections with names from the lyrics, each also given "sung" (bool) and
    "lyrics" (its first few words). Unchanged when the song has too few words.
    all_words: the whole song's words, when `words` are of a shortened cut
    (a chorus heard once in the cut is still the chorus)."""
    corpus = all_words if all_words is not None else words
    if not words or not corpus or len(corpus) < MIN_WORDS:
        return sections
    toks = section_words(a, sections, words)
    secs = [dict(s) for s in sections]
    # how often each run of three words is sung in the whole song
    heard = Counter(_triples_list([_norm(w) for _, _, w in corpus if _norm(w)]))
    for i, s in enumerate(secs):
        tri = _triples(toks[i])
        s["sung"] = len(toks[i]) / max(1, s["end"] - s["start"]) >= SUNG
        s["lyrics"] = " ".join(toks[i][:8]) + (" ..." if len(toks[i]) > 8 else "")
        s["repeated"] = s["sung"] and bool(tri) and sum(heard[t] >= 2 for t in tri) / len(tri) >= REPEATED
    rep = [s for s in secs if s["repeated"]]
    loudest = max((s["intensity"] for s in rep), default=0.0)
    count = {}
    for s in secs:
        count[s["letter"]] = count.get(s["letter"], 0) + 1
    choruses = [i for i, s in enumerate(secs) if s["repeated"] and s["intensity"] >= 0.85 * loudest]
    last = len(secs) - 1
    for i, s in enumerate(secs):
        quiet = s["intensity"] < 0.45
        if s["repeated"]:
            # words that come back: the chorus, or the build into it
            nxt = secs[i + 1] if i < last else None
            s["label"] = "chorus" if i in choruses or not (nxt and nxt.get("repeated")) else "build"
        elif s["sung"]:
            between = choruses and choruses[0] < i < choruses[-1]
            s["label"] = "bridge" if between and count[s["letter"]] == 1 else "verse"
        elif i == 0:
            s["label"] = "intro"
        elif i == last:
            s["label"] = "outro"
        elif quiet:
            s["label"] = "breakdown"
        elif s["label"] == "verse":
            s["label"] = "build"                       # no words: not a verse, whatever the music says
    return secs
