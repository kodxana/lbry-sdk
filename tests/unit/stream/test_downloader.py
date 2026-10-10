import asyncio
from unittest.mock import AsyncMock, Mock, patch

import lbry.wallet
from lbry.conf import Config
from lbry.dht import constants
from lbry.dht.node import Node
from lbry.dht.peer import PeerManager
from lbry.error import DownloadSDTimeoutError
from lbry.stream.managed_stream import ManagedStream
from lbry.testcase_async import AdvanceTimeTestCase


class StreamStartupTests(AdvanceTimeTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        config = Config(fixed_peers=[])
        blob_manager = Mock(decrypted_blob_lru_cache=None)
        self.stream = ManagedStream(self.loop, config, blob_manager, '00' * 48)
        self.downloader = self.stream.downloader
        self.node = Node(self.loop, PeerManager(self.loop), constants.generate_id(),
                         4444, 4444, 3333, '1.2.3.4')
        self.downloader.node = self.node
        self.producer_stopped = asyncio.Event()
        self.descriptor_result = self.loop.create_future()

        async def find_peers(blob_hash, result_queue):
            try:
                await asyncio.Future()
            finally:
                await asyncio.sleep(0)
                self.producer_stopped.set()

        async def load_descriptor(connection_id=0):
            await self.descriptor_result

        self.node._peers_for_value_producer = find_peers
        self.downloader.load_descriptor = load_descriptor
        tracker = patch('lbry.stream.downloader.enqueue_tracker_search')
        tracker.start()
        self.addCleanup(tracker.stop)
        self.addCleanup(self.downloader.stop)
        self.existing_tasks = asyncio.all_tasks()

    async def start_download(self):
        started = asyncio.create_task(self.stream.start(timeout=10))
        await self.advance(0)
        self.assertIsNotNone(self.downloader.accumulate_task)
        return started

    def assert_stopped(self):
        self.assertFalse(self.stream._running.is_set())
        self.assertIsNone(self.downloader.accumulate_task)
        self.assertTrue(self.producer_stopped.is_set())
        self.assertEqual(set(), asyncio.all_tasks() - self.existing_tasks - {asyncio.current_task()})

    async def test_descriptor_timeout_stops_peer_search(self):
        started = await self.start_download()
        await self.advance(10)
        with self.assertRaises(DownloadSDTimeoutError):
            await started
        self.assert_stopped()

    async def test_descriptor_error_stops_peer_search_and_allows_retry(self):
        started = await self.start_download()
        self.descriptor_result.set_exception(ValueError('invalid descriptor'))
        with self.assertRaisesRegex(ValueError, 'invalid descriptor'):
            await started
        self.assert_stopped()
        self.downloader.load_descriptor = AsyncMock(side_effect=ValueError('retried descriptor'))
        with self.assertRaisesRegex(ValueError, 'retried descriptor'):
            await self.stream.start()
        self.downloader.load_descriptor.assert_awaited_once()

    async def test_cancelled_start_stops_peer_search(self):
        started = await self.start_download()
        started.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await started
        self.assert_stopped()
