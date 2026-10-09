import os
import stat
import tempfile
from unittest import TestCase, mock

from lbry.wallet import WalletStorage


class TestWalletStorage(TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = os.path.join(directory.name, 'wallet.json')
        self.storage = WalletStorage(self.path)
        self.original = {
            'version': 1, 'name': 'Original wallet', 'preferences': {}, 'accounts': []
        }
        self.updated = dict(self.original, name='Updated wallet')
        self.storage.write(self.original)
        with open(self.path, 'rb') as wallet_file:
            self.original_bytes = wallet_file.read()

    def assert_original_wallet(self):
        self.assertTrue(os.path.isfile(self.path))
        with open(self.path, 'rb') as wallet_file:
            self.assertEqual(self.original_bytes, wallet_file.read())
        self.assertEqual(self.original, WalletStorage(self.path).read())

    def test_create_wallet(self):
        storage = WalletStorage(self.path + '.new')
        storage.write(self.updated)
        self.assertEqual(self.updated, WalletStorage(storage.path).read())
        mode = stat.S_IMODE(os.stat(storage.path).st_mode)
        if os.name == 'nt':
            self.assertTrue(mode & stat.S_IREAD)
            self.assertTrue(mode & stat.S_IWRITE)
        else:
            self.assertEqual(stat.S_IRUSR | stat.S_IWUSR, mode)

    def test_replace_wallet_preserves_permissions(self):
        os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
        original_mode = stat.S_IMODE(os.stat(self.path).st_mode)
        self.storage.write(self.updated)
        self.assertEqual(self.updated, WalletStorage(self.path).read())
        self.assertEqual(original_mode, stat.S_IMODE(os.stat(self.path).st_mode))

    def test_serialization_failure_preserves_wallet(self):
        with self.assertRaises(TypeError):
            self.storage.write(dict(self.updated, accounts=[object()]))
        self.assert_original_wallet()

    def test_sync_failure_preserves_wallet(self):
        error = OSError('injected sync failure')
        with mock.patch('lbry.wallet.wallet.os.fsync', side_effect=error):
            with self.assertRaises(OSError) as raised:
                self.storage.write(self.updated)
        self.assertIs(error, raised.exception)
        self.assert_original_wallet()

    def test_permission_failure_preserves_wallet(self):
        error = PermissionError('injected permission failure')
        with mock.patch('lbry.wallet.wallet.os.chmod', side_effect=error):
            with self.assertRaises(PermissionError) as raised:
                self.storage.write(self.updated)
        self.assertIs(error, raised.exception)
        self.assert_original_wallet()

    def test_replacement_failure_preserves_wallet_and_allows_retry(self):
        error = PermissionError('injected replacement failure')
        # Cover both the legacy rename path and replacement without depending
        # on which filesystem operation the writer uses.
        with mock.patch('lbry.wallet.wallet.os.rename', side_effect=error), \
                mock.patch('lbry.wallet.wallet.os.replace', side_effect=error):
            with self.assertRaises(PermissionError) as raised:
                self.storage.write(self.updated)
        self.assertIs(error, raised.exception)
        self.assert_original_wallet()

        self.storage.write(self.updated)
        self.assertEqual(self.updated, WalletStorage(self.path).read())

    def test_failed_first_save_reports_replacement_error(self):
        storage = WalletStorage(self.path + '.new')
        error = PermissionError('injected replacement failure')
        with mock.patch('lbry.wallet.wallet.os.rename', side_effect=error), \
                mock.patch('lbry.wallet.wallet.os.replace', side_effect=error):
            with self.assertRaises(PermissionError) as raised:
                storage.write(self.updated)
        self.assertIs(error, raised.exception)
        self.assertFalse(os.path.exists(storage.path))
