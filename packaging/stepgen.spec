# PyInstaller spec for the stepgen app. Built by build.bat; see BUILD.md.
from PyInstaller.utils.hooks import collect_all

root = SPECPATH + "/.."
datas = [(root + "/patterns.toml", "."), (root + "/profiles", "profiles"),
         (root + "/README.md", "."), (SPECPATH + "/stepgen.png", "."),
         (root + "/stems.py", "."), (root + "/lyrics.py", ".")]      # run by the optional add-ons' own Python
datas += [(root + "/models", "models")]                          # AI assist model
binaries, hidden = [], ["stepgen", "chartstats", "llm_review", "chart_editor", "groove", "layout", "shorten", "verses", "addons", "ai_assist", "stems", "mutagen", "sounddevice"]
for pkg in ("librosa", "soundfile", "lazy_loader", "audioread", "soxr", "sounddevice", "_sounddevice_data", "onnxruntime"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hidden += h
# ffmpeg.exe for .wma/.m4a, if build.bat fetched it
import os
if os.path.isdir(SPECPATH + "/ffmpeg"):
    datas.append((SPECPATH + "/ffmpeg", "ffmpeg"))

a = Analysis([root + "/stepgen_app.py"], pathex=[root], binaries=binaries, datas=datas,
             hiddenimports=hidden, excludes=["tkinter", "matplotlib", "IPython",
                      "torch", "torchaudio", "demucs"])   # vocal separation is a separate download
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="stepgen", console=False,
          icon=SPECPATH + "/stepgen.ico" if os.path.isfile(SPECPATH + "/stepgen.ico") else None)
coll = COLLECT(exe, a.binaries, a.datas, name="stepgen")
