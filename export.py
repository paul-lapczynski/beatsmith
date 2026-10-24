"""Copy made songs out to StepMania, or into a zip.

Only what StepMania needs goes: the chart, the song and the banner,
background and jacket the chart names. Each song gets a folder with a
plain-ASCII name, and so does every file in it (StepMania on Windows skips a
song whose folder or files have other letters in their names); the chart's
#MUSIC, #BANNER... are changed to match. #TITLE and the rest keep every
letter.

    python export.py <output folder> <destination folder or .zip> [song...]
"""
from __future__ import annotations

import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from layout import file_name

CHART_EXT = (".sm", ".ssc", ".dwi")
# the file tags a chart names, and what an ASCII copy of each is called
# after the song's folder: "<folder>-bn.png" and so on
FILE_TAGS = {"MUSIC": "", "BANNER": "-bn", "BACKGROUND": "-bg", "JACKET": "-jacket", "CDTITLE": "-cdtitle"}


@dataclass
class Song:
    sm: Path                    # the chart in the output folder
    title: str
    artist: str
    meters: dict[str, str] = field(default_factory=dict)

    @property
    def name(self) -> str:
        """The folder the song is exported as."""
        return file_name(self.sm.stem, self.artist)


def tags(sm: Path) -> dict[str, str]:
    """The chart's header tags (#TITLE:...;), up to the first chart."""
    out = {}
    for m in re.finditer(r"#([A-Z]+):([^;]*);", _header(sm.read_text(encoding="utf-8", errors="replace"))):
        out.setdefault(m.group(1), m.group(2).strip())
    return out


def _header(text: str) -> str:
    i = text.find("#NOTES:")
    return text if i < 0 else text[:i]


def made_songs(folder: Path) -> list[Song]:
    """The songs stepgen made in an output folder, in either layout
    (<title>/<title>/<title>.sm, or <title>/<title>.sm from before)."""
    found: dict[Path, Song] = {}
    if not folder.is_dir():
        return []
    for sm in list(folder.glob("*/*/*.sm")) + list(folder.glob("*/*.sm")):
        # only the song's own chart, not the ones kept in .compare/ and such
        if sm.stem != sm.parent.name or (sm.parent.parent != folder and sm.parent.parent.name != sm.stem):
            continue
        try:
            t = tags(sm)
        except OSError:
            continue
        if not t.get("CREDIT", "").startswith("stepgen") or sm in found:
            continue
        found[sm] = Song(sm, t.get("TITLE") or sm.stem, t.get("ARTIST", ""))
    return sorted(found.values(), key=lambda s: s.title.lower())


def plan(song: Song, name: str) -> tuple[dict[str, Path], dict[str, str], list[str]]:
    """What a song's export holds: {file name in the export: source file},
    the chart's file tags renamed to match, and what's missing."""
    t = tags(song.sm)
    files: dict[str, Path] = {}
    renamed: dict[str, str] = {}
    missing = []
    for tag, suffix in FILE_TAGS.items():
        value = t.get(tag, "")
        if not value:
            continue
        src = song.sm.parent / value
        if not src.is_file():
            missing.append(f"{tag} {value}")
            continue
        new = src.name if src.name.isascii() else f"{name}{suffix}{src.suffix.lower()}"
        if new.lower() in (f.lower() for f in files) and files.get(new) != src:
            new = f"{name}{suffix or '-music'}{src.suffix.lower()}"
        files[new] = src
        renamed[tag] = new
    sm_name = song.sm.name if song.sm.name.isascii() else f"{name}.sm"
    files[sm_name] = song.sm
    return files, renamed, missing


def chart_text(sm: Path, renamed: dict[str, str]) -> bytes:
    """The chart with its file tags pointing at the exported names."""
    text = sm.read_bytes().decode("utf-8", errors="surrogateescape")
    head, rest = (text, "") if "#NOTES:" not in text else (text[:text.find("#NOTES:")], text[text.find("#NOTES:"):])
    for tag, new in renamed.items():
        head = re.sub(rf"#{tag}:[^;]*;", lambda m: f"#{tag}:{new};", head, count=1)
    return (head + rest).encode("utf-8", errors="surrogateescape")


def names(songs: list[Song]) -> list[str]:
    """A folder name for each song, told apart when two come out the same."""
    used, out = set(), []
    for s in songs:
        base, n = s.name, 1
        name = base
        while name.lower() in used:
            n += 1
            name = f"{base} ({n})"
        used.add(name.lower())
        out.append(name)
    return out


def not_ours(folder: Path) -> bool:
    """A folder in the destination that has charts stepgen didn't make:
    left alone rather than written over."""
    for f in folder.glob("*"):
        if f.suffix.lower() in CHART_EXT:
            try:
                if not tags(f).get("CREDIT", "").startswith("stepgen"):
                    return True
            except OSError:
                return True
    return False


def export(songs: list[Song], dest: Path, log=print, step=lambda i, n: True) -> list[str]:
    """Copy the songs into dest (a folder, e.g. StepMania's Songs/<group>)
    or into a zip when dest ends in .zip. Returns the folder names written.
    step(i, n) is called before each song; returning False stops."""
    as_zip = dest.suffix.lower() == ".zip"
    written = []
    zf = None
    if as_zip:
        dest.parent.mkdir(parents=True, exist_ok=True)
        zf = zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED)
    else:
        dest.mkdir(parents=True, exist_ok=True)
    try:
        for i, (song, name) in enumerate(zip(songs, names(songs))):
            if not step(i, len(songs)):
                break
            try:
                files, renamed, missing = plan(song, name)
            except OSError as e:
                log(f"{song.title}: can't read the chart ({e})")
                continue
            for m in missing:
                log(f"{song.title}: {m} isn't there, left out")
            if zf is not None:
                for fname, src in files.items():
                    arc = f"{name}/{fname}"
                    if src == song.sm:
                        zf.writestr(arc, chart_text(src, renamed))
                    else:
                        # audio and PNGs are already compressed
                        zf.write(src, arc, compress_type=zipfile.ZIP_STORED)
            else:
                out = dest / name
                if out.is_dir() and not_ours(out):
                    log(f"{song.title}: {out} has charts stepgen didn't make, left alone")
                    continue
                out.mkdir(exist_ok=True)
                # an earlier export's chart under another name would make a second song
                for old in out.glob("*"):
                    if old.suffix.lower() in CHART_EXT and old.name not in files:
                        old.unlink()
                for fname, src in files.items():
                    data = chart_text(src, renamed) if src == song.sm else src.read_bytes()
                    (out / fname).write_bytes(data)
            written.append(name)
    finally:
        if zf is not None:
            zf.close()
    return written


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2:
        print(__doc__)
        return 2
    songs = made_songs(Path(argv[0]))
    if argv[2:]:
        want = {a.lower() for a in argv[2:]}
        songs = [s for s in songs if s.title.lower() in want or s.sm.stem.lower() in want]
    done = export(songs, Path(argv[1]), log=lambda m: print(m.encode("ascii", "replace").decode()))
    print(f"exported {len(done)} song{'s' * (len(done) != 1)}: " + ", ".join(done))
    return 0


if __name__ == "__main__":
    sys.exit(main())
