import asyncio
import contextvars
import unittest

from lbry.testcase_async import AsyncioTestCase, AdvanceTimeTestCase, wait_for_tasks


class TestWaitForTasks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.started = asyncio.Event()
        self.cleaned_up = asyncio.Event()

    async def pending_operation(self):
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            self.cleaned_up.set()

    async def test_accepts_coroutines_and_futures(self):
        future = asyncio.get_running_loop().create_future()

        async def complete():
            future.set_result('notification')
            return 'operation'

        self.assertEqual(await wait_for_tasks(complete(), future), ['operation', 'notification'])
        self.assertEqual(await wait_for_tasks(), [])

    async def test_failure_cancels_and_drains_sibling(self):
        async def fail():
            await self.started.wait()
            raise ValueError('operation failed')

        with self.assertRaisesRegex(ValueError, 'operation failed'):
            await wait_for_tasks(self.pending_operation(), fail())
        self.assertTrue(self.cleaned_up.is_set())

    async def test_timeout_cancels_and_drains_operations(self):
        future = asyncio.get_running_loop().create_future()
        with self.assertRaises(asyncio.TimeoutError):
            await wait_for_tasks(self.pending_operation(), future, timeout=0.01)
        self.assertTrue(self.cleaned_up.is_set())
        self.assertTrue(future.cancelled())

    async def test_cancellation_drains_operations(self):
        task = asyncio.create_task(wait_for_tasks(self.pending_operation()))
        await self.started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.cleaned_up.is_set())

    async def test_cleanup_failure_does_not_hide_original_error(self):
        async def fail():
            await self.started.wait()
            raise ValueError('operation failed')

        async def fail_during_cleanup():
            try:
                await self.pending_operation()
            finally:
                raise RuntimeError('cleanup failed')

        with self.assertRaisesRegex(ValueError, 'operation failed'):
            await wait_for_tasks(fail_during_cleanup(), fail())
        self.assertTrue(self.cleaned_up.is_set())


