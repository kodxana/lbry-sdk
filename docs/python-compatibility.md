# Python compatibility audit

Audited October 9, 2026, at SDK revision
`52f707043fdd6bcdeea1f3d937e16e6128476e45` and the Hub revision pinned in
`setup.py`, `929448d64bcbe6c5e476757ec78456beaa85e56a`.

The Hub baseline has since moved to the maintained fork at
`9f871d83c1a8e030148fb754c143998085c93240`, which includes upstream `ebcc6e5`,
the legacy database migration and schema rollback fixes, orderly service
shutdown, session-maintenance task cleanup, and the maintained RocksDB binding
on Linux x86-64 with CPython 3.9. The session manager now passes explicit tasks
to `asyncio.wait()` and finishes their cleanup before closing connections.
The SDK now shares its protobuf 3.20.3 requirement, and the test constraints pin
Hub's additional `rehash==1.0.0` dependency. The findings below describe the
original audit; these changes do not establish support for a newer interpreter.

The pinned Hub's [migration notes](https://github.com/kodxana/lbry-hub-ng/blob/9f871d83c1a8e030148fb754c143998085c93240/docs/testing.md#reorgs-across-a-schema-upgrade)
describe recovery when a reorg crosses a database schema upgrade. On Linux
x86-64 with CPython 3.9, Hub installs the published `lbry-rocksdb-ng` 0.8.3
wheel from GitHub with a SHA-256 pin. It includes the database-close, iterator
and snapshot fixes while retaining RocksDB 6.25.3. The wheel requires glibc
2.31 or newer; Alpine/musl is not supported. Other environments retain Hub's
legacy `lbry-rocksdb==0.8.2` requirement and are not newly validated here.

Use a fresh virtual environment when upgrading an SDK installation with the
`hub` extra. The old and new distributions own the same `rocksdb` files and
must not coexist; an in-place upgrade does not remove the old binding.
Keep wallet and Hub database directories intact when replacing the Python
environment. The SDK without the `hub` extra does not install either binding.

