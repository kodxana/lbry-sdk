# Preparing a community release

The package is still named `lbry`; the executable is `lbrynet`. Publish community
artifacts only under `kodxana/lbry-sdk-ng`. The old release helper targeted the
upstream repository and discarded release-candidate suffixes; it has been
retired. This repository does not publish to PyPI automatically.

## Release candidates

The `ci` workflow builds Windows x64, Linux x86-64 and Intel macOS binaries on
pull requests, master pushes, version tags and manual runs. It packages them
only after the entire test matrix succeeds. Each successful run retains a
`release-candidate` artifact for 90 days, containing versioned executables,
`SHA256SUMS`, the source/run record, release notes and an archive of CI logs and
dependency inventories. Individual build/test artifacts expire after 14 days.

Public prereleases are created automatically when a maintainer pushes a tag
such as `v0.114.0rc2`. The version must match `lbry/__init__.py`, and that commit
must already be merged into master. Creating the tag authorizes publication
after its checks pass. Pull requests, branch builds, other forks and stable
version tags cannot publish through this job.

1. Update `lbry/__init__.py` and add `docs/releases/<version>.md` in the same
   reviewed change. State the supported platforms, known skips and validation
   limits. Use a new candidate number; never move or reuse a published tag.
2. Merge the SDK changes and the pinned Hub dependency. The Hub pin must be a
   full commit SHA with successful Tests and CodeQL workflows. Its source must
   be merged into the community Hub's master branch.
3. Review the successful master build and its `release-candidate` artifact.
   Tag that commit with `v` followed by its exact version and push the tag.
4. The tag run repeats all checks: generated schemas, release tooling, async
   runner compatibility, Linux lint/unit/all six regtest groups, native
   Windows/macOS configuration/schema/wallet suites, and executable builds.
5. The publishing job downloads the packaged binaries from that same run,
   checks the tag, source revision, file hashes and pinned Hub checks, then
   creates a draft. It verifies every uploaded asset against GitHub's SHA-256
   digest before publishing it as a prerelease, without making it the latest
   stable release.

Users download the binaries from the repository's Releases page without needing
an Actions login. Python is included in each executable. Linux/macOS downloads
need `chmod +x`; the Linux binary requires glibc 2.36+, and the macOS binary
targets Intel macOS 15+. The files are unsigned and macOS is not notarized.

If publication stops during upload, rerun only the failed publishing job. It
can resume a matching draft using the original bundle, and refuses changed or
unexpected assets. It never replaces a published release. Rebuilding the
candidate can change artifact hashes; use a new version/tag when new binaries
are needed. A manual workflow run selected on an unpublished `v...rcN` tag has
the same publication behavior as a tag push.

The original `v0.114.0rc1` predates this automation and was published manually.
This workflow does not republish it. Stable releases require separate review
and publication; they are not automatically promoted from an `rc` tag.

## Local checks

The release tooling has no SDK dependencies. Run its tests with:

```sh
python3 -m unittest discover -v -s scripts/tests
```

Packaging runs in ordinary pull-request CI too, so the release bundle can be
reviewed before any tag is created. Only the publishing job receives repository
write permission, and its token is provided only to the publication step.

Passing isolated tests establishes regression coverage, not a mainnet-scale
deployment rehearsal. Release notes must state the tested platforms, dependency
requirements, known skips and any validation still outstanding. Before using a
candidate with existing funds, preserve a separate wallet backup and keep the
previous environment available for rollback. Never attach wallets or private
configuration to CI or release artifacts.
