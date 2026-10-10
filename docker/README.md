# Community SDK containers

Build from the repository root on Linux x86-64, or with Docker Desktop using
Linux containers. The images use Python 3.13 and run as user 999.

## Web gateway

Review `docker/webconf.yaml`, then run:

```sh
docker compose -f docker/docker-compose.yml up --build -d
```

The example is an ephemeral streaming gateway: its wallet, downloads and SDK
data live in the container's temporary directory and disappear when the
container is removed. Do not use this configuration to keep wallet funds.
The API and streaming ports bind to localhost on the host. Review access
controls before publishing either service beyond your machine.

To build and check the command without starting network services:

```sh
docker build -f docker/Dockerfile.web -t lbry-sdk-ng:web .
docker run --rm --network none --entrypoint lbrynet lbry-sdk-ng:web --version
```

## DHT node

```sh
docker build -f docker/Dockerfile.dht_node -t lbry-sdk-ng:dht .
docker run --rm --network none lbry-sdk-ng:dht --help
```

Starting a DHT node connects it to the configured network. Pass `--db_file`
to choose a persistent database path and provide a writable volume for user
999 when persistence is needed. The default database is temporary.

## Hub and regtests

Wallet-server services are maintained in
[LBRY Hub NG](https://github.com/kodxana/lbry-hub-ng). Build its Dockerfile and
select `HUB_COMMAND=scribe`, `herald`, or `scribe-elastic-sync` according to the
Hub documentation. The old SDK wallet-server image, Compose deployment and
snapshot/deployment helpers depended on removed commands and have been retired.

For isolated SDK integration tests use the [test runner](../docs/testing.md).
It replaces the old Torba-based orchstr8 image and supplies the matching Hub,
Elasticsearch and checksum-verified regtest executables. No mainnet node is needed.
