# Maintaining the archive fork

The `archive` branch contains our changes; `main` is the original upstream snapshot.
The original baseline is upstream 7.2.10 at `2ad3508`. The current upstream version
is recorded in the component manifest; the branch history records subsequent merges.
A GitHub Actions job merges upstream `main` daily at 03:17 UTC, runs the fork tests,
compiles the component, validates JSON and support metadata, then pushes to `archive`.
It also supports manual dispatch. Conflicts, failed checks or concurrent branch changes
stop the job without publishing. Check the Actions page for failed runs.

The job uses standard public-repository runners and no AI model or paid API. It never
contacts Home Assistant. Automated checks do not establish runtime compatibility;
HA updates remain an explicit installation action. GitHub schedules can be delayed
or disabled after prolonged repository inactivity.

## Installation and updates

This fork uses the same `tapo_control` integration domain. It replaces the upstream
component; do not install both simultaneously or remove your existing camera entries.

1. Back up your current component, Home Assistant configuration, and recordings.
2. Download or clone the `archive` branch, selecting a specific commit.
3. Stop Home Assistant Core. Replace the `custom_components/tapo_control` directory
   with the directory from that commit. Keep camera configuration and archive data.
4. Run Home Assistant's configuration check, start Core, and verify the cameras,
   media browser, playback, and synchronization.

The manifest retains the baseline upstream version until we publish a distinct fork
release. Do not infer the installed fork commit from that version number. Record the
Git commit used for deployment. Do not apply upstream HACS updates over this fork.

For HACS, add `https://github.com/kopiro/HomeAssistant-Tapo-Control` as a custom
Integration repository and select the default `archive` branch. Remove the upstream
repository from HACS tracking before downloading this fork; keep the HA camera entries
and archive data. Both repositories write the same integration directory and must not
be managed as two installed components. Until releases are published, updates are
commit-based. Do not use inherited upstream version tags: they omit the fork patches.

## Behavior and limits

- Flat storage is the default. Selecting Year/month/day migrates completed video and
  thumbnail files before camera tasks start. Switching back reverses that migration.
- A blank synchronization-hours setting retains downloaded recordings after camera
  rotation. This can grow indefinitely; monitor available storage. Numeric settings
  preserve bounded-window cleanup. Recordings already overwritten on the SD cannot
  be recovered.
- Historical corrections affect directory dates only. File names, video contents,
  embedded timestamps and media-browser labels are not rewritten.
- Failed archive scans, synchronization passes and clock updates wait five minutes
  before retrying, then double the delay up to one hour. The known ONVIF `error time`
  fault retains a 24-hour delay. Successful operations reset their failure count.
  A failed download ends the current pass; the synchronization sensor exposes failure
  counts and remaining sync/clock retry delays. These delays reset on integration reload.
  This limits repeated requests to an unhealthy camera; it does not establish or fix
  the cause of a camera's video service freezing. SD-card recording is unchanged.
- This is experimental. Hub and battery devices have not been tested live with these
  changes. Initial validation used Home Assistant 2026.10.2. Camera/session timeouts
  were observed during restart scans; this fork does not claim to solve them.

## Optional historical correction

Leave `.recording-date-correction.json` absent from the camera's archive root for
normal recording dates. Advanced users can provide this per-camera file:

```json
{
  "version": 1,
  "offset_seconds": 86400,
  "raw_before": 1704067200
}
```

This illustrative configuration adds one day only to raw start timestamps before
2024-01-01 UTC. Choose your own measured offset and cutoff; a constant shift cannot
reconstruct variable clock drift. Never commit real camera-specific settings or
credentials to this repository. Restart Core after editing the file: settings are
cached until restart and migration then updates the directory placement.

To reverse a correction, set its offset to zero and restart Core with this fork
still installed. Verify migration before removing the metadata or patched component.

## Reviewing an upstream update or resolving a failed scheduled merge

From a clean clone of this fork:

```sh
git remote add upstream https://github.com/JurajNyiri/HomeAssistant-Tapo-Control.git
git fetch upstream --tags
git switch archive
# Replace UPSTREAM_TAG with the exact release selected for review.
git merge UPSTREAM_TAG
```

Do not automatically select the newest commit or resolve conflicts by discarding our
changes. Review layout lookup, startup/unload ordering, the downloader, media cleanup,
configuration schema, and dependency changes. If the merge conflicts, resolve it
explicitly or abort it; do not deploy a partial merge.

Run `python3 -B -m unittest discover -s tests -v` and compile the component. Then
validate a candidate on Home Assistant: check both layouts, migration and rollback,
media browsing/playback, an actual new download, and retention behavior. Preserve a
rollback copy and compare file counts/content before and after migration. Only then
publish a clearly versioned fork release or deploy the candidate commit. Document the upstream tag,
patch commits, dependencies, observed results, and untested scenarios in release notes.
A clean Git merge alone is not compatibility evidence.

## Returning to upstream

While this fork is still installed, reverse historical corrections and select Flat
storage. Verify migration and independently back up retained recordings before
installing upstream: upstream Media Sync may delete recordings no longer on the SD.
Restore the saved component/configuration if an upgrade fails. Do not overwrite
concurrent configuration changes with a blanket restore.

## Contribution and provenance

Keep layout, retention and historical correction changes separate where practical.
Retain upstream attribution and license notices. Disclose AI assistance and distinguish
agent-run checks from human testing; do not claim review or runtime checks that did
not occur. Use this fork's issue tracker for archive behavior. Changes intended for
upstream should be proposed separately against upstream's rules and scope.
