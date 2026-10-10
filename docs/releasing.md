# Preparing a community release

The package is still named `lbry`; the executable is `lbrynet`. Publish community
artifacts only under `kodxana/lbry-sdk-ng`. The old release helper targeted the
upstream repository and discarded release-candidate suffixes; it has been
retired. This repository does not publish to PyPI automatically.

1. Review and merge the candidate changes, including the matching Hub revision.
   Keep the package version in `lbry/__init__.py` and the release notes together.
   A release-candidate version such as `0.114.0rc1` must retain its suffix.
2. Run the complete `ci` workflow on that commit. Require every job: generated
   schemas, the async runner, Linux lint/unit/all six regtest groups, native
   Windows/macOS configuration/schema/wallet suites, and all three executable
   builds. Check the matching Hub's database and resolve/session workflows too.
3. Download `lbrynet-linux`, `lbrynet-windows` and `lbrynet-macos` from that same
   workflow run before its 14-day retention expires. Keep their run URL and
   commit SHA with the release record. Do not mix artifacts from different runs.
4. Unpack and name the assets with their version and architecture. Preserve the
   executable bit on Linux/macOS. Generate `SHA256SUMS` from the final files, and
   retain `ci-*` test reports and package inventories with the validation record.
5. Create a GitHub draft release in this community repository, targeting the
   validated commit. Use tag `v` followed by the exact package version, attach
   the three executables and checksum file, and copy the reviewed release notes.
   Mark an `rc` version as a prerelease. Review the draft before publication.

Passing isolated tests establishes regression coverage, not a mainnet-scale
deployment rehearsal. Release notes must state the tested platforms, dependency
requirements, known skips and any validation still outstanding. Before using a
candidate with existing funds, preserve a separate wallet backup and keep the
previous environment available for rollback. Never attach wallets or private
configuration to CI or release artifacts.
