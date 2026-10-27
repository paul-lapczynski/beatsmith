# Versions and releases

Release Please prepares a version pull request with a new `version.txt` and
changelog. Paul reviews its version and notes, then squash-merges it. After
that commit's Windows, Mac and add-on builds pass, automation creates a draft
release and tag. The existing Release workflow builds the tagged commit,
uploads the installers and all four add-on packs, then publishes the draft.
A failed build leaves the release unpublished.

## Setup before enabling

Create a repository secret named `RELEASE_PLEASE_TOKEN` using a dedicated bot
or fine-grained token limited to this repository. It needs Contents, Issues
and Pull requests read/write. GitHub may require organization approval.
The token must be allowed to create PRs by the repository's Actions policy.
Do not put a token in a file or PR.

The normal `GITHUB_TOKEN` cannot replace this token: GitHub suppresses the
PR and tag events it creates, so installer builds would not start. The
workflow deliberately fails with a setup message if the secret is absent.
The build and upload workflow uses its normal repository token.

## Everyday changes

Use a clear squash-merge title: `fix: ...` for a patch, `feat: ...` for a
minor version, or `feat!: ...` for a breaking change. Other titles do not
request a release. Review the generated version PR before merging; it is
the approval to release. Never enable automatic merging of that PR.

Release Please uses its `simple` strategy for this Python application.
Changesets also supports a version PR, but would add a Node package and a
custom publish command only for version management. Release Please keeps
the version in a plain file and reads the squash-merge titles.

The initial version is the existing 1.0.0 release. The first feature release
should be 1.1.0 and include ready-made add-on packs. Check those notes in
the generated PR; older commits without `feat:` titles may need a manual
changelog entry. The manifest tracks the last proposed version and is
maintained by Release Please.

## Checks and recovery

`python packaging/version.py` prints the version used by both installers and
the bundled app. Tag builds reject a mismatch with `version.txt`. Test and
local builds use the file too; a local `BEATSMITH_VERSION` override is allowed.

Only a successful Release build of the current `main` commit can run release
preparation. If main changed while it built, wait for the newer build. A
manual run of Prepare release checks the same condition.

If a tag build fails, fix the cause and rerun the failed jobs. The draft
retains its changelog and is published only after one MSI, one EXE, one DMG
and both add-ons for Windows and Mac are present. Rerunning a failed upload
replaces draft assets. An already-published release is not overwritten.

Manual releases still work: update `version.txt` in a reviewed PR, wait for
green builds, then tag that commit. The Release workflow stages its files
in a draft before publishing. Do not create another release for an existing
published tag.

Sources: [Release Please](https://github.com/googleapis/release-please-action),
[Changesets](https://github.com/changesets/action).
