# LBRY SDK NG [![build](https://github.com/kodxana/lbry-sdk-ng/actions/workflows/main.yml/badge.svg)](https://github.com/kodxana/lbry-sdk-ng/actions/workflows/main.yml)

LBRY SDK NG is a community-maintained fork of [LBRY SDK](https://github.com/lbryio/lbry-sdk), originally developed by LBRY Inc. This project is maintained independently of LBRY Inc.; its changes and releases are community work, not official LBRY Inc. releases. Credit and license notices for the original authors are preserved.

The repository is now `kodxana/lbry-sdk-ng`. The Python package remains `lbry` and the command remains `lbrynet`; the repository rename does not change wallet formats or data directories.

LBRY is a decentralized peer-to-peer protocol for publishing and accessing digital content. It utilizes the [LBRY blockchain](https://github.com/lbryio/lbrycrd) as a global namespace and database of digital content. Blockchain entries contain searchable content metadata, identities, rights and access rules. LBRY also provides a data network that consists of peers (seeders) uploading and downloading data from other peers, possibly in exchange for payments, as well as a distributed hash table used by peers to discover other peers.

The SDK implements the LBRY network protocols in Python and includes components and tools for building decentralized applications:

 * Built on Python and `asyncio`; see the [tested baseline](docs/testing.md) and [Python compatibility work](docs/python-compatibility.md).
 * Kademlia DHT (Distributed Hash Table) implementation for peer discovery ([lbry.dht](lbry/dht)).
 * Blob exchange protocol for transferring encrypted content and negotiating payments ([lbry.blob_exchange](lbry/blob_exchange)).
 * Protobuf schema for encoding and decoding blockchain metadata ([lbry.schema](lbry/schema)).
 * Wallet implementation for the LBRY blockchain ([lbry.wallet](lbry/wallet)).
 * Daemon with a JSON-RPC API for applications and automation ([lbry.extras.daemon](lbry/extras/daemon)).

## Installation

Use [INSTALL.md](INSTALL.md) to work from this fork's source. Community releases belong on [this repository's releases page](https://github.com/kodxana/lbry-sdk-ng/releases). Historical [upstream binaries](https://github.com/lbryio/lbry-sdk/releases) do not include this fork's fixes.

## Usage

Run `lbrynet start` to launch the API server.

By default, `lbrynet` will provide a JSON-RPC server at `http://localhost:5279`. It is easy to interact with via cURL or sane programming languages.

The [upstream quickstart guide](https://lbry.tech/playground) provides a walkthrough and examples.

With the daemon running, `lbrynet commands` will show you a list of commands.

The full API is documented [here](https://lbry.tech/api/sdk).

## Running from source

Installing from source is also relatively painless. Full instructions are in [INSTALL.md](INSTALL.md)

## Contributing

Bug reports, tests, documentation and focused pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) and report fork issues in [this repository](https://github.com/kodxana/lbry-sdk-ng/issues).

Related community projects: [LBRY Hub NG](https://github.com/kodxana/lbry-hub-ng) and [lbry-rocksdb-ng](https://github.com/kodxana/lbry-rocksdb-ng).

## License

This project is MIT licensed. For the full license, see [LICENSE](LICENSE).

## Security

See [SECURITY.md](SECURITY.md) for reporting guidance. LBRY Inc. email addresses are not support contacts for this fork.

## Contact

The fork is maintained by [@kodxana](https://github.com/kodxana) and community contributors. Use this repository's issues for general questions and bug reports.

## Additional information and links

The documentation for the API can be found [here](https://lbry.tech/api/sdk).

Daemon defaults, ports, and other settings are documented [here](https://lbry.tech/resources/daemon-settings).

Settings can be configured using a daemon-settings.yml file. See the [example configuration](example_daemon_settings.yml).
