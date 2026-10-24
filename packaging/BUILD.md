# Building the stepgen installer (Windows)

Double-click `packaging\build.bat`. That's all.

It installs what it needs to build, if it isn't there already: Python 3.12,
the .NET 8 SDK and the WiX 5 toolset (all through winget, so Windows may ask
you to allow them). Then it makes a private Python environment in
`packaging\.venv`, fetches ffmpeg, bundles everything with PyInstaller and
builds:

- `packaging\dist\stepgen-0.0.1.msi`: the installer to share
- `packaging\dist\stepgen\stepgen.exe`: the app, runnable without installing
- `packaging\dist\stepgen-setup-0.0.1.exe`: an .exe installer as well, only
  if Inno Setup 6 happens to be installed

**People who install the MSI need nothing else.** Python, librosa, Qt and
ffmpeg are all inside it. It installs to Program Files with a Start menu and
desktop shortcut, shows up in Apps & features for uninstalling, and
installing a newer version replaces the old one.

Set `STEPGEN_VERSION=0.0.2` before running the build to change the version
number (an MSI only upgrades when the number goes up). It defaults to 0.0.1;
releases from GitHub take the number from the tag (`v0.0.2` makes 0.0.2).

The installer isn't code-signed, so Windows SmartScreen shows "unknown
publisher" the first time. Click "More info", then "Run anyway".

## Vocal separation is not bundled

Demucs and PyTorch (about 1 GB) are deliberately left out of the installer
(`excludes` in stepgen.spec). The app downloads them on request into
`%LOCALAPPDATA%\stepgen\addons\stems` with a private embeddable Python, and
runs `stems.py` (shipped as a plain data file) with it. Uninstalling the app
leaves that folder; delete it by hand to remove the add-on.
