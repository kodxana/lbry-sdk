import asyncio
from unittest.mock import AsyncMock, Mock

from lbry.blob_exchange.client import BlobExchangeClientProtocol
from lbry.testcase_async import AsyncioTestCase


class BlobClientResponseTests(AsyncioTestCase):
    async def test_download_timeout_closes_connection(self):
        protocol = BlobExchangeClientProtocol(self.loop)
        transport = Mock()
        transport.is_closing.return_value = False
        transport.get_extra_info.return_value = ('127.0.0.1', 3333)
        protocol.connection_made(transport)
        self.addCleanup(protocol.close)
        writer = Mock()
        writer.closed.return_value = False
        blob = Mock()
        blob.get_is_verified.return_value = False
        blob.is_writeable.return_value = True
        blob.get_blob_writer.return_value = writer
        protocol._download_blob = AsyncMock(side_effect=asyncio.TimeoutError)

        self.assertEqual(await protocol.download_blob(blob), (0, None))
        self.assertTrue(protocol.closed.is_set())
        transport.close.assert_called_once_with()
        writer.close_handle.assert_called_once_with()
        self.assertIsNone(protocol._response_fut)

    async def test_late_response_after_cancellation_closes_connection(self):
        protocol = BlobExchangeClientProtocol(self.loop)
        transport = Mock()
        transport.is_closing.return_value = False
        transport.get_extra_info.return_value = ('127.0.0.1', 3333)
        protocol.connection_made(transport)
        self.addCleanup(protocol.close)
        writer = Mock()
        writer.closed.return_value = False
        protocol.writer = writer
        response = self.loop.create_future()
        protocol._response_fut = response
        response.cancel()

        # A timeout can cancel the response future before the download task
        # resumes to close its transport. A packet may arrive in that gap.
        protocol.data_received(b'{"blob_data_payment_rate":"RATE_ACCEPTED"}')

        self.assertTrue(response.cancelled())
        self.assertTrue(protocol.closed.is_set())
        transport.close.assert_called_once_with()
        writer.close_handle.assert_called_once_with()
        writer.write.assert_not_called()
        self.assertIsNone(protocol._response_fut)
