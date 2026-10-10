import asyncio

from lbry.wallet.stream import StreamController
from lbry.wallet.tasks import TaskGroup
from lbry.testcase import AsyncioTestCase


class StreamControllerTestCase(AsyncioTestCase):
    async def test_waits_for_async_listeners(self):
        controller = StreamController()
        started = asyncio.Event()
        release = asyncio.Event()
        events = []

        async def listener(value):
            started.set()
            await release.wait()
            events.append(value)

        controller.stream.listen(on_data=listener)
        notification = controller.add('transaction')
        await started.wait()
        self.assertFalse(notification.done())
        release.set()
        done, pending = await notification
        self.assertEqual(events, ['transaction'])
        self.assertFalse(pending)
        self.assertEqual(len(done), 1)
        self.assertIsNone(done.pop().result())

    async def test_async_listener_failure_is_available_to_caller(self):
        controller = StreamController()

        async def fail(value):
            raise ValueError(value)

        controller.stream.listen(on_data=fail)
        done, pending = await controller.add('listener failed')
        self.assertFalse(pending)
        with self.assertRaisesRegex(ValueError, 'listener failed'):
            done.pop().result()

    def test_non_unique_events(self):
        events = []
        controller = StreamController()
        controller.stream.listen(on_data=events.append)
        controller.add("yo")
        controller.add("yo")
        self.assertListEqual(events, ["yo", "yo"])

    def test_unique_events(self):
        events = []
        controller = StreamController(merge_repeated_events=True)
        controller.stream.listen(on_data=events.append)
        controller.add("yo")
        controller.add("yo")
        self.assertListEqual(events, ["yo"])


class TaskGroupTestCase(AsyncioTestCase):

    async def test_cancel_sets_it_done(self):
        group = TaskGroup()
        group.cancel()
        self.assertTrue(group.done.is_set())
