"""Song artwork for the StepMania song folder: banner, background and jacket.

Where the picture comes from, in order:
  1. an image next to the song: the same name as the song (Song.jpg for
     Song.mp3), else cover/folder/front/album .jpg or .png
  2. art made on an earlier run, kept as it is (so hand edits survive and
     nothing is fetched twice; delete the files to make them again)
  3. the cover art inside the song file's own tags (MP3, FLAC, Ogg, M4A)
  4. only when asked (--art-online): looked up online by title and artist,
     on MusicBrainz with its Cover Art Archive, else the iTunes Search API.
     Each address is printed before it's fetched.

From the one picture it writes <title>-bn.png (418x164 banner),
<title>-bg.png (640x480 background, dimmed so the arrows stay readable)
and <title>-jacket.png (512x512). Resizing uses Qt (in the app) or Pillow;
with neither, the picture is copied as it is and StepMania stretches it.

    python artwork.py song.mp3 [--online] [--artist A] [--title T] [--out DIR]
"""
from __future__ import annotations

import base64
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BANNER = (418, 164)
BACKGROUND = (640, 480)
JACKET = (512, 512)
NEXT_TO_SONG = ("cover", "folder", "front", "album", "albumart")
IMAGE_EXT = (".jpg", ".jpeg", ".png")
MIN_SIZE = 200          # smaller than this looks like mush on a 640x480 background

USER_AGENT = "BeatSmith/0.0.1 ( https://github.com/paul-lapczynski/beatsmith )"   # MusicBrainz asks for one
MUSICBRAINZ = "https://musicbrainz.org/ws/2/recording/"
COVER_ART_ARCHIVE = "https://coverartarchive.org"
ITUNES = "https://itunes.apple.com/search"
# for the app's tooltip and the README: every place an online lookup reaches
ONLINE_SOURCES = [
    ("Song search by title and artist", "https://musicbrainz.org (MusicBrainz)"),
    ("Cover pictures for what it finds", "https://coverartarchive.org (Cover Art Archive; "
                                         "the files come from archive.org)"),
    ("When MusicBrainz has none", "https://itunes.apple.com (iTunes Search API; "
                                  "the pictures come from Apple's mzstatic.com)"),
]


def file_names(title: str) -> dict[str, str]:
    """The .sm tag for each picture and its file name in the song folder."""
    return {"BANNER": f"{title}-bn.png", "BACKGROUND": f"{title}-bg.png", "JACKET": f"{title}-jacket.png"}


# ------------------------------------------------------------------ finding

def next_to(src: Path) -> Path | None:
    """An image beside the song: its own name first, then an album cover."""
    for stem in (src.stem, *NEXT_TO_SONG):
        for ext in IMAGE_EXT:
            for name in (stem + ext, stem.capitalize() + ext, stem.upper() + ext):
                p = src.with_name(name)
                if p.is_file():
                    return p
    return None


def embedded(src: Path) -> bytes | None:
    """The front cover from the song file's tags, else any picture in them."""
    try:
        import mutagen
        f = mutagen.File(str(src))
    except Exception:
        return None
    if f is None:
        return None
    pics = []                                   # (is the front cover, bytes)
    tags = getattr(f, "tags", None) or {}
    try:
        for key in list(tags.keys()):
            v = tags[key]
            if key.startswith("APIC"):                          # MP3 (ID3)
                pics.append((v.type == 3, v.data))
            elif key == "covr":                                 # M4A
                pics += [(True, bytes(c)) for c in v]
            elif key.lower() == "metadata_block_picture":       # Ogg / Opus
                from mutagen.flac import Picture
                for b64 in v:
                    p = Picture(base64.b64decode(b64))
                    pics.append((p.type == 3, p.data))
    except Exception:
        pass
    for p in getattr(f, "pictures", []) or []:                  # FLAC
        pics.append((p.type == 3, p.data))
    pics.sort(key=lambda x: not x[0])
    return pics[0][1] if pics else None


def _norm(s: str) -> str:
    s = re.sub(r"\s*[\(\[].*?[\)\]]", "", s.casefold())         # "(Radio Edit)", "[feat. X]"
    s = re.sub(r"\b(feat|ft)\..*$", "", s)
    return re.sub(r"[^\w]+", "", s)


