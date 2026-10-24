#!/bin/sh
# Builds the BeatSmith app for macOS:
#   dist/BeatSmith.app               the app
#   dist/BeatSmith-<version>-mac.dmg  a disk image to share
# Needs Python 3.12 (python3.12 on PATH, or set PYTHON). See BUILD.md.
set -e
cd "$(dirname "$0")"
: "${BEATSMITH_VERSION:=0.0.1}"
export BEATSMITH_VERSION

[ -d .venv-mac ] || "${PYTHON:-python3.12}" -m venv .venv-mac
. .venv-mac/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -r ../requirements.txt -r ../requirements-app.txt pyinstaller

pyinstaller --noconfirm --clean --distpath dist --workpath build beatsmith.spec

rm -rf dmg && mkdir dmg
cp -R dist/BeatSmith.app dmg/
ln -s /Applications dmg/Applications
hdiutil create -volname "BeatSmith $BEATSMITH_VERSION" -srcfolder dmg -ov -format UDZO "dist/BeatSmith-$BEATSMITH_VERSION-mac.dmg"
rm -rf dmg
echo "Done. Disk image: $(pwd)/dist/BeatSmith-$BEATSMITH_VERSION-mac.dmg"
