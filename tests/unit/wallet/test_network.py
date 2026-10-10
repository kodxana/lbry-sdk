import asyncio
import gc
import json
from unittest.mock import Mock, patch

from lbry.testcase_async import AdvanceTimeTestCase
from lbry.wallet.network import ClientSession
from lbry.wallet.rpc import RPCError, ProtocolError
from lbry.wallet.rpc.jsonrpc import JSONRPCv2


class ClientSessionTests(AdvanceTimeTestCase):

    async def asyncSetUp(self):
        await super().asyncSetUp()
        clock = patch('lbry.wallet.network.perf_counter', self.loop.time)
        clock.start()
        self.addCleanup(clock.stop)
        self.session = ClientSession(network=None, server=('localhost', 50001), timeout=5, concurrency=1)
        self.session.last_packet_received = self.loop.time()
        self.sent = asyncio.Queue()
        self.session.transport = Mock()
        self.session.transport.is_closing.return_value = False
        self.session.transport.write.side_effect = lambda message: self.sent.put_nowait(
            (asyncio.current_task(), json.loads(message))
        )
        self.addCleanup(self.session.connection_lost, None)

    async def start_request(self, method='server.ping', args=()):
        caller = asyncio.create_task(self.session.send_request(method, args))
        request, message = await self.sent.get()
        self.assertEqual(message['method'], method)
        self.assertEqual(message.get('params', []), list(args))
        return caller, request, message

    def respond(self, message, result):
        self.session.connection.receive_message(JSONRPCv2.response_message(result, message['id']))

    async def test_result_releases_request_slot(self):
        caller, request, message = await self.start_request('blockchain.address.get_history', ['address'])
        self.assertEqual(self.session.concurrency, 0)
        self.respond(message, [{'tx_hash': 'transaction', 'height': 1}])
        self.assertEqual(await caller, [{'tx_hash': 'transaction', 'height': 1}])
        self.assertTrue(request.done())
        self.assertEqual(self.session.concurrency, 1)

    async def test_rpc_error_releases_request_slot(self):
        caller, request, message = await self.start_request()
        self.respond(message, RPCError(1, 'request failed'))
        with self.assertRaisesRegex(RPCError, 'request failed'):
            await caller
        self.assertTrue(request.done())
        self.assertEqual(self.session.concurrency, 1)
        self.session.transport.close.assert_not_called()

    async def test_connection_errors_release_request_slot(self):
        for error in (ConnectionResetError(), ProtocolError(1, 'bad response'), asyncio.TimeoutError()):
            with self.subTest(error=type(error).__name__):
                caller, request, _ = await self.start_request()
                self.session.connection.raise_pending_requests(error)
                with self.assertRaises(type(error)):
                    await caller
                self.assertTrue(request.done())
                self.assertEqual(self.session.concurrency, 1)
        self.session.transport.close.assert_called_once()

    async def test_cancellation_stops_request_and_accepts_late_response(self):
        caller, request, message = await self.start_request()
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertTrue(request.cancelled())
        self.assertEqual(self.session.concurrency, 1)
        # The wire request is still valid. Its late reply must not interfere
        # with another request on the same connection.
        next_caller, _, next_message = await self.start_request()
        self.respond(message, 'late reply')
        self.assertFalse(next_caller.done())
        self.respond(next_message, 'next reply')
        self.assertEqual(await next_caller, 'next reply')
        self.assertEqual(self.session.connection.pending_requests(), [])
        self.session.transport.close.assert_not_called()

    async def test_timeout_stops_request(self):
        caller, request, message = await self.start_request()
        await self.advance(5)
        with self.assertRaises(asyncio.TimeoutError):
            await caller
        self.assertTrue(request.cancelled())
        self.assertEqual(self.session.concurrency, 1)
        self.respond(message, 'late reply')
        self.assertEqual(self.session.connection.pending_requests(), [])

    async def test_recent_packets_extend_request_timeout(self):
        caller, request, message = await self.start_request()
        await self.advance(4)
        self.session.last_packet_received = self.loop.time()
        await self.advance(1)
        self.assertFalse(caller.done())
        self.assertFalse(request.done())
        self.assertEqual(self.session.concurrency, 0)
        self.respond(message, 'reply after first timeout')
        self.assertEqual(await caller, 'reply after first timeout')
        self.assertEqual(self.session.concurrency, 1)

    async def test_cancellation_while_waiting_does_not_add_request_slot(self):
        caller, _, message = await self.start_request()
        for method in ('server.ping', 'server.version'):
            with self.subTest(method=method):
                waiting = asyncio.create_task(self.session.send_request(method))
                await self.advance(0)
                self.assertFalse(waiting.done())
                waiting.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await waiting
                self.assertEqual(self.session.concurrency, 0)
                self.assertTrue(self.sent.empty())
        self.respond(message, 'reply')
        self.assertEqual(await caller, 'reply')
        self.assertEqual(self.session.concurrency, 1)

    async def test_cancellation_retrieves_concurrent_request_error(self):
        errors = []
        handler = self.loop.get_exception_handler()
        self.loop.set_exception_handler(lambda loop, context: errors.append(context))
        self.addCleanup(self.loop.set_exception_handler, handler)
        caller, request, _ = await self.start_request()
        # Cancel after the RPC task fails, before its caller reads the error.
        request.add_done_callback(lambda task: caller.cancel())
        self.session.connection.raise_pending_requests(asyncio.TimeoutError())
        with self.assertRaises(asyncio.CancelledError):
            await caller
        del caller, request
        await self.advance(0)
        gc.collect()
        self.assertEqual(errors, [])
        self.assertEqual(self.session.concurrency, 1)

    async def test_cancellation_while_transport_is_paused(self):
        self.session.pause_writing()
        blocked = asyncio.Queue()
        limited_wait = self.session._limited_wait

        async def wait_for_transport(seconds):
            blocked.put_nowait(asyncio.current_task())
            await limited_wait(seconds)

        with patch.object(self.session, '_limited_wait', wait_for_transport):
            caller = asyncio.create_task(self.session.send_request('server.ping'))
            request = await blocked.get()
            caller.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await caller
            self.assertTrue(request.cancelled())
        self.session.resume_writing()
        await self.advance(0)
        self.session.transport.write.assert_not_called()
        self.assertEqual(self.session.concurrency, 1)

    async def test_server_version_cancellation_stops_request(self):
        caller, request, _ = await self.start_request('server.version')
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertTrue(request.cancelled())
        self.assertIsNone(self.session.response_time)
        self.assertEqual(self.session.concurrency, 1)

    async def test_server_version_timeout_stops_request(self):
        caller, request, _ = await self.start_request('server.version')
        await self.advance(5)
        with self.assertRaises(asyncio.TimeoutError):
            await caller
        self.assertTrue(request.cancelled())
        self.assertIsNone(self.session.response_time)
        self.assertEqual(self.session.concurrency, 1)

    async def test_server_version_records_response_time(self):
        caller, _, message = await self.start_request('server.version', ['client', '0.65.0'])
        await self.advance(2)
        self.respond(message, ['server', '0.65.0'])
        self.assertEqual(await caller, ['server', '0.65.0'])
        self.assertEqual(self.session.response_time, 2)
        self.assertEqual(self.session.concurrency, 1)
