import asyncio
import os
from types import SimpleNamespace
from unittest.mock import Mock

from lbry.testcase_async import AsyncioTestCase
from lbry.torrent.session import TorrentHandle, TorrentSession


class TestTorrentHandle(AsyncioTestCase):
    async def test_events_can_be_awaited_on_session_loop(self):
        handle = TorrentHandle(self.loop, None, Mock())
        events = (handle.started, handle.finished, handle.metadata_completed)
        for event in events:
            self.assertFalse(event.is_set())
        waiters = [asyncio.create_task(event.wait()) for event in events]
        try:
            await asyncio.sleep(0)
            for event in events:
                event.set()
            self.assertEqual(await asyncio.wait_for(asyncio.gather(*waiters), 1), [True] * 3)
        finally:
            for waiter in waiters:
                waiter.cancel()
            await asyncio.gather(*waiters, return_exceptions=True)

    async def test_add_torrent_creates_events_on_session_loop(self):
        btih = 'ab' * 20
        files = Mock()
        files.num_files.return_value = 1
        files.file_size.return_value = 1024
        files.at.return_value = SimpleNamespace(path='video.mp4', offset=0)
        native_handle = Mock()
        native_handle.get_torrent_info.return_value.files.return_value = files
        native_handle.status.return_value = SimpleNamespace(
            has_metadata=True, total_wanted=1024, total_wanted_done=1024,
            name='video.mp4', info_hash=btih, save_path='downloads', is_seeding=True
        )
        native_handle.have_piece.return_value = True
        session = TorrentSession(self.loop, None)
        session._session = Mock()
        session._session.add_torrent.return_value = native_handle
        try:
            await asyncio.wait_for(session.add_torrent(btih, 'downloads'), 1)
            handle = session._handles[btih]
            self.assertTrue(handle.metadata_completed.is_set())
            self.assertTrue(handle.started.is_set())
            self.assertTrue(handle.finished.is_set())
            self.assertEqual(session.full_path(btih), os.path.join('downloads', 'video.mp4'))
            native_handle.force_dht_announce.assert_called_once_with()
        finally:
            tasks = [task for handle in session._handles.values() for task in handle.tasks]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
