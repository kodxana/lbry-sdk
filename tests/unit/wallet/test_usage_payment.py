import asyncio
from unittest.mock import AsyncMock, Mock

from lbry.testcase_async import AdvanceTimeTestCase
from lbry.wallet.usage_payment import WalletServerPayer


class WalletServerPayerTests(AdvanceTimeTestCase):

    # Advancing a day of virtual time is not a slow callback.
    LOOP_SLOW_CALLBACK_DURATION = float('inf')

    async def start_payer(self, payment_period, error):
        payer = WalletServerPayer(payment_period=payment_period)
        features = AsyncMock(side_effect=error)
        ledger = Mock()
        ledger.network.get_server_features = features
        await payer.start(ledger=ledger)
        self.addCleanup(self.stop_payer, payer)
        return payer, features

    async def stop_payer(self, payer):
        await payer.stop()
        await asyncio.gather(payer.task, return_exceptions=True)

    async def test_retry_delay_after_timeout_or_connection_error(self):
        for error in (asyncio.TimeoutError, ConnectionError):
            for payment_period, delay in ((24, 10), (24 * 60 * 60, 60 * 60)):
                with self.subTest(error=error.__name__, payment_period=payment_period):
                    payer, features = await self.start_payer(payment_period, error)
                    try:
                        await self.advance(payment_period)
                        self.assertEqual(features.await_count, 1)
                        for attempt in (2, 3):
                            await self.advance(delay - 1)
                            self.assertEqual(features.await_count, attempt - 1)
                            await self.advance(1)
                            # Each new payment loop still starts with its normal interval.
                            await self.advance(payment_period - 1)
                            self.assertEqual(features.await_count, attempt - 1)
                            await self.advance(1)
                            self.assertEqual(features.await_count, attempt)
                        self.assertFalse(payer.task.done())
                    finally:
                        await self.stop_payer(payer)

    async def test_stop_during_retry_delay(self):
        for error in (asyncio.TimeoutError, ConnectionError):
            with self.subTest(error=error.__name__):
                payer, features = await self.start_payer(24, error)
                await self.advance(24)
                features.assert_awaited_once()
                self.assertFalse(payer.task.done())

                await payer.stop()
                with self.assertRaises(asyncio.CancelledError):
                    await payer.task
                self.assertFalse(payer.running)
                await self.advance(100)
                features.assert_awaited_once()