Protobuf 3.18.3 crashes on macOS when importing the legacy claim messages,
consistent with [upstream issue #10691](https://github.com/protocolbuffers/protobuf/issues/10691).
Both projects use 3.20.3 with unchanged generated message definitions. Native CI
runs the schema suite, including the historical claim decoding fixtures, as well
as the configuration and wallet suites.

The Python 3.9 environment in [testing.md](testing.md) remains the tested
comparison baseline. Updating the interpreter alone cannot install the current
requirements on supported Python releases. The `python_requires='>=3.8'`
declaration does not establish compatibility with every later Python version.

## Installation findings

The audit inspected PyPI release metadata for all 63 distinct releases in
`docker/test-constraints.txt` and `docker/build-requirements.txt`. Wheel tags and
`Requires-Python` were checked for CPython 3.9 through 3.14 on x86-64 Windows,
Intel macOS 15, and glibc 2.31 Linux, matching the current CI architectures.
Yanked files were excluded. Compatible `abi3` and generic Python wheels were
included. This was an artifact inventory, not a successful installation of
every dependency combination or a security audit.

In the table, **source** means PyPI offers an eligible source archive but no
matching wheel; it does not mean the package cannot work. **Unavailable** means
neither an eligible source archive nor a matching wheel exists on PyPI for the
specified target. It does not rule out maintaining a separate source build.

| Current pin | Python 3.12 | Python 3.13 / 3.14 | Scope |
| --- | --- | --- | --- |
| [libtorrent 2.0.6](https://pypi.org/pypi/libtorrent/2.0.6/json) | Unavailable | Unavailable | SDK, all three platforms; wheels stop at 3.10, no source archive |
| [lbry-rocksdb 0.8.2](https://pypi.org/pypi/lbry-rocksdb/0.8.2/json) | Unavailable | Unavailable | Hub; CPython wheels stop at 3.9, no source archive or Windows wheel |
| [cffi 1.13.2](https://pypi.org/pypi/cffi/1.13.2/json) | Source; Linux build fails | Source | SDK and Hub, all three platforms |
| [aiohttp 3.7.4](https://pypi.org/pypi/aiohttp/3.7.4/json) | Source; Linux build and import pass | Source | SDK and Hub, all three platforms |
| [coincurve 15.0.0](https://pypi.org/pypi/coincurve/15.0.0/json) | Windows wheel; Linux/macOS source | Same | SDK and Hub; wallet signing and derivation |
| [PyYAML 5.3.1](https://pypi.org/pypi/PyYAML/5.3.1/json) | Source; Linux build passes | Source | SDK, all three platforms |
| [grpcio 1.38.0](https://pypi.org/pypi/grpcio/1.38.0/json), [msgpack 0.6.1](https://pypi.org/pypi/msgpack/0.6.1/json), [ujson 5.4.0](https://pypi.org/pypi/ujson/5.4.0/json) | Source | Source | Hub, all three platforms; builds not tested |
| [pywin32 301](https://pypi.org/pypi/pywin32/301/json) | Unavailable | Unavailable | Windows executable build; wheels stop at 3.9, no source archive |
| [PyInstaller 6.0.0](https://pypi.org/pypi/pyinstaller/6.0.0/json) | Wheel | Excluded by `Requires-Python <3.13` | Executable builds on all three platforms |

Other source-build exposure includes `netifaces==0.11.0`, pulled in by
`aioupnp`. Conversely, `cryptography==3.4.7` has compatible `abi3` wheels across
these interpreter targets. That is an installation observation, not evidence
that its old cryptographic backend is suitable for deployment.

### Build and runtime probes

Source builds used Linux CPython 3.12.15, GCC 12.2, pip 24.0, setuptools 75.8.0,
wheel 0.45.1, and Cython 0.29.37. The container was
`python:3.12-bookworm` at digest
`sha256:5560e9ab8709f459489e5b8aa696eda8a07ef821e14bb122be62d91234bfa98b`.
It had no host mounts or published ports and was removed after each probe.

- CFFI 1.13.2 fails compiling `_cffi_backend.c` with
  `lvalue required as left operand of assignment`. A compiler and Python
  headers were present; this was not a missing-toolchain failure.
- aiohttp 3.7.4 builds a `py3-none-any` wheel and imports successfully with its
  baseline transitive pins. This does not test HTTP behavior or establish that
  its C extensions work.
- PyYAML 5.3.1 builds with the baseline Cython pin and build isolation disabled.
  Configuration parsing behavior was not tested in this probe.
- pip rejects PyInstaller 6.0.0 for a Python 3.13 Windows target because of its
  Python version constraint.

Separate standard-library probes extracted `AsyncioTestCase` and
`TorrentHandle.__init__` from the SDK with `ast`, avoiding SDK dependency imports.
On Linux Python 3.12.3 and Windows Python 3.13.15 and 3.14.7, all three checks
reported the same failures:

| Probe | Result |
| --- | --- |
| Empty async test using `AsyncioTestCase` | `AttributeError: '_Outcome' object has no attribute 'errors'` |
| Passing a coroutine to `asyncio.wait` | `TypeError: Passing coroutines is forbidden, use tasks explicitly.` |
| Constructing `TorrentHandle` with a dummy handle | `TypeError: Event.__init__() got an unexpected keyword argument 'loop'` |

These were isolated compatibility failures, not full SDK runs. The test runner
now uses `IsolatedAsyncioTestCase`, with standard-library regression coverage
on Python 3.9, 3.12, 3.13 and 3.14. Transaction test helpers now schedule their
coroutines explicitly, propagate failures and timeouts, and cancel and drain
unfinished operations. Torrent events are created on the session loop without
the removed `loop=` argument; adding native torrents stays in the executor.
The focused async and torrent tests pass on Windows Python 3.9 and 3.13, using
libtorrent 2.0.6 and 2.0.15 respectively. The SDK dependency pin remains 2.0.6.
Production raw-coroutine waits in the daemon and wallet event controller still
need migration and runtime coverage before full Python 3.13 testing.

## Hub constraints

Installed metadata from the exact pinned Hub commit confirms shared exact pins
for aiohttp, CFFI, coincurve, protobuf, colorama, prometheus-client, pbkdf2,
hachoir, and filetype. Both projects also require `certifi>=2021.10.08`.
Upgrading one of those exact pins in the SDK alone makes a combined installation
conflict with the Hub's requirements. Constraints cannot override that conflict.

`lbry-rocksdb` still lists 0.8.2 as its latest PyPI release on the audit date.
There is no newer published wheel to select for the target interpreters.
The current integration harness imports and starts Hub services in the SDK's
Python process (`lbry/wallet/orchstr8/node.py`). Running the Hub on a separate
Python 3.9 interpreter would require orchestration changes, including tests
that currently inspect Hub state directly. It is not an existing runner option.

## Target and upgrade order

Use **Python 3.13 as the provisional SDK target**, keeping 3.9 only as the
historical regression environment during migration. This is a target for work,
not a new support claim. Python 3.13 has a scheduled security-support lifetime
through October 2029; 3.9 and 3.10 are already end-of-life according to the
[Python release status](https://devguide.python.org/versions/).

[libtorrent 2.0.15](https://pypi.org/pypi/libtorrent/2.0.15/json) provides 3.13
wheels for all three CI platforms, including a macOS 15 minimum on Intel.
Neither that release nor the current 2.1.1 release offers 3.14 wheels or a
source archive on PyPI. Staying on the 2.0 line is a candidate for testing,
not approval to change the pin. Python 3.14 needs a separate solution for this
dependency before it can become the default target. The Hub remains a blocker
for integration tests on either newer interpreter.

Make these changes as separate, reviewed steps:

1. Replace the private unittest runner with `IsolatedAsyncioTestCase`, preserving
   async cleanup, timeout failures, skip/expected-failure reporting, and the
   virtual-clock tests. Prove the runner's behavior with focused regressions
   and rerun the existing Python 3.9 suites before changing dependency pins.
2. Fix removed asyncio APIs, including torrent events and raw-coroutine waits,
   with regressions for cancellation and resource cleanup.
3. Resolve the Hub path: maintain compatible Hub/RocksDB builds and aligned
   shared requirements, or implement a separate-process regtest harness. Do
   not remove integration coverage to make a newer SDK environment pass.
4. Upgrade dependency groups independently: configuration/build tools;
   aiohttp and its networking dependencies; libtorrent; then wallet cryptography
   and protobuf. Each group needs its own compatibility review and test results.
   Generated protobuf code must be reviewed together with its runtime.
   While the same checkout still runs on 3.9, select transitional versions that
   support both interpreters rather than assuming the newest release does.
5. Add required Python 3.13 CI once installation and focused tests work. Gate
   support on all unit and regtest groups, native Windows/macOS wallet tests,
   and executable build checks. Retain the old comparison jobs until parity
   is demonstrated.

For cryptographic changes, require fixed key-derivation and signature vectors,
existing signed-claim decoding/validation, transaction serialization, and
encrypted-wallet save/reload checks. Add missing coverage before replacing a
backend. An import test or successful package resolution cannot establish wallet
compatibility.

## Repeating the installation probes

These commands inspect target artifacts without installing them. Run in a
disposable environment; the pinned probes below are expected to fail:

```sh
python -m pip download --no-deps --only-binary=:all: --python-version 3.12 --platform manylinux_2_24_x86_64 --dest audit-wheels 'lbry-rocksdb==0.8.2'
python -m pip download --no-deps --only-binary=:all: --python-version 3.12 --platform win_amd64 --dest audit-wheels 'libtorrent==2.0.6' 'pywin32==301'
python -m pip download --no-deps --only-binary=:all: --python-version 3.13 --platform win_amd64 --dest audit-wheels 'pyinstaller==6.0.0'
```

Check the linked PyPI JSON `urls` arrays as well: absence of a wheel alone does
not rule out a source archive. A resolver can stop at the first failure and
does not provide a complete inventory of blockers.

To repeat each source-build probe inside the Python 3.12 container above:

```sh
python -m pip install 'pip==24.0' 'setuptools==75.8.0' 'wheel==0.45.1' 'Cython==0.29.37'
python -m pip wheel --no-build-isolation --no-deps --wheel-dir /tmp/wheels 'cffi==1.13.2'
python -m pip wheel --no-build-isolation --no-deps --wheel-dir /tmp/wheels 'aiohttp==3.7.4'
python -m pip wheel --no-build-isolation --no-deps --wheel-dir /tmp/wheels 'PyYAML==5.3.1'
```

Rerun the inventory when selecting actual upgrade versions. PyPI files,
supported platforms, and Python support windows can change after this audit.
