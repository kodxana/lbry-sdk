import asyncio
from unittest import mock

from lbry.testcase import AdvanceTimeTestCase
from lbry.blob_exchange.serialization import BlobRequest
from lbry.blob_exchange.server import BlobServerProtocol


class TestBlobServerIdleTimeout(AdvanceTimeTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.loop.set_debug(False)
        self.protocol = BlobServerProtocol(
            self.loop, mock.Mock(), 'bQEaw42GXsgCAGio1nxFncJSyRmnztSCjP', idle_timeout=1)
        self.transport = mock.Mock(spec=asyncio.Transport)
        self.transport.get_extra_info.return_value = ('127.0.0.1', 33333)
        self.protocol.connection_made(self.transport)
        self.addCleanup(self.protocol.connection_lost, None)

    async def test_idle_connection_closes_after_timeout(self):
        await self.advance(0.9)
        self.transport.close.assert_not_called()
        await self.advance(0.2)
        self.transport.close.assert_called_once_with()

    async def test_transfer_resets_idle_timeout(self):
        blob_hash = '0' * 96
        blob = self.protocol.blob_manager.get_blob.return_value
        blob.blob_hash = blob_hash
        blob.length = 1
        blob.get_is_verified.return_value = True
        self.protocol.blob_manager.completed_blob_hashes = {blob_hash}

        for _ in range(2):
            finish_transfer = asyncio.Event()

            async def sendfile(_protocol):
                await finish_transfer.wait()
                return 1

            blob.sendfile = mock.AsyncMock(side_effect=sendfile)
            await self.advance(0.5)
            transfer = self.loop.create_task(
                self.protocol.handle_request(BlobRequest.make_request_for_blob_hash(blob_hash)))
            await self.advance(0)
            blob.sendfile.assert_awaited_once_with(self.protocol)
            await self.advance(5)
            self.transport.close.assert_not_called()
            finish_transfer.set()
            await self.advance(0)
            self.assertTrue(transfer.done())
            await transfer

        await self.advance(0.9)
        self.transport.close.assert_not_called()
        await self.advance(0.2)
        self.transport.close.assert_called_once_with()