def _same(a: str, b: str) -> bool:
    a, b = _norm(a), _norm(b)
    return bool(a and b) and (a == b or a.startswith(b) or b.startswith(a))


def _get(url: str, log, accept: str = "application/json") -> bytes | None:
    log(f"  artwork: fetching {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 503 and attempt == 0:      # MusicBrainz: over one request a second
                time.sleep(1.5)
                continue
            if e.code != 404:
                log(f"  artwork: {e.code} {e.reason}")
            return None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            log(f"  artwork: couldn't reach it ({getattr(e, 'reason', e)})")
            return None
    return None


def _clean(s: str) -> str:
    """A title as a search wants it: no "(CAUTION)", "[Official Video]",
    "feat. X", track numbers or underscores."""
    s = re.sub(r"\s*[\(\[\{].*?[\)\]\}]", " ", s.replace("_", " "))
    s = re.sub(r"\s+\b(feat|ft|featuring)\b\.?\s.*$", "", s, flags=re.I)
    s = re.sub(r"^\s*\d{1,3}\s*[.\-)]?\s+(?=\D)", "", s)         # "01 - ", "07. "
    return re.sub(r"\s+", " ", s).strip(" -")


def guesses(title: str, artist: str) -> list[tuple[str, str]]:
    """(title, artist) pairs to search for, best first. Without an artist,
    one is guessed from the name ("Artist - Title", "ARTIST-TITLE"), and
    last of all the title is searched on its own ("" for the artist)."""
    t, a = _clean(title), _clean(artist)
    out = []
    if a:
        out.append((t, a))
    for sep in (r"\s+[-\u2013\u2014]\s+", r"\s*[-\u2013\u2014]\s*"):
        parts = re.split(sep, t, maxsplit=1)
        if len(parts) == 2 and all(parts):
            if not a:
                out += [(parts[1], parts[0]), (parts[0], parts[1])]    # "Artist - Title", then the other way
            elif _same(parts[0], a):
                out.append((parts[1], a))                              # the artist written in the title too
            break
    if not a:
        out.append((t, ""))
    seen, res = set(), []
    for g in out:
        k = (_norm(g[0]), _norm(g[1]))
        if k[0] and k not in seen:
            seen.add(k)
            res.append(g)
    return res[:4]


def _lucene(s: str) -> str:
    return re.sub(r'[+\-&|!(){}\[\]^"~*?:\\/\']', " ", s).strip()


def _exact(a: str, b: str) -> bool:
    return bool(_norm(a)) and _norm(a) == _norm(b)


def musicbrainz(title: str, artist: str, log) -> tuple[bytes, str] | None:
    q = f"recording:({_lucene(title)})" + (f" AND artist:({_lucene(artist)})" if artist else "")
    data = _get(f"{MUSICBRAINZ}?{urllib.parse.urlencode({'query': q, 'fmt': 'json', 'limit': 15})}", log)
    try:
        recs = json.loads(data)["recordings"] if data else []
    except (ValueError, KeyError):
        return None
    groups, releases = [], []
    for rec in recs:
        credit = "".join(c.get("name", "") + c.get("joinphrase", "") for c in rec.get("artist-credit", []))
        if artist:
            ok = rec.get("score", 0) >= 60 and _same(rec.get("title", ""), title) and _same(credit, artist)
        else:                       # the title alone: only an exact, confident match
            ok = rec.get("score", 0) >= 95 and _exact(rec.get("title", ""), title)
        if not ok:
            continue
        for rel in rec.get("releases", []):
            rg = rel.get("release-group", {})
            # the artist's own albums and singles before compilations and live records
            plain = rel.get("status") == "Official" and not rg.get("secondary-types")
            rank = (not plain, rg.get("primary-type") not in ("Album", "Single", "EP"))
            what = f"{credit} - {rec.get('title', '')}"
            if rg.get("id"):
                groups.append((rank, rg["id"], what))
            releases.append((rank, rel["id"], what))
        if not artist and (groups or releases):
            break                   # without an artist, only the best match's covers
    for kind, ids in (("release-group", groups), ("release", releases)):
        seen = []
        for _, i, what in sorted(ids, key=lambda x: x[0]):
            if i not in [x for x, _ in seen]:
                seen.append((i, what))
        for i, what in seen[:3]:
            img = _get(f"{COVER_ART_ARCHIVE}/{kind}/{i}/front-500", log, accept="image/*")
            if img:
                return img, what
    return None


def itunes(title: str, artist: str, log) -> tuple[bytes, str] | None:
    term = f"{artist} {title}".strip()
    data = _get(f"{ITUNES}?{urllib.parse.urlencode({'term': term, 'entity': 'song', 'limit': 15})}", log)
    try:
        results = json.loads(data)["results"] if data else []
    except (ValueError, KeyError):
        return None
    for r in results:
        url = r.get("artworkUrl100", "")
        track, by = r.get("trackName", ""), r.get("artistName", "")
        ok = (_same(track, title) and _same(by, artist)) if artist else _exact(track, title)
        if url and ok:
            img = _get(url.replace("100x100bb", "600x600bb"), log, accept="image/*")
            if img:
                return img, f"{by} - {track}"
    return None


def online(title: str, artist: str, log=print) -> tuple[bytes, dict] | None:
    """Search by title and artist, trying a few readings of the name; the
    record says which song it matched, to check in the Details tab."""
    last_mb = 0.0
    for t, a in guesses(title, artist):
        log(f"  artwork: searching for {a + ' - ' if a else ''}{t}" + ("" if a else " (title only)"))
        for name, fn in (("MusicBrainz / Cover Art Archive", musicbrainz), ("iTunes", itunes)):
            if fn is musicbrainz:   # MusicBrainz allows one request a second
                time.sleep(max(0.0, 1.1 - (time.monotonic() - last_mb)))
                last_mb = time.monotonic()
            found = fn(t, a, log)
            if found and _size(found[0])[0] >= MIN_SIZE:
                where = {"from": name, "match": found[1]}
                if not a:
                    where["note"] = "matched by title only: check it's the right song"
                return found[0], where
    log(f"  artwork: nothing found online for {title}")
    return None


# ------------------------------------------------------------------ drawing

def _size(data: bytes) -> tuple[int, int]:
    """Width and height of a PNG or JPEG without decoding it; (0, 0) if neither."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    i = 2
    if data[:2] != b"\xff\xd8":
        return 0, 0
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker, n = data[i + 1], int.from_bytes(data[i + 2:i + 4], "big")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + n
    return 0, 0


def _layouts():
    """For each picture: (size, how big the sharp cover is in it, brightness
    of the blurred fill behind it, brightness of the cover)."""
    return {"BANNER": (BANNER, BANNER[1], 0.55, 1.0),
            "BACKGROUND": (BACKGROUND, 360, 0.35, 0.8),
            "JACKET": (JACKET, JACKET[0], 1.0, 1.0)}


def _draw_qt(data: bytes, out: dict[str, Path]) -> bool:
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QImage, QPainter
    img = QImage.fromData(data)
    if img.isNull():
        return False
    img = img.convertToFormat(QImage.Format_RGB32)
    for tag, ((w, h), side, fill, front) in _layouts().items():
        canvas = QImage(w, h, QImage.Format_RGB32)
        p = QPainter(canvas)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        # behind: the cover filling the frame, blurred (shrunk, then grown back) and dimmed
        big = img.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        big = big.copy((big.width() - w) // 2, (big.height() - h) // 2, w, h)
        blur = big.scaled(max(1, w // 24), max(1, h // 24), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        p.drawImage(QRect(0, 0, w, h), blur if side < max(w, h) else big)
        if fill < 1:
            p.fillRect(0, 0, w, h, QColor(0, 0, 0, round(255 * (1 - fill))))
        if side < max(w, h):
            # in front: the whole cover, sharp
            x = (w - side) // 2 if tag != "BANNER" else 0
            p.drawImage(QRect(x, (h - side) // 2, side, side),
                        img.scaled(side, side, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
            if front < 1:
                p.fillRect(x, (h - side) // 2, side, side, QColor(0, 0, 0, round(255 * (1 - front))))
        p.end()
        canvas.save(str(out[tag]), "PNG")
    return True


def _draw_pil(data: bytes, out: dict[str, Path]) -> bool:
    import io
    from PIL import Image, ImageEnhance, ImageOps
    img = Image.open(io.BytesIO(data)).convert("RGB")
    for tag, ((w, h), side, fill, front) in _layouts().items():
        big = ImageOps.fit(img, (w, h), Image.LANCZOS)
        if side < max(w, h):
            canvas = big.resize((max(1, w // 24), max(1, h // 24)), Image.BILINEAR).resize((w, h), Image.BILINEAR)
        else:
            canvas = big
        if fill < 1:
            canvas = ImageEnhance.Brightness(canvas).enhance(fill)
        if side < max(w, h):
            cover = ImageOps.fit(img, (side, side), Image.LANCZOS)
            if front < 1:
                cover = ImageEnhance.Brightness(cover).enhance(front)
            canvas.paste(cover, ((w - side) // 2 if tag != "BANNER" else 0, (h - side) // 2))
        canvas.save(out[tag], "PNG")
    return True


def draw(data: bytes, out: dict[str, Path]) -> None:
    """Write the banner, background and jacket from one picture."""
    for fn in (_draw_qt, _draw_pil):
        try:
            if fn(data, out):
                return
        except ImportError:
            continue
    # no way to resize: the picture as it is, under each name
    for path in out.values():
        path.write_bytes(data)


# ------------------------------------------------------------------ all of it

KEPT = "already in the song folder"


def describe(where: dict) -> str:
    """Where a picture came from, in words."""
    out = where.get("from") or "nowhere"
    if where.get("file"):
        out += f" ({where['file']})"
    if where.get("match"):
        out += f", matched to \u201c{where['match']}\u201d"
    if where.get("note"):
        out += f" ({where['note']})"
    return out


def find(src: Path, title: str, artist: str, song: Path | None = None, look_online: bool = False,
         log=print) -> tuple[bytes | None, dict]:
    """The picture for a song and where it came from. With the song folder
    given, art already in it is kept: (None, {"from": KEPT})."""
    pic = next_to(src)
    if pic is not None:
        # put there by hand for this song: always used
        return pic.read_bytes(), {"from": "image next to the song", "file": pic.name}
    if song is not None and all((song / n).is_file() for n in file_names(title).values()):
        # an earlier run's, or hand-made: kept, and nothing fetched again
        return None, {"from": KEPT}
    data = embedded(src)
    if data is not None:
        return data, {"from": "the song file's cover art"}
    if look_online:
        print("progress: finding artwork", file=sys.stderr, flush=True)
        found = online(title, artist, log)
        if found:
            return found
    return None, {"from": None}


def make(src: Path, song: Path, title: str, artist: str, look_online: bool = False,
         log=print, image: Path | None = None, image_from: str | None = None) -> tuple[dict[str, str], dict]:
    """Find a picture for the song and write its art into the song folder.
    `image` is one already chosen (the app finds it when the song is added).

    Returns the .sm tags to fill ({"BANNER": file name, ...}, empty when
    there is none) and a record of where it came from."""
    names = file_names(title)
    if image is not None:
        data, where = image.read_bytes(), {"from": image_from or "chosen in the app"}
    else:
        data, where = find(src, title, artist, song, look_online, log)
    if where["from"] == KEPT:
        log("  artwork: kept what's in the song folder (delete it to make it again)")
        return names, where
    if data is None:
        return {}, where
    draw(data, {tag: song / n for tag, n in names.items()})
    log(f"  artwork: from {describe(where)}")
    return names, where


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", type=Path)
    ap.add_argument("--title")
    ap.add_argument("--artist", default="")
    ap.add_argument("--online", action="store_true", help="look it up online when the song has none")
    ap.add_argument("--out", type=Path, default=Path("."))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    names, where = make(args.audio, args.out, args.title or args.audio.stem, args.artist, args.online)
    print(json.dumps({"tags": names, **where}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
