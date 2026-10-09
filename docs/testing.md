# Local test baseline

The Docker runner provides the historical Python 3.9 environment while work on
newer Python versions is underway. It tests the current checkout, including
uncommitted source changes. Python 3.9 and several dependencies are obsolete;
this image is a test environment, not a deployment image.

## Requirements

- Docker with Linux containers and BuildKit, on Linux or through WSL2 on Windows.
- An x86-64 machine; the regtest node binaries are Linux amd64 builds.
- Allow roughly 6 GiB of RAM for integration tests (4 GiB for the SDK and
  2 GiB for Elasticsearch), plus the host OS and space for build layers.
- Internet access for the first build and image pulls. Subsequent builds reuse
  Docker's cache.

Run these commands from the repository root in a Linux/WSL shell:

```sh
sh scripts/test.sh smoke
sh scripts/test.sh unit
sh scripts/test.sh wallet
sh scripts/test.sh integration
sh scripts/test.sh lint
```

The default is `smoke`: create a temporary regtest chain, mine test funds, and
send transactions between accounts. It does not sync mainnet or use real funds.
The unit and wallet commands do not start Elasticsearch.

To retain logs, installed package versions, and a coverage XML report after a
test run, set an output directory. Files are copied out after the container
stops; the directory is not mounted into the container.

```sh
TEST_OUTPUT_DIR=ci-results sh scripts/test.sh unit
TEST_OUTPUT_DIR=ci-results sh scripts/test.sh integration transactions
```

Use a different directory for each suite when retaining multiple reports. Logs
and package versions are also exported on test failures and timeouts. A forced
timeout can prevent Python from finishing its coverage report.

The image also contains the pinned binary build tools. To build the Linux
executable, check `--version`, and retain the result:

```sh
TEST_OUTPUT_DIR=ci-results sh scripts/test.sh build
```

Run one integration group or a specific test with:

```sh
sh scripts/test.sh integration transactions
sh scripts/test.sh test tests.unit.wallet.test_wallet.TestWalletCreation.test_read_write
```

Integration groups are `blockchain`, `claims`, `datanetwork`, `other`,
`takeovers`, and `transactions`, matching the existing tox environments.
The `test` command starts Elasticsearch so it can also run integration tests.
Each invocation has a one-hour test timeout; override it in seconds if needed:

```sh
TEST_TIMEOUT=600 sh scripts/test.sh smoke
```

From PowerShell, pass the command through WSL using your checkout's Linux path:

```powershell
wsl -d Ubuntu --exec sh -c 'cd /mnt/f/save_lbry/lbry-sdk && sh scripts/test.sh smoke'
```

## Isolation and dependencies

The build installs the SDK's existing requirements, pinned transitive versions
from `docker/test-constraints.txt`, the Hub revision in `setup.py`, FFmpeg,
and the regtest executables. The sample video comes from an immutable Android
CTS revision and is checked against the SHA-384 already expected by the claim
tests. It can also be prepared for a native test run with:

```sh
python -m tests.integration.claims.fixtures
```

Python and Elasticsearch images are pinned by digest. Debian packages come from
the August 1, 2025 snapshot, and the regtest archives have SHA-256 checks. These
pins capture a historical test environment; Python source distributions are
still built locally, so byte-for-byte image reproducibility is not guaranteed.
Installed Python versions are recorded in
`/opt/baseline-packages.txt` inside the image.

Tests run as an ordinary user, with no host directories mounted and no ports
published. Unit tests get a network namespace with loopback only. Integration
tests share Elasticsearch's loopback-only namespace so the SDK, Hub, and local
regtest processes can communicate. There is no external network route during
tests. Wallets, chains, and generated media live in temporary containers; the
runner removes its containers on success, failure, or interruption. Docker's
images and build cache remain for later runs.

The runner returns unittest's exit status, or 124 when its timeout expires.
A killed process can return a different nonzero status. A passing smoke test
only verifies basic regtest wiring; run the relevant suites before changing
wallet behavior.

## Troubleshooting

An Elasticsearch startup failure prints its container log. On Linux or WSL,
check Docker's memory allocation and the host's `vm.max_map_count`; Elasticsearch
7.12 requires at least 262144 for configurations that use memory-mapped indices.
The runner does not change host sysctl settings.

If an interrupted native fixture download left an invalid video, remove
`tests/integration/claims/files/ForBiggerEscapes.mp4` and run the fixture command
again. A checksum mismatch fails explicitly rather than changing expected test
results.

## Stream restart tests

The data-network suite tests interrupted and completed file saves separately.
The interrupted-save test pauses the second blob read until stopping the file
manager cancels it, verifies that the partial file is removed, then checks the
complete contents after restart. The completed-save test verifies the saved
path and contents after restart without waiting for a new write-start event.

Save, stop, start, and write-event waits in these two tests have ten-second
limits. Timeouts and cancellation propagate as test errors. A completed file
loaded from the database does not need to emit another write-start event.

## Historical SQLite diagnostic

The wallet unit suite checks batch writes through `AIOSQLite`, including
concurrent generator inputs, supported parameter types, rollback after binding
and constraint errors, and successful writes after an error. The batch-write
fixture closes its database and executors during cleanup.

The old `TestSQLiteRace` case exercised raw CPython SQLite and required a
historical binding error to occur. It could fail or time out when that error did
not occur. The reproducer is now a standalone, standard-library-only diagnostic:

```sh
python scripts/diagnose_sqlite_misuse.py --attempts 120000 --timeout 120
python scripts/diagnose_sqlite_misuse.py --attempts 120000 --timeout 120 --fetchall
```

The second command drains each cursor on the worker thread, matching the SDK's
existing workaround. Both commands print the Python and SQLite versions and
whether the historical error was observed. Reaching either limit without
reproducing it is inconclusive, not a failing SDK test. These diagnostic outcomes
exit successfully; unexpected exceptions still fail. The diagnostic is not part
of unittest discovery or CI, and uses only a temporary in-memory database.

## GitHub Actions

The `ci` workflow runs on pull requests, pushes to `master`, version tags, and
manual dispatch. Linux lint, unit tests, and all six integration groups use the
same container runner described above on Ubuntu 24.04. Windows 2022 and Intel
macOS 15 run configuration tests and the full wallet unit suite natively using
managed Python 3.9.25. The full wallet suite also runs in the Linux unit job.

The native jobs build executables and check `--version`. A Linux build runs
after the test jobs pass. Download `ci-*` artifacts for logs, package versions,
and per-suite coverage XML; `lbrynet-*` artifacts contain the binaries. These
artifacts expire after 14 days. Coveralls credentials are not needed.

The workflow has read-only repository permissions and does not publish releases.
Version tags run validation and produce artifacts only. The legacy Slack
notification is restricted to the upstream repository. Release publishing and
release validation are separate maintenance work; CI binaries still use the
historical Python and dependency baseline.
