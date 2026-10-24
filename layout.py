"""Where a song's files go.

    <output folder>/<title>/                 stats, settings, stems, compare charts...
    <output folder>/<title>/<title>/         just <title>.sm and the song: copy this
                                             folder into StepMania's Songs/<group>/

Songs made before this layout have everything in <output folder>/<title>/;
the helpers below find their files too.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path


# Korean (Hangul) in Latin letters, the Revised Romanization without its
# sound-change rules: each syllable is an initial, a vowel and a final
_L = "g kk n d tt r m b pp s ss - j jj ch k t p h".split()
_V = "a ae ya yae eo e yeo ye o wa wae oe yo u wo we wi yu eu ui i".split()
_T = "- k k k n n n t l k m l l l p l m p p t t ng t t k t p t".split()


def romanize(s: str) -> str:
    out = []
    for ch in s:
        i = ord(ch) - 0xAC00
        if 0 <= i < 11172:
            out.append((_L[i // 588] + _V[i % 588 // 28] + _T[i % 28]).replace("-", ""))
        else:
            out.append(ch)
    # a capital at the start of each Korean word
    return re.sub(r"(?<![A-Za-z])([a-z])", lambda m: m.group(1).upper(), "".join(out)) if out != list(s) else s


def _plain(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r'[<>:"/\\|?*]', "", s)
    s = re.sub(r"\(\s*\)|\[\s*\]|\{\s*\}", "", s)            # brackets that held only other letters
    return re.sub(r"\s+", " ", s).strip(" .-_")


def _latin(s: str) -> str:
    """s in plain letters: what's already Latin, else Korean spelled out."""
    p = _plain(s)
    return p if re.search(r"[A-Za-z0-9]", p) else _plain(romanize(s))


def file_name(title: str, artist: str = "") -> str:
    """The folder and file name for a song: plain ASCII, because StepMania
    on Windows skips a song whose folder or files have other letters in
    their names (Korean, Japanese...). Accents become plain letters; what's
    in another script is dropped when the rest has Latin letters, else
    Korean is spelled out. With the artist in front when the title had
    other letters, so it's easy to tell apart: "(타샤니) Caution (경고)" by
    Tashannie is "Tashannie - Caution", "경고" by 타샤니 is "Tasyani - Gyeonggo".
    The title shown in StepMania keeps every letter (#TITLE)."""
    if title.isascii():                 # as before: only what Windows can't have in a name goes
        return re.sub(r'[<>:"/\\|?*]', "", title).strip().rstrip(".") or "song"
    t, a = _latin(title), _latin(artist)
    return (f"{a} - {t}" if a and t else t or a) or "song"


def song_dirs(out: Path, title: str) -> tuple[Path, Path]:
    """(outer folder for everything else, inner StepMania song folder)."""
    outer = out / title
    return outer, outer / title


def outer_of(sm: Path) -> Path:
    """The folder that holds a chart's stats, settings and the rest."""
    inner = sm.parent
    return inner.parent if inner.name == inner.parent.name else inner


def side(sm: Path, suffix: str) -> Path:
    """A file kept beside the song rather than in the StepMania folder,
    e.g. side(sm, ".stats.md")."""
    return outer_of(sm) / f"{sm.stem}{suffix}"


def find_sm(outer: Path, title: str) -> Path:
    """The chart of a song made in `outer`, in either layout."""
    new = outer / title / f"{title}.sm"
    return new if new.is_file() or not (outer / f"{title}.sm").is_file() else outer / f"{title}.sm"
