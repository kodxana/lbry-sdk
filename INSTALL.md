# Installing LBRY SDK NG

These instructions use the community fork. Historical LBRY Inc. binaries do not contain its fixes. See the [README](README.md) for project and release links.

These instructions are for installing LBRY from source, which is recommended if you are interested in doing development work or LBRY is not available on your operating system (godspeed, TempleOS users).

## Prerequisites

Python 3.9 is the current tested baseline. Python 3.9 and several pinned dependencies are obsolete; support for newer interpreters is still being developed. See the [compatibility audit](docs/python-compatibility.md) for known blockers and the [Docker test runner](docs/testing.md) for a reproducible development environment.

The platform instructions below are inherited setup guidance. Use the pinned test environment when reproducing CI results.

### macOS

macOS users will need to install [xcode command line tools](https://developer.xamarin.com/guides/testcloud/calabash/configuring/osx/install-xcode-command-line-tools/) and [homebrew](http://brew.sh/).

These environment variables also need to be set:
```
PYTHONUNBUFFERED=1
EVENT_NOKQUEUE=1
```

Remaining dependencies can then be installed by running:
```
brew install python protobuf
```

Assistance installing Python3: https://docs.python-guide.org/starting/install3/osx/.

### Linux

The historical Ubuntu setup uses the following packages:
```
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install build-essential python3.9 python3.9-dev git python3.9-venv libssl-dev python-protobuf
```

Package availability depends on the Ubuntu release. The [Docker test runner](docs/testing.md)
pins the Python 3.9 environment used by this fork.

On Raspbian, you will also need to install `python-pyparsing`.

If you're running another Linux distro, install the equivalent of the above packages for your system.

## Installation

### Linux/Mac

Clone the repository:
```bash
git clone https://github.com/kodxana/lbry-sdk-ng.git
cd lbry-sdk-ng
```

Create a Python virtual environment for lbry-sdk:
```bash
python3.9 -m venv lbry-venv
```

Activate virtual environment:
```bash
source lbry-venv/bin/activate
```

Make sure you're on Python 3.9 as default in the virtual environment:
```bash
python --version
```

Install packages:
```bash
make install
```

If you are on Linux and using PyCharm, generates initial configs:
```bash
make idea
```

To verify your installation, `which lbrynet` should return a path inside
of the `lbry-venv` folder.
```bash
(lbry-venv) $ which lbrynet
/opt/lbry-sdk-ng/lbry-venv/bin/lbrynet
```

To exit the virtual environment simply use the command `deactivate`.

### Windows

Clone the repository:
```bash
git clone https://github.com/kodxana/lbry-sdk-ng.git
cd lbry-sdk-ng
```

Create a Python virtual environment for lbry-sdk:
```bash
python -m venv lbry-venv
```

Activate virtual environment:
```bash
lbry-venv\Scripts\activate
```

Install packages:
```bash
pip install -e .
```

## Run the tests

For a contained Python 3.9 baseline on Linux or Windows with WSL2, see
[the Docker test runner](docs/testing.md). It downloads its dependencies during
the build, then runs tests without external network access or a mainnet node.

### Elasticsearch

For running integration tests, Elasticsearch is required to be available at localhost:9200/

The easiest way to start it is using docker with:
```bash
make elastic-docker
```

Alternative installation methods are available [at Elasticsearch website](https://www.elastic.co/guide/en/elasticsearch/reference/current/install-elasticsearch.html).

To run the unit and integration tests from the repo directory:
```
python -m unittest discover tests.unit
python -m unittest discover tests.integration
```

## Usage

To start the API server:
```
lbrynet start
```

Whenever the code inside [lbry-sdk/lbry](./lbry)
is modified we should run `make install` to recompile the `lbrynet`
executable with the newest code.

## Development

When developing, remember to enter the environment,
and if you wish start the server interactively.
```bash
$ source lbry-venv/bin/activate

(lbry-venv) $ python lbry/extras/cli.py start
```

Parameters can be passed in the same way.
```bash
(lbry-venv) $ python lbry/extras/cli.py wallet balance
```

If a Python debugger (`pdb` or `ipdb`) is installed we can also start it
in this way, set up break points, and step through the code.
```bash
(lbry-venv) $ pip install ipdb

(lbry-venv) $ ipdb lbry/extras/cli.py
```

Happy hacking!
