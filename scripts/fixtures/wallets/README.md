# Wallet compatibility fixtures

These are public test keys. Never send funds to these addresses.

`plain.json` and `encrypted.json` were written by SDK 0.113.0 at commit
`67e28110c2bbb640e379acd85a4393630ebf2c71`, using CPython 3.9.25 before the
Python 3.13 migration. The source was extracted with `git archive` and imported
from that separate directory. They use the existing version 1 wallet format,
with a regtest account so the binary test never needs mainnet headers.

Both contain the seed from the historical `TestWalletCreation` fixture:
`carbon smart garage balance margin twelve chest sword toast envelope bottom stomach absent`.
The account is named `Public test account`, has `modified_on=1571762543`, and
uses the deterministic address generator with receiving gap 20, change gap 6,
and one use per address. The wallet is named `SDK 0.113 compatibility fixture`.
The legacy `Wallet.save()` wrote the plaintext file; `Wallet.encrypt()` wrote
the encrypted file using the password recorded in `expected.json`.

`expected.json` records the legacy account serialization and all 26 addresses
derived with the legacy account's receiving and change address managers. The
binary test checks these fixed values after loading, unlocking, changing the
password, saving and restarting. It does not regenerate them with current code.

The loopback Hub stub has no blocks or transaction history. These fixtures
cover wallet file and key compatibility; chain synchronization, transaction
validation and real Hub behavior are covered by the separate regtest suites.
