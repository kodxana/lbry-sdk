import asyncio
import sys
from unittest import skipIf
from unittest.mock import AsyncMock, Mock, patch

from lbry.testcase_async import AsyncioTestCase
from lbry.wallet.orchstr8.node import LBCWalletNode


@skipIf(sys.platform == 'win32', 'The regtest runner uses Unix child watchers.')
class LBCWalletCommandTests(AsyncioTestCase):

    async def asyncSetUp(self):
        self.node = LBCWalletNode('', '', '')
        self.addCleanup(self.node.cleanup)

    async def reap(self, process):
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.communicate()

    async def cancel_command(self, command):
        command.cancel()
        await asyncio.gather(command, return_exceptions=True)

    async def start_command(self, code):
        spawn = asyncio.create_subprocess_exec
        started = self.loop.create_future()

        async def python_child(*args, **kwargs):
            process = await spawn(sys.executable, '-c', code, **kwargs)
            started.set_result(process)
            return process

        with patch('lbry.wallet.orchstr8.node.asyncio.create_subprocess_exec', python_child):
            command = asyncio.create_task(self.node._cli_cmnd('getbalance'))
            try:
                process = await asyncio.wait_for(started, 5)
            except BaseException:
                await self.cancel_command(command)
                raise
        self.addCleanup(self.reap, process)
        self.addCleanup(self.cancel_command, command)
        return command, process

    def assert_reaped(self, process):
        self.assertIsNotNone(process.returncode)
        self.assertTrue(process.stdout.at_eof())
        self.assertTrue(process.stderr.at_eof())

    async def test_cancellation_reaps_child(self):
        command, process = await self.start_command('import time; time.sleep(60)')
        self.assertIsNone(process.returncode)
        command.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await command
        self.assert_reaped(process)

    async def test_timeout_reaps_child(self):
        command, process = await self.start_command('import time; time.sleep(60)')
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(command, 0.01)
        self.assertTrue(command.cancelled())
        self.assert_reaped(process)

    async def test_child_exit_during_cancellation_preserves_cancelled_error(self):
        process = Mock()
        process.communicate = AsyncMock(side_effect=[asyncio.CancelledError(), (b'', b'')])
        process.kill.side_effect = ProcessLookupError()
        with patch('lbry.wallet.orchstr8.node.asyncio.create_subprocess_exec', return_value=process):
            with self.assertRaises(asyncio.CancelledError):
                await self.node._cli_cmnd('getbalance')

    async def test_reads_both_pipes_and_returns_stripped_output(self):
        output = 'x' * (128 * 1024)
        diagnostic = 'y' * (128 * 1024)
        with self.assertLogs('lbry.wallet.orchstr8.node', level='WARNING') as logs:
            command, process = await self.start_command(
                "import sys; print('  ' + 'x' * (128 * 1024) + '  '); "
                "print('y' * (128 * 1024), file=sys.stderr)"
            )
            self.assertEqual(await asyncio.wait_for(command, 5), output)
        self.assertEqual([record.getMessage() for record in logs.records], [diagnostic])
        self.assert_reaped(process)

    async def test_command_errors_are_preserved(self):
        for code, error in (
            ("import sys; print('-1: failed', file=sys.stderr)", '-1: failed'),
            ("print('error code: -1')", 'error code: -1'),
        ):
            with self.subTest(error=error):
                command, process = await self.start_command(code)
                with self.assertRaisesRegex(Exception, error):
                    await asyncio.wait_for(command, 5)
                self.assert_reaped(process)
