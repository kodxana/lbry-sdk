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
```

The default is `smoke`: create a temporary regtest chain, mine test funds, and
send transactions between accounts. It does not sync mainnet or use real funds.
The unit and wallet commands do not start Elasticsearch.

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
