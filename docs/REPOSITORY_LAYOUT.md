# Repository layout

[Home](../README.md) · [Cleanup plan](REPOSITORY_PLAN.md)

This organization keeps app code, optional workers, developer tools, tests
and documentation separate. The charting algorithms and user-data locations
are unchanged.

| Folder or file | Purpose |
|---|---|
| `src/beatsmith/` | Desktop app, editor, generator, audio/chart helpers and integrations |
| `src/beatsmith/resources.py` | Source/frozen resource lookup and stable legacy source-data root |
| `workers/` | Plain Python separation and verse-detection workers, also shipped as data for the add-on Python |
| `tools/` | Chart statistics and the unfinished LLM review command |
| `tests/unit/` | Version, release sequencing, tempo, form controls and repository compatibility checks |
| `tests/installers/` | MSI/EXE tests and add-on fixtures; disposable GitHub runners only |
| `benchmarks/dials/` | Dial-test scripts and historical measurements |
| `benchmarks/reviews/` | Historical review notes |
| `docs/` | App/CLI/control guides, screenshots and the Pages site |
| `packaging/` | Build scripts, installer sources, resource artwork and frozen-app checks |
| `models/`, `profiles/`, `patterns.toml` | Existing resource locations, deliberately retained |
| `version.txt` and release configuration | Existing release-automation contracts, retained at root |
| Root `.py` entry points | Small compatibility launchers for existing documented commands |

## Existing commands still work

```sh
python beatsmith_app.py
python stepgen.py "My Song.mp3" --out songs/
python chart_editor.py "songs/My Song/My Song.sm"
python chartstats.py "songs/My Song/My Song.sm"
python llm_review.py "songs/My Song/My Song.sm" --prompt-only
python addons.py status
python accel.py
```

`run_app.bat` stays at root. The root launchers select the canonical modules;
they are not duplicate implementations. The frozen executable's child-process
dispatch is preserved. Root worker launchers also support isolated add-on
Python; frozen bundles ship the actual plain worker scripts and acceleration
helper so they do not depend on importing the app's compiled Python modules.

## Checks

```sh
python -m unittest discover -s tests -p "test_*.py"
python docs/capture_screenshots.py
python benchmarks/dials/dialtest.py --help
```

Both build scripts run the tests and frozen startup/generation checks.
The full frozen check uses temporary synthetic audio, runs the bundled
placement model, constructs the GUI/editor with isolated preferences and
checks shipped worker startup. Windows CI also exercises real MSI and EXE
installation, upgrades and uninstall/add-on cleanup.

The internal `--check-gui` entry point is a test hook. It uses temporary
settings, no user's library, no downloads and no audio playback.

## What did not move

User songs, exported charts, settings, cached stems and installed add-ons are
outside this reorganization. Source-run `song-data/` remains at the repository
root; installed app data keeps its existing location. An ignored local folder
is not disposable just because it is absent from Git.

Models, profiles, default patterns, installer build entry points and version
files stay where earlier builds and integrations expect them. Consolidating
those resources is an optional later stage, not required to use this layout.
No feature from the rejected lead-instrument experiment is included.
