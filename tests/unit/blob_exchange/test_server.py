import asyncio
from unittest import mock

from lbry.testcase import AdvanceTimeTestCase
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
        for _ in range(2):
            await self.advance(0.5)
            self.protocol.started_transfer.set()
            await self.advance(5)
            self.transport.close.assert_not_called()
            self.protocol.transfer_finished.set()
            await self.advance(0)

        await self.advance(0.9)
        self.transport.close.assert_not_called()
        await self.advance(0.2)
        self.transport.close.assert_called_once_with()
