from unittest.mock import Mock

from lbry.blob_exchange.client import BlobExchangeClientProtocol
from lbry.testcase_async import AsyncioTestCase


class BlobClientResponseTests(AsyncioTestCase):
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
