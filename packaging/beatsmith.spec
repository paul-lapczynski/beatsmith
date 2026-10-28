# PyInstaller spec for the BeatSmith app. Built by build.bat on Windows and
# build-mac.sh on macOS; see BUILD.md.
from PyInstaller.utils.hooks import collect_all

root = SPECPATH + "/.."
datas = [(root + "/patterns.toml", "."), (root + "/profiles", "profiles"),
         (root + "/README.md", "."), (SPECPATH + "/beatsmith.png", "."),
         (root + "/workers/stems.py", "."), (root + "/workers/lyrics.py", "."),     # run by the optional add-ons' own Python
         (root + "/src/beatsmith/accel.py", ".")]
datas += [(root + "/models", "models")]                          # AI assist model
# the app's version, for what it tells web services about itself (artwork.py's User-Agent)
import os
import runpy
version = runpy.run_path(SPECPATH + "/version.py")["build_version"]()
with open(SPECPATH + "/version.txt", "w") as f:
    f.write(version)
datas += [(SPECPATH + "/version.txt", ".")]
binaries, hidden = [], ['beatsmith.accel', 'beatsmith.addons', 'beatsmith.ai_assist', 'beatsmith.artwork', 'beatsmith.beatsmith_app', 'beatsmith.chart_editor', 'beatsmith.form_controls', 'beatsmith.groove', 'beatsmith.layout', 'beatsmith.resources', 'beatsmith.smoke_gui', 'beatsmith.shorten', 'beatsmith.stepgen', 'beatsmith.tempo', 'beatsmith.verses', 'tools.chartstats', 'tools.llm_review', 'workers.stems', 'workers.lyrics', 'mutagen', 'sounddevice']
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

a = Analysis([root + "/beatsmith_app.py"], pathex=[root, root + "/src"], binaries=binaries, datas=datas,
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
                 version=version,
                 info_plist={"CFBundleDisplayName": "BeatSmith", "NSHighResolutionCapable": True,
                             "LSMinimumSystemVersion": "12.0"})
