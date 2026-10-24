"""Where a song's files go.

    <output folder>/<title>/                 stats, settings, stems, compare charts...
    <output folder>/<title>/<title>/         just <title>.sm and the song: copy this
                                             folder into StepMania's Songs/<group>/

Songs made before this layout have everything in <output folder>/<title>/;
the helpers below find their files too.
"""
from __future__ import annotations

from pathlib import Path


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
