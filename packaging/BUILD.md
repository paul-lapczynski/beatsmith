# Building the BeatSmith installer (Windows)

Double-click `packaging\build.bat`. That's all.

It installs what it needs to build, if it isn't there already: Python 3.12,
the .NET 8 SDK and the WiX 5 toolset (all through winget, so Windows may ask
you to allow them). Then it makes a private Python environment in
`packaging\.venv`, fetches ffmpeg, bundles everything with PyInstaller and
builds:

- `packaging\dist\BeatSmith-0.0.1.msi`: the installer to share
- `packaging\dist\BeatSmith\BeatSmith.exe`: the app, runnable without installing
- `packaging\dist\BeatSmith-setup-0.0.1.exe`: an .exe installer as well, only
  if Inno Setup 6 happens to be installed

**People who install the MSI need nothing else.** Python, librosa, Qt and
ffmpeg are all inside it. It installs to Program Files with a Start menu and
desktop shortcut, shows up in Apps & features for uninstalling, and
installing a newer version replaces the old one.

Use the same installer type when upgrading. The MSI cannot upgrade a copy
installed by setup.exe; it blocks that combination and asks you to remove
the setup.exe copy first. If both appear in Settings > Apps, uninstall both
BeatSmith entries, then install one current copy. Songs, settings and add-ons
are kept. Overlapping installers can leave incompatible Python files in the
same application folder.

Each build starts the frozen app's command-line entry point before making
installers. Windows CI also checks that the compiled MSI blocks existing
setup.exe registrations, then installs the MSI into a temporary location and
checks startup there. These checks do not run the app's normal settings flow.

Set `BEATSMITH_VERSION=0.0.2` before running the build to change the version
number (an MSI only upgrades when the number goes up). Otherwise the build reads
the root `version.txt`. Release tags must agree with that file. See
[RELEASING.md](RELEASING.md) for version PRs and release automation.

The installer isn't code-signed, so Windows SmartScreen shows "unknown
publisher" the first time. Click "More info", then "Run anyway".

## Vocal separation is not bundled

Demucs and PyTorch (about 1 GB) are deliberately left out of the installer
(`excludes` in beatsmith.spec). The app downloads them on request into
`%LOCALAPPDATA%\BeatSmith\addons\stems` with a private embeddable Python, and
runs `stems.py` (shipped as a plain data file) with it. Uninstalling the app
leaves that folder; delete it by hand to remove the add-on.

## macOS

On a Mac with Python 3.12, run `sh packaging/build-mac.sh`. It makes
`packaging/dist/BeatSmith.app` and `packaging/dist/BeatSmith-<version>-mac.dmg`
(Apple Silicon). GitHub builds the same disk image for every release.

The app isn't signed with an Apple Developer ID, so the first time it's
opened macOS blocks it: open System Settings > Privacy & Security and click
"Open Anyway" next to BeatSmith. Vocal separation and AI verse detection
download as ready-made packs on Apple Silicon Macs. ffmpeg isn't bundled.
