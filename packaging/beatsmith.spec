# PyInstaller spec for the BeatSmith app. Built by build.bat on Windows and
# build-mac.sh on macOS; see BUILD.md.
from PyInstaller.utils.hooks import collect_all

root = SPECPATH + "/.."
datas = [(root + "/patterns.toml", "."), (root + "/profiles", "profiles"),
         (root + "/README.md", "."), (SPECPATH + "/beatsmith.png", "."),
         (root + "/stems.py", "."), (root + "/lyrics.py", "."),     # run by the optional add-ons' own Python
         (root + "/accel.py", ".")]
datas += [(root + "/models", "models")]                          # AI assist model
# the app's version, for what it tells web services about itself (artwork.py's User-Agent)
import os
with open(SPECPATH + "/version.txt", "w") as f:
    f.write(os.environ.get("BEATSMITH_VERSION", "0.0.1").lstrip("v"))
datas += [(SPECPATH + "/version.txt", ".")]
binaries, hidden = [], ["stepgen", "chartstats", "llm_review", "chart_editor", "groove", "layout", "shorten", "verses", "addons", "ai_assist", "accel", "artwork", "stems", "mutagen", "sounddevice"]
for pkg in ("librosa", "soundfile", "lazy_loader", "audioread", "soxr", "sounddevice", "_sounddevice_data", "onnxruntime"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hidden += h
# ffmpeg.exe for .wma/.m4a, if build.bat fetched it
import os
import sys
if os.path.isdir(SPECPATH + "/ffmpeg"):
    datas.append((SPECPATH + "/ffmpeg", "ffmpeg"))

a = Analysis([root + "/beatsmith_app.py"], pathex=[root], binaries=binaries, datas=datas,
             hiddenimports=hidden, excludes=["tkinter", "matplotlib", "IPython",
                      "torch", "torchaudio", "demucs"])   # vocal separation is a separate download
pyz = PYZ(a.pure)
mac = sys.platform == "darwin"
icon = SPECPATH + ("/beatsmith.icns" if mac else "/beatsmith.ico")
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="BeatSmith", console=False,
          icon=icon if os.path.isfile(icon) else None)
coll = COLLECT(exe, a.binaries, a.datas, name="BeatSmith")
if mac:
    app = BUNDLE(coll, name="BeatSmith.app", icon=icon, bundle_identifier="io.github.paul-lapczynski.beatsmith",
                 version=os.environ.get("BEATSMITH_VERSION", "0.0.1"),
                 info_plist={"CFBundleDisplayName": "BeatSmith", "NSHighResolutionCapable": True,
                             "LSMinimumSystemVersion": "12.0"})
