import os
import hashlib
from unittest import mock
import aiohttp
import aiohttp.web
import asyncio

from lbry.file.source import ManagedDownloadSource
from lbry.utils import aiohttp_request
from lbry.blob.blob_file import MAX_BLOB_SIZE
from lbry.testcase import CommandTestCase


def get_random_bytes(n: int) -> bytes:
    result = b''.join(hashlib.sha256(os.urandom(4)).digest() for _ in range(n // 16))
    if len(result) < n:
        result += os.urandom(n - len(result))
    elif len(result) > n:
        result = result[:-(len(result) - n)]
    assert len(result) == n, (n, len(result))
    return result


class RangeRequests(CommandTestCase):
    FILE_OPERATION_TIMEOUT = 10

    async def _restart_stream_manager(self):
        await self.daemon.file_manager.stop()
        await self.daemon.file_manager.start()
        return

    async def _setup_stream(self, data: bytes, save_blobs: bool = True, save_files: bool = False, file_size=0):
        self.daemon.conf.save_blobs = save_blobs
        self.daemon.conf.save_files = save_files
        self.data = data
        await self.stream_create('foo', '0.01', data=self.data, file_size=file_size)
        if save_blobs:
            self.assertGreater(len(os.listdir(self.daemon.blob_manager.blob_dir)), 1)
        await (await self.daemon.jsonrpc_file_list())['items'][0].fully_reflected.wait()
        await self.daemon.jsonrpc_file_delete(delete_from_download_dir=True, claim_name='foo')
        self.assertEqual(0, len(os.listdir(self.daemon.blob_manager.blob_dir)))
        # await self._restart_stream_manager()
        await self.daemon.streaming_runner.setup()
        site = aiohttp.web.TCPSite(self.daemon.streaming_runner, self.daemon.conf.streaming_host,
                                   self.daemon.conf.streaming_port)
        await site.start()
        self.assertItemCount(await self.daemon.jsonrpc_file_list(), 0)

    async def _test_range_requests(self):
        name = 'foo'
        url = f'http://{self.daemon.conf.streaming_host}:{self.daemon.conf.streaming_port}/get/{name}'

        async with aiohttp_request('get', url) as req:
            self.assertEqual(req.headers.get('Content-Type'), 'application/octet-stream')
            content_range = req.headers.get('Content-Range')
            content_length = int(req.headers.get('Content-Length'))
            streamed_bytes = await req.content.read()
        self.assertEqual(content_length, len(streamed_bytes))
        return streamed_bytes, content_range, content_length

    async def test_range_requests_2_byte(self):
        self.data = b'hi'
        await self._setup_stream(self.data)
        streamed, content_range, content_length = await self._test_range_requests()
        self.assertEqual(15, content_length)
        self.assertEqual(b'hi\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00', streamed)
        self.assertEqual('bytes 0-14/15', content_range)

    async def test_range_requests_15_byte(self):
        self.data = b'123456789abcdef'
        await self._setup_stream(self.data)
        streamed, content_range, content_length = await self._test_range_requests()
        self.assertEqual(15, content_length)
        self.assertEqual(15, len(streamed))
        self.assertEqual(self.data, streamed)
        self.assertEqual('bytes 0-14/15', content_range)

    async def test_range_requests_0_padded_bytes(self, size: int = (MAX_BLOB_SIZE - 1) * 4,
                                                 expected_range: str = 'bytes 0-8388603/8388604', padding=b'',
                                                 file_size=0):
        self.data = get_random_bytes(size)
        await self._setup_stream(self.data, file_size=file_size)
        streamed, content_range, content_length = await self._test_range_requests()
        self.assertEqual(len(self.data + padding), content_length)
        self.assertEqual(streamed, self.data + padding)
        self.assertEqual(expected_range, content_range)

    async def test_range_requests_1_padded_bytes(self):
        await self.test_range_requests_0_padded_bytes(
            ((MAX_BLOB_SIZE - 1) * 4) - 1, padding=b'\x00'
        )

    async def test_range_requests_2_padded_bytes(self):
        await self.test_range_requests_0_padded_bytes(
            ((MAX_BLOB_SIZE - 1) * 4) - 2, padding=b'\x00' * 2
        )

    async def test_range_requests_14_padded_bytes(self):
        await self.test_range_requests_0_padded_bytes(
            ((MAX_BLOB_SIZE - 1) * 4) - 14, padding=b'\x00' * 14
        )

    async def test_range_requests_no_padding_size_from_claim(self):
        size = ((MAX_BLOB_SIZE - 1) * 4) - 14
        await self.test_range_requests_0_padded_bytes(size, padding=b'', file_size=size,
                                                      expected_range=f"bytes 0-{size-1}/{size}")

    async def test_range_requests_15_padded_bytes(self):
        await self.test_range_requests_0_padded_bytes(
            ((MAX_BLOB_SIZE - 1) * 4) - 15, padding=b'\x00' * 15
        )

    async def test_forbidden(self):
        self.data = get_random_bytes(1000)
        await self._setup_stream(self.data, file_size=1000)
        url = f'http://{self.daemon.conf.streaming_host}:{self.daemon.conf.streaming_port}/get/foo'
        self.daemon.conf.streaming_get = False
        async with aiohttp_request('get', url) as req:
            self.assertEqual(403, req.status)

    async def test_range_requests_last_block_of_last_blob_padding(self):
        self.data = get_random_bytes(((MAX_BLOB_SIZE - 1) * 4) - 16)
        await self._setup_stream(self.data)
        streamed, content_range, content_length = await self._test_range_requests()
        self.assertEqual(len(self.data), content_length)
        self.assertEqual(streamed, self.data)
        self.assertEqual('bytes 0-8388587/8388588', content_range)

    async def test_streaming_only_with_blobs(self):
        self.data = get_random_bytes((MAX_BLOB_SIZE - 1) * 4)
        await self._setup_stream(self.data)

        await self._test_range_requests()
        stream = (await self.daemon.jsonrpc_file_list())['items'][0]
        self.assertTrue(os.path.isfile(self.daemon.blob_manager.get_blob(stream.sd_hash).file_path))
        self.assertIsNone(stream.download_directory)
        self.assertIsNone(stream.full_path)
        files_in_download_dir = list(os.scandir(self.daemon.conf.data_dir))

        # test that repeated range requests do not create duplicate files
        for _ in range(3):
            await self._test_range_requests()
            stream = (await self.daemon.jsonrpc_file_list())['items'][0]
            self.assertTrue(os.path.isfile(self.daemon.blob_manager.get_blob(stream.sd_hash).file_path))
            self.assertIsNone(stream.download_directory)
            self.assertIsNone(stream.full_path)
            current_files_in_download_dir = list(os.scandir(self.daemon.conf.data_dir))
            self.assertEqual(
                len(files_in_download_dir), len(current_files_in_download_dir)
            )

        # test that a range request after restart does not create a duplicate file
        await self._restart_stream_manager()

        current_files_in_download_dir = list(os.scandir(self.daemon.conf.data_dir))
        self.assertEqual(
            len(files_in_download_dir), len(current_files_in_download_dir)
        )
        stream = (await self.daemon.jsonrpc_file_list())['items'][0]
        self.assertTrue(os.path.isfile(self.daemon.blob_manager.get_blob(stream.sd_hash).file_path))
        self.assertIsNone(stream.download_directory)
        self.assertIsNone(stream.full_path)

        await self._test_range_requests()
        stream = (await self.daemon.jsonrpc_file_list())['items'][0]
        self.assertTrue(os.path.isfile(self.daemon.blob_manager.get_blob(stream.sd_hash).file_path))
        self.assertIsNone(stream.download_directory)
        self.assertIsNone(stream.full_path)
        current_files_in_download_dir = list(os.scandir(self.daemon.conf.data_dir))
        self.assertEqual(
            len(files_in_download_dir), len(current_files_in_download_dir)
        )

    async def test_streaming_only_without_blobs(self):
        self.data = get_random_bytes((MAX_BLOB_SIZE - 1) * 4)
        await self._setup_stream(self.data, save_blobs=False)
        await self._test_range_requests()
        stream = (await self.daemon.jsonrpc_file_list())['items'][0]
        self.assertIsNone(stream.download_directory)
        self.assertIsNone(stream.full_path)
        files_in_download_dir = list(os.scandir(self.daemon.conf.data_dir))

        # test that repeated range requests do not create duplicate files
        for _ in range(3):
            await self._test_range_requests()
            stream = (await self.daemon.jsonrpc_file_list())['items'][0]
            self.assertIsNone(stream.download_directory)
            self.assertIsNone(stream.full_path)
            current_files_in_download_dir = list(os.scandir(self.daemon.conf.data_dir))
            self.assertEqual(
                len(files_in_download_dir), len(current_files_in_download_dir)
            )

        # test that a range request after restart does not create a duplicate file
        await self._restart_stream_manager()

        current_files_in_download_dir = list(os.scandir(self.daemon.conf.data_dir))
        self.assertEqual(
            len(files_in_download_dir), len(current_files_in_download_dir)
        )
        stream = (await self.daemon.jsonrpc_file_list())['items'][0]
        self.assertIsNone(stream.download_directory)
        self.assertIsNone(stream.full_path)

        await self._test_range_requests()
        stream = (await self.daemon.jsonrpc_file_list())['items'][0]
        self.assertIsNone(stream.download_directory)
        self.assertIsNone(stream.full_path)
        current_files_in_download_dir = list(os.scandir(self.daemon.conf.data_dir))
        self.assertEqual(
            len(files_in_download_dir), len(current_files_in_download_dir)
        )

    async def test_stream_and_save_file_with_blobs(self):
        self.data = get_random_bytes((MAX_BLOB_SIZE - 1) * 4)
        await self._setup_stream(self.data, save_files=True)

        await self._test_range_requests()
        streams = (await self.daemon.jsonrpc_file_list())['items']
        self.assertEqual(1, len(streams))
        stream = streams[0]
        self.assertTrue(os.path.isfile(self.daemon.blob_manager.get_blob(stream.sd_hash).file_path))
        self.assertTrue(os.path.isdir(stream.download_directory))
        self.assertTrue(os.path.isfile(stream.full_path))
        full_path = stream.full_path
        files_in_download_dir = list(os.scandir(os.path.dirname(full_path)))

        for _ in range(3):
            await self._test_range_requests()
            streams = (await self.daemon.jsonrpc_file_list())['items']
            self.assertEqual(1, len(streams))
            stream = streams[0]
            self.assertTrue(os.path.isfile(self.daemon.blob_manager.get_blob(stream.sd_hash).file_path))
            self.assertTrue(os.path.isdir(stream.download_directory))
            self.assertTrue(os.path.isfile(stream.full_path))
            current_files_in_download_dir = list(os.scandir(os.path.dirname(full_path)))
            self.assertEqual(
                len(files_in_download_dir), len(current_files_in_download_dir)
            )

        await self._restart_stream_manager()

        current_files_in_download_dir = list(os.scandir(os.path.dirname(full_path)))
        self.assertEqual(
            len(files_in_download_dir), len(current_files_in_download_dir)
        )
        streams = (await self.daemon.jsonrpc_file_list())['items']
        self.assertEqual(1, len(streams))
        stream = streams[0]
        self.assertTrue(os.path.isfile(self.daemon.blob_manager.get_blob(stream.sd_hash).file_path))
        self.assertTrue(os.path.isdir(stream.download_directory))
        self.assertTrue(os.path.isfile(stream.full_path))

        await self._test_range_requests()
        streams = (await self.daemon.jsonrpc_file_list())['items']
        self.assertEqual(1, len(streams))
        stream = streams[0]
        self.assertTrue(os.path.isfile(self.daemon.blob_manager.get_blob(stream.sd_hash).file_path))
        self.assertTrue(os.path.isdir(stream.download_directory))
        self.assertTrue(os.path.isfile(stream.full_path))
        current_files_in_download_dir = list(os.scandir(os.path.dirname(full_path)))
        self.assertEqual(
            len(files_in_download_dir), len(current_files_in_download_dir)
        )
        with open(stream.full_path, 'rb') as f:
            self.assertEqual(self.data, f.read())

    async def test_stream_and_save_file_without_blobs(self):
        self.data = get_random_bytes((MAX_BLOB_SIZE - 1) * 4)
        await self._setup_stream(self.data, save_files=True)
        self.daemon.conf.save_blobs = False

        await self._test_range_requests()
        stream = (await self.daemon.jsonrpc_file_list())['items'][0]
        self.assertTrue(os.path.isdir(stream.download_directory))
        self.assertTrue(os.path.isfile(stream.full_path))
        full_path = stream.full_path
        files_in_download_dir = list(os.scandir(os.path.dirname(full_path)))

        for _ in range(3):
            await self._test_range_requests()
            stream = (await self.daemon.jsonrpc_file_list())['items'][0]
            self.assertTrue(os.path.isdir(stream.download_directory))
            self.assertTrue(os.path.isfile(stream.full_path))
            current_files_in_download_dir = list(os.scandir(os.path.dirname(full_path)))
            self.assertEqual(
                len(files_in_download_dir), len(current_files_in_download_dir)
            )

        await self._restart_stream_manager()
        current_files_in_download_dir = list(os.scandir(os.path.dirname(full_path)))
        self.assertEqual(
            len(files_in_download_dir), len(current_files_in_download_dir)
        )
        streams = (await self.daemon.jsonrpc_file_list())['items']
        self.assertEqual(1, len(streams))
        stream = streams[0]
        self.assertTrue(os.path.isdir(stream.download_directory))
        self.assertTrue(os.path.isfile(stream.full_path))

        await self._test_range_requests()
        streams = (await self.daemon.jsonrpc_file_list())['items']
        self.assertEqual(1, len(streams))
        stream = streams[0]
        self.assertTrue(os.path.isdir(stream.download_directory))
        self.assertTrue(os.path.isfile(stream.full_path))
        current_files_in_download_dir = list(os.scandir(os.path.dirname(full_path)))
        self.assertEqual(
            len(files_in_download_dir), len(current_files_in_download_dir)
        )

        with open(stream.full_path, 'rb') as f:
            self.assertEqual(self.data, f.read())

    async def test_switch_save_blobs_while_running(self):
        await self.test_streaming_only_without_blobs()
        self.daemon.conf.save_blobs = True
        blobs_in_stream = (await self.daemon.jsonrpc_file_list())['items'][0].blobs_in_stream
        sd_hash = (await self.daemon.jsonrpc_file_list())['items'][0].sd_hash
        start_file_count = len(os.listdir(self.daemon.blob_manager.blob_dir))
        await self._test_range_requests()
        self.assertEqual(start_file_count + blobs_in_stream, len(os.listdir(self.daemon.blob_manager.blob_dir)))
        self.assertEqual(0, (await self.daemon.jsonrpc_file_list())['items'][0].blobs_remaining)

        # switch back
        self.daemon.conf.save_blobs = False
        await self._test_range_requests()
        self.assertEqual(start_file_count + blobs_in_stream, len(os.listdir(self.daemon.blob_manager.blob_dir)))
        self.assertEqual(0, (await self.daemon.jsonrpc_file_list())['items'][0].blobs_remaining)
        await self.daemon.jsonrpc_file_delete(delete_from_download_dir=True, sd_hash=sd_hash)
        self.assertEqual(start_file_count, len(os.listdir(self.daemon.blob_manager.blob_dir)))
        await self._test_range_requests()
        self.assertEqual(start_file_count, len(os.listdir(self.daemon.blob_manager.blob_dir)))
        self.assertEqual(blobs_in_stream, (await self.daemon.jsonrpc_file_list())['items'][0].blobs_remaining)

    async def test_file_save_streaming_only_save_blobs(self):
        await self.test_streaming_only_with_blobs()
        stream = (await self.daemon.jsonrpc_file_list())['items'][0]
        self.assertIsNone(stream.full_path)
        self.server.stop_server()
        await self.daemon.jsonrpc_file_save('test', self.daemon.conf.data_dir)
        stream = (await self.daemon.jsonrpc_file_list())['items'][0]
        self.assertIsNotNone(stream.full_path)
        await stream.finished_writing.wait()
        with open(stream.full_path, 'rb') as f:
            self.assertEqual(self.data, f.read())
        await self.daemon.jsonrpc_file_delete(delete_from_download_dir=True, sd_hash=stream.sd_hash)

    async def _prepare_streaming_only_file_save(self):
        await self._setup_stream(get_random_bytes((MAX_BLOB_SIZE - 1) * 2))
        await self._test_range_requests()
        stream = (await self.daemon.jsonrpc_file_list())['items'][0]
        self.assertIsNone(stream.full_path)
        self.server.stop_server()
        return stream

    async def test_file_save_stop_before_finished_streaming_only(self):
        stream = await self._prepare_streaming_only_file_save()
        read_blob = stream.downloader.read_blob
        second_blob_requested = asyncio.Event()
        allow_second_blob = asyncio.Event()

        async def pause_second_blob(blob_info, connection_id=0):
            if blob_info.blob_num == 1:
                second_blob_requested.set()
                await allow_second_blob.wait()
            return await read_blob(blob_info, connection_id)

        # Keep the save incomplete until stop() cancels it. A fast disk must
        # not turn this into a test of restarting an already-finished file.
        with mock.patch.object(stream.downloader, 'read_blob', pause_second_blob):
            await asyncio.wait_for(
                self.daemon.jsonrpc_file_save('test', self.daemon.conf.data_dir), self.FILE_OPERATION_TIMEOUT
            )
            await asyncio.wait_for(stream.started_writing.wait(), self.FILE_OPERATION_TIMEOUT)
            await asyncio.wait_for(second_blob_requested.wait(), self.FILE_OPERATION_TIMEOUT)
            path = stream.full_path
            self.assertIsNotNone(path)
            self.assertEqual(stream.status, ManagedDownloadSource.STATUS_RUNNING)
            self.assertFalse(stream.finished_writing.is_set())
            with open(path, 'rb') as saved:
                self.assertEqual(self.data[:MAX_BLOB_SIZE - 1], saved.read())

            await asyncio.wait_for(self.daemon.file_manager.stop(), self.FILE_OPERATION_TIMEOUT)

        self.assertEqual((await self.daemon.jsonrpc_file_list())['items'], [])
        self.assertFalse(os.path.exists(path))
        await asyncio.wait_for(self.daemon.file_manager.start(), self.FILE_OPERATION_TIMEOUT)
        stream = (await self.daemon.jsonrpc_file_list())['items'][0]
        self.assertEqual(stream.full_path, path)
        await asyncio.wait_for(stream.started_writing.wait(), self.FILE_OPERATION_TIMEOUT)
        await asyncio.wait_for(stream.finished_write_attempt.wait(), self.FILE_OPERATION_TIMEOUT)
        self.assertTrue(stream.finished_writing.is_set())
        self.assertEqual(stream.status, ManagedDownloadSource.STATUS_FINISHED)
        with open(path, 'rb') as saved:
            self.assertEqual(self.data, saved.read())

    async def test_file_save_restart_after_finished_streaming_only(self):
        stream = await self._prepare_streaming_only_file_save()
        await asyncio.wait_for(
            self.daemon.jsonrpc_file_save('test', self.daemon.conf.data_dir), self.FILE_OPERATION_TIMEOUT
        )
        await asyncio.wait_for(stream.finished_write_attempt.wait(), self.FILE_OPERATION_TIMEOUT)
        self.assertTrue(stream.finished_writing.is_set())
        self.assertEqual(stream.status, ManagedDownloadSource.STATUS_FINISHED)
        path = stream.full_path
        with open(path, 'rb') as saved:
            self.assertEqual(self.data, saved.read())

        await asyncio.wait_for(self.daemon.file_manager.stop(), self.FILE_OPERATION_TIMEOUT)
        self.assertEqual((await self.daemon.jsonrpc_file_list())['items'], [])
        self.assertTrue(os.path.isfile(path))
        await asyncio.wait_for(self.daemon.file_manager.start(), self.FILE_OPERATION_TIMEOUT)
        stream = (await self.daemon.jsonrpc_file_list())['items'][0]
        self.assertEqual(stream.full_path, path)
        self.assertEqual(stream.status, ManagedDownloadSource.STATUS_FINISHED)
        with open(path, 'rb') as saved:
            self.assertEqual(self.data, saved.read())

    async def test_file_save_streaming_only_dont_save_blobs(self):
        await self.test_streaming_only_without_blobs()
        stream = (await self.daemon.jsonrpc_file_list())['items'][0]
        self.assertIsNone(stream.full_path)
        await self.daemon.jsonrpc_file_save('test', self.daemon.conf.data_dir)
        stream = (await self.daemon.jsonrpc_file_list())['items'][0]
        await stream.finished_writing.wait()
        with open(stream.full_path, 'rb') as f:
            self.assertEqual(self.data, f.read())


class RangeRequestsLRUCache(CommandTestCase):
    blob_lru_cache_size = 32

    async def _request_stream(self):
        name = 'foo'
        url = f'http://{self.daemon.conf.streaming_host}:{self.daemon.conf.streaming_port}/get/{name}'

        async with aiohttp_request('get', url) as req:
            self.assertEqual(req.headers.get('Content-Type'), 'application/octet-stream')
            content_range = req.headers.get('Content-Range')
            content_length = int(req.headers.get('Content-Length'))
            streamed_bytes = await req.content.read()
        self.assertEqual(content_length, len(streamed_bytes))
        self.assertEqual(15, content_length)
        self.assertEqual(b'hi\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00', streamed_bytes)
        self.assertEqual('bytes 0-14/15', content_range)

    async def test_range_requests_with_blob_lru_cache(self):
        self.data = b'hi'
        self.daemon.conf.save_blobs = False
        self.daemon.conf.save_files = False
        await self.stream_create('foo', '0.01', data=self.data, file_size=0)
        await (await self.daemon.jsonrpc_file_list())['items'][0].fully_reflected.wait()
        await self.daemon.jsonrpc_file_delete(delete_from_download_dir=True, claim_name='foo')
        self.assertEqual(0, len(os.listdir(self.daemon.blob_manager.blob_dir)))

        await self.daemon.streaming_runner.setup()
        site = aiohttp.web.TCPSite(self.daemon.streaming_runner, self.daemon.conf.streaming_host,
                                   self.daemon.conf.streaming_port)
        await site.start()
        self.assertItemCount(await self.daemon.jsonrpc_file_list(), 0)

        await self._request_stream()
        self.assertItemCount(await self.daemon.jsonrpc_file_list(), 1)
        self.server.stop_server()

        # running with cache size 0 gets through without errors without
        # this since the server doesn't stop immediately
        await asyncio.sleep(1)

        await self._request_stream()
