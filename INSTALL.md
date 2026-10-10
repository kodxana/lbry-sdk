# Installing LBRY SDK NG

This is the community-maintained fork. Its package remains `lbry` and its
command remains `lbrynet`. Historical LBRY Inc. binaries do not include these
changes.

## Requirements

Use **CPython 3.13, 64-bit**. Python 3.14 is not supported by the selected
libtorrent wheels. CI targets Linux x86-64, Windows x64 and Intel macOS 15.
Other architectures are not covered by these instructions.

Some dependencies build from source. Linux needs a C compiler and the headers
for the selected Python installation. Windows needs Microsoft C++ Build Tools;
macOS needs Xcode Command Line Tools. Install FFmpeg if you use video analysis
or transcoding. A system protobuf compiler is not needed to run the SDK.

Use a fresh virtual environment when upgrading. Keep existing wallet and data
directories intact. If you installed the `hub` extra, the old `lbry-rocksdb` and
new `lbry-rocksdb-ng` packages must not share an environment: they install the
same module files.

## Install from source

Clone the community repository:

```sh
git clone https://github.com/kodxana/lbry-sdk-ng.git
cd lbry-sdk-ng
```

On Linux or macOS:

```sh
python3.13 -m venv lbry-venv
source lbry-venv/bin/activate
```

On Windows, in PowerShell:

```powershell
py -3.13 -m venv lbry-venv
.\lbry-venv\Scripts\Activate.ps1
```

Install and verify the environment:

```sh
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip check
lbrynet --version
```

The editable installation uses source changes directly; it does not need to
be reinstalled for each Python edit. Run `deactivate` to leave the environment.

## Development and testing

Install unit-test dependencies with `python -m pip install -e '.[test]'`.
Use the [Docker test runner](docs/testing.md) for full Linux unit tests and
regtests. It supplies the matching Hub, isolated Elasticsearch, and checksum-
verified blockchain test binaries. Tests use temporary data and no real funds;
you do not need a mainnet node on your computer.

The optional `hub` extra is for Linux x86-64 with glibc 2.35 or newer. It installs
a SHA-256-pinned RocksDB wheel from the community GitHub release. Alpine/musl
is not supported. Normal SDK installations do not need this extra.

## Run the SDK

```sh
lbrynet start
```

This starts the SDK's normal wallet and network services. For isolated testing,
use the test runner instead. See the [README](README.md) for configuration and
API documentation, and the [compatibility notes](docs/python-compatibility.md)
for the upgrade's validation status.
