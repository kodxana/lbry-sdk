"""Async test helpers that can run without SDK dependencies installed."""
import asyncio
from asyncio.runners import _cancel_all_tasks
import functools
from time import time
import unittest
from unittest.case import _Outcome


class AsyncioTestCase(unittest.TestCase):
    # Implementation inspired by discussion:
    #  https://bugs.python.org/issue32972

    LOOP_SLOW_CALLBACK_DURATION = 0.2
    TIMEOUT = 120.0

    maxDiff = None

    async def asyncSetUp(self):  # pylint: disable=C0103
        pass

    async def asyncTearDown(self):  # pylint: disable=C0103
        pass

    def run(self, result=None):  # pylint: disable=R0915
        orig_result = result
        if result is None:
            result = self.defaultTestResult()
            startTestRun = getattr(result, 'startTestRun', None)  # pylint: disable=C0103
            if startTestRun is not None:
                startTestRun()

        result.startTest(self)

        testMethod = getattr(self, self._testMethodName)  # pylint: disable=C0103
        if (getattr(self.__class__, "__unittest_skip__", False) or
                getattr(testMethod, "__unittest_skip__", False)):
            # If the class or method was skipped.
            try:
                skip_why = (getattr(self.__class__, '__unittest_skip_why__', '')
                            or getattr(testMethod, '__unittest_skip_why__', ''))
                self._addSkip(result, self, skip_why)
            finally:
                result.stopTest(self)
            return
        expecting_failure_method = getattr(testMethod,
                                           "__unittest_expecting_failure__", False)
        expecting_failure_class = getattr(self,
                                          "__unittest_expecting_failure__", False)
        expecting_failure = expecting_failure_class or expecting_failure_method
        outcome = _Outcome(result)

        self.loop = asyncio.new_event_loop()  # pylint: disable=W0201
        asyncio.set_event_loop(self.loop)
        self.loop.set_debug(True)
        self.loop.slow_callback_duration = self.LOOP_SLOW_CALLBACK_DURATION

        try:
            self._outcome = outcome

            with outcome.testPartExecutor(self):
                self.setUp()
                self.add_timeout()
                self.loop.run_until_complete(self.asyncSetUp())
            if outcome.success:
                outcome.expecting_failure = expecting_failure
                with outcome.testPartExecutor(self, isTest=True):
                    maybe_coroutine = testMethod()
                    if asyncio.iscoroutine(maybe_coroutine):
                        self.add_timeout()
                        self.loop.run_until_complete(maybe_coroutine)
                outcome.expecting_failure = False
                with outcome.testPartExecutor(self):
                    self.add_timeout()
                    self.loop.run_until_complete(self.asyncTearDown())
                    self.tearDown()

            self.doAsyncCleanups()

            try:
                _cancel_all_tasks(self.loop)
                self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            finally:
                asyncio.set_event_loop(None)
                self.loop.close()

            for test, reason in outcome.skipped:
                self._addSkip(result, test, reason)
            self._feedErrorsToResult(result, outcome.errors)
            if outcome.success:
                if expecting_failure:
                    if outcome.expectedFailure:
                        self._addExpectedFailure(result, outcome.expectedFailure)
                    else:
                        self._addUnexpectedSuccess(result)
                else:
                    result.addSuccess(self)
            return result
        finally:
            result.stopTest(self)
            if orig_result is None:
                stopTestRun = getattr(result, 'stopTestRun', None)  # pylint: disable=C0103
                if stopTestRun is not None:
                    stopTestRun()  # pylint: disable=E1102

            # explicitly break reference cycles:
            # outcome.errors -> frame -> outcome -> outcome.errors
            # outcome.expectedFailure -> frame -> outcome -> outcome.expectedFailure
            outcome.errors.clear()
            outcome.expectedFailure = None

            # clear the outcome, no more needed
            self._outcome = None

    def doAsyncCleanups(self):  # pylint: disable=C0103
        outcome = self._outcome or _Outcome()
        while self._cleanups:
            function, args, kwargs = self._cleanups.pop()
            with outcome.testPartExecutor(self):
                maybe_coroutine = function(*args, **kwargs)
                if asyncio.iscoroutine(maybe_coroutine):
                    self.add_timeout()
                    self.loop.run_until_complete(maybe_coroutine)

    def cancel(self):
        for task in asyncio.all_tasks(self.loop):
            if not task.done():
                task.print_stack()
                task.cancel()

    def add_timeout(self):
        if self.TIMEOUT:
            self.loop.call_later(self.TIMEOUT, self.check_timeout, time())

    def check_timeout(self, started):
        if time() - started >= self.TIMEOUT:
            self.cancel()
        else:
            self.loop.call_later(self.TIMEOUT, self.check_timeout, started)


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
