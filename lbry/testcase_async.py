"""Async test helpers that can run without SDK dependencies installed."""
import asyncio
import functools
import inspect
from time import monotonic
import unittest


class AsyncioTestCase(unittest.IsolatedAsyncioTestCase):
    LOOP_SLOW_CALLBACK_DURATION = 0.2
    TIMEOUT = 120.0

    maxDiff = None

    def __init__(self, methodName='runTest'):
        super().__init__(methodName)
        # Registered first so user cleanups run before final resource shutdown.
        self.addCleanup(self._shutdown_resources)

    @functools.cached_property
    def loop(self):
        loop = asyncio.get_event_loop()
        loop.slow_callback_duration = self.LOOP_SLOW_CALLBACK_DURATION
        return loop

    def _callAsync(self, function, /, *args, **kwargs):
        async def run():
            return await self._await_with_timeout(function(*args, **kwargs))

        return super()._callAsync(run)

    def _callMaybeAsync(self, function, /, *args, **kwargs):
        if inspect.iscoroutinefunction(function):
            return self._callAsync(function, *args, **kwargs)
        result = super()._callMaybeAsync(function, *args, **kwargs)
        # Existing addCleanup callers include lambdas and callable objects
        # that return awaitables rather than being coroutine functions.
        if inspect.isawaitable(result):
            async def await_result():
                return await result
            return self._callAsync(await_result)
        return result

    @staticmethod
    async def _shutdown_resources():
        # Python 3.9's IsolatedAsyncioTestCase skips shutdown_asyncgens when
        # no pending tasks remain. Close generators consistently on every
        # supported interpreter, after cancelling any tasks using them.
        loop = asyncio.get_running_loop()
        current = asyncio.current_task()
        pending = [task for task in asyncio.all_tasks() if task is not current]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for task in pending:
            if not task.cancelled() and task.exception() is not None:
                loop.call_exception_handler({
                    'message': 'Unhandled exception during async test shutdown',
                    'exception': task.exception(),
                    'task': task,
                })
        await loop.shutdown_asyncgens()

    async def _await_with_timeout(self, awaitable):
        loop = asyncio.get_running_loop()
        loop.slow_callback_duration = self.LOOP_SLOW_CALLBACK_DURATION
        timeout = self.TIMEOUT
        if not timeout:
            return await awaitable

        task = asyncio.current_task()
        deadline = monotonic() + timeout
        expired = False

        def check_deadline():
            nonlocal handle, expired
            remaining = deadline - monotonic()
            if remaining > 0:
                # AdvanceTimeTestCase changes loop.time(). Advancing its
                # virtual clock must not consume the real-time timeout.
                handle = loop.call_later(remaining, check_deadline)
            else:
                expired = True
                task.cancel()

        handle = loop.call_later(timeout, check_deadline)
        try:
            # Await in unittest's task so ContextVars survive between phases.
            result = await awaitable
        except asyncio.CancelledError as error:
            if not expired:
                raise
            raise asyncio.TimeoutError(f'Async test phase exceeded {timeout} seconds') from error
        finally:
            handle.cancel()
        if expired:
            # A coroutine that catches cancellation still exceeded its limit.
            raise asyncio.TimeoutError(f'Async test phase exceeded {timeout} seconds')
        return result


class AdvanceTimeTestCase(AsyncioTestCase):

    async def asyncSetUp(self):
        self._time = 0  # pylint: disable=W0201
        self.loop.time = functools.wraps(self.loop.time)(lambda: self._time)
        await super().asyncSetUp()

    async def advance(self, seconds):
        while self.loop._ready:
            await asyncio.sleep(0)
        self._time += seconds
        await asyncio.sleep(0)
        while self.loop._ready:
            await asyncio.sleep(0)
