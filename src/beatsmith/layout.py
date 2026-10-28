"""Where a song's files go.

    <output folder>/<title>/                 just <title>.sm, the song and its pictures:
                                             the output folder can be StepMania's
                                             Songs/<group>/ itself
    <app data>/songs/<output folder>-<id>/<title>/
                                             stats, settings, stems, compare charts...
                                             (song-data/ beside this file when run
                                             from source rather than installed)

Songs made before this have the rest in <output folder>/<title>/ and the
StepMania folder inside it (<output folder>/<title>/<title>/), or, older
still, everything in <output folder>/<title>/. The helpers below find
their files too, and migrate() moves such a song to this layout.
"""
from __future__ import annotations

from beatsmith.resources import source_root

import hashlib
import os
import re
import shutil
import sys
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


def data_dir(name: str = "BeatSmith") -> Path:
    """The app's own data folder, the one the app's QStandardPaths
    AppDataLocation gives (BEATSMITH_DATA overrides it)."""
    if os.environ.get("BEATSMITH_DATA"):
        return Path(os.environ["BEATSMITH_DATA"])
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / name / name


def move_old_data() -> None:
    """Before the rename to BeatSmith the app's data folder was
    stepgen/stepgen: move it over the first time BeatSmith runs."""
    old, new = data_dir("stepgen"), data_dir()
    if old.is_dir() and not new.exists() and old != new:
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old), str(new))


def songs_data() -> Path:
    """Where the stats, settings and the rest of made songs go: the app's
    data folder when installed, song-data/ in the source folder when run
    from source, so it's at hand while developing (BEATSMITH_DATA overrides
    both)."""
    if getattr(sys, "frozen", False) or os.environ.get("BEATSMITH_DATA"):
        return data_dir() / "songs"
    return source_root() / "song-data"


def work_root(out: Path) -> Path:
    """Where the stats, settings and the rest of an output folder's songs
    go: one folder per output folder, named after it so it's easy to find."""
    full = os.path.normcase(os.path.abspath(out))
    tag = hashlib.sha1(full.encode("utf-8")).hexdigest()[:8]
    return songs_data() / f"{_plain(Path(os.path.abspath(out)).name) or 'songs'}-{tag}"


def song_dirs(out: Path, title: str) -> tuple[Path, Path]:
    """(folder for everything else, StepMania song folder)."""
    return work_root(out) / title, out / title


def _old_nested(sm: Path) -> bool:
    """<output folder>/<title>/<title>/<title>.sm, with the rest one level up
    (an output folder named like one of its songs would read as this too)."""
    return sm.parent.name == sm.parent.parent.name


def out_of(sm: Path) -> Path:
    """The output folder a chart was made in."""
    return sm.parent.parent.parent if _old_nested(sm) else sm.parent.parent


def outer_of(sm: Path) -> Path:
    """The folder that holds a chart's stats, settings and the rest."""
    if (sm.parent / f"{sm.stem}.stepgen.json").is_file():
        return sm.parent                     # the oldest layout: all in one folder
    if _old_nested(sm):
        return sm.parent.parent
    return song_dirs(sm.parent.parent, sm.parent.name)[0]


def song_folders(sm: Path) -> list[Path]:
    """Every folder that belongs to a made song: its StepMania folder and
    the one with the rest (the same folder in the old layouts)."""
    outer = outer_of(sm)
    if outer in (sm.parent, sm.parent.parent):
        return [outer]
    return [sm.parent, outer]


def side(sm: Path, suffix: str) -> Path:
    """A file kept beside the song rather than in the StepMania folder,
    e.g. side(sm, ".stats.md")."""
    return outer_of(sm) / f"{sm.stem}{suffix}"


def find_sm(folder: Path, title: str) -> Path:
    """The chart of the song in <output folder>/<title>/, in any layout."""
    nested = folder / title / f"{title}.sm"
    return nested if nested.is_file() else folder / f"{title}.sm"


def migrate(out: Path, title: str, log=print) -> None:
    """Move a song made in an older layout to this one: its StepMania
    files to <output folder>/<title>/ and the rest to the app's data
    folder. Nothing happens to a song already in this layout."""
    folder = out / title
    inner = folder / title
    work = song_dirs(out, title)[0]
    if (inner / f"{title}.sm").is_file():
        keep = {inner.name}                  # the rest one level up, the song in <title>/<title>/
    elif (folder / f"{title}.stepgen.json").is_file():
        keep = {f"{title}.sm"} | {v for v in _file_tags(folder / f"{title}.sm").values() if v}
        inner = None                         # the oldest layout: all in one folder
    else:
        return
    work.mkdir(parents=True, exist_ok=True)
    for f in list(folder.iterdir()):
        if f.name not in keep:
            _move(f, work / f.name)
    if inner is not None:                    # bring the StepMania folder's files up a level
        for f in list(inner.iterdir()):
            _move(f, folder / f.name)
        inner.rmdir()
    log(f"  moved {title} to the new layout: stats and settings are in {work}")


def _move(f: Path, dest: Path) -> None:
    if dest.is_dir():
        shutil.rmtree(dest)
    elif dest.exists():
        dest.unlink()
    shutil.move(str(f), str(dest))


def _file_tags(sm: Path) -> dict[str, str]:
    text = sm.read_text(encoding="utf-8", errors="replace")
    head = text[:text.find("#NOTES:")] if "#NOTES:" in text else text
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"#(MUSIC|BANNER|BACKGROUND|JACKET|CDTITLE):([^;]*);", head)}
