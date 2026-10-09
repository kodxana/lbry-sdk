# Maintenance baseline: October 9, 2026

Starting revision: `e7666f489418e96b6d2104974e93915b539235c5` (0.113.0).
This baseline adds the runner described in [testing.md](testing.md), repairs
the Windows temporary-file fixture, and restores the original video fixture
from Android CTS. It does not change SDK or wallet behavior.

## Environment

Linux tests run under Docker on WSL2, using Python 3.9.23, the constraints in
`docker/test-constraints.txt`, Elasticsearch 7.12.1, and the Hub revision already
pinned by `setup.py`. The runner uses an unprivileged account. Runtime networking
is limited to loopback, with temporary regtest wallets and no mainnet connection.
Each integration group runs in fresh containers; two groups ran concurrently
for this baseline.

The native Windows wallet run uses Python 3.9.25 and the existing SDK test
requirements. Its result is separate from the Linux baseline.

## Results

| Suite | Tests run | Result |
| --- | ---: | --- |
| Linux unit | 349 | 347 passed; 2 existing platform skips |
| Integration: blockchain | 43 | Passed |
| Integration: claims | 56 | 54 passed; 2 existing skips |
| Integration: datanetwork | 46 | Passed |
| Integration: other | 17 | Passed |
| Integration: takeovers | 38 | Passed |
| Integration: transactions | 8 | Passed |
| Windows wallet unit | 128 | 127 passed; 1 error described below |
| Regtest smoke | 1 | Passed |

Across the six integration groups, 206 tests passed and two were skipped.
All test containers were removed after the runs.

The Linux skips are `test_mac_defaults` and `test_windows_defaults`, which are
specific to other operating systems. The initial root-container run failed
`test_when_non_writable_dir_exists_then_raise`; running as an ordinary user
restored the intended permission check without changing its assertions.

The existing claim-test skips are `test_disconnect_on_memory_error` and
`test_no_source_and_valid_channel_signature_and_media_type`. They remain
unchanged and need review before they can count toward coverage.

On Windows, `TestWalletCreation.test_read_write` originally failed because
`NamedTemporaryFile` was still open when the wallet imported it. Closing a
regular file inside `TemporaryDirectory` before import fixes that fixture while
preserving its save/reload assertions.

`TestSQLiteRace.test_unhandled_sqlite_misuse` still times out with
`asyncio.CancelledError` on Windows. It tries to reproduce an old CPython SQLite
error and fails if that error does not occur. It passes in the pinned Linux
environment. This is not evidence of a wallet database failure or of correctness;
the test needs separate review as part of modernizing the harness. It has not
been skipped or weakened to make this baseline green.

Runner checks also verified invalid argument rejection, exit code 1 for a
deliberately missing test, exit code 124 for a forced timeout, and container
cleanup after those runs. The video download was checked against its existing
2,299,653-byte size and SHA-384; cached offline reuse and rejection of corrupted
bytes were checked as well.

## Limits and follow-up

These results establish a comparison point for maintenance, not a security
audit. They do not validate production wallet backups, mainnet behavior, current
Python releases, or packaged binaries. Existing async resource and deprecation
warnings remain visible in the test output.

The streaming test
`test_file_save_stop_before_finished_streaming_only_wait_for_start` suppresses
`CancelledError` while waiting for a write-start event. Its passing result does
not establish that the wait completed normally; cancellation handling belongs
in the harness review as well.

Next steps are to restore the fork's CI on supported runners, review the test
harness (including the SQLite reproducer and legacy skip decorators), and add
targeted regressions before changing wallet persistence, reorg handling, or
dependencies.