class TestAsyncioTestCase(unittest.TestCase):
    def run_case(self, case_type, method='test_body'):
        case = case_type(method)
        result = unittest.TestResult()
        returned = case.run(result)
        self.assertIs(returned, result)
        self.assertEqual(result.testsRun, 1)
        return case, result

    def assert_success(self, result):
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])
        self.assertTrue(result.wasSuccessful())

    def test_lifecycle_and_mixed_cleanups(self):
        events = []

        class Case(AsyncioTestCase):
            def setUp(self):
                self.assertIs(self.loop, asyncio.get_event_loop())
                self.assertTrue(self.loop.get_debug())
                events.append('setup')
                self.addCleanup(events.append, 'sync cleanup')

            async def asyncSetUp(self):
                events.append('async setup')
                self.addCleanup(lambda: self.cleanup('async cleanup'))

            async def cleanup(self, value):
                await asyncio.sleep(0)
                events.append(value)

            async def test_body(self):
                self.assertIs(self.loop, asyncio.get_running_loop())
                events.append('test')

            async def asyncTearDown(self):
                events.append('async teardown')

            def tearDown(self):
                events.append('teardown')

        case, result = self.run_case(Case)
        self.assert_success(result)
        self.assertEqual(events, ['setup', 'async setup', 'test', 'async teardown',
                                  'teardown', 'async cleanup', 'sync cleanup'])
        self.assertTrue(case.loop.is_closed())

    def test_setup_failure_still_runs_cleanups(self):
        events = []

        class Case(AsyncioTestCase):
            async def asyncSetUp(self):
                self.addCleanup(events.append, 'cleanup')
                raise ValueError('setup failed')

            async def test_body(self):
                events.append('test')

            async def asyncTearDown(self):
                events.append('teardown')

        _, result = self.run_case(Case)
        self.assertEqual(len(result.errors), 1)
        self.assertIn('ValueError: setup failed', result.errors[0][1])
        self.assertEqual(events, ['cleanup'])

    def test_teardown_and_cleanup_errors_are_both_reported(self):
        events = []

        class Case(AsyncioTestCase):
            async def test_body(self):
                self.addCleanup(events.append, 'last cleanup')
                self.addCleanup(self.failing_cleanup)

            async def asyncTearDown(self):
                raise ValueError('teardown failed')

            async def failing_cleanup(self):
                raise RuntimeError('cleanup failed')

        _, result = self.run_case(Case)
        self.assertEqual(len(result.errors), 2)
        self.assertIn('ValueError: teardown failed', result.errors[0][1])
        self.assertIn('RuntimeError: cleanup failed', result.errors[1][1])
        self.assertEqual(events, ['last cleanup'])

    def test_reporting(self):
        class Case(AsyncioTestCase):
            def test_sync(self):
                self.assertIs(self.loop, asyncio.get_event_loop())

            async def test_failure(self):
                self.fail('expected assertion')

            @unittest.skip('disabled case')
            async def test_skip(self):
                self.fail('must not run')

            @unittest.expectedFailure
            async def test_expected_failure(self):
                self.fail('expected assertion')

            @unittest.expectedFailure
            async def test_unexpected_success(self):
                pass

            async def test_subtests(self):
                for value in (0, 1):
                    with self.subTest(value=value):
                        self.assertEqual(value, 0)

        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Case)
        result = unittest.TestResult()
        suite.run(result)
        self.assertEqual(result.testsRun, 6)
        self.assertEqual(len(result.failures), 2)
        self.assertEqual(result.errors, [])
        self.assertEqual([reason for _, reason in result.skipped], ['disabled case'])
        self.assertEqual(len(result.expectedFailures), 1)
        self.assertEqual(len(result.unexpectedSuccesses), 1)
        self.assertFalse(result.wasSuccessful())

    def test_class_skip_returns_result(self):
        @unittest.skip('disabled class')
        class Case(AsyncioTestCase):
            def setUp(self):
                raise AssertionError('setup must not run')

            async def test_body(self):
                raise AssertionError('test must not run')

        _, result = self.run_case(Case)
        self.assertEqual([reason for _, reason in result.skipped], ['disabled class'])

    def test_cancellation_is_an_error_and_cleanup_runs(self):
        events = []

        class Case(AsyncioTestCase):
            async def test_body(self):
                self.addCleanup(events.append, 'cleanup')
                raise asyncio.CancelledError()

            async def asyncTearDown(self):
                events.append('teardown')

        _, result = self.run_case(Case)
        self.assertEqual(len(result.errors), 1)
        self.assertIn('CancelledError', result.errors[0][1])
        self.assertNotIn('TimeoutError', result.errors[0][1])
        self.assertEqual(events, ['teardown', 'cleanup'])

    def test_timeout_is_an_error_even_if_cancellation_is_suppressed(self):
        events = []

        class Case(AsyncioTestCase):
            TIMEOUT = 0.02

            async def test_body(self):
                self.addCleanup(events.append, 'cleanup')
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    events.append('cancelled')

        _, result = self.run_case(Case)
        self.assertEqual(len(result.errors), 1)
        self.assertIn('TimeoutError', result.errors[0][1])
        self.assertEqual(events, ['cancelled', 'cleanup'])

    def test_each_async_phase_has_its_own_deadline(self):
        events = []

        class Case(AsyncioTestCase):
            TIMEOUT = 0.5

            async def asyncSetUp(self):
                await asyncio.sleep(0.3)

            async def test_body(self):
                self.addCleanup(self.cleanup)
                await asyncio.sleep(0.3)
                events.append('test')

            async def asyncTearDown(self):
                await asyncio.sleep(0.3)
                events.append('teardown')

            async def cleanup(self):
                await asyncio.sleep(0.3)
                events.append('cleanup')

        _, result = self.run_case(Case)
        self.assert_success(result)
        self.assertEqual(events, ['test', 'teardown', 'cleanup'])

    def test_setup_teardown_and_cleanup_timeouts(self):
        for phase in ('asyncSetUp', 'asyncTearDown', 'cleanup'):
            with self.subTest(phase=phase):
                events = []

                class Case(AsyncioTestCase):
                    TIMEOUT = 0.02

                    def setUp(self):
                        self.addCleanup(events.append, 'final cleanup')
                        if phase == 'cleanup':
                            self.addCleanup(self.block)

                    async def block(self):
                        await asyncio.Event().wait()

                    async def test_body(self):
                        events.append('test')

                if phase != 'cleanup':
                    setattr(Case, phase, Case.block)
                _, result = self.run_case(Case)
                self.assertEqual(len(result.errors), 1)
                self.assertIn('TimeoutError', result.errors[0][1])
                self.assertEqual(events, ['final cleanup'] if phase == 'asyncSetUp'
                                 else ['test', 'final cleanup'])

    def test_async_context_is_shared_between_phases(self):
        value = contextvars.ContextVar('runner_test', default='outside')
        events = []

        class Case(AsyncioTestCase):
            async def asyncSetUp(self):
                self.token = value.set('setup')
                self.addCleanup(self.cleanup)

            async def test_body(self):
                self.assertEqual(value.get(), 'setup')
                value.set('test')

            async def asyncTearDown(self):
                self.assertEqual(value.get(), 'test')
                value.set('teardown')

            async def cleanup(self):
                events.append(value.get())
                value.reset(self.token)

        _, result = self.run_case(Case)
        self.assert_success(result)
        self.assertEqual(events, ['teardown'])
        self.assertEqual(value.get(), 'outside')

    def test_pending_tasks_and_async_generators_are_closed(self):
        events = []

        class Case(AsyncioTestCase):
            async def background(self):
                try:
                    await asyncio.Event().wait()
                finally:
                    events.append('task stopped')

            async def values(self):
                try:
                    yield 1
                finally:
                    events.append('generator closed')

            async def test_body(self):
                self.task = asyncio.create_task(self.background())
                self.generator = self.values()
                self.assertEqual(await self.generator.__anext__(), 1)
                await asyncio.sleep(0)

        case, result = self.run_case(Case)
        self.assert_success(result)
        self.assertTrue(case.task.cancelled())
        self.assertCountEqual(events, ['task stopped', 'generator closed'])

    def test_awaitable_cleanup_and_async_callable(self):
        events = []

        class Cleanup:
            async def __call__(self):
                events.append('callable')

        class Case(AsyncioTestCase):
            def future_cleanup(self):
                future = self.loop.create_future()

                def finish():
                    events.append('future')
                    future.set_result(None)

                self.loop.call_soon(finish)
                return future

            async def test_body(self):
                self.addCleanup(Cleanup())
                self.addCleanup(events.append, 'sync')
                self.addCleanup(self.future_cleanup)

        _, result = self.run_case(Case)
        self.assert_success(result)
        self.assertEqual(events, ['future', 'sync', 'callable'])

    def test_async_generator_is_closed_without_background_tasks(self):
        events = []

        class Case(AsyncioTestCase):
            async def values(self):
                try:
                    yield 1
                finally:
                    events.append('generator closed')

            async def test_body(self):
                self.generator = self.values()
                self.assertEqual(await self.generator.__anext__(), 1)

        _, result = self.run_case(Case)
        self.assert_success(result)
        self.assertEqual(events, ['generator closed'])

    def test_background_shutdown_errors_remain_visible(self):
        errors = []

        class Case(AsyncioTestCase):
            async def background(self):
                try:
                    await asyncio.Event().wait()
                finally:
                    raise ValueError('background shutdown failed')

            async def test_body(self):
                self.loop.set_exception_handler(lambda loop, context: errors.append(context))
                self.task = asyncio.create_task(self.background())
                await asyncio.sleep(0)

        case, result = self.run_case(Case)
        self.assert_success(result)
        self.assertEqual(len(errors), 1)
        self.assertIs(errors[0]['task'], case.task)
        self.assertIsInstance(errors[0]['exception'], ValueError)
        self.assertEqual(str(errors[0]['exception']), 'background shutdown failed')

    def test_virtual_clock_does_not_trigger_real_time_deadline(self):
        events = []

        class Case(AdvanceTimeTestCase):
            TIMEOUT = 1
            LOOP_SLOW_CALLBACK_DURATION = float('inf')

            async def test_body(self):
                self.loop.call_later(100, events.append, 'timer fired')
                await self.advance(99)
                self.assertEqual(events, [])
                await self.advance(1)
                self.assertEqual(events, ['timer fired'])
                await self.advance(10000)

        _, result = self.run_case(Case)
        self.assert_success(result)

    def test_timeout_can_be_disabled(self):
        class Case(AsyncioTestCase):
            TIMEOUT = 0

            async def test_body(self):
                await asyncio.sleep(0)

        case, result = self.run_case(Case)
        self.assert_success(result)
        self.assertTrue(case.loop.is_closed())
